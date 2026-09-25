import argparse
import logging
import re
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.memory import SESSION_ID_PREFIX, SessionMemoryManager, SessionNotFoundError, SessionState
from src.agent.orchestrator import DEFAULT_STUDENT_ID, EventCallback, SupportAgentOrchestrator
from src.tools.timetable_tool import STUDENT_ID_PATTERN
from src.utils.parser import build_boundary_refusal, detect_hard_boundary

SESSION_TOKEN_PATTERN = re.compile(rf"^{re.escape(SESSION_ID_PREFIX)}-\d{{3,}}$")
BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")
TICKET_CARD_WIDTH = 72
FLAGGED_NOTICE = "This has been flagged for a human staff member to review."

TOOL_STATUS_LABELS = {
    "get_course_schedule": (
        "Looking up your timetable",
        "Timetable retrieved",
        "Timetable lookup failed",
    ),
    "create_support_ticket": (
        "Creating your support ticket",
        "Support ticket created",
        "Support ticket could not be created",
    ),
    "retriever": (
        "Searching university policy documents",
        "Policy search complete",
        "Policy search failed",
    ),
}

HELP_HINT = "Type /help for commands, or 'exit' to quit."
HELP_TEXT = """Commands:
  /history   show the earlier turns of this session
  /session   show your session token
  /new       start a new session
  /help      show this list
  exit       leave the agent (your session is saved)"""


class SessionError(Exception):
    pass


def strip_markdown(text: str) -> str:
    return BOLD_PATTERN.sub(r"\1", text)


def student_id_arg(value: str) -> str:
    if not STUDENT_ID_PATTERN.match(value):
        raise argparse.ArgumentTypeError(f"invalid student number: {value!r}")
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="University Student Support Case Agent")
    parser.add_argument(
        "--student-id",
        type=student_id_arg,
        default=None,
        help=f"student number for a new session (default: {DEFAULT_STUDENT_ID})",
    )
    parser.add_argument(
        "--session",
        default=None,
        help="resume an earlier session using its session token",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="show the agent's internal step logs",
    )
    return parser.parse_args(argv)


def open_session(
    memory: SessionMemoryManager,
    student_id: str | None,
    token: str | None,
) -> tuple[str, str, bool]:
    if token is None:
        resolved_student = student_id or DEFAULT_STUDENT_ID
        return memory.create_session(student_ref=resolved_student), resolved_student, False

    if not SESSION_TOKEN_PATTERN.match(token):
        raise SessionError(f"Invalid session token: {token!r}")

    try:
        state = memory.get_session(token)
    except (SessionNotFoundError, ValueError):
        raise SessionError(f"No usable session found for token {token}") from None

    if state.status != "active":
        raise SessionError(f"Session {token} has been closed")
    if student_id and state.student_ref and state.student_ref != student_id:
        raise SessionError(f"Session {token} belongs to a different student")

    return token, state.student_ref or student_id or DEFAULT_STUDENT_ID, True


def format_history(state: SessionState) -> str:
    if not state.messages:
        return ""

    lines = [f"--- Previous conversation (session {state.session_id}) ---"]
    if state.summarized_turns:
        lines.append(f"({state.summarized_turns} earlier message(s) are summarised and not shown)")
    for message in state.messages:
        speaker = "You" if message.role == "user" else "Agent"
        lines.append(f"{speaker}: {strip_markdown(message.content)}")
    lines.append("--- End of previous conversation ---")
    return "\n".join(lines)


def print_status(event: dict[str, Any]) -> None:
    running, done, failed = TOOL_STATUS_LABELS.get(
        event["tool"],
        (f"Running {event['tool']}", f"{event['tool']} finished", f"{event['tool']} failed"),
    )
    if event["event"] == "tool_start":
        print(f"  [..] {running}", flush=True)
    elif event["status"] == "ok":
        print(f"  [ok] {done} ({event['latency_ms']:.0f} ms)", flush=True)
    else:
        print(f"  [!!] {failed}", flush=True)


def format_timestamp(value: str) -> str:
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return value
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def format_ticket_confirmation(ticket: dict[str, Any]) -> str:
    rows = [
        ("Ticket ID", ticket["ticket_id"]),
        ("Status", ticket["status"]),
        ("Queue", ticket["queue"]),
        ("Category", ticket["category"]),
        ("Priority", ticket["priority"]),
        ("Student", ticket["student_id"]),
        ("Logged", format_timestamp(ticket["created_at"])),
        ("Summary", ticket["summary"]),
    ]
    label_width = max(len(label) for label, _ in rows) + 2

    detail_lines = []
    for label, value in rows:
        prefix = f"  {label:<{label_width}}"
        detail_lines.append(
            textwrap.fill(
                str(value),
                width=TICKET_CARD_WIDTH,
                initial_indent=prefix,
                subsequent_indent=" " * len(prefix),
            )
        )

    next_steps = [
        f"1. The {ticket['queue']} will review your ticket.",
        f"2. Quote {ticket['ticket_id']} in any follow-up with support staff.",
    ]

    lines = [
        "Your request has been escalated to university support staff.",
        "",
        "  Ticket confirmation",
        "  -------------------",
        *detail_lines,
        "",
        "  What happens next",
        "  -----------------",
        *(
            textwrap.fill(step, width=TICKET_CARD_WIDTH, initial_indent="  ", subsequent_indent="     ")
            for step in next_steps
        ),
    ]
    return "\n".join(lines)


def find_tool_call(result: dict[str, Any], tool_name: str) -> dict[str, Any] | None:
    for call in result.get("tool_calls", []):
        if call["tool"] == tool_name:
            return call
    return None


def find_created_ticket(result: dict[str, Any]) -> dict[str, Any] | None:
    ticket_call = find_tool_call(result, "create_support_ticket")
    if ticket_call and ticket_call["status"] == "ok":
        return ticket_call["result"]
    return None


def render_reply(result: dict[str, Any]) -> str:
    ticket = find_created_ticket(result)
    if ticket is not None:
        return f"Agent: {format_ticket_confirmation(ticket)}"

    lines = [f"Agent: {strip_markdown(result['response'])}"]
    if result.get("escalation_required"):
        lines.append(f"Agent: {FLAGGED_NOTICE}")
    return "\n".join(lines)


def process_turn(
    agent: SupportAgentOrchestrator,
    session_token: str,
    student_id: str,
    message: str,
    on_event: EventCallback | None = print_status,
) -> str:
    boundary = detect_hard_boundary(message)
    if boundary:
        refusal = build_boundary_refusal(boundary, message)
        agent.memory.add_turn(session_token, "user", message)
        agent.memory.add_turn(session_token, "assistant", refusal.message)
        return f"Agent: {refusal.message}\nAgent: {FLAGGED_NOTICE}"

    result = agent.run(session_token, message, student_id=student_id, on_event=on_event)

    ticket = find_created_ticket(result)
    if ticket is not None:
        agent.memory.replace_last_assistant_turn(session_token, format_ticket_confirmation(ticket))

    return render_reply(result)


def tolerate_unencodable_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


def run_cli(argv: list[str] | None = None, memory: SessionMemoryManager | None = None) -> int:
    args = parse_args(argv)
    tolerate_unencodable_output()
    logging.getLogger().setLevel(logging.INFO if args.verbose else logging.CRITICAL)
    memory = memory or SessionMemoryManager()

    try:
        token, student_id, resumed = open_session(memory, args.student_id, args.session)
    except SessionError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    agent = SupportAgentOrchestrator(memory_manager=memory)

    print("Student Support Agent")
    print(f"Student: {student_id} | Session token: {token} ({'resumed' if resumed else 'new'})")
    if not agent.has_live_model:
        print("Note: the live AI model is unavailable, so replies are built directly from timetable records and policy documents.")
    print(HELP_HINT)

    if resumed:
        history = format_history(memory.get_session(token))
        if history:
            print()
            print(history)

    while True:
        try:
            user_message = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        command = user_message.lower()
        if command in {"exit", "quit"}:
            break
        if not user_message:
            continue
        if command == "/help":
            print(HELP_TEXT)
            continue
        if command == "/session":
            print(f"Session token: {token}")
            continue
        if command == "/history":
            print(format_history(memory.get_session(token)) or "No earlier turns in this session yet.")
            continue
        if command == "/new":
            token = memory.create_session(student_ref=student_id)
            print(f"Started a new session. Session token: {token}")
            continue
        if command.startswith("/"):
            print(f"Unknown command {user_message.split()[0]!r}. {HELP_HINT}")
            continue

        print(process_turn(agent, token, student_id, user_message))

    print(f"Session {token} saved. Resume with: python src/app.py --session {token}")
    return 0


if __name__ == "__main__":
    sys.exit(run_cli())
