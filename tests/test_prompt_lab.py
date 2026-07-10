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
    assert cell["output"] == "POLISHED[A PROMPT]"
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
