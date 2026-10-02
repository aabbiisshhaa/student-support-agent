from __future__ import annotations

from typing import Any


def escalate_to_human_admin(
    *,
    session_id: str,
    student_id: str,
    reason: str,
    conversation_history: list[dict[str, Any]],
    iteration_count: int,
    max_allowed_iterations: int,
    escalation_target: str = "General Administration Queue",
) -> dict[str, Any]:
    """Build an auditable, non-mutating human hand-off payload."""

    if not session_id or not student_id or not reason:
        raise ValueError("session_id, student_id, and reason are required")
    if iteration_count < 0 or max_allowed_iterations < 1:
        raise ValueError("iteration counts must be valid non-negative values")

    return {
        "status": "escalated",
        "reason": reason,
        "user_metadata": {
            "student_id": student_id,
            "session_id": session_id,
        },
        "iteration_count": iteration_count,
        "max_allowed_iterations": max_allowed_iterations,
        "conversation_history": conversation_history,
        "escalation_target": escalation_target,
    }
