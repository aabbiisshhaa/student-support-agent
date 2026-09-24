"""
src/rag/session_memory.py - Session State & Conversational Memory Manager.

BSE4104 Agentic AI Capstone - University Student-Support Case Agent.
Week 4, Task: "Session State & Conversational Memory".
AI Safety Impact: Deterministic Code (no model call decides what is kept).

Task requirement (from the ClickUp task card)
-----------------------------------------------
"Implement a deterministic session-memory manager that preserves conversation
history across multi-turn interactions, prevents unbounded context bloat
through a sliding window or summarization strategy, and tracks active student
support session IDs."

What this file does
--------------------
It gives the agent a place to keep per-student-case conversation state
between turns, without ever growing that state without bound and without
letting a model decide what to forget.

    student asks a question
          |
          v
    SessionMemoryManager.get_or_create(session_id)   -> SessionState
          |
          v
    add_turn(session_id, "user", text)
          |
          v
    sliding window: keep the last WINDOW_SIZE messages verbatim
          |
          +--> window full? oldest message is popped and folded into a
          |    short, rule-based summary line (deterministic - first
          |    sentence / first N words, never an LLM call)
          v
    get_context(session_id) -> [system summary?] + [verbatim window]
          |                     ready to hand to the RAG/agent layer as the
          |                     conversation so far
          v
    persisted to data/sessions/<session_id>.json after every turn, and the
    session_id is added to data/sessions/_active_sessions.json so the set of
    active student-support sessions can always be listed and inspected

This module owns *only* state and memory. It does not answer questions - that
is the retriever/agent's job (src/rag/retriever.py, src/rag/ingest.py). A
tiny stub responder is included purely so `--demo` can exercise the memory
manager end to end and print a transcript as evidence. It is clearly marked
as a stub, every line of its output is prefixed "[STUB]", and the demo
banner says outright that the content is synthetic - none of it should be
read as a real answer from the student-support agent, and the demo session
uses an explicitly synthetic test reference, never a real student's details.

Why this counts as "deterministic code" and not model memory
--------------------------------------------------------------
Nothing here asks a language model what to keep or drop. The window size,
the eviction order (oldest turn first, FIFO) and the summarisation rule
(truncate to the first sentence, or the first SUMMARY_SNIPPET_WORDS words)
are fixed, inspectable functions. Given the same sequence of turns, this
manager always produces the same retained window and the same summary text.

Usage
-----
    # scripted multi-turn demo - this is the transcript to screenshot
    python src/rag/session_memory.py --demo

    # smaller window, to see eviction/summarisation kick in sooner
    python src/rag/session_memory.py --demo --window 3

    # list every session id currently tracked as active
    python src/rag/session_memory.py --list-active

Or as a library:

    from session_memory import SessionMemoryManager

    memory = SessionMemoryManager(window_size=5)
    session_id = memory.create_session(student_ref="23/U/16852/EVE")
    memory.add_turn(session_id, "user", "What courses am I taking?")
    memory.add_turn(session_id, "assistant", "You are taking ...")
    context = memory.get_context(session_id)   # feed this to the agent/LLM

Requirements: standard library only.

Owners: Pauline Peace (PP), Abisha Baingana (AB).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

# ==========================================================================
# 1. Project paths (same auto-detection convention as ingest.py / retriever.py)
# ==========================================================================


def find_project_root(start: Path | None = None) -> Path:
    """Locate the project root, two levels above this file by default."""
    here = (start or Path(__file__)).resolve()
    for candidate in here.parents:
        if (candidate / "data").is_dir():
            return candidate
    if here.parent.name == "rag" and here.parent.parent.name == "src":
        return here.parents[2]
    return here.parent


PROJECT_ROOT = find_project_root()
DATA_DIR = PROJECT_ROOT / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
ACTIVE_INDEX_PATH = SESSIONS_DIR / "_active_sessions.json"
COUNTER_PATH = SESSIONS_DIR / "_session_counter.json"

SESSION_ID_PREFIX = "STU"

# ==========================================================================
# 2. Tunables - the deterministic memory-control strategy
# ==========================================================================

# How many most-recent messages are kept verbatim per session. This is the
# "sliding window" half of the strategy: once a session has more than this
# many messages, the oldest is evicted (FIFO) and folded into the summary.
DEFAULT_WINDOW_SIZE = 6

# The "summarization" half of the strategy: an evicted message is not
# dropped, it is compressed to at most this many words, extracted from the
# start of the message (no model call - a fixed, repeatable rule).
SUMMARY_SNIPPET_WORDS = 18

# The rolling summary itself is also bounded, so it cannot grow forever
# across a very long session: only the most recent SUMMARY_MAX_LINES folded
# turns are kept in the summary text; older summary lines are dropped.
SUMMARY_MAX_LINES = 8

Role = Literal["user", "assistant", "system"]
SessionStatus = Literal["active", "closed"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ==========================================================================
# 3. Data model
# ==========================================================================


@dataclass
class Message:
    """One turn of a conversation, as retained verbatim in the window."""

    turn_index: int
    role: Role
    content: str
    timestamp: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "SessionState":
        # Handle cases where created_at might be in a metadata sub-dict or missing
        created = data.get("created_at") or data.get("metadata", {}).get("created_at", _now_iso())
        last_active = data.get("last_active_at") or data.get("metadata", {}).get("last_active", _now_iso())
        student_ref = data.get("student_ref") or data.get("metadata", {}).get("student_id")
        
        return SessionState(
            session_id=data["session_id"],
            student_ref=student_ref,
            created_at=str(created),
            last_active_at=str(last_active),
            status=data.get("status", "active"),
            turn_count=data.get("turn_count", 0),
            window_size=data.get("window_size", DEFAULT_WINDOW_SIZE),
            messages=[Message.from_dict(m) for m in data.get("messages", [])],
            summary=data.get("summary"),
            summarized_turns=data.get("summarized_turns", 0),
        )


@dataclass
class SessionState:
    """Everything the memory manager tracks for one student-support case."""

    session_id: str
    student_ref: str | None
    created_at: str
    last_active_at: str
    status: SessionStatus
    turn_count: int
    window_size: int
    messages: list[Message]
    summary: str | None
    summarized_turns: int

    def to_dict(self) -> dict:
        d = asdict(self)
        d["messages"] = [m.to_dict() for m in self.messages]
        return d

    @staticmethod
    def from_dict(data: dict) -> "SessionState":
        return SessionState(
            session_id=data["session_id"],
            student_ref=data.get("student_ref"),
            created_at=data["created_at"],
            last_active_at=data["last_active_at"],
            status=data.get("status", "active"),
            turn_count=data.get("turn_count", 0),
            window_size=data.get("window_size", DEFAULT_WINDOW_SIZE),
            messages=[Message.from_dict(m) for m in data.get("messages", [])],
            summary=data.get("summary"),
            summarized_turns=data.get("summarized_turns", 0),
        )


# ==========================================================================
# 4. Deterministic summarisation rule
# ==========================================================================


def _snippet(text: str, max_words: int = SUMMARY_SNIPPET_WORDS) -> str:
    """First sentence of `text`, or its first `max_words` words if longer.

    Purely rule-based string handling - no model call, no randomness. The
    same input always produces the same snippet.
    """
    text = " ".join(text.split())  # collapse whitespace
    sentence_end = re.search(r"[.!?](\s|$)", text)
    if sentence_end and sentence_end.start() <= 140:
        candidate = text[: sentence_end.start() + 1]
    else:
        candidate = text
    words = candidate.split(" ")
    if len(words) > max_words:
        candidate = " ".join(words[:max_words]) + "..."
    return candidate


def _fold_into_summary(summary: str | None, message: Message) -> str:
    """Compress one evicted message into the session's rolling summary.

    Deterministic FIFO on the summary itself too: only the most recent
    SUMMARY_MAX_LINES folded lines survive, so the summary is bounded no
    matter how long the session runs.
    """
    line = f"[turn {message.turn_index} - {message.role}] {_snippet(message.content)}"
    lines = summary.split("\n") if summary else []
    lines.append(line)
    lines = lines[-SUMMARY_MAX_LINES:]
    return "\n".join(lines)


# ==========================================================================
# 5. Session memory manager
# ==========================================================================


class SessionNotFoundError(KeyError):
    """Raised when a session id has no known state, in memory or on disk."""


class SessionMemoryManager:
    """Deterministic session-state and conversational-memory manager.

    Responsibilities (and only these):
      1. Preserve conversation history across multi-turn interactions.
      2. Prevent unbounded context bloat via a sliding window + rule-based
         summarisation of evicted turns.
      3. Track which student-support session ids are currently active.

    It does not generate answers and does not call a language model.
    """

    def __init__(
            self,
            window_size: int = DEFAULT_WINDOW_SIZE,
            sessions_dir: Path = SESSIONS_DIR,
            persist: bool = True,
            retention_days: int = 30,
        ) -> None:
            self.window_size = window_size
            self.sessions_dir = sessions_dir
            self.persist = persist
            self.retention_seconds = retention_days * 24 * 3600
            self._sessions: dict[str, SessionState] = {}
            self._active_ids: set[str] = set()
            if self.persist:
                self.sessions_dir.mkdir(parents=True, exist_ok=True)
                self._active_ids = set(self._read_active_index())

    # -- session lifecycle -------------------------------------------------

    def create_session(self, student_ref: str | None = None) -> str:
        """Start a new session and return its deterministic session id."""
        session_id = self._next_session_id()
        now = _now_iso()
        state = SessionState(
            session_id=session_id,
            student_ref=student_ref,
            created_at=now,
            last_active_at=now,
            status="active",
            turn_count=0,
            window_size=self.window_size,
            messages=[],
            summary=None,
            summarized_turns=0,
        )
        self._sessions[session_id] = state
        self._active_ids.add(session_id)
        self._save(state)
        self._write_active_index()
        return session_id

    def get_session(self, session_id: str) -> SessionState:
        if session_id in self._sessions:
            return self._sessions[session_id]
        state = self._load(session_id)
        if state is None:
            raise SessionNotFoundError(session_id)
        self._sessions[session_id] = state
        return state

    def get_or_create(self, session_id: str | None, student_ref: str | None = None) -> str:
        """Return `session_id` if it exists, otherwise start a fresh one."""
        if session_id:
            try:
                self.get_session(session_id)
                return session_id
            except SessionNotFoundError:
                # If session_id passed explicitly, use it rather than forcing next counter
                now = _now_iso()
                state = SessionState(
                    session_id=session_id,
                    student_ref=student_ref,
                    created_at=now,
                    last_active_at=now,
                    status="active",
                    turn_count=0,
                    window_size=self.window_size,
                    messages=[],
                    summary=None,
                    summarized_turns=0,
                )
                self._sessions[session_id] = state
                self._active_ids.add(session_id)
                self._save(state)
                self._write_active_index()
                return session_id
        return self.create_session(student_ref=student_ref)

    def close_session(self, session_id: str) -> None:
        state = self.get_session(session_id)
        state.status = "closed"
        self._active_ids.discard(session_id)
        self._save(state)
        self._write_active_index()

    def active_session_ids(self) -> list[str]:
        """The deterministic set of currently-active session ids, sorted."""
        return sorted(self._active_ids)

    # -- conversation memory -------------------------------------------------

    def add_turn(self, session_id: str, role: Role, content: str) -> SessionState:
        """Record one turn, then enforce the sliding window deterministically."""
        state = self.get_session(session_id)
        state.turn_count += 1
        message = Message(turn_index=state.turn_count, role=role, content=content)
        state.messages.append(message)
        state.last_active_at = message.timestamp

        # Sliding window: evict oldest-first while over the limit. This is
        # the "prevents unbounded context bloat" requirement - the window
        # size is a fixed number, not a model decision.
        while len(state.messages) > state.window_size:
            oldest = state.messages.pop(0)
            state.summary = _fold_into_summary(state.summary, oldest)
            state.summarized_turns += 1

        self._save(state)
        return state

    def get_context(self, session_id: str, include_summary: bool = True) -> list[dict]:
        """Conversation so far, ready to hand to the RAG/agent layer.

        Returns a list of {"role", "content"} dicts: an optional leading
        "system" message carrying the rolling summary of evicted turns,
        followed by the verbatim sliding window in order.
        """
        state = self.get_session(session_id)
        context: list[dict] = []
        if include_summary and state.summary:
            context.append(
                {
                    "role": "system",
                    "content": (
                        f"Earlier in this session ({state.summarized_turns} "
                        f"older turn(s), summarised):\n{state.summary}"
                    ),
                }
            )
        context.extend({"role": m.role, "content": m.content} for m in state.messages)
        return context

    # -- persistence -------------------------------------------------

    def _path_for(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def _save(self, state: SessionState) -> None:
        if not self.persist:
            return
        self._path_for(state.session_id).write_text(
            json.dumps(state.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _load(self, session_id: str) -> SessionState | None:
        if not self.persist:
            return None
        path = self._path_for(session_id)
        if not path.exists():
            return None
        return SessionState.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def _read_active_index(self) -> list[str]:
        if not ACTIVE_INDEX_PATH.exists():
            return []
        try:
            return json.loads(ACTIVE_INDEX_PATH.read_text(encoding="utf-8")).get("active", [])
        except json.JSONDecodeError:
            return []

    def _write_active_index(self) -> None:
        if not self.persist:
            return
        ACTIVE_INDEX_PATH.write_text(
            json.dumps(
                {"active": sorted(self._active_ids), "updated_at": _now_iso()},
                indent=2,
            ),
            encoding="utf-8",
        )

    def _next_session_id(self) -> str:
        """Deterministic, monotonically increasing session id (STU-001, ...).

        The counter is persisted to disk so ids keep incrementing across
        separate runs of this program, instead of colliding or depending on
        randomness.
        """
        if not self.persist:
            self._counter = getattr(self, "_counter", 0) + 1
            return f"{SESSION_ID_PREFIX}-{self._counter:03d}"
        n = 1
        if COUNTER_PATH.exists():
            try:
                n = json.loads(COUNTER_PATH.read_text(encoding="utf-8"))["next"]
            except (json.JSONDecodeError, KeyError):
                n = 1
        COUNTER_PATH.write_text(json.dumps({"next": n + 1}), encoding="utf-8")
        return f"{SESSION_ID_PREFIX}-{n:03d}"
    
    
    # -- compatibility bridges for orchestrator --------------------------

    def initialize_session(self, session_id: str, student_id: str = "2300712345") -> str:
        """Alias bridge for orchestrator initialization."""
        return self.get_or_create(session_id=session_id, student_ref=student_id)

    def get_recent_history(self, session_id: str, turns: int = 4) -> list[dict]:
        """Returns the most recent verbatim turns for orchestrator prompt synthesis."""
        try:
            state = self.get_session(session_id)
            recent = state.messages[-turns:]
            return [{"role": m.role, "content": m.content} for m in recent]
        except SessionNotFoundError:
            return []

    # -- gdpr & retention compliance ------------------------------------

    def delete_session(self, session_id: str) -> bool:
        """Permanently purges a session from RAM and disk for institutional GDPR compliance."""
        deleted = False
        if session_id in self._sessions:
            del self._sessions[session_id]
            deleted = True

        self._active_ids.discard(session_id)
        if self.persist:
            self._write_active_index()
            path = self._path_for(session_id)
            if path.exists():
                path.unlink()
                deleted = True
        return deleted

    def cleanup_expired_sessions(self) -> int:
        """Purges sessions older than the retention threshold from disk and memory."""
        now = datetime.now(timezone.utc)
        expired = 0
        all_ids = set(self._active_ids)
        if self.persist:
            for f in self.sessions_dir.glob(f"{SESSION_ID_PREFIX}-*.json"):
                all_ids.add(f.stem)

        for sid in all_ids:
            try:
                state = self.get_session(sid)
                last_time = datetime.fromisoformat(state.last_active_at)
                if (now - last_time).total_seconds() > self.retention_seconds:
                    self.delete_session(sid)
                    expired += 1
            except Exception:
                continue
        return expired

# Backwards-compatibility alias for orchestrator imports
ConversationMemory = SessionMemoryManager

# ==========================================================================
# 6. Stub responder - for the demo transcript only, not the real agent
# ==========================================================================


SYNTHETIC_STUDENT_REF = "SYN-STUDENT-0001"  # fabricated test reference, not a real student

STUB_DISCLAIMER = (
    "Deterministic memory-manager test using STUB/SYNTHETIC data - "
    "not production student-support data. None of the content below is a "
    "real answer from the agent; only the memory mechanics are evidence."
)


def _stub_respond(question: str) -> str:
    """A tiny canned responder, only so --demo can exercise the manager.

    This is NOT the student-support agent, and its output is not grounded
    in any real policy document. The real answers come from
    src/rag/retriever.py against the ingested corpus. Every string this
    function returns is fabricated placeholder text, on purpose, so it
    cannot be mistaken for a real grounded answer - callers should treat
    it, and the whole demo transcript, as synthetic test data only.
    """
    q = question.lower()
    if "course" in q:
        content = "[synthetic] you are taking course A, course B and course C this semester."
    elif "earlier" in q or "before" in q or "first" in q:
        content = "[synthetic] earlier in this session you asked about your courses."
    elif "deadline" in q or "add" in q or "drop" in q:
        content = "[synthetic] the add/drop deadline is a placeholder date for this test."
    elif "library" in q:
        content = "[synthetic] library fines are a placeholder amount for this test."
    else:
        content = "[synthetic] no grounded information available in this stub."
    return f"[STUB] {content}"


# ==========================================================================
# 7. Command line entry point
# ==========================================================================

_DEMO_TURNS = [
    "What courses am I taking?",
    "When is the add/drop deadline?",
    "What are the library fines?",
    "What did I ask about earlier?",
]


def _print_state(state: SessionState) -> None:
    print(f"\nSession ID: {state.session_id}")
    if state.student_ref:
        print(f"Student: {state.student_ref}")
    print(f"Session history limit: {state.window_size} messages")
    print(f"Older messages: {state.summarized_turns} removed/summarised")
    if state.summary:
        print("\nMemory (rolling summary of evicted turns):")
        print(state.summary)
    print(f"\nRetained window ({len(state.messages)} message(s)):")
    for m in state.messages:
        speaker = "User" if m.role == "user" else "System"
        print(f"  [{m.turn_index}] {speaker}: {m.content}")


def run_demo(window_size: int) -> SessionState:
    print(STUB_DISCLAIMER)
    memory = SessionMemoryManager(window_size=window_size)
    session_id = memory.create_session(student_ref=SYNTHETIC_STUDENT_REF)
    print(f"\nSession ID: {session_id}")
    print(f"Student ref: {SYNTHETIC_STUDENT_REF} (synthetic test reference, not a real student)")

    for question in _DEMO_TURNS:
        memory.add_turn(session_id, "user", question)
        answer = _stub_respond(question)
        memory.add_turn(session_id, "assistant", answer)
        print(f"\nUser: {question}")
        print(f"System: {answer}")

    state = memory.get_session(session_id)
    print("\n" + "=" * 60)
    print("Memory manager state after the conversation above")
    print("=" * 60)
    _print_state(state)

    print("\nContext handed to the agent for the next turn:")
    for turn in memory.get_context(session_id):
        print(f"  ({turn['role']}) {turn['content']}")

    print(f"\nActive student support session IDs: {memory.active_session_ids()}")
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic session-memory manager (BSE4104, Week 4)"
    )
    parser.add_argument(
        "--demo", action="store_true", help="run a scripted multi-turn demo session"
    )
    parser.add_argument(
        "--window", type=int, default=DEFAULT_WINDOW_SIZE, help="sliding window size"
    )
    parser.add_argument(
        "--list-active", action="store_true", help="list active session ids and exit"
    )
    args = parser.parse_args(argv)

    if args.list_active:
        memory = SessionMemoryManager(window_size=args.window)
        for session_id in memory.active_session_ids():
            print(session_id)
        return 0

    # Default action is the demo, so `python session_memory.py` on its own
    # produces the transcript needed as testing evidence.
    run_demo(window_size=args.window)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(0)