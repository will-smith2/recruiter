from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def load_prompt(name: str) -> str:
    path = BASE_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8")


system_prompt = load_prompt("system_prompt")
planning_prompt = load_prompt("planning_prompt")
action_prompt = load_prompt("action_prompt")
reflection_prompt = load_prompt("reflection_prompt")
