# WEEK 4 PROGRESS REPORT: Stateful Conversational Memory & Multi-Step Agent Orchestration

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

### 1. Overview & Core Deliverables

Week 4 advanced the case agent into a stateful, autonomous multi-step orchestrator running a bounded **Sense $\rightarrow$ Plan $\rightarrow$ Act $\rightarrow$ Observe $\rightarrow$ Revise** loop. Core achievements include:

- **Sliding-Window Memory (`/src/agent/memory.py`):** Bounded FIFO retention (`window_size=6`), deterministic rolling summarization without LLM cost, active session registry (`_active_sessions.json`), and GDPR hard-purge/TTL deletion.
- **Bounded ReAct Orchestrator (`/src/agent/orchestrator.py`):** Capped at 3 iterations to prevent runaway execution; enforces deterministic Iteration-0 safety refusals for grade/fee changes.
- **Model Synthesis & Live RAG:** Integrated `gemini-3.5-flash-lite` for citation-grounded answers; honest retrieval failure handling without synthetic mocks.
- **Runtime Telemetry (`/src/telemetry/tracker.py`):** Structured JSONL logging capturing token counts, context window percentage (>80% warning threshold), and decoupled model vs. tool latencies.

---

### 2. Team Contributions & Ownership Matrix

| Team Member | Engineering Role | Key Deliverables & Ownership |
| :--- | :--- | :--- |
| **Baingana Abisha** | Backend Core & Agent Architecture | Implemented `SupportAgentOrchestrator`, runtime execution telemetry (`tracker.py`), and memory compatibility bridges. |
| **Mbasani Pauline Peace** | AI Engineering & Retrieval Lead | Designed `SessionMemoryManager` with sliding-window FIFO eviction and maintained RAG grounding pipelines. |
| **Bantrobusa Kazibwe FZ** | Tool Integration & Infrastructure | Validated 6-parameter schema compliance for `ticket_tool.py` and schedule lookups (`timetable_tool.py`). |
| **Tendo Jemimah Nakayiwa** | Quality Assurance & E2E Testing | Executed verification suites for multi-turn retention, FIFO summary pruning, and grade-change guardrails. |
| **Tusiime Mable** | System Documentation & Governance | Enforced data layer git hygiene (`.gitignore`), telemetry audit rules, and compiled Week 4 reporting. |

---

### 3. Key Decisions & Architectural Governance

- **Deterministic Memory Pruning:** A fixed 6-turn sliding window evicts older turns into an 18-word rolling summary deterministically without speculative LLM calls, eliminating prompt inflation.
- **Safety Boundary Refusals:** Deterministic checks intercept administrative overrides (e.g., grade edits) in sub-10ms with 0 token leakage before LLM planning.
- **GDPR & Storage Hygiene:** Built-in `delete_session()` and 30-day TTL purges protect student privacy; session files and JSONL telemetry logs are excluded from git.
- **Resource Containment:** Strict 3-iteration loop ceiling and token utilization monitoring prevent denial-of-wallet and infinite looping states.

---

### 4. Challenges & Mitigation Strategies

- **Schema Deserialization Failure:** Legacy transcripts threw `KeyError: 'created_at'`.  
  *Mitigation:* Added defensive `.get()` fallbacks and automatic index assignment inside `SessionState.from_dict` and `Message.from_dict`.
- **Ticket Parameter Mismatch:** Orchestrator calls failed against strict `ticket_tool.py` definitions.  
  *Mitigation:* Hardened planner to supply all 6 expected parameters with lowercase enum validation.
- **Branch Merge Conflicts:** Divergent memory implementations collided in `memory.py`.  
  *Mitigation:* Unified implementations into `SessionMemoryManager` with backward-compatible bridge methods.

---

### 5. Next Steps (Week 5 Plans)

1. Wrap the agent orchestrator inside a production asynchronous FastAPI service.
2. Build front-end UI views for ticket review and interaction history.
3. Conduct adversarial red-teaming evaluations (prompt injections and jailbreak tests).
