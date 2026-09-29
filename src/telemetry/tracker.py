# Telemetry & Metrics Tracker
# AI Safety Impact: Observability, auditability, and token quota tracking.

import time
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

logger = logging.getLogger("Telemetry")


@dataclass
class TurnTelemetry:
    # Metrics collected per conversational turn and agent loop cycle."""

    session_id: str
    turn_index: int
    user_query: str
    model_name: str = "gemini-3.5-flash-lite"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    context_window_limit: int = 1_000_000
    context_window_usage_pct: float = 0.0
    model_latency_ms: float = 0.0
    tool_latency_ms: float = 0.0
    total_turn_latency_ms: float = 0.0
    tools_invoked: List[str] = field(default_factory=list)
    overflow_warning: bool = False
    status: str = "success"
    timestamp: float = field(default_factory=time.time)


class TelemetryTracker:
    # Records real-time execution telemetry and appends structured records to JSONL."""

    def __init__(self, log_dir: Optional[str] = None):
        self.log_dir = Path(log_dir) if log_dir else PROJECT_ROOT / "data" / "telemetry"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "agent_telemetry.jsonl"

    def record_turn(self, metrics: TurnTelemetry) -> None:
        # Calculates window usage thresholds and appends turn metrics to disk."""
        if metrics.context_window_limit > 0:
            metrics.context_window_usage_pct = round(
                (metrics.total_tokens / metrics.context_window_limit) * 100, 4
            )
        metrics.overflow_warning = metrics.context_window_usage_pct > 80.0

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(metrics)) + "\n")

        logger.info(
            f"[Telemetry] Session {metrics.session_id} Turn {metrics.turn_index} | "
            f"Total: {metrics.total_turn_latency_ms:.1f}ms (Model: {metrics.model_latency_ms:.1f}ms, Tool: {metrics.tool_latency_ms:.1f}ms) | "
            f"Tokens: {metrics.total_tokens} (Prompt: {metrics.prompt_tokens}, Resp: {metrics.completion_tokens})"
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("\n=== TESTING TELEMETRY TRACKER STANDALONE ===")
    tracker = TelemetryTracker()
    sample = TurnTelemetry(
        session_id="test-telemetry-01",
        turn_index=1,
        user_query="Schedule check",
        prompt_tokens=120,
        completion_tokens=45,
        total_tokens=165,
        model_latency_ms=450.2,
        tool_latency_ms=12.5,
        total_turn_latency_ms=480.0,
        tools_invoked=["get_course_schedule"],
    )
    tracker.record_turn(sample)
    assert tracker.log_file.exists(), "Telemetry log file does not exist!"
    print(f"Log written successfully to: {tracker.log_file}")
    print("Telemetry module verified.")