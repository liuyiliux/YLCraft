"""Focused tests for the append-only dynamic-state ledger."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlmodel import Session

from app.db.models.creative_project import ProjectStateEntry
from app.services.creative_project.state_ledger import StateLedger, _apply


@pytest.fixture()
def state_session():
    engine = create_engine("sqlite:///:memory:")
    ProjectStateEntry.__table__.create(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_apply_semantics():
    assert _apply(5, "set", 6) == 6
    assert _apply(5, "add", 1) == 6
    assert _apply(6, "remove", 1) == 5
    assert _apply(["a"], "add", ["b", "a"]) == ["a", "b"]
    assert _apply(["a", "b"], "remove", ["a"]) == ["b"]
    assert _apply("x", "remove", "x") is None
    assert _apply("anything", "unknown-op", 1) == "anything"


def test_apply_changes_and_compute_state(state_session):
    added = StateLedger.apply_changes(
        state_session,
        "p1",
        [
            {"scope": "character:c1", "key": "level", "op": "add", "value": 1},
            {"scope": "character:c1", "key": "skills", "op": "add", "value": ["剑术", "身法"]},
            {"scope": "world", "key": "countdown", "op": "set", "value": "剩余3天"},
        ],
        chapter_number=1,
        source_content_id="content-1",
    )
    state_session.commit()
    assert added == 3

    state = StateLedger.compute_state(state_session, "p1")
    assert state["character:c1"]["level"] == 1
    assert state["character:c1"]["skills"] == ["剑术", "身法"]
    assert state["world"]["countdown"] == "剩余3天"


def test_dedup(state_session):
    changes = [{"scope": "character:c1", "key": "level", "op": "add", "value": 1}]
    first = StateLedger.apply_changes(state_session, "p1", changes, chapter_number=1, source_content_id="c1")
    second = StateLedger.apply_changes(state_session, "p1", changes, chapter_number=1, source_content_id="c1")
    state_session.commit()
    assert first == 1
    assert second == 0
    assert StateLedger.compute_state(state_session, "p1")["character:c1"]["level"] == 1


def test_rollback_to_chapter(state_session):
    StateLedger.apply_changes(state_session, "p1", [{"scope": "character:c1", "key": "level", "op": "add", "value": 1}], chapter_number=1, source_content_id="c1")
    StateLedger.apply_changes(state_session, "p1", [{"scope": "character:c1", "key": "level", "op": "add", "value": 2}], chapter_number=2, source_content_id="c2")
    StateLedger.apply_changes(state_session, "p1", [{"scope": "character:c1", "key": "skills", "op": "add", "value": ["剑术"]}], chapter_number=2, source_content_id="c2")
    state_session.commit()

    as_of_ch1 = StateLedger.state_as_of(state_session, "p1", 1)
    as_of_ch2 = StateLedger.compute_state(state_session, "p1")
    assert as_of_ch1["character:c1"] == {"level": 1}
    assert as_of_ch2["character:c1"]["level"] == 3
    assert as_of_ch2["character:c1"]["skills"] == ["剑术"]


def test_replace_chapter_entries(state_session):
    StateLedger.apply_changes(state_session, "p1", [{"scope": "character:c1", "key": "level", "op": "add", "value": 1}], chapter_number=1, source_content_id="c1")
    state_session.commit()
    StateLedger.replace_chapter_entries(
        state_session,
        "p1",
        1,
        [{"scope": "character:c1", "key": "level", "op": "set", "value": 5}],
        source_content_id="c1-new",
    )
    state_session.commit()
    state = StateLedger.compute_state(state_session, "p1")
    assert state["character:c1"]["level"] == 5


def test_scope_separation(state_session):
    StateLedger.apply_changes(state_session, "p1", [{"scope": "world", "key": "phase", "op": "set", "value": "序章"}], chapter_number=1, source_content_id="c1")
    state_session.commit()
    assert StateLedger.compute_state(state_session, "p1", scope="world") == {"world": {"phase": "序章"}}
    assert StateLedger.compute_state(state_session, "p1", scope="character:c1") == {}
