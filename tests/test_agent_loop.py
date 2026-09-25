import logging
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agent.memory import SessionMemoryManager
from src.agent.orchestrator import DEFAULT_STUDENT_ID, SupportAgentOrchestrator
from src.telemetry.tracker import TelemetryTracker
from src.tools.ticket_tool import (
    TicketCategory,
    TicketPriority,
    TicketValidationError,
    create_support_ticket,
    get_ticket,
)
from src.tools.timetable_tool import get_course_schedule

TICKET_ID_PATTERN = re.compile(r"^TCK-\d{6}$")
TICKET_REQUEST = "Please create a support ticket for my portal login issue."


class IsolatedToolsTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)

        database_url = "sqlite:///" + (Path(self.workspace.name) / "tickets.db").as_posix()
        environment = patch.dict(os.environ, {"DATABASE_URL": database_url})
        environment.start()
        self.addCleanup(environment.stop)

    def ticket_arguments(self, **overrides) -> dict:
        arguments = {
            "student_id": DEFAULT_STUDENT_ID,
            "summary": "Cannot open the student portal",
            "original_message": "I cannot open the student portal since Monday.",
            "category": "administrative",
            "priority": "medium",
            "student_confirmed": True,
        }
        arguments.update(overrides)
        return arguments


class AgentLoopTestCase(IsolatedToolsTestCase):
    def setUp(self) -> None:
        super().setUp()

        logging.disable(logging.CRITICAL)
        self.addCleanup(logging.disable, logging.NOTSET)

        model_patch = patch("src.agent.orchestrator.GeminiModel", side_effect=ValueError("no api key"))
        model_patch.start()
        self.addCleanup(model_patch.stop)

        tracker_patch = patch(
            "src.agent.orchestrator.TelemetryTracker",
            side_effect=lambda: TelemetryTracker(log_dir=self.workspace.name),
        )
        tracker_patch.start()
        self.addCleanup(tracker_patch.stop)

        self.agent = SupportAgentOrchestrator(memory_manager=SessionMemoryManager(persist=False))


class TestTicketCreationFromAgentLoop(AgentLoopTestCase):
    def test_ticket_request_returns_created_ticket_payload(self) -> None:
        result = self.agent.run("session-ticket", TICKET_REQUEST)

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["escalation_required"])

        ticket_calls = [call for call in result["tool_calls"] if call["tool"] == "create_support_ticket"]
        self.assertEqual(len(ticket_calls), 1)
        self.assertEqual(ticket_calls[0]["status"], "ok")

        ticket = ticket_calls[0]["result"]
        self.assertRegex(ticket["ticket_id"], TICKET_ID_PATTERN)
        self.assertEqual(ticket["student_id"], DEFAULT_STUDENT_ID)
        self.assertEqual(ticket["category"], "administrative")
        self.assertEqual(ticket["priority"], "medium")
        self.assertEqual(ticket["status"], "open")
        self.assertEqual(ticket["queue"], "General Administration Queue")
        self.assertEqual(ticket["original_message"], TICKET_REQUEST)
        self.assertIn(ticket["ticket_id"], result["response"])

    def test_created_ticket_payload_matches_the_stored_record(self) -> None:
        result = self.agent.run("session-ticket", TICKET_REQUEST)

        ticket = result["tool_calls"][0]["result"]
        self.assertEqual(get_ticket(ticket["ticket_id"]), ticket)

    def test_ticket_tool_is_called_with_the_six_required_arguments(self) -> None:
        with patch("src.agent.orchestrator.create_support_ticket", wraps=create_support_ticket) as tool:
            self.agent.run("session-ticket", TICKET_REQUEST)

        tool.assert_called_once_with(
            student_id=DEFAULT_STUDENT_ID,
            summary=TICKET_REQUEST,
            original_message=TICKET_REQUEST,
            category="administrative",
            priority="medium",
            student_confirmed=True,
        )

    def test_ticket_uses_the_student_number_of_the_session(self) -> None:
        result = self.agent.run("session-ticket", TICKET_REQUEST, student_id="2300798765")

        self.assertEqual(result["tool_calls"][0]["result"]["student_id"], "2300798765")

    def test_short_escalation_message_still_creates_a_ticket(self) -> None:
        result = self.agent.run("session-short", "escalate")

        call = result["tool_calls"][0]
        self.assertEqual(call["status"], "ok")
        self.assertRegex(call["result"]["ticket_id"], TICKET_ID_PATTERN)
        self.assertEqual(call["result"]["summary"], "Student request: escalate")
        self.assertEqual(call["result"]["original_message"], "escalate")

    def test_each_ticket_receives_a_distinct_sequential_id(self) -> None:
        first = self.agent.run("session-one", TICKET_REQUEST)
        second = self.agent.run("session-two", "Please lodge a complaint about the library opening hours")

        ticket_ids = [
            first["tool_calls"][0]["result"]["ticket_id"],
            second["tool_calls"][0]["result"]["ticket_id"],
        ]
        self.assertEqual(ticket_ids, ["TCK-000001", "TCK-000002"])

    def test_refused_request_creates_no_ticket(self) -> None:
        result = self.agent.run("session-refused", "I want a grade change, please open a ticket")

        self.assertEqual(result["status"], "refused")
        self.assertEqual(result["tool_calls"], [])
        self.assertIsNone(get_ticket("TCK-000001"))

    def test_status_events_bracket_the_ticket_tool_call(self) -> None:
        events = []

        self.agent.run("session-events", TICKET_REQUEST, on_event=events.append)

        self.assertEqual(
            [(event["event"], event["tool"]) for event in events],
            [("tool_start", "create_support_ticket"), ("tool_end", "create_support_ticket")],
        )
        self.assertEqual(events[1]["status"], "ok")
        self.assertGreaterEqual(events[1]["latency_ms"], 0)


class TestTicketArgumentEnums(AgentLoopTestCase):
    def test_dispatch_normalises_ticket_enums_to_lowercase(self) -> None:
        ticket = self.agent._dispatch_tool(
            "create_support_ticket",
            self.ticket_arguments(category="Administrative", priority=TicketPriority.HIGH),
        )

        self.assertEqual(ticket["category"], "administrative")
        self.assertEqual(ticket["priority"], "high")
        self.assertIs(type(ticket["category"]), str)
        self.assertIs(type(ticket["priority"]), str)

    def test_dispatch_reports_an_unknown_category_as_a_tool_error(self) -> None:
        outcome = self.agent._dispatch_tool(
            "create_support_ticket",
            self.ticket_arguments(category="finance"),
        )

        self.assertIn("Invalid category", outcome["error"])

    def test_tool_rejects_capitalised_category(self) -> None:
        with self.assertRaises(TicketValidationError):
            create_support_ticket(**self.ticket_arguments(category="Administrative"))

    def test_tool_rejects_uppercase_priority(self) -> None:
        with self.assertRaises(TicketValidationError):
            create_support_ticket(**self.ticket_arguments(priority="HIGH"))

    def test_tool_accepts_enum_members_and_stores_plain_lowercase_values(self) -> None:
        ticket = create_support_ticket(
            **self.ticket_arguments(category=TicketCategory.POLICY, priority=TicketPriority.LOW)
        )

        self.assertEqual(ticket["category"], "policy")
        self.assertEqual(ticket["priority"], "low")
        self.assertEqual(ticket["queue"], "Academic Policy Queue")
        self.assertIs(type(ticket["category"]), str)
        self.assertEqual(get_ticket(ticket["ticket_id"])["category"], "policy")


class TestTimetableBindingFromAgentLoop(AgentLoopTestCase):
    def test_default_student_number_has_a_timetable(self) -> None:
        self.assertEqual(DEFAULT_STUDENT_ID, "2300712345")
        self.assertTrue(get_course_schedule(DEFAULT_STUDENT_ID))

    def test_schedule_uses_the_student_number_of_the_session(self) -> None:
        result = self.agent.run("session-schedule", "What is my lecture schedule?", student_id="2300798765")

        call = result["tool_calls"][0]
        self.assertEqual(call["tool"], "get_course_schedule")
        self.assertEqual(call["params"]["student_id"], "2300798765")
        self.assertEqual({entry["course_code"] for entry in call["result"]}, {"BSE4104", "MTH2201"})

    def test_schedule_binds_the_course_code_found_in_the_question(self) -> None:
        result = self.agent.run("session-schedule", "When is the lecture schedule for csc3103?")

        call = result["tool_calls"][0]
        self.assertEqual(call["params"], {"student_id": DEFAULT_STUDENT_ID, "course_code": "CSC3103"})
        self.assertEqual([entry["day"] for entry in call["result"]], ["tuesday"])

    def test_schedule_without_a_course_code_returns_the_full_timetable(self) -> None:
        result = self.agent.run("session-schedule", "show my timetable")

        call = result["tool_calls"][0]
        self.assertIsNone(call["params"]["course_code"])
        self.assertEqual(len(call["result"]), 4)
        self.assertEqual(call["status"], "ok")

    def test_year_in_a_question_is_not_mistaken_for_a_course_code(self) -> None:
        result = self.agent.run("session-schedule", "show my timetable for the 2026 semester")

        self.assertIsNone(result["tool_calls"][0]["params"]["course_code"])

    def test_course_without_lectures_gets_a_plain_answer(self) -> None:
        result = self.agent.run("session-schedule", "lecture schedule for xyz9999")

        self.assertEqual(result["tool_calls"][0]["result"], [])
        self.assertIn("no lectures", result["response"])

    def test_unknown_student_reports_a_tool_error(self) -> None:
        result = self.agent.run("session-unknown", "show my timetable", student_id="9999999999")

        call = result["tool_calls"][0]
        self.assertEqual(call["status"], "error")
        self.assertIn("9999999999", call["result"]["error"])
        self.assertEqual(result["status"], "tool_error")
        self.assertIn("could not complete", result["response"])

    def test_invalid_student_number_reports_a_tool_error(self) -> None:
        result = self.agent.run("session-invalid", "show my timetable", student_id="!!")

        self.assertEqual(result["tool_calls"][0]["status"], "error")
        self.assertIn("Invalid student_id", result["tool_calls"][0]["result"]["error"])


if __name__ == "__main__":
    unittest.main()
