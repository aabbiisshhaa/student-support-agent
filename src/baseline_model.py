"""Wrapper for communicating with the Gemini model API."""

from __future__ import annotations

import os
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from src.utils.telemetry import Telemetry


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_MODEL = "gemini-3.5-flash-lite"


class ModelAPIError(RuntimeError):
    """Raised when a Gemini API request fails."""


class GeminiModel:
    """Provides a simple interface to the Gemini API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        telemetry: Telemetry | None = None,
    ) -> None:
        resolved_api_key = (
            api_key
            or os.getenv("GEMINI_API_KEY")
        )

        if not resolved_api_key:
            raise ValueError(
                "GEMINI_API_KEY is missing. "
                "Add it to your local .env file."
            )

        self.model = (
            model
            or os.getenv("GEMINI_MODEL")
            or DEFAULT_MODEL
        )

        self.client = genai.Client(
            api_key=resolved_api_key
        )

        self.telemetry = (
            telemetry
            if telemetry is not None
            else Telemetry()
        )

    def generate_response(
        self,
        user_message: str,
        system_prompt: str | None = None,
        max_tokens: int = 500,
        session_id: str = "anonymous",
    ) -> str:
        """Send a message to Gemini and return its text."""

        if not user_message.strip():
            raise ValueError(
                "The user message cannot be empty."
            )

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=max_tokens,
            temperature=0.2,
        )

        started = perf_counter()

        try:
            chat = self.client.chats.create(
                model=self.model,
                config=config,
            )

            response = chat.send_message(
                user_message
            )

        except errors.APIError as error:
            latency_ms = (
                perf_counter() - started
            ) * 1000

            self.telemetry.record_step(
                session_id=session_id,
                step_type="model",
                step_name="gemini_generate_response",
                latency_ms=latency_ms,
                success=False,
                error_type=type(error).__name__,
            )

            raise ModelAPIError(
                "Gemini API request failed "
                f"with status {error.code}."
            ) from error

        latency_ms = (
            perf_counter() - started
        ) * 1000

        self.telemetry.record_gemini_response(
            session_id=session_id,
            model=self.model,
            response=response,
            latency_ms=latency_ms,
        )

        if not response.text:
            raise ModelAPIError(
                "Gemini returned a response "
                "without text."
            )

        return response.text.strip()