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


def test_fabrication_check_inconclusive_none_preserved():
    checker = lambda text, blocks, ctx=None: SimpleNamespace(
        ok=None, fabrications=[], notes="inconclusive")
    r = ps.fabrication_check(checker, "polished", {"id": 1, "text": "orig"})
    assert r["ok"] is None


def test_score_output_shape():
    checker = lambda text, blocks, ctx=None: SimpleNamespace(ok=True, fabrications=[], notes="")
    s = ps.score_output("Dev\n• a", "Dev\n• a!", {"id": 1, "text": "Dev\n• a"}, checker)
    assert set(s) == {"fabrication", "filler_count", "length_delta", "structure"}
