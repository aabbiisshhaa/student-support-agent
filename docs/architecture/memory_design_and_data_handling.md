# Memory Design and Student Data Handling

## Document Status

| Item | Value |
|---|---|
| System | AI-Native University Student-Support Case Agent |
| Document type | Institutional compliance and data-handling note |
| AI safety impact | Human Approval Required |
| Evidence category | Documentation |
| Owner | Project team |
| Approval authority | University administration and authorised Data Protection Officer |
| Status | Proposed controls pending institutional approval |

## 1. Purpose

This document explains how the University Student-Support Case Agent handles student information during conversations, timetable enquiries and support-ticket creation.

It identifies:

- the student data collected and stored;
- the operational reason for storing each category;
- access restrictions based on user roles;
- proposed retention periods;
- deletion and Right-to-be-Forgotten procedures; and
- controls that require institutional approval before production deployment.

This document does not replace legal advice or Makerere University policy. Retention periods, legal bases, staff permissions and deletion exceptions must be approved by the University or its authorised Data Protection Officer before the system handles production student data.

## 2. Data-Protection Principles

The system shall follow these principles:

1. **Purpose limitation:** Student data shall only be used to answer enquiries, maintain conversation continuity, retrieve authorised timetable information and manage support cases.
2. **Data minimisation:** The system shall collect only the information needed to complete the requested service.
3. **Storage limitation:** Personal data shall not be retained longer than necessary.
4. **Accuracy:** Students and authorised staff shall be able to request correction of inaccurate information.
5. **Security and confidentiality:** Access shall be limited according to assigned roles.
6. **Transparency:** Students shall be informed about what data is collected, why it is needed and how long it is retained.
7. **Human oversight:** Retention exceptions, access to sensitive records and rejected deletion requests require authorised human approval.

These principles reflect the Uganda Data Protection and Privacy Act, 2019 and the data-protection principles expressed in the General Data Protection Regulation.

## 3. Data Stored by the System

### 3.1 Conversation Session Data

The session-memory component may store:

| Data item | Operational justification |
|---|---|
| Session ID | Connects messages belonging to the same support interaction without using the student's name as the primary identifier. |
| Student reference or student ID | Associates the session with the authenticated student and supports authorised timetable or case enquiries. |
| Conversation messages | Preserves recent questions and responses so the student does not need to repeat information during a multi-turn conversation. |
| Rolling conversation summary | Retains limited context after older messages leave the sliding window. |
| Message role | Distinguishes student, assistant and system messages. |
| Turn number | Preserves the order of the conversation and supports debugging and audit review. |
| Creation time | Records when the support session began. |
| Last-active time | Supports inactivity detection and retention cleanup. |
| Session status | Records whether the session is active or closed. |
| Number of summarised turns | Provides evidence that the bounded-memory mechanism is operating. |

The current deterministic memory implementation retains a maximum of six recent messages by default. Older messages are converted into bounded, rule-based summary lines. The summary retains no more than eight lines.

The summarisation process does not call an AI model and therefore produces the same result for the same input.

### 3.2 Timetable Enquiry Data

A timetable request may process:

- authenticated student ID;
- course code;
- requested day;
- relevant timetable records; and
- tool execution status.

Timetable information is read-only. The agent cannot create, alter or delete official timetable records.

Timetable results should remain in the active conversation only unless they are required as part of a support ticket or authorised audit record.

### 3.3 Support-Ticket Data

A confirmed support ticket may contain:

- ticket ID;
- student ID;
- case ID, where applicable;
- student's original message;
- factual ticket summary;
- request category;
- priority;
- confirmation that the student approved submission;
- ticket creation time;
- ticket status; and
- assigned support queue or authorised staff member.

A support ticket shall only be created after the student confirms the drafted information. Ticket identifiers, routing, storage and status changes are performed by deterministic application code.

### 3.4 Telemetry and Audit Data

The telemetry component may record:

- session ID;
- model name;
- input, output and total token counts;
- model latency;
- tool-execution latency;
- total request latency;
- tools invoked;
- context-window utilisation;
- overflow-risk warnings;
- execution status; and
- timestamp.

Telemetry is used to monitor reliability, performance, context-window risks and system failures.

Raw student messages should not be copied into telemetry records. Where correlation is necessary, the system should use a pseudonymous session identifier rather than the student's name.

### 3.5 Data the System Must Not Store

The system shall not intentionally store:

- student passwords;
- API keys or other system credentials;
- payment-card information;
- unnecessary copies of grades or examination results;
- unnecessary fee or financial records;
- medical, disciplinary or disability information unless specifically required and institutionally approved;
- unrestricted model reasoning or hidden chain-of-thought;
- personal information unrelated to the support request; or
- data belonging to another student.

Students should be warned not to enter passwords, payment details or unrelated sensitive personal information into the enquiry interface.

## 4. Data Storage Locations

The current prototype stores session-memory records as JSON files under:

```text
data/sessions/