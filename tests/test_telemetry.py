import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.utils.telemetry import Telemetry


class TestTelemetry(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.log_path = (
            Path(self.temp_directory.name)
            / "telemetry.jsonl"
        )

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def read_events(self) -> list[dict]:
        lines = self.log_path.read_text(
            encoding="utf-8"
        ).splitlines()

        return [json.loads(line) for line in lines]

    def test_records_model_token_usage(self) -> None:
        telemetry = Telemetry(
            context_limit=1000,
            log_path=self.log_path,
        )

        event = telemetry.record_model_turn(
            session_id="session-1",
            model="gemini-test",
            input_tokens=100,
            output_tokens=50,
            latency_ms=125.5,
        )

        self.assertEqual(event["total_tokens"], 150)
        self.assertEqual(event["overflow_risk"], "normal")
        self.assertEqual(event["latency_ms"], 125.5)

        saved_event = self.read_events()[0]
        self.assertEqual(saved_event["input_tokens"], 100)
        self.assertEqual(saved_event["output_tokens"], 50)

    def test_warns_when_context_usage_is_high(self) -> None:
        telemetry = Telemetry(
            context_limit=1000,
            warning_threshold=0.80,
            log_path=self.log_path,
        )

        event = telemetry.record_model_turn(
            session_id="session-2",
            model="gemini-test",
            input_tokens=800,
            output_tokens=50,
            latency_ms=100,
        )

        self.assertEqual(event["overflow_risk"], "warning")
        self.assertEqual(
            event["context_utilization"],
            0.85,
        )

    def test_reads_gemini_usage_metadata(self) -> None:
        telemetry = Telemetry(
            context_limit=1000,
            log_path=self.log_path,
        )

        response = SimpleNamespace(
            usage_metadata=SimpleNamespace(
                prompt_token_count=120,
                candidates_token_count=30,
                total_token_count=150,
            )
        )

        event = telemetry.record_gemini_response(
            session_id="session-3",
            model="gemini-test",
            response=response,
            latency_ms=75,
        )

        self.assertEqual(event["input_tokens"], 120)
        self.assertEqual(event["output_tokens"], 30)
        self.assertEqual(event["total_tokens"], 150)

    def test_measures_tool_execution(self) -> None:
        telemetry = Telemetry(
            context_limit=1000,
            log_path=self.log_path,
        )

        with telemetry.measure_step(
            session_id="session-4",
            step_type="tool",
            step_name="get_course_schedule",
        ):
            result = 2 + 2

        self.assertEqual(result, 4)

        event = self.read_events()[0]
        self.assertEqual(
            event["event"],
            "execution_step",
        )
        self.assertEqual(
            event["step_name"],
            "get_course_schedule",
        )
        self.assertTrue(event["success"])
        self.assertGreaterEqual(event["latency_ms"], 0)


if __name__ == "__main__":
    unittest.main()