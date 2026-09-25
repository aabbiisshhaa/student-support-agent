import unittest

from src.agent.memory import SessionMemoryManager


class TestReplaceLastAssistantTurn(unittest.TestCase):
    def setUp(self) -> None:
        self.memory = SessionMemoryManager(persist=False)
        self.token = self.memory.create_session(student_ref="2300712345")

    def test_replaces_the_content_of_the_latest_assistant_turn(self) -> None:
        self.memory.add_turn(self.token, "user", "hello")
        self.memory.add_turn(self.token, "assistant", "model wording")

        replaced = self.memory.replace_last_assistant_turn(self.token, "confirmed wording")

        self.assertTrue(replaced)
        self.assertEqual(
            self.memory.get_context(self.token),
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "confirmed wording"},
            ],
        )

    def test_does_not_change_turn_count_or_earlier_turns(self) -> None:
        self.memory.add_turn(self.token, "user", "first question")
        self.memory.add_turn(self.token, "assistant", "first answer")
        self.memory.add_turn(self.token, "user", "second question")
        self.memory.add_turn(self.token, "assistant", "second answer")

        self.memory.replace_last_assistant_turn(self.token, "amended answer")

        state = self.memory.get_session(self.token)
        self.assertEqual(state.turn_count, 4)
        self.assertEqual(
            [message.content for message in state.messages],
            ["first question", "first answer", "second question", "amended answer"],
        )

    def test_leaves_a_trailing_user_turn_alone(self) -> None:
        self.memory.add_turn(self.token, "user", "waiting for an answer")

        replaced = self.memory.replace_last_assistant_turn(self.token, "should not appear")

        self.assertFalse(replaced)
        self.assertEqual(self.memory.get_session(self.token).messages[-1].content, "waiting for an answer")

    def test_returns_false_for_an_empty_session(self) -> None:
        self.assertFalse(self.memory.replace_last_assistant_turn(self.token, "nothing to replace"))


if __name__ == "__main__":
    unittest.main()
