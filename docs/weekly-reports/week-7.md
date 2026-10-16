# WEEK 7 PROGRESS REPORT: Evaluation, Observability, Guardrails & Failure Remediation

**Course:** BSE4104 Emerging Trends In Software Engineering – Capstone Project
**Project:** AI-Native University Student Support Case Agent
**Delivery Timeline:** 12th October, 2026 – 16th October, 2026
**Primary Focus:** Evaluation, Observability, Guardrails & Failure Remediation
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

## 1. Work Completed Against Weekly Objectives

| Task ID & Title                       | Assignee                   | Concrete Output & Artifact                                                                                                                                                                                                                                          |
| :------------------------------------ | :------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **30+ Benchmark Suite & Runner**      | Tendo Jemimah Nakayiwa     | Curated 30+ multi-domain scenarios (normal, edge, adversarial, tool-failure, injection, admin bypass); built automated evaluator scoring groundedness, latency, and 0% safety violations. `/tests/evaluation/eval_dataset_30.json`, `/tests/evaluation/run_eval.py` |
| **Guardrails & Approval Gates**       | Bantrobusa Kazibwe Francis | Built deterministic `GuardrailEngine` enforcing input scanning, strict tool allow-lists, `human_confirmed=True` gates for mutative tools, and output citation sanitization. `/src/agent/guardrails.py`, `/tests/guardrails/test_guardrails.py`                      |
| **Telemetry & Tracing Evidence**      | Tusiime Mable              | Implemented structured execution traces capturing prompt hashes, RAG context, tool payloads, and per-step latencies. Compiled observability guide with UI trace samples. `/src/telemetry/tracker.py`, `/docs/eval/observability_evidence.md`                        |
| **Failure Catalogue & Re-Tests**      | Mbasani Pauline Peace      | Documented empirical failures (FC-01 to FC-13) with root causes, failing traces, and escalation rules. Maintained `xfail` safety-floor regression tests. `/docs/architecture/failure_catalogue.md`, `/tests/evaluation/test_failure_catalogue.py`                   |
| **Orchestrator Integration & Report** | Baingana Abisha            | Integrated `GuardrailEngine` into agent loop: Iteration 0 input halts, pre-auth tool parameter normalization, output citation scrubbing, and telemetry. `/src/agent/orchestrator.py`, `/docs/weekly-reports/week-7.md`                                              |

---

## 2. Key Engineering Decisions & Rationale

1. **Deterministic Gate at Iteration 0 (`AgentStep.STOP`):**Intercept prompt injections and unauthorized administrative actions before invoking the LLM or tool registry. Prevents non-deterministic bypasses and eliminates wasted API latency.
2. **Pre-Authorization Parameter Normalization:**Normalized typed enums (e.g., `TicketPriority.HIGH`) and mixed-case strings to lowercase canonical form in `_dispatch_tool` prior to guardrail checks, preventing false-positive rejections.
3. **Multi-Variant Citation Matching:**Standardized retrieved context citations into raw, bracketed, and prefix-stripped variants (`[1]`, `1`, `source:1`) during synthesis checking to scrub hallucinated claims without redacting valid evidence.
4. **Human-in-the-Loop Confirmation Flags:**
   Required explicit `human_confirmed=True` confirmation on persistent side-effect operations (ticket dispatch, record updates) while permitting automated escalation routing on security stops.

---

## 3. Failures, Challenges & Current Responses

1. **FC-01 (Escalation Contract Casing):**Escalations emitted lowercase reasons (`out_of_scope_administrative_action`), breaking contract assertions._Mitigation:_ Applied `.upper()` normalization to all escalation payloads in `_escalation_payload`.
2. **FC-12 (Over-Refusal False Positives):**Administrative verb patterns (`change` + `grades`) falsely blocked benign inquiries (e.g., _"If I change programme, do my grades transfer?"_)._Mitigation:_ Added `POLICY_SUFFIX` negative lookaheads and an informational intent heuristic in `screen_input` to permit benign questions while blocking active record modifications.
3. **FC-09 (Paraphrased Administrative Overrides):**
   Varied phrasing (`waive`, `expunge`, `approve`, `set status`, `bump`) bypassed initial token windows.
   _Mitigation:_ Expanded `ADMIN_VERBS` and `PROTECTED_OBJECTS` and widened regex separation boundaries in `guardrails.py`.

---

## 6. Plan for Next Week (Week 8)

1. **System Packaging & Final Polish:** Finalize containerization, dependency pinning, and environment configs for deployment.
2. **Close Open Failure Catalogue Items:** Remediate remaining open catalogue edge cases (FC-08 weak retrieval hedging, FC-11 token boundary collisions, FC-13 confirmation state planning).
3. **End-to-End Live Validation:** Run end-to-end acceptance checks with the full web UI and live Gemini endpoints to measure student response latency and reliability.
4. **Submission Deliverables:** Finalize architecture documentation, deployment runbooks, and record the final demonstration video.
