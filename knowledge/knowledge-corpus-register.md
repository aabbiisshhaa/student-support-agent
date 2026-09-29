# Knowledge Corpus & Provenance Register

**System:** AI-Native University Student-Support Case Agent
**Module:** RAG Knowledge Pipeline

---

## Overview

The knowledge corpus contains all public handbook documents, course guidelines, and mock database schemas used by the agent for RAG retrieval and tool execution.

The primary, machine-readable provenance register is maintained in **[`mak_knowledge-corpus-register.csv`](./knowledge-corpus-register.csv)**.

---

## Data Summary

| Source ID     | Document Title                               | Domain / Category     | Source Type              | Ingestion Format |
| :------------ | :------------------------------------------- | :-------------------- | :----------------------- | :--------------- |
| **CORPUS-01** | Makerere University Undergraduate Prospectus | Academic Policy       | Official Public Handbook | Plain Text / PDF |
| **CORPUS-02** | CoCIS Course Outlines & Guidelines           | Course Administration | Official Public Document | Markdown / PDF   |
| **CORPUS-03** | Semester Timetable & Room Allocation Index   | Timetable Service     | Mock Database / API      | JSON / SQLite    |
| **CORPUS-04** | Synthetic Student Support Ticket History     | Case Management       | Synthetic Benchmark      | JSON Records     |
