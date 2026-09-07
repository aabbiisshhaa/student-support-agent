# System Architecture Diagram

**System:** AI-Native University Student-Support Case Agent  
**Module:** System Architecture & Data Flow

---

## High-Level System Architecture

![Initial Architecture Diagram](./Initial%20architecture%20diagram.drawio.png)

---

## Layer Breakdown

- **Users Layer:** Primary users (Students submitting queries) and Secondary users (Support staff handling escalated tickets).
- **User Interface Layer:** Dedicated web interfaces for student inquiry submission and staff dashboard management.
- **Application Layer (Deterministic Controls):** Intake handling, input sanitization, and user access/authentication checks executed before handing off control to the AI agent.
- **AI Layer:** Houses core agent orchestration, LLM reasoning (Foundation Model), and semantic RAG retrieval (Document Search).
- **Tools Layer:** Bounded tool execution functions for querying the timetable database and creating/routing support tickets.
- **Data Layer:** Isolated storage databases for activity logs, active case sessions, ingested university handbooks, timetable records, and ticket history.
