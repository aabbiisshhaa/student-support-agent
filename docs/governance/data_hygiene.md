# Data Layer Hygiene & Version Control Governance

**System:** AI-Native University Student Support Case Agent  
**Module:** Data Hygiene, Privacy & Repository Governance  
**Course:** BSE4104 Emerging Trends in Software Engineering

---

## 1. Overview & Policy Objective

This document formalizes the repository governance and data hygiene standards enforced across development and deployment environments. Because the Student Support Case Agent processes student identifiers, academic inquiries, conversation transcripts, and runtime telemetry, strict controls are mandated to prevent data leakage into version control.

---

## 2. Directory Classification & Tracking Rules

| Directory / Path       | Classification                   | Git Status              | Retention & Compliance Rationale                                                                                           |
| :--------------------- | :------------------------------- | :---------------------- | :------------------------------------------------------------------------------------------------------------------------- |
| `data/knowledge_base/` | Static Public / Policy Documents | **Tracked**             | Official university policies, handbook markdown files, and course guidelines.                                              |
| `data/mock/`           | Static Mock Seed Data            | **Tracked**             | Mock course timetables and baseline student lookup seeds (no PII).                                                         |
| `data/sessions/`       | Dynamic Ephemeral State          | **Untracked / Ignored** | Active student dialogue transcripts, turn indices, and session JSON files. Ignored under GDPR/institutional privacy rules. |
| `data/telemetry/`      | Append-Only Runtime Logs         | **Untracked / Ignored** | Per-turn latency figures, token burn metrics, and raw JSONL records (`agent_telemetry.jsonl`).                             |
| `data/vector_store/`   | Derived Binary Embeddings        | **Untracked / Ignored** | Generated `.joblib` / index caches. Generated reproducibly via `src/rag/ingest.py`.                                        |

---

## 3. Git Hygiene Configuration (`.gitignore`)

The following rules are actively enforced at the root `.gitignore`:

```gitignore
# Runtime Session Transcripts (GDPR Compliance)
data/sessions/*.json
!data/sessions/.gitkeep

# Runtime Telemetry & Observability Logs
data/telemetry/*.jsonl
!data/telemetry/.gitkeep

# Derived Vector Store Artifacts
data/vector_store/*.joblib
data/vector_store/*.index

# Environment Secrets & Local Config
.env
.env.local
*.env

# Python Caches & Build Artifacts
__pycache__/
*.py[cod]
*$py.class
.pytest_cache/
.coverage
htmlcov/
.venv/
env/
```
