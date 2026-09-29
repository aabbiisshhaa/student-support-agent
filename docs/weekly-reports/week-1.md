# Week 1 Progress Report: Project Setup & Baseline Scaffolding

**Course:** BSE4104 Emerging Trends in Software Engineering  
**Project:** AI-Native University Student-Support Case Agent  
**Period:** Week 1 (31st August 2026 – 6th September 2026)  
**Repository Location:** `docs/weekly-reports/week-1.md`  

---

## 1. Executive Summary

During Week 1, our team initialized the foundational repository infrastructure, project management tracking, and baseline governance artifacts for the AI-Native University Student-Support Case Agent. We established a course-compliant GitHub repository structure, configured an 8-week ClickUp workspace, defined team roles, and drafted core requirements deliverables (Project Charter, AI Boundary Matrix, User Stories, Knowledge Corpus Register, and Initial System Architecture Diagram).

---

## 2. Deliverables Completed

| Deliverable | Repository / Artifact Location | Evidence Category | AI Safety Impact | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Repository Scaffolding** | Root structure (`/docs`, `/src`, `/prompts`, `/knowledge`, `/tests`, `/evidence`) | Documentation | Deterministic Code | Complete |
| **Base README.md** | `README.md` | Documentation | Deterministic Code | Complete |
| **ClickUp Workspace Setup** | 8 Weekly Folders & Task Tracking | Documentation | Deterministic Code | Complete |
| **Project Charter** | `docs/requirements/project-charter.md` | Documentation | Deterministic Code | Complete |
| **AI Boundary Matrix** | `docs/requirements/ai-boundary-matrix.md` | Documentation | Deterministic Code | Complete |
| **User Stories & Criteria** | `docs/requirements/user-stories.md` | Documentation | Deterministic Code | Complete |
| **Knowledge Corpus Register** | `knowledge/knowledge-corpus-register.csv` | RAG Corpus | Deterministic Code | Complete |
| **System Architecture Diagram** | `docs/architecture/Initial architecture diagram.drawio.png` | Documentation | Deterministic Code | Complete |

---

## 3. Individual Contributions & Role Alignment

* **Project / Requirements Lead:** Authored the Project Charter, problem context statement, and core system scope boundaries.
* **Application / Integration Lead:** Defined functional user stories covering timetable lookups, case tracking, and support ticket workflows.
* **AI Engineering Lead:** Structured RAG lookup user stories and defined the machine-readable knowledge corpus register schema (`.csv`).
* **Quality / Security Lead:** Authored the AI Boundary Matrix, establishing explicit non-negotiable safety guardrails (zero autonomous grade, fee, or disciplinary actions).
* **DevOps / Documentation Lead:** Configured the GitHub repository tree, branch workflows, architecture diagram rendering, and compiled weekly progress documentation.

---

## 4. Key Decisions & Governance

1. **RAG Grounding Policy:** All policy queries require source citations from ingested handbooks; ungrounded generation is prohibited.
2. **Deterministic Control:** Timetable queries, ticket ID generation, authentication, and permission checks run exclusively via rule-based code.
3. **Safety Boundaries:** Out-of-scope actions (grades, admissions, discipline) trigger hard-coded refusals before LLM processing.
4. **Git & Evidence Tracking:** Deliverables are version-controlled via feature branches and merged into `main` via Pull Requests.

---

## 5. Challenges & Mitigation Strategies

* **Challenge:** Ensuring full alignment between high-level project goals and course evaluation criteria.  
  * *Mitigation:* Documented explicit evidence tags (Artifact Link, AI Safety Impact, Evidence Category) across task descriptions and progress reports.
* **Challenge:** Differentiating AI reasoning from deterministic logic.  
  * *Mitigation:* Created the AI Boundary Matrix early to clearly delineate autonomous AI capabilities, rule-based execution, and human approval gates.

---

## 6. Next Steps (Week 2 Plans)

* Initialize prompt template conventions and versioned store (`/prompts/v1/`).
* Build mock datasets for timetable services and synthetic ticket logs inside `/knowledge`.
* Define API schemas for tool execution (timetable lookups and ticket routing).
