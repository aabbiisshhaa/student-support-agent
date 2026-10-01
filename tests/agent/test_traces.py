"""Contract and termination tests for agent execution traces."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

import src.agent.orchestrator as orchestrator_module
from src.agent.memory import SessionMemoryManager
from src.agent.orchestrator import (
    MAX_AGENT_ITERATIONS,
    VALID_RUN_STATUSES,
    SupportAgentOrchestrator,
)
from src.telemetry.tracker import TelemetryTracker


@pytest.fixture
def build_agent(tmp_path, monkeypatch):
    """Create an offline orchestrator with isolated telemetry."""

    monkeypatch.setattr(
        orchestrator_module,
        "GeminiModel",
        lambda: (_ for _ in ()).throw(
            ValueError("offline test mode")
        ),
    )

    monkeypatch.setattr(
        orchestrator_module,
        "TelemetryTracker",
        lambda: TelemetryTracker(log_dir=tmp_path),
    )

    def factory(
        max_iterations: int = MAX_AGENT_ITERATIONS,
    ) -> SupportAgentOrchestrator:
        return SupportAgentOrchestrator(
            memory_manager=SessionMemoryManager(
                persist=False
            ),
            max_iterations=max_iterations,
        )

    return factory


def test_iteration_limit_is_exactly_three():
    """The system-level execution ceiling must remain three."""

    assert MAX_AGENT_ITERATIONS == 3


@pytest.mark.parametrize(
    "invalid_limit",
    [0, 4, -1, True, 1.5, "3"],
)
def test_invalid_iteration_limits_are_rejected(
    build_agent,
    invalid_limit,
):
    """Callers cannot disable or exceed the loop boundary."""

    with pytest.raises(ValueError):
        build_agent(max_iterations=invalid_limit)


def test_agent_never_executes_more_than_three_iterations(
    build_agent,
):
    """A non-terminating plan must escalate after three cycles."""

    agent = build_agent()
    planner = Mock(
        return_value={
            "action": "UNKNOWN_ACTION",
        }
    )

    with patch.object(
        agent,
        "_plan_next_step",
        planner,
    ):
        result = agent.run(
            "trace-loop-limit",
            "Continue working without stopping.",
        )

    assert planner.call_count == 3
    assert result["iterations"] == 3
    assert result["iterations"] <= MAX_AGENT_ITERATIONS
    assert result["status"] == "escalated"
    assert result["escalation_required"] is True


def test_agent_stops_immediately_after_verified_success(
    build_agent,
):
    """Final synthesis should stop the loop without extra work."""

    agent = build_agent()
    planner = Mock(
        return_value={
            "action": "FINAL_SYNTHESIS",
        }
    )

    with (
        patch.object(
            agent,
            "_plan_next_step",
            planner,
        ),
        patch.object(
            agent,
            "_synthesize_response",
            return_value="Verified grounded response.",
        ),
    ):
        result = agent.run(
            "trace-success",
            "Give me a grounded answer.",
        )

    assert planner.call_count == 1
    assert result["iterations"] == 1
    assert result["status"] == "success"
    assert result["escalation_required"] is False
    assert result["tool_calls"] == []


def test_tool_failure_exits_with_recovered_status(
    build_agent,
):
    """A failed tool call must produce a controlled recovery."""

    agent = build_agent()

    planner = Mock(
        side_effect=[
            {
                "action": "EXECUTE_TOOL",
                "tool_name": "invented_tool",
                "tool_params": {
                    "invented_parameter": "unsafe-value",
                },
            },
            {
                "action": "FINAL_SYNTHESIS",
            },
        ]
    )

    with (
        patch.object(
            agent,
            "_plan_next_step",
            planner,
        ),
        patch.object(
            agent,
            "_synthesize_response",
            return_value=(
                "The requested tool could not be used. "
                "A safe fallback was returned."
            ),
        ),
    ):
        result = agent.run(
            "trace-recovery",
            "Use an unavailable tool.",
        )

    assert result["iterations"] == 2
    assert result["status"] == "recovered"
    assert result["escalation_required"] is False
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["status"] == "error"
    assert "not recognized" in str(
        result["tool_calls"][0]["result"]
    ).lower()


def test_prohibited_request_exits_as_escalated(
    build_agent,
):
    """Prohibited operations must stop before tool execution."""

    agent = build_agent()

    result = agent.run(
        "trace-escalation",
        "Update my grade from C to A.",
    )

    assert result["status"] == "escalated"
    assert result["escalation_required"] is True
    assert result["iterations"] == 0
    assert result["tool_calls"] == []
    assert "not authorized" in result["response"].lower()


@pytest.mark.parametrize(
    "status",
    ["success", "recovered", "escalated"],
)
def test_only_verified_terminal_statuses_are_allowed(
    status,
):
    """The published task contract has exactly three statuses."""

    assert status in VALID_RUN_STATUSES


def test_result_obeys_task_contract(build_agent):
    """Every completed run must return the required fields."""

    agent = build_agent()

    with (
        patch.object(
            agent,
            "_plan_next_step",
            return_value={
                "action": "FINAL_SYNTHESIS",
            },
        ),
        patch.object(
            agent,
            "_synthesize_response",
            return_value="Completed safely.",
        ),
    ):
        result = agent.run(
            "trace-contract",
            "Complete this request safely.",
        )

    required_fields = {
        "status",
        "response",
        "escalation_required",
        "iterations",
        "tool_calls",
    }

    assert required_fields.issubset(result)
    assert result["status"] in VALID_RUN_STATUSES
    assert isinstance(result["response"], str)
    assert result["response"].strip()
    assert isinstance(
        result["escalation_required"],
        bool,
    )
    assert isinstance(result["iterations"], int)
    assert 0 <= result["iterations"] <= 3
    assert isinstance(result["tool_calls"], list)