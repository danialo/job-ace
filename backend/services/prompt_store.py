"""Polish prompt file store.

Shipped prompts are versioned files under backend/prompts/polish/.
Resolution: <category>.txt if present, else default.txt. Placeholders are
replaced literally ({block_text}, {category}) — never str.format, because
resume text may contain braces. See specs/polish-prompt-lab.md.
"""

from __future__ import annotations

from pathlib import Path

PROMPT_DIR = Path(__file__).parent.parent / "prompts" / "polish"


def load_polish_template(category: str | None) -> str:
    if category:
        candidate = PROMPT_DIR / f"{category.lower().strip()}.txt"
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    return (PROMPT_DIR / "default.txt").read_text(encoding="utf-8")


def render_polish_prompt(block_text: str, category: str | None) -> str:
    template = load_polish_template(category)
    return render_template(template, block_text, category)


def render_template(template: str, block_text: str, category: str | None) -> str:
    return (
        template
        .replace("{block_text}", block_text)
        .replace("{category}", category or "general")
    )


def shipped_prompt_text() -> str:
    """Raw default template — the Prompt Lab's read-only baseline."""
    return (PROMPT_DIR / "default.txt").read_text(encoding="utf-8")
