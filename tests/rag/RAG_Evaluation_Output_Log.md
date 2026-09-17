# RAG System Evaluation: Retrieval Accuracy & Citation Fidelity Output Log

## 1. System & Run Metadata
- **Date/Time:** 2026-09-17 13:47:02 UTC
- **Model Baseline:** Gemini 3.5 Flash-Lite (baseline project wrapper)
- **Embedding Model:** tfidf-svd-lsa-v1
- **Vector Index / Knowledge Base:** Academic Policies & Student Handbook
- **Total Test Queries:** 12 (10 In-Scope | 2 Missing Knowledge)

---

## 2. Metrics Summary Dashboard

| Metric Name | Tested Cases | Passed | Failed | Pass Rate (%) |
|---|---:|---:|---:|---:|
| **Retrieval Accuracy** | 12 | 10 | 2 | 83.33 |
| **Citation Fidelity** | 10 | 10 | 0 | 100.00 |
| **Missing Knowledge Refusal** | 2 | 0 | 2 | 0.00 |
| **Overall Execution Pass Rate** | 12 | 10 | 2 | 83.33 |

---

## 3. Detailed Execution Log

| Query_ID | Category | Input_Query | Retrieved_Chunks_and_Sources | Generated_Response | Retrieval_Accuracy | Citation_Fidelity | Refusal_Correctness | Overall_Status |
|---|---|---|---|---|---|---|---|---|
| RAG-TC-01 | In-Scope | What is the official procedure and deadline for appealing a final course grade? | Nakawa University ICT and Student Portal Guidelines, s. 1 (University Accounts), p. 1 (Score: 0.277); Nakawa University Academic Calendar 2025/2026, s. 6 (Graduation), p. 3 (Score: 0.268) | Every admitted student is issued two credentials: A Student Portal account, with the student number as the username. The Portal is used for registration, course selection, results, fees statements and the Examination.... | Pass | Pass | N/A (In-Scope) | Pass |
| RAG-TC-02 | In-Scope | How is a student's term GPA calculated, and what weight is assigned to letter grades? | Course Handbook: BSc Software Engineering, s. 8 (Academic Advising), p. 4 (Score: 0.458); Course Handbook: BSc Software Engineering, s. 6 (Industrial Training), p. 3 (Score: 0.259) | Every student is assigned a Personal Academic Tutor on first registration and retains the same tutor for the duration of the programme where possible. The tutor meets the student at least once per semester, advises on... | Pass | Pass | N/A (In-Scope) | Pass |
| RAG-TC-03 | In-Scope | What is the minimum cumulative GPA required to avoid academic probation? | Nakawa University Graduation and Academic Awards Policy, s. 2 (Classification of Awards), p. 2 (Score: 0.335); Nakawa University Academic Handbook 2025/2026, s. 3 (Course Add and Drop), p. 2 (Score: 0.286) | The class of an undergraduate award is determined by the cumulative grade point average computed over all courses counting toward the award. | Cumulative GPA | Class of award | |---|---| | 4.40 - 5.00 | First Class Ho... | Pass | Pass | N/A (In-Scope) | Pass |
| RAG-TC-04 | In-Scope | What are the accepted payment methods and portals for settling tuition balances online? | Nakawa University Academic Handbook 2025/2026, s. 2 (Registration), p. 1 (Score: 0.344); Nakawa University Student Fees and Financial Policy, s. 1 (Scope), p. 1 (Score: 0.317) | Every student must register at the beginning of each semester. Registration consists of three steps which must all be completed: Payment of at least sixty per cent (60%) of the semester tuition. Online course selectio... | Pass | Pass | N/A (In-Scope) | Pass |
| RAG-TC-05 | In-Scope | What is the refund schedule percentage if a student drops a course in the second week of the semester? | Nakawa University Student Fees and Financial Policy, s. 5 (Refunds), p. 3 (Score: 0.408); Course Handbook: BSc Software Engineering, s. 6 (Industrial Training), p. 3 (Score: 0.340) | A student who formally drops a course within the add/drop period has the tuition for that course credited in full to their Portal account. A student who withdraws from a course after the add/drop deadline, whether or.... | Pass | Pass | N/A (In-Scope) | Pass |
| RAG-TC-06 | In-Scope | What are the consequences or late penalty charges for unpaid tuition after the official due date? | Nakawa University Academic Calendar 2025/2026, s. 5 (Fees Deadlines), p. 3 (Score: 0.262); Nakawa University Accommodation and Halls of Residence Policy, s. 7 (Withdrawal of a Residence Place), p. 3 (Score: 0.260) | | Activity | Date | |---|---| | Semester I first instalment (60% minimum) due | Friday 26 September 2025 | | Semester I balance due | Friday 31 October 2025 | | Semester II first instalment (60% minimum) due | Friday.... | Pass | Pass | N/A (In-Scope) | Pass |
| RAG-TC-07 | In-Scope | What constitutes academic dishonesty under the university honor code? | Nakawa University Complaints, Appeals and Grievance Procedure, s. 1 (Scope), p. 1 (Score: 0.354); Nakawa University Student Regulations and Code of Conduct, s. 1 (Application of the Code), p. 1 (Score: 0.286) | This Procedure applies to a complaint by a student about a service, a decision or the conduct of a member of the University, and to an appeal against an academic decision on procedural grounds. This Procedure does not... | Pass | Pass | N/A (In-Scope) | Pass |
| RAG-TC-08 | In-Scope | What are the formal steps for a student to report an alleged violation of the code of conduct? | Nakawa University Student Support and Welfare Services, s. 8 (Reporting a Safeguarding or Harassment Concern), p. 3 (Score: 0.293); Nakawa University Academic Handbook 2025/2026, s. 4 (Withdrawal from a Course), p. 3 (Score: 0.284) | A concern about harassment, sexual misconduct or safeguarding is reported to the Dean of Students in person, or through the confidential reporting form on the Portal under Student Services, then Report a Concern. A re... | Pass | Pass | N/A (In-Scope) | Pass |
| RAG-TC-09 | In-Scope | What is the official policy and deadline for dropping a class without receiving a 'W' grade? | Nakawa University Graduation and Academic Awards Policy, s. 2 (Classification of Awards), p. 2 (Score: 0.361); Nakawa University Graduation and Academic Awards Policy, s. 6 (Certificates and Transcripts), p. 3 (Score: 0.259) | The class of an undergraduate award is determined by the cumulative grade point average computed over all courses counting toward the award. | Cumulative GPA | Class of award | |---|---| | 4.40 - 5.00 | First Class Ho... | Pass | Pass | N/A (In-Scope) | Pass |
| RAG-TC-10 | In-Scope | How can a student schedule an official appointment with an academic advisor? | Nakawa University Complaints, Appeals and Grievance Procedure, s. 1 (Scope), p. 1 (Score: 0.318); Nakawa University Graduation and Academic Awards Policy, s. 6 (Certificates and Transcripts), p. 3 (Score: 0.310) | This Procedure applies to a complaint by a student about a service, a decision or the conduct of a member of the University, and to an appeal against an academic decision on procedural grounds. This Procedure does not... | Pass | Pass | N/A (In-Scope) | Pass |
| RAG-TC-11 | Missing Knowledge | What is the specific per-credit tuition fee policy for auditing post-graduate law courses? | Nakawa University Examination Regulations, s. 2 (Eligibility to Sit an Examination), p. 1 (Score: 0.366); Nakawa University Student Fees and Financial Policy, s. 1 (Scope), p. 1 (Score: 0.302) | I’m sorry, but the provided university policy context does not contain information for this request, so I cannot provide a factual answer without risking hallucination. | Fail | N/A (Refused) | Fail | Fail |
| RAG-TC-12 | Missing Knowledge | What are the eligibility requirements and pet deposit fees for on-campus family housing? | Nakawa University Student Fees and Financial Policy, s. 1 (Scope), p. 1 (Score: 0.326); Nakawa University Student Fees and Financial Policy, s. 2 (Structure of Fees), p. 1 (Score: 0.272) | I’m sorry, but the provided university policy context does not contain information for this request, so I cannot provide a factual answer without risking hallucination. | Fail | N/A (Refused) | Fail | Fail |

---

## 4. Failure Analysis & Recommendations
- **Failed Cases Summary:** RAG-TC-11, RAG-TC-12
- **Observed Failure Modes:** Hallucinated citations or weak retrieval signal when the question is outside the approved corpus; over-refusal or false positives are flagged during evaluation.
- **Remediation Actions:** Improve chunk coverage and knowledge-base filtering, enforce stronger threshold checks before generating an answer, and require explicit refusal wording whenever retrieved support is absent.
