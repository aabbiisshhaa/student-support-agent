import argparse
import io
import logging
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from src import app
from src.agent.memory import SessionMemoryManager
from src.agent.orchestrator import DEFAULT_STUDENT_ID, SupportAgentOrchestrator
from src.telemetry.tracker import TelemetryTracker
from src.tools.ticket_tool import get_ticket

TICKET_REQUEST = "Please create a support ticket for my portal login issue."


class AppTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)

        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

        database_url = "sqlite:///" + (Path(self.workspace.name) / "tickets.db").as_posix()
        environment = patch.dict(os.environ, {"DATABASE_URL": database_url})
        environment.start()
        self.addCleanup(environment.stop)

        model_patch = patch("src.agent.orchestrator.GeminiModel", side_effect=ValueError("no api key"))
        model_patch.start()
        self.addCleanup(model_patch.stop)

        tracker_patch = patch(
            "src.agent.orchestrator.TelemetryTracker",
            side_effect=lambda: TelemetryTracker(log_dir=self.workspace.name),
        )
        tracker_patch.start()
        self.addCleanup(tracker_patch.stop)

        self.memory = SessionMemoryManager(persist=False)

    def sample_ticket(self, **overrides) -> dict:
        ticket = {
            "ticket_id": "TCK-000042",
            "student_id": DEFAULT_STUDENT_ID,
            "case_id": None,
            "summary": "Portal login fails after password reset",
            "original_message": "I cannot log in to the portal after resetting my password.",
            "category": "administrative",
            "priority": "medium",
            "queue": "General Administration Queue",
            "status": "open",
            "created_at": "2026-09-25T10:15:30.123456+00:00",
        }
        ticket.update(overrides)
        return ticket


class TestSessionTokens(AppTestCase):
    def test_new_session_issues_a_token_for_the_default_student(self) -> None:
        token, student_id, resumed = app.open_session(self.memory, None, None)

        self.assertRegex(token, app.SESSION_TOKEN_PATTERN)
        self.assertEqual(student_id, DEFAULT_STUDENT_ID)
        self.assertFalse(resumed)
        self.assertEqual(self.memory.get_session(token).student_ref, DEFAULT_STUDENT_ID)

    def test_new_session_is_bound_to_the_requested_student(self) -> None:
        token, student_id, _ = app.open_session(self.memory, "2300798765", None)

        self.assertEqual(student_id, "2300798765")
        self.assertEqual(self.memory.get_session(token).student_ref, "2300798765")

    def test_each_new_session_gets_a_different_token(self) -> None:
        first, _, _ = app.open_session(self.memory, None, None)
        second, _, _ = app.open_session(self.memory, None, None)

        self.assertNotEqual(first, second)

    def test_resume_restores_the_student_stored_with_the_session(self) -> None:
        token, _, _ = app.open_session(self.memory, "2300798765", None)

        resumed_token, student_id, resumed = app.open_session(self.memory, None, token)

        self.assertEqual(resumed_token, token)
        self.assertEqual(student_id, "2300798765")
        self.assertTrue(resumed)

    def test_resume_accepts_the_matching_student_number(self) -> None:
        token, _, _ = app.open_session(self.memory, "2300798765", None)

        self.assertTrue(app.open_session(self.memory, "2300798765", token)[2])

    def test_resume_rejects_an_unknown_token(self) -> None:
        with self.assertRaises(app.SessionError):
            app.open_session(self.memory, None, "STU-999")

    def test_resume_rejects_a_token_that_is_not_a_session_token(self) -> None:
        with patch.object(self.memory, "get_session") as get_session:
            for token in ("../../secrets", "session-live-01", "STU-1", "stu-001", ""):
                with self.subTest(token=token):
                    with self.assertRaises(app.SessionError):
                        app.open_session(self.memory, None, token)

        get_session.assert_not_called()

    def test_resume_rejects_another_students_session(self) -> None:
        token, _, _ = app.open_session(self.memory, "2300798765", None)

        with self.assertRaises(app.SessionError):
            app.open_session(self.memory, DEFAULT_STUDENT_ID, token)

    def test_resume_rejects_a_closed_session(self) -> None:
        token, _, _ = app.open_session(self.memory, None, None)
        self.memory.close_session(token)

        with self.assertRaises(app.SessionError):
            app.open_session(self.memory, None, token)

    def test_student_number_argument_is_validated(self) -> None:
        self.assertEqual(app.student_id_arg("2300712345"), "2300712345")
        with self.assertRaises(argparse.ArgumentTypeError):
            app.student_id_arg("not a student!")

    def test_invalid_student_number_flag_stops_the_program(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            app.parse_args(["--student-id", "??"])


class TestConversationHistory(AppTestCase):
    def test_empty_session_has_no_history_to_display(self) -> None:
        token, _, _ = app.open_session(self.memory, None, None)

        self.assertEqual(app.format_history(self.memory.get_session(token)), "")

    def test_prior_turns_are_listed_in_order_with_speaker_labels(self) -> None:
        token, _, _ = app.open_session(self.memory, None, None)
        self.memory.add_turn(token, "user", "show my timetable")
        self.memory.add_turn(token, "assistant", "Here is your **verified** timetable")

        lines = app.format_history(self.memory.get_session(token)).splitlines()

        self.assertEqual(
            lines,
            [
                f"--- Previous conversation (session {token}) ---",
                "You: show my timetable",
                "Agent: Here is your verified timetable",
                "--- End of previous conversation ---",
            ],
        )

    def test_history_says_when_older_turns_were_summarised(self) -> None:
        memory = SessionMemoryManager(window_size=2, persist=False)
        token = memory.create_session(student_ref=DEFAULT_STUDENT_ID)
        for index in range(3):
            memory.add_turn(token, "user", f"question {index}")

        history = app.format_history(memory.get_session(token))

        self.assertIn("1 earlier message(s) are summarised and not shown", history)
        self.assertNotIn("question 0", history)
        self.assertIn("question 2", history)


class TestToolStatusIndicators(AppTestCase):
    def capture_status(self, event: dict) -> str:
        output = io.StringIO()
        with redirect_stdout(output):
            app.print_status(event)
        return output.getvalue().strip()

    def test_running_tool_is_announced(self) -> None:
        line = self.capture_status({"event": "tool_start", "tool": "get_course_schedule"})

        self.assertEqual(line, "[..] Looking up your timetable")

    def test_finished_tool_reports_success_and_latency(self) -> None:
        line = self.capture_status(
            {"event": "tool_end", "tool": "create_support_ticket", "status": "ok", "latency_ms": 12.6}
        )

        self.assertEqual(line, "[ok] Support ticket created (13 ms)")

    def test_failed_tool_is_flagged(self) -> None:
        line = self.capture_status(
            {"event": "tool_end", "tool": "get_course_schedule", "status": "error", "latency_ms": 1.0}
        )

        self.assertEqual(line, "[!!] Timetable lookup failed")

    def test_policy_search_has_its_own_labels(self) -> None:
        start = self.capture_status({"event": "tool_start", "tool": "retriever"})
        end = self.capture_status({"event": "tool_end", "tool": "retriever", "status": "ok", "latency_ms": 5})

        self.assertEqual(start, "[..] Searching university policy documents")
        self.assertEqual(end, "[ok] Policy search complete (5 ms)")

    def test_unregistered_tool_still_gets_a_readable_label(self) -> None:
        line = self.capture_status({"event": "tool_start", "tool": "new_tool"})

        self.assertEqual(line, "[..] Running new_tool")


class TestTicketConfirmation(AppTestCase):
    def test_confirmation_has_headline_details_and_next_steps(self) -> None:
        text = app.format_ticket_confirmation(self.sample_ticket())

        self.assertTrue(text.startswith("Your request has been escalated"))
        self.assertIn("Ticket confirmation", text)
        self.assertIn("What happens next", text)
        for expected in (
            "TCK-000042",
            "open",
            "General Administration Queue",
            "administrative",
            "medium",
            DEFAULT_STUDENT_ID,
            "2026-09-25 10:15 UTC",
            "Portal login fails after password reset",
        ):
            self.assertIn(expected, text)
        self.assertIn("Quote TCK-000042 in any follow-up", text)

    def test_confirmation_lists_each_detail_on_its_own_row(self) -> None:
        lines = app.format_ticket_confirmation(self.sample_ticket()).splitlines()

        self.assertIn("  Ticket ID  TCK-000042", lines)
        self.assertIn("  Queue      General Administration Queue", lines)
        self.assertIn("  Priority   medium", lines)

    def test_long_summary_is_wrapped_and_aligned(self) -> None:
        summary = "Portal login keeps failing after every password reset attempt " * 3
        lines = app.format_ticket_confirmation(self.sample_ticket(summary=summary.strip())).splitlines()

        self.assertLessEqual(max(len(line) for line in lines), app.TICKET_CARD_WIDTH)
        summary_start = next(index for index, line in enumerate(lines) if line.startswith("  Summary"))
        self.assertTrue(lines[summary_start + 1].startswith(" " * 12))

    def test_timestamp_is_shown_in_utc(self) -> None:
        text = app.format_ticket_confirmation(self.sample_ticket(created_at="2026-09-25T13:15:30+03:00"))

        self.assertIn("2026-09-25 10:15 UTC", text)

    def test_unparseable_timestamp_is_shown_as_is(self) -> None:
        text = app.format_ticket_confirmation(self.sample_ticket(created_at="yesterday"))

        self.assertIn("yesterday", text)

    def test_reply_uses_the_confirmation_when_a_ticket_was_created(self) -> None:
        ticket = self.sample_ticket()
        result = {
            "status": "success",
            "response": "Your support ticket **TCK-999999** has been registered.",
            "escalation_required": True,
            "tool_calls": [{"tool": "create_support_ticket", "status": "ok", "result": ticket}],
        }

        reply = app.render_reply(result)

        self.assertEqual(reply, f"Agent: {app.format_ticket_confirmation(ticket)}")
        self.assertNotIn("TCK-999999", reply)

    def test_reply_falls_back_to_the_agent_text_when_the_ticket_failed(self) -> None:
        result = {
            "status": "tool_error",
            "response": "I could not complete that request: summary is too short.",
            "escalation_required": False,
            "tool_calls": [{"tool": "create_support_ticket", "status": "error", "result": {"error": "x"}}],
        }

        self.assertEqual(app.render_reply(result), f"Agent: {result['response']}")

    def test_reply_flags_escalations_that_have_no_ticket(self) -> None:
        result = {"status": "refused", "response": "Not permitted.", "escalation_required": True, "tool_calls": []}

        reply = app.render_reply(result)

        self.assertEqual(reply.splitlines(), ["Agent: Not permitted.", f"Agent: {app.FLAGGED_NOTICE}"])

    def test_reply_strips_bold_markers(self) -> None:
        result = {"status": "success", "response": "**Monday** at **09:00**", "escalation_required": False}

        self.assertEqual(app.render_reply(result), "Agent: Monday at 09:00")


class TestProcessTurn(AppTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.agent = SupportAgentOrchestrator(memory_manager=self.memory)
        self.token, self.student_id, _ = app.open_session(self.memory, None, None)

    def test_ticket_request_prints_the_confirmation_with_the_created_id(self) -> None:
        events = []

        reply = app.process_turn(self.agent, self.token, self.student_id, TICKET_REQUEST, on_event=events.append)

        self.assertIn("TCK-000001", reply)
        self.assertIn("Ticket confirmation", reply)
        self.assertIn("What happens next", reply)
        self.assertEqual(get_ticket("TCK-000001")["student_id"], self.student_id)
        self.assertEqual([event["event"] for event in events], ["tool_start", "tool_end"])

    def test_conversation_turns_are_saved_under_the_session_token(self) -> None:
        app.process_turn(self.agent, self.token, self.student_id, "show my timetable", on_event=None)

        roles = [message.role for message in self.memory.get_session(self.token).messages]

        self.assertEqual(roles, ["user", "assistant"])

    def test_history_keeps_the_confirmation_the_student_saw_not_the_model_wording(self) -> None:
        model_wording = "I created TCK-000001. Our support team will reach out to you shortly."

        with patch.object(self.agent, "_synthesize_response", return_value=model_wording):
            reply = app.process_turn(self.agent, self.token, self.student_id, TICKET_REQUEST, on_event=None)

        stored = self.memory.get_session(self.token).messages[-1]
        self.assertEqual(stored.role, "assistant")
        self.assertEqual(stored.content, app.format_ticket_confirmation(get_ticket("TCK-000001")))
        self.assertNotIn("reach out", stored.content)
        self.assertEqual(reply, f"Agent: {stored.content}")

    def test_history_shows_the_confirmation_without_a_doubled_speaker_label(self) -> None:
        app.process_turn(self.agent, self.token, self.student_id, TICKET_REQUEST, on_event=None)

        history = app.format_history(self.memory.get_session(self.token))

        self.assertIn("Agent: Your request has been escalated to university support staff.", history)
        self.assertNotIn("Agent: Agent:", history)
        self.assertIn("Ticket ID  TCK-000001", history)

    def test_non_ticket_turn_keeps_the_agent_text_in_history(self) -> None:
        app.process_turn(self.agent, self.token, self.student_id, "show my timetable", on_event=None)

        stored = self.memory.get_session(self.token).messages[-1]

        self.assertIn("Database Systems II", stored.content)
        self.assertNotIn("Ticket confirmation", stored.content)

    def test_failed_ticket_leaves_the_agent_text_in_history(self) -> None:
        failure = {"error": "summary must be a string between 10 and 500 characters"}

        with patch.object(self.agent, "_dispatch_tool", return_value=failure):
            app.process_turn(self.agent, self.token, self.student_id, TICKET_REQUEST, on_event=None)

        stored = self.memory.get_session(self.token).messages[-1]

        self.assertIn("I could not complete that request", stored.content)
        self.assertNotIn("Ticket confirmation", stored.content)

    def test_boundary_request_is_refused_recorded_and_never_reaches_the_agent(self) -> None:
        with patch.object(self.agent, "run") as run:
            reply = app.process_turn(self.agent, self.token, self.student_id, "Can you waive my fees?")

        run.assert_not_called()
        self.assertIn("Finance/Accounts Office", reply)
        self.assertIn(app.FLAGGED_NOTICE, reply)
        self.assertEqual(
            [message.role for message in self.memory.get_session(self.token).messages],
            ["user", "assistant"],
        )
        self.assertIsNone(get_ticket("TCK-000001"))


class TestRunCli(AppTestCase):
    def run_cli(self, inputs: list, argv: list[str] | None = None) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("builtins.input", side_effect=inputs), redirect_stdout(stdout), redirect_stderr(stderr):
            code = app.run_cli(argv or [], memory=self.memory)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_new_session_shows_token_status_lines_and_reply(self) -> None:
        code, output, _ = self.run_cli(["show my timetable", "exit"])

        self.assertEqual(code, 0)
        self.assertIn(f"Student: {DEFAULT_STUDENT_ID} | Session token: STU-001 (new)", output)
        self.assertIn("[..] Looking up your timetable", output)
        self.assertIn("[ok] Timetable retrieved", output)
        self.assertIn("Database Systems II", output)
        self.assertIn("Session STU-001 saved. Resume with: python src/app.py --session STU-001", output)
        self.assertNotIn("**", output)

    def test_ticket_request_prints_the_multi_part_confirmation(self) -> None:
        _, output, _ = self.run_cli([TICKET_REQUEST, "exit"])

        self.assertIn("[..] Creating your support ticket", output)
        self.assertIn("[ok] Support ticket created", output)
        self.assertIn("Ticket ID  TCK-000001", output)
        self.assertIn("What happens next", output)

    def test_resumed_session_displays_prior_turns_before_the_prompt(self) -> None:
        self.run_cli(["show my timetable", "exit"])

        code, output, _ = self.run_cli(["exit"], ["--session", "STU-001"])

        self.assertEqual(code, 0)
        self.assertIn("Session token: STU-001 (resumed)", output)
        self.assertIn("--- Previous conversation (session STU-001) ---", output)
        self.assertIn("You: show my timetable", output)
        self.assertIn("Agent: Here is your verified lecture timetable:", output)

    def test_resumed_session_keeps_the_student_it_was_created_for(self) -> None:
        self.run_cli(["exit"], ["--student-id", "2300798765"])

        _, output, _ = self.run_cli(["show my timetable", "exit"], ["--session", "STU-001"])

        self.assertIn("Student: 2300798765", output)
        self.assertIn("Discrete Mathematics", output)

    def test_invalid_token_exits_with_an_error_before_starting(self) -> None:
        code, output, error = self.run_cli([], ["--session", "../../etc/passwd"])

        self.assertEqual(code, 1)
        self.assertIn("Invalid session token", error)
        self.assertNotIn("Student Support Agent", output)

    def test_session_history_and_new_commands(self) -> None:
        _, output, _ = self.run_cli(["/history", "show my timetable", "/history", "/session", "/new", "/session", "exit"])

        self.assertIn("No earlier turns in this session yet.", output)
        self.assertIn("You: show my timetable", output)
        self.assertIn("Session token: STU-001", output)
        self.assertIn("Started a new session. Session token: STU-002", output)
        self.assertIn("Session STU-002 saved.", output)

    def test_help_and_unknown_commands(self) -> None:
        _, output, _ = self.run_cli(["/help", "/bogus now", "exit"])

        self.assertIn("/history   show the earlier turns of this session", output)
        self.assertIn("Unknown command '/bogus'", output)

    def test_failed_lookup_shows_a_failure_indicator(self) -> None:
        _, output, _ = self.run_cli(["show my timetable", "exit"], ["--student-id", "9999999999"])

        self.assertIn("[!!] Timetable lookup failed", output)
        self.assertIn("I could not complete that request", output)

    def test_end_of_input_leaves_cleanly(self) -> None:
        code, output, _ = self.run_cli([EOFError], [])

        self.assertEqual(code, 0)
        self.assertIn("Session STU-001 saved.", output)

    def test_blank_lines_are_ignored(self) -> None:
        _, output, _ = self.run_cli(["   ", "exit"])

        self.assertNotIn("Agent:", output)

    def test_notice_is_shown_when_the_live_model_is_unavailable(self) -> None:
        _, output, _ = self.run_cli(["exit"])

        self.assertIn("the live AI model is unavailable", output)


if __name__ == "__main__":
    unittest.main()
