from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_DATABASE_URL = "sqlite:///./student_support.db"

STUDENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_-]{2,29}$")
CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,49}$")

class TicketCategory(str, Enum):
    TIMETABLE = "timetable"
    POLICY = "policy"
    ADMINISTRATIVE = "administrative"
    OTHER = "other"


class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


VALID_CATEGORIES = {category.value for category in TicketCategory}
VALID_PRIORITIES = {priority.value for priority in TicketPriority}

CATEGORY_QUEUES = {
    "timetable": "Timetable & Registration Queue",
    "policy": "Academic Policy Queue",
    "administrative": "General Administration Queue",
    "other": "General Support Queue",
}


class TicketRecord(TypedDict):
    ticket_id: str
    student_id: str
    case_id: str | None
    summary: str
    original_message: str
    category: str
    priority: str
    queue: str
    status: str
    created_at: str


class TicketValidationError(ValueError):
    pass


def _resolve_sqlite_path() -> Path:
    database_url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    if not database_url.startswith("sqlite:///"):
        raise TicketValidationError(f"Unsupported DATABASE_URL scheme: {database_url!r}")
    raw_path = database_url[len("sqlite:///"):]
    path = Path(raw_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _get_connection() -> sqlite3.Connection:
    db_path = _resolve_sqlite_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT UNIQUE NOT NULL,
            student_id TEXT NOT NULL,
            case_id TEXT,
            summary TEXT NOT NULL,
            original_message TEXT NOT NULL,
            category TEXT NOT NULL,
            priority TEXT NOT NULL,
            queue TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return connection


def _validate_student_id(student_id: str) -> str:
    if not isinstance(student_id, str) or not STUDENT_ID_PATTERN.match(student_id):
        raise TicketValidationError(f"Invalid student_id: {student_id!r}")
    return student_id


def _validate_case_id(case_id: str | None) -> str | None:
    if case_id is None:
        return None
    if not isinstance(case_id, str) or not CASE_ID_PATTERN.match(case_id):
        raise TicketValidationError(f"Invalid case_id: {case_id!r}")
    return case_id


def _validate_summary(summary: str) -> str:
    if not isinstance(summary, str) or not (10 <= len(summary) <= 500):
        raise TicketValidationError("summary must be a string between 10 and 500 characters")
    return summary


def _validate_original_message(original_message: str) -> str:
    if not isinstance(original_message, str) or not (1 <= len(original_message) <= 2000):
        raise TicketValidationError("original_message must be a string between 1 and 2000 characters")
    return original_message


def _validate_category(category: str | TicketCategory) -> str:
    value = category.value if isinstance(category, Enum) else category
    if not isinstance(value, str) or value not in VALID_CATEGORIES:
        raise TicketValidationError(f"Invalid category: {category!r}")
    return value


def _validate_priority(priority: str | TicketPriority) -> str:
    value = priority.value if isinstance(priority, Enum) else priority
    if not isinstance(value, str) or value not in VALID_PRIORITIES:
        raise TicketValidationError(f"Invalid priority: {priority!r}")
    return value


def _validate_student_confirmed(student_confirmed: bool) -> None:
    if student_confirmed is not True:
        raise TicketValidationError("student_confirmed must be true to create a ticket")


def create_support_ticket(
    student_id: str,
    summary: str,
    original_message: str,
    category: str | TicketCategory,
    priority: str | TicketPriority,
    student_confirmed: bool,
    case_id: str | None = None,
) -> TicketRecord:
    student_id = _validate_student_id(student_id)
    case_id = _validate_case_id(case_id)
    summary = _validate_summary(summary)
    original_message = _validate_original_message(original_message)
    category = _validate_category(category)
    priority = _validate_priority(priority)
    _validate_student_confirmed(student_confirmed)

    queue = CATEGORY_QUEUES[category]
    created_at = datetime.now(timezone.utc).isoformat()

    connection = _get_connection()
    try:
        cursor = connection.execute(
            """
            INSERT INTO tickets (
                ticket_id, student_id, case_id, summary, original_message,
                category, priority, queue, status, created_at
            ) VALUES ('', ?, ?, ?, ?, ?, ?, ?, 'open', ?)
            """,
            (student_id, case_id, summary, original_message, category, priority, queue, created_at),
        )
        row_id = cursor.lastrowid
        ticket_id = f"TCK-{row_id:06d}"
        connection.execute(
            "UPDATE tickets SET ticket_id = ? WHERE id = ?",
            (ticket_id, row_id),
        )
        connection.commit()
    finally:
        connection.close()

    return {
        "ticket_id": ticket_id,
        "student_id": student_id,
        "case_id": case_id,
        "summary": summary,
        "original_message": original_message,
        "category": category,
        "priority": priority,
        "queue": queue,
        "status": "open",
        "created_at": created_at,
    }


def get_ticket(ticket_id: str) -> TicketRecord | None:
    connection = _get_connection()
    try:
        row = connection.execute(
            """
            SELECT ticket_id, student_id, case_id, summary, original_message,
                   category, priority, queue, status, created_at
            FROM tickets WHERE ticket_id = ?
            """,
            (ticket_id,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return None

    return {
        "ticket_id": row[0],
        "student_id": row[1],
        "case_id": row[2],
        "summary": row[3],
        "original_message": row[4],
        "category": row[5],
        "priority": row[6],
        "queue": row[7],
        "status": row[8],
        "created_at": row[9],
    }
