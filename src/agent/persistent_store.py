"""Small persistent store for safe, user-scoped session context."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path


_USER_ID = re.compile(r"^STU-\d{5}$")
_COURSE_CODE = re.compile(r"^[A-Z]{2,4}-\d{3,4}$")
_ALLOWED_KEYS = frozenset({"student_id", "enrolled_course"})
_UNSAFE = re.compile(
    r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions|"
    r"system\s+prompt|override\s+(?:safety|guardrails?)|"
    r"(?:admin|administrator)\s+role|bypass\s+(?:policy|safety)",
    re.IGNORECASE,
)


class PersistentMemoryValidationError(ValueError):
    """Raised when memory content is outside the fixed safe schema."""


class PersistentMemoryStore:
    """SQLite-backed key-value memory scoped to one authenticated user."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    user_id TEXT NOT NULL,
                    memory_key TEXT NOT NULL,
                    memory_value TEXT NOT NULL,
                    PRIMARY KEY (user_id, memory_key)
                )
                """
            )

    @staticmethod
    def _validate_user_id(user_id: str) -> str:
        if not isinstance(user_id, str) or not _USER_ID.fullmatch(user_id):
            raise PersistentMemoryValidationError("invalid user_id")
        return user_id

    @staticmethod
    def _validate_value(key: str, value: str, user_id: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise PersistentMemoryValidationError("memory value must be non-empty text")
        value = value.strip()
        if _UNSAFE.search(value):
            raise PersistentMemoryValidationError("unsafe instruction-like memory rejected")
        if key == "student_id" and value != user_id:
            raise PersistentMemoryValidationError("student_id must match user_id")
        if key == "enrolled_course" and not _COURSE_CODE.fullmatch(value):
            raise PersistentMemoryValidationError("invalid enrolled course code")
        return value

    def write_memory(self, user_id: str, key: str, value: str) -> None:
        """Write one allow-listed, validated value for ``user_id``."""

        user_id = self._validate_user_id(user_id)
        if key not in _ALLOWED_KEYS:
            raise PersistentMemoryValidationError("memory key is not allow-listed")
        value = self._validate_value(key, value, user_id)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO memories (user_id, memory_key, memory_value)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, memory_key) DO UPDATE SET memory_value = excluded.memory_value
                """,
                (user_id, key, value),
            )

    def read_memory(self, user_id: str) -> dict[str, str]:
        """Return a copy of the validated memory for ``user_id``."""

        user_id = self._validate_user_id(user_id)
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                "SELECT memory_key, memory_value FROM memories WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return {key: value for key, value in rows}
