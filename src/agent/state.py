"""
Strongly-typed state for the bounded multi-step agent workflow.

`AgentState` is the single source of truth for one agent run of the
Sense -> Plan -> Act -> Observe -> Re-plan / Stop cycle. It records:

    goal              what the run is trying to achieve
    current_step      where in the cycle the run currently is
    plan_history      every plan produced, including re-plans
    tool_observations every tool call and its outcome
    status            running | success | recovered | escalated
    iteration_count   completed planning cycles, including re-plans

All rules below are enforced by deterministic code, never by the model:

    * only the cycle transitions in `ALLOWED_STEP_TRANSITIONS` are legal;
    * status may only move from `running` to exactly one terminal status;
    * a terminal (sealed) state rejects every further change;
    * `iteration_count` can never exceed `max_iterations`;
    * re-plans are capped by `max_replans`.

See docs/architecture/agent_task_contract.md, Sections 5 and 6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Literal, Mapping

# ==========================================================================
# 1. Limits (Agent Task Contract, Section 6)
# ==========================================================================

RETAKE_WORKFLOW_MAX_ITERATIONS = 5
MAX_REPLANS = 2
MAX_RETRIES_PER_TOOL = 1

ObservationStatus = Literal["ok", "error"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


# ==========================================================================
# 2. Enumerations
# ==========================================================================


class AgentStatus(str, Enum):
    """Lifecycle status of a run. Only RUNNING is non-terminal."""

    RUNNING = "running"
    SUCCESS = "success"
    RECOVERED = "recovered"
    ESCALATED = "escalated"

    @property
    def is_terminal(self) -> bool:
        return self is not AgentStatus.RUNNING


class AgentStep(str, Enum):
    """Phase of the Sense -> Plan -> Act -> Observe -> Re-plan / Stop cycle."""

    SENSE = "sense"
    PLAN = "plan"
    ACT = "act"
    OBSERVE = "observe"
    REPLAN = "replan"
    STOP = "stop"


class PlanAction(str, Enum):
    """Actions the planner may choose (mirrors the orchestrator's planner)."""

    RETRIEVE_KNOWLEDGE = "RETRIEVE_KNOWLEDGE"
    EXECUTE_TOOL = "EXECUTE_TOOL"
    FINAL_SYNTHESIS = "FINAL_SYNTHESIS"


ALLOWED_STEP_TRANSITIONS: Mapping[AgentStep, frozenset[AgentStep]] = MappingProxyType(
    {
        AgentStep.SENSE: frozenset({AgentStep.PLAN, AgentStep.STOP}),
        AgentStep.PLAN: frozenset({AgentStep.ACT, AgentStep.STOP}),
        AgentStep.ACT: frozenset({AgentStep.OBSERVE}),
        AgentStep.OBSERVE: frozenset({AgentStep.PLAN, AgentStep.REPLAN, AgentStep.STOP}),
        AgentStep.REPLAN: frozenset({AgentStep.ACT, AgentStep.STOP}),
        AgentStep.STOP: frozenset(),
    }
)

# Steps that start a new planning cycle and therefore count as an iteration.
ITERATION_STEPS = frozenset({AgentStep.PLAN, AgentStep.REPLAN})


# ==========================================================================
# 3. Errors
# ==========================================================================


class AgentStateError(RuntimeError):
    """Base class for every violation of the state contract."""


class InvalidTransitionError(AgentStateError):
    """Raised for an illegal step or status transition."""


class IterationLimitExceededError(AgentStateError):
    """Raised when a new cycle would exceed `max_iterations`."""


class ReplanLimitExceededError(AgentStateError):
    """Raised when a re-plan would exceed `max_replans`."""


class StateSealedError(AgentStateError):
    """Raised when a terminal state is modified."""


# ==========================================================================
# 4. Immutable records
# ==========================================================================


@dataclass(frozen=True)
class PlanRecord:
    """One plan chosen by the planner during a single iteration."""

    iteration: int
    action: PlanAction
    tool_name: str | None = None
    tool_params: Mapping[str, Any] = field(default_factory=dict)
    rationale: str = ""
    is_replan: bool = False
    timestamp: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        if not isinstance(self.action, PlanAction):
            raise TypeError(f"action must be a PlanAction, got {self.action!r}")
        if isinstance(self.iteration, bool) or not isinstance(self.iteration, int) or self.iteration < 1:
            raise ValueError("iteration must be a positive integer")
        if self.action is PlanAction.EXECUTE_TOOL and not self.tool_name:
            raise ValueError("EXECUTE_TOOL plans must name a tool")
        if not isinstance(self.is_replan, bool):
            raise TypeError("is_replan must be a bool")
        # Freeze params so the recorded plan cannot be altered later.
        object.__setattr__(self, "tool_params", MappingProxyType(dict(self.tool_params)))

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "action": self.action.value,
            "tool_name": self.tool_name,
            "tool_params": dict(self.tool_params),
            "rationale": self.rationale,
            "is_replan": self.is_replan,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class ToolObservation:
    """The observed outcome of one tool call."""

    iteration: int
    tool: str
    params: Mapping[str, Any]
    status: ObservationStatus
    result: Any
    latency_ms: float = 0.0
    timestamp: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        if not isinstance(self.tool, str) or not self.tool:
            raise ValueError("tool must be a non-empty string")
        if self.status not in ("ok", "error"):
            raise ValueError(f"status must be 'ok' or 'error', got {self.status!r}")
        if isinstance(self.iteration, bool) or not isinstance(self.iteration, int) or self.iteration < 1:
            raise ValueError("iteration must be a positive integer")
        if not isinstance(self.latency_ms, (int, float)) or self.latency_ms < 0:
            raise ValueError("latency_ms must be a non-negative number")
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))

    @property
    def failed(self) -> bool:
        return self.status == "error"

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "tool": self.tool,
            "params": dict(self.params),
            "status": self.status,
            "result": self.result,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
        }


# ==========================================================================
# 5. Agent state
# ==========================================================================


@dataclass
class AgentState:
    """Mutable, contract-checked state of one bounded agent run.

    Change the state only through the methods below; they enforce every
    transition and limit. Direct field assignment bypasses the contract.
    """

    goal: str
    max_iterations: int = RETAKE_WORKFLOW_MAX_ITERATIONS
    max_replans: int = MAX_REPLANS
    current_step: AgentStep = AgentStep.SENSE
    plan_history: list[PlanRecord] = field(default_factory=list)
    tool_observations: list[ToolObservation] = field(default_factory=list)
    status: AgentStatus = AgentStatus.RUNNING
    iteration_count: int = 0
    escalation_reason: str | None = None
    started_at: str = field(default_factory=_now_iso)
    finished_at: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.goal, str) or not self.goal.strip():
            raise ValueError("goal must be a non-empty string")
        for name in ("max_iterations", "max_replans", "iteration_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
        if self.max_iterations > RETAKE_WORKFLOW_MAX_ITERATIONS:
            raise ValueError(
                f"max_iterations may not exceed {RETAKE_WORKFLOW_MAX_ITERATIONS}"
            )
        if self.iteration_count > self.max_iterations:
            raise ValueError("iteration_count may not exceed max_iterations")
        if not isinstance(self.current_step, AgentStep):
            raise TypeError("current_step must be an AgentStep")
        if not isinstance(self.status, AgentStatus):
            raise TypeError("status must be an AgentStatus")
        self.goal = self.goal.strip()

    # ------------------------------------------------------------------
    # Read-only views
    # ------------------------------------------------------------------

    @property
    def is_terminal(self) -> bool:
        return self.status.is_terminal

    @property
    def replan_count(self) -> int:
        return sum(1 for plan in self.plan_history if plan.is_replan)

    @property
    def remaining_iterations(self) -> int:
        return self.max_iterations - self.iteration_count

    @property
    def has_tool_failure(self) -> bool:
        return any(obs.failed for obs in self.tool_observations)

    @property
    def last_plan(self) -> PlanRecord | None:
        return self.plan_history[-1] if self.plan_history else None

    @property
    def last_observation(self) -> ToolObservation | None:
        return self.tool_observations[-1] if self.tool_observations else None

    def failure_count(self, tool: str) -> int:
        return sum(1 for obs in self.tool_observations if obs.tool == tool and obs.failed)

    def can_retry(self, tool: str) -> bool:
        """True when `tool` may be retried under the per-tool retry limit."""

        return (
            not self.is_terminal
            and self.failure_count(tool) <= MAX_RETRIES_PER_TOOL
            and self.replan_count < self.max_replans
            and self.remaining_iterations > 0
        )

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------

    def _ensure_open(self) -> None:
        if self.is_terminal:
            raise StateSealedError(
                f"run already finished with status '{self.status.value}'"
            )

    def advance_to(self, step: AgentStep) -> None:
        """Move to `step`; entering PLAN or REPLAN starts a new iteration."""

        self._ensure_open()
        if not isinstance(step, AgentStep):
            raise TypeError("step must be an AgentStep")
        if step not in ALLOWED_STEP_TRANSITIONS[self.current_step]:
            raise InvalidTransitionError(
                f"cannot move from '{self.current_step.value}' to '{step.value}'"
            )
        if step is AgentStep.STOP:
            raise InvalidTransitionError("use finish() or escalate() to stop a run")
        if step in ITERATION_STEPS:
            if self.iteration_count >= self.max_iterations:
                raise IterationLimitExceededError(
                    f"iteration limit of {self.max_iterations} reached"
                )
            if step is AgentStep.REPLAN and self.replan_count >= self.max_replans:
                raise ReplanLimitExceededError(
                    f"re-plan limit of {self.max_replans} reached"
                )
            self.iteration_count += 1
        self.current_step = step

    def record_plan(
        self,
        action: PlanAction,
        tool_name: str | None = None,
        tool_params: Mapping[str, Any] | None = None,
        rationale: str = "",
    ) -> PlanRecord:
        """Record the plan for the current PLAN or REPLAN step."""

        self._ensure_open()
        if self.current_step not in ITERATION_STEPS:
            raise InvalidTransitionError(
                f"plans may only be recorded during plan/replan, not '{self.current_step.value}'"
            )
        if self.last_plan is not None and self.last_plan.iteration == self.iteration_count:
            raise InvalidTransitionError("a plan was already recorded for this iteration")
        plan = PlanRecord(
            iteration=self.iteration_count,
            action=action,
            tool_name=tool_name,
            tool_params=tool_params or {},
            rationale=rationale,
            is_replan=self.current_step is AgentStep.REPLAN,
        )
        self.plan_history.append(plan)
        return plan

    def record_observation(
        self,
        tool: str,
        params: Mapping[str, Any],
        status: ObservationStatus,
        result: Any,
        latency_ms: float = 0.0,
    ) -> ToolObservation:
        """Record a tool outcome; the run must be in the OBSERVE step."""

        self._ensure_open()
        if self.current_step is not AgentStep.OBSERVE:
            raise InvalidTransitionError(
                f"observations may only be recorded during observe, not '{self.current_step.value}'"
            )
        observation = ToolObservation(
            iteration=self.iteration_count,
            tool=tool,
            params=params,
            status=status,
            result=result,
            latency_ms=latency_ms,
        )
        self.tool_observations.append(observation)
        return observation

    def finish(self, status: AgentStatus, escalation_reason: str | None = None) -> None:
        """Seal the run with a terminal status. This can happen only once."""

        self._ensure_open()
        if not isinstance(status, AgentStatus) or not status.is_terminal:
            raise InvalidTransitionError("finish() requires a terminal status")
        if AgentStep.STOP not in ALLOWED_STEP_TRANSITIONS[self.current_step]:
            raise InvalidTransitionError(
                f"cannot stop from '{self.current_step.value}'"
            )
        if status is AgentStatus.ESCALATED:
            if not escalation_reason:
                raise ValueError("an escalated run must state an escalation_reason")
        elif escalation_reason is not None:
            raise ValueError("only escalated runs may carry an escalation_reason")
        if status is AgentStatus.SUCCESS and self.has_tool_failure:
            raise InvalidTransitionError(
                "a run with a failed tool call must finish as 'recovered' or 'escalated'"
            )
        if status is AgentStatus.RECOVERED and not self.has_tool_failure:
            raise InvalidTransitionError(
                "'recovered' requires at least one failed tool call"
            )
        self.current_step = AgentStep.STOP
        self.status = status
        self.escalation_reason = escalation_reason
        self.finished_at = _now_iso()

    def escalate(self, reason: str) -> None:
        """Hand the run to a human from any open step."""

        self._ensure_open()
        if self.current_step is AgentStep.ACT:
            # An escalation mid-action still stops; the tool result is lost.
            self.current_step = AgentStep.OBSERVE
        self.finish(AgentStatus.ESCALATED, escalation_reason=reason)

    def complete(self) -> AgentStatus:
        """Finish as success, or recovered if any tool call failed."""

        status = AgentStatus.RECOVERED if self.has_tool_failure else AgentStatus.SUCCESS
        self.finish(status)
        return status

    # ------------------------------------------------------------------
    # Serialisation (for traces, telemetry and staff hand-off)
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "current_step": self.current_step.value,
            "status": self.status.value,
            "iteration_count": self.iteration_count,
            "max_iterations": self.max_iterations,
            "max_replans": self.max_replans,
            "escalation_reason": self.escalation_reason,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "plan_history": [plan.to_dict() for plan in self.plan_history],
            "tool_observations": [obs.to_dict() for obs in self.tool_observations],
        }
