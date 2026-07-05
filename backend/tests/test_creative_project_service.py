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


def long_test_body(prefix: str = "Lin Zhao") -> str:
    paragraphs = []
    actions = ["停住", "回看", "标记", "截取", "备份", "核对", "压低", "翻转", "记录", "锁屏"]
    for index in range(1, 46):
        action = actions[index % len(actions)]
        paragraphs.append(
            (
                f"{prefix}在第{index}次确认时间线时{action}了手。第{index}处屏幕水印只闪了一帧，"
                f"却足够把匿名包裹、旧照片和公司档案库连成同一条线。第{index}轮判断里她没有立刻喊人，"
                f"先把原始文件复制到离线硬盘，又把桌上的钥匙压在照片边缘，像压住一个随时会翻面的证词。"
                f"第{index}次脚步声从走廊经过时，她把呼吸放轻，等声音远了，才在便签上写下可核验的疑点。"
            )
        )
    return "\n\n".join(paragraphs)


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
            content = long_test_body("Lin Zhao")
            return self._result(
                {
                    "chapter_number": 1,
                    "title": "Entry",
                    "content": content,
                    "word_count": len(content),
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
        self.last_user_content = ""

    async def chat(self, messages, **kwargs):
        self.messages = messages
        self.last_user_content = messages[-1].content
        return await super().chat(messages, **kwargs)


class PlainNovelBodyAIService(FakeAIService):
    async def chat(self, messages, **kwargs):
        user_content = messages[-1].content
        if "质量不达标的输出" in user_content:
            content = "Su Tangran said remember the clue。\n\n" + long_test_body("Su Tangran")
            return LLMGenerationResult(
                success=True,
                content=json.dumps(
                    {
                        "chapter_number": 2,
                        "title": "Counterproof",
                        "content": content,
                        "word_count": len(content),
                        "continuity_notes": ["Su Tangran backs up the evidence."],
                    },
                    ensure_ascii=False,
                ),
                provider="fake",
                model="plain-body",
            )
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
        if "质量不达标的输出" in user_content:
            content = "Su Tangran said remember the clue。\n\n" + long_test_body("Su Tangran")
            return LLMGenerationResult(
                success=True,
                content=json.dumps(
                    {
                        "chapter_number": 2,
                        "title": "Counterproof",
                        "content": content,
                        "word_count": len(content),
                        "continuity_notes": ["Su Tangran keeps the clue."],
                    },
                    ensure_ascii=False,
                ),
                provider="fake",
                model="truncated-json-body",
            )
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


class WriterRoomAIService(FakeAIService):
    async def chat(self, messages, **kwargs):
        user_content = messages[-1].content

        if '"scene_beats"' in user_content and '"dramatic_question"' in user_content:
            return self._result(
                {
                    "chapter_number": 1,
                    "title": "Entry",
                    "summary": "Lin receives the package and chooses to investigate.",
                    "scene_beats": [
                        {
                            "scene_number": 1,
                            "title": "Package",
                            "purpose": "Push Lin from observer to actor.",
                            "location": "editing room",
                            "characters": ["Lin Zhao"],
                            "dramatic_question": "Will Lin ignore the clue?",
                            "character_wants": ["Lin wants proof before acting."],
                            "obstacle": "The package has no sender.",
                            "conflict_pressure": "The clue can implicate her employer.",
                            "action_beats": ["Lin shuts down the timeline.", "She cuts the tape with a key."],
                            "subtext": "She is afraid this is personal.",
                            "sensory_anchors": ["plastic tape", "monitor hum"],
                            "turning_point": "The photo shows a company watermark.",
                            "hook": "A childhood photo slides out.",
                        }
                    ],
                    "continuity_notes": ["Lin must trace the watermark next."],
                }
            )

        if '"scene_rehearsals"' in user_content:
            return self._result(
                {
                    "chapter_number": 1,
                    "title": "Entry",
                    "scene_rehearsals": [
                        {
                            "scene_number": 1,
                            "conflict": "Lin wants certainty while the evidence forces urgency.",
                            "usable_moments": ["Lin hides the photo when footsteps pass the door."],
                        }
                    ],
                    "character_reactions": [
                        {
                            "character": "Lin Zhao",
                            "public_goal": "Finish the edit.",
                            "private_goal": "Verify the package without alerting coworkers.",
                            "fear": "Being manipulated by a fake clue.",
                            "knows": "The watermark belongs to the company archive.",
                            "hides": "She recognizes the child in the photo.",
                            "likely_action": "She copies the file before calling anyone.",
                            "likely_dialogue": ["This is not a script."],
                            "subtext": "She needs time before trusting the clue.",
                            "voice_rules": ["Short, evidence-driven lines."],
                        }
                    ],
                    "usable_conflicts": ["Evidence vs. self-protection"],
                    "continuity_notes": ["Lin should not accuse anyone yet."],
                }
            )

        if '"overall_score"' in user_content and '"ai_smell_score"' in user_content:
            return self._result(
                {
                    "chapter_number": 1,
                    "title": "Entry",
                    "overall_score": 72,
                    "ai_smell_score": 38,
                    "quality_tags": ["动作明确", "钩子可加强"],
                    "ai_smell_checks": ["直接情绪标签较少", "物件互动可再补"],
                    "strengths": ["证据链清楚"],
                    "issues": [
                        {
                            "severity": "medium",
                            "category": "钩子",
                            "location": "结尾",
                            "problem": "悬念还不够锋利。",
                            "suggestion": "把公司水印提前压到最后一句。",
                            "rewrite_instruction": "加强结尾钩子，保留证据链。",
                        }
                    ],
                    "rewrite_plan": ["压缩解释", "增强结尾钩子"],
                    "approval_recommendation": "建议重写后提升",
                }
            )

        if "完整重写正文" in user_content:
            return self._result(
                {
                    "chapter_number": 1,
                    "title": "Entry",
                    "content": "Lin Zhao cut the tape with her key. The final photo carried the company's watermark.",
                    "word_count": 83,
                    "continuity_notes": ["The watermark becomes the next clue."],
                }
            )

        if "完整润色正文" in user_content:
            return self._result(
                {
                    "chapter_number": 1,
                    "title": "Entry",
                    "content": "Lin Zhao shut down the timeline, waited for the monitor hum to settle, and opened the package.",
                    "word_count": 94,
                    "continuity_notes": ["Lin keeps the package secret."],
                }
            )

        if "正文初稿" in user_content and '"word_count"' in user_content:
            return self._result(
                {
                    "chapter_number": 1,
                    "title": "Entry",
                    "content": "Lin Zhao shuts down the timeline and opens the anonymous package.",
                    "word_count": 65,
                    "continuity_notes": ["Lin starts suspecting the production company."],
                }
            )

        return await super().chat(messages, **kwargs)

    def _result(self, content: dict) -> LLMGenerationResult:
        return LLMGenerationResult(
            success=True,
            content=json.dumps(content, ensure_ascii=False),
            provider="deepseek",
            model="deepseek-v4-pro",
        )


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
async def test_sync_project_bible_creates_editable_cards_without_duplicates(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="", idea="smart short drama")

    await service.generate_outline(project.id)
    created = service.sync_project_bible(project.id)
    second_pass = service.sync_project_bible(project.id)

    assert created
    assert second_pass == []
    content_types = {item.content_type for item in created}
    assert {"project_bible", "world_asset"}.issubset(content_types)
    assert any(loads_json(item.data_json).get("section_key") == "worldview" for item in created)
    assert any(loads_json(item.data_json).get("role") == "location" for item in created)
    assert all(item.is_locked is False for item in created)


@pytest.mark.asyncio
async def test_locked_project_bible_context_is_injected_into_chapter_outline_prompt(session: Session):
    ai_service = CapturingAIService()
    service = CreativeProjectService(session, ai_service=ai_service)
    project = service.create_project(title="", idea="smart short drama")

    await service.generate_outline(project.id)
    await service.generate_chapter_plan(project.id, chapter_count=2)
    service.sync_project_bible(project.id)

    world_asset = session.exec(
        select(ProjectContent).where(ProjectContent.content_type == "world_asset")
    ).first()
    assert world_asset is not None
    data = loads_json(world_asset.data_json)
    data["summary"] = "Every reversal must have an evidence chain."
    data["details"] = "No magic shortcuts; every twist needs a verifiable clue."
    service.update_content(
        project_id=project.id,
        content_id=world_asset.id,
        data=data,
        text_content="No magic shortcuts; every twist needs a verifiable clue.",
        is_locked=True,
    )

    await service.generate_chapter_outline(project.id, chapter_number=1)

    assert "已锁定项目圣经/世界资产" in ai_service.last_user_content
    assert "No magic shortcuts" in ai_service.last_user_content


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
async def test_writer_room_step_saves_content_and_generation_log(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="", idea="smart short drama")
    await service.generate_outline(project.id)
    await service.generate_chapter_plan(project.id, chapter_count=2)
    await service.generate_chapter_outline(project.id, chapter_number=1)

    service.ai_service = WriterRoomAIService()
    content = await service.run_writer_room_step(
        project.id,
        step="scene_beats",
        chapter_number=1,
        provider="deepseek",
        model="deepseek-v4-pro",
    )

    assert content.content_type == "scene_beats"
    assert content.chapter_number == 1
    assert "Lin receives the package" in content.text_content
    assert loads_json(content.data_json)["writer_room"]["step"] == "scene_beats"

    log = session.exec(select(ProjectGenerationLog).where(ProjectGenerationLog.stage == "scene_beats")).one()
    assert log.status == "success"
    assert log.provider == "deepseek"
    assert log.model == "deepseek-v4-pro"
    assert "scene_beats" in log.normalized_json


@pytest.mark.asyncio
async def test_writer_room_promote_creates_new_novel_body_version_without_overwriting_old(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="", idea="smart short drama")
    await service.generate_outline(project.id)
    await service.generate_chapter_plan(project.id, chapter_count=2)
    await service.generate_chapter_outline(project.id, chapter_number=1)
    original_body = service._create_content(
        project_id=project.id,
        content_type="novel_body",
        chapter_number=1,
        episode_number=1,
        title="Entry",
        data={
            "chapter_number": 1,
            "title": "Entry",
            "content": "Original readable prose that should remain in history.",
            "word_count": 52,
        },
        text_content="Original readable prose that should remain in history.",
    )
    session.commit()
    session.refresh(original_body)

    service.ai_service = WriterRoomAIService()
    rewrite = await service.run_writer_room_step(
        project.id,
        step="prose_rewrite",
        chapter_number=1,
        content_id=session.exec(select(ProjectContent).where(ProjectContent.content_type == "novel_body")).first().id,
        instruction="加强结尾钩子",
        provider="deepseek",
        model="deepseek-v4-pro",
    )
    promoted = service.promote_writer_room_content(project.id, content_id=rewrite.id)

    assert promoted.content_type == "novel_body"
    assert promoted.version == 2
    assert promoted.source_content_id == rewrite.id
    assert "company's watermark" in promoted.text_content

    bodies = session.exec(select(ProjectContent).where(ProjectContent.content_type == "novel_body")).all()
    assert len(bodies) == 2
    assert any(item.version == 1 and item.text_content == original_body.text_content for item in bodies)
    assert loads_json(promoted.data_json)["promoted_from_content_id"] == rewrite.id


@pytest.mark.asyncio
async def test_writer_room_run_humanizes_without_overwriting_existing_novel_body(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="", idea="smart short drama")
    await service.generate_outline(project.id)
    await service.generate_chapter_plan(project.id, chapter_count=2)
    await service.generate_chapter_outline(project.id, chapter_number=1)
    original_body = service._create_content(
        project_id=project.id,
        content_type="novel_body",
        chapter_number=1,
        episode_number=1,
        title="Entry",
        data={
            "chapter_number": 1,
            "title": "Entry",
            "content": "Original approved prose remains untouched.",
            "word_count": 39,
        },
        text_content="Original approved prose remains untouched.",
    )
    session.commit()
    session.refresh(original_body)

    service.ai_service = WriterRoomAIService()
    result = await service.run_writer_room(
        project.id,
        steps=["scene_beats", "character_rehearsal", "prose_draft", "prose_humanized", "prose_review"],
        chapter_number=1,
        provider="deepseek",
        model="deepseek-v4-pro",
    )

    assert result["summary"] == {"total": 5, "success": 5, "failed": 0}
    humanized = session.exec(select(ProjectContent).where(ProjectContent.content_type == "prose_humanized")).one()
    assert "monitor hum" in humanized.text_content

    bodies = session.exec(select(ProjectContent).where(ProjectContent.content_type == "novel_body")).all()
    assert len(bodies) == 1
    assert bodies[0].id == original_body.id
    assert bodies[0].text_content == "Original approved prose remains untouched."

    logs = session.exec(select(ProjectGenerationLog)).all()
    stages = {log.stage for log in logs}
    assert {"scene_beats", "character_rehearsal", "prose_draft", "prose_humanized", "prose_review"}.issubset(stages)
    review_log = next(log for log in logs if log.stage == "prose_review")
    assert review_log.prompt
    assert review_log.raw_response
    assert "加强结尾钩子" in review_log.normalized_json


@pytest.mark.asyncio
async def test_writer_room_review_outputs_actionable_rewrite_issue(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="", idea="smart short drama")
    await service.generate_outline(project.id)
    await service.generate_chapter_plan(project.id, chapter_count=2)
    await service.generate_chapter_outline(project.id, chapter_number=1)
    source = service._create_content(
        project_id=project.id,
        content_type="novel_body",
        chapter_number=1,
        episode_number=1,
        title="Entry",
        data={"content": "Draft prose for review."},
        text_content="Draft prose for review.",
    )
    session.commit()
    session.refresh(source)

    service.ai_service = WriterRoomAIService()
    review = await service.run_writer_room_step(
        project.id,
        step="prose_review",
        chapter_number=1,
        content_id=source.id,
        provider="deepseek",
        model="deepseek-v4-pro",
    )

    data = loads_json(review.data_json)
    issue = data["issues"][0]
    assert issue["location"] == "结尾"
    assert issue["problem"]
    assert issue["rewrite_instruction"] == "加强结尾钩子，保留证据链。"
    assert "钩子可加强" in data["quality_tags"]


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
