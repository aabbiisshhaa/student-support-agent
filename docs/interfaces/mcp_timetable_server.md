# MCP Timetable Server — Interface Contract

## Document Status

| Item | Value |
|---|---|
| System | AI-Native University Student-Support Case Agent |
| Capability specified | Course timetable query service |
| Document type | API Specification & Schema |
| AI safety impact | Deterministic Code |
| Evidence category | API Specification & Schema |
| Owner | Tool Interoperability & Protocols Lead |
| Status | Contract specified; transport binding not yet implemented (see Section 13) |
| Source of truth (code) | `src/tools/timetable_tool.py`, `src/tools/registry.py`, `src/schemas/tool_definitions.json` |
| Related artifacts | [`agent_task_contract.md`](../architecture/agent_task_contract.md), [`state_model.md`](../architecture/state_model.md), [`ai-boundary-matrix.md`](../requirements/ai-boundary-matrix.md) |

---

## 1. Purpose & Scope

This document specifies **one** project capability — the course timetable query service — as a standalone [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server contract. It does not specify the ticket, policy-search, or escalation capabilities; each of those would get its own contract document if standardized the same way.

Today, this capability is a deterministic Python function, `get_course_schedule()` in `src/tools/timetable_tool.py`, called in-process through the execution whitelist in `src/tools/registry.py`. This document specifies the **stable, versioned, schema-validated contract** that the same capability exposes when served over MCP — so any MCP-aware client (not only this project's own orchestrator) can call it, and so the request/response/error shape can never silently drift between the in-process call path and a future standalone server process.

Everything in this contract is enforced by deterministic code: fixed regex patterns, a fixed JSON Schema, and a fixed whitelist entry. No step in validating, authorizing, or answering a request is delegated to a language model.

---

## 2. Capability Metadata

| Field | Value |
|---|---|
| `name` | `get_course_schedule` |
| `version` | `1.0.0` (tracks `src/schemas/tool_definitions.json`) |
| `title` | Course Timetable Query |
| `description` | Retrieves the authenticated student's own course schedule from the institutional timetable store. Read-only; never generates, infers, or changes timetable data. |
| Transport | `stdio` (trusted local/same-host) or `HTTP + SSE` (requires TLS and a bearer session token — see Section 9) |
| Protocol | JSON-RPC 2.0, framed per the MCP specification |
| MCP server name | `student-support.timetable` |
| Backing implementation | `src/tools/timetable_tool.get_course_schedule` |
| Whitelist entry | `src/tools/registry.py` → `ToolSpec(name="get_course_schedule", mutates_database=False, ...)` |
| Idempotent | Yes — repeated identical calls return identical results until the timetable store changes |
| Read-only | Yes — structurally incapable of writing; see Section 9 |
| Deterministic | Yes — no model call, no randomness; same input always produces the same output |
| Authentication required | Yes (Section 9) |
| Rate-limited | Yes (Section 8) |

---

## 3. JSON-RPC 2.0 Envelope

All exchanges use the standard JSON-RPC 2.0 envelope, as required by MCP.

**Request**

```json
{"jsonrpc": "2.0", "id": "<string|number>", "method": "<string>", "params": { "...": "..." }}
```

**Success response**

```json
{"jsonrpc": "2.0", "id": "<same id>", "result": { "...": "..." }}
```

**Protocol-error response** (malformed envelope, unknown method, invalid params shape — see Section 7)

```json
{"jsonrpc": "2.0", "id": "<same id, or null>", "error": {"code": -32602, "message": "...", "data": { "...": "..." }}}
```

This server implements three MCP methods. Only the third carries this capability's business logic; the first two are the standard MCP handshake and discovery methods, included here because "capability metadata" in MCP is delivered through them, not out of band.

| Method | Purpose |
|---|---|
| `initialize` | Capability negotiation. Returns `serverInfo` (`name`, `version`) and declares `capabilities.tools = {}`. No timetable data is exchanged here. |
| `tools/list` | Returns the capability descriptor in Section 4. A client calls this once per session to learn the input schema before calling the tool. |
| `tools/call` | Executes the query. `params.name` must equal `"get_course_schedule"`; any other value is rejected per Section 7 before anything in Section 5 or 6 runs. |

---

## 4. Capability Descriptor (`tools/list` result)

This is the metadata the server returns from `tools/list`. It is generated from the same schema this document defines (Section 5), so the descriptor and the runtime validator can never disagree.

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "get_course_schedule",
        "title": "Course Timetable Query",
        "description": "Retrieves the authenticated student's own course schedule. Read-only; never generates or changes timetable data.",
        "inputSchema": { "$ref": "#/Section-5/request-schema" },
        "outputSchema": { "$ref": "#/Section-6/response-schema" },
        "annotations": {
          "readOnlyHint": true,
          "destructiveHint": false,
          "idempotentHint": true,
          "openWorldHint": false
        }
      }
    ]
  }
}
```

The `annotations` block is the MCP-standard way a server declares its own safety posture to a client **before** any call is made. `readOnlyHint: true` and `destructiveHint: false` are load-bearing here: a conforming MCP client may use them to decide this tool never needs a human-in-the-loop confirmation prompt, unlike a hypothetical `create_support_ticket` MCP contract, which would declare `readOnlyHint: false`.

---

## 5. Request Schema (`tools/call`)

### 5.1 Envelope

```json
{
  "jsonrpc": "2.0",
  "id": 42,
  "method": "tools/call",
  "params": {
    "name": "get_course_schedule",
    "arguments": {
      "student_id": "2300712345",
      "course_code": "BSE4104"
    }
  }
}
```

### 5.2 Strict input model

Identical to `src/schemas/tool_definitions.json` and to the validators in `src/tools/timetable_tool.py` (`_validate_student_id`, `_validate_course_code`, `_validate_day`) and to the `ParamSpec` entries for `get_course_schedule` in `src/tools/registry.py`. One definition, three enforcement points — see Section 12.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "student_id": {
      "type": "string",
      "minLength": 3,
      "maxLength": 30,
      "pattern": "^[A-Za-z0-9][A-Za-z0-9/_-]{2,29}$",
      "description": "The caller's own authenticated student identifier. See Section 9 — the server never trusts this value for authorization by itself."
    },
    "course_code": {
      "type": ["string", "null"],
      "minLength": 2,
      "maxLength": 20,
      "pattern": "^[A-Za-z0-9][A-Za-z0-9 -]{1,19}$",
      "description": "Optional filter. Omit or pass null for the student's full schedule."
    },
    "day": {
      "type": ["string", "null"],
      "enum": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", null],
      "description": "Optional filter."
    }
  },
  "required": ["student_id"]
}
```

`additionalProperties: false` is the schema-level half of the parameter-boundary guarantee: a request carrying any key outside this list is rejected at validation time (Section 7, `-32602`), the same behavior `ToolParameterError` already enforces in-process in `src/tools/registry.py`.

---

## 6. Response Schema (success)

### 6.1 Envelope

```json
{
  "jsonrpc": "2.0",
  "id": 42,
  "result": {
    "isError": false,
    "content": [{ "type": "text", "text": "2 matching session(s) found." }],
    "structuredContent": {
      "schedule": [
        {
          "course_code": "BSE4104",
          "course_name": "Emerging Trends in Software Engineering",
          "day": "monday",
          "start_time": "09:00",
          "end_time": "11:00",
          "room": "CIT-LR1",
          "instructor": "Dr. K. Mugisha"
        },
        {
          "course_code": "BSE4104",
          "course_name": "Emerging Trends in Software Engineering",
          "day": "wednesday",
          "start_time": "09:00",
          "end_time": "11:00",
          "room": "CIT-LR1",
          "instructor": "Dr. K. Mugisha"
        }
      ]
    }
  }
}
```

### 6.2 Strict output model

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "schedule": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["course_code", "course_name", "day", "start_time", "end_time", "room", "instructor"],
        "properties": {
          "course_code": { "type": "string" },
          "course_name": { "type": "string" },
          "day": { "type": "string", "enum": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"] },
          "start_time": { "type": "string", "pattern": "^([01]\\d|2[0-3]):[0-5]\\d$" },
          "end_time": { "type": "string", "pattern": "^([01]\\d|2[0-3]):[0-5]\\d$" },
          "room": { "type": "string" },
          "instructor": { "type": "string" }
        }
      }
    }
  },
  "required": ["schedule"]
}
```

This mirrors the `ScheduleEntry` `TypedDict` in `src/tools/timetable_tool.py` field for field. `schedule` entries are returned sorted by day order then `start_time`, matching `get_course_schedule`'s own sort.

### 6.3 Empty-result semantics

A `course_code` or `day` filter that matches nothing is **not an error**. The server returns `result.structuredContent.schedule: []` with `isError: false`. A client should render this as "no sessions match," not retry or escalate. This matches the orchestrator's own deterministic formatter (`_synthesize_response` in `src/agent/orchestrator.py`), which turns an empty list into "I found no lectures matching your request."

---

## 7. Error Model

MCP draws a hard line between **protocol errors** (the envelope or the request shape is invalid — the call never reaches the capability) and **domain errors** (the request was valid and authorized, but the capability's own business logic could not satisfy it). This contract keeps that line exactly where `src/tools/registry.py` already puts it: a `ToolParameterError` never reaches `get_course_schedule`; a `TimetableValidationError` or `StudentNotFoundError` raised inside it does.

### 7.1 Protocol errors — standard JSON-RPC `error` object

| Code | Name | When |
|---|---|---|
| `-32700` | Parse error | The transport payload is not valid JSON. |
| `-32600` | Invalid Request | The envelope is not a valid JSON-RPC 2.0 request. |
| `-32601` | Method not found | `method` is not `initialize`, `tools/list`, or `tools/call` — **or** `params.name` in a `tools/call` is not `"get_course_schedule"`. The second case is this capability's execution-whitelist boundary (Section 9) expressed at the protocol layer; it is the direct analogue of `registry.UnknownToolError`. |
| `-32602` | Invalid params | `arguments` fails Section 5.2 (wrong type, unknown key, failed pattern/enum, missing `student_id`). Direct analogue of `registry.ToolParameterError` / `TimetableValidationError`. |
| `-32001` | Rate limit exceeded | See Section 8. Reserved server-error range per JSON-RPC 2.0 (`-32000` to `-32099`). |
| `-32002` | Unauthorized | `student_id` does not match the caller's authenticated identity. See Section 9. |

Example — invalid `student_id`:

```json
{"jsonrpc": "2.0", "id": 42, "error": {"code": -32602, "message": "Invalid params", "data": {"field": "student_id", "reason": "does not match ^[A-Za-z0-9][A-Za-z0-9/_-]{2,29}$"}}}
```

### 7.2 Domain errors — a successful envelope with `isError: true`

A request that is well-formed and authorized but cannot be satisfied (for example, no timetable record exists for a syntactically valid `student_id`) is **not** a JSON-RPC error. Per the MCP tool-result shape, it is a normal `result` with `isError: true`, so a client (including an LLM reading the content block) can see and react to the failure without special-casing transport-level errors.

```json
{
  "jsonrpc": "2.0",
  "id": 42,
  "result": {
    "isError": true,
    "content": [{ "type": "text", "text": "No timetable found for student_id '2300799999'." }],
    "structuredContent": { "error": { "type": "StudentNotFoundError", "student_id": "2300799999" } }
  }
}
```

This is the same information shape `src/tools/registry.py` already surfaces as `{"error": str(exception)}`, and that `src/agent/orchestrator.py` already records as a `tool_observations` entry with `status: "error"` — this contract only standardizes it for an external MCP client.

---

## 8. Rate Limits

Enforced by the server process itself, independent of and in addition to any limit an MCP client-side agent loop imposes (such as the orchestrator's own `max_iterations`/`max_replans` bounds in `src/agent/state.py`, which already caps how many times a single bounded run can call any one tool). This is the outer safety net for callers that reach the MCP server directly, outside that loop.

| Scope | Limit | On exceed |
|---|---|---|
| Per `session_id`, sliding window | 30 calls / 60 s, burst ceiling 5 calls / 1 s | `-32001`, `data.retry_after_ms` |
| Per authenticated `student_id`, rolling | 500 calls / 24 h | `-32001`, `data.retry_after_ms` |
| Server-wide | 120 calls / 60 s across all sessions | `-32001`, `data.retry_after_ms` |

Rate-limit state is held in deterministic, in-memory counters (or a shared store if the server is horizontally scaled) — never inferred or waived by a model. Every rejection is logged with `session_id`, `student_id` (if authenticated), and the limit that triggered, to the same telemetry sink pattern already used by `src/telemetry/tracker.py`.

```json
{"jsonrpc": "2.0", "id": 42, "error": {"code": -32001, "message": "Rate limit exceeded", "data": {"scope": "session", "limit": "30/60s", "retry_after_ms": 4120}}}
```

---

## 9. Read-Only Permission & Security Boundary

1. **Structurally read-only.** `get_course_schedule` performs only dict lookups over `MOCK_TIMETABLE` (or, in a production store, only `SELECT`-equivalent reads). No code path in this capability issues a write. This is stronger than a policy flag — there is no write statement to disable. Contrast `ToolSpec.mutates_database=False, confirmation_param=None` here against `create_support_ticket`'s `mutates_database=True, confirmation_param="student_confirmed"` in the same registry.

2. **Input validation is not authorization.** A syntactically valid `student_id` (one that matches the Section 5.2 pattern) proves only that the string is well-formed — it proves nothing about who is asking. The server **must** resolve the caller's authenticated identity independently (from the transport-level session/bearer token, never from the `arguments` payload) and compare it against the requested `student_id`. A mismatch is rejected with `-32002` before `get_course_schedule` is called, regardless of how well-formed the request looks. This is the MCP-contract expression of Rule I-1 in `agent_task_contract.md`: *"the `student_id` used in every tool call must equal the authenticated `student_id` of the session... a student can never look up another student's timetable, even if they type another ID."*

3. **Execution whitelist.** Only `get_course_schedule` and the project's other explicitly registered tools are reachable through `tools/call`; any other `name` is rejected at the protocol layer (`-32601`, Section 7.1) before any handler code runs. This is the MCP-facing counterpart of the static whitelist in `src/tools/registry.py` — no dynamic dispatch, no `eval`-style resolution of tool names, ever.

4. **No scope creep in the response.** The output model (Section 6.2) returns only schedule fields. It never includes grades, fees, disciplinary records, or any data outside this capability's declared scope, per the AI Boundary Matrix.

5. **Transport security.**
   - `stdio` transport is trusted only for a local, same-host, same-trust-boundary client (e.g., this project's own orchestrator process). It carries no network exposure.
   - `HTTP + SSE` transport **requires** TLS and a bearer or session token on every request. It must never be exposed without both. Token validation happens before JSON-RPC parsing — an unauthenticated request never reaches Section 7's JSON-RPC-level error handling at all; it is rejected by the transport layer.

6. **Auditability.** Every call — success, protocol error, domain error, or rate-limit rejection — is logged with `session_id`, resolved `student_id`, `method`, latency, and outcome, mirroring the `ToolObservation` record already defined in `src/agent/state.py`.

---

## 10. Versioning & Compatibility

- This contract is versioned independently (`1.0.0`, Section 2) but changes in lock-step with `src/schemas/tool_definitions.json`; the two must never disagree on the input schema.
- **Minor version** (`1.x.0`): additive, backward-compatible changes only — a new optional request field, a new optional response field, a new non-breaking annotation.
- **Major version** (`x.0.0`): any breaking change — a new required field, a removed field, a changed error code, a changed pattern that rejects previously-valid input. A major version bump requires a new `tools/list` descriptor and should keep the previous `name` available at the prior version until clients migrate, or expose it under a new `name` (e.g. `get_course_schedule_v2`).
- Change control follows the same process as `agent_task_contract.md` Section 11: update this document and the code in the same change, add or update a test proving the new rule, and have at least one other team member review before merging to `main`.

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-10-09 | First MCP contract for the course timetable query capability. |

---

## 11. Example End-to-End Exchanges

**(a) Successful query, filtered by course**

```json
→ {"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_course_schedule","arguments":{"student_id":"2300712345","course_code":"BSE4104"}}}
← {"jsonrpc":"2.0","id":1,"result":{"isError":false,"content":[{"type":"text","text":"2 matching session(s) found."}],"structuredContent":{"schedule":[{"course_code":"BSE4104","course_name":"Emerging Trends in Software Engineering","day":"monday","start_time":"09:00","end_time":"11:00","room":"CIT-LR1","instructor":"Dr. K. Mugisha"},{"course_code":"BSE4104","course_name":"Emerging Trends in Software Engineering","day":"wednesday","start_time":"09:00","end_time":"11:00","room":"CIT-LR1","instructor":"Dr. K. Mugisha"}]}}}
```

**(b) No matching sessions (not an error)**

```json
→ {"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"get_course_schedule","arguments":{"student_id":"2300712345","course_code":"XYZ9999"}}}
← {"jsonrpc":"2.0","id":2,"result":{"isError":false,"content":[{"type":"text","text":"0 matching session(s) found."}],"structuredContent":{"schedule":[]}}}
```

**(c) Invalid params — malformed student_id**

```json
→ {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_course_schedule","arguments":{"student_id":"!!"}}}
← {"jsonrpc":"2.0","id":3,"error":{"code":-32602,"message":"Invalid params","data":{"field":"student_id","reason":"does not match ^[A-Za-z0-9][A-Za-z0-9/_-]{2,29}$"}}}
```

**(d) Domain error — well-formed but unknown student**

```json
→ {"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"get_course_schedule","arguments":{"student_id":"2300799999"}}}
← {"jsonrpc":"2.0","id":4,"result":{"isError":true,"content":[{"type":"text","text":"No timetable found for student_id '2300799999'."}],"structuredContent":{"error":{"type":"StudentNotFoundError","student_id":"2300799999"}}}}
```

**(e) Unauthorized — requested student_id does not match the authenticated caller**

```json
→ {"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"get_course_schedule","arguments":{"student_id":"2300798765"}}}
   (caller's session token resolves to student_id "2300712345")
← {"jsonrpc":"2.0","id":5,"error":{"code":-32002,"message":"Unauthorized","data":{"reason":"student_id does not match the authenticated session"}}}
```

**(f) Unregistered tool name**

```json
→ {"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"delete_timetable_record","arguments":{}}}
← {"jsonrpc":"2.0","id":6,"error":{"code":-32601,"message":"Method not found","data":{"name":"delete_timetable_record"}}}
```

---

## 12. Traceability

| Contract clause | Implemented / verified in |
|---|---|
| Input schema (Section 5.2) | `src/tools/timetable_tool.py` (`_validate_student_id`, `_validate_course_code`, `_validate_day`); `src/schemas/tool_definitions.json`; `src/tools/registry.py` (`ParamSpec` for `get_course_schedule`) |
| Output schema (Section 6.2) | `ScheduleEntry` `TypedDict` in `src/tools/timetable_tool.py` |
| Execution whitelist (Section 9.3) | `src/tools/registry.py` (`_REGISTRY`, `UnknownToolError`); `tests/test_tool_registry.py` |
| Read-only / no mutation path (Section 9.1) | `ToolSpec(mutates_database=False)` in `src/tools/registry.py`; `tests/test_tool_registry.py::TestMutationGuard` |
| Domain-error shape (Section 7.2) | `StudentNotFoundError`, `TimetableValidationError` in `src/tools/timetable_tool.py`; surfaced as `{"error": ...}` in `src/agent/orchestrator.py` |
| Caller-identity binding (Section 9.2, Rule I-1) | `agent_task_contract.md` Section 3; **not yet enforced in code** — the in-process orchestrator currently passes the session's own `student_id`, but no standalone MCP transport/auth layer exists to enforce this for an external caller (see Section 13) |
| Rate limiting (Section 8) | **Not yet implemented** — specified here for the first time (see Section 13) |
| JSON-RPC transport (Sections 3, 7) | **Not yet implemented** — no MCP server process exists in this repository yet (see Section 13) |

---

## 13. Open Items — Not Yet Implemented

This document specifies the contract; it does not itself stand up a server process. Honestly, as of this writing:

1. No MCP server SDK is a project dependency (`requirements.txt` has no `mcp` / `modelcontextprotocol` package). Adding one and a thin `src/mcp/timetable_server.py` binding is follow-up implementation work, not covered by this specification document.
2. The caller-identity-vs-`student_id` check in Section 9.2 exists today only inside the orchestrator's own in-process session binding (`open_session` in `src/app.py`); it is not yet enforced by anything at a JSON-RPC/transport boundary, because that boundary does not exist yet.
3. Rate limiting (Section 8) is specified but not implemented; no counter store exists yet.
4. `tools/list` and `initialize` handler code does not exist yet; Section 4's descriptor is this document's authoritative definition of what that handler must return once written.

Each of these should become its own "Working Code" evidence item, tested against the request/response/error examples in Section 11, before this capability is actually exposed outside this repository's own process.
