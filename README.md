# BSE4104: AI-Native University Student-Support Case Agent

An AI-native, bounded agentic system designed to assist university students with academic policies, course inquiries, timetable lookups, and administrative case routing. Built for **BSE4104 Emerging Trends in Software Engineering** at Makerere University (Academic Year 2026/2027).

---

## 📌 Project Overview

- **Target User:** University undergraduate students and administrative support staff.
- **Primary Workflow:** Students submit inquiries regarding academic handbooks, timetables, or administrative procedures. The system provides grounded answers using Retrieval-Augmented Generation (RAG), queries live timetable status, or routes complex inquiries by creating support tickets.

---

## 🎯 Bounded Scope & Safety Boundaries

To maintain software engineering integrity, AI autonomy is strictly bounded:

- **AI Responsibilities:** Policy retrieval, intent classification, multi-step inquiry reasoning, and support ticket drafting.
- **Deterministic Responsibilities:** Timetable queries, database validation, unique ID generation, and permission controls.
- **Explicit Hard Limits:** The agent **cannot** alter grades, make admissions/fee clearance decisions, or perform disciplinary actions.

---

## 🛠 Project Structure

```text
├── .env.example              # Template for environment variables
├── README.md                 # Project description and quickstart
├── docs/
│   ├── requirements/         # Project Charter, User Stories, AI Boundary Matrix
│   ├── architecture/         # System diagrams and workflows
│   └── weekly-reports/       # Weekly 1-2 page status reports
├── prompts/                  # Versioned prompt templates
├── knowledge/                # Provenance register and public handbook metadata
├── src/                      # Source code (API, RAG pipeline, Agent tools)
├── tests/                    # Unit, integration, and evaluation suites
└── evidence/
    ├── evaluation/           # 30-scenario test results
    ├── traces/               # Agent execution traces
    └── screenshots/          # System and ClickUp evidence
```

## 👥 Team & Roles

- **Project / Requirements Lead:** Baingana Abisha
  - _Responsibilities:_ Scope definition, Project Charter, user stories, acceptance criteria, and overall project alignment.
- **Application / Integration Lead:** Bantrobusa Kazibwe FZ
  - _Responsibilities:_ Core application orchestration, API routes, user interface integration, and deterministic business logic.
- **AI Engineering Lead:** Mbasani Pauline Peace
  - _Responsibilities:_ Prompt engineering and versioning, RAG pipeline construction, vector indexing, and tool contracts.
- **Quality / Security Lead:** Tendo Jemimah Nakayiwa
  - _Responsibilities:_ AI Boundary Matrix compliance, 30-scenario evaluation suite, failure cataloging, guardrails, and corpus provenance.
- **DevOps / Documentation Lead:** Tusiime Mable
  - _Responsibilities:_ GitHub workflow automation, repository structure, ClickUp workspace tracking, architecture diagrams, and weekly reports.


---

## Quickstart

### Requirements

- Python 3.12
- Docker Desktop with Docker Compose
- A Gemini API key for online mode

### Environment setup

Create the local environment file:

```powershell
Copy-Item .env.example .env
```

Add the Gemini API key to `.env` for online operation. Real credentials must never be committed.

For deterministic offline operation, set:

```text
MODEL_OFFLINE_MODE=true
```

### Run locally

Install the pinned dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Start the CLI:

```powershell
python src\app.py
```

Start the Web UI:

```powershell
streamlit run src\ui\app.py
```

The Web UI is available at `http://localhost:8501`.

### Run with Docker

Build the images:

```powershell
docker compose build
docker compose --profile cli build cli
```

Start the Web UI:

```powershell
docker compose up web
```

Start the interactive CLI:

```powershell
docker compose --profile cli run --rm cli
```

Stop the services:

```powershell
docker compose down
```

For complete environment configuration, offline-mode instructions, port bindings, troubleshooting and release procedures, see [the deployment runbook](docs/deployment/runbook.md).

## Testing

Run the complete test suite before submitting changes:

```powershell
python -m pytest -q
```

## Release

The official release is published from the immutable Git tag `v1.0.0`. The tag must only be created after the deployment pull request has been tested, reviewed and merged into `main`.