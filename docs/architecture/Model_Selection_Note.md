# MODEL SELECTION NOTE

*University Student-Support Case Agent | Week 2 | BSE4104*

## 1. Decision

| | |
|---|---|
| **CHOSEN MODEL** | Gemini 3.5 Flash-Lite (via Google AI Studio free tier) |
| **PROVIDER / ACCESS** | Google AI Studio (Gemini API), free tier |
| **ROLE** | Foundation/default model for the Week 2 baseline (single-model setup; no multi-model routing yet) |
| **WHY** | Sufficient capability for the agent's approved scope; genuinely free tier (no card); fast enough for routine interactions; accessible from Uganda with no setup barriers |

## 2. Selection Rationale

- **Capability fit:** The Boundary Matrix limits the agent to grounded Q&A, ticket drafting, tool-use decisions, and plain-language replies — none needing frontier-level reasoning. Flash-Lite is built for fast, straightforward, high-volume tasks, matching this scope.
- **Cost:** Free input/output tokens via AI Studio, no card, ~5-15 req/min and up to 1,000 req/day (verified against Google's docs, 11 Sept 2026). Removes cost as a constraint at this prototype stage; paid tier (~$0.30/$2.50 per MTok) stays inexpensive if limits bind later.
- **Latency:** Google positions Flash-Lite as its fastest, most cost-efficient tier for straightforward tasks, fitting routine lookups. This is provider-stated positioning, not yet our own measured benchmark — real measurements to follow once wired up.
- **Privacy & access:** Only public/handbook documents and synthetic student data are sent; no real records at this stage, since free-tier content may be used to improve Google's products. API key lives in `.env` (excluded from Git); only the Application Layer may call the model.
- **Team/architecture fit (tie-breaker):** The tool contract was drafted against Anthropic's format; Gemini's `google-genai` SDK supports an equivalent function-calling format, so the contract is portable but needs remapping/retesting before Week 3 — acknowledged as integration work, not a reason to keep Haiku 4.5.

## 3. Alternatives Considered

| Model | Cost (in/out per MTok) | Latency | Why less suitable than Gemini 3.5 Flash-Lite |
|---|---|---|---|
| Gemini 3.5 Flash-Lite (chosen) | Free tier (~$0.30/$2.50 paid) | Fastest, most cost-efficient current tier | **SELECTED** |
| Claude Sonnet 5 | $2 / $10 | Moderate — stronger reasoning, slower than Haiku | Capability exceeds routine enquiry/lookup needs; kept as a possible future escalation model |
| GPT-4o-mini (OpenAI) | $0.15 / $0.60 | Fast | Cheaper, but tool-call contracts are already built on the Anthropic format — switching adds integration work with no capability gain |
| Claude Haiku 4.5 (Anthropic) | $1 / $5 | Anthropic's fastest current model | Strong fit and matches original tool-contract format, but no sustained free API tier — fails this week's pay-nothing requirement |
| DeepSeek V4-Flash | Very low per-token rate, draws down a topped-up/promo balance | Fast | Cheap but not reliably free; API availability from Uganda may vary |
