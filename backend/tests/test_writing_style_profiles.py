from __future__ import annotations

import json

import pytest
from sqlmodel import Session, create_engine

from app.db.models.creative_project import (
    CreativeProject,
    ProjectContent,
    ProjectContinuityCandidate,
    ProjectForeshadowing,
    ProjectGenerationLog,
    ProjectNarrativeContextSnapshot,
    ProjectNarrativeRun,
    ProjectNarrativeSnapshot,
    ProjectWritingStyleLink,
    WritingStyleProfile,
)
from app.db.models.novel_source import NovelSourceSnapshot, NovelTextChunk
from app.services.creative_project.service import CreativeProjectService
from app.services.creative_project.writing_style import (
    WritingStyleService,
    aggregate_sample_measurements,
    measure_text_sample,
    parse_style_json,
)
from tests.test_creative_project_service import FakeAIService


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    CreativeProject.__table__.create(engine)
    ProjectContent.__table__.create(engine)
    ProjectGenerationLog.__table__.create(engine)
    ProjectContinuityCandidate.__table__.create(engine)
    ProjectNarrativeRun.__table__.create(engine)
    ProjectNarrativeContextSnapshot.__table__.create(engine)
    ProjectNarrativeSnapshot.__table__.create(engine)
    ProjectForeshadowing.__table__.create(engine)
    WritingStyleProfile.__table__.create(engine)
    ProjectWritingStyleLink.__table__.create(engine)
    NovelSourceSnapshot.__table__.create(engine)
    NovelTextChunk.__table__.create(engine)
    with Session(engine) as db:
        yield db


def _profile():
    return {
        "dimensions": {
            "句式节奏": {
                "value": "长短句交替，动作段落在关键处收紧",
                "confidence": 0.92,
                "evidence_summary": "多个样本段落呈现短句收束",
                "measurement_keys": ["sentence_length", "paragraph_rhythm"],
            },
            "对话机制": {
                "value": "对话少解释，多用停顿和未说完的话保留潜台词",
                "confidence": 0.8,
            },
        },
        "new_examples": ["雨停了。他没有回头。"],
        "anti_template_constraints": ["不要把每段都写成同样长度。"],
        "prohibited_source_material": ["来源作品专名和原句"],
    }


def test_style_profile_requires_review_before_activation_and_checksum_is_stable(session: Session):
    service = WritingStyleService(session)
    item = service.create_profile(name="克制悬疑", profile=_profile())

    with pytest.raises(ValueError, match="必须先审核"):
        service.activate(item.id)

    reviewed = service.review(item.id)
    assert reviewed.status == "reviewed"
    activated = service.activate(item.id)
    assert activated.status == "active"
    assert len(activated.checksum) == 64
    assert activated.checksum == service.get(item.id).checksum


def test_only_active_profiles_can_bind_and_stage_scope_is_enforced(session: Session):
    project = CreativeProject(title="风格项目")
    session.add(project)
    session.commit()
    service = WritingStyleService(session)
    item = service.create_profile(name="冷峻", profile=_profile())
    with pytest.raises(ValueError, match="已激活"):
        service.bind(project.id, item.id)

    service.review(item.id)
    service.activate(item.id)
    link = service.bind(project.id, item.id, stage_scope=["novel_body"], intensity="subtle")
    assert link.project_id == project.id
    assert service.runtime_profiles(project.id, stage="chapter_outline") == []
    assert service.runtime_profiles(project.id, stage="novel_body")[0]["intensity"] == "subtle"


def test_context_pack_injects_only_bound_active_style_in_t6(session: Session):
    project_service = CreativeProjectService(session, ai_service=FakeAIService())
    project = project_service.create_project(title="T6", project_type="novel")
    style_service = WritingStyleService(session)
    item = style_service.create_profile(name="叙事克制", profile=_profile())
    style_service.review(item.id)
    style_service.activate(item.id)
    style_service.bind(project.id, item.id, stage_scope=["novel_body"])

    pack = project_service._creative_context_pack(project.id, 1, stage="novel_body")
    t6 = next(layer for layer in pack["metadata"]["layers"] if layer["id"] == "T6")
    assert t6["applied_style_profiles"][0]["id"] == item.id
    assert "长短句交替" in pack["text"]
    assert "writing_style_profile" in {source["kind"] for source in pack["metadata"]["included_source_ids"]}
    assert "已锁定项目圣经" not in pack["metadata"]["writing_style_profiles"]


def test_tampering_profile_json_blocks_runtime_use(session: Session):
    project = CreativeProject(title="篡改检查")
    session.add(project)
    session.commit()
    service = WritingStyleService(session)
    item = service.create_profile(name="待篡改", profile=_profile())
    service.review(item.id)
    service.activate(item.id)
    service.bind(project.id, item.id, stage_scope=["novel_body"])
    item.profile_json = json.dumps({"dimensions": {"句式节奏": {"value": "被篡改"}}}, ensure_ascii=False)
    session.add(item)
    session.commit()
    with pytest.raises(ValueError, match="校验和"):
        service.runtime_profiles(project.id, stage="novel_body")


# ---------------------------------------------------------------------------
# 来源测量聚合与草稿提取（OpenSpec 任务 2）
# ---------------------------------------------------------------------------

def test_measure_text_sample_is_deterministic_and_bounded():
    text = "他走进院子。屋里没人，只有风声。\n\n“来了？”她问，声音很轻。"
    first = measure_text_sample(text)
    assert measure_text_sample(text) == first  # 确定性
    assert first["chars"] == len(text)
    assert first["sentence_count"] >= 3
    assert 0 < first["dialogue_mark_ratio"] < 1
    assert first["avg_sentence_chars"] > 0
    # 空文本不炸，指标归零
    assert measure_text_sample("")["chars"] == 0


def test_aggregate_sample_measurements_weights_by_chars():
    short = "短句。"
    long = "这是一段明显更长的叙述文字，用来拉高加权后的平均句长指标。" * 3
    merged = aggregate_sample_measurements([short, long])
    assert merged["chunk_count"] == 2
    assert merged["sample_chars"] == len(short) + len(long)
    # 加权平均应落在两者之间，且被长文本拉高
    assert measure_text_sample(short)["avg_sentence_chars"] < merged["avg_sentence_chars"]
    assert merged["avg_sentence_chars"] < measure_text_sample(long)["avg_sentence_chars"]
    assert aggregate_sample_measurements([]) == {}


def test_parse_style_json_accepts_fence_and_rejects_garbage():
    fenced = '```json\n{"dimensions": {"a": {"value": "x"}}}\n```'
    assert parse_style_json(fenced)["dimensions"]["a"]["value"] == "x"
    assert parse_style_json('{"ok": 1}') == {"ok": 1}
    with pytest.raises(ValueError, match="缺少 JSON 对象"):
        parse_style_json("抱歉，我无法完成")
    with pytest.raises(ValueError, match="无法解析"):
        parse_style_json("{不是合法 json}")


class _StubStyleAI:
    """返回固定风格结构的假模型。"""

    def __init__(self, payload: str | None = None, success: bool = True):
        self._payload = payload
        self._success = success
        self.prompts: list[str] = []

    async def chat(self, messages, provider=None, model=None, **kwargs):
        self.prompts.append(messages[-1].content)
        if not self._success:
            return type("R", (), {"success": False, "error": "上游 500", "content": ""})()
        payload = self._payload or json.dumps(
            {
                "dimensions": {
                    "句式长度与节奏": {
                        "value": "短句推进，长句收束",
                        "confidence": 0.8,
                        "evidence_summary": "平均句长偏低",
                        "measurement_keys": ["avg_sentence_chars"],
                    }
                },
                "new_examples": ["他推开门，屋里只剩风声。"],
                "anti_template_constraints": ["避免三段式排比开头"],
                "prohibited_source_material": ["禁止带出角色原名"],
            },
            ensure_ascii=False,
        )
        return type("R", (), {"success": True, "content": payload, "error": None})()


@pytest.fixture
def snapshot_with_chunks(session):
    from app.db.models.novel_source import SourceKind

    snap = NovelSourceSnapshot(title="活着", author="余华", source_kind=SourceKind.TXT.value)
    session.add(snap)
    session.flush()
    for index, text in enumerate(
        [
            "福贵牵着牛走过田埂。天很热，牛走得慢。\n\n“歇会儿吧。”他说。",
            "后来他常坐在村口，看人来人往，不说话。风把土吹起来。",
        ]
    ):
        session.add(
            NovelTextChunk(
                snapshot_id=snap.id,
                ordinal=index,
                start_offset=index * 100,
                end_offset=index * 100 + len(text),
                content=text,
            )
        )
    session.commit()
    return snap


async def test_extract_draft_from_source_creates_draft_with_provenance(
    session, snapshot_with_chunks, monkeypatch
):
    fake = _StubStyleAI()
    monkeypatch.setattr(
        "app.services.ai.get_ai_service",
        lambda: fake,
        raising=False,
    )
    service = WritingStyleService(session)
    item = await service.extract_draft_from_source(snapshot_id=snapshot_with_chunks.id)

    # 产出恒为 draft：设计上禁止自动激活。
    assert item.status == "draft"
    assert item.source_type == "extracted_from_source"
    assert item.source_snapshot_id == snapshot_with_chunks.id
    assert item.source_sample_hash  # 样本 hash 用于溯源与去重

    profile = json.loads(item.profile_json)
    assert "句式长度与节奏" in profile["dimensions"]
    assert profile["dimensions"]["句式长度与节奏"]["measurement_keys"] == ["avg_sentence_chars"]
    assert profile["prohibited_source_material"] == ["禁止带出角色原名"]

    provenance = json.loads(item.provenance_json)
    assert provenance["snapshot_id"] == snapshot_with_chunks.id
    assert provenance["sample_chars"] > 0
    assert provenance["measurements"]["chunk_count"] == 2
    # 来源正文不入库：档案里只有统计指标与偏移，没有原文。
    assert "福贵" not in json.dumps(profile, ensure_ascii=False)
    assert "福贵" not in json.dumps(provenance, ensure_ascii=False)


async def test_extract_draft_from_source_rejects_bad_source(session, monkeypatch):
    service = WritingStyleService(session)
    with pytest.raises(ValueError, match="来源快照不存在"):
        await service.extract_draft_from_source(snapshot_id="missing")

    from app.db.models.novel_source import SourceKind

    empty = NovelSourceSnapshot(title="空", source_kind=SourceKind.TXT.value)
    session.add(empty)
    session.commit()
    with pytest.raises(ValueError, match="还没有可分析的文本块"):
        await service.extract_draft_from_source(snapshot_id=empty.id)


async def test_extract_draft_from_source_surfaces_model_failure(
    session, snapshot_with_chunks, monkeypatch
):
    fake = _StubStyleAI(success=False)
    monkeypatch.setattr(
        "app.services.ai.get_ai_service",
        lambda: fake,
        raising=False,
    )
    service = WritingStyleService(session)
    with pytest.raises(ValueError, match="上游 500"):
        await service.extract_draft_from_source(snapshot_id=snapshot_with_chunks.id)


async def test_extract_draft_from_source_rejects_unparsable_model_output(
    session, snapshot_with_chunks, monkeypatch
):
    fake = _StubStyleAI(payload="抱歉，我不能分析这段文字")
    monkeypatch.setattr(
        "app.services.ai.get_ai_service",
        lambda: fake,
        raising=False,
    )
    service = WritingStyleService(session)
    with pytest.raises(ValueError, match="缺少 JSON 对象"):
        await service.extract_draft_from_source(snapshot_id=snapshot_with_chunks.id)
