# Project Charter: AI-Native University Student-Support Case Agent

**Course:** BSE4104 Emerging Trends in Software Engineering  
**Academic Year:** 2026/2027 | Semester I  
**Week 1 Delivery Window:** 31st August 2026 – 7th September 2026 

---

## 1. Problem Context & Target User

### Problem Statement
University students frequently face administrative friction, delayed responses, and conflicting information when navigating course policies, handbooks, timetable changes, and student-support workflows. Academic support offices receive high volumes of repetitive inquiries, leading to delayed issue resolution and operational bottlenecks.

### Target User Persona
* **Primary Users:** Undergraduate university students seeking quick, accurate answers regarding academic regulations, timetables, and support procedures.
* **Secondary Users:** University administrative and support staff who handle escalated student tickets and require structured case context.

---

## 2. Core Workflow & AI Value Justification

### End-to-End Primary Workflow
1. **Inquiry Submission:** A student submits a natural-language query regarding academic policy, timetable availability, or administrative procedures.
2. **Intent Classification & Grounding:** The system classifies the request and retrieves context-grounded passages from official university policy handbooks using Retrieval-Augmented Generation (RAG).
3. **Deterministic Tool Execution:** For status-based or schedule-based queries, the system calls deterministic lookup tools (e.g., timetable database query).
4. **Response Generation or Ticket Routing:** The system returns a grounded, citation-backed answer. If the issue is unresolved or involves an administrative decision, it drafts and routes a structured support ticket to human staff.

### Why AI Is Justified
* **Semantic Understanding:** Students phrase administrative inquiries in varied, informal ways that traditional rule-based search fails to parse effectively.
* **Context Synthesis:** Policy information is scattered across lengthy handbook PDFs; LLM-driven retrieval synthesizes actionable answers while providing explicit source citations.
* **Multi-Step Agent Reasoning:** Bounded agent workflows enable the system to dynamically decide when to retrieve policy information versus when to execute database tool queries or draft support tickets.

---

## 3. Minimum Proposal Statement & System Boundaries

### Proposal Statement
> *"Our system helps **university undergraduate students** complete **academic policy inquiries, timetable lookups, and administrative ticket routing**. AI is used for **retrieving grounded policy context, intent classification, and drafting ticket summaries**. Deterministic software remains responsible for **timetable database queries, unique ticket ID generation, and user role validation**. The agent may use **approved handbook search and ticket creation tools** but may not **make autonomous decisions regarding admissions, grading, fee clearance, or disciplinary actions**. We will build and evaluate the system using **public university handbooks, course outlines, and synthetic student support records**."*

---

## 4. Architectural Boundaries & System Constraints

### What AI MAY Do (Bounded Scope)
* Parse multi-turn student queries and classify intent.
* Retrieve relevant context from approved handbook/policy vector databases.
* Summarize policy rules with direct citations.
* Query deterministic APIs (e.g., timetable search) using explicit schemas.
* Draft structured support tickets for staff review.

### What Stays Deterministic (Software Control)
* Database CRUD operations and unique ID generation.
* Authentication, session management, and authorization checks.
* Schema validation for all tool inputs/outputs.
* Hard iteration limits and execution stop conditions.

### What Requires Human Approval / Prohibited Actions
* **Prohibited:** Grade adjustments, admissions evaluations, fee clearance status changes, or disciplinary decisions.
* **Human Approval Required:** Final ticket resolution closure, administrative policy exceptions, and official student record updates.

---

## 5. Success Criteria & Evaluation Standards

1. **Groundedness:** 100% of policy answers must include source citations from the ingested handbook corpus.
2. **Safety Compliance:** Zero autonomous execution of prohibited administrative actions across all test scenarios.
3. **Reliability:** Successful completion of 30 final evaluation scenarios (covering normal, edge, adversarial, and tool-failure cases).
4. **Observability:** Complete execution traces logged for model calls, prompt versions, retrieval chunks, and tool invocations.