import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.baseline_model import GeminiModel


class TestGeminiModel(unittest.TestCase):

    def setUp(self):
        self.model = GeminiModel(api_key="test-api-key")
        self.model.client = MagicMock()

    def test_generate_response_returns_text(self):
        chat = MagicMock()
        chat.send_message.return_value = SimpleNamespace(
            text="Mock student-support response."
        )
        self.model.client.chats.create.return_value = chat

        result = self.model.generate_response(
            "When does registration close?"
        )

        self.assertEqual(
            result,
            "Mock student-support response.",
        )
        chat.send_message.assert_called_once_with(
            "When does registration close?"
        )

    def test_empty_message_is_rejected(self):
        with self.assertRaises(ValueError):
            self.model.generate_response("   ")


if __name__ == "__main__":
    unittest.main()