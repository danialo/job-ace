from __future__ import annotations

import json
from pathlib import Path


def test_form_schema_file_exists() -> None:
    path = Path("docs/schemas/form_schema.json")
    assert path.exists(), "form_schema.json should exist"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("title") == "Captured Job Form Schema"


def test_worksheet_answers_schema_file_exists() -> None:
    path = Path("docs/schemas/worksheet_answers.json")
    assert path.exists(), "worksheet_answers.json should exist"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("title") == "Worksheet Answers"

