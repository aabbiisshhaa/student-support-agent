"""Aggregated telemetry for complete agent conversation turns."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List

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
    tools_invoked: List[str] = field(
        default_factory=list
    )
    overflow_warning: bool = False
    status: str = "success"
    timestamp: float = field(
        default_factory=time.time
    )


class TelemetryTracker:
    """Stores privacy-conscious summaries of agent turns."""

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

    def record_turn(
        self,
        metrics: TurnTelemetry,
    ) -> None:
        """Calculate context usage and save the turn."""

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

        # Do not store the student's message in telemetry.
        query = payload.pop("user_query", "")
        payload["query_length"] = len(query)

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