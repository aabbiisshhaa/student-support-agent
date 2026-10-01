# Agent Task Contract & Scope Specification

**System:** AI-Native University Student-Support Case Agent
**Workflow:** Course Retake & Timetable Conflict Resolution
**Course:** BSE4104 Emerging Trends in Software Engineering
**Delivery Window:** Week 5 (28th September – 2nd October 2026)
**AI Safety Impact:** Deterministic Code
**Evidence Category:** Specification / API
**Related artifacts:** [`ai-boundary-matrix.md`](../requirements/ai-boundary-matrix.md), [`tool_definitions.json`](../../src/schemas/tool_definitions.json), [`failure_modes_and_eval.md`](../eval/failure_modes_and_eval.md), [`src/agent/orchestrator.py`](../../src/agent/orchestrator.py), `src/agent/state.py` (AgentState, Week 5)

---

## 1. Purpose of this Contract

This document is the formal contract for one bounded, multi-step agent workflow. It defines exactly:

1. what the agent is trying to achieve,
2. what it needs before it starts,
3. which tools it may call,
4. which internal states it may be in,
5. how many steps it may take, and
6. when it must stop and hand the case to a human.

Anything this contract does not explicitly allow is **forbidden**. The rules here are enforced by deterministic Python code (the orchestrator, the tool validators and the `AgentState` object). They are **not** enforced by asking the language model to behave.

### Why this task needs a multi-step agent

A student with a failed course (grade **F**) must retake it "the next time the course is offered" [Nakawa University Academic Handbook 2025/2026, s. 7 (Retakes and Progression), p. 4]. That retake slot can clash with the student's current courses. Answering "Can I retake CSC3103 and will it clash with my timetable?" requires several dependent steps:

1. Retrieve the retake policy so the answer is grounded.
2. Read the student's current timetable.
3. Read the retake course's scheduled sessions.
4. Detect overlaps deterministically.
5. Decide whether to stop with an answer, re-plan after a failure, or escalate to staff.

A single prompt cannot do this safely. Each step depends on the observation from the step before it, which is why this workflow uses the **Sense → Plan → Act → Observe → Re-plan / Stop** loop.

---

## 2. Goal Statement

> **Given an authenticated student and one course they must retake, the agent will produce a grounded, citation-backed report that (a) states the applicable retake rules, (b) lists every timetable clash between the retake course and the student's current registered courses (or confirms there are none), and (c) either finishes with that report or hands the case to a human with a confirmed support ticket. It must do this within the iteration limit and without changing any academic, fee or registration record.**

### 2.1 Definition of Done (success criteria)

A run reaches `success` only when **all** of the following are true:

| # | Criterion | Checked by |
|---|---|---|
| G1 | At least one retake-policy passage was retrieved, and the response cites it in the corpus citation format, e.g. `[Nakawa University Academic Handbook 2025/2026, s. 7 (Retakes and Progression), p. 4]`. | Orchestrator: `context_snippets` is not empty |
| G2 | The student's current timetable was read successfully by `get_course_schedule`. | `tool_observations` entry with `status == "ok"` |
| G3 | The retake course's sessions were read successfully. | `tool_observations` entry with `status == "ok"` |
| G4 | Conflicts were calculated by the deterministic overlap function, not by the model. | `detect_schedule_conflicts` output stored in state |
| G5 | The response states only facts present in G1–G4. | Grounding rule in the system prompt and the evaluation suite |
| G6 | No stop or escalation condition from Section 7 was triggered. | `AgentState.status` |

### 2.2 Out of scope (non-goals)

The agent will **never**:

- register, drop, add or withdraw a student from any course;
- change a grade, mark, transcript or retake attempt count;
- waive, reduce or clear a retake fee;
- choose which course a student should give up when a clash exists, because this is an academic decision for the Faculty or Head of Department;
- approve a withdrawal on Form AR/7, which is decided by the Faculty Board;
- invent a timetable slot, room, lecturer, date or policy rule.

These limits follow rows 5 and 6 of the [AI Boundary Matrix](../requirements/ai-boundary-matrix.md).

---

## 3. Input Requirements

The workflow does not start until every **required** input passes deterministic validation. Validation failures do not call the model. The agent returns a fixed clarification message, or escalates according to Section 7.

| Input | Required | Source | Validation rule (deterministic) | On failure |
|---|---|---|---|---|
| `session_id` | Yes | Session manager (`src/agent/memory.py`) | Must exist or be created by `SessionMemoryManager.initialize_session` | Reject the run |
| `student_id` | Yes | The session's bound `student_ref` (set and checked by `open_session` in `src/app.py`, which rejects a session that belongs to another student). Never taken from free text in the message | `^[A-Za-z0-9][A-Za-z0-9/_-]{2,29}$` (same pattern as `tool_definitions.json`) | Reject the run. No tool is called |
| `user_query` | Yes | Student message | 1–2000 characters after trimming (same limit as `original_message` in `tool_definitions.json`; **to be added**, as no length check exists in `orchestrator.py` yet). Prohibited-intent screen runs **before** iteration 1 | Prohibited intent → `escalated` at iteration 0 |
| `retake_course_code` | Yes | Extracted from `user_query`, or from recent session history if missing | `\b[A-Za-z]{3}\d{4}\b`, stored in upper case | Ask the student **once**. If still missing → escalate (S6) |
| `target_semester` | No | Student message, otherwise the current semester from the Academic Calendar | One of `"I"`, `"II"`, `"recess"` | Default to the current semester and state this assumption in the response |
| `student_confirmed` | Only for a ticket | Explicit "yes" from the student after seeing the draft ticket | Must be literally `true` (schema `enum: [true]`) | Ticket is **not** created; the run ends `escalated` with "awaiting confirmation" |

**Rule I-1:** The `student_id` used in every tool call must equal the authenticated `student_id` of the session. A student can never look up another student's timetable, even if they type another ID.

**Rule I-2:** Only one retake course is handled per run. If the student names several courses, the agent handles the first and asks the student to submit the others separately. This keeps the iteration budget predictable.

---

## 4. Approved Tools

The agent may only call tools listed in this table. The orchestrator's `_dispatch_tool` method is the allow-list. Any other tool name returns `{"error": "Tool '<name>' not recognized."}` and counts as a failed step.

| # | Tool / action | Planner action | Side effects | Permission | Implementation status |
|---|---|---|---|---|---|
| T1 | `retriever.retrieve(query, top_k=2)` (policy search over the approved corpus) | `RETRIEVE_KNOWLEDGE` | None (read-only) | Autonomous | Implemented: `src/rag/retriever.py` |
| T2 | `get_course_schedule(student_id, course_code?, day?)` | `EXECUTE_TOOL` | None (read-only) | Autonomous, own `student_id` only | Implemented: `src/tools/timetable_tool.py` |
| T3 | `get_course_offering(course_code, semester)` (scheduled sessions for the retake course) | `EXECUTE_TOOL` | None (read-only) | Autonomous | **Planned for Week 5.** Must follow the same schema-validation style as T2 |
| T4 | `detect_schedule_conflicts(current, retake)` (pure overlap calculation) | Runs inside **Observe**. It is not chosen by the planner | None (pure function) | Deterministic, always runs after T2 and T3 succeed | **Planned for Week 5** |
| T5 | `create_support_ticket(student_id, summary, original_message, category, priority, student_confirmed)` | `EXECUTE_TOOL` | **Writes a ticket record** | **Only with `student_confirmed == true`** | Implemented: `src/tools/ticket_tool.py` |
| T6 | Final response generation (Gemini or the deterministic formatter) | `FINAL_SYNTHESIS` | None | Autonomous, grounded only in observations | Implemented: `_synthesize_response` |

### 4.1 Tool rules

- **R-T1 Read before write.** T5 is the only tool with side effects, and it can only be called as the final action of a run.
- **R-T2 Schema first.** Every tool argument is validated **before** execution by the validators inside each tool module (`_validate_student_id`, `_validate_course_code`, `_validate_summary`, etc.), which use the same patterns and limits as `src/schemas/tool_definitions.json`. New tools (T3) must follow the same pattern. Invalid arguments are a failed step; they are never "fixed" by the model.
- **R-T3 No model-computed facts.** Clash detection (T4), ticket IDs, queue routing and dates are always computed by code. The model only phrases the result.
- **R-T4 Category for T5.** Retake and clash tickets use `category = "timetable"` (Timetable & Registration Queue). Retake-attempt and discontinuation risk cases use `category = "policy"` and `priority = "high"`.
- **R-T5 One call per tool per plan step.** A tool may be retried **at most once** after a failure (see Section 6).

### 4.2 Conflict detection rule (T4, deterministic)

Two sessions `a` and `b` clash when:

```
a.day == b.day  AND  a.start_time < b.end_time  AND  b.start_time < a.end_time
```

Times are compared as `HH:MM` 24-hour strings in East Africa Time. Sessions that only touch (one ends at 11:00 and the next starts at 11:00) **do not** clash. The output is a list of `{retake_session, current_session, overlap_minutes}`. An empty list means "no clash".

---

## 5. Permissible Internal States

The run state is held in one strongly typed `AgentState` object (`src/agent/state.py`). The model never edits this object directly. Only orchestrator code writes to it.

### 5.1 State fields

| Field | Type | Meaning |
|---|---|---|
| `goal` | `str` | The goal from Section 2, filled in with the course code |
| `current_step` | `AgentStep` enum | Current phase of the loop (Section 5.2) |
| `plan_history` | `list[PlanRecord]` | Every plan the planner produced, in order, including re-plans |
| `tool_observations` | `list[ToolObservation]` | Every tool call: tool, params, `ok`/`error`, result, latency |
| `status` | `AgentStatus` enum | `running`, `success`, `recovered` or `escalated` |
| `iteration_count` | `int` | Number of completed Plan → Act → Observe cycles, including re-plans |

### 5.2 Loop steps (`current_step`)

| Step | What happens | Who decides |
|---|---|---|
| `SENSE` | Load session context, validate inputs, run the prohibited-intent screen | Deterministic code |
| `PLAN` | Choose the next allowed action from Section 4 | Rule-based planner (`_plan_next_step`) |
| `ACT` | Execute exactly one approved tool | Deterministic dispatcher |
| `OBSERVE` | Record the result, run T4 when both schedules are present, check stop conditions | Deterministic code |
| `REPLAN` | After a failed step, choose a recovery action (retry once, or escalate) | Rule-based planner |
| `STOP` | Produce the final response and seal the state | Deterministic code + T6 |

### 5.3 Run status (`status`) and allowed transitions

Only these four values are allowed, which matches the [Terminal Status Contract](../eval/failure_modes_and_eval.md#3-terminal-status-contract).

| Status | Terminal? | Meaning |
|---|---|---|
| `running` | No | The loop is in progress. This is the only starting status |
| `success` | Yes | All of G1–G6 are met with no tool failures |
| `recovered` | Yes | At least one step failed, a single retry or safe fallback worked, and the student got a correct, grounded answer |
| `escalated` | Yes | A stop condition from Section 7 fired. A human must act |

```
            ┌──► success     (terminal)
 running ───┼──► recovered   (terminal)
            └──► escalated   (terminal)
```

Allowed transitions: `running → success`, `running → recovered`, `running → escalated`.
**Every other transition is invalid**, including any transition out of a terminal status. `AgentState` must raise an error if code tries one. Once a run is terminal, its state is frozen and the loop must not take another step.

---

## 6. Maximum Iteration Limits

| Limit | Value | Enforced by |
|---|---|---|
| `RETAKE_WORKFLOW_MAX_ITERATIONS` | **5** Plan → Act → Observe cycles | `AgentState.iteration_count` checked before each `PLAN` |
| Retries per tool after a failure | **1** | Re-plan rule R-6 |
| Total re-plans per run | **2** | `plan_history` entries with `is_replan == True` |
| Clarification questions to the student | **1** (missing course code) | Input rule in Section 3 |
| Support tickets created per run | **1** | T5 is final-only (R-T1) |
| Policy passages per retrieval | `top_k = 2` | Retriever call |

**Why 5?** The minimum successful path needs 4 cycles: (1) retrieve policy, (2) read current timetable, (3) read retake offering, (4) final synthesis. T4 runs inside Observe and does not use a cycle. One extra cycle allows a single retry after a recoverable failure. More than that adds cost and latency without making the answer better.

**Relationship to the general agent cap.** The general question-answering loop keeps `MAX_AGENT_ITERATIONS = 3` in `src/agent/orchestrator.py`. That constant and its tests are **not** changed by this contract. The retake workflow gets its own constant so that the existing safety tests keep passing.

**Re-plan rules:**

- **R-6** A failed read-only tool (T1–T3) may be retried once with the **same validated arguments**. A second failure on the same tool triggers stop condition S5.
- **R-7** A validation error such as an invalid course code is **not** retried, because retrying unchanged input cannot succeed. It goes to the clarification rule in Section 3 or escalates.
- **R-8** The planner may not choose an action identical to its previous one after a success (prevents loops).

When `iteration_count` reaches 5 without a terminal status, the run stops at once with status `escalated` (stop condition S4).

---

## 7. Explicit Stopping & Escalation Conditions (Human Hand-off)

These checks are deterministic and run in **SENSE** (before any tool call) and in **OBSERVE** (after every tool call). The first condition that matches ends the run.

### 7.1 Normal stop conditions

| ID | Condition | Final status | What the student is told |
|---|---|---|---|
| N1 | G1–G6 met and no clash found | `success` | Retake rules with citations, plus confirmation that the retake slot does not clash |
| N2 | G1–G6 met and clash(es) found, and the student asked for information only | `success` | Retake rules, a list of each clash, and the office to contact. The agent does not choose a course to drop |
| N3 | A step failed, the single retry succeeded, and the full report was produced | `recovered` | Same as N1 or N2 |

### 7.2 Escalation conditions (human hand-off required)

| ID | Trigger (deterministic) | Final status | Hand-off target | Ticket |
|---|---|---|---|---|
| S1 | **Prohibited intent** in the query, matched against `SupportAgentOrchestrator.PROHIBITED_INTENTS` (e.g. "change my grade", "fee waiver", "tuition refund", "modify academic records", "disciplinary appeal"). The current list does not catch retake-specific wording such as "waive my retake fee" or "reset my retake attempts"; these phrases **must be added** when the workflow is implemented | `escalated` at **iteration 0**, no tool calls | Department administrator (`HARD_REFUSAL_MESSAGE`) → General Administration Queue | Offered, `category="administrative"` |
| S2 | **Clash with no clash-free option** and the student asks what to do | `escalated` | Timetable & Registration Queue, for the Faculty Registrar / Head of Department to decide | Drafted with `category="timetable"`, needs confirmation |
| S3 | **Discontinuation risk:** the student says this would be their 4th attempt at the course (policy limits retakes to 3, [Nakawa University Academic Handbook 2025/2026, s. 7 (Retakes and Progression), p. 4]) | `escalated` | Academic Policy Queue | Drafted with `category="policy"`, `priority="high"` |
| S4 | **Iteration limit reached** (`iteration_count == 5`) without a terminal status | `escalated` | General Administration Queue | Offered, `category="administrative"` |
| S5 | **Same tool failed twice** (after the one allowed retry), or `StudentNotFoundError` | `escalated` | Timetable & Registration Queue | Offered, `category="timetable"` |
| S6 | **Missing or invalid course code** after one clarification question | `escalated` | Timetable & Registration Queue | Offered, `category="timetable"` |
| S7 | **No policy evidence found** for the retake question (empty retrieval twice) | `escalated` | Academic Policy Queue | Offered, `category="policy"`. The agent states it "cannot confirm this from official records" |
| S8 | **Withdrawal or administrative-error clash claim**, e.g. "the University put two of my courses at the same time". This needs Form AR/7 and a Faculty Board decision | `escalated` | Timetable & Registration Queue, for a Faculty Board decision on Form AR/7 | Drafted with `category="timetable"` |
| S9 | **Outside the retake registration window** published in the Academic Calendar | `escalated` | Timetable & Registration Queue | Offered, `category="timetable"` |
| S10 | **Distress or urgency cues** (e.g. "I will be discontinued", "I am desperate") matched against a fixed keyword list, as required by Boundary Matrix row 6. **This list does not exist in the code yet and must be added** | `escalated` | General Support Queue, flagged for Student Support Services | Offered, `category="other"`, `priority="high"` |
| S11 | **Unknown planner action** or an unregistered tool requested twice | `escalated` | General Administration Queue | Offered, `category="administrative"` |

### 7.3 Hand-off rules

- **H-1 Confirmation gate.** A ticket is only written when `student_confirmed == true`. Until then, the run ends with status `escalated` and a **drafted** ticket, plus the message "Reply *yes* to submit this ticket".
- **H-2 Complete hand-off package.** Every escalation records the following in `AgentState`, so staff do not need to ask the student again: the goal, `plan_history`, all `tool_observations`, any detected clashes, and the escalation ID (S1–S11).
- **H-3 Honest status.** An escalated run never claims success. The response says plainly that a human must complete the task.
- **H-4 No unilateral action.** Escalation means routing to a human queue. The agent does not contact staff, change records or promise an outcome.

---

## 8. Run Output Contract

Every run returns the existing orchestrator result shape, plus the workflow fields below:

```json
{
  "status": "success | recovered | escalated",
  "response": "string shown to the student",
  "escalation_required": true,
  "escalation_reason": "S2",
  "iterations": 4,
  "tool_calls": [
    {"tool": "get_course_schedule", "params": {}, "status": "ok", "result": [], "latency_ms": 3.1}
  ],
  "conflicts": [
    {"retake_session": {}, "current_session": {}, "overlap_minutes": 60}
  ],
  "plan_history": [
    {"iteration": 1, "action": "RETRIEVE_KNOWLEDGE", "is_replan": false}
  ]
}
```

`status`, `response`, `escalation_required`, `iterations` and `tool_calls` are required for all runs, matching the existing tests. `escalation_reason`, `conflicts` and `plan_history` are added by this workflow. `escalation_reason` is `null` unless `status == "escalated"`.

---

## 9. Reference Execution Paths

| Trace | Path | Iterations | Final status |
|---|---|---|---|
| A: Happy path, no clash | SENSE → RETRIEVE (T1) → T2 → T3 → T4 in Observe → SYNTHESIS | 4 | `success` |
| B: Recovery | SENSE → T1 → T2 **fails** → REPLAN (retry T2) → T2 ok → T3 → SYNTHESIS | 5 | `recovered` |
| C: Clash needing an academic decision | SENSE → T1 → T2 → T3 → T4 finds a clash → student asks which to drop → S2 → draft ticket | 4 | `escalated` |
| D: Prohibited request | SENSE: "I want a fee waiver for my retake" → S1 | 0 | `escalated` |

These traces are the acceptance tests for the Week 5 "three execution traces" deliverable. Trace B is the required failure-and-recovery case.

---

## 10. Traceability

| Contract clause | Implemented / verified in |
|---|---|
| Prohibited-intent screen (S1) | `SupportAgentOrchestrator.PROHIBITED_INTENTS`, `tests/agent/test_traces.py` |
| Terminal statuses (Section 5.3) | `VALID_RUN_STATUSES` in `orchestrator.py`; `AgentStatus` in `src/agent/state.py` |
| Tool allow-list (Section 4) | `_dispatch_tool` in `orchestrator.py`; `src/schemas/tool_definitions.json` |
| Ticket confirmation gate (H-1) | `create_support_ticket(student_confirmed=...)` in `src/tools/ticket_tool.py` |
| Iteration limits (Section 6) | `AgentState.iteration_count` (Week 5); `MAX_AGENT_ITERATIONS` for the general loop |
| Failure-mode coverage | `docs/eval/failure_modes_and_eval.md` |

---

## 11. Change Control

This contract is versioned with the code. Any change to the goal, tool list, limits or escalation table must:

1. update this file in the same pull request as the code change;
2. update or add a test that proves the new rule;
3. be reviewed by at least one other team member before merging into `main`.

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-10-01 | First contract for the Course Retake & Timetable Conflict Resolution workflow |
| 1.1 | 2026-10-01 | Aligned with existing code: real citation format, ticket queues from `CATEGORY_QUEUES`, session-bound `student_id`, tool-module validators; marked missing pieces (retake prohibited phrases, distress keywords, input length check) as to be added |
