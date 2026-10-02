# WEEK 5 PROGRESS REPORT: Bounded Autonomy, Multi-Step State Machines & Re-planning Loop

**Course:** BSE4104 Emerging Trends In Software Engineering – Capstone Project
**Project:** AI-Native University Student Support Case Agent
**Delivery Timeline:** 28th September, 2026 – 2nd October, 2026
**Primary Focus:** Stateful Re-planning Loop, Bounded Execution Ceilings, Contextual Recovery & Repository Hygiene
**Group Name:** Group C Day

---

## Group Members

| S/N | Name                   | Student Number | Registration Number |
| :-: | :--------------------- | :------------: | :-----------------: |
| 1.  | Bantrobusa Kazibwe FZ  |   2300707416   |   23/U/07416/EVE    |
| 2.  | Baingana Abisha        |   2300707328   |    23/U/07328/PS    |
| 3.  | Mbasani Pauline Peace  |   2300700765   |      23/U/0765      |
| 4.  | Tendo Jemimah Nakayiwa |   2300717920   |    23/U/17920/PS    |
| 5.  | Tusiime Mable          |   2300701494   |      23/U/1494      |

---

### 1. Overview & Core Deliverables

During Week 5, the engineering focus advanced from a linear ReAct loop to a stateful, goal-directed orchestration state machine capable of autonomous recovery under bounded safety ceilings. Grounded in industry best practices for agentic loops, the agent dynamically evaluates intermediate tool observations to adapt its next execution step or terminate cleanly. Key deliverables achieved include:

- **Goal-Directed Orchestrator & Re-planning Engine (`/src/agent/orchestrator.py`):** Implemented a stateful multi-step loop (`Sense -> Plan -> Act -> Observe -> Stop/Re-plan`) enforcing a hard `max_iterations = 3` safety ceiling.
- **Dynamic Observation Evaluation & Recovery:** Implemented intermediate observation inspection to detect failed preconditions, schema mismatches, or empty query results, triggering automated re-planning toward university policy retrieval or administrative ticketing.
- **Cross-Turn Session Context Extraction:** Enhanced session history resolution to extract course codes across sliding-window memory boundaries, enabling seamless follow-up query resolutions without prompt re-seeding.
- **Hardened Iteration-0 Safety Boundaries:** Expanded adversarial detection for mark, grade, and record tampering attempts, enforcing deterministic refusal in $<10\text{ ms}$ with zero token burn prior to upstream LLM calls.
- **Environment & Build Standardization (`pytest.ini`):** Codified unified module discovery (`pythonpath = .`) and permanently purged tracked binary bytecode cache artifacts (`.pyc`, `.db`) from version control.

---

### 2. Team Contributions & Ownership Matrix

| Team Member                | Engineering Role                        | Key Week 5 Deliverables & Ownership                                                                                                                                                                                         |
| :------------------------- | :-------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Baingana Abisha**        | Backend Core & System Architecture Lead | Engineered the dynamic re-planning loop and state transitions in`orchestrator.py`, implemented contextual memory lookups, purged tracked bytecode caches, configured `pytest.ini`, and authored the Week 5 progress report. |
| **Mbasani Pauline Peace**  | AI Engineering & Retrieval Lead         | Authored the formal Agent Task Contract (`task_contract.md`), refined RAG passage formatting for strict inline citation compliance, and maintained sliding memory buffer interfaces.                                        |
| **Bantrobusa Kazibwe FZ**  | Tool Integration & Infrastructure       | Hardened tool execution handlers, standardized dictionary error contracts for recovery workflows, and validated timetable parameter lookups against mock databases.                                                         |
| **Tendo Jemimah Nakayiwa** | Quality Assurance & E2E Testing         | Authored and maintained the automated evaluation suite (`test_orchestrator.py`), asserting green status across session-context retrieval, adversarial grade refusals, and grounded policy citations.                        |
| **Tusiime Mable**          | DevOps & Infrastructure Lead            | Integrated re-plan counter instrumentation and iteration telemetry into`tracker.py`, verifying per-turn latency and model token allocations across all test runs.                                                           |

---

### 3. Technical Governance, Failure Handling & Empirical Traces

- **Bounded Execution Ceiling (`max_iterations = 3`):** The orchestrator strictly limits reasoning cycles. If a plan does not converge within three iterations, execution halts safely with a structured `max_iterations_reached` payload and routes the query directly to human support.
- **Multi-Turn Context Recovery:** When a student refers implicitly to a prior subject (e.g., _"What time is my lecture for the course I mentioned in my first question?"_), the planner traverses previous turn dictionaries and session history buffers to resolve the entity (`BSE4104`) without model hallucination.
- **Empirical Execution Performance:**
  - _Adversarial Refusal (Iteration 0):_ Blocked administrative modification requests in $5.7\text{ ms}$ with 0 prompt tokens.
  - _Contextual Timetable Resolution:_ Completed in 2 iterations (Iteration 1: Tool Dispatch; Iteration 2: Grounded Synthesis) in $1.82\text{ s}$ total latency.
  - _Policy Document Grounding:_ Retrieved vector passages and synthesized responses citing regulations in $5.03\text{ s}$ across 935 tokens.
  - _Support Case Ticketing:_ Validated all 6 required fields to generate ticket `TCK-000008` in $1.41\text{ s}$ with full queue metadata.
- **Repository Data Hygiene:** Purged compiled `.pyc` cache files and local SQLite database instances from Git tracking while enforcing strict ignore rules in root `.gitignore`.

---

### 4. Next Steps (Week 6 Plans)

1. Package and commit empirical production traces into `/docs/traces/` demonstrating happy path, tool failure recovery, and hard safety handoffs.
2. Implement dynamic multi-tool chaining allowing automatic ticket escalation following detected timetable clashes within a single session.
3. Integrate the end-to-end evaluation harness comparing baseline zero-shot prompting versus bounded stateful orchestrator performance.
