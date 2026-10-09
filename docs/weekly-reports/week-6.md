# WEEK 6 PROGRESS REPORT: State Modeling, Memory Governance & Interoperability

**Course:** BSE4104 Emerging Trends In Software Engineering – Capstone Project
**Project:** AI-Native University Student Support Case Agent
**Delivery Timeline:** 5th October, 2026 – 9th October, 2026
**Primary Focus:** Finite State Machine (FSM), Persistent Case Memory, Data Compliance, MCP Interface Contract, and Telemetry Tracing
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

## 1. Overview & Core Deliverables

During Week 6, the development focus transitioned the Student Support Case Agent from an implicit reactive agent into a formal, mathematically bounded Finite State Machine (FSM) backed by persistent cross-session memory governance and modular tool protocols. By establishing strictly typed state containers, immutable snapshot persistence, role-based memory boundaries, and standard JSON-RPC interfaces, the agent's behavior is explicitly constrained by deterministic software rather than heuristic model alignment.

All engineering work packages for Week 6 were executed across five key tasks:

1. **Typed State Architecture:** Formulated discrete lifecycle enums, immutable snapshot models, and mathematical transition invariants (`docs/architecture/state_model.md`, `src/agent/state.py`).
2. **Deterministic Orchestrator Integration:** Refactored `SupportAgentOrchestrator` to execute under explicit FSM phases with point-in-time state snapshots captured before and after tool calls (`src/agent/orchestrator.py`).
3. **Justified Persistent Memory Layer:** Implemented an isolated SQLite/JSON-backed store for academic profile retention across independent conversation sessions (`src/agent/persistent_memory.py`, `tests/agent/test_memory.py`).
4. **Data Handling & Compliance Architecture:** Authored institutional compliance documentation governing Data Protection and GDPR-aligned retention/forgetting policies (`docs/architecture/memory_design_and_data_handling.md`).
5. **Model Context Protocol (MCP) Contract:** Standardized institutional timetable retrieval as an isolated MCP-compliant server contract (`docs/interfaces/mcp_timetable_server.md`).
6. **Multi-Session Verification & Reporting:** Produced auditable multi-session execution traces confirming memory usage without safety bypasses (`docs/traces/memory_demo_trace.jsonl`).

---

## 2. Team Contributions & Ownership Matrix

---

| Team Member                | Engineering Role                       | Key Week 6 Deliverables & Ownership                                                                                                                                                                                                                                             |
| :------------------------- | :------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Baingana Abisha**        | State Modeling & Orchestrator Lead     | Formalized typed FSM state representations and immutable snapshots (`src/agent/state.py`, `docs/architecture/state_model.md`), refactored the orchestrator loop for deterministic lifecycle transitions (`src/agent/orchestrator.py`), and compiled the Week 6 progress report. |
| **Mbasani Pauline Peace**  | Persistent Memory & Storage Lead       | Implemented the justified persistent cross-session student case memory layer (`src/agent/persistent_memory.py`), ensuring advisory-only profile retention without authorization bypass, and validated storage integrity via unit tests (`tests/agent/test_memory.py`).          |
| **Tusiime Mable**          | Data Governance & Compliance Lead      | Authored the institutional compliance document (`docs/architecture/memory_design_and_data_handling.md`), establishing RBAC data access controls, retention schedules, and GDPR/Data Protection Right-to-be-Forgotten mechanisms.                                                |
| **Bantrobusa Kazibwe FZ**  | Tool Interoperability & Protocols Lead | Standardized the course timetable query capability into a formal Model Context Protocol (MCP) server contract (`docs/interfaces/mcp_timetable_server.md`), establishing JSON-RPC schemas, parameter regex validation, and read-only boundaries.                                 |
| **Tendo Jemimah Nakayiwa** | QA & Multi-Session Verification Lead   | Executed and documented verifiable multi-session execution traces demonstrating cross-session profile continuity and injection refusal (`docs/traces/memory_demo_trace.jsonl`).                                                                                                 |

---

## 3. Next Steps (Week 7 Plans)

1. **Comprehensive Evaluation Suite (30+ Scenarios):** Curate and automate a benchmark dataset covering 6 core scenario distributions. Define measurable quantitative rubrics e.g., Task Completion Rate, Groundedness, Tool Selection Precision, etc.,
2. **Full-Stack Observability & Tracing:** Extend telemetry instrumentation to capture end-to-end spans, prompt template hashes, retriever citations, tool latency breakdowns, token consumption, and state transition snapshots.
3. **Multi-Layer Guardrail Hardening:** Enforce deterministic input and output validators before and after LLM synthesis.
4. **Failure Catalogue & Remediation:** Document at least 5 empirical failure modes (root cause, failure trace, remediation patch, and automated regression test).
