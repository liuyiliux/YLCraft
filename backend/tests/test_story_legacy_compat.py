from __future__ import annotations

import json

import pytest
from sqlmodel import Session, create_engine

from app.api.v1.story import get_story, list_stories
from app.db.models.story import Story, StoryCharacterPortrait, StoryStatus


@pytest.fixture
def story_session():
    engine = create_engine("sqlite:///:memory:")
    Story.__table__.create(engine)
    StoryCharacterPortrait.__table__.create(engine)
    with Session(engine) as session:
        yield session


@pytest.mark.asyncio
async def test_legacy_story_list_returns_migration_hint(story_session: Session):
    story = Story(
        id="legacy-story-1",
        title="旧 Story Maker 项目",
        topic="测试迁移提示",
        status=StoryStatus.COMPLETED.value,
        scene_count=2,
    )
    story_session.add(story)
    story_session.commit()

    response = await list_stories(session=story_session)

    assert response.success is True
    assert response.total == 1
    assert response.stories[0]["id"] == "legacy-story-1"
    assert response.migration_hint
    assert response.migration_hint["replacement_api"] == "/api/v1/creative-projects"
    assert response.migration_hint["replacement_page"] == "/story"


@pytest.mark.asyncio
async def test_legacy_story_detail_keeps_payload_and_points_to_creative_projects(story_session: Session):
    story = Story(
        id="legacy-story-2",
        title="旧故事详情",
        topic="详情兼容",
        characters_json=json.dumps([{"name": "阿青"}], ensure_ascii=False),
        scenes_json=json.dumps([{"scene_number": 1, "summary": "开场"}], ensure_ascii=False),
        status=StoryStatus.COMPLETED.value,
        scene_count=1,
    )
    portrait = StoryCharacterPortrait(
        story_id=story.id,
        character_name="阿青",
        portrait_urls=json.dumps(["/assets/a.png"], ensure_ascii=False),
        selected_url="/assets/a.png",
    )
    story_session.add(story)
    story_session.add(portrait)
    story_session.commit()

    response = await get_story(story.id, session=story_session)

    assert response["success"] is True
    assert response["story"]["id"] == story.id
    assert response["characters"][0]["name"] == "阿青"
    assert response["scenes"][0]["summary"] == "开场"
    assert response["portraits"]["阿青"]["selected_url"] == "/assets/a.png"
    assert response["migration_hint"]["replacement_api"] == "/api/v1/creative-projects"
