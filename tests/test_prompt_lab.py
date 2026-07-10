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
