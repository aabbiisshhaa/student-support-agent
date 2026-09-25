# WEEK 4 PROGRESS REPORT: Stateful Conversational Memory & Agent Orchestration

**Course:** BSE4104 Emerging Trends in Software Engineering – Capstone Project  
**Project:** AI-Native University Student Support Case Agent  
**Delivery Timeline:** 21st September, 2026 – 25th September, 2026  
**Group Name:** Group C Day

---

## Team Members

| S/N | Name                   | Student Number | Registration Number |
| :-: | :--------------------- | :------------: | :-----------------: |
|  1  | Bantrobusa Kazibwe FZ  |   2300707416   |   23/U/07416/EVE    |
|  2  | Baingana Abisha        |   2300707328   |    23/U/07328/PS    |
|  3  | Mbasani Pauline Peace  |   2300700765   |      23/U/0765      |
|  4  | Tendo Jemimah Nakayiwa |   2300717920   |    23/U/17920/PS    |
|  5  | Tusiime Mable          |   2300701494   |      23/U/1494      |

---

### 1. Overview

During Week 4, the team advanced the Student Support Case Agent from isolated tools and retrieval functions into a unified, autonomous, multi-step orchestrator driven by the Sense $\rightarrow$ Plan $\rightarrow$ Act $\rightarrow$ Observe $\rightarrow$ Revise control loop. We integrated live model generation with `gemini-3.5-flash-lite`, deployed a deterministic sliding-window session memory manager with rolling summaries and GDPR deletion routines, instrumented real-time execution telemetry and token usage tracking, and enforced deterministic iteration-0 safety refusals against unauthorized administrative actions.

---

### 2. Deliverables Completed

| Deliverable                               | GitHub Artifact Location            | Evidence Category | AI Safety Impact        | Status   |
| :---------------------------------------- | :---------------------------------- | :---------------- | :---------------------- | :------- |
| **Multi-Step Agent Orchestrator**         | `/src/agent/orchestrator.py`        | Working Code      | AI Assisted             | Complete |
| **Stateful Memory & GDPR Persistence**    | `/src/agent/memory.py`              | Working Code      | Deterministic Code      | Complete |
| **Execution Telemetry & Token Tracker**   | `/src/telemetry/tracker.py`         | Working Code      | Deterministic Code      | Complete |
| **Deterministic Hard Guardrail Refusals** | `/src/agent/orchestrator.py`        | Working Code      | Deterministic Code      | Complete |
| **Multi-Turn Integration Test Suite**     | `/tests/agent/test_orchestrator.py` | Test Suite        | Human Approval Required | Complete |

---

### 3. Individual Contributions & Role Alignment

- **AI Engineering Lead:** Integrated `GeminiModel` (`gemini-3.5-flash-lite`) into the orchestrator loop, built honest RAG error handling removing synthetic mocks, and standardized grounded response synthesis with bracketed citations.
- **Application / Integration Lead:** Built the `TelemetryTracker` (`/src/telemetry/tracker.py`) module, instrumenting per-turn model vs. tool latencies, token consumption counters, and context-window threshold monitoring.
- **DevOps / Documentation Lead:** Standardized parameter signatures across tool dispatches (specifically enforcing 6-parameter lowercase enum schemas on `/src/tools/ticket_tool.py`), maintaining Git hygiene by ignoring session and telemetry runtime logs.
- **Quality / Security Lead:** Engineered deterministic sliding-window FIFO memory pruning and rolling summary folding (`/src/agent/memory.py`), adding GDPR session purges and active session registry tracking (`_active_sessions.json`).
- **Project / Requirements Lead:** Coordinated ClickUp sprint board deliverables, conducted safety boundary audits to guarantee sub-10ms iteration-0 refusals for academic grade modifications, and compiled the Week 4 progress documentation.

---

### 4. Key Engineering Decisions & Evaluation

- **Autonomous ReAct Control Loop:** Configured an iterative execution loop capped at `max_iterations = 3`. This enforces deterministic termination and prevents runaway token billing or unbounded multi-step execution cycles.
- **Deterministic Memory Pruning vs. LLM Summarization:** Conversation context retention is strictly bounded by a FIFO sliding window (`window_size = 6`). Evicted turns are folded into a rule-based rolling summary using deterministic string extraction (first sentence or 18 words) without making speculative LLM calls, guaranteeing repeatable prompt assembly.
- **Data Protection & Compliance:** Integrated `delete_session()` for immediate hard-purging of student conversation records from disk and memory, complemented by `cleanup_expired_sessions()` enforcing a 30-day institutional time-to-live (TTL) limit.
- **Runtime Observability:** Every turn logs an append-only entry to `data/telemetry/agent_telemetry.jsonl`. Monitored token utilization against the 1,000,000 token context window ceiling, automatically flagging an `overflow_warning` whenever memory utilization exceeds 80%.

---

### 5. Challenges & Mitigation Strategies

- **Challenge:** The orchestrator crashed with a `KeyError: 'created_at'` when reading persisted legacy sessions saved under older, differing dictionary schemas.
  - _Mitigation:_ Implemented defensive deserialization within `SessionState.from_dict` and `Message.from_dict`, safely falling back to metadata sub-dictionaries, auto-assigning turn indexes, and supplying ISO-8601 timestamps.
- **Challenge:** Support ticket creation failed dynamically during integration testing due to casing and parameter mismatches between orchestrator dispatches and the strict tool schema.
  - _Mitigation:_ Hardened the orchestrator planning layer to strictly pass all 6 expected parameters (`student_id`, `summary`, `original_message`, `category`, `priority`, `student_confirmed`) using validated lowercase enum constraints.
- **Challenge:** Branch merge conflict between independent memory implementations (`SessionMemoryManager` with active registries vs. `ConversationMemory` orchestrator calls).
  - _Mitigation:_ Unified both into `src/agent/memory.py` by adding compatibility bridges (`initialize_session`, `get_recent_history`) and GDPR purge methods directly onto the core sliding-window class, preserving both teammates' contributions.

---

### 6. Next Steps (Week 5 Plans)

1. Package the agent orchestrator behind a production FastAPI asynchronous backend service.
2. Develop front-end case management UI views for student ticket escalation workflows.
3. Conduct adversarial red-teaming evaluations on prompt injection and prompt leak vulnerabilities.
