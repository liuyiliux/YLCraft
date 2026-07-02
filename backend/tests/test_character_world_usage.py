from types import SimpleNamespace

from app.db.models.character import CharacterStoryLink
from app.services.character.service import CharacterService


def test_story_link_response_contains_project_world_and_constraints():
    service = CharacterService.__new__(CharacterService)
    link = CharacterStoryLink(
        id="link-1",
        character_id="char-1",
        story_id="project-1",
        world_id="world-1",
        world_name="霓虹城",
        usage_role="反派",
        local_alias="黑伞",
        local_identity="地下情报商",
        local_faction="灰塔",
        local_status="active",
        local_costume="黑色长风衣",
        local_prompt_tags='["赛博朋克", "雨夜"]',
        ooc_notes="不会无理由救主角",
        off_model_notes="银色吊坠不能丢失",
        bible_overrides_json='{"voice":"低声"}',
        visual_overrides_json='{"lighting":"冷色"}',
    )
    project = SimpleNamespace(id="project-1", title="测试项目", project_type="short_drama")

    data = service.story_link_to_response(link, project)

    assert data["project_title"] == "测试项目"
    assert data["world_name"] == "霓虹城"
    assert data["usage_role"] == "反派"
    assert data["local_prompt_tags"] == ["赛博朋克", "雨夜"]
    assert data["ooc_notes"] == "不会无理由救主角"
    assert data["off_model_notes"] == "银色吊坠不能丢失"
    assert data["bible_overrides"]["voice"] == "低声"
    assert data["visual_overrides"]["lighting"] == "冷色"
