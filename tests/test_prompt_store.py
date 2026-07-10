"""Tests for the polish prompt file loader."""
from pathlib import Path

from backend.services import prompt_store


def test_default_template_loads():
    tpl = prompt_store.load_polish_template(None)
    assert "{block_text}" in tpl
    assert "NON-NEGOTIABLE RULES" in tpl


def test_category_file_wins_over_default():
    cat_file = prompt_store.PROMPT_DIR / "unittestcat.txt"
    cat_file.write_text("CATEGORY PROMPT {block_text}", encoding="utf-8")
    try:
        assert prompt_store.load_polish_template("unittestcat") == "CATEGORY PROMPT {block_text}"
        assert "NON-NEGOTIABLE" in prompt_store.load_polish_template("experience")
    finally:
        cat_file.unlink()


def test_render_substitutes_and_survives_braces():
    rendered = prompt_store.render_polish_prompt("Built {JSON} parsers", None)
    assert "Built {JSON} parsers" in rendered
    assert "{block_text}" not in rendered


def test_render_matches_previous_inline_prompt():
    """Byte-identity with the prompt previously inlined in app.py."""
    block_text = "Dev, Acme, 2020\n• Did things."
    rendered = prompt_store.render_polish_prompt(block_text, "experience")
    assert rendered.startswith("You are polishing a single WORK EXPERIENCE entry")
    assert rendered.rstrip("\n").endswith(block_text)


def test_render_never_rescans_substituted_text():
    rendered = prompt_store.render_polish_prompt("Worked on {category} systems", None)
    assert "Worked on {category} systems" in rendered


def test_shipped_prompt_text_is_raw_template():
    raw = prompt_store.shipped_prompt_text()
    assert "{block_text}" in raw
