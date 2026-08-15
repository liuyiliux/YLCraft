"""Focused tests for the Writer Room team-mode helper methods.

These exercise the pure character-resolution and scene-context helpers used by
``CreativeProjectService._run_character_rehearsal_team`` without a database.
"""

from __future__ import annotations

from app.services.creative_project.service import CreativeProjectService


def _bare_service() -> CreativeProjectService:
    # Bypass __init__ (which needs a session); the tested helpers are pure.
    return CreativeProjectService.__new__(CreativeProjectService)


def test_resolve_team_characters_from_outline():
    svc = _bare_service()

    class _Character:
        name = "沈清"

    svc.sync_outline_characters = lambda project_id: [_Character()]
    assert svc._resolve_team_characters("p1", {}) == ["沈清"]


def test_resolve_team_characters_falls_back_to_scene_beats():
    svc = _bare_service()

    def _raise(project_id):
        raise ValueError("no characters")

    svc.sync_outline_characters = _raise
    context = {"scene_beats": {"scene_beats": [{"characters": ["沈清", "陆沉", "沈清"]}]}}
    assert svc._resolve_team_characters("p1", context) == ["沈清", "陆沉"]


def test_resolve_team_characters_empty_when_no_source():
    svc = _bare_service()
    svc.sync_outline_characters = lambda project_id: (_ for _ in ()).throw(ValueError("none"))
    assert svc._resolve_team_characters("p1", {"scene_beats": {}}) == []


def test_scene_context_for_team_includes_beats_and_outline():
    svc = _bare_service()
    context = {
        "scene_beats": {"scene_beats": [{"title": "雨夜"}]},
        "chapter_outline": {"title": "第一章"},
    }
    text = svc._scene_context_for_team(context)
    assert "场景节拍" in text
    assert "章节细纲" in text


def test_scene_context_for_team_defaults():
    svc = _bare_service()
    assert svc._scene_context_for_team({}) == "本章场景"
