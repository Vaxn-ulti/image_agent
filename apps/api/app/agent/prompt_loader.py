from __future__ import annotations

from pathlib import Path


PROMPT_ROOT = Path(__file__).with_name("prompts")
PROMPT_NAMES = ("planner", "responder", "safety", "tool-use", "rag-use")


def load_prompt(name: str) -> str:
    if name not in PROMPT_NAMES:
        raise KeyError(name)
    return (PROMPT_ROOT / f"{name}.md").read_text(encoding="utf-8").strip()


def load_prompt_bundle() -> dict[str, str]:
    return {name: load_prompt(name) for name in PROMPT_NAMES}
