# Polish Prompt Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A gated "Prompt Lab" debug menu where prompt variants for the polish feature run against snapshots of real resume blocks, get auto-scored, and are compared side by side — per `specs/polish-prompt-lab.md`.

**Architecture:** The shipped polish prompt moves from an inline string in `backend/api/app.py` to `backend/prompts/polish/default.txt`, resolved per-category by a small loader. A `PromptLabService` stores corpora/variants/experiments as JSON under `data_root/prompt_lab/` (gitignored via `artifacts/`; real instances point data_root outside the repo). Experiments run **one cell (variant × block) per HTTP request** so no request outlives Cloudflare's ~100 s limit; the frontend drives a worker pool with progress, reusing the Polish All patterns and diff rendering.

**Tech Stack:** FastAPI + SQLAlchemy (existing), JSON-file storage (no DB migrations), vanilla JS frontend, pytest.

## Global Constraints

- Branch: `feat/prompt-lab` in `/opt/job-ace/worktrees/job-resume-pairing` (spec already committed there). Venv: `.venv/bin/python`.
- The repo is public: **no real resume text may be committed**. All lab data lives under `settings.data_root / "prompt_lab"`.
- New setting `debug_menu: bool = False`, env `JOB_ACE_DEBUG_MENU`. `GET /prompt-lab/status` always answers; **every other** `/prompt-lab/*` route returns 404 when the tunable is off.
- The polish endpoint's rendered prompt must be byte-identical to the current inline string for the same block.
- Prompt templates use literal-token replacement (`{block_text}`, `{category}`) via `str.replace`, NOT `str.format` (resume text may contain braces).
- Module-level `settings = get_settings()` pattern (like `resume_store.py`); tests patch `backend.services.prompt_lab.settings` etc. via `tests/conftest.py`'s `patched_settings`.
- Frontend: all server strings through `esc()`; asset links bumped to `?v=20260710-6`.
- Run the full suite (`.venv/bin/python -m pytest tests/ -q`) before each commit; never run against a live DB (tests use in-memory SQLite + patched settings).

---

### Task 1: debug_menu tunable, prompt files, prompt_store loader, polish endpoint switch

**Files:**
- Modify: `backend/config.py` (add `debug_menu` field)
- Create: `backend/prompts/__init__.py` (empty), `backend/prompts/polish/default.txt`
- Create: `backend/services/prompt_store.py`
- Modify: `backend/api/app.py` (polish_block uses the loader; the inline prompt string is deleted)
- Test: `tests/test_prompt_store.py`

**Interfaces:**
- Produces: `prompt_store.load_polish_template(category: str | None) -> str` (raw template), `prompt_store.render_polish_prompt(block_text: str, category: str | None) -> str` (placeholders substituted), `prompt_store.shipped_prompt_text() -> str` (default.txt raw content, for the lab's baseline), `prompt_store.PROMPT_DIR: Path`.
- Consumes: nothing new.

- [ ] **Step 1: Add the tunable to Settings**

In `backend/config.py`, after `llm_temperature: float = 0.3` add:

```python
    # Debug/tuning surfaces (Prompt Lab). Off everywhere except staging.
    debug_menu: bool = False
```

- [ ] **Step 2: Create the shipped prompt file**

Create `backend/prompts/__init__.py` empty. Create `backend/prompts/polish/default.txt` with EXACTLY the current inline prompt from `backend/api/app.py` (the f-string body at `polish_block`), with `{block.text}` replaced by `{block_text}`:

```text
You are polishing a single WORK EXPERIENCE entry from a resume.

Your job is to improve clarity, readability, grammar, and professional presentation while preserving all factual meaning.

GOAL:
Rewrite this work experience entry so it is:
- cleaner
- tighter
- easier to read
- more consistent
- more professional

NON-NEGOTIABLE RULES:
1. DO NOT invent facts.
2. DO NOT add metrics, percentages, time savings, business impact, scale, or outcomes unless explicitly stated in the source text.
3. DO NOT add tools, technologies, responsibilities, certifications, or achievements not present in the source text.
4. DO NOT change job title, company name, or date range.
5. DO NOT strengthen claims beyond what the source text supports.
6. DO NOT remove important technical specificity.
7. DO NOT rewrite the experience to sound more senior, strategic, or leadership-oriented unless the source explicitly supports that.
8. Preserve the original meaning of every bullet.

ALLOWED CHANGES:
- Fix grammar, punctuation, and awkward phrasing
- Tighten sentence structure
- Improve bullet consistency and parallelism
- Replace weak or repetitive wording with stronger accurate wording
- Break overly long bullets for readability
- Merge redundant bullets only if no meaning is lost
- Improve formatting and readability of the section

STYLE RULES:
- Keep the original structure: header + bullet list
- Keep approximately the same number of bullets unless combining duplicates improves clarity
- Use concise, professional, credible language
- Prefer clear and specific wording over generic corporate language
- Avoid filler like "results-driven," "dynamic," "passionate," or "team player"
- Avoid keyword stuffing
- Avoid exaggerated language

OUTPUT REQUIREMENTS:
Return only the polished work experience entry.
Preserve this format:
- First line: Job Title, Company, Date Range
- Then bullet points
No commentary.
No explanations.
No notes.
No markdown fences.

SOURCE WORK EXPERIENCE ENTRY:
{block_text}
```

IMPORTANT: verify against the live file — open `backend/api/app.py`, find `def polish_block`, and copy the prompt body verbatim (the plan text above must match; if the file differs, the file wins). The file must NOT end with a trailing newline beyond the template's final line (`{block_text}` is the last line; a single trailing `\n` from the editor is fine because `render` strips nothing — see byte-identity test).

- [ ] **Step 3: Write the failing tests**

Create `tests/test_prompt_store.py`:

```python
"""Tests for the polish prompt file loader."""
from pathlib import Path

from backend.services import prompt_store


def test_default_template_loads():
    tpl = prompt_store.load_polish_template(None)
    assert "{block_text}" in tpl
    assert "NON-NEGOTIABLE RULES" in tpl


def test_category_file_wins_over_default(tmp_path, monkeypatch):
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


def test_shipped_prompt_text_is_raw_template():
    raw = prompt_store.shipped_prompt_text()
    assert "{block_text}" in raw
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_prompt_store.py -v`
Expected: FAIL / ERROR with `ModuleNotFoundError: backend.services.prompt_store`

- [ ] **Step 5: Implement the loader**

Create `backend/services/prompt_store.py`:

```python
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
```

- [ ] **Step 6: Switch the polish endpoint to the loader**

In `backend/api/app.py`, in `def polish_block`, delete the entire `prompt = f"""You are polishing ... {block.text}"""` statement and replace with:

```python
    from backend.services.prompt_store import render_polish_prompt
    prompt = render_polish_prompt(block.text, block.category)
```

(The `.strip()` handling, LLM call, and response model stay untouched.)

- [ ] **Step 7: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass (existing polish tests confirm no behavior change; if any test asserted on the inline prompt string, update it to use `prompt_store.render_polish_prompt`).

- [ ] **Step 8: Commit**

```bash
git add backend/config.py backend/prompts backend/services/prompt_store.py backend/api/app.py tests/test_prompt_store.py
git commit -m "feat: polish prompt moves to versioned files with per-category loader"
```

---

### Task 2: auto-scorers module

**Files:**
- Create: `backend/services/polish_scorers.py`
- Test: `tests/test_polish_scorers.py`

**Interfaces:**
- Produces:
  - `FILLER_WORDS: list[str]`
  - `filler_count(text: str) -> int`
  - `length_delta(original: str, polished: str) -> float` (fraction, e.g. `-0.25` = 25 % shorter; `0.0` when original empty)
  - `structure_score(original: str, polished: str) -> dict` with keys `bullets_original: int`, `bullets_polished: int`, `bullets_preserved: bool` (within ±1), `header_preserved: bool`
  - `fabrication_check(checker, polished: str, source_block: dict) -> dict` with keys `ok: bool | None`, `fabrications: list`, `notes: str` (`ok=None` means the checker errored)
  - `score_output(original: str, polished: str, source_block: dict, checker) -> dict` — all four combined: `{"fabrication": {...}, "filler_count": int, "length_delta": float, "structure": {...}}`
- Consumes: `checker` is any callable `(resume_text: str, source_blocks: list[dict], job_context: dict | None) -> ComplianceCheck` — production passes `llm_client.check_compliance`, tests pass a stub.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_polish_scorers.py`:

```python
"""Tests for the Prompt Lab auto-scorers."""
from types import SimpleNamespace

from backend.services import polish_scorers as ps


def test_filler_count_case_insensitive():
    text = "Results-Driven dynamic professional. A real team player, very dynamic."
    assert ps.filler_count(text) == 4  # results-driven, dynamic x2, team player


def test_filler_count_zero_on_clean_text():
    assert ps.filler_count("Maintained CI pipelines for 40 services.") == 0


def test_length_delta_shrink_and_growth():
    assert ps.length_delta("aaaa", "aa") == -0.5
    assert ps.length_delta("aa", "aaa") == 0.5
    assert ps.length_delta("", "anything") == 0.0


def test_structure_score_preserved():
    original = "Dev, Acme, 2020\n• built APIs\n• wrote tests"
    polished = "Dev, Acme, 2020\n• Built APIs.\n• Wrote tests."
    s = ps.structure_score(original, polished)
    assert s["bullets_original"] == 2
    assert s["bullets_polished"] == 2
    assert s["bullets_preserved"] is True
    assert s["header_preserved"] is True


def test_structure_score_gutted_bullets():
    original = "Dev, Acme, 2020\n• a\n• b\n• c\n• d"
    polished = "Dev, Acme, 2020\n• a and b and c and d"
    s = ps.structure_score(original, polished)
    assert s["bullets_preserved"] is False


def test_structure_score_lost_header():
    original = "Dev, Acme, 2020\n• built APIs"
    polished = "• built APIs better"
    s = ps.structure_score(original, polished)
    assert s["header_preserved"] is False


def test_structure_header_not_required_when_original_has_none():
    original = "• only bullets here"
    polished = "• still only bullets"
    assert ps.structure_score(original, polished)["header_preserved"] is True


def test_fabrication_check_ok():
    checker = lambda text, blocks, ctx=None: SimpleNamespace(
        ok=True, fabrications=[], notes="clean")
    r = ps.fabrication_check(checker, "polished", {"id": 1, "text": "orig"})
    assert r["ok"] is True and r["fabrications"] == []


def test_fabrication_check_flags():
    checker = lambda text, blocks, ctx=None: SimpleNamespace(
        ok=False,
        fabrications=[{"claim": "40% faster", "explanation": "not in source", "severity": "high"}],
        notes="invented metric")
    r = ps.fabrication_check(checker, "polished 40% faster", {"id": 1, "text": "orig"})
    assert r["ok"] is False
    assert r["fabrications"][0]["claim"] == "40% faster"


def test_fabrication_check_error_is_none_not_crash():
    def checker(text, blocks, ctx=None):
        raise RuntimeError("api down")
    r = ps.fabrication_check(checker, "polished", {"id": 1, "text": "orig"})
    assert r["ok"] is None
    assert "api down" in r["notes"]


def test_score_output_shape():
    checker = lambda text, blocks, ctx=None: SimpleNamespace(ok=True, fabrications=[], notes="")
    s = ps.score_output("Dev\n• a", "Dev\n• a!", {"id": 1, "text": "Dev\n• a"}, checker)
    assert set(s) == {"fabrication", "filler_count", "length_delta", "structure"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_polish_scorers.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the scorers**

Create `backend/services/polish_scorers.py`:

```python
"""Auto-scorers for Prompt Lab outputs.

Regression guards, not final judges: they rank variants and flag fabrication;
the owner's side-by-side pick is the recorded verdict.
See specs/polish-prompt-lab.md §3.
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List

FILLER_WORDS: List[str] = [
    "results-driven",
    "dynamic",
    "passionate",
    "team player",
    "go-getter",
    "self-starter",
    "detail-oriented",
    "synergy",
    "proven track record",
    "think outside the box",
]

_BULLET_RE = re.compile(r"^\s*[•\-\*]\s+")


def filler_count(text: str) -> int:
    lowered = text.lower()
    return sum(len(re.findall(re.escape(w), lowered)) for w in FILLER_WORDS)


def length_delta(original: str, polished: str) -> float:
    if not original:
        return 0.0
    return round((len(polished) - len(original)) / len(original), 4)


def _bullet_lines(text: str) -> List[str]:
    return [ln for ln in text.splitlines() if _BULLET_RE.match(ln)]


def _first_nonempty_line(text: str) -> str:
    for ln in text.splitlines():
        if ln.strip():
            return ln
    return ""


def structure_score(original: str, polished: str) -> Dict:
    bo, bp = len(_bullet_lines(original)), len(_bullet_lines(polished))
    original_has_header = bool(_first_nonempty_line(original)) and not _BULLET_RE.match(
        _first_nonempty_line(original)
    )
    polished_has_header = bool(_first_nonempty_line(polished)) and not _BULLET_RE.match(
        _first_nonempty_line(polished)
    )
    return {
        "bullets_original": bo,
        "bullets_polished": bp,
        "bullets_preserved": abs(bo - bp) <= 1,
        "header_preserved": polished_has_header if original_has_header else True,
    }


def fabrication_check(checker: Callable, polished: str, source_block: Dict) -> Dict:
    """Run the compliance checker; never raise — an errored check is ok=None."""
    try:
        result = checker(polished, [source_block], None)
        return {
            "ok": bool(result.ok),
            "fabrications": list(result.fabrications or []),
            "notes": result.notes or "",
        }
    except Exception as exc:  # scorer must not kill an experiment cell
        return {"ok": None, "fabrications": [], "notes": f"check failed: {exc}"}


def score_output(original: str, polished: str, source_block: Dict, checker: Callable) -> Dict:
    return {
        "fabrication": fabrication_check(checker, polished, source_block),
        "filler_count": filler_count(polished),
        "length_delta": length_delta(original, polished),
        "structure": structure_score(original, polished),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_polish_scorers.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add backend/services/polish_scorers.py tests/test_polish_scorers.py
git commit -m "feat: prompt-lab auto-scorers (fabrication, filler, length, structure)"
```

---

### Task 3: PromptLabService — storage, corpus snapshots, variant CRUD

**Files:**
- Create: `backend/services/prompt_lab.py`
- Modify: `tests/conftest.py` (add `prompt_lab.settings` patch to `patched_settings`)
- Test: `tests/test_prompt_lab.py`

**Interfaces:**
- Produces (class `PromptLabService(db: Session)`):
  - `is_enabled() -> bool` (module function: `settings.debug_menu`)
  - `snapshot_corpus() -> dict` — `{"id": "corpus-<n>", "created_at": iso, "blocks": [{"block_id", "category", "text", "job_title", "company"}]}`; raises `ValueError` when no blocks exist
  - `list_corpora() -> list[dict]` — `[{"id", "created_at", "block_count"}]` newest first
  - `get_corpus(corpus_id: str) -> dict | None`
  - `create_variant(name: str, base: str) -> dict` — base is `"shipped:default"` or an existing variant slug; returns `{"name": slug, "base", "prompt_text", "created_at"}`; `ValueError` on name collision or unknown base
  - `list_variants() -> list[dict]` — first entry always `{"name": "shipped:default", "prompt_text": <raw template>, "read_only": True}`, then local variants
  - `get_variant(name: str) -> dict | None` (resolves `shipped:default` too)
  - `update_variant(name: str, prompt_text: str) -> dict` — `ValueError` for `shipped:default` or unknown
  - `delete_variant(name: str) -> None` — `ValueError` for `shipped:default` or unknown
- Consumes: `prompt_store.shipped_prompt_text()`; module-level `settings = get_settings()`.
- Storage layout (all under `settings.data_root / "prompt_lab"`): `corpus/corpus-<n>.json`, `variants/<slug>.json`. Slugs: lowercase, `[a-z0-9-]`, from `python-slugify` (already a dependency — `from slugify import slugify`).

- [ ] **Step 1: Add the conftest patch**

In `tests/conftest.py`, in `patched_settings`, extend the `with patch(...)` stack:

```python
    with patch("backend.services.artifacts.settings", settings), \
         patch("backend.services.resume_store.settings", settings), \
         patch("backend.services.prompt_lab.settings", settings), \
         patch("backend.config.get_settings", return_value=settings):
        yield settings
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_prompt_lab.py`:

```python
"""Tests for PromptLabService storage, corpus, and variants."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.session import Base
from backend.models import models
from backend.services.prompt_lab import PromptLabService


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def _seed_blocks(session):
    blocks = [
        models.ResumeBlock(category="summary", text="Psych grad with care experience."),
        models.ResumeBlock(category="experience", text="Mentor, Telos, 2025\n• Supported youth.",
                           job_title="Mentor", company="Telos"),
    ]
    session.add_all(blocks)
    session.commit()
    return blocks


def test_snapshot_corpus_roundtrip(session, patched_settings):
    _seed_blocks(session)
    svc = PromptLabService(session)
    corpus = svc.snapshot_corpus()
    assert corpus["id"] == "corpus-1"
    assert len(corpus["blocks"]) == 2
    assert corpus["blocks"][1]["job_title"] == "Mentor"

    assert svc.list_corpora() == [
        {"id": "corpus-1", "created_at": corpus["created_at"], "block_count": 2}
    ]
    assert svc.get_corpus("corpus-1")["blocks"][0]["category"] == "summary"
    assert svc.get_corpus("corpus-99") is None

    corpus2 = svc.snapshot_corpus()
    assert corpus2["id"] == "corpus-2"


def test_snapshot_corpus_empty_db_raises(session, patched_settings):
    svc = PromptLabService(session)
    with pytest.raises(ValueError, match="[Nn]o resume blocks"):
        svc.snapshot_corpus()


def test_variant_crud(session, patched_settings):
    svc = PromptLabService(session)

    v = svc.create_variant("Punchier Verbs", base="shipped:default")
    assert v["name"] == "punchier-verbs"
    assert "{block_text}" in v["prompt_text"]
    assert v["base"] == "shipped:default"

    listed = svc.list_variants()
    assert listed[0]["name"] == "shipped:default"
    assert listed[0]["read_only"] is True
    assert any(x["name"] == "punchier-verbs" for x in listed)

    updated = svc.update_variant("punchier-verbs", "NEW {block_text}")
    assert updated["prompt_text"] == "NEW {block_text}"

    clone = svc.create_variant("clone of punchy", base="punchier-verbs")
    assert clone["prompt_text"] == "NEW {block_text}"

    svc.delete_variant("punchier-verbs")
    assert svc.get_variant("punchier-verbs") is None
    assert svc.get_variant("shipped:default")["read_only"] is True


def test_variant_name_collision_and_guards(session, patched_settings):
    svc = PromptLabService(session)
    svc.create_variant("Alpha", base="shipped:default")
    with pytest.raises(ValueError, match="exists"):
        svc.create_variant("alpha", base="shipped:default")
    with pytest.raises(ValueError, match="read-only"):
        svc.update_variant("shipped:default", "nope")
    with pytest.raises(ValueError, match="read-only"):
        svc.delete_variant("shipped:default")
    with pytest.raises(ValueError, match="not found"):
        svc.update_variant("ghost", "x")
    with pytest.raises(ValueError, match="Unknown base"):
        svc.create_variant("Beta", base="ghost")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_prompt_lab.py -v`
Expected: FAIL with `ModuleNotFoundError: backend.services.prompt_lab`

- [ ] **Step 4: Implement the service (storage + corpus + variants)**

Create `backend/services/prompt_lab.py`:

```python
"""Prompt Lab: tuning/scoring pipeline for the polish prompt.

Stores corpora, variants, and experiments as JSON under
data_root/prompt_lab/ (gitignored — the repo is public and corpora contain
real resume text). See specs/polish-prompt-lab.md.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from slugify import slugify
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.models import models
from backend.services import polish_scorers
from backend.services.prompt_store import render_template, shipped_prompt_text

settings = get_settings()

SHIPPED_BASELINE = "shipped:default"


def is_enabled() -> bool:
    return bool(settings.debug_menu)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PromptLabService:
    def __init__(self, db: Session):
        self.db = db

    # -- storage helpers ------------------------------------------------

    @property
    def root(self) -> Path:
        return settings.data_root / "prompt_lab"

    def _dir(self, name: str) -> Path:
        d = self.root / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _next_numbered_id(self, dirname: str, prefix: str) -> str:
        pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)\.json$")
        highest = 0
        for f in self._dir(dirname).iterdir():
            m = pattern.match(f.name)
            if m:
                highest = max(highest, int(m.group(1)))
        return f"{prefix}-{highest + 1}"

    @staticmethod
    def _read(path: Path) -> Optional[Dict]:
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write(path: Path, payload: Dict) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # -- corpus ----------------------------------------------------------

    def snapshot_corpus(self) -> Dict:
        blocks = self.db.scalars(
            select(models.ResumeBlock).order_by(models.ResumeBlock.id)
        ).all()
        if not blocks:
            raise ValueError("No resume blocks to snapshot")
        corpus_id = self._next_numbered_id("corpus", "corpus")
        payload = {
            "id": corpus_id,
            "created_at": _now(),
            "blocks": [
                {
                    "block_id": b.id,
                    "category": b.category,
                    "text": b.text,
                    "job_title": b.job_title,
                    "company": b.company,
                }
                for b in blocks
            ],
        }
        self._write(self._dir("corpus") / f"{corpus_id}.json", payload)
        return payload

    def list_corpora(self) -> List[Dict]:
        out = []
        for f in sorted(self._dir("corpus").glob("corpus-*.json")):
            data = self._read(f)
            if data:
                out.append(
                    {
                        "id": data["id"],
                        "created_at": data["created_at"],
                        "block_count": len(data["blocks"]),
                    }
                )
        out.sort(key=lambda c: int(c["id"].split("-")[1]), reverse=True)
        return out

    def get_corpus(self, corpus_id: str) -> Optional[Dict]:
        return self._read(self._dir("corpus") / f"{corpus_id}.json")

    # -- variants ---------------------------------------------------------

    def create_variant(self, name: str, base: str) -> Dict:
        slug = slugify(name)
        if not slug:
            raise ValueError("Variant name produces an empty slug")
        path = self._dir("variants") / f"{slug}.json"
        if path.exists():
            raise ValueError(f"Variant '{slug}' already exists")
        base_variant = self.get_variant(base)
        if base_variant is None:
            raise ValueError(f"Unknown base variant: {base}")
        payload = {
            "name": slug,
            "base": base,
            "prompt_text": base_variant["prompt_text"],
            "created_at": _now(),
        }
        self._write(path, payload)
        return payload

    def list_variants(self) -> List[Dict]:
        out: List[Dict] = [
            {
                "name": SHIPPED_BASELINE,
                "prompt_text": shipped_prompt_text(),
                "read_only": True,
            }
        ]
        for f in sorted(self._dir("variants").glob("*.json")):
            data = self._read(f)
            if data:
                data["read_only"] = False
                out.append(data)
        return out

    def get_variant(self, name: str) -> Optional[Dict]:
        if name == SHIPPED_BASELINE:
            return {
                "name": SHIPPED_BASELINE,
                "prompt_text": shipped_prompt_text(),
                "read_only": True,
            }
        return self._read(self._dir("variants") / f"{slugify(name)}.json")

    def update_variant(self, name: str, prompt_text: str) -> Dict:
        if name == SHIPPED_BASELINE:
            raise ValueError("The shipped baseline is read-only")
        path = self._dir("variants") / f"{slugify(name)}.json"
        data = self._read(path)
        if data is None:
            raise ValueError(f"Variant not found: {name}")
        data["prompt_text"] = prompt_text
        self._write(path, data)
        return data

    def delete_variant(self, name: str) -> None:
        if name == SHIPPED_BASELINE:
            raise ValueError("The shipped baseline is read-only")
        path = self._dir("variants") / f"{slugify(name)}.json"
        if not path.is_file():
            raise ValueError(f"Variant not found: {name}")
        path.unlink()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_prompt_lab.py -v`
Expected: PASS (all)

- [ ] **Step 6: Run the full suite and commit**

Run: `.venv/bin/python -m pytest tests/ -q` — expected: all pass.

```bash
git add backend/services/prompt_lab.py tests/test_prompt_lab.py tests/conftest.py
git commit -m "feat: PromptLabService storage — corpus snapshots and variant CRUD"
```

---

### Task 4: PromptLabService — experiments, cell runs, picks, rollups

**Files:**
- Modify: `backend/services/prompt_lab.py` (extend class)
- Test: `tests/test_prompt_lab.py` (extend)

**Interfaces:**
- Produces (on `PromptLabService`):
  - `create_experiment(variant_names: list[str], corpus_id: str) -> dict` — validates ≥2 variants, all exist, corpus exists; returns `{"id": "exp-<n>", "created_at", "variants": [...], "corpus_id", "cells": [{"variant", "block_id", "status": "pending"}], "results": {}, "picks": {}}`; results/picks keyed `"<variant>::<block_id>"` and `"<block_id>"` respectively
  - `run_cell(exp_id: str, variant: str, block_id: int, llm_runner=None, checker=None) -> dict` — runs one variant × block, scores it, persists into the experiment file, returns the cell: `{"variant", "block_id", "output": str|None, "error": str|None, "scores": dict|None}`; `ValueError` on unknown experiment/variant/block
  - `record_pick(exp_id: str, block_id: int, variant: str) -> dict` — persists `picks[str(block_id)] = variant`, returns updated picks
  - `get_experiment(exp_id: str) -> dict | None` — the stored file plus computed `"rollups": {variant: {"cells_run", "errors", "fabrication_failures", "fabrication_unchecked", "mean_filler", "mean_abs_length_delta", "structure_breaks", "picks"}}`
  - `list_experiments() -> list[dict]` — `[{"id", "created_at", "variants", "corpus_id", "cells_total", "cells_run"}]` newest first
- Consumes: `polish_scorers.score_output`, `prompt_store.render_template`, `models.ResumeBlock` via corpus file (not DB — cells run against the snapshot).
- `llm_runner` default: build once per call from `get_llm_client(settings, task="tailoring")`; if `OpenAIClient`, `chat.completions.create(model=..., messages=[{"role":"user","content":prompt}], temperature=0.3, max_tokens=2000)` → content; otherwise return the block text unchanged (stub behavior, mirrors the polish endpoint). `checker` default: that client's `check_compliance`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_prompt_lab.py`:

```python
# --- experiments ---

def _lab_with_corpus_and_variants(session):
    _seed_blocks(session)
    svc = PromptLabService(session)
    corpus = svc.snapshot_corpus()
    svc.create_variant("Variant A", base="shipped:default")
    svc.update_variant("variant-a", "A PROMPT {block_text}")
    svc.create_variant("Variant B", base="shipped:default")
    svc.update_variant("variant-b", "B PROMPT {block_text}")
    return svc, corpus


def _fake_runner(prompt):
    return f"POLISHED[{prompt[:8]}]"


def _ok_checker(text, blocks, ctx=None):
    from types import SimpleNamespace
    return SimpleNamespace(ok=True, fabrications=[], notes="")


def test_create_experiment_shape(session, patched_settings):
    svc, corpus = _lab_with_corpus_and_variants(session)
    exp = svc.create_experiment(["variant-a", "variant-b"], corpus["id"])
    assert exp["id"] == "exp-1"
    assert len(exp["cells"]) == 4  # 2 variants x 2 blocks
    assert all(c["status"] == "pending" for c in exp["cells"])


def test_create_experiment_validation(session, patched_settings):
    svc, corpus = _lab_with_corpus_and_variants(session)
    with pytest.raises(ValueError, match="at least two"):
        svc.create_experiment(["variant-a"], corpus["id"])
    with pytest.raises(ValueError, match="Unknown variant"):
        svc.create_experiment(["variant-a", "ghost"], corpus["id"])
    with pytest.raises(ValueError, match="Corpus not found"):
        svc.create_experiment(["variant-a", "variant-b"], "corpus-99")


def test_run_cell_stores_output_and_scores(session, patched_settings):
    svc, corpus = _lab_with_corpus_and_variants(session)
    exp = svc.create_experiment(["variant-a", "variant-b"], corpus["id"])
    block_id = corpus["blocks"][0]["block_id"]

    cell = svc.run_cell(exp["id"], "variant-a", block_id,
                        llm_runner=_fake_runner, checker=_ok_checker)
    assert cell["output"] == "POLISHED[A PROMPT ]"
    assert cell["error"] is None
    assert cell["scores"]["fabrication"]["ok"] is True

    stored = svc.get_experiment(exp["id"])
    key = f"variant-a::{block_id}"
    assert stored["results"][key]["output"] == cell["output"]


def test_run_cell_llm_failure_recorded_not_raised(session, patched_settings):
    svc, corpus = _lab_with_corpus_and_variants(session)
    exp = svc.create_experiment(["variant-a", "variant-b"], corpus["id"])
    block_id = corpus["blocks"][0]["block_id"]

    def boom(prompt):
        raise RuntimeError("rate limited")

    cell = svc.run_cell(exp["id"], "variant-a", block_id,
                        llm_runner=boom, checker=_ok_checker)
    assert cell["output"] is None
    assert "rate limited" in cell["error"]
    assert cell["scores"] is None


def test_picks_and_rollups(session, patched_settings):
    svc, corpus = _lab_with_corpus_and_variants(session)
    exp = svc.create_experiment(["variant-a", "variant-b"], corpus["id"])
    for c in exp["cells"]:
        svc.run_cell(exp["id"], c["variant"], c["block_id"],
                     llm_runner=_fake_runner, checker=_ok_checker)

    b0 = corpus["blocks"][0]["block_id"]
    b1 = corpus["blocks"][1]["block_id"]
    svc.record_pick(exp["id"], b0, "variant-a")
    svc.record_pick(exp["id"], b1, "variant-a")

    got = svc.get_experiment(exp["id"])
    ra = got["rollups"]["variant-a"]
    assert ra["cells_run"] == 2
    assert ra["errors"] == 0
    assert ra["fabrication_failures"] == 0
    assert ra["picks"] == 2
    assert got["rollups"]["variant-b"]["picks"] == 0


def test_record_pick_validation(session, patched_settings):
    svc, corpus = _lab_with_corpus_and_variants(session)
    exp = svc.create_experiment(["variant-a", "variant-b"], corpus["id"])
    with pytest.raises(ValueError, match="not part of"):
        svc.record_pick(exp["id"], corpus["blocks"][0]["block_id"], "ghost")
    with pytest.raises(ValueError, match="Experiment not found"):
        svc.record_pick("exp-99", 1, "variant-a")


def test_list_experiments(session, patched_settings):
    svc, corpus = _lab_with_corpus_and_variants(session)
    exp = svc.create_experiment(["variant-a", "variant-b"], corpus["id"])
    svc.run_cell(exp["id"], "variant-a", corpus["blocks"][0]["block_id"],
                 llm_runner=_fake_runner, checker=_ok_checker)
    listed = svc.list_experiments()
    assert listed[0]["id"] == exp["id"]
    assert listed[0]["cells_total"] == 4
    assert listed[0]["cells_run"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_prompt_lab.py -v -k experiment or pick or list_exp`
Expected: FAIL with `AttributeError: ... has no attribute 'create_experiment'`

- [ ] **Step 3: Implement experiments on the service**

Append to `backend/services/prompt_lab.py` (inside `PromptLabService`):

```python
    # -- experiments -------------------------------------------------------

    def create_experiment(self, variant_names: List[str], corpus_id: str) -> Dict:
        if len(variant_names) < 2:
            raise ValueError("An experiment needs at least two variants")
        for name in variant_names:
            if self.get_variant(name) is None:
                raise ValueError(f"Unknown variant: {name}")
        corpus = self.get_corpus(corpus_id)
        if corpus is None:
            raise ValueError(f"Corpus not found: {corpus_id}")

        exp_id = self._next_numbered_id("experiments", "exp")
        payload = {
            "id": exp_id,
            "created_at": _now(),
            "variants": list(variant_names),
            "corpus_id": corpus_id,
            "cells": [
                {"variant": v, "block_id": b["block_id"], "status": "pending"}
                for v in variant_names
                for b in corpus["blocks"]
            ],
            "results": {},
            "picks": {},
        }
        self._write(self._dir("experiments") / f"{exp_id}.json", payload)
        return payload

    def _default_llm(self):
        from backend.services.llm import OpenAIClient, get_llm_client

        client = get_llm_client(settings, task="tailoring")

        def runner(prompt: str) -> str:
            if isinstance(client, OpenAIClient):
                response = client.client.chat.completions.create(
                    model=client.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=2000,
                )
                return (response.choices[0].message.content or "").strip()
            # Stub provider mirrors the polish endpoint: no rewrite.
            marker = "SOURCE WORK EXPERIENCE ENTRY:\n"
            return prompt.split(marker, 1)[-1] if marker in prompt else prompt

        return runner, client.check_compliance

    def run_cell(
        self,
        exp_id: str,
        variant: str,
        block_id: int,
        llm_runner=None,
        checker=None,
    ) -> Dict:
        path = self._dir("experiments") / f"{exp_id}.json"
        exp = self._read(path)
        if exp is None:
            raise ValueError(f"Experiment not found: {exp_id}")
        if variant not in exp["variants"]:
            raise ValueError(f"Variant {variant} is not part of {exp_id}")
        corpus = self.get_corpus(exp["corpus_id"])
        block = next(
            (b for b in corpus["blocks"] if b["block_id"] == block_id), None
        )
        if block is None:
            raise ValueError(f"Block {block_id} is not in corpus {exp['corpus_id']}")

        if llm_runner is None or checker is None:
            default_runner, default_checker = self._default_llm()
            llm_runner = llm_runner or default_runner
            checker = checker or default_checker

        variant_data = self.get_variant(variant)
        prompt = render_template(
            variant_data["prompt_text"], block["text"], block.get("category")
        )

        cell: Dict = {"variant": variant, "block_id": block_id}
        try:
            output = llm_runner(prompt)
            cell["output"] = output
            cell["error"] = None
            cell["scores"] = polish_scorers.score_output(
                block["text"], output, block, checker
            )
        except Exception as exc:
            cell["output"] = None
            cell["error"] = str(exc)
            cell["scores"] = None

        exp["results"][f"{variant}::{block_id}"] = cell
        for c in exp["cells"]:
            if c["variant"] == variant and c["block_id"] == block_id:
                c["status"] = "error" if cell["error"] else "done"
        self._write(path, exp)
        return cell

    def record_pick(self, exp_id: str, block_id: int, variant: str) -> Dict:
        path = self._dir("experiments") / f"{exp_id}.json"
        exp = self._read(path)
        if exp is None:
            raise ValueError(f"Experiment not found: {exp_id}")
        if variant not in exp["variants"]:
            raise ValueError(f"Variant {variant} is not part of {exp_id}")
        exp["picks"][str(block_id)] = variant
        self._write(path, exp)
        return exp["picks"]

    def get_experiment(self, exp_id: str) -> Optional[Dict]:
        exp = self._read(self._dir("experiments") / f"{exp_id}.json")
        if exp is None:
            return None
        exp["rollups"] = self._rollups(exp)
        return exp

    def list_experiments(self) -> List[Dict]:
        out = []
        for f in sorted(self._dir("experiments").glob("exp-*.json")):
            e = self._read(f)
            if e:
                out.append(
                    {
                        "id": e["id"],
                        "created_at": e["created_at"],
                        "variants": e["variants"],
                        "corpus_id": e["corpus_id"],
                        "cells_total": len(e["cells"]),
                        "cells_run": sum(
                            1 for c in e["cells"] if c["status"] != "pending"
                        ),
                    }
                )
        out.sort(key=lambda e: int(e["id"].split("-")[1]), reverse=True)
        return out

    @staticmethod
    def _rollups(exp: Dict) -> Dict:
        rollups: Dict = {}
        for v in exp["variants"]:
            cells = [
                c for k, c in exp["results"].items() if k.startswith(f"{v}::")
            ]
            scored = [c for c in cells if c.get("scores")]
            fillers = [c["scores"]["filler_count"] for c in scored]
            deltas = [abs(c["scores"]["length_delta"]) for c in scored]
            rollups[v] = {
                "cells_run": len(cells),
                "errors": sum(1 for c in cells if c.get("error")),
                "fabrication_failures": sum(
                    1 for c in scored if c["scores"]["fabrication"]["ok"] is False
                ),
                "fabrication_unchecked": sum(
                    1 for c in scored if c["scores"]["fabrication"]["ok"] is None
                ),
                "mean_filler": round(sum(fillers) / len(fillers), 2) if fillers else 0,
                "mean_abs_length_delta": round(sum(deltas) / len(deltas), 3)
                if deltas
                else 0,
                "structure_breaks": sum(
                    1
                    for c in scored
                    if not c["scores"]["structure"]["bullets_preserved"]
                    or not c["scores"]["structure"]["header_preserved"]
                ),
                "picks": sum(1 for p in exp["picks"].values() if p == v),
            }
        return rollups
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_prompt_lab.py -v`
Expected: PASS (all, including Task 3's)

- [ ] **Step 5: Full suite + commit**

Run: `.venv/bin/python -m pytest tests/ -q` — expected: all pass.

```bash
git add backend/services/prompt_lab.py tests/test_prompt_lab.py
git commit -m "feat: prompt-lab experiments — per-cell runs, scoring, picks, rollups"
```

---

### Task 5: gated /prompt-lab/* API routes

**Files:**
- Modify: `backend/api/app.py` (routes, placed after the `/uploaded-resumes` endpoints)
- Modify: `backend/models/schemas.py` (request models)
- Test: `tests/test_api.py` (append)

**Interfaces:**
- Produces routes (all JSON):
  - `GET /prompt-lab/status` → `{"enabled": bool}` — ALWAYS answers, even when disabled
  - `POST /prompt-lab/corpus` → snapshot (400 on empty DB); `GET /prompt-lab/corpus` → list; `GET /prompt-lab/corpus/{corpus_id}` → full corpus or 404
  - `GET /prompt-lab/variants`; `POST /prompt-lab/variants` body `{"name", "base"}` (409 on collision, 400 on unknown base); `PUT /prompt-lab/variants/{name}` body `{"prompt_text"}` (400 read-only, 404 unknown); `DELETE /prompt-lab/variants/{name}` (400 read-only, 404 unknown)
  - `POST /prompt-lab/experiments` body `{"variant_names": [...], "corpus_id"}` (400 on validation errors); `GET /prompt-lab/experiments`; `GET /prompt-lab/experiments/{exp_id}` (404 unknown)
  - `POST /prompt-lab/experiments/{exp_id}/cells` body `{"variant", "block_id"}` → runs ONE cell (400 on validation errors)
  - `POST /prompt-lab/experiments/{exp_id}/picks` body `{"block_id", "variant"}` → `{"picks": {...}}`
  - Gate: every route except `/status` starts with `_require_prompt_lab()` which raises 404 `"Not found"` when `prompt_lab.is_enabled()` is false.
- Consumes: Task 3/4 service methods, exact signatures as defined there.

- [ ] **Step 1: Add request schemas**

In `backend/models/schemas.py`, append:

```python
class PromptLabVariantCreate(BaseModel):
    """Create a Prompt Lab variant by cloning a base."""
    name: str
    base: str = "shipped:default"


class PromptLabVariantUpdate(BaseModel):
    prompt_text: str


class PromptLabExperimentCreate(BaseModel):
    variant_names: List[str]
    corpus_id: str


class PromptLabCellRun(BaseModel):
    variant: str
    block_id: int


class PromptLabPick(BaseModel):
    block_id: int
    variant: str
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_api.py`:

```python
# --- Prompt Lab ---

from unittest.mock import patch as _patch


def _enable_lab():
    from backend.services import prompt_lab
    return _patch.object(prompt_lab.settings, "debug_menu", True)


def test_prompt_lab_status_reflects_tunable(client, patched_settings):
    resp = client.get("/prompt-lab/status")
    assert resp.status_code == 200
    assert resp.json() == {"enabled": False}
    with _enable_lab():
        assert client.get("/prompt-lab/status").json() == {"enabled": True}


def test_prompt_lab_routes_404_when_disabled(client, patched_settings):
    assert client.get("/prompt-lab/variants").status_code == 404
    assert client.post("/prompt-lab/corpus").status_code == 404
    assert client.get("/prompt-lab/experiments").status_code == 404


def test_prompt_lab_corpus_endpoints(client, api_session, patched_settings):
    api_session.add(models.ResumeBlock(category="summary", text="Real text."))
    api_session.commit()
    with _enable_lab():
        resp = client.post("/prompt-lab/corpus")
        assert resp.status_code == 201
        corpus_id = resp.json()["id"]
        assert client.get("/prompt-lab/corpus").json()[0]["id"] == corpus_id
        assert client.get(f"/prompt-lab/corpus/{corpus_id}").status_code == 200
        assert client.get("/prompt-lab/corpus/corpus-99").status_code == 404


def test_prompt_lab_corpus_empty_400(client, patched_settings):
    with _enable_lab():
        resp = client.post("/prompt-lab/corpus")
        assert resp.status_code == 400
        assert "No resume blocks" in resp.json()["detail"]


def test_prompt_lab_variant_endpoints(client, patched_settings):
    with _enable_lab():
        resp = client.post("/prompt-lab/variants",
                           json={"name": "Test One", "base": "shipped:default"})
        assert resp.status_code == 201
        assert resp.json()["name"] == "test-one"

        dup = client.post("/prompt-lab/variants",
                          json={"name": "test one", "base": "shipped:default"})
        assert dup.status_code == 409

        upd = client.put("/prompt-lab/variants/test-one",
                         json={"prompt_text": "X {block_text}"})
        assert upd.status_code == 200
        assert upd.json()["prompt_text"] == "X {block_text}"

        ro = client.put("/prompt-lab/variants/shipped:default",
                        json={"prompt_text": "nope"})
        assert ro.status_code == 400

        names = [v["name"] for v in client.get("/prompt-lab/variants").json()]
        assert names[0] == "shipped:default" and "test-one" in names

        assert client.delete("/prompt-lab/variants/test-one").status_code == 204
        assert client.delete("/prompt-lab/variants/ghost").status_code == 404


def test_prompt_lab_experiment_flow(client, api_session, patched_settings):
    api_session.add(models.ResumeBlock(category="summary", text="Real text."))
    api_session.commit()
    with _enable_lab():
        client.post("/prompt-lab/variants", json={"name": "A", "base": "shipped:default"})
        client.post("/prompt-lab/variants", json={"name": "B", "base": "shipped:default"})
        corpus_id = client.post("/prompt-lab/corpus").json()["id"]

        resp = client.post("/prompt-lab/experiments",
                           json={"variant_names": ["a", "b"], "corpus_id": corpus_id})
        assert resp.status_code == 201
        exp = resp.json()
        assert len(exp["cells"]) == 2

        bad = client.post("/prompt-lab/experiments",
                          json={"variant_names": ["a"], "corpus_id": corpus_id})
        assert bad.status_code == 400

        cell_req = {"variant": "a", "block_id": exp["cells"][0]["block_id"]}
        with _patch("backend.services.prompt_lab.PromptLabService._default_llm",
                    return_value=(lambda p: "POLISHED", 
                                  lambda t, b, c=None: __import__("types").SimpleNamespace(
                                      ok=True, fabrications=[], notes=""))):
            run = client.post(f"/prompt-lab/experiments/{exp['id']}/cells", json=cell_req)
        assert run.status_code == 200
        assert run.json()["output"] == "POLISHED"

        pick = client.post(f"/prompt-lab/experiments/{exp['id']}/picks",
                           json={"block_id": cell_req["block_id"], "variant": "a"})
        assert pick.status_code == 200

        got = client.get(f"/prompt-lab/experiments/{exp['id']}")
        assert got.status_code == 200
        assert got.json()["rollups"]["a"]["picks"] == 1
        assert client.get("/prompt-lab/experiments/exp-99").status_code == 404
        assert client.get("/prompt-lab/experiments").json()[0]["id"] == exp["id"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_api.py -v -k prompt_lab`
Expected: FAIL — 404s everywhere (routes don't exist), status test fails first

- [ ] **Step 4: Implement the routes**

In `backend/api/app.py`: add imports `from backend.services import prompt_lab as prompt_lab_module`, `from backend.services.prompt_lab import PromptLabService`, and the new schemas (`PromptLabVariantCreate, PromptLabVariantUpdate, PromptLabExperimentCreate, PromptLabCellRun, PromptLabPick`) to the schemas import block. After the `/uploaded-resumes/{upload_id}/download` route add:

```python
# --- Prompt Lab (debug tunable; see specs/polish-prompt-lab.md) ---


def _require_prompt_lab() -> None:
    if not prompt_lab_module.is_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


@app.get("/prompt-lab/status")
def prompt_lab_status() -> dict:
    """Always answers — the frontend uses this to decide whether to show the lab."""
    return {"enabled": prompt_lab_module.is_enabled()}


@app.post("/prompt-lab/corpus", status_code=status.HTTP_201_CREATED)
def prompt_lab_snapshot_corpus(db: Session = Depends(get_db)) -> dict:
    _require_prompt_lab()
    try:
        return PromptLabService(db).snapshot_corpus()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/prompt-lab/corpus")
def prompt_lab_list_corpora(db: Session = Depends(get_db)) -> list[dict]:
    _require_prompt_lab()
    return PromptLabService(db).list_corpora()


@app.get("/prompt-lab/corpus/{corpus_id}")
def prompt_lab_get_corpus(corpus_id: str, db: Session = Depends(get_db)) -> dict:
    _require_prompt_lab()
    corpus = PromptLabService(db).get_corpus(corpus_id)
    if corpus is None:
        raise HTTPException(status_code=404, detail=f"Corpus not found: {corpus_id}")
    return corpus


@app.get("/prompt-lab/variants")
def prompt_lab_list_variants(db: Session = Depends(get_db)) -> list[dict]:
    _require_prompt_lab()
    return PromptLabService(db).list_variants()


@app.post("/prompt-lab/variants", status_code=status.HTTP_201_CREATED)
def prompt_lab_create_variant(
    payload: PromptLabVariantCreate, db: Session = Depends(get_db)
) -> dict:
    _require_prompt_lab()
    try:
        return PromptLabService(db).create_variant(payload.name, payload.base)
    except ValueError as exc:
        code = 409 if "already exists" in str(exc) else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@app.put("/prompt-lab/variants/{name}")
def prompt_lab_update_variant(
    name: str, payload: PromptLabVariantUpdate, db: Session = Depends(get_db)
) -> dict:
    _require_prompt_lab()
    try:
        return PromptLabService(db).update_variant(name, payload.prompt_text)
    except ValueError as exc:
        code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@app.delete("/prompt-lab/variants/{name}", status_code=status.HTTP_204_NO_CONTENT)
def prompt_lab_delete_variant(name: str, db: Session = Depends(get_db)) -> None:
    _require_prompt_lab()
    try:
        PromptLabService(db).delete_variant(name)
    except ValueError as exc:
        code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@app.post("/prompt-lab/experiments", status_code=status.HTTP_201_CREATED)
def prompt_lab_create_experiment(
    payload: PromptLabExperimentCreate, db: Session = Depends(get_db)
) -> dict:
    _require_prompt_lab()
    try:
        return PromptLabService(db).create_experiment(
            payload.variant_names, payload.corpus_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/prompt-lab/experiments")
def prompt_lab_list_experiments(db: Session = Depends(get_db)) -> list[dict]:
    _require_prompt_lab()
    return PromptLabService(db).list_experiments()


@app.get("/prompt-lab/experiments/{exp_id}")
def prompt_lab_get_experiment(exp_id: str, db: Session = Depends(get_db)) -> dict:
    _require_prompt_lab()
    exp = PromptLabService(db).get_experiment(exp_id)
    if exp is None:
        raise HTTPException(status_code=404, detail=f"Experiment not found: {exp_id}")
    return exp


@app.post("/prompt-lab/experiments/{exp_id}/cells")
def prompt_lab_run_cell(
    exp_id: str, payload: PromptLabCellRun, db: Session = Depends(get_db)
) -> dict:
    _require_prompt_lab()
    try:
        return PromptLabService(db).run_cell(exp_id, payload.variant, payload.block_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/prompt-lab/experiments/{exp_id}/picks")
def prompt_lab_record_pick(
    exp_id: str, payload: PromptLabPick, db: Session = Depends(get_db)
) -> dict:
    _require_prompt_lab()
    try:
        picks = PromptLabService(db).record_pick(
            exp_id, payload.block_id, payload.variant
        )
        return {"picks": picks}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_api.py -v -k prompt_lab`
Expected: PASS (all)

- [ ] **Step 6: Full suite + commit**

Run: `.venv/bin/python -m pytest tests/ -q` — expected: all pass.

```bash
git add backend/api/app.py backend/models/schemas.py tests/test_api.py
git commit -m "feat: gated /prompt-lab API routes"
```

---

### Task 6: frontend — nav gating, corpus and variants panels

**Files:**
- Modify: `frontend/index.html` (nav item + tab skeleton + cache-busters)
- Modify: `frontend/static/js/app.js`
- Modify: `frontend/static/css/styles.css`

**Interfaces:**
- Consumes: `/prompt-lab/status`, `/prompt-lab/corpus` (GET/POST), `/prompt-lab/variants` (GET/POST/PUT/DELETE). Existing helpers: `esc()`, `initTabs()` binds all `.nav-item` clicks at load.
- Produces (used by Task 7): globals `promptLabVariants` (array), `promptLabCorpora` (array); functions `loadPromptLabVariants()`, `loadPromptLabCorpora()` (each re-renders its panel AND refreshes the experiment form selectors via `renderExperimentForm()` if that function exists — guard with `typeof renderExperimentForm === 'function'`).

- [ ] **Step 1: Add the nav item and tab skeleton**

In `frontend/index.html`, after the Apply nav button add:

```html
                <button class="nav-item hidden" id="prompt-lab-nav" data-tab="prompt-lab"><span class="nav-num">🧪</span><span class="nav-label">Prompt Lab</span></button>
```

After the Apply tab's closing `</div>` (the `id="apply"` tab-content), add:

```html
        <!-- Prompt Lab (debug tunable) -->
        <div id="prompt-lab" class="tab-content">
            <div class="card">
                <h2>🧪 Prompt Lab</h2>
                <p>Tune the polish prompt: snapshot real blocks, edit prompt variants, run experiments, compare side by side. Local to this instance — nothing here is committed or shared.</p>

                <h3>Corpus</h3>
                <button type="button" class="btn btn-secondary" onclick="snapshotPromptLabCorpus()">Snapshot current blocks</button>
                <div id="prompt-lab-corpora"><p class="text-muted">Loading…</p></div>

                <h3>Variants</h3>
                <div id="prompt-lab-variants"><p class="text-muted">Loading…</p></div>
                <div id="prompt-lab-variant-editor" class="hidden">
                    <h4 id="variant-editor-title"></h4>
                    <textarea id="variant-editor-text" rows="18"></textarea>
                    <p>
                        <button type="button" class="btn btn-primary" onclick="saveVariantEditor()">Save variant</button>
                        <button type="button" class="btn btn-secondary" onclick="closeVariantEditor()">Close</button>
                    </p>
                </div>

                <h3>Experiments</h3>
                <div id="prompt-lab-experiment-form"></div>
                <div id="prompt-lab-experiments"><p class="text-muted">Loading…</p></div>
                <div id="prompt-lab-results"></div>
            </div>
        </div>
```

Bump both asset links from `?v=20260710-5` to `?v=20260710-6`.

- [ ] **Step 2: Add gating + corpus + variants JS**

In `frontend/static/js/app.js`, add to the first `DOMContentLoaded` handler (after `loadUploadedResumes();`):

```javascript
    initPromptLab();
```

Then add (near `loadUploadedResumes`):

```javascript
// --- Prompt Lab (visible only when the JOB_ACE_DEBUG_MENU tunable is on) ---

let promptLabVariants = [];
let promptLabCorpora = [];
let promptLabEditingVariant = null;

async function initPromptLab() {
    try {
        const resp = await fetch(`${API_BASE}/prompt-lab/status`);
        if (!resp.ok) return;
        const data = await resp.json();
        if (!data.enabled) return;
        document.getElementById('prompt-lab-nav').classList.remove('hidden');
        loadPromptLabCorpora();
        loadPromptLabVariants();
        if (typeof loadPromptLabExperiments === 'function') loadPromptLabExperiments();
    } catch (e) {
        console.error('Prompt Lab status check failed:', e);
    }
}

async function loadPromptLabCorpora() {
    const el = document.getElementById('prompt-lab-corpora');
    try {
        const resp = await fetch(`${API_BASE}/prompt-lab/corpus`);
        if (!resp.ok) return;
        promptLabCorpora = await resp.json();
        el.innerHTML = promptLabCorpora.length
            ? `<ul class="job-review-list">${promptLabCorpora.map(c =>
                `<li>${esc(c.id)} — ${c.created_at ? new Date(c.created_at).toLocaleString() : 'unknown'}, ${c.block_count} block(s)</li>`).join('')}</ul>`
            : '<p class="text-muted">No corpus snapshots yet.</p>';
        if (typeof renderExperimentForm === 'function') renderExperimentForm();
    } catch (e) {
        console.error('Failed to load corpora:', e);
    }
}

async function snapshotPromptLabCorpus() {
    try {
        const resp = await fetch(`${API_BASE}/prompt-lab/corpus`, { method: 'POST' });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            alert('Snapshot failed: ' + (err.detail || resp.status));
            return;
        }
        await loadPromptLabCorpora();
    } catch (e) {
        alert('Snapshot error: ' + e.message);
    }
}

async function loadPromptLabVariants() {
    const el = document.getElementById('prompt-lab-variants');
    try {
        const resp = await fetch(`${API_BASE}/prompt-lab/variants`);
        if (!resp.ok) return;
        promptLabVariants = await resp.json();
        el.innerHTML = `<ul class="job-review-list">${promptLabVariants.map(v => {
            const actions = v.read_only
                ? `<button type="button" class="btn-select-action" onclick="clonePromptLabVariant('${esc(v.name)}')">Clone</button>
                   <button type="button" class="btn-select-action" onclick="openVariantEditor('${esc(v.name)}', true)">View</button>`
                : `<button type="button" class="btn-select-action" onclick="openVariantEditor('${esc(v.name)}', false)">Edit</button>
                   <button type="button" class="btn-select-action" onclick="clonePromptLabVariant('${esc(v.name)}')">Clone</button>
                   <button type="button" class="btn-select-action" onclick="deletePromptLabVariant('${esc(v.name)}')">Delete</button>`;
            return `<li><strong>${esc(v.name)}</strong>${v.read_only ? ' (shipped, read-only)' : ''} ${actions}</li>`;
        }).join('')}</ul>`;
        if (typeof renderExperimentForm === 'function') renderExperimentForm();
    } catch (e) {
        console.error('Failed to load variants:', e);
    }
}

async function clonePromptLabVariant(base) {
    const name = prompt(`Name for the new variant (cloned from ${base}):`);
    if (!name) return;
    const resp = await fetch(`${API_BASE}/prompt-lab/variants`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, base })
    });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        alert('Clone failed: ' + (err.detail || resp.status));
        return;
    }
    const created = await resp.json();
    await loadPromptLabVariants();
    openVariantEditor(created.name, false);
}

function openVariantEditor(name, readOnly) {
    const v = promptLabVariants.find(x => x.name === name);
    if (!v) return;
    promptLabEditingVariant = readOnly ? null : name;
    document.getElementById('variant-editor-title').textContent =
        readOnly ? `${name} (read-only)` : `Editing: ${name}`;
    const ta = document.getElementById('variant-editor-text');
    ta.value = v.prompt_text;
    ta.readOnly = !!readOnly;
    document.getElementById('prompt-lab-variant-editor').classList.remove('hidden');
}

async function saveVariantEditor() {
    if (!promptLabEditingVariant) { alert('This variant is read-only.'); return; }
    const text = document.getElementById('variant-editor-text').value;
    const resp = await fetch(
        `${API_BASE}/prompt-lab/variants/${encodeURIComponent(promptLabEditingVariant)}`,
        { method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt_text: text }) });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        alert('Save failed: ' + (err.detail || resp.status));
        return;
    }
    await loadPromptLabVariants();
    alert('Variant saved.');
}

function closeVariantEditor() {
    promptLabEditingVariant = null;
    document.getElementById('prompt-lab-variant-editor').classList.add('hidden');
}

async function deletePromptLabVariant(name) {
    if (!confirm(`Delete variant "${name}"? Past experiment results keep their copies.`)) return;
    const resp = await fetch(
        `${API_BASE}/prompt-lab/variants/${encodeURIComponent(name)}`, { method: 'DELETE' });
    if (!resp.ok && resp.status !== 204) {
        const err = await resp.json().catch(() => ({}));
        alert('Delete failed: ' + (err.detail || resp.status));
        return;
    }
    await loadPromptLabVariants();
}
```

- [ ] **Step 3: Add panel CSS**

Append to `frontend/static/css/styles.css`:

```css
/* Prompt Lab */
#prompt-lab h3 {
    margin-top: 1.5rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border-color);
}

#prompt-lab-variant-editor textarea {
    width: 100%;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 0.85rem;
    line-height: 1.45;
}

.job-review-list .btn-select-action {
    margin-left: 0.35rem;
    padding: 0.15rem 0.5rem;
    font-size: 0.75rem;
}
```

- [ ] **Step 4: Verify by hand**

Run: `node --check frontend/static/js/app.js` — expected: no output (valid).
Start a scratch server with the tunable on and check the flows:

```bash
cd /opt/job-ace/worktrees/job-resume-pairing && \
JOB_ACE_DEBUG_MENU=true JOB_ACE_DATABASE_URL=sqlite:////tmp/promptlab-e2e/db.sqlite3 \
JOB_ACE_DATA_ROOT=/tmp/promptlab-e2e/artifacts \
.venv/bin/uvicorn backend.api.app:app --host 127.0.0.1 --port 3998 &
sleep 2
curl -s http://127.0.0.1:3998/prompt-lab/status   # {"enabled":true}
curl -s http://127.0.0.1:3998/prompt-lab/variants | head -c 200  # shipped baseline
kill %1
```

Also confirm gating: start WITHOUT the env var, `/prompt-lab/status` → `{"enabled":false}`, `/prompt-lab/variants` → 404.

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html frontend/static/js/app.js frontend/static/css/styles.css
git commit -m "feat: Prompt Lab UI — gated nav, corpus and variant panels"
```

---

### Task 7: frontend — experiments panel with runs, diffs, picks

**Files:**
- Modify: `frontend/index.html` (nothing new — containers exist from Task 6)
- Modify: `frontend/static/js/app.js`
- Modify: `frontend/static/css/styles.css`

**Interfaces:**
- Consumes: `/prompt-lab/experiments` (GET/POST), `/prompt-lab/experiments/{id}` (GET), `/prompt-lab/experiments/{id}/cells` (POST per cell), `/prompt-lab/experiments/{id}/picks` (POST); globals `promptLabVariants`, `promptLabCorpora` from Task 6; existing `diffTokens(a, b)` and `renderDiffPane(ops, side)` from the polish review; `esc()`.
- Produces: `renderExperimentForm()`, `loadPromptLabExperiments()`, `startPromptLabExperiment()`, `openPromptLabExperiment(expId)`, `recordPromptLabPick(expId, blockId, variant)`.

- [ ] **Step 1: Add the experiments JS**

Append to the Prompt Lab section of `frontend/static/js/app.js`:

```javascript
// --- Prompt Lab experiments ---

function renderExperimentForm() {
    const el = document.getElementById('prompt-lab-experiment-form');
    if (!el) return;
    if (promptLabVariants.length < 2 || !promptLabCorpora.length) {
        el.innerHTML = '<p class="text-muted">Need at least two variants (shipped counts) and one corpus snapshot to run an experiment.</p>';
        return;
    }
    el.innerHTML = `
        <div class="prompt-lab-form-row">
            <span><strong>Variants:</strong>
            ${promptLabVariants.map(v =>
                `<label class="prompt-lab-check"><input type="checkbox" class="exp-variant" value="${esc(v.name)}"> ${esc(v.name)}</label>`
            ).join('')}</span>
            <span><strong>Corpus:</strong>
            <select id="exp-corpus">${promptLabCorpora.map(c =>
                `<option value="${esc(c.id)}">${esc(c.id)} (${c.block_count} blocks)</option>`).join('')}</select></span>
            <button type="button" class="btn btn-primary" id="exp-run-btn" onclick="startPromptLabExperiment()">Run experiment</button>
        </div>`;
}

async function loadPromptLabExperiments() {
    const el = document.getElementById('prompt-lab-experiments');
    if (!el) return;
    try {
        const resp = await fetch(`${API_BASE}/prompt-lab/experiments`);
        if (!resp.ok) return;
        const exps = await resp.json();
        el.innerHTML = exps.length
            ? `<ul class="job-review-list">${exps.map(e =>
                `<li>${esc(e.id)} — ${e.variants.map(esc).join(' vs ')} on ${esc(e.corpus_id)},
                 ${e.cells_run}/${e.cells_total} cells
                 <button type="button" class="btn-select-action" onclick="openPromptLabExperiment('${esc(e.id)}')">Open</button></li>`).join('')}</ul>`
            : '<p class="text-muted">No experiments yet.</p>';
    } catch (e) {
        console.error('Failed to load experiments:', e);
    }
}

async function startPromptLabExperiment() {
    const variants = [...document.querySelectorAll('.exp-variant:checked')].map(cb => cb.value);
    const corpusId = document.getElementById('exp-corpus').value;
    if (variants.length < 2) { alert('Pick at least two variants.'); return; }

    const btn = document.getElementById('exp-run-btn');
    btn.disabled = true;
    try {
        const resp = await fetch(`${API_BASE}/prompt-lab/experiments`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ variant_names: variants, corpus_id: corpusId })
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            alert('Could not create experiment: ' + (err.detail || resp.status));
            return;
        }
        const exp = await resp.json();
        const cells = [...exp.cells];
        const total = cells.length;
        let done = 0;
        btn.textContent = `Running 0/${total}…`;

        // Two cells in flight — each cell is one polish + one fabrication check.
        async function worker() {
            while (cells.length) {
                const cell = cells.shift();
                try {
                    await fetch(`${API_BASE}/prompt-lab/experiments/${exp.id}/cells`, {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ variant: cell.variant, block_id: cell.block_id })
                    });
                } catch (e) {
                    console.error('Cell failed:', cell, e);
                }
                done += 1;
                btn.textContent = `Running ${done}/${total}…`;
            }
        }
        await Promise.all(Array.from({ length: Math.min(2, total) }, worker));
        await loadPromptLabExperiments();
        await openPromptLabExperiment(exp.id);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Run experiment';
    }
}

async function openPromptLabExperiment(expId) {
    const el = document.getElementById('prompt-lab-results');
    el.innerHTML = '<p class="text-muted">Loading results…</p>';
    const resp = await fetch(`${API_BASE}/prompt-lab/experiments/${encodeURIComponent(expId)}`);
    if (!resp.ok) { el.innerHTML = '<p class="text-muted">Could not load experiment.</p>'; return; }
    const exp = await resp.json();
    const corpusResp = await fetch(`${API_BASE}/prompt-lab/corpus/${encodeURIComponent(exp.corpus_id)}`);
    const corpus = corpusResp.ok ? await corpusResp.json() : { blocks: [] };

    const scoreTable = `
        <table class="prompt-lab-scores">
            <tr><th>variant</th><th>cells</th><th>errors</th><th>fabrications</th><th>unchecked</th><th>mean filler</th><th>mean |Δlen|</th><th>structure breaks</th><th>your picks</th></tr>
            ${exp.variants.map(v => {
                const r = exp.rollups[v];
                return `<tr><td>${esc(v)}</td><td>${r.cells_run}</td><td>${r.errors}</td>
                    <td class="${r.fabrication_failures ? 'lab-bad' : ''}">${r.fabrication_failures}</td>
                    <td>${r.fabrication_unchecked}</td><td>${r.mean_filler}</td>
                    <td>${r.mean_abs_length_delta}</td><td>${r.structure_breaks}</td>
                    <td><strong>${r.picks}</strong></td></tr>`;
            }).join('')}
        </table>`;

    const blockSections = corpus.blocks.map(b => {
        const cols = exp.variants.map(v => {
            const cell = exp.results[`${v}::${b.block_id}`];
            if (!cell) return `<div class="lab-cell"><h5>${esc(v)}</h5><p class="text-muted">pending</p></div>`;
            if (cell.error) return `<div class="lab-cell"><h5>${esc(v)}</h5><p class="lab-bad">error: ${esc(cell.error)}</p></div>`;
            const ops = diffTokens(b.text, cell.output);
            const fab = cell.scores && cell.scores.fabrication;
            const fabBanner = fab && fab.ok === false
                ? `<p class="lab-fab-banner">⚠ fabrication: ${esc((fab.fabrications[0] || {}).claim || fab.notes)}</p>` : '';
            const picked = exp.picks[String(b.block_id)] === v;
            return `<div class="lab-cell${picked ? ' lab-picked' : ''}">
                <h5>${esc(v)}
                    <button type="button" class="btn-select-action" onclick="recordPromptLabPick('${esc(exp.id)}', ${b.block_id}, '${esc(v)}')">${picked ? '✔ picked' : 'pick'}</button>
                </h5>
                ${fabBanner}
                <pre class="polish-all-text">${renderDiffPane(ops, 'polished')}</pre>
            </div>`;
        }).join('');
        const title = [b.category, b.job_title, b.company].filter(Boolean).join(' — ');
        return `<div class="lab-block">
            <div class="polish-all-row-header"><strong>${esc(title || ('block ' + b.block_id))}</strong></div>
            <details><summary>original</summary><pre class="polish-all-text">${esc(b.text)}</pre></details>
            <div class="lab-cells" style="grid-template-columns: repeat(${exp.variants.length}, 1fr);">${cols}</div>
        </div>`;
    }).join('');

    el.innerHTML = `<h4>${esc(exp.id)} — ${exp.variants.map(esc).join(' vs ')}</h4>${scoreTable}${blockSections}`;
}

async function recordPromptLabPick(expId, blockId, variant) {
    const resp = await fetch(`${API_BASE}/prompt-lab/experiments/${encodeURIComponent(expId)}/picks`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ block_id: blockId, variant })
    });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        alert('Pick failed: ' + (err.detail || resp.status));
        return;
    }
    await openPromptLabExperiment(expId);
}
```

- [ ] **Step 2: Add experiments CSS**

Append to `frontend/static/css/styles.css`:

```css
.prompt-lab-form-row {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    align-items: center;
    margin-bottom: 1rem;
}

.prompt-lab-check { display: inline-flex; align-items: center; gap: 0.3rem; margin-right: 0.75rem; font-weight: 400; }

.prompt-lab-scores { border-collapse: collapse; margin: 0.75rem 0 1.25rem; font-size: 0.85rem; }
.prompt-lab-scores th, .prompt-lab-scores td { border: 1px solid var(--border-color); padding: 0.35rem 0.6rem; text-align: center; }
.prompt-lab-scores th { background: var(--bg-color); }

.lab-block { border: 1px solid var(--border-color); border-radius: 0.5rem; padding: 0.75rem; margin-bottom: 1rem; }
.lab-cells { display: grid; gap: 1rem; margin-top: 0.5rem; }
.lab-cell h5 { margin: 0 0 0.4rem; display: flex; justify-content: space-between; align-items: center; }
.lab-cell.lab-picked { outline: 2px solid var(--success-color); border-radius: 0.375rem; }
.lab-bad { color: var(--danger-color); font-weight: 600; }
.lab-fab-banner { background: #fee2e2; color: #991b1b; border-radius: 0.375rem; padding: 0.35rem 0.6rem; font-size: 0.85rem; }
```

- [ ] **Step 3: Verify**

Run: `node --check frontend/static/js/app.js` — expected: valid.
Re-run the scratch server from Task 6 Step 4 with the tunable on, seed a couple of blocks via `POST /confirm-resume-blocks`, then in a browser (or curl the API flow): snapshot → clone shipped → edit variant → run experiment (stub provider returns source text — cells complete, scores compute, diff panes render identical text without highlights) → pick → rollup pick count updates.

- [ ] **Step 4: Full suite + commit**

Run: `.venv/bin/python -m pytest tests/ -q` — expected: all pass.

```bash
git add frontend/static/js/app.js frontend/static/css/styles.css
git commit -m "feat: Prompt Lab experiments UI — cell-by-cell runs, diffs, picks"
```

---

### Task 8: verification, PR, staging rollout

**Files:**
- No new code. PR + deploy.

- [ ] **Step 1: Full local verification**

```bash
cd /opt/job-ace/worktrees/job-resume-pairing
.venv/bin/python -m pytest tests/ -q         # all pass
node --check frontend/static/js/app.js       # valid
git log --oneline origin/master..HEAD        # spec + 7 feature commits
```

Check branch-introduced ruff violations only (advisory): `.venv/bin/ruff check backend/ tests/ --exit-zero` and clean anything the branch added.

- [ ] **Step 2: Open the PR**

```bash
GH_CONFIG_DIR=/home/d/.config/gh gh pr create -R danialo/job-ace --base master --head feat/prompt-lab \
  --title "Prompt Lab: polish prompt tuning/scoring pipeline" \
  --body "Implements specs/polish-prompt-lab.md ..."
```

Wait for the CI `test` check to pass.

- [ ] **Step 3: Merge and deploy to staging with the tunable on**

After merge: add `Environment=JOB_ACE_DEBUG_MENU=true` to `jobace-staging.service` (systemd drop-in or service file edit + `daemon-reload`), then fetch + ff `/opt/jobace-staging` and restart. Verify:

```bash
curl -s http://127.0.0.1:3001/prompt-lab/status    # {"enabled":true}
curl -s http://127.0.0.1:3000/prompt-lab/status 2>/dev/null   # {"enabled":false} or connection refused (live not updated)
```

- [ ] **Step 4: First experiment (acceptance test)**

In the staging UI: snapshot the real blocks, clone `shipped:default` into a de-neutered draft, run shipped vs draft, review diffs and picks. The winner becomes the PR that updates `backend/prompts/polish/default.txt` and closes issue #5 — that's a separate follow-up PR, not part of this plan.

---

## Self-Review (completed)

- **Spec coverage:** §1 prompts→files (Task 1), §2 service/storage (Tasks 3–4), §3 scorers (Task 2), §4 API+gating (Task 5, status-always-answers resolved as spec intended), §5 UI (Tasks 6–7), §6 error handling (per-cell errors Task 4, 404/400/409 Task 5, empty-corpus 400 Tasks 3/5, delete-keeps-experiments Task 3 storage design), §7 testing (each task's tests), §8 rollout (Task 8). No gaps.
- **Placeholder scan:** none — every step has complete code/commands.
- **Type consistency:** `render_template(template, block_text, category)` defined Task 1, consumed Task 4; scorer signatures Task 2 = usage Task 4; service methods Tasks 3–4 = routes Task 5; route paths Task 5 = fetches Tasks 6–7; `diffTokens`/`renderDiffPane` names match the shipped app.js; globals `promptLabVariants`/`promptLabCorpora` shared Tasks 6→7 with `typeof` guards for load order.
