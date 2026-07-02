from __future__ import annotations

import json
import uuid
from types import SimpleNamespace

import pytest
from sqlmodel import Session, create_engine, select

from app.db.models.creative_project import (
    CreativeProject,
    ProjectAssetLink,
    ProjectContent,
    ProjectGenerationLog,
)
from app.db.models.character import Character, CharacterStoryLink
from app.services.ai.types import LLMGenerationResult
from app.services.creative_project.service import CreativeProjectService, loads_json


class FakeAIService:
    async def chat(self, messages, **kwargs):
        assert hasattr(messages[-1], "role")
        user_content = messages[-1].content

        if '"pages"' in user_content and '"page_count"' in user_content:
            return self._result(
                {
                    "episode_number": 1,
                    "chapter_number": 1,
                    "title": "Comic pages",
                    "page_count": 2,
                    "visual_style": "cinematic comic",
                    "pages": [
                        {
                            "page_number": 1,
                            "title": "Package",
                            "content": "Page 1:\n[Panel 1] Lin opens the anonymous package.",
                            "image_prompt": "cold editing room, anonymous package, cinematic light",
                        },
                        {
                            "page_number": 2,
                            "title": "Photo",
                            "content": "Page 2:\n[Panel 1] Lin finds an old photo.",
                            "image_prompt": "short-haired woman holding an old photo, close-up",
                        },
                    ],
                }
            )

        if '"panels"' in user_content and '"panel_number"' in user_content:
            return self._result(
                {
                    "episode_number": 1,
                    "title": "Storyboard",
                    "visual_style": "cold urban realism",
                    "panels": [
                        {
                            "panel_number": 1,
                            "source_scene_number": 1,
                            "image_prompt": (
                                "cold editing room, short-haired Lin opens an anonymous package, "
                                "medium shot, cinematic composition, consistent character design"
                            ),
                            "camera_hint": "medium shot",
                            "shot_size": "medium",
                            "composition": "center composition",
                            "characters": ["Lin Zhao"],
                            "action": "Lin opens the package",
                            "emotion": "alert",
                            "dialogue_bubbles": ["This is not a script. This is evidence."],
                            "sound_effect": "click",
                            "negative_prompt": "low quality",
                            "notes": "Emphasize evidence on desk",
                        }
                    ],
                }
            )

        if '"duration_target_seconds"' in user_content:
            return self._result(
                {
                    "episode_number": 1,
                    "title": "Episode script",
                    "duration_target_seconds": 90,
                    "hook": "Lin finds her childhood photo inside short-drama material.",
                    "scenes": [
                        {
                            "scene_number": 1,
                            "location": "editing room",
                            "characters": ["Lin Zhao"],
                            "action": "Lin opens the anonymous package and finds monitoring stills.",
                            "dialogue": [{"character": "Lin Zhao", "line": "This is not a script."}],
                            "camera_hint": "handheld close shot",
                            "emotion": "shocked",
                            "image_prompt": "cold editing room, short-haired woman opening package",
                        }
                    ],
                    "ending_hook": "A company watermark appears behind the photo.",
                }
            )

        if '"word_count"' in user_content and '"continuity_notes"' in user_content:
            return self._result(
                {
                    "chapter_number": 1,
                    "title": "Entry",
                    "content": "Lin Zhao shuts down the timeline and opens the anonymous package.",
                    "word_count": 65,
                    "continuity_notes": ["Lin starts suspecting the production company."],
                }
            )

        if '"summary"' in user_content and '"scenes"' in user_content:
            return self._result(
                {
                    "chapter_number": 1,
                    "title": "Entry",
                    "summary": "Lin receives an anonymous package and finds evidence.",
                    "objective": "Make the protagonist investigate actively.",
                    "keywords": ["evidence", "package"],
                    "scenes": [
                        {
                            "scene_number": 1,
                            "title": "Anonymous package",
                            "location": "editing room",
                            "characters": ["Lin Zhao"],
                            "purpose": "Throw out the old case clue.",
                            "scene_role": "hook",
                            "objective": "Reveal the clue.",
                            "conflict": "The source cannot be traced.",
                            "beats": ["Package arrives", "Lin finds a photo"],
                            "action": "Lin opens the anonymous package.",
                            "key_dialogue": "This is not a script. This is evidence.",
                            "emotion": "alert",
                            "emotional_turn": "alert to shocked",
                            "visual_focus": "old photo on desk",
                            "shot_design": "low-angle medium shot",
                            "image_prompt": "cold editing room, short-haired woman opening anonymous package",
                        }
                    ],
                    "key_dialogues": ["This is not a script. This is evidence."],
                    "foreshadowing": ["The photo has a watermark."],
                    "ending_hook": "A childhood photo appears in the package.",
                    "continuity_notes": ["Next chapter traces package source."],
                }
            )

        if '"chapter_count"' in user_content:
            return self._result(
                {
                    "chapter_count": 2,
                    "chapters": [
                        {
                            "chapter_number": 1,
                            "title": "Entry",
                            "goal": "Find the old case clue.",
                            "conflict": "A colleague hides evidence.",
                            "key_events": ["Package arrives", "Monitor blind spot"],
                            "character_focus": ["Lin Zhao"],
                            "ending_hook": "A childhood photo appears.",
                            "status": "planned",
                        },
                        {
                            "chapter_number": 2,
                            "title": "Counterproof",
                            "goal": "Verify the clue.",
                            "conflict": "A witness changes testimony.",
                            "key_events": ["Find backup audio", "Public challenge"],
                            "character_focus": ["Lin Zhao"],
                            "ending_hook": "The dead person's voice appears.",
                            "status": "planned",
                        },
                    ],
                }
            )

        return self._result(
            {
                "title": "Smart short drama",
                "genre": ["suspense", "urban"],
                "premise": "A video editor tracks evidence through short-drama scripts.",
                "logline": "A video editor uses logic and evidence to break a manipulative script.",
                "selling_points": ["No dumb plot", "Evidence chain"],
                "target_reader": "Readers who like strong suspense short dramas.",
                "audience_emotion": "tense and satisfied",
                "tone": "fast, restrained, evidence-driven",
                "worldview": "Modern city where every reversal needs evidence.",
                "narrative_rules": ["No coincidence-only twists"],
                "main_conflict": "Expose the real case while fighting a production company.",
                "themes": ["truth", "logic"],
                "characters": [
                    {
                        "name": "Lin Zhao",
                        "role": "protagonist",
                        "age_range": "28-32",
                        "appearance": "short hair, calm expression",
                        "costume_hint": "white shirt and dark jeans",
                        "personality": "rational and sharp",
                        "background": "video editor",
                        "goal": "find the truth",
                        "arc": "observer to actor",
                        "visual_tags": ["short hair", "cold tone"],
                        "voice": "precise",
                        "image_prompt": "short-haired woman, white shirt, cold urban light",
                    }
                ],
                "relationship_map": "Lin and Xu test each other, then build trust.",
                "locations": [
                    {
                        "name": "editing room",
                        "role": "main workspace",
                        "visual_description": "screens, desk, blue light",
                        "mood": "tense",
                        "reusable_asset_note": "can be reused as background",
                    }
                ],
                "story_arc": {
                    "beginning": "Lin finds script material overlapping an old case.",
                    "middle": "The evidence chain is polluted.",
                    "climax": "Evidence is released live.",
                    "ending_direction": "Truth is revealed, but a larger manipulator appears.",
                },
                "visual_style": "cold urban realism with screen information",
                "image_style_prompt": "cinematic cold light, realistic characters",
                "production_notes": ["Keep evidence visible."],
            }
        )

    def _result(self, content: dict) -> LLMGenerationResult:
        return LLMGenerationResult(
            success=True,
            content=json.dumps(content, ensure_ascii=False),
            provider="fake",
            model="fake-llm",
        )


class FailingAIService:
    async def chat(self, messages, **kwargs):
        return LLMGenerationResult(
            success=False,
            error="Client error '403 Forbidden' for url 'https://api.siliconflow.cn/v1/chat/completions'",
            provider="siliconflow",
            model="Qwen/QwQ-32B",
        )


class BrokenJsonAIService:
    async def chat(self, messages, **kwargs):
        return LLMGenerationResult(
            success=True,
            content=(
                '{"title":"Locally repaired story" '
                '"genre":["suspense"] '
                '"logline":"A protagonist uses logic to break a bad script." '
                '"characters":[{"name":"Lin Zhao" "role":"protagonist" "goal":"find truth"}] '
                '"story_arc":{"beginning":"find clue" "middle":"trace rules" "climax":"release evidence" "ending_direction":"continue"}}'
            ),
            provider="fake",
            model="broken-json",
        )


class CapturingAIService(FakeAIService):
    def __init__(self):
        self.messages = []

    async def chat(self, messages, **kwargs):
        self.messages = messages
        return await super().chat(messages, **kwargs)


class PlainNovelBodyAIService(FakeAIService):
    async def chat(self, messages, **kwargs):
        user_content = messages[-1].content
        if '"content"' in user_content and '"word_count"' in user_content:
            return LLMGenerationResult(
                success=True,
                content="The signal turned black, then recovered. Su Tangran backed up the evidence.",
                provider="fake",
                model="plain-body",
            )
        return await super().chat(messages, **kwargs)


class TruncatedJsonNovelBodyAIService(FakeAIService):
    async def chat(self, messages, **kwargs):
        user_content = messages[-1].content
        if '"content"' in user_content and '"word_count"' in user_content:
            return LLMGenerationResult(
                success=True,
                content=(
                    '{"chapter_number": 2, "title": "Counterproof", "content": '
                    '"Su Tangran said \\"remember the clue\\". The signal broke'
                ),
                provider="fake",
                model="truncated-json-body",
            )
        return await super().chat(messages, **kwargs)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Character.__table__.create(engine)
    CharacterStoryLink.__table__.create(engine)
    CreativeProject.__table__.create(engine)
    ProjectContent.__table__.create(engine)
    ProjectAssetLink.__table__.create(engine)
    ProjectGenerationLog.__table__.create(engine)
    with Session(engine) as session:
        yield session


@pytest.mark.asyncio
async def test_generate_outline_and_chapter_plan(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="", idea="smart short drama")

    outline = await service.generate_outline(project.id)
    plan = await service.generate_chapter_plan(project.id, chapter_count=2)

    refreshed = session.get(CreativeProject, project.id)
    assert refreshed is not None
    assert refreshed.title == "Smart short drama"
    assert refreshed.current_stage == "script"
    assert loads_json(refreshed.outline_json)["logline"].startswith("A video editor")
    assert outline["characters"][0]["name"] == "Lin Zhao"
    assert plan["chapter_count"] == 2
    assert plan["chapters"][0]["ending_hook"]

    contents = session.exec(select(ProjectContent)).all()
    assert {item.content_type for item in contents} == {"outline", "chapter_plan"}

    logs = session.exec(select(ProjectGenerationLog)).all()
    assert {log.stage for log in logs} == {"outline", "chapter_plan"}
    assert all(log.status == "success" for log in logs)


@pytest.mark.asyncio
async def test_generate_chapter_outline_novel_body_storyboard_and_comic_pages(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="", idea="smart short drama")

    await service.generate_outline(project.id)
    await service.generate_chapter_plan(project.id, chapter_count=2)
    chapter_outline = await service.generate_chapter_outline(project.id, chapter_number=1)
    novel_body = await service.generate_novel_body(project.id, chapter_number=1)
    script = await service.generate_script(project.id, chapter_number=1)
    script_content = session.exec(
        select(ProjectContent).where(ProjectContent.content_type == "script")
    ).first()
    assert script_content is not None
    storyboard = await service.generate_storyboard(project.id, content_id=script_content.id)
    comic_pages = await service.split_comic_pages(project.id, chapter_number=1, page_count=2)

    assert chapter_outline["scenes"][0]["image_prompt"]
    assert "Lin Zhao" in novel_body["content"]
    assert script["scenes"][0]["image_prompt"]
    assert storyboard["panels"][0]["image_prompt"]
    assert "medium shot" in storyboard["panels"][0]["image_prompt"]
    assert comic_pages["pages"][0]["content"].startswith("Page 1")

    contents = session.exec(select(ProjectContent)).all()
    content_types = {item.content_type for item in contents}
    assert {"chapter_outline", "novel_body", "script", "storyboard", "comic_pages"}.issubset(content_types)
    storyboard_content = next(item for item in contents if item.content_type == "storyboard")
    comic_content = next(item for item in contents if item.content_type == "comic_pages")
    assert comic_content.source_content_id == storyboard_content.id

    logs = session.exec(select(ProjectGenerationLog)).all()
    assert {"chapter_outline", "novel_body", "script", "storyboard", "comic_pages"}.issubset({log.stage for log in logs})


@pytest.mark.asyncio
async def test_generate_novel_body_wraps_plain_text_response(session: Session):
    service = CreativeProjectService(session, ai_service=PlainNovelBodyAIService())
    project = service.create_project(title="", idea="smart short drama")

    await service.generate_outline(project.id)
    await service.generate_chapter_plan(project.id, chapter_count=2)
    await service.generate_chapter_outline(project.id, chapter_number=2)
    novel_body = await service.generate_novel_body(project.id, chapter_number=2)

    assert novel_body["chapter_number"] == 2
    assert "Su Tangran" in novel_body["content"]
    assert novel_body["word_count"] == len(novel_body["content"])

    content = session.exec(
        select(ProjectContent).where(ProjectContent.content_type == "novel_body")
    ).first()
    assert content is not None
    assert "Su Tangran" in content.text_content

    logs = session.exec(select(ProjectGenerationLog).where(ProjectGenerationLog.stage == "novel_body")).all()
    assert logs[-1].status == "success_locally_repaired"
    assert "Su Tangran" in logs[-1].normalized_json


@pytest.mark.asyncio
async def test_generate_novel_body_salvages_truncated_json_content(session: Session):
    service = CreativeProjectService(session, ai_service=TruncatedJsonNovelBodyAIService())
    project = service.create_project(title="", idea="smart short drama")

    await service.generate_outline(project.id)
    await service.generate_chapter_plan(project.id, chapter_count=2)
    await service.generate_chapter_outline(project.id, chapter_number=2)
    novel_body = await service.generate_novel_body(project.id, chapter_number=2)

    assert novel_body["chapter_number"] == 2
    assert novel_body["title"] == "Counterproof"
    assert novel_body["content"].startswith("Su Tangran said")
    assert '"chapter_number"' not in novel_body["content"]
    assert 'remember the clue' in novel_body["content"]
    assert novel_body["word_count"] == len(novel_body["content"])

    logs = session.exec(select(ProjectGenerationLog).where(ProjectGenerationLog.stage == "novel_body")).all()
    assert logs[-1].status == "success_locally_repaired"


@pytest.mark.asyncio
async def test_generate_outline_does_not_repair_upstream_failure(session: Session):
    service = CreativeProjectService(session, ai_service=FailingAIService())
    project = service.create_project(title="failure test", idea="smart short drama")

    with pytest.raises(ValueError) as exc:
        await service.generate_outline(project.id)

    assert "403 Forbidden" in str(exc.value)
    assert "repair failed" not in str(exc.value)

    logs = session.exec(select(ProjectGenerationLog)).all()
    assert len(logs) == 1
    assert logs[0].status == "failed"
    assert "403 Forbidden" in logs[0].validation_error
    assert "repair failed" not in logs[0].validation_error


@pytest.mark.asyncio
async def test_generate_outline_repairs_malformed_json_locally(session: Session):
    service = CreativeProjectService(session, ai_service=BrokenJsonAIService())
    project = service.create_project(title="local repair test", idea="smart short drama")

    outline = await service.generate_outline(project.id)

    assert outline["title"] == "Locally repaired story"
    assert outline["characters"][0]["name"] == "Lin Zhao"

    logs = session.exec(select(ProjectGenerationLog)).all()
    assert len(logs) == 1
    assert logs[0].status == "success_locally_repaired"
    assert logs[0].validation_error == ""


def test_story_visual_context_uses_global_character_and_world_usage_overrides(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="霓虹测试", idea="cyber drama")
    character = Character(
        name="林昭",
        role="protagonist",
        appearance="黑色短发，凤眼",
        costume_hint="白衬衫",
        signature_items=json.dumps(["银色吊坠"], ensure_ascii=False),
        expressions=json.dumps(["冷静"], ensure_ascii=False),
        poses=json.dumps(["抱臂"], ensure_ascii=False),
        visual_consistency="吊坠不能丢",
        identity_json=json.dumps({"organization": "灰塔", "position": "情报商"}, ensure_ascii=False),
        behavior_json=json.dumps({"never_do": "不会无理由背叛交易"}, ensure_ascii=False),
    )
    session.add(character)
    session.flush()
    session.add(
        CharacterStoryLink(
            character_id=character.id,
            story_id=project.id,
            world_name="霓虹城",
            usage_role="反派盟友",
            local_identity="地下情报商",
            local_faction="灰塔",
            local_costume="黑色长风衣",
            local_prompt_tags=json.dumps(["赛博雨夜"], ensure_ascii=False),
            ooc_notes="不会主动暴露客户",
            off_model_notes="银色吊坠必须出现",
        )
    )
    session.commit()
    outline = {"characters": [{"name": "林昭", "role": "主角"}], "image_style_prompt": "冷色漫画"}

    profiles = service._project_character_production_profiles(project.id, outline)
    context = service._story_visual_context(outline, character_profiles=profiles)

    assert "地下情报商" in context
    assert "黑色长风衣" in context
    assert "不会主动暴露客户" in context
    assert "银色吊坠必须出现" in context


def test_enhance_storyboard_prompt_uses_world_usage_profile(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    data = {
        "panels": [
            {
                "panel_number": 1,
                "characters": ["林昭"],
                "action": "递出情报",
                "emotion": "克制",
                "image_prompt": "递出纸条",
            }
        ]
    }
    outline = {"characters": [{"name": "林昭", "appearance": "旧外貌"}], "image_style_prompt": "冷色漫画"}
    profiles = [
        {
            "name": "林昭",
            "local_identity": "地下情报商",
            "usage_role": "反派盟友",
            "age_range": "28岁",
            "appearance": "黑色短发，凤眼",
            "costume": "黑色长风衣",
            "visual_tags": "赛博雨夜",
            "signature_items": "银色吊坠",
            "visual_consistency": "银色吊坠必须出现",
            "ooc_rules": "不会主动暴露客户",
        }
    ]

    service._enhance_storyboard_image_prompts(data, outline, character_profiles=profiles)

    prompt = data["panels"][0]["image_prompt"]
    assert "地下情报商" in prompt
    assert "黑色长风衣" in prompt
    assert "银色吊坠必须出现" in prompt
    assert "不会主动暴露客户" in data["panels"][0]["negative_prompt"]


@pytest.mark.asyncio
async def test_generate_outline_uses_configured_system_template(session: Session):
    ai_service = CapturingAIService()
    service = CreativeProjectService(session, ai_service=ai_service)
    project = service.create_project(title="template test", idea="smart short drama")

    template_id = uuid.uuid4()
    service._resolve_prompt_template = lambda **_: SimpleNamespace(
        id=template_id,
        platform="creative_outline_custom",
        name="custom outline",
        template_scope="creative_project",
        template_stage="outline",
        system_template="You are the {project_type} editor. Output JSON only.",
        outline_template="Create outline JSON for {project_title}: {idea}",
    )

    await service.generate_outline(project.id)

    assert ai_service.messages[0].role == "system"
    assert ai_service.messages[0].content == "You are the short_drama editor. Output JSON only."
    assert "template test" in ai_service.messages[1].content


def test_link_asset_records_project_relationship(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="asset link", idea="smart short drama")

    link = service.link_asset(project_id=project.id, asset_id="asset-1", role="reference", relation="uses")

    assert isinstance(link, ProjectAssetLink)
    assert link.project_id == project.id
    assert link.asset_id == "asset-1"
