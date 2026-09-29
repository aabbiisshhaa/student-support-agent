"""Lightweight telemetry for model and tool execution."""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Iterator

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger("student_support.telemetry")

DEFAULT_CONTEXT_LIMIT = int(
    os.getenv("MODEL_CONTEXT_LIMIT", "1048576")
)

DEFAULT_WARNING_THRESHOLD = float(
    os.getenv("TOKEN_WARNING_THRESHOLD", "0.80")
)


class Telemetry:
    """Records token usage, context risk, and execution latency."""

    def __init__(
        self,
        context_limit: int = DEFAULT_CONTEXT_LIMIT,
        warning_threshold: float = DEFAULT_WARNING_THRESHOLD,
        log_path: str | Path | None = None,
    ) -> None:
        if context_limit <= 0:
            raise ValueError(
                "context_limit must be greater than zero"
            )

        if not 0 < warning_threshold < 1:
            raise ValueError(
                "warning_threshold must be between zero and one"
            )

        self.context_limit = context_limit
        self.warning_threshold = warning_threshold

        self.log_path = Path(
            log_path
            or os.getenv(
                "TELEMETRY_LOG_PATH",
                "logs/telemetry.jsonl",
            )
        )

    def record_model_turn(
        self,
        *,
        session_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float,
        total_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Record tokens and latency for one model turn."""

        self._validate_count(
            "input_tokens",
            input_tokens,
        )
        self._validate_count(
            "output_tokens",
            output_tokens,
        )

        if latency_ms < 0:
            raise ValueError(
                "latency_ms cannot be negative"
            )

        measured_total = input_tokens + output_tokens

        if total_tokens is not None:
            self._validate_count(
                "total_tokens",
                total_tokens,
            )
            measured_total = total_tokens

        utilization = (
            measured_total / self.context_limit
        )

        event = {
            "event": "model_turn",
            "timestamp": self._timestamp(),
            "session_id": session_id,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": measured_total,
            "context_limit": self.context_limit,
            "context_utilization": round(
                utilization,
                4,
            ),
            "overflow_risk": self._context_risk(
                utilization
            ),
            "latency_ms": round(latency_ms, 2),
        }

        self._emit(event)
        return event

    def record_gemini_response(
        self,
        *,
        session_id: str,
        model: str,
        response: Any,
        latency_ms: float,
    ) -> dict[str, Any]:
        """Read token information from a Gemini response."""

        usage = getattr(
            response,
            "usage_metadata",
            None,
        )

        input_tokens = int(
            getattr(
                usage,
                "prompt_token_count",
                0,
            )
            or 0
        )

        output_tokens = int(
            getattr(
                usage,
                "candidates_token_count",
                0,
            )
            or 0
        )

        total_tokens = int(
            getattr(
                usage,
                "total_token_count",
                input_tokens + output_tokens,
            )
            or input_tokens + output_tokens
        )

        return self.record_model_turn(
            session_id=session_id,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
        )

    def record_step(
        self,
        *,
        session_id: str,
        step_type: str,
        step_name: str,
        latency_ms: float,
        success: bool,
        error_type: str | None = None,
    ) -> dict[str, Any]:
        """Record the duration and result of a step."""

        if latency_ms < 0:
            raise ValueError(
                "latency_ms cannot be negative"
            )

        event = {
            "event": "execution_step",
            "timestamp": self._timestamp(),
            "session_id": session_id,
            "step_type": step_type,
            "step_name": step_name,
            "latency_ms": round(latency_ms, 2),
            "success": success,
            "error_type": error_type,
        }

        self._emit(event)
        return event

    @contextmanager
    def measure_step(
        self,
        *,
        session_id: str,
        step_type: str,
        step_name: str,
    ) -> Iterator[None]:
        """Measure how long a code block takes."""

        started = perf_counter()

        try:
            yield
        except Exception as error:
            self.record_step(
                session_id=session_id,
                step_type=step_type,
                step_name=step_name,
                latency_ms=(
                    perf_counter() - started
                ) * 1000,
                success=False,
                error_type=type(error).__name__,
            )
            raise
        else:
            self.record_step(
                session_id=session_id,
                step_type=step_type,
                step_name=step_name,
                latency_ms=(
                    perf_counter() - started
                ) * 1000,
                success=True,
            )

    def _context_risk(
        self,
        utilization: float,
    ) -> str:
        if utilization >= 1:
            return "overflow"

        if utilization >= 0.90:
            return "critical"

        if utilization >= self.warning_threshold:
            return "warning"

        return "normal"

    def _emit(
        self,
        event: dict[str, Any],
    ) -> None:
        """Write an event without storing message content."""

        self.log_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        serialized = json.dumps(
            event,
            ensure_ascii=False,
        )

        with self.log_path.open(
            "a",
            encoding="utf-8",
        ) as log_file:
            log_file.write(serialized + "\n")

        if event.get("overflow_risk") in {
            "warning",
            "critical",
            "overflow",
        }:
            logger.warning(serialized)
        else:
            logger.info(serialized)

    @staticmethod
    def _validate_count(
        name: str,
        value: int,
    ) -> None:
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value < 0
        ):
            raise ValueError(
                f"{name} must be a non-negative integer"
            )

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()