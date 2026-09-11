import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.baseline_model import GeminiModel, ModelAPIError
from src.utils.parser import ParsedResponse, parse_model_response

PROMPT_VERSION = "v2"
PROMPT_PATH = PROJECT_ROOT / "prompts" / PROMPT_VERSION / "system-prompt.md"


def load_system_prompt(prompt_path: Path = PROMPT_PATH) -> str:
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8").strip()
    return ""


def handle_message(model: GeminiModel, system_prompt: str, user_message: str) -> ParsedResponse:
    try:
        raw_response = model.generate_response(user_message, system_prompt=system_prompt)
    except ValueError as error:
        return parse_model_response(f"[CLARIFY]\n{error}")
    except ModelAPIError as error:
        return parse_model_response(f"[ESCALATE]\n{error}")

    return parse_model_response(raw_response)


def run_cli() -> None:
    model = GeminiModel()
    system_prompt = load_system_prompt()

    print("Student Support Agent (baseline). Type 'exit' to quit.")

    while True:
        try:
            user_message = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if user_message.lower() in {"exit", "quit"}:
            break
        if not user_message:
            continue

        parsed = handle_message(model, system_prompt, user_message)
        print(f"Agent [{parsed.intent.value}]: {parsed.message}")

        if parsed.requires_human:
            print("Agent: This has been flagged for a human staff member to review.")


if __name__ == "__main__":
    run_cli()
