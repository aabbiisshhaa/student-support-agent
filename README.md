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
