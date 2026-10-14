"""Privacy-conscious telemetry and observability traces for agent runs."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, List

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger("student_support.turn_telemetry")

DEFAULT_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite",
)

DEFAULT_CONTEXT_LIMIT = int(
    os.getenv(
        "MODEL_CONTEXT_LIMIT",
        "1048576",
    )
)

_raw_warning_threshold = float(
    os.getenv(
        "TOKEN_WARNING_THRESHOLD",
        "0.80",
    )
)

WARNING_THRESHOLD_PERCENT = (
    _raw_warning_threshold * 100
    if _raw_warning_threshold <= 1
    else _raw_warning_threshold
)

SENSITIVE_TEXT_FIELDS = {
    "content",
    "final_response",
    "message",
    "observation",
    "original_message",
    "query",
    "summary",
    "text",
    "user_query",
    "goal",
    "response",
}

IDENTIFIER_FIELDS = {
    "student_id",
    "student_ref",
}

SECRET_FIELDS = {
    "api_key",
    "authorization",
    "password",
    "secret",
    "token",
}


@dataclass
class TurnTelemetry:
    """Metrics collected for one complete agent turn."""

    session_id: str
    turn_index: int
    user_query: str
    model_name: str = DEFAULT_MODEL
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    context_window_limit: int = DEFAULT_CONTEXT_LIMIT
    context_window_usage_pct: float = 0.0
    model_latency_ms: float = 0.0
    tool_latency_ms: float = 0.0
    total_turn_latency_ms: float = 0.0
    tools_invoked: List[str] = field(default_factory=list)
    overflow_warning: bool = False
    status: str = "success"
    timestamp: float = field(default_factory=time.time)


class TelemetryTracker:
    """Stores privacy-conscious turn summaries and execution traces."""

    def __init__(
        self,
        log_dir: str | Path | None = None,
    ) -> None:
        self.log_dir = (
            Path(log_dir)
            if log_dir
            else PROJECT_ROOT / "logs"
        )

        self.log_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.log_file = (
            self.log_dir
            / "agent_turn_telemetry.jsonl"
        )

        self.trace_dir = self.log_dir.parent / "traces"
        self.trace_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    @staticmethod
    def hash_text(value: str) -> str:
        """Return a stable SHA-256 fingerprint without storing the text."""

        return hashlib.sha256(
            value.encode("utf-8")
        ).hexdigest()

    @classmethod
    def text_evidence(cls, value: str) -> dict[str, Any]:
        """Represent sensitive text using only its hash and length."""

        return {
            "sha256": cls.hash_text(value),
            "length": len(value),
        }

    @staticmethod
    def _safe_trace_name(trace_name: str) -> str:
        """Prevent trace names from creating unsafe filesystem paths."""

        cleaned = re.sub(
            r"[^A-Za-z0-9_.-]+",
            "_",
            trace_name,
        ).strip("._")

        return cleaned or "agent_trace"

    @classmethod
    def _sanitize_value(
        cls,
        value: Any,
        field_name: str = "",
    ) -> Any:
        """Recursively remove secrets and replace sensitive text with evidence."""

        normalised_name = field_name.lower()

        if any(
            secret in normalised_name
            for secret in SECRET_FIELDS
        ):
            return "[REDACTED]"

        if value is None or isinstance(
            value,
            (bool, int, float),
        ):
            return value

        if isinstance(value, str):
            if normalised_name in IDENTIFIER_FIELDS:
                return {
                    "sha256": cls.hash_text(value),
                    "type": "pseudonymous_identifier",
                }

            if (
                normalised_name in SENSITIVE_TEXT_FIELDS
                or normalised_name.endswith("_query")
                or normalised_name.endswith("_message")
            ):
                return cls.text_evidence(value)

            return value[:500]

        if isinstance(value, dict):
            return {
                str(key): cls._sanitize_value(
                    item,
                    str(key),
                )
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [
                cls._sanitize_value(
                    item,
                    field_name,
                )
                for item in value
            ]

        return str(value)[:500]

    @classmethod
    def _rag_evidence(
        cls,
        context_snippets: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Create inspectable RAG evidence without storing passage text."""

        evidence: list[dict[str, Any]] = []

        for index, snippet in enumerate(
            context_snippets,
            start=1,
        ):
            text = str(snippet.get("text", ""))

            evidence.append(
                {
                    "rank": index,
                    "document": snippet.get("doc"),
                    "citation": snippet.get("citation"),
                    "text_sha256": (
                        cls.hash_text(text)
                        if text
                        else None
                    ),
                    "text_length": len(text),
                }
            )

        return evidence

    @classmethod
    def _build_spans(
        cls,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Convert an agent payload into ordered observability spans."""

        spans: list[dict[str, Any]] = []

        prompt_template = str(
            payload.get("prompt_template", "")
        )
        prompt_template_hash = payload.get(
            "prompt_template_hash"
        )

        if prompt_template:
            prompt_template_hash = cls.hash_text(
                prompt_template
            )

        user_query = str(
            payload.get("user_query", "")
        )

        spans.append(
            {
                "span_id": "span-001",
                "span_type": "prompt",
                "name": "prompt.prepare",
                "status": "ok",
                "latency_ms": 0.0,
                "attributes": {
                    "template_sha256": prompt_template_hash,
                    "query_sha256": (
                        cls.hash_text(user_query)
                        if user_query
                        else None
                    ),
                    "query_length": len(user_query),
                },
            }
        )

        context_snippets = payload.get(
            "context_snippets",
            [],
        )

        if context_snippets:
            spans.append(
                {
                    "span_id": (
                        f"span-{len(spans) + 1:03d}"
                    ),
                    "span_type": "retrieval_context",
                    "name": "rag.context_selected",
                    "status": "ok",
                    "latency_ms": 0.0,
                    "attributes": {
                        "passage_count": len(
                            context_snippets
                        ),
                        "sources": cls._rag_evidence(
                            context_snippets
                        ),
                    },
                }
            )

        for tool_call in payload.get(
            "tool_calls",
            [],
        ):
            tool_name = str(
                tool_call.get(
                    "tool",
                    "unknown_tool",
                )
            )

            span_type = (
                "retrieval"
                if tool_name == "retriever"
                else "tool"
            )

            spans.append(
                {
                    "span_id": (
                        f"span-{len(spans) + 1:03d}"
                    ),
                    "span_type": span_type,
                    "name": (
                        "rag.retrieve"
                        if tool_name == "retriever"
                        else f"tool.{tool_name}"
                    ),
                    "status": tool_call.get(
                        "status",
                        "unknown",
                    ),
                    "latency_ms": round(
                        float(
                            tool_call.get(
                                "latency_ms",
                                0.0,
                            )
                        ),
                        3,
                    ),
                    "attributes": {
                        "parameters": (
                            cls._sanitize_value(
                                tool_call.get(
                                    "params",
                                    {},
                                )
                            )
                        ),
                        "return_payload": (
                            cls._sanitize_value(
                                tool_call.get(
                                    "result"
                                ),
                                "result",
                            )
                        ),
                    },
                }
            )

        token_usage = payload.get(
            "token_usage",
            {},
        )
        latencies = payload.get(
            "latencies_ms",
            {},
        )
        final_response = str(
            payload.get(
                "final_response",
                "",
            )
        )

        spans.append(
            {
                "span_id": (
                    f"span-{len(spans) + 1:03d}"
                ),
                "span_type": "model",
                "name": "model.generate_response",
                "status": payload.get(
                    "status",
                    "unknown",
                ),
                "latency_ms": round(
                    float(
                        latencies.get(
                            "model",
                            0.0,
                        )
                    ),
                    3,
                ),
                "attributes": {
                    "model": payload.get(
                        "model_name",
                        DEFAULT_MODEL,
                    ),
                    "prompt_tokens": int(
                        token_usage.get(
                            "prompt",
                            0,
                        )
                    ),
                    "completion_tokens": int(
                        token_usage.get(
                            "completion",
                            0,
                        )
                    ),
                    "total_tokens": int(
                        token_usage.get(
                            "total",
                            0,
                        )
                    ),
                    "response_sha256": (
                        cls.hash_text(
                            final_response
                        )
                        if final_response
                        else None
                    ),
                    "response_length": len(
                        final_response
                    ),
                },
            }
        )

        return spans

    def record_trace(
        self,
        trace_name: str,
        payload: dict[str, Any],
    ) -> Path:
        """Persist a structured, privacy-conscious execution trace."""

        safe_name = self._safe_trace_name(
            trace_name
        )
        trace_path = (
            self.trace_dir
            / f"{safe_name}.json"
        )

        stored_trace = {
            "trace_version": "1.0",
            "trace_name": safe_name,
            "session_id": payload.get(
                "session_id"
            ),
            "timestamp": time.time(),
            "status": payload.get(
                "status",
                "unknown",
            ),
            "escalation_required": bool(
                payload.get(
                    "escalation_required",
                    False,
                )
            ),
            "iterations": int(
                payload.get(
                    "iterations",
                    0,
                )
            ),
            "prompt_template_hash": (
                self.hash_text(
                    str(
                        payload.get(
                            "prompt_template",
                            "",
                        )
                    )
                )
                if payload.get("prompt_template")
                else payload.get(
                    "prompt_template_hash"
                )
            ),
            "token_usage": self._sanitize_value(
                payload.get(
                    "token_usage",
                    {},
                )
            ),
            "latencies_ms": self._sanitize_value(
                payload.get(
                    "latencies_ms",
                    {},
                )
            ),
            "rag_evidence": self._rag_evidence(
                payload.get(
                    "context_snippets",
                    [],
                )
            ),
            "spans": self._build_spans(
                payload
            ),
            "events": self._sanitize_value(
                payload.get(
                    "events",
                    [],
                )
            ),
            "snapshots": self._sanitize_value(
                payload.get(
                    "snapshots",
                    [],
                )
            ),
        }

        try:
            with trace_path.open(
                "w",
                encoding="utf-8",
            ) as trace_file:
                json.dump(
                    stored_trace,
                    trace_file,
                    ensure_ascii=False,
                    indent=2,
                )
                trace_file.write("\n")
        except OSError as error:
            logger.error(
                "Could not write execution trace: %s",
                error,
            )

        return trace_path

    def record_turn(
        self,
        metrics: TurnTelemetry,
    ) -> None:
        """Calculate context usage and save the turn summary."""

        if metrics.context_window_limit > 0:
            metrics.context_window_usage_pct = round(
                (
                    metrics.total_tokens
                    / metrics.context_window_limit
                )
                * 100,
                4,
            )

        metrics.overflow_warning = (
            metrics.context_window_usage_pct
            >= WARNING_THRESHOLD_PERCENT
        )

        payload = asdict(metrics)

        # Do not store the student's raw message in telemetry.
        query = payload.pop(
            "user_query",
            "",
        )
        payload["query_length"] = len(query)
        payload["query_sha256"] = self.hash_text(
            query
        )

        try:
            with self.log_file.open(
                "a",
                encoding="utf-8",
            ) as log_file:
                log_file.write(
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except OSError as error:
            # Telemetry failure must not stop the agent.
            logger.error(
                "Could not write turn telemetry: %s",
                error,
            )
            return

        logger.info(
            "[Telemetry] Session %s Turn %s | "
            "Total %.1fms | Model %.1fms | "
            "Tools %.1fms | Tokens %s | Risk %s",
            metrics.session_id,
            metrics.turn_index,
            metrics.total_turn_latency_ms,
            metrics.model_latency_ms,
            metrics.tool_latency_ms,
            metrics.total_tokens,
            (
                "warning"
                if metrics.overflow_warning
                else "normal"
            ),
        )