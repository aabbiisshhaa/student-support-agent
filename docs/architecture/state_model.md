# State Machine Diagram

**System:** AI-Native University Student-Support Case Agent
**Module:** Agent Workflow & Session State Machine Specification

## 1. Architectural Scope & Design Principles

In accordance with explicit workflow state modeling principles, the Student Support Case Agent models execution state as a deterministic Finite State Machine (FSM) implemented in `src/agent/state.py`.

Runtime state is encapsulated in `AgentState`, which serves as the single source of truth for the entire Sense -> Plan -> Act -> Observe -> Re-plan / Stop cycle. Key architectural invariants:

1. **Deterministic Transition Enforcement:** Only transitions defined in `ALLOWED_STEP_TRANSITIONS` are permitted; illegal steps raise `InvalidTransitionError`.
2. **Terminal State Sealing:** Once a run completes or escalates (`SUCCESS`, `RECOVERED`, or `ESCALATED`), the state is permanently sealed and rejects any further mutations (`StateSealedError`).
3. **Hard Computational Ceilings:** Iteration bounds (`max_iterations = 5`) and recovery limits (`max_replans = 2`) prevent unbounded reasoning loops.
4. **Point-in-Time Observability:** Generates immutable `StateSnapshot` instances for zero-side-effect auditing and telemetry sinks.

---

## 2. Finite State Machine Diagram

![State Machine Diagram](./state_machine_diagram.png)

---

## 3. Workflow Phase Enums & Transitions (`AgentStep` / `WorkflowPhase`)

The lifecycle phases map directly to `AgentStep` in `src/agent/state.py`:

| Phase (`AgentStep`) | Category        | Description                                                                          | Permitted Next Steps (`ALLOWED_STEP_TRANSITIONS`) |     |
| :------------------ | :-------------- | :----------------------------------------------------------------------------------- | :------------------------------------------------ | --- |
| `SENSE`             | Intake & Safety | Evaluates user input against safety guardrails and institutional boundaries.         | `PLAN`, `STOP`                                    |     |
| `PLAN`              | Strategy        | Selects deterministic tool actions, policy retrievals, or final synthesis.           | `ACT`, `STOP`                                     |     |
| `ACT`               | Action          | Dispatches deterministic institutional tools (`get_course_schedule`, `ticket_tool`). | `OBSERVE`                                         |     |
| `OBSERVE`           | Assessment      | Evaluates tool execution status (`ok` vs. `error`) and records latency.              | `PLAN`, `REPLAN`, `STOP`                          |     |
| `REPLAN`            | Recovery        | Reformulates strategy upon failure within bounded`max_replans`.                      | `ACT`, `STOP`                                     |     |
| `STOP`              | Terminal        | Seals state with`SUCCESS`, `RECOVERED`, or `ESCALATED` status.                       | _None_ (Terminal Node)                            |     |

---

## 4. State Representation & Snapshot Schema

At any point during execution, the agent's complete state is represented and captured via the following typed schema[cite: 1]:

| Field Name          | Type                   | Description                                                                                   |
| :------------------ | :--------------------- | :-------------------------------------------------------------------------------------------- |
| `goal`              | `str`                  | The high-level intent or user problem being resolved by the run[cite: 1].                     |
| `current_step`      | `str`                  | Current active lifecycle step (`sense`, `plan`, `act`, `observe`, `replan`, `stop`)[cite: 1]. |
| `status`            | `str`                  | Run status:`running`, `success`, `recovered`, or `escalated`.                                 |
| `iteration_count`   | `int`                  | Number of completed planning/replanning cycles ($0 \le i \le \text{max\_iterations}$).        |
| `max_iterations`    | `int`                  | Hard computational cap on planning cycles (default: 5).                                       |
| `max_replans`       | `int`                  | Hard limit on recovery replanning cycles (default: 2).                                        |
| `session_id`        | `Optional[str]`        | Unique session identifier mapping to the conversation container.                              |
| `student_id`        | `Optional[str]`        | Verified student registration/identifier (e.g.,`"2300712345"`).                               |
| `context_snippets`  | `List[Dict[str, Any]]` | Grounded policy passages retrieved from institutional knowledge stores.                       |
| `plan_history`      | `List[Dict[str, Any]]` | Chronological list of serialized`PlanRecord` plans created during the run.                    |
| `tool_observations` | `List[Dict[str, Any]]` | Chronological list of serialized`ToolObservation` records capturing tool returns.             |
| `timestamp`         | `str`                  | ISO 8601 UTC timestamp of the snapshot capture.                                               |

### Example Serialized JSON State Snapshot

```json
{
  "goal": "Retrieve timetable for BSE4104",
  "current_step": "observe",
  "status": "running",
  "iteration_count": 1,
  "max_iterations": 5,
  "max_replans": 2,
  "session_id": "session-live-01",
  "student_id": "2300712345",
  "context_snippets": [],
  "plan_history": [
    {
      "iteration": 1,
      "action": "EXECUTE_TOOL",
      "tool_name": "get_course_schedule",
      "tool_params": { "course_code": "BSE4104" },
      "rationale": "Fetch lecture schedule",
      "is_replan": false,
      "timestamp": "2026-10-09T07:15:00.000Z"
    }
  ],
  "tool_observations": [
    {
      "iteration": 1,
      "tool": "get_course_schedule",
      "params": { "course_code": "BSE4104" },
      "status": "ok",
      "result": { "slots": ["Mon 09:00 - 11:00", "Wed 11:00 - 13:00"] },
      "latency_ms": 32.5,
      "timestamp": "2026-10-09T07:15:00.032Z"
    }
  ],
  "timestamp": "2026-10-09T07:15:00.035Z"
}
```

---

## 5. Invariant Checks & Guardrail Rules

1. **State Invariance:** Direct field mutations are rejected; transitions must occur through `advance_to()`, `record_plan()`, and `record_observation()`.
2. **Terminal Inviolability:** Once `finish()`, `complete()`, or `escalate()` is invoked, the state transitions to `AgentStep.STOP` and raises `StateSealedError` on any subsequent modification attempt.
3. **Recovery Semantics:** A run that experienced tool failures cannot complete with `AgentStatus.SUCCESS`; it must complete as `AgentStatus.RECOVERED` or `AgentStatus.ESCALATED`.
4. **Bounded Iterations & Replans:** Entering `PLAN` or `REPLAN` increments `iteration_count`. If `iteration_count >= max_iterations`, execution raises `IterationLimitExceededError`. If `replan_count >= max_replans`, entering `REPLAN` raises `ReplanLimitExceededError`.
5. **Human Escalation Safety:** An escalation handoff (`escalate()`) requires an explicit `escalation_reason` string and seals the run immediately from any open step.
