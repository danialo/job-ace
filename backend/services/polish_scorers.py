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
