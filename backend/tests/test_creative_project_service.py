from __future__ import annotations

import json
import math
import uuid
from types import SimpleNamespace

import pytest
from sqlmodel import Session, create_engine, select

from app.api.v1.creative_projects import serialize_content
from app.db.models.creative_project import (
    CreativeProject,
    ProjectAssetLink,
    ProjectContent,
    ProjectContinuityCandidate,
    ProjectNarrativeRun,
    ProjectNarrativeContextSnapshot,
    ProjectNarrativeSnapshot,
    ProjectStoryEvent,
    ProjectForeshadowing,
    ProjectStyleMeasurement,
    ProjectGenerationLog,
)
from app.db.models.character import Character, CharacterStoryLink
from app.services.ai.types import LLMGenerationResult
from app.services.creative_project.schemas import (
    NovelBodySchema,
    StoryboardPanelSchema,
    WriterRoomProseReviewSchema,
)
from app.services.creative_project.semantic_recall import NarrativeRecallResult
from app.services.creative_project.service import (
    CreativeProjectService,
    loads_json,
    normalize_chapter_plan,
    repair_utf8_mojibake,
    writer_room_allows_length_expansion,
    writer_room_effective_instruction,
    writer_room_output_max_tokens,
    writer_room_requested_maximum_characters,
    writer_room_requested_minimum_characters,
)


def test_normalize_chapter_plan_uses_valid_unique_rows_and_keeps_legacy_count():
    normalized = normalize_chapter_plan(
        {
            "chapter_count": 18,
            "chapters": [
                {"chapter_number": 1},
                {"chapter_number": "2"},
                {"chapter_number": 2},
                {"chapter_number": 0},
                {"title": "missing number"},
            ],
        }
    )

    assert normalized["chapter_count"] == 2
    assert normalized["legacy_chapter_count"] == 18


def test_pipeline_chapters_do_not_fall_back_to_stale_count_when_plan_has_invalid_rows(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="Invalid plan", idea="Do not make ghost chapters")
    project.chapter_plan_json = json.dumps(
        {"chapter_count": 18, "chapters": [{"chapter_number": 0}]}
    )
    session.add(project)
    session.commit()

    assert service._normalize_pipeline_chapters(project, chapters=None, chapter_count=None) == [1]


def test_repair_utf8_mojibake_repairs_nested_legacy_project_data():
    original = "短剧但是不降智"
    twice_garbled = original.encode("utf-8").decode("latin-1").encode("utf-8").decode("latin-1")

    repaired = repair_utf8_mojibake({"outline": {"title": twice_garbled, "genre": [twice_garbled]}})

    assert repaired == {"outline": {"title": original, "genre": [original]}}


def test_loads_json_repairs_legacy_project_data_at_read_boundary():
    original = "短剧但是不降智"
    garbled = original.encode("utf-8").decode("latin-1")

    loaded = loads_json(json.dumps({"title": garbled}, ensure_ascii=False))

    assert loaded == {"title": original}


def test_serialize_content_repairs_legacy_text_fields_for_the_ui():
    original = "短剧但是不降智"
    garbled = original.encode("utf-8").decode("latin-1")
    content = ProjectContent(
        project_id="project",
        content_type="outline",
        title=garbled,
        data_json=json.dumps({"title": garbled}, ensure_ascii=False),
        text_content=garbled,
    )

    serialized = serialize_content(content)

    assert serialized["title"] == original
    assert serialized["data"] == {"title": original}
    assert serialized["text_content"] == original


def test_update_project_repairs_legacy_project_text(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="Encoding", idea="encoding test")
    original = "短剧但是不降智"
    garbled = original.encode("utf-8").decode("latin-1")

    updated = service.update_project(project.id, {"outline": {"title": garbled}})

    assert updated is not None
    assert loads_json(updated.outline_json)["title"] == original


def test_project_export_keeps_content_versions_and_asset_lineage(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(
        title="Export project",
        idea="A project that can leave the workspace",
        settings={"tone": "quiet"},
    )
    first = ProjectContent(
        project_id=project.id,
        content_type="novel_body",
        chapter_number=1,
        title="First chapter",
        text_content="The first approved version.",
        data_json=json.dumps({"continuity_notes": ["keep the key"]}),
        version=1,
    )
    rewrite = ProjectContent(
        project_id=project.id,
        content_type="prose_humanized",
        chapter_number=1,
        title="First chapter candidate",
        text_content="The candidate retains the key.",
        source_content_id=first.id,
        version=2,
    )
    session.add(first)
    session.add(rewrite)
    session.flush()
    session.add(ProjectAssetLink(
        project_id=project.id,
        asset_id="asset-portrait-1",
        content_id=rewrite.id,
        role="character",
        relation="references",
        metadata_json=json.dumps({"character_name": "Lin"}),
    ))
    session.commit()

    exported = service.build_project_export(project.id)

    assert exported["format"] == "ylcraft-creative-project-export/v1"
    assert exported["project"]["id"] == project.id
    settings = exported["project"]["settings"]
    assert settings["tone"] == "quiet"
    assert settings["production_profile"] == "vertical_drama"
    assert settings["production_profile_version"] == 1
    assert {content["id"] for content in exported["contents"]} == {first.id, rewrite.id}
    candidate = next(content for content in exported["contents"] if content["id"] == rewrite.id)
    assert candidate["source_content_id"] == first.id
    assert exported["asset_manifest"] == [{
        "asset_id": "asset-portrait-1",
        "content_id": rewrite.id,
        "role": "character",
        "relation": "references",
        "metadata": {"character_name": "Lin"},
        "created_at": exported["asset_manifest"][0]["created_at"],
    }]


def test_extract_continuity_candidates_is_non_destructive_and_idempotent(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="Continuity", idea="test")
    source = ProjectContent(
        project_id=project.id,
        content_type="novel_body",
        chapter_number=2,
        data_json=json.dumps({"continuity_notes": ["钥匙不能离开旧仓库", "苏棠已经知道真相"]}),
        text_content="正文",
    )
    session.add(source)
    session.commit()

    first = service.extract_continuity_candidates(project.id, source.id)
    second = service.extract_continuity_candidates(project.id, source.id)

    assert len(first) == 2
    assert {item.id for item in first} == {item.id for item in second}
    assert all(loads_json(item.data_json)["status"] == "candidate" for item in first)
    assert all(item.source_content_id == source.id for item in first)
    assert session.get(ProjectContent, source.id).text_content == "正文"


def test_check_continuity_finds_conflict_with_locked_fact(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="Conflict", idea="test")

    # 锁定事实：主角 28 岁
    locked_fact = ProjectContent(
        project_id=project.id,
        content_type="project_bible",
        chapter_number=1,
        title="林昭年龄",
        text_content="林昭今年 28 岁，是剪辑师。",
        data_json=json.dumps(
            {
                "fact": "林昭今年 28 岁，是剪辑师。",
                "entity_type": "character",
                "entity_name": "林昭",
                "claim": "林昭今年 28 岁",
            }
        ),
        is_locked=True,
        version=1,
    )
    # 正文候选：写主角 35 岁，触发冲突
    body = ProjectContent(
        project_id=project.id,
        content_type="novel_body",
        chapter_number=2,
        title="第二章",
        text_content="林昭已经 35 岁了，在旧仓库整理胶片。",
        data_json=json.dumps({"chapter_number": 2, "word_count": 20}),
        version=1,
    )
    session.add(locked_fact)
    session.add(body)
    session.commit()

    result = service.check_continuity(project.id, chapter_number=2)

    assert result["project_id"] == project.id
    assert result["chapter_number"] == 2
    assert result["skipped"] is False
    assert len(result["conflicts"]) >= 1
    conflict = result["conflicts"][0]
    assert conflict["contradicting_fact_id"] == locked_fact.id
    assert "林昭" in conflict["contradicting_fact_excerpt"]
    assert conflict["suggested_action"] in {"resolve_conflict", "rewrite_excerpt"}


def test_check_continuity_with_candidate_entity(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="Conflict candidate", idea="test")

    locked_fact = ProjectContent(
        project_id=project.id,
        content_type="world_asset",
        title="钥匙",
        text_content="钥匙不能离开旧仓库。",
        data_json=json.dumps(
            {
                "fact": "钥匙不能离开旧仓库",
                "entity_type": "item",
                "entity_name": "钥匙",
                "claim": "钥匙不能离开旧仓库",
            }
        ),
        is_locked=True,
        version=1,
    )
    source = ProjectContent(
        project_id=project.id,
        content_type="novel_body",
        chapter_number=3,
        text_content="正文",
        data_json=json.dumps({"chapter_number": 3}),
        version=1,
    )
    session.add(locked_fact)
    session.add(source)
    session.commit()

    candidate = ProjectContinuityCandidate(
        project_id=project.id,
        source_content_id=source.id,
        source_kind="prose_review",
        source_fingerprint="fp1",
        entity_type="item",
        entity_name="钥匙",
        claim="林昭把钥匙带出了旧仓库",
        evidence_excerpt="林昭把钥匙放进了口袋，走出仓库。",
        evidence_anchor_json=json.dumps({"chapter_number": 3, "paragraph_index": 1}),
        severity="warning",
        suggested_action="resolve_conflict",
        target_fact_type="world_asset",
        status="pending",
    )
    session.add(candidate)
    session.commit()

    result = service.check_continuity(project.id, chapter_number=3, candidate_id=candidate.id)

    assert result["candidate_id"] == candidate.id
    assert result["skipped"] is False
    assert any(c["contradicting_fact_id"] == locked_fact.id for c in result["conflicts"])


def test_check_continuity_is_project_isolated(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project_a = service.create_project(title="A", idea="test")
    project_b = service.create_project(title="B", idea="test")

    fact_b = ProjectContent(
        project_id=project_b.id,
        content_type="project_bible",
        title="B 事实",
        text_content="B 项目专属事实",
        data_json=json.dumps({"fact": "B 项目专属事实"}),
        is_locked=True,
        version=1,
    )
    body_a = ProjectContent(
        project_id=project_a.id,
        content_type="novel_body",
        chapter_number=1,
        title="A 正文",
        text_content="B 项目专属事实出现在 A 项目，这只是文本重叠。",
        data_json=json.dumps({}),
        version=1,
    )
    session.add(fact_b)
    session.add(body_a)
    session.commit()

    result = service.check_continuity(project_a.id, chapter_number=1)

    # A 项目检查不应把 B 项目事实作为 contradicting fact
    assert all(c["contradicting_fact_id"] != fact_b.id for c in result["conflicts"])


@pytest.mark.asyncio
async def test_rewrite_paragraph_creates_candidate_version(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="Rewrite", idea="test")

    body = ProjectContent(
        project_id=project.id,
        content_type="novel_body",
        chapter_number=1,
        title="第一章",
        text_content="第一段：林昭走进剪辑室。\n\n第二段：她打开匿名包裹。\n\n第三段：一张照片滑了出来。",
        data_json=json.dumps({"chapter_number": 1, "word_count": 40}),
        version=1,
    )
    session.add(body)
    session.commit()

    result = await service.rewrite_paragraph(
        project.id,
        body.id,
        paragraph_index=1,
        instruction="让林昭更紧张",
    )

    assert result["project_id"] == project.id
    assert result["source_content_id"] == body.id
    assert result["paragraph_index"] == 1
    assert result["anchor_not_found"] is False
    assert result["status"] == "candidate"
    assert "重写结果" in result["rewritten_paragraph"]
    candidate_id = result["candidate_content_id"]
    assert candidate_id is not None

    candidate = session.get(ProjectContent, candidate_id)
    assert candidate is not None
    assert candidate.content_type == "prose_rewrite"
    assert candidate.source_content_id == body.id
    # 原文不被覆盖
    assert body.text_content == "第一段：林昭走进剪辑室。\n\n第二段：她打开匿名包裹。\n\n第三段：一张照片滑了出来。"


@pytest.mark.asyncio
async def test_rewrite_paragraph_returns_anchor_not_found(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="Rewrite missing", idea="test")

    body = ProjectContent(
        project_id=project.id,
        content_type="novel_body",
        chapter_number=1,
        title="第一章",
        text_content="只有一段。",
        data_json=json.dumps({"chapter_number": 1}),
        version=1,
    )
    session.add(body)
    session.commit()

    result = await service.rewrite_paragraph(
        project.id,
        body.id,
        paragraph_index=5,
        instruction="无论如何重写",
    )

    assert result["anchor_not_found"] is True
    assert result["status"] == "anchor_not_found"
    assert result["candidate_content_id"] is None


@pytest.mark.asyncio
async def test_pipeline_persists_step_diagnostics_for_skipped_stage(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="Pipeline diagnostics", idea="test")
    project.outline_json = json.dumps({"title": "already exists"})
    session.add(project)
    session.commit()

    result = await service.run_pipeline(
        project.id,
        stages=["outline"],
        provider="configured-provider",
        model="configured-model",
        template_id="creative-outline-template",
        skip_existing=True,
    )

    log = session.exec(
        select(ProjectGenerationLog)
        .where(ProjectGenerationLog.project_id == project.id)
        .where(ProjectGenerationLog.scene == "pipeline")
    ).one()
    diagnostics = loads_json(log.request_json)
    assert result["summary"] == {"total": 1, "generated": 0, "skipped": 1, "failed": 0}
    assert log.stage == "outline"
    assert log.status == "skipped"
    assert log.provider == "configured-provider"
    assert log.model == "configured-model"
    assert diagnostics["template_id"] == "creative-outline-template"
    assert isinstance(diagnostics["duration_ms"], int)


@pytest.mark.asyncio
async def test_pipeline_continues_after_one_chapter_step_fails(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="Pipeline recovery", idea="test")

    async def fake_generate_script(project_id: str, *, chapter_number: int, **_kwargs):
        if chapter_number == 1:
            raise ValueError("chapter 1 script failed")
        return {"title": "Chapter 2 script"}

    service.generate_script = fake_generate_script
    result = await service.run_pipeline(
        project.id,
        stages=["script"],
        chapters=[1, 2],
        skip_existing=False,
        continue_on_error=True,
    )

    assert result["summary"] == {"total": 2, "generated": 1, "skipped": 0, "failed": 1}
    assert result["results"][0]["status"] == "failed"
    assert result["results"][1]["status"] == "generated"
    logs = session.exec(
        select(ProjectGenerationLog)
        .where(ProjectGenerationLog.project_id == project.id)
        .where(ProjectGenerationLog.scene == "pipeline")
        .order_by(ProjectGenerationLog.created_at)
    ).all()
    assert len(logs) == 2
    assert logs[0].status == "failed"
    assert logs[0].validation_error == "chapter 1 script failed"
    assert logs[1].status == "generated"


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


def test_novel_body_parser_normalizes_body_alias(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())

    data = service._parse_and_validate(
        json.dumps(
            {
                "chapter_number": 1,
                "title": "Alias response",
                "body": "A complete chapter returned under the provider body alias.",
            }
        ),
        NovelBodySchema,
    )

    assert data["content"] == "A complete chapter returned under the provider body alias."


def test_novel_body_fallback_recovers_unescaped_long_json_content(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    raw_response = '''模型输出如下：
{
  "chapter_number": 12,
  "title": "无私的博弈",
  "content": "苏棠把门卡扣在掌心，抬头时听见走廊有人说 \"别回头\"。

她没有照做，反而把录音笔塞进桌脚缝里。",
  "word_count": 58,
  "continuity_notes": ["下一章追查录音来源"]
}'''

    data = service._wrap_plain_novel_body_response(raw_response, "第 12 章续写", NovelBodySchema)

    assert data["chapter_number"] == 12
    assert data["title"] == "无私的博弈"
    assert '有人说 "别回头"' in data["content"]
    assert "录音笔塞进桌脚缝里" in data["content"]


@pytest.mark.asyncio
async def test_writer_room_persists_actual_character_count_not_model_claim(session: Session):
    body = long_test_body("Actual length")

    class InflatedCountAIService:
        async def chat(self, messages, **kwargs):
            return LLMGenerationResult(
                success=True,
                content=json.dumps(
                    {
                        "chapter_number": 1,
                        "title": "Actual count",
                        "content": body,
                        "word_count": 1,
                    }
                ),
                provider="fake",
                model="fake-model",
            )

    service = CreativeProjectService(session, ai_service=InflatedCountAIService())
    project = service.create_project(title="", idea="count test")
    service.update_project(project.id, {"outline": {"title": "Count", "characters": []}})
    service.update_project(
        project.id,
        {"chapter_plan": {"chapter_count": 1, "chapters": [{"chapter_number": 1, "title": "Count"}]}},
    )
    service._create_content(
        project_id=project.id,
        content_type="chapter_outline",
        chapter_number=1,
        episode_number=1,
        title="Count",
        data={"chapter_number": 1, "title": "Count", "summary": "scene"},
        text_content="scene",
    )

    content = await service.run_writer_room_step(
        project.id,
        step="prose_rewrite",
        chapter_number=1,
        provider="fake",
        model="fake-model",
    )

    assert loads_json(content.data_json)["word_count"] == len(body)


async def test_writer_room_watermark_clean_is_optional_and_promotable(session: Session):
    """Layer B watermark-clean must be opt-in, produce a prose candidate, and be promotable."""
    from app.services.creative_project.service import DEFAULT_WRITER_ROOM_STEPS, WRITER_ROOM_STEP_ORDER

    # The optional step is registered but deliberately excluded from the default chain.
    assert "prose_watermark_clean" in WRITER_ROOM_STEP_ORDER
    assert "prose_watermark_clean" not in DEFAULT_WRITER_ROOM_STEPS

    body = long_test_body("Watermark")
    service = CreativeProjectService(session, ai_service=FakeAIService())
    # _normalize_writer_room_step accepts the new step and its alias.
    assert service._normalize_writer_room_step("watermark_clean") == "prose_watermark_clean"

    project = service.create_project(title="", idea="watermark clean")
    service.update_project(project.id, {"outline": {"title": "W", "characters": []}})
    service.update_project(
        project.id,
        {"chapter_plan": {"chapter_count": 1, "chapters": [{"chapter_number": 1, "title": "W"}]}},
    )
    draft = service._create_content(
        project_id=project.id,
        content_type="prose_draft",
        chapter_number=1,
        episode_number=1,
        title="W",
        data={"chapter_number": 1, "title": "W", "content": body},
        text_content=body,
    )

    content = await service.run_writer_room_step(
        project.id,
        step="prose_watermark_clean",
        chapter_number=1,
        content_id=draft.id,
        provider="fake",
        model="fake-model",
    )

    assert content.content_type == "prose_watermark_clean"
    assert content.source_content_id == draft.id
    data = loads_json(content.data_json)
    assert data["content"].strip()
    # The watermark step keeps the same prose source; the guard only rejects
    # collapses below 88% of the source word count.
    assert len(data["content"]) >= (len(body) * 88) // 100

    promoted = service.promote_writer_room_content(project.id, content_id=content.id)
    assert promoted.content_type == "novel_body"
    assert promoted.source_content_id == content.id
    assert promoted.text_content.strip()


def test_writer_room_review_normalizes_nested_chapter_review(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())

    review = service._normalize_writer_room_review(
        {
            "chapter_review": {
                "issues": [
                    {
                        "position": "第 1 段",
                        "problem_type": "AI腔",
                        "detail": "删去说明性语句。",
                        "rewrite_instruction": "改为动作与停顿。",
                    }
                ]
            }
        }
    )

    assert review["issues"][0] == {
        "severity": "high",
        "category": "AI腔",
        "location": "第 1 段",
        "problem": "删去说明性语句。",
        "suggestion": "删去说明性语句。",
        "rewrite_instruction": "改为动作与停顿。",
    }
    assert review["overall_score"] == 67
    assert review["ai_smell_score"] == 51


def test_writer_room_review_normalizes_blank_recommendation_to_rewrite(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())

    review = service._normalize_writer_room_review(
        {
            "overall_score": 39,
            "approval_recommendation": "",
            "quality_tags": ["说明腔", "对话工整"],
            "ai_smell_checks": ["术语压过动作", "意象堆叠"],
            "issues": [
                {
                    "severity": "high",
                    "category": "AI腔",
                    "location": "开场",
                    "problem": "设定说明压过人物动作。",
                    "suggestion": "用动作带出规则。",
                }
            ],
        }
    )

    assert review["approval_recommendation"] == "建议重写"


def test_writer_room_review_parser_coerces_object_checklists(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())

    review = service._parse_and_validate(
        json.dumps(
            {
                "chapter_number": 4,
                "title": "Review variant",
                "overall_score": 72,
                "ai_smell_score": 63,
                "quality_tags": {"rhythm": "tight", "dialogue": "natural"},
                "ai_smell_checks": {
                    "metaphor_density": "high: replace abstract comparisons with physical action",
                    "voice_drift": "medium: keep the antagonist evasive",
                },
                "strengths": {"plot": "evidence chain is clear"},
                "rewrite_plan": {"first": "cut explanatory paragraphs"},
                "issues": {"location": "paragraph 3", "problem": "explains motive directly"},
            }
        ),
        WriterRoomProseReviewSchema,
    )

    assert review["ai_smell_checks"] == [
        "metaphor_density: high: replace abstract comparisons with physical action",
        "voice_drift: medium: keep the antagonist evasive",
    ]
    assert review["quality_tags"] == ["rhythm: tight", "dialogue: natural"]
    assert review["issues"][0]["location"] == "paragraph 3"


def test_writer_room_review_checklist_only_is_not_a_blocking_issue(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())

    review = service._normalize_writer_room_review(
        {
            "overall_score": 72,
            "ai_smell_score": 35,
            "ai_smell_checks": ["第 2 段有一个泛化比喻"],
        }
    )

    assert review["issues"][0]["severity"] == "medium"
    assert review["approval_recommendation"] == "建议提升"


def test_writer_room_review_restores_complete_chapter_baseline_without_high_issue(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())

    review = service._normalize_writer_room_review(
        {
            "overall_score": 39,
            "issues": [{"severity": "medium", "category": "AI味", "problem": "语气偏解释"}],
        }
    )

    assert review["overall_score"] == 70
    assert review["approval_recommendation"] == "建议提升"


def test_writer_room_review_rejects_empty_json_as_non_substantive(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())

    review = service._normalize_writer_room_review({})

    assert review["approval_recommendation"] == "建议重写"
    assert not service._writer_room_review_has_substance(review)


def test_writer_room_review_accepts_evidenced_promotion(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    review = service._normalize_writer_room_review(
        {
            "overall_score": 74,
            "ai_smell_score": 18,
            "quality_tags": ["动作推进清晰", "结尾有钩子"],
            "ai_smell_checks": ["开篇以门锁声切入", "对白没有直接解释动机"],
            "strengths": ["苏棠抢走录音笔的动作改变了场面", "结尾的撤离决定自然承接下一章"],
            "issues": [],
            "approval_recommendation": "建议提升",
        }
    )

    assert service._writer_room_review_has_substance(review)


@pytest.mark.asyncio
async def test_scene_expansion_keeps_plain_prose_when_schema_defaults_are_empty(session: Session):
    class PlainBridgeAIService:
        async def chat(self, messages, **kwargs):
            bridge = "苏棠把钥匙扣在桌边，没去看萧然。门外脚步停住时，她先把纸条压进杯垫下面，再抬头说自己只是来换水。萧然顺着她的手指看见杯垫边缘露出的半行地址，伸手盖住，朝门口应了一声。"
            return LLMGenerationResult(success=True, content=bridge, provider="fake", model="plain-bridge")

    service = CreativeProjectService(session, ai_service=PlainBridgeAIService())
    project = service.create_project(title="", idea="smart short drama")
    source = "\n\n".join([
        "萧然把钥匙放在桌上，听见走廊有人停下。" * 12,
        "苏棠没有抬头，只把杯子往里推了一点。" * 12,
        "门锁轻响后，房间重新安静下来。" * 12,
    ])

    expanded = await service._expand_short_novel_body_candidate(
        project=project,
        stage="prose_rewrite",
        data={"chapter_number": 1, "title": "Entry", "content": source},
        reason=f"正文过短（{len(source)} 字）",
        provider="fake",
        model="plain-bridge",
        minimum_characters=len(source) + 60,
        maximum_characters=len(source) + 800,
    )

    assert expanded is not None
    assert "苏棠把钥匙扣在桌边" in expanded["content"]
    assert expanded["length_guard"]["inserted_characters"] > 60


def test_writer_room_length_expansion_instruction_detection():
    assert writer_room_allows_length_expansion("请扩写到 4000 字，增加篇幅")
    assert writer_room_allows_length_expansion("expand this chapter into a longer scene")
    assert not writer_room_allows_length_expansion("保持原稿长度，不要扩写")


def test_writer_room_requested_minimum_characters_detection():
    assert writer_room_requested_minimum_characters("目标 3800-4800 字，增加篇幅") == 3800
    assert writer_room_requested_maximum_characters("目标 3800-4800 字，增加篇幅") == 4800
    assert writer_room_requested_minimum_characters("扩写到 4000~5000 字") == 4000
    assert writer_room_requested_maximum_characters("扩写到 4000~5000 字") == 5000
    assert writer_room_requested_minimum_characters("达到 4000 至 5000 个中文字符") == 4000
    assert writer_room_requested_maximum_characters("达到 4000 至 5000 个中文字符") == 5000
    assert writer_room_requested_minimum_characters("重写为 4000-5000 个中文字符") == 4000
    assert writer_room_requested_maximum_characters("重写为 4000-5000 个中文字符") == 5000
    assert writer_room_requested_minimum_characters("Please expand this chapter to at least 4000 characters") == 4000
    assert writer_room_requested_maximum_characters("Please expand this chapter to at least 4000 characters") is None
    assert writer_room_requested_minimum_characters("保持原稿长度，不要扩写到 4000 字") is None
    assert writer_room_requested_maximum_characters("保持原稿长度，不要扩写到 4000 字") is None


def test_writer_room_effective_instruction_defaults_only_for_blank_prose_requests():
    default_instruction = writer_room_effective_instruction("prose_rewrite", None, 4200)

    assert "至少 4000 字" in default_instruction
    assert writer_room_effective_instruction("prose_review", None, 4200) == ""
    assert writer_room_effective_instruction("prose_rewrite", "只加强结尾钩子", 4200) == "只加强结尾钩子"


def test_writer_room_output_budget_tracks_explicit_length_ceiling():
    assert writer_room_output_max_tokens(4800) == 5150
    assert writer_room_output_max_tokens(4000) == 4350
    assert writer_room_output_max_tokens(None) == 12000


def test_writer_room_rewrite_prompt_elevates_explicit_length_range(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="Length", idea="length test")
    context = {
        "outline": {},
        "chapter_plan": {},
        "chapter_outline": {},
        "scene_beats": {},
        "character_rehearsal": {},
        "prose_review": {},
        "source_text": long_test_body("Source"),
        "source_content_type": "novel_body",
        "source_content_version": 1,
        "source_word_count": len(long_test_body("Source")),
        "selected_text": "",
        "previous_context": "",
    }

    prompt = service._writer_room_prompt(
        project=project,
        step="prose_rewrite",
        chapter_number=1,
        context=context,
        instruction="Expand and rewrite to 4000-4800 characters.",
    )

    assert "4000-4800" in prompt
    assert "4400" in prompt


def test_writer_room_prose_prompt_includes_human_style_contract(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="", idea="smart short drama")
    context = {
        "outline": {},
        "chapter_plan": {},
        "chapter_outline": {},
        "scene_beats": {},
        "character_rehearsal": {},
        "prose_review": {},
        "source_text": "",
        "source_content_type": "",
        "source_content_version": 0,
        "source_word_count": 0,
        "selected_text": "",
        "previous_context": "",
    }

    draft_prompt = service._writer_room_prompt(
        project=project,
        step="prose_draft",
        chapter_number=1,
        context=context,
        instruction="",
    )
    review_prompt = service._writer_room_prompt(
        project=project,
        step="prose_review",
        chapter_number=1,
        context=context,
        instruction="",
    )

    assert "写作质感硬约束" in draft_prompt
    assert "系统/剧本/存在值" in draft_prompt
    assert "每 500-800 字至少发生一次可见变化" in draft_prompt
    assert "写作质感硬约束" not in review_prompt
    assert "只评价正文中真实存在的句子" in review_prompt
    assert "建议提升" in review_prompt


@pytest.mark.asyncio
async def test_short_novel_body_can_be_completed_with_a_contextual_scene_bridge(session: Session):
    class SceneBridgeAIService:
        async def chat(self, messages, **kwargs):
            return LLMGenerationResult(
                success=True,
                content="补写场景" + "。走廊尽头的灯忽明忽暗，他把钥匙压进掌心，没有立刻回头。" * 82,
                provider="fake",
                model="scene-bridge",
            )

    service = CreativeProjectService(session, ai_service=SceneBridgeAIService())
    project = service.create_project(title="", idea="smart short drama")
    source = "\n\n".join(
        f"第{index}段" + "。人物在房间里检查证据，压住惊惧，决定继续向前。" * 24
        for index in range(1, 5)
    )

    expanded = await service._expand_short_novel_body_candidate(
        project=project,
        stage="prose_rewrite",
        data={"chapter_number": 1, "title": "Entry", "content": source},
        reason=f"正文过短（{len(source)} 字）",
        provider="fake",
        model="scene-bridge",
        minimum_characters=len(source) + 1000,
        maximum_characters=len(source) + 2600,
    )

    assert expanded is not None
    assert len(expanded["content"]) >= len(source) + 1000
    assert expanded["length_guard"]["strategy"] == "scene_expansion"


@pytest.mark.asyncio
async def test_quality_repair_accepts_plain_prose_from_compatible_provider(session: Session):
    repaired_text = long_test_body("Repair")

    class PlainRepairAIService:
        async def chat(self, messages, **kwargs):
            return LLMGenerationResult(
                success=True,
                content=repaired_text,
                provider="fake",
                model="plain-repair",
            )

    service = CreativeProjectService(session, ai_service=PlainRepairAIService())
    project = service.create_project(title="", idea="smart short drama")
    repaired = await service._ensure_novel_body_quality(
        project=project,
        stage="prose_rewrite",
        prompt="Rewrite chapter 4 as a full novel body.",
        system_prompt="Return a novel body.",
        data={"chapter_number": 4, "title": "Repair", "content": "too short"},
        provider="fake",
        model="plain-repair",
        minimum_characters=2800,
    )

    assert repaired["content"] == repaired_text
    assert repaired["chapter_number"] == 4
    assert repaired["title"] == "Repair"
    log = session.exec(
        select(ProjectGenerationLog)
        .where(ProjectGenerationLog.stage == "prose_rewrite_quality_repair")
        .order_by(ProjectGenerationLog.created_at.desc())
    ).first()
    assert log is not None
    assert '"parse_mode": "plain_prose"' in log.request_json


@pytest.mark.asyncio
async def test_short_novel_body_small_gap_uses_scene_bridge_within_maximum_length(session: Session):
    class SmallGapBridgeAIService:
        async def chat(self, messages, **kwargs):
            return LLMGenerationResult(
                success=True,
                content="补写场景" + "。她把折好的纸条压在掌心，直到边角硌得发疼。" * 24,
                provider="fake",
                model="small-gap-bridge",
            )

    service = CreativeProjectService(session, ai_service=SmallGapBridgeAIService())
    project = service.create_project(title="", idea="smart short drama")
    source = "\n\n".join(
        f"第{index}段" + "。他站在走廊里，没有立刻推门。" * 46
        for index in range(1, 5)
    )
    minimum = len(source) + 240
    maximum = len(source) + 700

    expanded = await service._expand_short_novel_body_candidate(
        project=project,
        stage="prose_rewrite",
        data={"chapter_number": 1, "title": "Entry", "content": source},
        reason=f"正文过短（{len(source)} 字）",
        provider="fake",
        model="small-gap-bridge",
        minimum_characters=minimum,
        maximum_characters=maximum,
    )

    assert expanded is not None
    assert len(expanded["content"]) >= minimum
    assert len(expanded["content"]) <= maximum


@pytest.mark.asyncio
async def test_quality_repair_shortfall_uses_scene_bridge_before_rejecting(session: Session):
    original = long_test_body("Overlong") + "\n\n" + long_test_body("Overlong continuation")
    compressed = long_test_body("Compressed")
    minimum = len(compressed) + 400
    maximum = minimum + 700
    bridge = "Bridge scene. " + "She checks the key, hears the corridor door, and chooses not to run. " * 8

    class RepairThenBridgeAIService:
        def __init__(self):
            self.calls = 0

        async def chat(self, messages, **kwargs):
            self.calls += 1
            content = compressed if self.calls == 1 else bridge
            return LLMGenerationResult(
                success=True,
                content=json.dumps(
                    {
                        "chapter_number": 1,
                        "title": "Repaired",
                        "content": content,
                        "word_count": len(content),
                        "continuity_notes": [],
                    }
                ),
                provider="fake",
                model="repair-then-bridge",
            )

    service = CreativeProjectService(session, ai_service=RepairThenBridgeAIService())
    project = service.create_project(title="Repair", idea="repair test")
    result = await service._ensure_novel_body_quality(
        project=project,
        stage="prose_rewrite",
        prompt="Rewrite the chapter.",
        system_prompt=None,
        data={"chapter_number": 1, "title": "Original", "content": original, "word_count": len(original)},
        provider="fake",
        model="repair-then-bridge",
        minimum_characters=minimum,
        maximum_characters=maximum,
    )

    assert len(result["content"]) >= minimum
    assert len(result["content"]) <= maximum
    assert result["length_guard"]["strategy"] == "scene_expansion"


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

        if "待重写段落" in user_content or "重写后的段落" in user_content:
            return self._result("【重写结果】这是根据指令修改后的段落。")

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

        if "刚才生成的小说正文质量不达标" in user_content:
            content = long_test_body("Lin Zhao")
            return self._result(
                {
                    "chapter_number": 1,
                    "title": "Entry",
                    "content": content,
                    "word_count": len(content),
                    "continuity_notes": ["Lin keeps the package and follows the watermark."],
                }
            )

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
    ProjectContinuityCandidate.__table__.create(engine)
    ProjectNarrativeRun.__table__.create(engine)
    ProjectNarrativeContextSnapshot.__table__.create(engine)
    ProjectNarrativeSnapshot.__table__.create(engine)
    ProjectStoryEvent.__table__.create(engine)
    ProjectForeshadowing.__table__.create(engine)
    ProjectStyleMeasurement.__table__.create(engine)
    with Session(engine) as session:
        yield session


def test_writing_preflight_explains_missing_chapter_outline(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="Preflight", idea="A serial novel", project_type="novel")
    service.update_project(
        project.id,
        {
            "outline": {"title": "Preflight", "genre": ["都市"]},
            "chapter_plan": {"chapter_count": 1, "chapters": [{"chapter_number": 1, "title": "Opening"}]},
        },
    )

    result = service.writing_preflight(project.id, chapter_number=1, stage="novel_body")

    assert result["ready"] is False
    assert any(item["id"] == "chapter_outline" for item in result["blockers"])
    assert "chapter outline" in result["next_action"]
    assert any(item["id"] == "chapter-hook-rhythm" for item in result["method_candidates"])


def test_writing_preflight_ready_for_chapter_outline_without_model_call(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="Ready", idea="A serial novel", project_type="novel")
    service.update_project(
        project.id,
        {
            "outline": {"title": "Ready", "genre": ["都市"]},
            "chapter_plan": {"chapter_count": 1, "chapters": [{"chapter_number": 1, "title": "Opening"}]},
        },
    )

    result = service.writing_preflight(project.id, chapter_number=1, stage="chapter_outline")

    assert result["ready"] is True
    assert result["blockers"] == []
    assert result["stage"] == "chapter_outline"


def test_writing_preflight_rejects_unknown_stage(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="Invalid preflight", idea="A serial novel", project_type="novel")

    with pytest.raises(ValueError, match="unsupported writing preflight stage"):
        service.writing_preflight(project.id, chapter_number=1, stage="teleport_to_publish")


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


def test_chapter_plan_count_is_derived_from_existing_entries(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="Finished story", idea="A complete short drama")
    stale_plan = {
        "chapter_count": 18,
        "chapters": [
            {"chapter_number": number, "title": f"Episode {number}"}
            for number in range(1, 16)
        ],
    }

    service.update_project(project.id, {"chapter_plan": stale_plan})

    refreshed = session.get(CreativeProject, project.id)
    assert refreshed is not None
    saved_plan = loads_json(refreshed.chapter_plan_json)
    assert saved_plan["chapter_count"] == 15
    assert service._normalize_pipeline_chapters(refreshed, chapters=None, chapter_count=None) == list(range(1, 16))


def test_chapter_plan_rejects_duplicate_chapter_numbers(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="Duplicate plan", idea="duplicate test")

    with pytest.raises(ValueError, match="章节号重复：第 1 章"):
        service.update_project(
            project.id,
            {
                "chapter_plan": {
                    "chapter_count": 2,
                    "chapters": [
                        {"chapter_number": 1, "title": "First"},
                        {"chapter_number": 1, "title": "Duplicate"},
                    ],
                }
            },
        )


@pytest.mark.asyncio
async def test_extend_chapter_plan_only_appends_missing_tail(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="", idea="smart short drama")
    await service.generate_outline(project.id)
    await service.generate_chapter_plan(project.id, chapter_count=2)

    class ExtensionAIService(FakeAIService):
        async def chat(self, messages, **kwargs):
            if "只输出第 3 到第 3 章" in messages[-1].content:
                return self._result(
                    {
                        "chapter_count": 1,
                        "chapters": [
                            {
                                "chapter_number": 3,
                                "title": "Final proof",
                                "goal": "Resolve the evidence chain.",
                                "conflict": "The culprit deletes the last record.",
                                "key_events": ["Trace the record", "Publish proof"],
                                "character_focus": ["Lin Zhao"],
                                "ending_hook": "The archive opens.",
                                "status": "planned",
                            }
                        ],
                    }
                )
            return await super().chat(messages, **kwargs)

    service.ai_service = ExtensionAIService()
    extended = await service.generate_chapter_plan(project.id, chapter_count=3, append_existing=True)

    assert [item["chapter_number"] for item in extended["chapters"]] == [1, 2, 3]
    assert extended["appended_chapter_numbers"] == [3]
    refreshed = session.get(CreativeProject, project.id)
    assert refreshed is not None
    assert [item["chapter_number"] for item in loads_json(refreshed.chapter_plan_json)["chapters"]] == [1, 2, 3]


def test_list_contents_returns_only_latest_version_by_default(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="Versioned story", idea="content history")

    first = service._create_content(
        project_id=project.id,
        content_type="novel_body",
        chapter_number=1,
        title="Chapter one",
        data={"content": "first draft"},
        text_content="first draft",
    )
    second = service._create_content(
        project_id=project.id,
        content_type="novel_body",
        chapter_number=1,
        title="Chapter one",
        data={"content": "revised draft"},
        text_content="revised draft",
    )
    chapter_two = service._create_content(
        project_id=project.id,
        content_type="novel_body",
        chapter_number=2,
        title="Chapter two",
        data={"content": "chapter two"},
        text_content="chapter two",
    )
    session.commit()

    current = service.list_contents(project.id, content_type="novel_body")
    history = service.list_contents(project.id, content_type="novel_body", latest_only=False)

    assert {item.id for item in current} == {second.id, chapter_two.id}
    assert {item.id for item in history} == {first.id, second.id, chapter_two.id}


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
async def test_novel_generation_and_writer_room_share_locked_context_pack(session: Session):
    ai_service = CapturingAIService()
    service = CreativeProjectService(session, ai_service=ai_service)
    project = service.create_project(title="", idea="smart short drama")

    await service.generate_outline(project.id)
    await service.generate_chapter_plan(project.id, chapter_count=2)
    service.sync_project_bible(project.id)
    world_asset = session.exec(
        select(ProjectContent).where(ProjectContent.project_id == project.id, ProjectContent.content_type == "world_asset")
    ).first()
    assert world_asset is not None
    service.update_content(
        project_id=project.id,
        content_id=world_asset.id,
        data={"role": "rule", "summary": "LOCKED FACT: Lin never carries a gun."},
        text_content="LOCKED FACT: Lin never carries a gun.",
        is_locked=True,
    )
    unlocked = service._create_content(
        project_id=project.id,
        content_type="world_asset",
        title="Unconfirmed note",
        data={"role": "candidate", "summary": "UNLOCKED FACT: Lin owns a spaceship."},
        text_content="UNLOCKED FACT: Lin owns a spaceship.",
    )
    session.commit()
    session.refresh(unlocked)

    await service.generate_chapter_outline(project.id, chapter_number=1)
    await service.generate_novel_body(project.id, chapter_number=1)

    assert "LOCKED FACT: Lin never carries a gun." in ai_service.last_user_content
    assert "UNLOCKED FACT: Lin owns a spaceship." not in ai_service.last_user_content
    novel_log = session.exec(
        select(ProjectGenerationLog)
        .where(ProjectGenerationLog.project_id == project.id, ProjectGenerationLog.stage == "novel_body")
        .order_by(ProjectGenerationLog.created_at.desc())
    ).first()
    assert novel_log is not None
    context_metadata = loads_json(novel_log.request_json)["creative_context"]
    assert context_metadata["locked_bible_card_count"] == 1
    assert context_metadata["fingerprint"]
    assert context_metadata["context_snapshot_id"]
    persisted_context = session.get(
        ProjectNarrativeContextSnapshot, context_metadata["context_snapshot_id"]
    )
    assert persisted_context is not None
    assert persisted_context.stage == "novel_body"
    assert "LOCKED FACT: Lin never carries a gun." in persisted_context.context_text

    await service.generate_chapter_outline(project.id, chapter_number=2)
    await service.run_writer_room_step(project.id, step="scene_beats", chapter_number=2)

    assert "LOCKED FACT: Lin never carries a gun." in ai_service.last_user_content
    assert "第 1 章 novel_body" in ai_service.last_user_content
    assert "UNLOCKED FACT: Lin owns a spaceship." not in ai_service.last_user_content


def test_context_pack_reports_t0_overflow_and_excludes_pending_or_foreign_data(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="Context A", idea="A")
    other_project = service.create_project(title="Context B", idea="B")
    locked = service._create_content(
        project_id=project.id,
        content_type="project_bible",
        title="Large canon",
        data={"summary": "CANON-" + "x" * 6100},
        text_content="CANON-" + "x" * 6100,
    )
    foreign = service._create_content(
        project_id=other_project.id,
        content_type="project_bible",
        title="Foreign canon",
        data={"summary": "FOREIGN-SECRET"},
        text_content="FOREIGN-SECRET",
    )
    pending = ProjectContinuityCandidate(
        project_id=project.id,
        source_kind="review",
        source_fingerprint="pending-context-test",
        claim="PENDING-SECRET",
        evidence_excerpt="PENDING-SECRET",
    )
    session.add(pending)
    session.commit()
    service.update_content(project_id=project.id, content_id=locked.id, is_locked=True)
    service.update_content(project_id=other_project.id, content_id=foreign.id, is_locked=True)

    preview = service.preview_narrative_context(project.id, chapter_number=2)

    assert "CANON-" in preview["text"]
    assert "FOREIGN-SECRET" not in preview["text"]
    assert "PENDING-SECRET" not in preview["text"]
    assert preview["metadata"]["excluded_sources"]["pending_continuity_candidates"] == 1
    assert preview["metadata"]["overflow"]
    assert preview["metadata"]["overflow"][0]["layer"] == "T0"
    assert preview["metadata"]["overflow"][0]["action"] == "reported"
    assert preview["persisted"] is False
    assert session.exec(select(ProjectNarrativeContextSnapshot)).all() == []


def test_context_pack_uses_optional_semantic_adapter_only_with_approved_project_prose(session: Session):
    class CapturingRecallAdapter:
        def __init__(self):
            self.project_id = ""
            self.candidate_ids: list[str] = []

        def recall(self, *, project_id, chapter_number, query, candidates, character_budget):
            self.project_id = project_id
            self.candidate_ids = [candidate.content_id for candidate in candidates]
            selected = candidates[0]
            return NarrativeRecallResult(
                text=f"Relevant approved excerpt: {selected.text}",
                source_content_ids=[selected.content_id],
            )

    adapter = CapturingRecallAdapter()
    service = CreativeProjectService(session, ai_service=FakeAIService(), semantic_recall_adapter=adapter)
    project = service.create_project(title="Recall scope", idea="Recover a lost key")
    other_project = service.create_project(title="Foreign recall", idea="Do not leak this")
    approved = service._create_content(
        project_id=project.id,
        content_type="novel_body",
        chapter_number=1,
        title="Approved source",
        data={"content": "The lost key is hidden in a clock."},
        text_content="The lost key is hidden in a clock.",
    )
    foreign = service._create_content(
        project_id=other_project.id,
        content_type="novel_body",
        chapter_number=1,
        title="Foreign source",
        data={"content": "FOREIGN-SECRET"},
        text_content="FOREIGN-SECRET",
    )
    project.chapter_plan_json = json.dumps({"chapters": [{"chapter_number": 2, "summary": "Find the key."}]})
    session.add(project)
    session.commit()

    preview = service.preview_narrative_context(project.id, chapter_number=2)

    assert adapter.project_id == project.id
    assert adapter.candidate_ids == [approved.id]
    assert foreign.id not in adapter.candidate_ids
    assert "Relevant approved excerpt" in preview["text"]
    assert "FOREIGN-SECRET" not in preview["text"]
    t5 = next(layer for layer in preview["metadata"]["layers"] if layer["id"] == "T5")
    assert t5["status"] == "available"
    assert {source["id"] for source in preview["metadata"]["included_source_ids"] if source["layer"] == "T5"} == {approved.id}


def test_context_pack_routes_declared_creative_skills_by_project_type_and_stage(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(
        title="Skill-routed novel",
        idea="A courier hides a dangerous letter.",
        project_type="novel",
        settings={"creative_skill_ids": ["prose_humanize", "comic_image_prompt"]},
    )
    project.outline_json = json.dumps({"genre": "悬疑"}, ensure_ascii=False)
    session.add(project)
    session.commit()

    prose_pack = service._creative_context_pack(project.id, chapter_number=1, stage="prose_draft")
    prose_skills = prose_pack["metadata"]["applied_skills"]
    assert {item["id"] for item in prose_skills} == {"novel_completion"}
    assert prose_skills[0]["source"] == "genre_compatible"
    assert prose_pack["metadata"]["excluded_sources"]["creative_skills"]["skipped"] == [
        {"id": "comic_image_prompt", "reason": "not_a_creative_skill"},
        {"id": "prose_humanize", "reason": "stage_incompatible"},
    ]

    humanized_pack = service._creative_context_pack(project.id, chapter_number=1, stage="prose_humanized", persist=True)
    humanized_skills = humanized_pack["metadata"]["applied_skills"]
    assert {item["id"] for item in humanized_skills} == {"prose_humanize"}
    snapshot = session.get(ProjectNarrativeContextSnapshot, humanized_pack["snapshot_id"])
    assert loads_json(snapshot.applied_skill_ids_json) == ["prose_humanize"]
    assert "正文去 AI 腔" in humanized_pack["text"]


@pytest.mark.asyncio
async def test_writer_room_batch_reuses_one_persisted_context_snapshot(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="Batch context", idea="A coherent scene")
    await service.generate_outline(project.id)
    await service.generate_chapter_plan(project.id, chapter_count=1)
    await service.generate_chapter_outline(project.id, chapter_number=1)

    result = await service.run_writer_room(
        project.id,
        chapter_number=1,
        steps=["scene_beats", "character_rehearsal"],
        rehearsal_mode="fast",
    )

    snapshot_id = result["context_snapshot_id"]
    assert snapshot_id
    generated = session.exec(
        select(ProjectGenerationLog).where(
            ProjectGenerationLog.project_id == project.id,
            ProjectGenerationLog.stage.in_(["scene_beats", "character_rehearsal"]),
        )
    ).all()
    assert len(generated) == 2
    assert {
        loads_json(item.request_json)["creative_context"]["context_snapshot_id"]
        for item in generated
    } == {snapshot_id}


@pytest.mark.asyncio
async def test_refine_novel_body_receives_project_context_pack(session: Session):
    ai_service = CapturingAIService()
    service = CreativeProjectService(session, ai_service=ai_service)
    project = service.create_project(title="", idea="smart short drama")
    locked = service._create_content(
        project_id=project.id,
        content_type="project_bible",
        title="Immutable identity",
        data={"role": "character", "summary": "LOCKED FACT: Lin is a video editor."},
        text_content="LOCKED FACT: Lin is a video editor.",
    )
    body = service._create_content(
        project_id=project.id,
        content_type="novel_body",
        chapter_number=1,
        episode_number=1,
        title="Entry",
        data={"chapter_number": 1, "content": long_test_body("Lin Zhao")},
        text_content=long_test_body("Lin Zhao"),
    )
    session.commit()
    service.update_content(project_id=project.id, content_id=locked.id, is_locked=True)

    await service.refine_novel_body(
        project_id=project.id,
        content_id=body.id,
        instruction="加强结尾钩子",
    )

    assert "LOCKED FACT: Lin is a video editor." in ai_service.last_user_content


@pytest.mark.asyncio
async def test_generate_chapter_outline_novel_body_storyboard_and_comic_pages(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="", idea="smart short drama")

    await service.generate_outline(project.id)
    await service.generate_chapter_plan(project.id, chapter_count=2)
    chapter_outline = await service.generate_chapter_outline(project.id, chapter_number=1)
    novel_body = await service.generate_novel_body(project.id, chapter_number=1)
    body_content = session.exec(
        select(ProjectContent).where(ProjectContent.content_type == "novel_body")
    ).one()
    narrative_snapshot = ProjectNarrativeSnapshot(
        project_id=project.id,
        source_content_id=body_content.id,
        source_version=body_content.version,
        chapter_number=1,
        source_fingerprint="approved-body-v1",
        status="success",
        summary="Lin commits to following the clue.",
    )
    session.add(narrative_snapshot)
    session.commit()
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
    assert script_content.source_content_id == body_content.id
    assert loads_json(script_content.data_json)["narrative_provenance"] == {
        "source_kind": "approved_prose",
        "source_content_id": body_content.id,
        "source_content_version": body_content.version,
        "source_chapter_number": 1,
        "narrative_snapshot_id": narrative_snapshot.id,
        "narrative_snapshot_fingerprint": "approved-body-v1",
    }
    assert loads_json(storyboard_content.data_json)["narrative_provenance"] == loads_json(script_content.data_json)["narrative_provenance"]
    comic_content = next(item for item in contents if item.content_type == "comic_pages")
    assert comic_content.source_content_id == storyboard_content.id

    logs = session.exec(select(ProjectGenerationLog)).all()
    assert {"chapter_outline", "novel_body", "script", "storyboard", "comic_pages"}.issubset({log.stage for log in logs})
    script_log = next(log for log in logs if log.stage == "script")
    storyboard_log = next(log for log in logs if log.stage == "storyboard")
    assert script_log.content_id == script_content.id
    assert storyboard_log.content_id == storyboard_content.id
    assert loads_json(script_log.request_json)["narrative_provenance"]["narrative_snapshot_id"] == narrative_snapshot.id
    assert loads_json(storyboard_log.request_json)["narrative_provenance"]["source_content_id"] == body_content.id


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
    assert len(promoted.text_content) >= 2800

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
        rehearsal_mode="fast",
    )

    assert result["summary"] == {"total": 5, "success": 5, "failed": 0, "skipped": 0}
    humanized = session.exec(select(ProjectContent).where(ProjectContent.content_type == "prose_humanized")).one()
    assert len(humanized.text_content) >= 2800

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
async def test_writer_room_batch_records_the_exact_upstream_candidate_chain(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="Pipeline", idea="candidate lineage")
    await service.generate_outline(project.id)
    await service.generate_chapter_plan(project.id, chapter_count=1)
    await service.generate_chapter_outline(project.id, chapter_number=1)
    service.ai_service = WriterRoomAIService()

    result = await service.run_writer_room(
        project.id,
        steps=["scene_beats", "character_rehearsal", "prose_draft"],
        chapter_number=1,
        provider="deepseek",
        model="deepseek-v4-pro",
        rehearsal_mode="fast",
    )

    assert result["summary"] == {"total": 3, "success": 3, "failed": 0, "skipped": 0}
    scene_beats = session.exec(select(ProjectContent).where(ProjectContent.content_type == "scene_beats")).one()
    rehearsal = session.exec(select(ProjectContent).where(ProjectContent.content_type == "character_rehearsal")).one()
    draft = session.exec(select(ProjectContent).where(ProjectContent.content_type == "prose_draft")).one()
    assert rehearsal.source_content_id == scene_beats.id
    assert draft.source_content_id == rehearsal.id
    assert loads_json(rehearsal.data_json)["writer_room"]["source_content_id"] == scene_beats.id
    assert loads_json(draft.data_json)["writer_room"]["source_content_id"] == rehearsal.id


@pytest.mark.asyncio
async def test_writer_room_batch_orders_selected_steps_before_execution(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="Ordered pipeline", idea="candidate lineage")
    await service.generate_outline(project.id)
    await service.generate_chapter_plan(project.id, chapter_count=1)
    await service.generate_chapter_outline(project.id, chapter_number=1)
    service.ai_service = WriterRoomAIService()

    result = await service.run_writer_room(
        project.id,
        steps=["prose_draft", "character_rehearsal", "scene_beats", "prose_draft"],
        chapter_number=1,
        provider="deepseek",
        model="deepseek-v4-pro",
        rehearsal_mode="fast",
    )

    assert result["requested_steps"] == ["prose_draft", "character_rehearsal", "scene_beats", "prose_draft"]
    assert result["steps"] == ["scene_beats", "character_rehearsal", "prose_draft"]
    assert [item["step"] for item in result["results"]] == result["steps"]
    draft = session.exec(select(ProjectContent).where(ProjectContent.content_type == "prose_draft")).one()
    rehearsal = session.exec(select(ProjectContent).where(ProjectContent.content_type == "character_rehearsal")).one()
    assert draft.source_content_id == rehearsal.id


@pytest.mark.asyncio
async def test_writer_room_batch_skips_downstream_steps_after_upstream_failure(session: Session):
    service = CreativeProjectService(session, ai_service=FailingAIService())
    project = service.create_project(title="Blocked pipeline", idea="failure propagation")
    service.update_project(
        project.id,
        {
            "outline": {"title": "Blocked", "characters": []},
            "chapter_plan": {"chapters": [{"chapter_number": 1, "title": "Chapter one"}]},
        },
    )
    service._create_content(
        project_id=project.id,
        content_type="chapter_outline",
        chapter_number=1,
        episode_number=1,
        title="Chapter one",
        data={"chapter_number": 1, "summary": "An actionable scene."},
        text_content="An actionable scene.",
    )
    session.commit()

    result = await service.run_writer_room(
        project.id,
        steps=["scene_beats", "character_rehearsal", "prose_draft"],
        chapter_number=1,
        continue_on_error=True,
    )

    assert [item["status"] for item in result["results"]] == ["failed", "skipped", "skipped"]
    assert result["results"][1]["blocked_by"] == "scene_beats"
    assert result["summary"] == {"total": 3, "success": 0, "failed": 1, "skipped": 2}


@pytest.mark.asyncio
async def test_writer_room_humanization_reuses_draft_and_records_source_provenance(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="", idea="smart short drama")
    draft = service._create_content(
        project_id=project.id,
        content_type="prose_draft",
        chapter_number=1,
        episode_number=1,
        title="Entry",
        data={"chapter_number": 1, "content": "Draft prose with enough detail for humanization.", "word_count": 47},
        text_content="Draft prose with enough detail for humanization.",
    )
    first_humanized = service._create_content(
        project_id=project.id,
        content_type="prose_humanized",
        chapter_number=1,
        episode_number=1,
        title="Entry",
        data={"chapter_number": 1, "content": "An older humanized candidate that must not become the default source."},
        text_content="An older humanized candidate that must not become the default source.",
        source_content_id=draft.id,
    )
    session.commit()
    session.refresh(draft)
    session.refresh(first_humanized)

    service.ai_service = WriterRoomAIService()
    result = await service.run_writer_room_step(
        project.id,
        step="prose_humanized",
        chapter_number=1,
        provider="deepseek",
        model="deepseek-v4-pro",
    )

    writer_room = loads_json(result.data_json)["writer_room"]
    assert result.source_content_id == draft.id
    assert writer_room["source_content_id"] == draft.id
    assert writer_room["source_content_type"] == "prose_draft"
    assert writer_room["source_content_version"] == draft.version
    humanize_log = session.exec(
        select(ProjectGenerationLog)
        .where(ProjectGenerationLog.stage == "prose_humanized")
        .order_by(ProjectGenerationLog.created_at.desc())
    ).first()
    assert humanize_log is not None
    assert "90%-110%" in humanize_log.prompt
    assert "来源：prose_draft" in humanize_log.prompt


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
async def test_writer_room_review_persists_continuity_candidates(session: Session):
    """Prose review must surface bounded continuity_candidates as pending rows."""
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

    class ReviewWithCandidatesAIService(FakeAIService):
        async def chat(self, messages, **kwargs):
            user_content = messages[-1].content
            if '"overall_score"' in user_content and '"ai_smell_score"' in user_content:
                return LLMGenerationResult(
                    success=True,
                    content=json.dumps(
                        {
                            "chapter_number": 1,
                            "title": "Entry",
                            "overall_score": 74,
                            "ai_smell_score": 30,
                            "quality_tags": ["证据链清楚", "钩子可加强"],
                            "ai_smell_checks": ["直接情绪标签较少", "物件互动可再补"],
                            "strengths": ["开头进入快"],
                            "issues": [
                                {
                                    "severity": "medium",
                                    "category": "钩子",
                                    "location": "结尾",
                                    "problem": "悬念不够锋利。",
                                    "suggestion": "把水印压到最后一句。",
                                    "rewrite_instruction": "加强结尾钩子。",
                                }
                            ],
                            "rewrite_plan": ["压缩解释"],
                            "approval_recommendation": "建议提升",
                            "continuity_candidates": [
                                {
                                    "entity_type": "character",
                                    "entity_name": "Lin Zhao",
                                    "claim": "林昭是编辑室剪辑师，持有匿名包裹。",
                                    "evidence_excerpt": "林昭拆开匿名包裹。",
                                    "severity": "info",
                                    "suggested_action": "create_fact",
                                    "target_fact_type": "world_asset",
                                }
                            ],
                        },
                        ensure_ascii=False,
                    ),
                    provider="deepseek",
                    model="deepseek-v4-pro",
                )
            return await super().chat(messages, **kwargs)

    service.ai_service = ReviewWithCandidatesAIService()
    review = await service.run_writer_room_step(
        project.id,
        step="prose_review",
        chapter_number=1,
        content_id=source.id,
        provider="deepseek",
        model="deepseek-v4-pro",
    )

    candidates = session.exec(
        select(ProjectContinuityCandidate).where(
            ProjectContinuityCandidate.project_id == project.id,
            ProjectContinuityCandidate.source_kind == "prose_review",
        )
    ).all()
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.source_content_id == review.id
    assert candidate.status == "pending"
    assert candidate.entity_name == "Lin Zhao"
    assert "编辑室剪辑师" in candidate.claim
    # The candidates are also stored on the review content for traceability.
    assert loads_json(review.data_json).get("continuity_candidates")


@pytest.mark.asyncio
async def test_continuity_full_pipeline_smoke(session: Session):
    """End-to-end continuity loop through the real service pipeline.

    prose_review auto-extract -> list -> accept (locked fact) ->
    context-summary -> check-continuity -> rewrite-paragraph.
    """
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="", idea="smart short drama")
    await service.generate_outline(project.id)
    await service.generate_chapter_plan(project.id, chapter_count=2)
    await service.generate_chapter_outline(project.id, chapter_number=1)

    novel_body = service._create_content(
        project_id=project.id,
        content_type="novel_body",
        chapter_number=1,
        episode_number=1,
        title="Entry",
        data={"content": "林昭是编辑室剪辑师。她拆开匿名包裹，照片上有公司水印。"},
        text_content="林昭是编辑室剪辑师。她拆开匿名包裹，照片上有公司水印。",
    )
    session.commit()
    session.refresh(novel_body)

    class PipelineReviewAIService(FakeAIService):
        async def chat(self, messages, **kwargs):
            user_content = messages[-1].content
            if '"overall_score"' in user_content and '"ai_smell_score"' in user_content:
                return LLMGenerationResult(
                    success=True,
                    content=json.dumps(
                        {
                            "chapter_number": 1,
                            "title": "Entry",
                            "overall_score": 74,
                            "ai_smell_score": 30,
                            "quality_tags": ["证据链清楚", "钩子可加强"],
                            "ai_smell_checks": ["直接情绪标签较少", "物件互动可再补"],
                            "strengths": ["开头进入快"],
                            "issues": [
                                {
                                    "severity": "medium",
                                    "category": "钩子",
                                    "location": "结尾",
                                    "problem": "悬念不够锋利。",
                                    "suggestion": "把水印压到最后一句。",
                                    "rewrite_instruction": "加强结尾钩子。",
                                }
                            ],
                            "rewrite_plan": ["压缩解释"],
                            "approval_recommendation": "建议提升",
                            "continuity_candidates": [
                                {
                                    "entity_type": "character",
                                    "entity_name": "Lin Zhao",
                                    "claim": "林昭是编辑室剪辑师，持有匿名包裹。",
                                    "evidence_excerpt": "林昭拆开匿名包裹。",
                                    "severity": "info",
                                    "suggested_action": "create_fact",
                                    "target_fact_type": "world_asset",
                                }
                            ],
                        },
                        ensure_ascii=False,
                    ),
                    provider="deepseek",
                    model="deepseek-v4-pro",
                )
            return await super().chat(messages, **kwargs)

    service.ai_service = PipelineReviewAIService()
    await service.run_writer_room_step(
        project.id,
        step="prose_review",
        chapter_number=1,
        content_id=novel_body.id,
        provider="deepseek",
        model="deepseek-v4-pro",
    )

    candidates = session.exec(
        select(ProjectContinuityCandidate).where(
            ProjectContinuityCandidate.project_id == project.id,
            ProjectContinuityCandidate.source_kind == "prose_review",
        )
    ).all()
    assert len(candidates) == 1
    assert candidates[0].status == "pending"

    accepted = service.accept_continuity_candidate(project.id, candidates[0].id)
    assert accepted.status == "accepted"
    assert accepted.resolved_fact_id

    summary = service.build_continuity_context_summary(project.id)
    assert summary["locked_fact_count"] >= 1
    assert summary["pending_candidate_count"] == 0

    check = service.check_continuity(project.id, 1)
    assert isinstance(check.get("conflicts"), list)

    rewrite = await service.rewrite_paragraph(
        project.id,
        novel_body.id,
        0,
        "把开头改得更抓人",
        provider="fake",
        model="fake",
    )
    assert rewrite.get("anchor_not_found") is False
    assert rewrite.get("candidate_content_id")


@pytest.mark.asyncio
async def test_writer_room_rewrite_rejects_short_candidate_without_creating_content(session: Session):
    class ShortRewriteAIService(FakeAIService):
        async def chat(self, messages, **kwargs):
            return LLMGenerationResult(
                success=True,
                content=json.dumps(
                    {
                        "chapter_number": 1,
                        "title": "Entry",
                        "content": "This is still only a summary.",
                        "word_count": 28,
                        "continuity_notes": [],
                    }
                ),
                provider="fake",
                model="short-rewrite",
            )

    service = CreativeProjectService(session, ai_service=ShortRewriteAIService())
    project = service.create_project(title="", idea="smart short drama")
    source = service._create_content(
        project_id=project.id,
        content_type="novel_body",
        chapter_number=1,
        episode_number=1,
        title="Entry",
        data={"content": long_test_body("Source")},
        text_content=long_test_body("Source"),
    )
    session.commit()

    with pytest.raises(ValueError, match="正文质量仍不达标"):
        await service.run_writer_room_step(
            project.id,
            step="prose_rewrite",
            chapter_number=1,
            content_id=source.id,
            provider="fake",
            model="short-rewrite",
        )

    rewrites = session.exec(
        select(ProjectContent).where(ProjectContent.content_type == "prose_rewrite")
    ).all()
    assert rewrites == []


@pytest.mark.asyncio
async def test_writer_room_rewrite_allows_expanded_candidate_when_requested(session: Session):
    source = "\n\n".join(
        f"Source paragraph {index}. " + "She checks the file, waits, and keeps the clue. " * 10
        for index in range(1, 4)
    )
    expanded = "\n\n".join(
        f"Expanded paragraph {index}. " + "She checks the file, waits, touches the folded note, and keeps moving. " * 14
        for index in range(1, 5)
    )

    class ExpandedRewriteAIService(FakeAIService):
        async def chat(self, messages, **kwargs):
            return LLMGenerationResult(
                success=True,
                content=json.dumps(
                    {
                        "chapter_number": 1,
                        "title": "Expanded",
                        "content": expanded,
                        "word_count": len(expanded),
                        "continuity_notes": ["Expanded prose keeps the clue active."],
                    }
                ),
                provider="fake",
                model="expanded-rewrite",
            )

    service = CreativeProjectService(session, ai_service=ExpandedRewriteAIService())
    project = service.create_project(title="", idea="smart short drama")
    source_content = service._create_content(
        project_id=project.id,
        content_type="novel_body",
        chapter_number=1,
        episode_number=1,
        title="Entry",
        data={"content": source},
        text_content=source,
    )
    session.commit()

    result = await service.run_writer_room_step(
        project.id,
        step="prose_rewrite",
        chapter_number=1,
        content_id=source_content.id,
        instruction="请扩写到 4000 字，增加篇幅和场面细节",
        provider="fake",
        model="expanded-rewrite",
    )

    assert result.text_content == expanded
    assert len(result.text_content) > len(source) * 1.15
    assert result.source_content_id == source_content.id


def test_writer_room_rewrite_uses_only_review_bound_to_selected_source(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="", idea="smart short drama")
    selected = service._create_content(
        project_id=project.id,
        content_type="novel_body",
        chapter_number=1,
        episode_number=1,
        title="Selected",
        data={"content": long_test_body("Selected")},
        text_content=long_test_body("Selected"),
    )
    other = service._create_content(
        project_id=project.id,
        content_type="prose_humanized",
        chapter_number=1,
        episode_number=1,
        title="Other candidate",
        data={"content": long_test_body("Other")},
        text_content=long_test_body("Other"),
    )
    service._create_content(
        project_id=project.id,
        content_type="prose_review",
        chapter_number=1,
        episode_number=1,
        title="Selected review",
        data={
            "issues": [{"rewrite_instruction": "KEEP_SELECTED_REVIEW"}],
            "writer_room": {"source_content_id": selected.id},
        },
        text_content="KEEP_SELECTED_REVIEW",
        source_content_id=selected.id,
    )
    service._create_content(
        project_id=project.id,
        content_type="prose_review",
        chapter_number=1,
        episode_number=1,
        title="Other review",
        data={
            "issues": [{"rewrite_instruction": "DO_NOT_LEAK_OTHER_REVIEW"}],
            "writer_room": {"source_content_id": other.id},
        },
        text_content="DO_NOT_LEAK_OTHER_REVIEW",
        source_content_id=other.id,
    )
    session.commit()

    context = service._writer_room_context(
        project_id=project.id,
        step="prose_rewrite",
        chapter_number=1,
        source_content_id=selected.id,
        selected_text=None,
    )

    review_json = json.dumps(context["prose_review"], ensure_ascii=False)
    assert "KEEP_SELECTED_REVIEW" in review_json
    assert "DO_NOT_LEAK_OTHER_REVIEW" not in review_json


class HumanizationRetryAIService(FakeAIService):
    """First humanization returns a too-short chapter (triggers the length
    retry), the retry call returns a full-length chapter."""

    async def chat(self, messages, **kwargs):
        user_content = messages[-1].content
        if "长度复核" in user_content:
            content = long_test_body("Lin Zhao")
            return self._result(
                {
                    "chapter_number": 1,
                    "title": "Entry",
                    "content": content,
                    "word_count": len(content),
                    "continuity_notes": ["Lin keeps the evidence."],
                }
            )
        if '"prose_humanized"' in user_content or "完整润色正文" in user_content:
            return self._result(
                {
                    "chapter_number": 1,
                    "title": "Entry",
                    "content": "Lin opened the package.",
                    "word_count": 21,
                    "continuity_notes": ["Short humanization."],
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


def test_writer_room_prose_alias_normalizes_chapter_content():
    payload = {"chapter_content": "A complete chapter returned under a provider alias."}

    CreativeProjectService._normalize_prose_content_alias(payload)

    assert payload["content"] == payload["chapter_content"]


@pytest.mark.asyncio
async def test_writer_room_step_binds_generation_log_to_candidate(session: Session):
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

    data = loads_json(content.data_json)
    assert data["writer_room"]["generation_log_id"]

    log = session.exec(select(ProjectGenerationLog).where(ProjectGenerationLog.stage == "scene_beats")).one()
    # The final successful log is backfilled with the candidate id.
    assert log.content_id == content.id
    # The candidate metadata records the same stable log id.
    assert data["writer_room"]["generation_log_id"] == log.id
    # Exactly one log is linked to this candidate.
    linked = session.exec(
        select(ProjectGenerationLog).where(ProjectGenerationLog.content_id == content.id)
    ).all()
    assert len(linked) == 1


@pytest.mark.asyncio
async def test_writer_room_humanization_retry_only_binds_final_log(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="", idea="smart short drama")
    await service.generate_outline(project.id)
    await service.generate_chapter_plan(project.id, chapter_count=2)
    await service.generate_chapter_outline(project.id, chapter_number=1)
    draft = service._create_content(
        project_id=project.id,
        content_type="prose_draft",
        chapter_number=1,
        episode_number=1,
        title="Entry",
        data={"content": long_test_body("Lin Zhao"), "word_count": len(long_test_body("Lin Zhao"))},
        text_content=long_test_body("Lin Zhao"),
    )
    session.commit()
    session.refresh(draft)

    service.ai_service = HumanizationRetryAIService()
    humanized = await service.run_writer_room_step(
        project.id,
        step="prose_humanized",
        chapter_number=1,
        content_id=draft.id,
        provider="deepseek",
        model="deepseek-v4-pro",
    )

    data = loads_json(humanized.data_json)
    final_log_id = data["writer_room"]["generation_log_id"]
    assert final_log_id

    # Only the final (retry) log is bound to the candidate.
    linked = session.exec(
        select(ProjectGenerationLog).where(ProjectGenerationLog.content_id == humanized.id)
    ).all()
    assert len(linked) == 1
    final_log = linked[0]
    assert final_log.id == final_log_id
    # The final log carries the full-length humanized output, not the short one.
    assert "压住一个随时会翻面的证词" in final_log.normalized_json

    # The earlier short response's log still exists but stays trace-only.
    short_logs = session.exec(
        select(ProjectGenerationLog).where(
            ProjectGenerationLog.stage == "prose_humanized",
            ProjectGenerationLog.content_id.is_(None),
        )
    ).all()
    assert len(short_logs) == 1
    assert "Lin opened the package." in short_logs[0].normalized_json


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


def test_storyboard_video_plan_normalizes_legacy_panels(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    data = {
        "panels": [
            {
                "panel_number": 1,
                "panel_goal": "发现门缝下的纸条",
                "location": "雨夜走廊",
                "action": "林昭弯腰捡起纸条，抬头望向尽头",
                "emotion": "警觉",
                "shot_size": "特写",
                "camera_angle": "平视",
                "camera_motion": "镜头缓慢推进",
                "image_prompt": "这是一段静态生图提示词，不应该进入视频提示词",
            },
            {
                "panel_number": 2,
                "action": "走廊灯闪烁",
                "shot_size": "远景",
                "duration_seconds": 12,
                "generate_audio": "yes",
                "video_prompt": "灯光闪烁后熄灭，镜头缓慢拉远。",
            },
        ]
    }

    service._normalize_storyboard_v2(data)

    first, second = data["panels"]
    assert first["duration_seconds"] == 3
    assert first["camera_motion"] == "推近"
    assert "静态生图提示词" not in first["video_prompt"]
    assert "林昭弯腰捡起纸条" in first["video_prompt"]
    assert first["generate_audio"] is False
    assert second["duration_seconds"] == 6
    assert second["generate_audio"] is True
    assert second["video_prompt"] == "灯光闪烁后熄灭，镜头缓慢拉远。"
    assert StoryboardPanelSchema(panel_number=3).duration_seconds == 5
    assert StoryboardPanelSchema(panel_number=3).generate_audio is False


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


def test_sync_outline_characters_creates_library_records_and_project_links(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="角色同步", idea="character sync")
    project.outline_json = json.dumps(
        {
            "characters": [
                {
                    "name": "沈知夏",
                    "role": "主角",
                    "appearance": "黑色短发，风衣",
                    "personality": "冷静执拗",
                    "visual_tags": ["雨夜", "旧相机"],
                }
            ]
        },
        ensure_ascii=False,
    )
    session.add(project)
    session.commit()

    synced = service.sync_outline_characters(project.id)

    assert len(synced) == 1
    character = synced[0]
    assert character.name == "沈知夏"
    assert character.appearance == "黑色短发，风衣"
    story_link = session.exec(
        select(CharacterStoryLink).where(
            CharacterStoryLink.story_id == project.id,
            CharacterStoryLink.character_id == character.id,
        )
    ).one()
    assert story_link.usage_role == "protagonist"
    project = service.get_project(project.id)
    assert loads_json(project.outline_json)["characters"][0]["character_id"] == character.id


def test_project_text_asset_payload_keeps_project_content_lineage(session: Session):
    service = CreativeProjectService(session, ai_service=FakeAIService())
    project = service.create_project(title="文本素材", idea="asset projection")
    content = service._create_content(
        project_id=project.id,
        content_type="novel_body",
        chapter_number=3,
        episode_number=3,
        title="雨夜合同",
        data={"content": "正文快照"},
        text_content="正文快照",
    )

    payload = service._project_text_asset_payload(project, content)

    assert payload["metadata"]["source"] == "creative_project"
    assert payload["metadata"]["project_id"] == project.id
    assert payload["metadata"]["content_id"] == content.id
    assert payload["metadata"]["text_preview"] == "正文快照"
    assert payload["version_params"]["text_content"] == "正文快照"
    assert payload["lineage"]["content_id"] == content.id
    assert "novel_body" in payload["tags"]
