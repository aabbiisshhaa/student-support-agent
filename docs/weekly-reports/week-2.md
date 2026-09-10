# WEEK 2 PROGRESS REPORT: Foundation-Model Engineering & Prompting

**Course:** BSE4104 Emerging Trends in Software Engineering – Capstone Project
**Project:** AI-Native University Student Support Case Agent
**Delivery Timeline:** 7th September, 2026 – 11th September, 2026
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

During Week 2, our team established a tested baseline model interaction loop prior to introducing RAG or autonomous tool execution. We selected and evaluated our foundation model, integrated the model API into our application infrastructure, authored Prompt Specification v1.0 and v2.0 with versioned history, and executed a 10-case evaluation matrix to verify prompt behavior and refusal guardrails.

---

### 2. Deliverables Completed

| Deliverable                          | GitHub Artifact Location                                       | Evidence Category | AI Safety Impact        | Status   |
| :----------------------------------- | :------------------------------------------------------------- | :---------------- | :---------------------- | :------- |
| **Model API Setup & SDK Wrapper**    | `/src/baseline_model.py`                                       | Working Code      | Deterministic Code      | Complete |
| **Model Selection Note**             | `docs/architecture/model-selection-note.md`                    | Documentation     | Deterministic Code      | Complete |
| **Prompt Specification v1.0 & v2.0** | `/prompts/v1/system-prompt.md`, `/prompts/v2/system-prompt.md` | Prompts / Config  | AI Assisted             | Complete |
| **App Workflow & Refusal Logic**     | `/src/app.py`, `/src/utils/parser.py`                          | Working Code      | AI Assisted             | Complete |
| **10-Case Prompt Evaluation Table**  | `tests/prompts/evaluation-table.md`                            | Test Suite        | Human Approval Required | Complete |
| **Week 2 Progress Report**           | `docs/weekly-reports/week-2.md`                                | Documentation     | Deterministic Code      | Complete |

---

### 3. Individual Contributions & Role Alignment

- **DevOps / Documentation Lead:** Configured API credentials, built the core model client (`/src/baseline_model.py`), and established environment variable management.
- **AI Engineering Lead:** Authored the Model Selection Note, created System Prompt Specification v1.0, and iterated to v2.0 based on initial failure modes.
- **Application / Integration Lead:** Connected the model wrapper into `/src/app.py` and implemented deterministic parser logic (`/src/utils/parser.py`) for handling responses and refusal codes.
- **Quality / Security Lead:** Built and executed the 10-case prompt evaluation suite (`tests/prompts/evaluation-table.md`), verifying boundary refusals for high-risk queries.
- **Project / Requirements Lead:** Managed ClickUp task tracking, maintained deliverable traceability tags, and compiled the Week 2 progress documentation.

---

### 4. Key Engineering Decisions & Evaluation

- **Model Selection:** Selected Google Gemini 1.5 Flash for its low latency, high context window, cost effectiveness, and strong instruction-following capabilities.
- **Prompt Versioning (`v1` → `v2`):** Prompt v1 yielded unstructured output for edge cases; v2 introduced strict markdown output rules and explicit refusal templates for out-of-scope requests.
- **Boundary Guardrails:** Verified via 10 evaluation test cases that queries regarding grade changes, fee waivers, or disciplinary appeals trigger hard-coded non-autonomous refusal responses.

---

### 5. Challenges & Mitigation Strategies

- **Challenge:** Inconsistent output formatting when the model handled ambiguous student inquiries.
  - _Mitigation:_ Added structured JSON output schemas and explicit fallback parsing logic inside `/src/utils/parser.py`.
- **Challenge:** Preventing hallucinated policy claims during plain-prompt testing.
  - _Mitigation:_ Tightened prompt constraints in v2 to state explicitly: "If exact information is not in the system context, reply that human escalation is required."

---

### 6. Next Steps (Week 3 Plans)

1. Initialize vector store ingestion and chunking pipelines for official university handbooks (RAG implementation).
2. Implement bounded function-calling schemas for live timetable lookups and ticket generation.
