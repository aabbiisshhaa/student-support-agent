import unittest

from src.agent.state import (
    RETAKE_WORKFLOW_MAX_ITERATIONS,
    AgentState,
    AgentStatus,
    AgentStep,
    InvalidTransitionError,
    IterationLimitExceededError,
    PlanAction,
    PlanRecord,
    ReplanLimitExceededError,
    StateSealedError,
)

GOAL = "Resolve retake of CSC3103 against the current timetable"
STUDENT = {"student_id": "2300712345"}


def run_tool_cycle(state, tool, status="ok", result=None, replan=False):
    """Drive one Plan/Replan -> Act -> Observe cycle."""

    state.advance_to(AgentStep.REPLAN if replan else AgentStep.PLAN)
    state.record_plan(PlanAction.EXECUTE_TOOL, tool_name=tool, tool_params=STUDENT)
    state.advance_to(AgentStep.ACT)
    state.advance_to(AgentStep.OBSERVE)
    state.record_observation(tool, STUDENT, status, result if result is not None else [])


def plan_synthesis(state):
    state.advance_to(AgentStep.PLAN)
    state.record_plan(PlanAction.FINAL_SYNTHESIS)


class TestInitialState(unittest.TestCase):
    def test_new_state_starts_running_at_sense(self) -> None:
        state = AgentState(goal=GOAL)

        self.assertEqual(state.status, AgentStatus.RUNNING)
        self.assertEqual(state.current_step, AgentStep.SENSE)
        self.assertEqual(state.iteration_count, 0)
        self.assertEqual(state.plan_history, [])
        self.assertEqual(state.tool_observations, [])
        self.assertEqual(state.max_iterations, RETAKE_WORKFLOW_MAX_ITERATIONS)

    def test_rejects_empty_goal(self) -> None:
        with self.assertRaises(ValueError):
            AgentState(goal="   ")

    def test_rejects_invalid_limits(self) -> None:
        for bad in (0, -1, True, 2.5, RETAKE_WORKFLOW_MAX_ITERATIONS + 1):
            with self.subTest(max_iterations=bad), self.assertRaises(ValueError):
                AgentState(goal=GOAL, max_iterations=bad)

    def test_rejects_untyped_status_and_step(self) -> None:
        with self.assertRaises(TypeError):
            AgentState(goal=GOAL, status="running")
        with self.assertRaises(TypeError):
            AgentState(goal=GOAL, current_step="sense")

    def test_status_values_match_the_contract(self) -> None:
        self.assertEqual(
            {status.value for status in AgentStatus},
            {"running", "success", "recovered", "escalated"},
        )


class TestReferenceTraces(unittest.TestCase):
    def test_trace_a_happy_path_ends_in_success(self) -> None:
        state = AgentState(goal=GOAL)
        run_tool_cycle(state, "retriever")
        run_tool_cycle(state, "get_course_schedule")
        run_tool_cycle(state, "get_course_offering")
        plan_synthesis(state)

        self.assertEqual(state.complete(), AgentStatus.SUCCESS)
        self.assertEqual(state.iteration_count, 4)
        self.assertEqual(len(state.plan_history), 4)
        self.assertEqual(len(state.tool_observations), 3)
        self.assertEqual(state.current_step, AgentStep.STOP)
        self.assertIsNotNone(state.finished_at)

    def test_trace_b_failure_then_retry_ends_in_recovered(self) -> None:
        state = AgentState(goal=GOAL)
        run_tool_cycle(state, "retriever")
        run_tool_cycle(state, "get_course_schedule", status="error", result={"error": "timeout"})

        self.assertTrue(state.can_retry("get_course_schedule"))
        run_tool_cycle(state, "get_course_schedule", replan=True)
        run_tool_cycle(state, "get_course_offering")
        plan_synthesis(state)

        self.assertEqual(state.complete(), AgentStatus.RECOVERED)
        self.assertEqual(state.iteration_count, 5)
        self.assertEqual(state.replan_count, 1)
        self.assertTrue(state.plan_history[2].is_replan)

    def test_trace_c_clash_needing_decision_is_escalated(self) -> None:
        state = AgentState(goal=GOAL)
        run_tool_cycle(state, "retriever")
        run_tool_cycle(state, "get_course_schedule")
        run_tool_cycle(state, "get_course_offering")

        state.escalate("S2")

        self.assertEqual(state.status, AgentStatus.ESCALATED)
        self.assertEqual(state.escalation_reason, "S2")

    def test_trace_d_prohibited_request_escalates_at_iteration_zero(self) -> None:
        state = AgentState(goal=GOAL)

        state.escalate("S1")

        self.assertEqual(state.status, AgentStatus.ESCALATED)
        self.assertEqual(state.iteration_count, 0)
        self.assertEqual(state.tool_observations, [])


class TestLimits(unittest.TestCase):
    def test_iteration_count_never_exceeds_limit(self) -> None:
        state = AgentState(goal=GOAL, max_iterations=2)
        run_tool_cycle(state, "retriever")
        run_tool_cycle(state, "get_course_schedule")

        with self.assertRaises(IterationLimitExceededError):
            state.advance_to(AgentStep.PLAN)

        self.assertEqual(state.iteration_count, 2)
        state.escalate("S4")
        self.assertEqual(state.status, AgentStatus.ESCALATED)

    def test_replan_limit_is_enforced(self) -> None:
        state = AgentState(goal=GOAL, max_replans=1)
        run_tool_cycle(state, "retriever", status="error", result={"error": "x"})
        run_tool_cycle(state, "retriever", status="error", result={"error": "x"}, replan=True)

        with self.assertRaises(ReplanLimitExceededError):
            state.advance_to(AgentStep.REPLAN)

    def test_tool_may_be_retried_only_once(self) -> None:
        state = AgentState(goal=GOAL)
        run_tool_cycle(state, "get_course_schedule", status="error", result={"error": "x"})
        self.assertTrue(state.can_retry("get_course_schedule"))

        run_tool_cycle(
            state, "get_course_schedule", status="error", result={"error": "x"}, replan=True
        )
        self.assertFalse(state.can_retry("get_course_schedule"))


class TestTransitions(unittest.TestCase):
    def test_cannot_skip_from_sense_to_act(self) -> None:
        state = AgentState(goal=GOAL)
        with self.assertRaises(InvalidTransitionError):
            state.advance_to(AgentStep.ACT)

    def test_act_must_be_followed_by_observe(self) -> None:
        state = AgentState(goal=GOAL)
        state.advance_to(AgentStep.PLAN)
        state.advance_to(AgentStep.ACT)
        with self.assertRaises(InvalidTransitionError):
            state.advance_to(AgentStep.PLAN)

    def test_stop_only_through_finish(self) -> None:
        state = AgentState(goal=GOAL)
        with self.assertRaises(InvalidTransitionError):
            state.advance_to(AgentStep.STOP)

    def test_plan_only_recorded_once_per_iteration(self) -> None:
        state = AgentState(goal=GOAL)
        state.advance_to(AgentStep.PLAN)
        state.record_plan(PlanAction.RETRIEVE_KNOWLEDGE)
        with self.assertRaises(InvalidTransitionError):
            state.record_plan(PlanAction.FINAL_SYNTHESIS)

    def test_observation_only_recorded_during_observe(self) -> None:
        state = AgentState(goal=GOAL)
        state.advance_to(AgentStep.PLAN)
        with self.assertRaises(InvalidTransitionError):
            state.record_observation("retriever", {}, "ok", [])

    def test_success_rejected_after_tool_failure(self) -> None:
        state = AgentState(goal=GOAL)
        run_tool_cycle(state, "retriever", status="error", result={"error": "x"})
        plan_synthesis(state)
        with self.assertRaises(InvalidTransitionError):
            state.finish(AgentStatus.SUCCESS)

    def test_recovered_rejected_without_tool_failure(self) -> None:
        state = AgentState(goal=GOAL)
        run_tool_cycle(state, "retriever")
        plan_synthesis(state)
        with self.assertRaises(InvalidTransitionError):
            state.finish(AgentStatus.RECOVERED)

    def test_escalation_requires_reason(self) -> None:
        state = AgentState(goal=GOAL)
        with self.assertRaises(ValueError):
            state.finish(AgentStatus.ESCALATED)

    def test_cannot_finish_with_running(self) -> None:
        state = AgentState(goal=GOAL)
        with self.assertRaises(InvalidTransitionError):
            state.finish(AgentStatus.RUNNING)

    def test_terminal_state_is_sealed(self) -> None:
        state = AgentState(goal=GOAL)
        state.escalate("S1")

        with self.assertRaises(StateSealedError):
            state.advance_to(AgentStep.PLAN)
        with self.assertRaises(StateSealedError):
            state.finish(AgentStatus.SUCCESS)
        with self.assertRaises(StateSealedError):
            state.escalate("S4")


class TestRecords(unittest.TestCase):
    def test_records_are_immutable(self) -> None:
        state = AgentState(goal=GOAL)
        run_tool_cycle(state, "get_course_schedule")

        with self.assertRaises(AttributeError):
            state.plan_history[0].action = PlanAction.FINAL_SYNTHESIS
        with self.assertRaises(TypeError):
            state.tool_observations[0].params["student_id"] = "someone-else"

    def test_execute_tool_plan_requires_tool_name(self) -> None:
        with self.assertRaises(ValueError):
            PlanRecord(iteration=1, action=PlanAction.EXECUTE_TOOL)

    def test_plan_action_must_be_enum(self) -> None:
        with self.assertRaises(TypeError):
            PlanRecord(iteration=1, action="EXECUTE_TOOL", tool_name="x")

    def test_to_dict_is_json_ready(self) -> None:
        import json

        state = AgentState(goal=GOAL)
        run_tool_cycle(state, "get_course_schedule")
        plan_synthesis(state)
        state.complete()

        data = json.loads(json.dumps(state.to_dict()))
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["iteration_count"], 2)
        self.assertEqual(data["plan_history"][0]["action"], "EXECUTE_TOOL")
        self.assertEqual(data["tool_observations"][0]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
