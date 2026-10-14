"""Tests for privacy-conscious observability spans."""

import json

from src.telemetry.tracker import TelemetryTracker


def test_trace_contains_required_observability_spans(tmp_path):
    tracker = TelemetryTracker(log_dir=tmp_path / "logs")

    trace_path = tracker.record_trace(
        "session-1_run",
        {
            "session_id": "session-1",
            "user_query": "Show my BSE4104 timetable.",
            "prompt_template": "You are a student-support agent.",
            "model_name": "gemini-test",
            "context_snippets": [
                {
                    "doc": "Academic Handbook",
                    "citation": "Section 4.2",
                    "text": "Students must register before the deadline.",
                }
            ],
            "tool_calls": [
                {
                    "tool": "get_course_schedule",
                    "params": {
                        "student_id": "2300712345",
                        "course_code": "BSE4104",
                    },
                    "status": "ok",
                    "result": [
                        {
                            "course_code": "BSE4104",
                            "day": "Monday",
                            "time": "09:00",
                        }
                    ],
                    "latency_ms": 12.5,
                }
            ],
            "token_usage": {
                "prompt": 120,
                "completion": 30,
                "total": 150,
            },
            "latencies_ms": {
                "model": 80.0,
                "tools": 12.5,
                "total": 95.0,
            },
            "status": "success",
            "iterations": 1,
            "final_response": "Your BSE4104 lecture is on Monday.",
            "events": [],
            "snapshots": [],
        },
    )

    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    span_types = [span["span_type"] for span in trace["spans"]]

    assert trace["status"] == "success"
    assert trace["prompt_template_hash"]
    assert trace["token_usage"]["total"] == 150
    assert "prompt" in span_types
    assert "retrieval_context" in span_types
    assert "tool" in span_types
    assert "model" in span_types


def test_trace_does_not_store_raw_sensitive_text(tmp_path):
    tracker = TelemetryTracker(log_dir=tmp_path / "logs")

    secret_query = "My student number is 2300712345."
    secret_response = "The private student response."

    trace_path = tracker.record_trace(
        "private-session",
        {
            "session_id": "private-session",
            "user_query": secret_query,
            "prompt_template": "System instructions",
            "context_snippets": [],
            "tool_calls": [],
            "token_usage": {},
            "latencies_ms": {},
            "status": "success",
            "iterations": 1,
            "final_response": secret_response,
            "events": [],
            "snapshots": [],
        },
    )

    stored_text = trace_path.read_text(encoding="utf-8")

    assert secret_query not in stored_text
    assert secret_response not in stored_text
    assert "2300712345" not in stored_text


def test_tool_parameters_and_results_are_sanitized(tmp_path):
    tracker = TelemetryTracker(log_dir=tmp_path / "logs")

    trace_path = tracker.record_trace(
        "tool-session",
        {
            "session_id": "tool-session",
            "user_query": "Create a support ticket.",
            "prompt_template": "System instructions",
            "context_snippets": [],
            "tool_calls": [
                {
                    "tool": "create_support_ticket",
                    "params": {
                        "student_id": "2300712345",
                        "original_message": "My private support request.",
                        "api_key": "do-not-store-this",
                    },
                    "status": "ok",
                    "result": {
                        "ticket_id": "TICKET-001",
                        "summary": "Private ticket summary",
                    },
                    "latency_ms": 20.0,
                }
            ],
            "token_usage": {},
            "latencies_ms": {"tools": 20.0},
            "status": "success",
            "iterations": 1,
            "final_response": "Ticket created.",
            "events": [],
            "snapshots": [],
        },
    )

    stored_text = trace_path.read_text(encoding="utf-8")

    assert "2300712345" not in stored_text
    assert "My private support request." not in stored_text
    assert "Private ticket summary" not in stored_text
    assert "do-not-store-this" not in stored_text
    assert "[REDACTED]" in stored_text


def test_unsafe_trace_name_is_cleaned(tmp_path):
    tracker = TelemetryTracker(log_dir=tmp_path / "logs")

    trace_path = tracker.record_trace(
        "../../unsafe trace",
        {
            "session_id": "session-4",
            "status": "success",
            "iterations": 0,
        },
    )

    assert trace_path.parent == tracker.trace_dir
    assert trace_path.name == "unsafe_trace.json"