# WEEK 4 PROGRESS REPORT: Tools, Bounded Function Calling & Orchestration

**Course:** BSE4104 Emerging Trends In Software Engineering – Capstone Project
**Project:** AI-Native University Student Support Case Agent
**Delivery Timeline:** 21st September, 2026 – 25th September, 2026
**Primary Focus:** Safe Tool Execution, Bounded Function Calling, Failure Handling & Session State
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

During Week 4, the engineering focus progressed beyond open-ended generative answers to safe, bounded software capabilities via explicit tool invocation. The core deliverables achieved include:

- **Tool Catalogue & Schemas (`/src/schemas/tool_definitions.json`):** Strict JSON Schema specifications defining parameter types, mandatory fields, and return models.
- **Deterministic Tool Implementations:** Deployed `timetable_tool.py` for read-only course schedule lookups and `ticket_tool.py` for simulated administrative case creation.
- **Bounded ReAct Orchestrator (`/src/agent/orchestrator.py`):** Multi-step control loop running Sense $\rightarrow$ Plan $\rightarrow$ Act $\rightarrow$ Observe bounded by a strict 3-iteration cap.
- **Updated System Architecture Diagram (`/docs/architecture/system_architecture.png`):** Multi-tier blueprint capturing the Iteration-0 safety guardrail, sliding memory, tool execution, and telemetry sinks.
- **Failure & Authorization Suite (`/tests/agent/test_orchestrator.py`):** Verified sub-10ms rejection paths for prohibited intents and graceful recovery from missing tool parameters.

---

### 2. Team Contributions & Ownership Matrix

| Team Member                | Engineering Role                        | Key Week 4 Deliverables & Ownership                                                                                                                                                                                        |
| :------------------------- | :-------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Baingana Abisha**        | Backend Core & System Architecture Lead | Engineered`SupportAgentOrchestrator` (`orchestrator.py`), designed the updated system architecture diagram (`system_architecture.png`), enforced `.gitignore` data layer hygiene, and authored the Week 4 progress report. |
| **Mbasani Pauline Peace**  | AI Engineering & Retrieval Lead         | Authored strict tool schemas (`tool_definitions.json`), RAG retriever grounding bridges, and the 6-turn sliding memory manager (`memory.py`).                                                                              |
| **Bantrobusa Kazibwe FZ**  | Tool Integration & Infrastructure       | Built 6-parameter validation handlers for`ticket_tool.py` and schedule lookups in `timetable_tool.py`.                                                                                                                     |
| **Tendo Jemimah Nakayiwa** | Quality Assurance & E2E Testing         | Executed verification suites for missing tool parameters, enum schema violations, and grade-tampering refusals (`test_orchestrator.py`).                                                                                   |
| **Tusiime Mable**          | DevOps & Infrastructure Lead            | Built runtime telemetry logging (`/src/utils/telemetry.py`) tracking decoupled model vs. tool latencies, per-turn token burn rates, and context overflow risks.                                                            |

---

### 3. Technical Governance & Failure Handling

- **Deterministic Fast-Fail Guardrails:** Intercepts prohibited actions (grade or fee changes) at Iteration 0 in $<10\text{ms}$ with zero token leakage prior to model invocation.
- **Side-Effect Confirmation Gates:** Writing to the case repository (`tickets.json`) requires explicit verification (`student_confirmed: bool`). Missing arguments return structured error dictionaries to the orchestrator rather than crashing.
- **Memory & Telemetry Guardrails:** A 6-turn FIFO sliding window evicts older dialogue into an 18-word deterministic rolling summary without speculative LLM calls. Telemetry tracks token saturation against the 1M ceiling, warning at $\ge 80\%$.

---

### 4. Next Steps (Week 5 Plans)

1. Author the **Agent Task Contract** defining input requirements, state representation, iteration limits, and human escalation conditions.
2. Implement goal-directed multi-step re-planning (`Sense -> Plan -> Act -> Observe -> Stop/Re-plan`).
3. Capture three empirical execution traces (successful workflow, tool error recovery, and human hand-off stop condition).
