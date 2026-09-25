# WEEK 3 PROGRESS REPORT: Grounding with RAG & Deterministic Tool Execution

**Course:** BSE4104 Emerging Trends in Software Engineering – Capstone Project
**Project:** AI-Native University Student Support Case Agent
**Delivery Timeline:** 14th September, 2026 – 18th September, 2026
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

During Week 3, the team transitioned the Student Support Case Agent from standalone prompting to an architecture grounded in Retrieval-Augmented Generation (RAG) and deterministic tool execution. We implemented a document ingestion and chunking pipeline using our Week 1 Knowledge Corpus Register, deployed a vector retrieval module with strict source attribution, defined bounded JSON function-calling schemas, and integrated deterministic handlers for timetable queries and student support ticket logging.

---

### 2. Deliverables Completed

| Deliverable                              | GitHub Artifact Location                                    | Evidence Category | AI Safety Impact        | Status   |
| :--------------------------------------- | :---------------------------------------------------------- | :---------------- | :---------------------- | :------- |
| **Corpus Ingestion & Chunking Pipeline** | `/src/rag/ingest.py`                                        | Working Code      | Deterministic Code      | Complete |
| **Vector Store & Semantic Retriever**    | `/src/rag/retriever.py`                                     | Working Code      | AI Assisted             | Complete |
| **Bounded Tool API Schemas**             | `/src/schemas/tool_definitions.json`                        | API / Schemas     | Deterministic Code      | Complete |
| **Deterministic Tool Handlers**          | `/src/tools/timetable_tool.py`, `/src/tools/ticket_tool.py` | Working Code      | Deterministic Code      | Complete |
| **RAG Grounding & Retrieval Test Suite** | `/tests/rag/test_retrieval.md`                              | Test Suite        | Human Approval Required | Complete |
| **Week 3 Progress Report**               | `/docs/weekly-reports/week-3.md`                            | Documentation     | Deterministic Code      | Complete |

---

### 3. Individual Contributions & Role Alignment

- **AI Engineering Lead:** Developed the text ingestion and recursive chunking pipeline (`/src/rag/ingest.py`) and implemented top-$k$ semantic retrieval with similarity scoring (`/src/rag/retriever.py`).
- **Application / Integration Lead:** Built deterministic execution handlers (`/src/tools/timetable_tool.py` and `ticket_tool.py`) to resolve model tool calls against mock datasets without probabilistic side effects.
- **DevOps / Documentation Lead:** Authored strictly typed JSON function-calling schemas (`/src/schemas/tool_definitions.json`) and maintained CI testing workflows.
- **Quality / Security Lead:** Formulated and executed the 10-query RAG grounding evaluation suite (`/tests/rag/test_retrieval.md`), auditing source attribution accuracy and out-of-domain refusals.
- **Project / Requirements Lead:** Supervised ClickUp deliverable tracking, maintained governance tags across GitHub branches, and compiled the Week 3 documentation.

---

### 4. Key Engineering Decisions & Evaluation

- **Chunking Strategy:** Implemented recursive character splitting with a chunk size of 500 characters and 50-character overlap, attaching strict metadata tags (`source_document`, `section`, `last_updated`) to eliminate lost context across policy boundaries.
- **Bounded Function Calling:** Tools are strictly constrained to parameter-validated read/write operations. The agent cannot write arbitrary SQL or execute unbounded database mutations; ticket creation is limited to the defined schema.
- **Retrieval Evaluation:** Evaluated across 10 distinct student inquiries; answers achieved 100% citation compliance (`[Source: Document, Section]`), and policy queries with no vector match cleanly triggered the required human-escalation fallback.

---

### 5. Challenges & Mitigation Strategies

- **Challenge:** Chunk boundary fragmentation caused multi-clause academic policies (e.g., retake criteria) to be split across chunks.
  - _Mitigation:_ Switched to header-aware Markdown chunking so entire policy sub-sections remain intact inside single retrieval documents.
- **Challenge:** LLM hallucinating arguments for tool calls when optional parameters were omitted in user queries.
  - _Mitigation:_ Enforced strict `required` parameter lists inside `/src/schemas/tool_definitions.json` and added deterministic fallback checks in the tool handlers.

---

### 6. Next Steps (Week 4 Plans)

1. Implement multi-turn conversational memory and session state management.
2. Build end-to-end integration tests orchestrating RAG retrieval, tool execution, and boundary refusal workflows.
