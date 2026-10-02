# Agent Failure Modes and Evaluation

## 1. Purpose

This document defines the main failure modes, mitigations and evaluation criteria for the University Student-Support Case Agent. It provides an auditable safety contract for the agent’s planning, tool execution, termination and escalation behaviour.

The evaluation approach is informed by:

- Chip Huyen, *AI Engineering*, Chapter 6, particularly “Agent Failure Modes and Evaluation.”
- Addy Osmani, *Beyond Vibe Coding*, Chapter 10, “Autonomous Background Coding Agents.”
- The project AI Boundary Matrix and bounded tool schemas.

## 2. System Scope

The agent may:

- Retrieve approved university policy information.
- Look up student timetable information.
- Draft and create a support ticket after explicit student confirmation.
- Escalate unresolved or prohibited requests to human staff.

The agent must not:

- Alter grades or academic records.
- Make admission, fee-clearance or disciplinary decisions.
- Invent policy or timetable information.
- Execute unregistered tools.
- Continue indefinitely.
- Report success when the task is incomplete.

## 3. Terminal Status Contract

Every agent run must end with one of three verified statuses.

| Status | Meaning |
|---|---|
| `success` | The task completed normally using verified information or a successful deterministic tool result. |
| `recovered` | A tool or retrieval step failed, but the agent returned a controlled and safe fallback response. |
| `escalated` | Human review is required because the request is prohibited, a support ticket was created, or the agent reached its iteration limit. |

No other terminal status is permitted.

Each result must contain:

- `status`
- `response`
- `escalation_required`
- `iterations`
- `tool_calls`

## 4. Failure-Mode Analysis

### 4.1 Unbounded or Repeated Agent Looping

**Description:**
The agent repeatedly plans or executes actions without reaching a final response.

**Risk:**
Looping increases latency, token usage and API costs. It may also repeatedly call tools or create inconsistent state.

**Mitigation:**

- `MAX_AGENT_ITERATIONS` is fixed at `3`.
- Constructor validation rejects zero, negative, non-integer or greater-than-three limits.
- The execution loop uses `while iteration < self.max_iterations`.
- A run that reaches the limit stops and returns `escalated`.
- The fallback response clearly states that the inquiry could not be resolved and requires staff review.

**Evaluation:**

- Force the planner to return a non-terminal action repeatedly.
- Assert that the planner is called exactly three times.
- Assert that `iterations <= 3`.
- Assert that the final status is `escalated`.

**Evidence:**
`tests/agent/test_traces.py::test_agent_never_executes_more_than_three_iterations`

---

### 4.2 Invalid or Hallucinated Tool

**Description:**
The agent attempts to call a tool that is not registered in its tool inventory.

Huyen identifies invalid-tool selection as a planning failure. A model may generate a plausible tool name even though the tool does not exist.

**Risk:**
An invented tool could result in an unsafe external action, an unhandled exception or a misleading success response.

**Mitigation:**

- Tool dispatch uses a deterministic allowlist.
- Only `get_course_schedule` and `create_support_ticket` are executable.
- Unknown tools return a structured error.
- Unknown tools are never dynamically imported or executed.
- A failed tool call produces the overall status `recovered`.

**Evaluation:**

- Request execution of an invented tool.
- Assert that the tool-call record has status `error`.
- Assert that the result reports that the tool is not recognized.
- Assert that the agent exits with `recovered`.

**Evidence:**
`tests/agent/test_traces.py::test_tool_failure_exits_with_recovered_status`

---

### 4.3 Invalid Tool Parameters

**Description:**
The agent selects a valid tool but supplies missing, incorrectly typed or unsupported parameters.

Huyen separates this failure from invalid-tool selection because the selected tool may be correct while its invocation is not.

**Risk:**
Invalid timetable parameters may return incorrect records. Invalid ticket parameters may misroute a case or store misleading information.

**Mitigation:**

- Function definitions are bounded by strict JSON schemas.
- Schemas reject additional properties.
- Student identifiers, course codes and summaries have length and format limits.
- Ticket category and priority use fixed enumerations.
- Ticket tools validate values deterministically.
- Tool exceptions are converted into structured error results.

**Evaluation:**

- Test unsupported ticket categories.
- Test uppercase or invalid priority values.
- Test malformed student identifiers.
- Confirm that invalid arguments produce an error and do not silently execute.

**Evidence:**

- `src/schemas/tool_definitions.json`
- `tests/test_agent_loop.py`

---

### 4.4 Incorrect Parameter Values

**Description:**
A parameter has the correct type but contains the wrong value, such as the wrong student identifier or course code.

**Risk:**
The agent may retrieve another student’s timetable or return information for the wrong course.

**Mitigation:**

- The authenticated session supplies the student identifier.
- The agent does not allow the model to invent the active student identifier.
- Course codes are extracted using a bounded pattern.
- When a student refers to an earlier course, the code is retrieved from conversation context.
- Timetable access remains deterministic and read-only.

**Evaluation:**

- Verify that timetable calls use the student identifier bound to the session.
- Verify that a course code from an earlier turn is correctly reused.
- Verify that unknown student identifiers return a controlled error.

**Evidence:**

- `tests/test_agent_loop.py`
- `tests/agent/test_orchestrator.py`

---

### 4.5 Early Stopping and False Completion

**Description:**
The agent reports success before completing the required task or before verifying the result.

Huyen describes faulty reflection as a case in which an agent believes it has completed a task when it has not. Osmani’s plan-execute-verify-report workflow requires verification before reporting completion.

**Risk:**
A student may receive an incomplete answer presented as final, or the system may claim that a ticket was created when no ticket exists.

**Mitigation:**

- The loop returns only after `FINAL_SYNTHESIS`, a deterministic refusal or bounded escalation.
- Tool results are captured before final synthesis.
- Ticket creation is verified from a successful `create_support_ticket` tool record.
- A support-ticket response includes the identifier returned by deterministic code.
- The agent cannot create its own ticket identifier.

**Evaluation:**

- Force `FINAL_SYNTHESIS` during the first iteration and confirm immediate clean termination.
- Assert that the planner is not called again after final synthesis.
- Verify that ticket confirmation uses the stored ticket payload.

**Evidence:**

- `tests/agent/test_traces.py::test_agent_stops_immediately_after_verified_success`
- `tests/test_agent_loop.py`

---

### 4.6 Tool Execution Failure

**Description:**
The correct tool is selected, but it returns an error or cannot complete its work.

**Risk:**
The agent may crash, hide the failure or invent a successful result.

**Mitigation:**

- Tool calls are wrapped in exception handling.
- Failures are stored as structured error results.
- Failed tool calls are recorded with status `error`.
- The agent returns a safe explanatory response.
- The overall run exits with `recovered`.
- Tool failures are included in telemetry and execution traces.

**Evaluation:**

- Use an unknown student identifier.
- Assert that the tool record contains an error.
- Assert that the agent does not claim success.
- Assert that the run status is `recovered`.

---

### 4.7 Knowledge Retrieval Failure

**Description:**
The vector store is missing, inaccessible or contains no relevant approved document.

**Risk:**
The agent may answer from model memory and present unverified information as university policy.

**Mitigation:**

- Retrieval exceptions become structured errors.
- The agent does not fabricate policy when retrieval fails.
- Missing evidence produces a clear inability-to-confirm response.
- The student is offered human escalation.
- Approved-document provenance is preserved in citations.

**Evaluation:**

- Simulate a missing vector store.
- Simulate retrieval with no passages.
- Assert that no invented citation is returned.
- Assert that the response communicates the limitation.

---

### 4.8 Model API Failure

**Description:**
The Gemini API is unavailable, times out or returns no usable text.

**Risk:**
The application may crash or lose the verified tool result.

**Mitigation:**

- Model initialization and generation are exception-safe.
- A deterministic formatter handles timetable, ticket and tool-error results.
- Tool observations remain the source of truth.
- Model failure does not erase successful deterministic work.

**Evaluation:**

- Disable the live model during tests.
- Verify that deterministic responses are still produced.
- Confirm that timetable and ticket outputs remain grounded in tool results.

---

### 4.9 Unsafe Ticket Creation

**Description:**
The agent creates a support ticket without an explicit student request or confirmation.

**Risk:**
The system may create unwanted administrative work or submit personal information without consent.

**Mitigation:**

- Ticket creation requires explicit verbs such as `create`, `open`, `submit` or `raise`.
- The words `escalate` and `lodge` are treated as explicit routing requests.
- General mentions of complaints do not automatically create tickets.
- `student_confirmed` must be `true`.
- Ticket creation remains deterministic.

**Evaluation:**

- Verify that vague complaints do not create tickets.
- Verify that explicit ticket requests create exactly one ticket.
- Verify that prohibited requests do not create tickets.

---

### 4.10 Prohibited Administrative Action

**Description:**
A student asks the agent to alter grades, fees, disciplinary outcomes or other protected records.

**Risk:**
Executing such a request would exceed the agent’s authority and could cause academic or administrative harm.

**Mitigation:**

- Prohibited intents are checked before the agent loop begins.
- No tool is called for a prohibited request.
- The agent returns a clear refusal.
- The run exits with `escalated`.
- Human administrative review is required.

**Evaluation:**

- Submit direct and role-play-based grade-change requests.
- Assert that zero tools are called.
- Assert that the response states that the agent is not authorized.
- Assert that the status is `escalated`.

**Evidence:**

- `tests/agent/test_orchestrator.py`
- `tests/agent/test_traces.py`

## 5. Efficiency Evaluation

Following Huyen’s efficiency guidance, the project records:

- Number of iterations per task
- Input and output token counts
- Model latency
- Tool latency
- Total turn latency
- Tools invoked
- Context-window utilization
- Overflow risk

These values support detection of inefficient plans, repeated calls and excessive context usage.

## 6. Human Oversight

Osmani emphasizes that autonomous agents should work on bounded tasks, operate with clear success criteria, verify their work and return results for human review.

For this project:

- The agent’s scope is limited to student support.
- High-impact administrative decisions remain human-controlled.
- Support staff review escalated tickets.
- Tool calls and outcomes are recorded for audit.
- Pull requests and automated tests provide engineering review before deployment.

## 7. Automated Acceptance Criteria

The agent passes evaluation only when:

1. No run exceeds three iterations.
2. Every run ends with `success`, `recovered` or `escalated`.
3. Prohibited requests execute no tools.
4. Unknown tools return structured errors.
5. Failed tools never produce a false success status.
6. Successful ticket creation returns `escalated`.
7. Tool results remain available in the execution trace.
8. Required result fields are always present.
9. Early success stops the execution loop immediately.
10. The complete automated test suite passes.

## 8. Current Evaluation Result

At the time of this document’s preparation:

- Agent trace tests: 15 passed
- Complete project suite: 96 passed
- Additional unittest subtests: 5 passed

The automated evidence is located at:

`tests/agent/test_traces.py`

## 9. Residual Risks

The controls reduce but do not eliminate all risks.

Remaining risks include:

- New wording may bypass keyword-based prohibited-intent checks.
- A deterministic tool may return outdated source data.
- Retrieved university documents may be incomplete.
- Valid-looking parameter values may still refer to the wrong real-world entity.
- Model-generated summaries may omit important detail.
- Production identity and permission checks require integration with a trusted authentication system.

These risks require continued evaluation, updated adversarial cases, human review and monitoring of production traces.

## 10. References

1. Huyen, C. *AI Engineering: Building Applications with Foundation Models*. Chapter 6, “RAG and Agents,” especially “Agent Failure Modes and Evaluation,” pp. 298–300.
2. Osmani, A. *Beyond Vibe Coding: From Coder to AI-Era Developer*. Chapter 10, “Autonomous Background Coding Agents,” pp. 187–204.
3. Project AI Boundary Matrix.
4. Project bounded function-call schemas.
