# Student-Support Case Agent v1.0.0

## Release Summary

Version 1.0.0 is the first reproducible release of the AI-Native University Student-Support Case Agent. It provides bounded student-support workflows through an interactive command-line application and a Streamlit Web UI.

## Included Features

- Grounded university-policy retrieval using RAG
- Read-only student timetable lookup
- Confirmed support-ticket creation
- Multi-turn conversation memory
- Bounded Sense-Plan-Act-Observe-Revise execution
- Maximum agent iteration enforcement
- Deterministic safety guardrails and escalation
- Token, latency and execution-trace telemetry
- CLI and Streamlit interfaces
- Deterministic offline fallback mode

## Deployment

The release includes:

- Fully pinned Python dependencies
- Python 3.12 multi-stage Docker image
- Separate CLI and Web UI image targets
- Docker Compose service definitions
- Persistent data, log and trace volumes
- Streamlit health check
- Environment-variable configuration
- Deployment and troubleshooting runbook

See [the deployment runbook](runbook.md) for complete instructions.

## Verification

The release was verified using:

```text
394 tests passed
190 subtests passed