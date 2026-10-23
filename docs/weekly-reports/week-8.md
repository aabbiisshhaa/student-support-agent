# WEEK 8 PROGRESS REPORT: Hardening, Final Release and Demonstration

**Course:** BSE4104 Emerging Trends In Software Engineering – Capstone Project
**Project:** AI-Native University Student Support Case Agent
**Delivery Timeline:** 19th October, 2026 – 23rd October, 2026
**Primary Focus:** Hardening, Final Release Packaging, and Final Demonstration
**Group Name:** Group C Day

## Group Members

| S/N | Name                   | Student Number | Registration Number |
| :-: | :--------------------- | :------------: | :-----------------: |
| 1.  | Bantrobusa Kazibwe FZ  |   2300707416   |   23/U/07416/EVE    |
| 2.  | Baingana Abisha        |   2300707328   |    23/U/07328/PS    |
| 3.  | Mbasani Pauline Peace  |   2300700765   |      23/U/0765      |
| 4.  | Tendo Jemimah Nakayiwa |   2300717920   |    23/U/17920/PS    |
| 5.  | Tusiime Mable          |   2300701494   |      23/U/1494      |

---

## 1. Individual Contribution Summary Against Weekly Objectives

| Task Owned & Role                                                          | Assignee                   | Concrete Technical Output & Evidence                                                                                                                                                                                                                  |
| :------------------------------------------------------------------------- | :------------------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Final Tagged Release (`v1.0.0`) & Packaging** (DevOps & Deployment Lead) | Tusiime Mable              | Authored multi-stage `Dockerfile` and `docker-compose.yml`; pinned production dependencies in `requirements.txt`; tagged official Git release `v1.0.0` with deployment runbook (`/Dockerfile`, `/docker-compose.yml`, `/docs/deployment/runbook.md`). |
| **Defect Remediation & Limitations** (AI Engineering Lead)                 | Mbasani Pauline Peace      | Resolved cold-start network latency and session state re-runs; audited architectural boundaries; catalogued remaining constraints in `/docs/architecture/limitations.md`.                                                                             |
| **Final Evaluation & Evidence Pack** (QA & Evaluation Lead)                | Tendo Jemimah Nakayiwa     | Executed benchmark suite across all 6 scenario categories against `v1.0.0`, consolidated automated scoring: 100% Task Completion, 0% Safety Violations, and verified citation grounding (`/docs/eval/final_evidence_pack.md`).                        |
| **UI Polish, Demo Script & Deck** (Application / Integration Lead)         | Bantrobusa Kazibwe Francis | Added sidebar inspection toggle to `src/ui/app.py` for seamless demo and portal switching; prepared live demonstration script and slide deck (`/docs/presentation/demo_script.md`, `/docs/presentation/capstone_deck.pdf`).                           |
| **Final Capstone Report & Coordination** (Project Lead / Architecture)     | Baingana Abisha            | Drafted the comprehensive 8–12 page Final Engineering Report synthesizing Weeks 1–8 architecture, guardrails, telemetry, and empirical outcomes (`/docs/reports/final_engineering_report.md`).                                                        |

---

## 2. Key Engineering Decisions & Rationale

1. **Dual-Mode UI Toggle (Portal View vs. Inspector View):**
   - _Decision:_ Implemented a sidebar toggle switch in `src/ui/app.py` allowing instant switching between a clean, student-facing portal layout and the split-screen real-time inspector.
   - _Rationale:_ Provides an uncluttered student experience during regular use while enabling evaluators to inspect FSM badges, telemetry, and guardrail interrupts side-by-side during demonstrations.

2. **Decoupled Prompt Queue for UI Reruns:**
   - _Decision:_ Migrated scenario button execution from nested inline callbacks to an asynchronous session state queue (`pending_prompt`).
   - _Rationale:_ Eliminates Streamlit WebSocket deadlocks, preventing spinner freezes during multi-step model planning cycles.

3. **Pinned Containerized Release (`v1.0.0`):**
   - _Decision:_ Bundled both the CLI entry point (`src/app.py`) and Streamlit web interface (`src/ui/app.py`) into a single container image with verified mock databases and frozen dependencies.
   - _Rationale:_ Guarantees 100% deterministic reproducibility across host evaluation machines without host Python dependency conflicts.

---

## 3. Failures, Challenges & Current Responses

1. **Remote API Latency & AFC Connection Cold Starts:**
   - _Root Cause:_ First-turn API calls over WAN incurred high socket handshake latency (~55 seconds) during automatic function calling negotiation.
   - _Response:_ Implemented client session reuse and cached tool definitions in `SupportAgentOrchestrator` to maintain keep-alive TCP connections across conversational turns.

2. **Streamlit Component Import Resolution:**
   - _Root Cause:_ Module resolution failed when launching `src/ui/app.py` directly from subdirectories due to path scoping.
   - _Response:_ Standardized root path injection (`sys.path.insert(0, str(PROJECT_ROOT))`) across all UI entry points.
