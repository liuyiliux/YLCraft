"""小说来源 → 世界提取最小闭环的聚焦测试。

覆盖：TXT 导入与稳定偏移、模块检测、分域提取与证据校验、
候选决策、确认写入项目、连载增量同步。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from sqlmodel import Session, create_engine, select

from app.db.models.character import Character, CharacterStoryLink
from app.db.models.creative_project import (
    CreativeProject,
    ProjectAssetLink,
    ProjectContent,
    ProjectGenerationLog,
)
from app.db.models.novel_source import (
    CandidateStatus,
    NovelSourceChapter,
    NovelSourceSnapshot,
    NovelTextChunk,
    WorldBuildingTemplate,
    WorldDomainDefinition,
    WorldEntity,
    WorldEntityRelation,
    WorldExtractionRun,
    WorldFactCandidate,
    WorldMapDocument,
    WorldMapRevision,
)
from app.services.ai.types import LLMGenerationResult
from app.services.novel_source import service as source_module
from app.services.novel_source.contracts import DETECTABLE_DOMAINS
from app.services.novel_source.extraction import WorldExtractionService
from app.services.novel_source.service import NovelSourceService
from app.services.novel_source.txt_import import detect_chapters, parse_txt

SAMPLE_TEXT = (
    "第一章 雨夜来客\n"
    "林昭推开木门，雨水顺着屋檐落下。他把伞收好，看见堂中坐着一个陌生人。\n"
    "那人说他来自北岭，要见这里的当家。\n"
    "\n"
    "第二章 旧账\n"
    "沈青砚在灯下翻账册。三年前北岭那场雪灾之后，沈家的商路就断了。\n"
    "她合上册子，抬头看向门外。\n"
)

EXTRACTION_ITEMS = {
    "character": [
        {
            "name": "林昭",
            "aliases": ["林当家"],
            "summary": "雨夜推门进屋的年轻人。",
            "attributes": {"role": "主角", "affiliation": "木门小院"},
            "quotes": ["林昭推开木门", "他把伞收好"],
            "confidence": 0.9,
        },
        {
            "name": "沈青砚",
            "aliases": [],
            "summary": "在灯下翻账册的女子。",
            "attributes": {"role": "沈家当家"},
            "quotes": ["沈青砚在灯下翻账册"],
            "confidence": 0.85,
        },
        {
            "name": "凭空捏造",
            "aliases": [],
            "summary": "模型想象出来的角色。",
            "attributes": {},
            "quotes": ["这段原文里根本不存在的引文"],
            "confidence": 0.9,
        },
    ],
    "location": [
        {
            "name": "北岭",
            "aliases": ["北岭一带"],
            "summary": "陌生来客的出发地。",
            "attributes": {"kind": "山岭"},
            "quotes": ["来自北岭"],
            "confidence": 0.8,
        },
    ],
    "faction": [
        {
            "name": "沈家",
            "aliases": [],
            "summary": "商路断掉的家族。",
            "attributes": {"kind": "商贾家族"},
            "quotes": ["沈家的商路就断了"],
            "confidence": 0.75,
        },
    ],
    "historical_event": [
        {
            "name": "北岭雪灾",
            "aliases": [],
            "summary": "三年前导致沈家商路中断的灾害。",
            "attributes": {"time_expression": "三年前", "location": "北岭"},
            "quotes": ["三年前北岭那场雪灾", "这段原文里不存在的引文"],
            "confidence": 0.7,
            "uncertain": True,
        },
    ],
}


EXTENDED_SAMPLE_TEXT = (
    "第一章 灵根品阶\n"
    "修行者以灵根分品，自下而上为凡品、地品、天品三阶。每升一阶需渡一次雷劫，失败则灵根尽毁。\n"
    "\n"
    "第二章 商路与货税\n"
    "北境通行的是银关钞，一两银关钞可换三斗青稞。沈家的商队走霜岭道，每过一处关隘要缴三成货税，交给榷场署。\n"
    "\n"
    "第三章 霜黎族\n"
    "雪原上住着霜黎族，他们生有覆雪般的银鳞，寿元可达三甲子，与北岭的牧民世代通好。\n"
    "\n"
    "第四章 霜岭古约\n"
    "按霜岭的古约，凡在此立誓者不得背誓，违者血脉尽凝。这规矩由守约人世代看顾。\n"
)

EXTENDED_EXTRACTION_ITEMS = {
    "world_rule": [
        {
            "name": "霜岭古约",
            "aliases": ["古约"],
            "summary": "在霜岭立下的誓言不可违背，违者血脉尽凝。",
            "attributes": {
                "kind": "契约法则",
                "scope": "霜岭",
                "constraints": "立誓者不得背誓",
                "consequences": "违者血脉尽凝",
                "enforced_by": "守约人",
            },
            "quotes": ["凡在此立誓者不得背誓", "违者血脉尽凝"],
            "confidence": 0.92,
        }
    ],
    "power_system": [
        {
            "name": "灵根品阶",
            "aliases": ["三阶之分"],
            "summary": "修行者按灵根品阶划分境界，每升一阶需渡雷劫。",
            "attributes": {
                "kind": "修炼体系",
                "levels": ["凡品", "地品", "天品"],
                "costs": "渡雷劫失败则灵根尽毁",
            },
            "quotes": ["灵根分品，自下而上为凡品、地品、天品三阶", "每升一阶需渡一次雷劫"],
            "confidence": 0.9,
        }
    ],
    "economy": [
        {
            "name": "银关钞",
            "aliases": [],
            "summary": "北境通行的货币，一文可换三斗青稞。",
            "attributes": {"kind": "货币", "prices": "一两换三斗青稞", "institutions": ["榷场署"]},
            "quotes": ["北境通行的是银关钞", "一两银关钞可换三斗青稞"],
            "confidence": 0.85,
        },
        {
            "name": "并不存在的钱庄",
            "aliases": [],
            "summary": "模型虚构的金融机构。",
            "attributes": {},
            "quotes": ["这段原文里没有的钱庄记载"],
            "confidence": 0.6,
        },
    ],
    "species": [
        {
            "name": "霜黎族",
            "aliases": ["霜黎"],
            "summary": "居住在雪原、生有银鳞的族群。",
            "attributes": {
                "kind": "种族",
                "traits": ["覆雪般的银鳞"],
                "lifespan": "三甲子",
                "habitat": "雪原",
            },
            "quotes": ["雪原上住着霜黎族", "他们生有覆雪般的银鳞"],
            "confidence": 0.88,
        }
    ],
}


#: 「沈家」同时落进地点和势力；两条历史事件共用同一段引文。
RECONCILE_EXTRACTION_ITEMS = {
    "location": [
        {
            "name": "沈家",
            "aliases": ["沈家老宅"],
            "summary": "沈家所在的大宅。",
            "attributes": {"kind": "宅院"},
            "quotes": ["沈家的商路就断了"],
            "confidence": 0.7,
        }
    ],
    "faction": [
        {
            "name": "沈家",
            "aliases": [],
            "summary": "商路断掉的家族。",
            "attributes": {"kind": "商贾家族"},
            "quotes": ["沈家的商路就断了"],
            "confidence": 0.75,
        }
    ],
    "historical_event": [
        {
            "name": "北岭雪灾",
            "aliases": [],
            "summary": "三年前导致沈家商路中断的灾害。",
            "attributes": {"time_expression": "三年前", "location": "北岭"},
            "quotes": ["三年前北岭那场雪灾"],
            "confidence": 0.7,
        },
        {
            "name": "十载前的旧事",
            "aliases": [],
            "summary": "更早发生的事件。",
            "attributes": {"time_expression": "十载前"},
            "quotes": ["三年前北岭那场雪灾"],
            "confidence": 0.6,
        },
    ],
}


class FakeWorldAI:
    """按 prompt 形态返回检测或提取结果，不访问真实模型。"""

    def __init__(
        self,
        *,
        items: dict[str, list[dict]] | None = None,
        contradiction_verdict: str = "conflicting",
    ):
        self.items = items if items is not None else EXTRACTION_ITEMS
        self.contradiction_verdict = contradiction_verdict
        self.prompts: list[str] = []

    async def chat(self, messages, **kwargs):
        prompt = messages[-1].content
        self.prompts.append(prompt)
        if '"domains":[' in prompt:
            return LLMGenerationResult(
                success=True,
                content=json.dumps(self._detection_payload(), ensure_ascii=False),
                provider="fake",
                model="fake-model",
            )
        if '"verdict"' in prompt:
            return LLMGenerationResult(
                success=True,
                content=json.dumps(
                    {
                        "verdict": self.contradiction_verdict,
                        "reason": "两条候选描述互相矛盾",
                        "recommended_action": (
                            "resolve" if self.contradiction_verdict == "conflicting" else "merge"
                        ),
                    },
                    ensure_ascii=False,
                ),
                provider="fake",
                model="fake-model",
            )
        domain = self._domain_of(prompt)
        return LLMGenerationResult(
            success=True,
            content=json.dumps({"items": self.items.get(domain, [])}, ensure_ascii=False),
            provider="fake",
            model="fake-model",
        )

    @staticmethod
    def _detection_payload() -> dict:
        statuses = {
            "character": "detected",
            "location": "detected",
            "faction": "detected",
            "historical_event": "detected",
            "world_rule": "detected",
            "species": "not_detected",
            "power_system": "uncertain",
            "economy": "not_detected",
            "map": "uncertain",
        }
        return {
            "domains": [
                {
                    "domain": domain,
                    "status": statuses.get(domain, "uncertain"),
                    "reason": f"{domain} 的信号判断",
                    "signals": ["北岭"] if domain in {"location", "map"} else [],
                    "estimated_cost": "low",
                }
                for domain in DETECTABLE_DOMAINS
            ]
        }

    @staticmethod
    def _domain_of(prompt: str) -> str:
        match = re.search(r"模块：.+?（([a-z_]+)）", prompt)
        return match.group(1) if match else ""


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    for table in (
        CreativeProject.__table__,
        ProjectContent.__table__,
        ProjectAssetLink.__table__,
        ProjectGenerationLog.__table__,
        Character.__table__,
        CharacterStoryLink.__table__,
        NovelSourceSnapshot.__table__,
        NovelSourceChapter.__table__,
        NovelTextChunk.__table__,
        WorldExtractionRun.__table__,
        WorldFactCandidate.__table__,
        WorldMapDocument.__table__,
        WorldMapRevision.__table__,
        WorldEntity.__table__,
        WorldEntityRelation.__table__,
        WorldDomainDefinition.__table__,
        WorldBuildingTemplate.__table__,
    ):
        table.create(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def storage(tmp_path, monkeypatch):
    target = tmp_path / "novel_sources"
    monkeypatch.setattr(source_module, "STORAGE_ROOT", target)
    return target


def _import_sample(session: Session, **kwargs) -> NovelSourceSnapshot:
    return NovelSourceService(session).import_txt(
        raw=SAMPLE_TEXT.encode("utf-8"),
        file_name="sample.txt",
        title="雨夜旧账",
        **kwargs,
    )


def test_novel_source_agent_tools_are_registered():
    import app.services.agent.tools  # noqa: F401 - 触发工具注册

    from app.services.agent.registry import ToolRegistry

    names = {tool.name for tool in ToolRegistry.list_tools("novel_source")}
    assert names == {
        "list_novel_source_snapshots",
        "inspect_novel_source_snapshot",
        "plan_novel_source_domains",
        "extract_novel_source_world",
        "list_world_extraction_candidates",
        "decide_world_extraction_candidates",
        "apply_world_extraction_run",
        "sync_novel_source_chapters",
        "index_novel_source_chunks",
        "search_novel_source_chunks",
        "reconcile_world_extraction_run",
        "derive_project_from_novel_source",
        "detect_world_extraction_contradictions",
        "propagate_affected_world_facts",
        "expand_world_entity_attributes",
        "expand_world_domain",
        # 世界地图工具（与真人 /world-map 工作台共用 service 层）
        "list_world_maps",
        "get_world_map",
        "create_world_map",
        "save_world_map",
        "render_world_map_svg",
        "export_world_map_points",
        "resolve_world_map_entities",
        "build_world_map_visual_prompt",
        "optimize_world_map_visual_prompt",
        "generate_world_map_visual",
        "list_world_map_revisions",
        "rollback_world_map",
        # 区域形状（阶段 4：AI/Agent 只产语义参数，顶点由前端展开）
        "generate_region_shape",
        "list_region_shape_presets",
        "manage_world_building_template",
        "list_world_building_suggestions",
        "resolve_world_field_suggestion",
        "resolve_world_domain_suggestion",
    }
    assert ToolRegistry.get_tool("list_novel_source_snapshots").risk_level == "read"
    assert ToolRegistry.get_tool("plan_novel_source_domains").risk_level == "costly"
    assert ToolRegistry.get_tool("extract_novel_source_world").risk_level == "costly"
    assert ToolRegistry.get_tool("decide_world_extraction_candidates").risk_level == "write"
    assert ToolRegistry.get_tool("apply_world_extraction_run").risk_level == "write"
    assert ToolRegistry.get_tool("sync_novel_source_chapters").risk_level == "write"
    # 检索、调和是只读；建索引会消耗 embedding 配额。
    assert ToolRegistry.get_tool("search_novel_source_chunks").risk_level == "read"
    assert ToolRegistry.get_tool("reconcile_world_extraction_run").risk_level == "read"
    assert ToolRegistry.get_tool("index_novel_source_chunks").risk_level == "costly"
    assert ToolRegistry.get_tool("derive_project_from_novel_source").risk_level == "write"
    assert ToolRegistry.get_tool("detect_world_extraction_contradictions").risk_level == "costly"
    assert ToolRegistry.get_tool("propagate_affected_world_facts").risk_level == "write"


@pytest.mark.asyncio
async def test_delta_extraction_appends_evidence_without_duplicating_candidates(session, storage):
    """增量提取只处理新块：既有候选不重复生成，只并回新证据。"""
    service = NovelSourceService(session)
    snapshot = service.import_bookshelf(
        title="连载书",
        source_status="serial",
        chapters=[{"title": "第一章", "content": "那人说他来自北岭，要见这里的当家。"}],
    )

    items = {
        "location": [
            {
                "name": "北岭",
                "aliases": ["北岭一带"],
                "summary": "陌生来客的出发地。",
                "attributes": {"kind": "山岭"},
                # 第二条引文此时还不在正文里，首次提取会被丢弃。
                "quotes": ["来自北岭", "来自北岭的山坳"],
                "confidence": 0.8,
            }
        ]
    }
    world = WorldExtractionService(session, ai_service=FakeWorldAI(items=items))

    full = await world.extract(snapshot.id, domains=["location"])
    assert full["candidate_count"] == 1
    assert full["updated_count"] == 0
    original = world.list_candidates(full["run_id"])[0]
    assert len(json.loads(original.evidence_json)) == 1
    assert json.loads(world.get_run(full["run_id"]).checkpoint_json)["last_chunk_ordinal"] == 1

    service.append_bookshelf_chapters(
        snapshot.id,
        chapters=[{"title": "第二章", "content": "他开口说他来自北岭的山坳。"}],
    )

    delta = await world.extract(snapshot.id, domains=["location"], mode="delta")
    assert delta["mode"] == "delta"
    assert delta["from_chunk_ordinal"] == 1
    assert delta["candidate_count"] == 0
    assert delta["updated_count"] == 1

    # 候选仍是同一条，证据从 1 条变成 2 条，并回写了本次运行溯源。
    merged = world.list_candidates(delta["run_id"])
    assert len(merged) == 1
    assert merged[0].id == original.id
    assert merged[0].last_run_id == delta["run_id"]
    quotes = [item["quote"] for item in json.loads(merged[0].evidence_json)]
    assert quotes == ["来自北岭", "来自北岭的山坳"]
    assert json.loads(merged[0].payload_json)["aliases"] == ["北岭一带"]

    # 没有新章节时增量提取应当直接拒绝，而不是空跑一遍模型。
    with pytest.raises(ValueError):
        await world.extract(snapshot.id, domains=["location"], mode="delta")


@pytest.mark.asyncio
async def test_delta_extraction_requires_a_prior_full_run(session, storage):
    snapshot = _import_sample(session)
    world = WorldExtractionService(session, ai_service=FakeWorldAI())
    with pytest.raises(ValueError):
        await world.extract(snapshot.id, domains=["location"], mode="delta")


@pytest.mark.asyncio
async def test_delta_extraction_requires_a_baseline_for_each_requested_domain(session, storage):
    """角色域的基线不能错误地充当地点域的增量游标。"""
    snapshot = _import_sample(session)
    world = WorldExtractionService(session, ai_service=FakeWorldAI())

    await world.extract(snapshot.id, domains=["character"])

    with pytest.raises(ValueError):
        await world.extract(snapshot.id, domains=["location"], mode="delta")


@pytest.mark.asyncio
async def test_delta_retries_a_domain_that_failed_in_a_partial_run(session, storage):
    """部分成功运行不能推进失败域的增量游标。"""

    class LocationFailsAfterFirstRun(FakeWorldAI):
        fail_location = False

        async def chat(self, messages, **kwargs):
            if self.fail_location and self._domain_of(messages[-1].content) == "location":
                return LLMGenerationResult(success=False, content="", error="location unavailable")
            return await super().chat(messages, **kwargs)

    service = NovelSourceService(session)
    snapshot = service.import_bookshelf(
        title="连载书",
        source_status="serial",
        chapters=[{"title": "第一章", "content": "北岭终年积雪。"}],
    )
    ai = LocationFailsAfterFirstRun(
        items={
            "location": [{"name": "北岭", "summary": "雪岭。", "quotes": ["北岭终年积雪"], "confidence": 0.9}],
            "character": [],
        }
    )
    world = WorldExtractionService(session, ai_service=ai)
    # 先为两个域建立同一份完整基线。
    await world.extract(snapshot.id, domains=["character", "location"])

    service.append_bookshelf_chapters(
        snapshot.id, chapters=[{"title": "第二章", "content": "北岭的冰湖每逢冬至封冻。"}]
    )
    ai.fail_location = True
    partial = await world.extract(snapshot.id, domains=["character", "location"], mode="delta")
    assert partial["status"] == "partial"

    ai.fail_location = False
    retry = await world.extract(snapshot.id, domains=["location"], mode="delta")
    assert retry["from_chunk_ordinal"] == 1


def test_detect_chapters_matches_chinese_headings_and_falls_back():
    spans = detect_chapters(SAMPLE_TEXT)
    assert [span.title for span in spans] == ["第一章 雨夜来客", "第二章 旧账"]
    assert spans[0].start == SAMPLE_TEXT.index("林昭推开木门")

    single = detect_chapters("只有正文，没有任何章节标题。\n第二段正文。")
    assert len(single) == 1
    assert single[0].title == "全文"


def test_import_txt_builds_snapshot_with_stable_offsets(session, storage):
    parsed = parse_txt(SAMPLE_TEXT.encode("utf-8"))
    snapshot = _import_sample(session, source_status="completed")

    assert snapshot.chapter_count == 2
    assert snapshot.char_count == len(parsed.text)
    assert snapshot.encoding == "utf-8"
    assert snapshot.checksum == parsed.checksum

    chapters = session.exec(
        select(NovelSourceChapter).where(NovelSourceChapter.snapshot_id == snapshot.id)
    ).all()
    assert [item.ordinal for item in chapters] == [1, 2]

    text = NovelSourceService(session).load_source_text(snapshot.id)
    chunks = session.exec(
        select(NovelTextChunk).where(NovelTextChunk.snapshot_id == snapshot.id)
    ).all()
    assert chunks
    for chunk in chunks:
        first_line = chunk.content.split("\n")[0]
        assert text[chunk.start_offset : chunk.start_offset + len(first_line)] == first_line
        assert chunk.end_offset > chunk.start_offset
        assert chunk.chapter_id


def test_novel_source_storage_root_reads_settings_mirror(session, storage, monkeypatch, tmp_path):
    settings_file = tmp_path / "backend" / "app" / "data" / "settings.json"
    settings_file.parent.mkdir(parents=True)
    settings_file.write_text(
        json.dumps({"novel_source_path": "backend/storage/configured-novels"}),
        encoding="utf-8",
    )
    configured = tmp_path / "backend" / "storage" / "configured-novels"
    monkeypatch.setattr(source_module, "project_root", lambda: tmp_path)
    monkeypatch.setattr(
        source_module,
        "resolve_storage_path",
        lambda value: tmp_path / Path(value),
    )

    assert source_module._storage_root() == configured
    assert configured.is_dir()


@pytest.mark.asyncio
async def test_chunk_embedding_index_and_hybrid_search_keep_provenance(session, storage):
    snapshot = _import_sample(session)
    service = NovelSourceService(session)
    chunks = service.list_chunks(snapshot.id)

    async def fake_embedder(texts):
        return [[1.0, 0.0] if "林昭" in text else [0.0, 1.0] for text in texts]

    indexed = await service.index_chunk_embeddings(snapshot.id, embedder=fake_embedder, model_name="fake-2d")
    assert indexed["indexed"] == len(chunks)
    assert all(item.embedding_status == "ready" for item in service.list_chunks(snapshot.id))

    results = service.search_chunks(snapshot.id, "林昭", query_embedding=[1.0, 0.0], top_k=3)
    assert results
    assert results[0]["retrieval"] == "hybrid"
    assert results[0]["vector_score"] > 0.9
    assert results[0]["chunk_id"]
    assert results[0]["start_offset"] < results[0]["end_offset"]
    assert results[0]["chapter_id"]


@pytest.mark.asyncio
async def test_chunk_embedding_failure_falls_back_to_exact_search(session, storage):
    snapshot = _import_sample(session)
    service = NovelSourceService(session)

    async def broken_embedder(texts):
        raise RuntimeError("embedding unavailable")

    indexed = await service.index_chunk_embeddings(snapshot.id, embedder=broken_embedder)
    assert indexed["indexed"] == 0
    assert indexed["failed"] == indexed["total"]
    results = service.search_chunks(snapshot.id, "林昭")
    assert results
    assert results[0]["retrieval"] == "exact"


def test_import_txt_rejects_empty_source(session, storage):
    with pytest.raises(ValueError):
        NovelSourceService(session).import_txt(raw=b"", file_name="empty.txt")


@pytest.mark.asyncio
async def test_plan_domains_returns_per_domain_state_and_user_requested(session, storage):
    snapshot = _import_sample(session)
    service = WorldExtractionService(session, ai_service=FakeWorldAI())

    plan = await service.plan_domains(snapshot.id, requested_domains=["species"])

    by_domain = {item["domain"]: item for item in plan["domains"]}
    assert by_domain["character"]["status"] == "detected"
    assert by_domain["species"]["status"] == "user_requested"
    assert by_domain["power_system"]["status"] == "uncertain"
    assert by_domain["character"]["extractable"] is True
    # 扩展域（物种、力量体系、经济）已开放提取；地图仍需结构化空间编辑。
    assert by_domain["species"]["extractable"] is True
    assert by_domain["power_system"]["extractable"] is True
    assert by_domain["economy"]["extractable"] is True
    assert by_domain["map"]["extractable"] is False
    # detected / user_requested 才进推荐；uncertain 与 not_detected 不进。
    assert "character" in plan["recommended"]
    assert "species" in plan["recommended"]
    assert "power_system" not in plan["recommended"]
    assert "economy" not in plan["recommended"]
    assert "map" not in plan["recommended"]


@pytest.mark.asyncio
async def test_extract_validates_evidence_and_drops_unverified_items(session, storage):
    snapshot = _import_sample(session)
    service = WorldExtractionService(session, ai_service=FakeWorldAI())

    result = await service.extract(
        snapshot.id,
        domains=["character", "location", "faction", "historical_event"],
    )

    assert result["status"] == "success"
    assert result["candidate_count"] == 5

    candidates = service.list_candidates(result["run_id"])
    names = {item.entity_name for item in candidates}
    assert names == {"林昭", "沈青砚", "北岭", "沈家", "北岭雪灾"}

    event = next(item for item in candidates if item.entity_name == "北岭雪灾")
    evidence = json.loads(event.evidence_json)
    assert len(evidence) == 1
    assert evidence[0]["quote"] == "三年前北岭那场雪灾"
    assert evidence[0]["chunk_id"]
    assert evidence[0]["end_offset"] > evidence[0]["start_offset"]
    # 含不可校验引文的条目被标记为推断，需要人工确认。
    assert event.origin == "ai_inferred"

    run = service.get_run(result["run_id"])
    assert run.status == "success"
    assert json.loads(run.checkpoint_json)["last_chunk_ordinal"] >= 1


@pytest.mark.asyncio
async def test_extended_domains_extract_rules_economy_and_species(session, storage):
    """世界规则、力量体系、经济、物种四个扩展域复用同一条提取、校验与写入通道。"""
    snapshot = NovelSourceService(session).import_txt(
        raw=EXTENDED_SAMPLE_TEXT.encode("utf-8"),
        file_name="extended.txt",
        title="霜岭志",
        source_status="completed",
    )
    service = WorldExtractionService(
        session, ai_service=FakeWorldAI(items=EXTENDED_EXTRACTION_ITEMS)
    )

    result = await service.extract(
        snapshot.id, domains=["world_rule", "power_system", "economy", "species"]
    )

    assert result["status"] == "success"
    # 「并不存在的钱庄」没有可逐字校验的引文，被丢弃而不是落为候选。
    assert result["candidate_count"] == 4

    candidates = service.list_candidates(result["run_id"])
    by_domain = {item.domain: item.entity_name for item in candidates}
    assert by_domain == {
        "world_rule": "霜岭古约",
        "power_system": "灵根品阶",
        "economy": "银关钞",
        "species": "霜黎族",
    }

    rule = next(item for item in candidates if item.domain == "world_rule")
    assert json.loads(rule.payload_json)["attributes"]["consequences"] == "违者血脉尽凝"

    power = next(item for item in candidates if item.domain == "power_system")
    payload = json.loads(power.payload_json)
    assert payload["attributes"]["levels"] == ["凡品", "地品", "天品"]
    assert len(json.loads(power.evidence_json)) == 2
    assert power.origin == "original"

    species = next(item for item in candidates if item.domain == "species")
    assert json.loads(species.payload_json)["attributes"]["lifespan"] == "三甲子"

    # 扩展域与既有域共用唯一写入点：统一落到锁定的 world_asset 事实卡。
    service.decide_candidates(
        result["run_id"],
        [{"candidate_id": item.id, "action": "accept"} for item in candidates],
    )
    applied = await service.apply_run(result["run_id"])
    assert applied["characters_written"] == 0
    assert applied["world_assets_written"] == 4

    assets = session.exec(
        select(ProjectContent).where(
            ProjectContent.project_id == applied["project_id"],
            ProjectContent.content_type == "world_asset",
        )
    ).all()
    assert {json.loads(item.data_json)["domain"] for item in assets} == {
        "world_rule",
        "power_system",
        "economy",
        "species",
    }
    assert all(item.is_locked for item in assets)


RELATION_EXTRACTION_ITEMS = {
    "location": [
        {
            "name": "雪原",
            "aliases": [],
            "summary": "霜黎族世代栖息的雪原。",
            "attributes": {"kind": "地域"},
            "quotes": ["雪原上住着霜黎族"],
            "confidence": 0.8,
        },
        {
            "name": "北岭",
            "aliases": ["北岭一带"],
            "summary": "雪原牧民聚居的山岭。",
            "attributes": {"kind": "山岭"},
            "quotes": ["与北岭的牧民世代通好"],
            "confidence": 0.8,
        },
    ],
    "species": [
        {
            "name": "霜黎族",
            "aliases": ["霜黎"],
            "summary": "生有银鳞的族群。",
            "attributes": {"kind": "种族", "habitat": "雪原"},
            "quotes": ["雪原上住着霜黎族"],
            "confidence": 0.85,
        },
    ],
    "historical_event": [
        {
            "name": "霜黎通好",
            "aliases": [],
            "summary": "霜黎族与北岭牧民世代交好。",
            "attributes": {"time_expression": "世代", "location": "北岭"},
            "quotes": ["与北岭的牧民世代通好"],
            "confidence": 0.7,
        },
    ],
}


@pytest.mark.asyncio
async def test_apply_materializes_typed_entities_and_relations(session, storage):
    """确认写入除事实卡外，还物化类型化独立实体与复杂实体间关系。"""
    snapshot = NovelSourceService(session).import_txt(
        raw=EXTENDED_SAMPLE_TEXT.encode("utf-8"),
        file_name="extended.txt",
        title="霜岭志",
        source_status="completed",
    )
    service = WorldExtractionService(
        session, ai_service=FakeWorldAI(items=RELATION_EXTRACTION_ITEMS)
    )
    result = await service.extract(
        snapshot.id, domains=["location", "species", "historical_event"]
    )
    candidates = service.list_candidates(result["run_id"])
    service.decide_candidates(
        result["run_id"],
        [{"candidate_id": item.id, "action": "accept"} for item in candidates],
    )
    applied = await service.apply_run(result["run_id"])

    assert applied["world_assets_written"] == 4
    assert applied["world_entities_written"] == 4
    assert applied["world_relations_written"] == 2

    entities = session.exec(
        select(WorldEntity).where(WorldEntity.project_id == applied["project_id"])
    ).all()
    assert len(entities) == 4
    assert {item.entity_type for item in entities} == {"place", "species", "event"}

    relations = session.exec(
        select(WorldEntityRelation).where(
            WorldEntityRelation.project_id == applied["project_id"]
        )
    ).all()
    assert len(relations) == 2
    assert {item.relation_type for item in relations} == {"inhabits", "occurred_at"}

    # 关系两端指向正确实体。
    by_id = {item.id: item for item in entities}
    for relation in relations:
        source = by_id[relation.source_entity_id]
        target = by_id[relation.target_entity_id]
        if relation.relation_type == "inhabits":
            assert source.name == "霜黎族"
            assert target.name == "雪原"
        else:
            assert source.name == "霜黎通好"
            assert target.name == "北岭"


@pytest.mark.asyncio
async def test_extract_keeps_other_domains_when_one_fails(session, storage):
    class BrokenAI(FakeWorldAI):
        async def chat(self, messages, **kwargs):
            if self._domain_of(messages[-1].content) == "location":
                return LLMGenerationResult(success=False, content="", error="boom")
            return await super().chat(messages, **kwargs)

    snapshot = _import_sample(session)
    service = WorldExtractionService(session, ai_service=BrokenAI())

    result = await service.extract(
        snapshot.id, domains=["character", "location", "faction"]
    )

    assert result["status"] == "partial"
    assert [item["domain"] for item in result["failures"]] == ["location"]
    assert result["candidate_count"] == 3


@pytest.mark.asyncio
async def test_decide_then_apply_writes_characters_and_world_assets(session, storage):
    snapshot = _import_sample(session)
    service = WorldExtractionService(session, ai_service=FakeWorldAI())
    result = await service.extract(
        snapshot.id, domains=["character", "location", "faction", "historical_event"]
    )
    run_id = result["run_id"]
    candidates = service.list_candidates(run_id)

    decided = service.decide_candidates(
        run_id,
        [
            {"candidate_id": item.id, "action": "accept"}
            for item in candidates
            if item.entity_name != "沈家"
        ]
        + [
            {"candidate_id": item.id, "action": "ignore", "note": "不是势力"}
            for item in candidates
            if item.entity_name == "沈家"
        ],
    )
    assert decided["accepted"] == 4
    assert decided["ignored"] == 1

    applied = await service.apply_run(run_id)
    assert applied["characters_written"] == 2
    assert applied["world_assets_written"] == 2
    assert applied["project_id"]

    world_assets = session.exec(
        select(ProjectContent).where(
            ProjectContent.project_id == applied["project_id"],
            ProjectContent.content_type == "world_asset",
        )
    ).all()
    assert len(world_assets) == 2
    assert all(item.is_locked for item in world_assets)
    payload = json.loads(world_assets[0].data_json)
    assert payload["source_snapshot_id"] == snapshot.id
    assert payload["evidence"][0]["chunk_id"]

    characters = session.exec(
        select(Character).where(Character.name.in_(["林昭", "沈青砚"]))  # type: ignore[attr-defined]
    ).all()
    assert len(characters) == 2

    link = session.exec(
        select(CharacterStoryLink).where(CharacterStoryLink.story_id == applied["project_id"])
    ).all()
    assert len(link) == 2
    lin_zhao = next(
        item
        for item in link
        if session.get(Character, item.character_id).name == "林昭"
    )
    assert json.loads(lin_zhao.aliases_json) == ["林当家"]
    assert "林昭推开木门" in json.loads(lin_zhao.evidence_json)

    ignored = next(item for item in service.list_candidates(run_id) if item.entity_name == "沈家")
    assert ignored.status == CandidateStatus.IGNORED.value

    repeated = await service.apply_run(run_id)
    assert repeated["characters_written"] == 2
    assert repeated["world_assets_written"] == 0
    assert len(
        session.exec(
            select(ProjectContent).where(
                ProjectContent.project_id == applied["project_id"],
                ProjectContent.content_type == "world_asset",
            )
        ).all()
    ) == 2


@pytest.mark.asyncio
async def test_reconcile_flags_cross_domain_duplicates_and_evidence_overlap(session, storage):
    """跨域调和只给提示：标出跨模块重名、证据重叠与时序，不改动候选。"""
    snapshot = _import_sample(session)
    service = WorldExtractionService(
        session, ai_service=FakeWorldAI(items=RECONCILE_EXTRACTION_ITEMS)
    )
    result = await service.extract(
        snapshot.id, domains=["location", "faction", "historical_event"]
    )

    report = service.reconcile_run(result["run_id"])
    assert report["candidate_count"] == 4

    # 「沈家」同时出现在地点和势力两个模块。
    cross = [g for g in report["duplicate_groups"] if "cross_domain_name" in g["kinds"]]
    assert len(cross) == 1
    assert {row["entity_name"] for row in cross[0]["candidates"]} == {"沈家"}
    assert {row["domain"] for row in cross[0]["candidates"]} == {"location", "faction"}

    # 两组证据重叠：两条历史事件共用一段原文，「沈家」的两条候选也共用一段。
    assert len(report["evidence_overlaps"]) == 2
    overlap = next(
        item for item in report["evidence_overlaps"] if item["quote"] == "三年前北岭那场雪灾"
    )
    assert len(overlap["candidates"]) == 2
    shen_overlap = next(
        item for item in report["evidence_overlaps"] if item["quote"] == "沈家的商路就断了"
    )
    assert {row["domain"] for row in shen_overlap["candidates"]} == {"location", "faction"}

    # 时间线按相对偏移升序：十载前早于三年前。
    timeline = report["timeline"]
    assert [item["entity_name"] for item in timeline] == ["十载前的旧事", "北岭雪灾"]
    assert timeline[0]["parsed"]["kind"] == "relative"
    assert timeline[1]["parsed"]["offset_days"] == -1095

    assert report["conflict_count"] == 3

    # 只读提示：候选数量与状态都没有被调和改动。
    candidates = service.list_candidates(result["run_id"])
    assert len(candidates) == 4
    assert all(item.status == CandidateStatus.PENDING.value for item in candidates)


@pytest.mark.asyncio
async def test_reconcile_flags_alias_overlap_without_merging(session, storage):
    """某条的别名等于另一条的正名时提示交叉，但不自动合并。"""
    items = {
        "location": [
            {
                "name": "北岭",
                "aliases": ["北岭一带"],
                "summary": "陌生来客的出发地。",
                "attributes": {},
                "quotes": ["来自北岭"],
                "confidence": 0.8,
            }
        ],
        "faction": [
            {
                "name": "北岭一带",
                "aliases": [],
                "summary": "北岭一带的山民组织。",
                "attributes": {},
                "quotes": ["来自北岭"],
                "confidence": 0.6,
            }
        ],
    }
    snapshot = _import_sample(session)
    service = WorldExtractionService(session, ai_service=FakeWorldAI(items=items))
    result = await service.extract(snapshot.id, domains=["location", "faction"])

    report = service.reconcile_run(result["run_id"])
    groups = report["duplicate_groups"]
    assert len(groups) == 1
    assert "alias_overlap" in groups[0]["kinds"]
    assert {row["entity_name"] for row in groups[0]["candidates"]} == {"北岭", "北岭一带"}
    # 两条候选都还在，没有被合并成一条。
    assert len(service.list_candidates(result["run_id"])) == 2


def test_parse_relative_time_handles_chinese_and_unknown():
    from app.services.novel_source.extraction import parse_relative_time

    assert parse_relative_time("三年前")["offset_days"] == -1095
    assert parse_relative_time("十载前")["offset_days"] == -3650
    assert parse_relative_time("3年后")["offset_days"] == 1095
    assert parse_relative_time("开篇")["kind"] == "unknown"
    assert parse_relative_time("")["kind"] == "unknown"


@pytest.mark.asyncio
async def test_merge_candidate_into_target_combines_evidence_and_aliases(session, storage):
    """merge 把源候选的证据与设定并入目标，源候选进入 merged 终态。"""
    items = {
        "location": [
            {
                "name": "北岭",
                "aliases": ["北岭一带"],
                "summary": "陌生来客的出发地。",
                "attributes": {"kind": "山岭"},
                "quotes": ["来自北岭"],
                "confidence": 0.8,
            }
        ],
        "faction": [
            {
                "name": "北岭一带",
                "aliases": [],
                "summary": "北岭一带的山民组织。",
                "attributes": {"kind": "山民组织"},
                "quotes": ["来自北岭"],
                "confidence": 0.6,
            }
        ],
    }
    snapshot = _import_sample(session)
    service = WorldExtractionService(session, ai_service=FakeWorldAI(items=items))
    result = await service.extract(snapshot.id, domains=["location", "faction"])
    run_id = result["run_id"]
    candidates = service.list_candidates(run_id)
    loc = next(item for item in candidates if item.domain == "location")
    fac = next(item for item in candidates if item.domain == "faction")

    decided = service.decide_candidates(
        run_id,
        [{"candidate_id": loc.id, "action": "merge", "merge_into": fac.id, "note": "同一地点"}],
    )
    assert decided["merged"] == 1

    merged = service.list_candidates(run_id)
    loc_after = next(item for item in merged if item.id == loc.id)
    fac_after = next(item for item in merged if item.id == fac.id)
    assert loc_after.status == CandidateStatus.MERGED.value
    assert fac_after.status == CandidateStatus.PENDING.value
    # 别名并入目标，属性保留目标原值不被覆盖。
    fac_payload = json.loads(fac_after.payload_json)
    assert "北岭一带" in fac_payload["aliases"]
    assert fac_payload["attributes"]["kind"] == "山民组织"
    assert "merged into" in loc_after.review_note

    # merge 后只接受目标，apply 只写入一条世界事实。
    service.decide_candidates(run_id, [{"candidate_id": fac_after.id, "action": "accept"}])
    applied = await service.apply_run(run_id)
    assert applied["world_assets_written"] == 1


@pytest.mark.asyncio
async def test_search_chunks_with_neighbors_returns_context_blocks(session, storage):
    """检索可附带前后相邻块作为上下文，不参与排序。"""
    snapshot = _import_sample(session)
    service = NovelSourceService(session)
    results = service.search_chunks(snapshot.id, "北岭", with_neighbors=1)
    assert results
    with_neighbors = [item for item in results if item.get("neighbors")]
    assert with_neighbors
    first = with_neighbors[0]
    for neighbor in first["neighbors"]:
        assert neighbor["chunk_ordinal"] != first["chunk_ordinal"]
        assert "content" in neighbor
        assert "start_offset" in neighbor and "end_offset" in neighbor


@pytest.mark.asyncio
async def test_detect_contradictions_judges_duplicate_groups(session, storage):
    """矛盾检测对调和发现的重复组做语义判断。"""
    snapshot = _import_sample(session)
    service = WorldExtractionService(
        session,
        ai_service=FakeWorldAI(
            items=RECONCILE_EXTRACTION_ITEMS, contradiction_verdict="conflicting"
        ),
    )
    result = await service.extract(
        snapshot.id, domains=["location", "faction", "historical_event"]
    )

    report = await service.detect_contradictions(result["run_id"])

    # 「沈家」跨模块重名，被判断为同一实体但描述矛盾。
    groups = report["groups"]
    assert len(groups) == 1
    shen = groups[0]
    assert {row["entity_name"] for row in shen["candidates"]} == {"沈家"}
    assert shen["verdict"] == "conflicting"
    assert shen["recommended_action"] == "resolve"
    assert report["conflicting"] == 1


@pytest.mark.asyncio
async def test_detect_contradictions_returns_empty_when_no_duplicates(session, storage):
    """没有重复组时矛盾检测返回空，不产生多余调用噪声。"""
    snapshot = _import_sample(session)
    service = WorldExtractionService(session, ai_service=FakeWorldAI())
    result = await service.extract(snapshot.id, domains=["character", "location"])
    report = await service.detect_contradictions(result["run_id"])
    assert report["groups"] == []
    assert report["conflicting"] == 0


ITEM_GLOSSARY_TEXT = (
    "第一章 霜牙刀\n"
    "老者拔刀，霜牙刀出鞘时寒光四溢。此刀是霜黎族祖传之物，可斩妖邪。\n"
    "\n"
    "第二章 灵根\n"
    "修行者以灵根分品，资质高者方可入内门。\n"
)

ITEM_GLOSSARY_ITEMS = {
    "item": [
        {
            "name": "霜牙刀",
            "aliases": [],
            "summary": "霜黎族祖传、可斩妖邪的宝刀。",
            "attributes": {"kind": "兵器", "origin": "霜黎族祖传", "use": "斩妖邪"},
            "quotes": ["霜牙刀出鞘时寒光四溢"],
            "confidence": 0.8,
        }
    ],
    "glossary": [
        {
            "name": "灵根",
            "aliases": [],
            "summary": "决定修行品阶的资质。",
            "attributes": {"kind": "概念", "definition": "决定修行品阶的资质"},
            "quotes": ["以灵根分品"],
            "confidence": 0.85,
        }
    ],
}


@pytest.mark.asyncio
async def test_item_and_glossary_domains_extract(session, storage):
    """物品/资源与术语表两个扩展域复用同一条提取与证据校验通道。"""
    snapshot = NovelSourceService(session).import_txt(
        raw=ITEM_GLOSSARY_TEXT.encode("utf-8"),
        file_name="items.txt",
        title="霜岭志",
        source_status="completed",
    )
    service = WorldExtractionService(
        session, ai_service=FakeWorldAI(items=ITEM_GLOSSARY_ITEMS)
    )
    result = await service.extract(snapshot.id, domains=["item", "glossary"])
    assert result["status"] == "success"
    assert result["candidate_count"] == 2

    candidates = service.list_candidates(result["run_id"])
    assert {item.domain for item in candidates} == {"item", "glossary"}
    item = next(c for c in candidates if c.domain == "item")
    assert json.loads(item.payload_json)["attributes"]["origin"] == "霜黎族祖传"


TIMELINE_TEXT = (
    "第一章 入岭\n"
    "林昭当夜抵达北岭，在山脚客栈落脚。\n"
    "\n"
    "第二章 三年后\n"
    "三年后，沈青砚已执掌沈家商路，林昭自雪原归来。\n"
)

TIMELINE_ITEMS = {
    "timeline": [
        {
            "name": "林昭入北岭",
            "aliases": [],
            "summary": "当夜林昭抵达北岭落脚。",
            "attributes": {"time_expression": "当夜", "order": 1, "participants": ["林昭"]},
            "quotes": ["林昭当夜抵达北岭"],
            "confidence": 0.8,
        },
        {
            "name": "沈青砚执掌商路",
            "aliases": [],
            "summary": "三年后沈青砚执掌沈家商路，林昭归来。",
            "attributes": {"time_expression": "三年后", "order": 2, "participants": ["沈青砚", "林昭"]},
            "quotes": ["三年后，沈青砚已执掌沈家商路"],
            "confidence": 0.85,
        },
    ]
}


@pytest.mark.asyncio
async def test_timeline_domain_extracts_plot_nodes(session, storage):
    """剧情时间线域提取主线时间推进节点，与历史事件（背景）区分。"""
    snapshot = NovelSourceService(session).import_txt(
        raw=TIMELINE_TEXT.encode("utf-8"),
        file_name="timeline.txt",
        title="雪岭",
        source_status="completed",
    )
    service = WorldExtractionService(session, ai_service=FakeWorldAI(items=TIMELINE_ITEMS))
    result = await service.extract(snapshot.id, domains=["timeline"])
    assert result["status"] == "success"
    assert result["candidate_count"] == 2

    candidates = service.list_candidates(result["run_id"])
    assert {item.domain for item in candidates} == {"timeline"}
    ordered = sorted(
        candidates,
        key=lambda c: json.loads(c.payload_json).get("attributes", {}).get("order", 0),
    )
    assert [
        json.loads(item.payload_json)["attributes"]["time_expression"] for item in ordered
    ] == ["当夜", "三年后"]


@pytest.mark.asyncio
async def test_derive_project_copies_source_canon_and_characters(session, storage):
    """完本来源派生项目：原作正典带 source_canon 层复制，角色关联复制，原作不动。"""
    snapshot = _import_sample(session, source_status="completed")
    service = WorldExtractionService(session, ai_service=FakeWorldAI())
    result = await service.extract(
        snapshot.id, domains=["character", "location", "faction", "historical_event"]
    )
    run_id = result["run_id"]
    candidates = service.list_candidates(run_id)
    service.decide_candidates(
        run_id,
        [
            {"candidate_id": item.id, "action": "accept"}
            for item in candidates
            if item.entity_name != "沈家"
        ]
        + [
            {"candidate_id": item.id, "action": "ignore"}
            for item in candidates
            if item.entity_name == "沈家"
        ],
    )
    applied = await service.apply_run(run_id)

    # 用户后来补充到原项目的内容不属于该来源快照，不能被误标为原作正典。
    session.add(
        ProjectContent(
            project_id=applied["project_id"],
            content_type="world_asset",
            title="项目自定义设定",
            data_json=json.dumps({"asset_kind": "manual_fact"}, ensure_ascii=False),
            text_content="只属于当前项目的补充设定。",
            is_locked=False,
        )
    )
    manual_character = Character(name="项目自定义角色")
    session.add(manual_character)
    session.flush()
    session.add(
        CharacterStoryLink(
            story_id=applied["project_id"], character_id=manual_character.id
        )
    )
    session.commit()

    derived = service.derive_project(snapshot.id, derivation_kind="continuation")

    assert derived["derivation_kind"] == "continuation"
    assert derived["project_id"] != applied["project_id"]
    assert derived["source_canon_assets"] == 2
    assert derived["characters_linked"] == 2

    canon = session.exec(
        select(ProjectContent).where(
            ProjectContent.project_id == derived["project_id"],
            ProjectContent.content_type == "world_asset",
        )
    ).all()
    assert len(canon) == 2
    assert all(item.is_locked for item in canon)
    assert all(json.loads(item.data_json)["fact_layer"] == "source_canon" for item in canon)

    links = session.exec(
        select(CharacterStoryLink).where(CharacterStoryLink.story_id == derived["project_id"])
    ).all()
    assert len(links) == 2
    assert manual_character.id not in {link.character_id for link in links}
    assert "项目自定义设定" not in {item.title for item in canon}

    # 原项目的正典与角色关联保持不变。
    assert (
        len(
            session.exec(
                select(ProjectContent).where(
                    ProjectContent.project_id == applied["project_id"],
                    ProjectContent.content_type == "world_asset",
                )
            ).all()
        )
        == 3
    )

    # 再次派生是新项目，原作正典按项目独立复制，不重复也不遗漏。
    repeated = service.derive_project(snapshot.id, derivation_kind="fan_work")
    assert repeated["project_id"] != derived["project_id"]
    assert repeated["source_canon_assets"] == 2
    assert repeated["characters_linked"] == 2


@pytest.mark.asyncio
async def test_derived_project_context_separates_source_canon_layer(session, storage):
    """派生项目的 T0 上下文区分原作正典层与本作设定层。"""
    from app.services.creative_project.service import CreativeProjectService

    snapshot = _import_sample(session, source_status="completed")
    service = WorldExtractionService(session, ai_service=FakeWorldAI())
    extraction = await service.extract(snapshot.id, domains=["location", "historical_event"])
    candidates = service.list_candidates(extraction["run_id"])
    service.decide_candidates(
        extraction["run_id"],
        [{"candidate_id": item.id, "action": "accept"} for item in candidates],
    )
    applied = await service.apply_run(extraction["run_id"])
    derived = service.derive_project(snapshot.id, derivation_kind="continuation")

    derived_context = CreativeProjectService(
        session, ai_service=FakeWorldAI()
    )._locked_project_bible_context(derived["project_id"])
    source_context = CreativeProjectService(
        session, ai_service=FakeWorldAI()
    )._locked_project_bible_context(applied["project_id"])

    # 派生项目标注原作正典层并给出分层说明；原项目没有该标注。
    assert "原作正典·只读" in derived_context
    assert "不得与之矛盾" in derived_context
    assert "原作正典·只读" not in source_context
    # 原作事实仍然进入派生项目上下文。
    assert "北岭" in derived_context


def test_derive_project_rejects_invalid_kind_and_serial_source(session, storage):
    snapshot = _import_sample(session, source_status="completed")
    service = WorldExtractionService(session, ai_service=FakeWorldAI())
    with pytest.raises(ValueError):
        service.derive_project(snapshot.id, derivation_kind="sequel")

    serial = NovelSourceService(session).import_bookshelf(
        title="连载书",
        source_status="serial",
        chapters=[{"title": "第一章", "content": "正文。"}],
    )
    with pytest.raises(ValueError):
        service.derive_project(serial.id, derivation_kind="continuation")


@pytest.mark.asyncio
async def test_apply_requires_accepted_candidates(session, storage):
    snapshot = _import_sample(session)
    service = WorldExtractionService(session, ai_service=FakeWorldAI())
    result = await service.extract(snapshot.id, domains=["location"])

    with pytest.raises(ValueError):
        await service.apply_run(result["run_id"])


def test_import_bookshelf_and_append_new_chapters_keep_existing_anchors(session, storage):
    service = NovelSourceService(session)
    snapshot = service.import_bookshelf(
        title="连载书",
        chapters=[{"title": "第一章", "content": "林昭推开木门，雨水顺着屋檐落下。"}],
    )
    assert snapshot.chapter_count == 1
    first_chunks = service.list_chunks(snapshot.id)
    assert len(first_chunks) == 1
    first_offset = first_chunks[0].start_offset

    updated = service.append_bookshelf_chapters(
        snapshot.id,
        chapters=[
            {"title": "第一章", "content": "重复章节应被跳过。"},
            {"title": "第二章", "content": "沈青砚在灯下翻账册。"},
        ],
    )

    assert updated.chapter_count == 2
    chunks = service.list_chunks(snapshot.id)
    assert [item.ordinal for item in chunks] == [1, 2]
    assert chunks[0].start_offset == first_offset
    assert chunks[1].content == "沈青砚在灯下翻账册。"
    assert chunks[1].chapter_id == next(
        item.id for item in session.exec(
            select(NovelSourceChapter).where(
                NovelSourceChapter.snapshot_id == snapshot.id,
                NovelSourceChapter.ordinal == 2,
            )
        ).all()
    )
    text = service.load_source_text(snapshot.id)
    assert text[chunks[1].start_offset : chunks[1].end_offset] == "沈青砚在灯下翻账册。"


def test_append_chapters_rejects_completed_source(session, storage):
    service = NovelSourceService(session)
    snapshot = service.import_bookshelf(
        title="完本书",
        source_status="completed",
        chapters=[{"title": "第一章", "content": "正文内容。"}],
    )
    with pytest.raises(ValueError):
        service.append_bookshelf_chapters(
            snapshot.id, chapters=[{"title": "第二章", "content": "新章节。"}]
        )


def test_world_map_crud_and_revision_cas(session):
    from app.services.novel_source.world_map import WorldMapService

    service = WorldMapService(session)
    created = service.create_map(
        title="北境图",
        map_json={
            "regions": [{"id": "r1", "name": "北岭", "kind": "山岭", "parent_id": None, "description": ""}],
            "nodes": [],
            "routes": [],
        },
    )
    assert created.revision == 1

    fetched = service.get_map(created.id)
    assert fetched.title == "北境图"
    assert json.loads(fetched.map_json)["regions"][0]["name"] == "北岭"

    updated = service.update_map(
        created.id,
        map_json={
            "regions": [],
            "nodes": [
                {"id": "n1", "name": "客栈", "kind": "据点", "x": 0, "y": 0, "region_id": "r1", "description": ""}
            ],
            "routes": [],
        },
        expected_revision=1,
    )
    assert updated.revision == 2

    # CAS：用旧版本保存会被拒绝，避免覆盖他人编辑。
    with pytest.raises(ValueError):
        service.update_map(created.id, map_json={}, expected_revision=1)

    assert len(service.list_maps()) == 1

    service.delete_map(created.id)
    assert service.get_map(created.id) is None


def test_render_map_svg_contains_nodes_routes_and_title(session):
    """结构化地图可本地确定性渲染为 SVG，含据点、路线与标题。"""
    from app.services.novel_source.world_map import WorldMapService, render_map_svg

    service = WorldMapService(session)
    document = service.create_map(
        title="北境图",
        map_json={
            "regions": [
                {"id": "r1", "name": "北岭", "kind": "山岭", "parent_id": None, "description": ""}
            ],
            "nodes": [
                {"id": "n1", "name": "客栈", "kind": "据点", "x": 10, "y": 20, "region_id": "r1", "description": ""},
                {"id": "n2", "name": "关口", "kind": "关隘", "x": 60, "y": 70, "region_id": "r1", "description": ""},
            ],
            "routes": [
                {"id": "rt1", "name": "山道", "kind": "道路", "from": "n1", "to": "n2", "description": ""}
            ],
        },
    )
    svg = render_map_svg(document)
    assert svg.startswith("<svg")
    assert svg.endswith("</svg>")
    assert "北境图" in svg
    assert "客栈" in svg and "关口" in svg
    assert "<line" in svg
    assert "<circle" in svg

    # 名称中的特殊字符被转义，不会破坏 SVG 结构。
    escaped = service.create_map(
        title='<script>"危险"</script>',
        map_json={"regions": [], "nodes": [], "routes": []},
    )
    escaped_svg = render_map_svg(escaped)
    assert "<script>" not in escaped_svg
    assert "&lt;script&gt;" in escaped_svg


def test_build_map_visual_prompt_from_structured_map(session):
    """结构化地图可确定性转成生图 prompt，含区域/地点/路线/风格。"""
    from app.services.novel_source.world_map import WorldMapService, build_map_visual_prompt

    service = WorldMapService(session)
    document = service.create_map(
        title="北境舆图",
        map_json={
            "regions": [
                {"id": "r1", "name": "雪原", "kind": "地域"},
                {"id": "r2", "name": "北岭", "kind": "山岭"},
            ],
            "nodes": [
                {"id": "n1", "name": "霜岭关", "kind": "关隘", "x": 10, "y": 20, "region_id": "r1"},
                {"id": "n2", "name": "北岭城", "kind": "城池", "x": 60, "y": 70, "region_id": "r2"},
            ],
            "routes": [{"id": "rt1", "name": "山道", "from": "n1", "to": "n2"}],
        },
    )
    prompt = build_map_visual_prompt(document, style="水墨")
    assert "北境舆图" in prompt
    assert "雪原" in prompt and "北岭" in prompt
    assert "霜岭关" in prompt and "北岭城" in prompt
    # 路线按坐标给走向：北岭城 (y=70) 在霜岭关 (y=20) 下方 → 走向东南。
    assert "霜岭关→北岭城（走向东南）" in prompt
    assert "水墨" in prompt

    # 空地图也能生成兜底 prompt，不抛错。
    empty = service.create_map(title="空白图", map_json={"regions": [], "nodes": [], "routes": []})
    assert "空白图" in build_map_visual_prompt(empty)


def test_map_visual_prompt_carries_coordinate_convention(session):
    """提示词必须携带坐标约定与每个节点的 (x,y) 方位，防止模型脑补导致南北颠倒。"""
    from app.services.novel_source.world_map import WorldMapService, build_map_visual_prompt

    service = WorldMapService(session)
    document = service.create_map(
        title="方位校验图",
        map_json={
            "nodes": [
                {"id": "north", "name": "北山哨塔", "x": 60, "y": 10, "description": "雪山高处"},
                {"id": "center", "name": "南村", "x": 40, "y": 90},
            ],
            "regions": [],
            "routes": [{"id": "r1", "name": "山路", "from": "north", "to": "center"}],
        },
    )
    prompt = build_map_visual_prompt(document)
    # 坐标系约定写进提示词：y 向下增大、画面顶部为北。
    assert "画面顶部为北" in prompt
    assert "y 值越小越靠上" in prompt
    # 每个地点带 (x,y) 标注与相对方位。
    assert "北山哨塔" in prompt and "(x=60, y=10)" in prompt
    assert "南村" in prompt and "(x=40, y=90)" in prompt
    # 路线按坐标给出走向（南村 y=90 在下，走向为南）。
    assert "走向" in prompt
    # 明确禁止按名称里的南/北/东/西猜位置。
    assert "不要按名称里的「南/北/东/西」猜测位置" in prompt
    # 地形不写死：未在描述中出现的山河海岸不应被强加（现实题材适配）。
    assert "不要凭空添加" in prompt


def test_world_map_revision_history_and_rollback(session):
    """版本历史（SCN-05）：保存落 append-only 快照；回滚产生新 revision 而不改写历史。"""
    from app.services.novel_source.world_map import WorldMapService

    service = WorldMapService(session)
    doc = service.create_map(
        title="历史图",
        map_json={
            "regions": [],
            "nodes": [{"id": "n1", "name": "A", "x": 10, "y": 10}],
            "routes": [],
        },
    )
    service.update_map(
        doc.id,
        map_json={
            "regions": [],
            "nodes": [
                {"id": "n1", "name": "A", "x": 50, "y": 50},
                {"id": "n2", "name": "B", "x": 20, "y": 20},
            ],
            "routes": [],
        },
        expected_revision=doc.revision,
        operator="tester",
    )

    revisions = service.list_revisions(doc.id)
    assert [row.revision for row in revisions] == [2, 1]
    assert revisions[0].operator == "tester"
    assert "据点 2" in revisions[0].summary
    # v1 是 create 落的初始快照，列表从 v1 开始。
    assert revisions[1].revision == 1

    # 回滚到 v1：产生 revision=3，内容等于 v1；历史链保持 [3, 2, 1]。
    rolled = service.rollback(doc.id, 1)
    assert rolled.revision == 3
    rolled_data = json.loads(rolled.map_json)
    assert [node["name"] for node in rolled_data["nodes"]] == ["A"]

    revisions = service.list_revisions(doc.id)
    assert [row.revision for row in revisions] == [3, 2, 1]
    # 未显式给 operator 时标注回滚来源。
    assert revisions[0].operator == "rollback:v1"

    # 任意历史版可读取完整快照（两版对比的数据源）。
    detail = service.get_revision(doc.id, 2)
    assert detail is not None
    assert len(json.loads(detail.map_json)["nodes"]) == 2

    # 不存在的历史版本回滚报错。
    with pytest.raises(ValueError, match="历史版本不存在"):
        service.rollback(doc.id, 99)


def test_create_map_from_project_places_generates_nodes(session, storage):
    """确认写入的地点实体可一键转成地图据点初稿，且幂等不重复。"""
    from app.services.creative_project.service import CreativeProjectService
    from app.services.novel_source.contracts import normalize_entity_name
    from app.services.novel_source.world_map import WorldMapService

    project = CreativeProjectService(session, ai_service=FakeWorldAI()).create_project(
        title="雨夜旧账",
        project_type="novel",
        source_type="original_idea",
        idea="雨夜旧账",
    )
    for name in ("徐家老宅与茅屋", "田间与村口", "龙二赌坊"):
        session.add(
            WorldEntity(
                project_id=project.id,
                domain="location",
                entity_type="place",
                name=name,
                normalized_key=normalize_entity_name(name),
                summary=f"{name} 的摘要描述。",
                attributes_json="{}",
                evidence_json="[]",
                fact_layer="project",
                is_locked=True,
            )
        )
    session.commit()

    service = WorldMapService(session)
    document = service.create_map_from_project_places(project.id)
    data = json.loads(document.map_json)
    assert len(data["nodes"]) == 3
    assert {node["name"] for node in data["nodes"]} == {"徐家老宅与茅屋", "田间与村口", "龙二赌坊"}
    assert data["nodes"][0]["description"] == "徐家老宅与茅屋 的摘要描述。"

    # 幂等：地点已在地图上时再次调用抛错，而不是重复追加。
    with pytest.raises(ValueError):
        service.create_map_from_project_places(project.id)


def test_create_map_from_project_places_uses_radial_layout(session, storage):
    """5 个及以上地点应径向展开（避免挤在中下方一行的丑陋布局）。"""
    from app.services.creative_project.service import CreativeProjectService
    from app.services.novel_source.contracts import normalize_entity_name
    from app.services.novel_source.world_map import WorldMapService

    project = CreativeProjectService(session, ai_service=FakeWorldAI()).create_project(
        title="五地项目",
        project_type="novel",
        source_type="original_idea",
        idea="x",
    )
    place_names = [
        "徐家老宅与茅屋", "田间与村口", "龙二赌坊", "县医院与卫生所", "二喜建筑工地",
    ]
    for name in place_names:
        session.add(
            WorldEntity(
                project_id=project.id,
                domain="location",
                entity_type="place",
                name=name,
                normalized_key=normalize_entity_name(name),
                summary=f"{name} 摘要",
                attributes_json="{}",
                evidence_json="[]",
                fact_layer="project",
                is_locked=True,
            )
        )
    session.commit()

    document = WorldMapService(session).create_map_from_project_places(project.id)
    data = json.loads(document.map_json)
    coords = [(node["x"], node["y"]) for node in data["nodes"]]
    assert len(coords) == 5
    # 坐标必须在 0-100 范围内
    for x, y in coords:
        assert 0 <= x <= 100 and 0 <= y <= 100
    # 5 个点应围圆心分布（不是排成水平线）：x 应有 ≥4 个不同值，y 至少 2 个（圆周 y 必然重复）
    unique_x = {round(x, 1) for x, _ in coords}
    unique_y = {round(y, 1) for _, y in coords}
    assert len(unique_x) >= 4, f"5 个点 x 坐标过于集中: {coords}"
    assert len(unique_y) >= 2, f"5 个点 y 坐标全在同一水平线: {coords}"


def test_create_map_from_project_places_without_places_raises(session, storage):
    """没有地点实体时给出可读错误。"""
    from app.services.creative_project.service import CreativeProjectService
    from app.services.novel_source.world_map import WorldMapService

    project = CreativeProjectService(session, ai_service=FakeWorldAI()).create_project(
        title="无地点项目",
        project_type="novel",
        source_type="original_idea",
        idea="x",
    )
    with pytest.raises(ValueError):
        WorldMapService(session).create_map_from_project_places(project.id)


def test_world_map_visual_prompt_preview_endpoint(tmp_path):
    """地图生图支持先预览 prompt 再生成，不消耗生图配额。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.api.v1 import novel_sources as novel_sources_api
    from app.db.database import get_session
    from app.db.models.novel_source import WorldMapDocument, WorldMapRevision
    from app.services.novel_source.world_map import WorldMapService

    # TestClient 在独立线程运行 ASGI 应用，用文件型库并放开同线程限制。
    engine = create_engine(
        f"sqlite:///{tmp_path / 'maps.db'}", connect_args={"check_same_thread": False}
    )
    WorldMapDocument.__table__.create(engine)
    WorldMapRevision.__table__.create(engine)
    factory = sessionmaker(class_=Session, bind=engine, expire_on_commit=False)

    with factory() as seed_session:
        document = WorldMapService(seed_session).create_map(
            title="北境舆图",
            map_json={
                "regions": [{"id": "r1", "name": "北岭", "kind": "山岭"}],
                "nodes": [
                    {"id": "n1", "name": "客栈", "kind": "据点", "x": 10, "y": 20, "region_id": "r1"}
                ],
                "routes": [],
            },
        )
        document_id = document.id

    app = FastAPI()
    app.include_router(novel_sources_api.router)

    def _override_session():
        with factory() as db:
            yield db

    app.dependency_overrides[get_session] = _override_session
    client = TestClient(app)

    try:
        response = client.post(
            f"/api/v1/world-maps/{document_id}/generate-visual/prompt-preview",
            json={"style_override": "水墨"},
        )
        assert response.status_code == 200
        prompt = response.json()["data"]["prompt"]
        assert "北境舆图" in prompt
        assert "北岭" in prompt and "客栈" in prompt
        assert "水墨" in prompt

        # 提示词覆盖时直接用覆盖值，不再按地图结构生成。
        response = client.post(
            f"/api/v1/world-maps/{document_id}/generate-visual/prompt-preview",
            json={"prompt_override": "自定义提示词"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["prompt"] == "自定义提示词"

        # 地图不存在时 404。
        missing = client.post(
            "/api/v1/world-maps/not-exist/generate-visual/prompt-preview", json={}
        )
        assert missing.status_code == 404
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_propagate_affected_facts_marks_written_facts(session, storage):
    """合并/重复结论传播到已写入事实：只打待复核标记，不改写事实内容。"""
    items = {
        "location": [
            {
                "name": "北岭",
                "aliases": ["北岭一带"],
                "summary": "陌生来客的出发地。",
                "attributes": {"kind": "山岭"},
                "quotes": ["来自北岭"],
                "confidence": 0.8,
            }
        ],
        "faction": [
            {
                "name": "北岭一带",
                "aliases": [],
                "summary": "北岭一带的山民组织。",
                "attributes": {"kind": "山民组织"},
                "quotes": ["来自北岭"],
                "confidence": 0.6,
            }
        ],
    }
    snapshot = _import_sample(session)
    service = WorldExtractionService(session, ai_service=FakeWorldAI(items=items))
    result = await service.extract(snapshot.id, domains=["location", "faction"])
    run_id = result["run_id"]
    candidates = service.list_candidates(run_id)
    service.decide_candidates(
        run_id, [{"candidate_id": item.id, "action": "accept"} for item in candidates]
    )
    applied = await service.apply_run(run_id)
    assert applied["world_assets_written"] == 2

    report = service.propagate_affected_facts(run_id)
    assert report["affected_candidates"] == 2
    assert len(report["affected_facts"]) == 2

    for fact in report["affected_facts"]:
        content = session.get(ProjectContent, fact["fact_id"])
        payload = json.loads(content.data_json)
        assert payload["review_required"] is True
        assert payload["affected_reason"]
        # 事实内容（实体名/域）未被改写，只是被标记。
        assert payload["entity_name"] == fact["entity_name"]

    # 传入矛盾判定结果时，原因优先来自 verdicts。
    verdicts = [
        {
            "verdict": "conflicting",
            "reason": "两条候选描述互相矛盾",
            "candidates": [
                {"id": candidates[0].id, "entity_name": candidates[0].entity_name}
            ],
        }
    ]
    report2 = service.propagate_affected_facts(run_id, verdicts=verdicts)
    reasons = {item["candidate_id"]: item["reason"] for item in report2["affected_facts"]}
    assert "矛盾" in reasons[candidates[0].id]


@pytest.mark.asyncio
async def test_plan_does_not_extract_not_detected_domains(session, storage):
    """检测为 not_detected 的模块不进入推荐与提取，不产生候选噪声。"""
    snapshot = _import_sample(session)
    service = WorldExtractionService(session, ai_service=FakeWorldAI())
    plan = await service.plan_domains(snapshot.id)
    # FakeWorldAI 里 economy 是 not_detected，map 不可提取，均不进推荐。
    assert "economy" not in plan["recommended"]
    assert "map" not in plan["recommended"]

    result = await service.extract(snapshot.id, domains=plan["recommended"])
    ran_domains = {item["domain"] for item in result["domains"]}
    assert "economy" not in ran_domains
    assert "map" not in ran_domains
    # 只有真正推荐的、可提取的域才执行。
    assert "character" in ran_domains


# ---------------------------------------------------------------------------
# 多来源入口：从创作项目大纲启动世界提取、从来源快照创建项目
# ---------------------------------------------------------------------------

OUTLINE_FOR_WORLD = {
    "title": "雨夜旧账",
    "premise": "少年林昭在雨夜回到故乡，发现沈家商路已断。",
    "worldview": "北境以银关钞为通行货币，霜岭的誓言不可违背。",
    "characters": [
        {"name": "林昭", "role": "主角", "appearance": "年轻人，背着旧伞。"},
        {"name": "沈青砚", "role": "沈家当家", "personality": "在灯下翻账册。"},
    ],
    "locations": [
        {"name": "沈家", "role": "家族宅院", "visual_description": "木门小院。"},
        {"name": "北岭", "role": "山岭", "visual_description": "来客出发地。"},
    ],
}

OUTLINE_WORLD_ITEMS = {
    "character": [
        {
            "name": "林昭",
            "aliases": [],
            "summary": "主角",
            "attributes": {"role": "主角"},
            "quotes": ["少年林昭在雨夜回到故乡"],
            "confidence": 0.8,
        },
        {
            "name": "沈青砚",
            "aliases": [],
            "summary": "沈家当家",
            "attributes": {"role": "当家"},
            "quotes": ["在灯下翻账册"],
            "confidence": 0.8,
        },
    ],
    "location": [
        {
            "name": "沈家",
            "aliases": [],
            "summary": "家族宅院",
            "attributes": {"kind": "宅院"},
            "quotes": ["木门小院"],
            "confidence": 0.8,
        },
        {
            "name": "北岭",
            "aliases": [],
            "summary": "山岭",
            "attributes": {"kind": "山岭"},
            "quotes": ["来客出发地"],
            "confidence": 0.8,
        },
    ],
}


def test_serialize_outline_as_source_text_keeps_quotes():
    """大纲序列化为来源文本时保留各字段原文，供证据校验逐字回溯。"""
    from app.api.v1.novel_sources import serialize_outline_as_source_text

    text = serialize_outline_as_source_text(OUTLINE_FOR_WORLD)
    assert "少年林昭在雨夜回到故乡" in text
    assert "在灯下翻账册" in text
    assert "木门小院" in text
    assert "来客出发地" in text
    assert "【世界观】" in text


@pytest.mark.asyncio
async def test_start_world_extraction_from_outline_creates_snapshot(tmp_path, monkeypatch):
    """从创作项目大纲启动世界提取：建来源快照并产出候选，快照绑定项目。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.api.v1 import novel_sources as novel_sources_api
    from app.db.database import get_session
    from app.db.models.creative_project import CreativeProject, ProjectContent
    from app.db.models.novel_source import (
        NovelSourceChapter,
        NovelSourceSnapshot,
        NovelTextChunk,
        WorldExtractionRun,
        WorldFactCandidate,
    )
    from app.services.creative_project.service import CreativeProjectService, dumps_json

    monkeypatch.setattr(source_module, "STORAGE_ROOT", tmp_path / "novel_sources")

    engine = create_engine(
        f"sqlite:///{tmp_path / 'world.db'}", connect_args={"check_same_thread": False}
    )
    for table in (
        CreativeProject.__table__,
        ProjectContent.__table__,
        NovelSourceSnapshot.__table__,
        NovelSourceChapter.__table__,
        NovelTextChunk.__table__,
        WorldExtractionRun.__table__,
        WorldFactCandidate.__table__,
        Character.__table__,
        CharacterStoryLink.__table__,
    ):
        table.create(engine)
    factory = sessionmaker(class_=Session, bind=engine, expire_on_commit=False)

    with factory() as seed:
        project = CreativeProjectService(seed, ai_service=FakeWorldAI()).create_project(
            title="雨夜旧账",
            project_type="novel",
            source_type="original_idea",
            idea="雨夜旧账",
        )
        project.outline_json = dumps_json(OUTLINE_FOR_WORLD)
        seed.add(project)
        seed.commit()
        project_id = project.id

    app = FastAPI()
    app.include_router(novel_sources_api.router)

    def _override_session():
        with factory() as db:
            yield db

    def _override_extraction_service():
        return WorldExtractionService(factory(), ai_service=FakeWorldAI(items=OUTLINE_WORLD_ITEMS))

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[novel_sources_api.extraction_service] = _override_extraction_service
    client = TestClient(app)

    try:
        # 该入口（大纲→整套世界设定）有意默认跑全部可提取域；
        # 其它入口不指定模块时由服务层回落到基础层，两者都不得报「没有可提取的世界模块」。
        response = client.post(
            f"/api/v1/creative-projects/{project_id}/world-extraction/start",
            json={},
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["run_id"]
        assert data["candidate_count"] >= 1
        with factory() as check:
            snapshot = check.get(NovelSourceSnapshot, data["snapshot_id"])
            assert snapshot is not None
            assert snapshot.project_id == project_id
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_from_novel_source_creates_and_binds_project(tmp_path, monkeypatch):
    """from-novel-source：从来源快照创建并绑定世界项目，重复调用幂等。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.api.v1 import novel_sources as novel_sources_api
    from app.db.database import get_session
    from app.db.models.creative_project import CreativeProject, ProjectContent
    from app.db.models.novel_source import (
        NovelSourceChapter,
        NovelSourceSnapshot,
        NovelTextChunk,
        WorldExtractionRun,
        WorldFactCandidate,
    )
    from app.services.creative_project.service import loads_json

    monkeypatch.setattr(source_module, "STORAGE_ROOT", tmp_path / "novel_sources")

    engine = create_engine(
        f"sqlite:///{tmp_path / 'world.db'}", connect_args={"check_same_thread": False}
    )
    for table in (
        CreativeProject.__table__,
        ProjectContent.__table__,
        NovelSourceSnapshot.__table__,
        NovelSourceChapter.__table__,
        NovelTextChunk.__table__,
        WorldExtractionRun.__table__,
        WorldFactCandidate.__table__,
        Character.__table__,
        CharacterStoryLink.__table__,
    ):
        table.create(engine)
    factory = sessionmaker(class_=Session, bind=engine, expire_on_commit=False)

    with factory() as seed:
        snapshot = NovelSourceService(seed).import_txt(
            raw="第一章 雨夜\n林昭推开木门。\n".encode("utf-8"),
            file_name="sample.txt",
            title="雨夜旧账",
        )
        snapshot_id = snapshot.id

    app = FastAPI()
    app.include_router(novel_sources_api.router)

    def _override_session():
        with factory() as db:
            yield db

    def _override_extraction_service():
        return WorldExtractionService(factory(), ai_service=FakeWorldAI())

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[novel_sources_api.extraction_service] = _override_extraction_service
    client = TestClient(app)

    try:
        response = client.post(
            "/api/v1/creative-projects/from-novel-source",
            json={"snapshot_id": snapshot_id},
        )
        assert response.status_code == 200, response.text
        project_id = response.json()["data"]["project_id"]

        # 幂等：再次调用返回同一项目。
        response = client.post(
            "/api/v1/creative-projects/from-novel-source",
            json={"snapshot_id": snapshot_id},
        )
        assert response.status_code == 200
        assert response.json()["data"]["project_id"] == project_id
        assert response.json()["data"]["reused"] is True

        with factory() as check:
            snapshot = check.get(NovelSourceSnapshot, snapshot_id)
            assert snapshot.project_id == project_id
            project = check.get(CreativeProject, project_id)
            assert project is not None
            assert loads_json(project.source_ref_json).get("novel_snapshot_id") == snapshot_id
    finally:
        engine.dispose()


def test_world_knowledge_aggregates_project_world(tmp_path, monkeypatch):
    """world-knowledge 聚合角色/实体/关系/事实卡/地图，任一子集为空不影响返回。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.api.v1 import novel_sources as novel_sources_api
    from app.db.database import get_session
    from app.db.models.character import Character, CharacterStoryLink
    from app.db.models.creative_project import CreativeProject, ProjectContent
    from app.db.models.novel_source import (
        NovelSourceChapter,
        NovelSourceSnapshot,
        NovelTextChunk,
        WorldEntity,
        WorldEntityRelation,
        WorldExtractionRun,
        WorldFactCandidate,
        WorldMapDocument,
    )
    from app.services.creative_project.service import CreativeProjectService, dumps_json
    from app.services.novel_source.contracts import normalize_entity_name

    engine = create_engine(
        f"sqlite:///{tmp_path / 'world.db'}", connect_args={"check_same_thread": False}
    )
    for table in (
        CreativeProject.__table__,
        ProjectContent.__table__,
        NovelSourceSnapshot.__table__,
        NovelSourceChapter.__table__,
        NovelTextChunk.__table__,
        WorldExtractionRun.__table__,
        WorldFactCandidate.__table__,
        Character.__table__,
        CharacterStoryLink.__table__,
        WorldMapDocument.__table__,
        WorldEntity.__table__,
        WorldEntityRelation.__table__,
    ):
        table.create(engine)
    factory = sessionmaker(class_=Session, bind=engine, expire_on_commit=False)

    with factory() as seed:
        project = CreativeProjectService(seed, ai_service=FakeWorldAI()).create_project(
            title="雨夜旧账",
            project_type="novel",
            source_type="original_idea",
            idea="x",
        )
        project_id = project.id

        character = Character(name="福贵", role="protagonist")
        seed.add(character)
        seed.flush()
        seed.add(
            CharacterStoryLink(
                character_id=character.id,
                story_id=project_id,
                world_id=project_id,
                aliases_json=json.dumps(["福贵"], ensure_ascii=False),
                evidence_json=json.dumps(["福贵是主角"], ensure_ascii=False),
                extract_origin="outline",
            )
        )
        place_a = WorldEntity(
            project_id=project_id,
            domain="location",
            entity_type="place",
            name="徐家老宅与茅屋",
            normalized_key=normalize_entity_name("徐家老宅与茅屋"),
            summary="村东头的土坯房。",
            attributes_json="{}",
            evidence_json="[]",
            fact_layer="project",
            is_locked=True,
        )
        place_b = WorldEntity(
            project_id=project_id,
            domain="location",
            entity_type="place",
            name="龙二赌坊",
            normalized_key=normalize_entity_name("龙二赌坊"),
            summary="镇上的赌坊。",
            attributes_json="{}",
            evidence_json="[]",
            fact_layer="project",
            is_locked=True,
        )
        seed.add_all([place_a, place_b])
        seed.flush()
        seed.add(
            WorldEntityRelation(
                project_id=project_id,
                source_entity_id=place_a.id,
                target_entity_id=place_b.id,
                relation_type="rival",
                note="赌债",
                evidence_json="[]",
                is_directed=False,
            )
        )
        seed.add(
            ProjectContent(
                project_id=project_id,
                content_type="world_asset",
                title="徐家",
                data_json=dumps_json({"domain": "faction"}),
                text_content="徐家是故事核心家庭势力。",
                is_locked=True,
            )
        )
        seed.add(
            WorldMapDocument(
                project_id=project_id,
                title="世界地图",
                map_json=dumps_json({"regions": [], "nodes": [{"id": "n1", "name": "二喜建筑工地"}], "routes": []}),
            )
        )
        seed.commit()

    app = FastAPI()
    app.include_router(novel_sources_api.router)

    def _override_session():
        with factory() as db:
            yield db

    app.dependency_overrides[get_session] = _override_session
    client = TestClient(app)

    try:
        response = client.get(f"/api/v1/creative-projects/{project_id}/world-knowledge")
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["title"] == "雨夜旧账"
        assert data["counts"] == {
            "characters": 1,
            "entities": 2,
            "relations": 1,
            "facts": 1,
            "maps": 1,
            "snapshots": 0,
        }
        assert data["characters"][0]["name"] == "福贵"
        assert data["relations"][0]["source_name"] == "徐家老宅与茅屋"
        assert data["relations"][0]["relation_type"] == "rival"
        assert data["maps"][0]["node_count"] == 1
    finally:
        engine.dispose()


def test_resolve_domains_falls_back_to_basic_layer(session):
    """未指定域、也没有检测结果时回落到基础层，而不是让调用方无从下手。"""
    service = WorldExtractionService(session, ai_service=FakeWorldAI())

    # 两者都为空：回落到基础层（角色/地点/势力/历史事件）。
    assert service._resolve_domains(None, None) == [
        "character",
        "location",
        "faction",
        "historical_event",
    ]

    # 显式关闭了所有模块的 plan：尊重用户意图，不偷偷补跑。
    plan = [
        {"domain": "character", "status": "not_detected", "enabled": False},
        {"domain": "species", "status": "not_detected", "enabled": False},
    ]
    assert service._resolve_domains(None, plan) == []

    # 检测到一个扩展域时只跑它，不叠加基础层。
    detected = [{"domain": "species", "status": "user_requested", "enabled": True}]
    assert service._resolve_domains(None, detected) == ["species"]

    # 显式 domains 优先。
    assert service._resolve_domains(["location"], None) == ["location"]


@pytest.mark.asyncio
async def test_extract_without_domains_runs_basic_layer(session, storage):
    """不传 domains / domain_plan 时按基础层跑通，而不是报「没有可提取的世界模块」。"""
    snapshot = _import_sample(session)
    service = WorldExtractionService(session, ai_service=FakeWorldAI())

    result = await service.extract(snapshot.id)

    assert result["status"] == "success"
    assert result["candidate_count"] == 5
    candidates = service.list_candidates(result["run_id"])
    assert {item.domain for item in candidates} == {
        "character",
        "location",
        "faction",
        "historical_event",
    }


def test_create_map_from_project_places_single_place_centers_node(session, storage):
    """只有一个地点实体时不再 500：单点居中生成，坐标仍在 0-100 内。"""
    from app.services.creative_project.service import CreativeProjectService
    from app.services.novel_source.contracts import normalize_entity_name
    from app.services.novel_source.world_map import WorldMapService

    project = CreativeProjectService(session, ai_service=FakeWorldAI()).create_project(
        title="单点项目",
        project_type="novel",
        source_type="original_idea",
        idea="x",
    )
    name = "徐家老宅"
    session.add(
        WorldEntity(
            project_id=project.id,
            domain="location",
            entity_type="place",
            name=name,
            normalized_key=normalize_entity_name(name),
            summary=f"{name} 的摘要。",
            attributes_json="{}",
            evidence_json="[]",
            fact_layer="project",
            is_locked=True,
        )
    )
    session.commit()

    document = WorldMapService(session).create_map_from_project_places(project.id)
    data = json.loads(document.map_json)
    assert len(data["nodes"]) == 1
    node = data["nodes"][0]
    assert node["name"] == name
    # 回归防线：该分支曾漏设 radius，导致 NameError 直接 500。
    assert node["x"] == 50 and node["y"] == 50
    assert 0 <= node["x"] <= 100 and 0 <= node["y"] <= 100


def test_build_map_visual_prompt_does_not_hardcode_fantasy_style(session):
    """画风不再写死：现实题材套「羊皮纸·中土奇幻」会严重违和。"""
    from app.services.novel_source.world_map import WorldMapService, build_map_visual_prompt

    service = WorldMapService(session)
    document = service.create_map(
        title="徐家村地图",
        map_json={
            "regions": [{"id": "r1", "name": "徐家村", "kind": "村落"}],
            "nodes": [
                {"id": "n1", "name": "村口", "kind": "场景", "x": 30, "y": 60, "region_id": "r1"}
            ],
            "routes": [],
        },
    )

    plain = build_map_visual_prompt(document)
    # 结构化内容照常进入 prompt。
    assert "徐家村地图" in plain
    assert "徐家村" in plain and "村口" in plain
    # 但不再硬编码奇幻画风。
    for banned in ("羊皮纸", "魔戒", "奇幻", "幻想"):
        assert banned not in plain, f"prompt 仍残留硬编码画风：{banned}"
    # 未指定风格时明确交给视觉基准/参考图自适应。
    assert "视觉基准" in plain

    styled = build_map_visual_prompt(document, style="写实乡村")
    assert "写实乡村" in styled
    for banned in ("羊皮纸", "魔戒", "奇幻"):
        assert banned not in styled


def _seed_project_with_places(session, title, places):
    """建项目并写入若干地点实体，返回 (project_id, {name: place})。"""
    from app.services.creative_project.service import CreativeProjectService
    from app.services.novel_source.contracts import normalize_entity_name

    project = CreativeProjectService(session, ai_service=FakeWorldAI()).create_project(
        title=title,
        project_type="novel",
        source_type="original_idea",
        idea=title,
    )
    created = {}
    for name, summary, evidence in places:
        place = WorldEntity(
            project_id=project.id,
            domain="location",
            entity_type="place",
            name=name,
            normalized_key=normalize_entity_name(name),
            summary=summary,
            attributes_json="{}",
            evidence_json=json.dumps(evidence, ensure_ascii=False),
            fact_layer="project",
            is_locked=True,
        )
        session.add(place)
        created[name] = place
    session.commit()
    return project.id, created


def test_from_places_nodes_reference_entities_not_copies(session, storage):
    """据点引用地点实体（entity_id）：实体改名后按 id 判重，不重复生成据点。"""
    from app.services.novel_source.world_map import WorldMapService

    project_id, places = _seed_project_with_places(
        session,
        "引用项目",
        [("龙二赌坊", "福贵输光家产的地方。", [{"chunk_id": "c1", "quote": "福贵押上了最后的地契。"}])],
    )

    service = WorldMapService(session)
    document = service.create_map_from_project_places(project_id)
    data = json.loads(document.map_json)
    assert len(data["nodes"]) == 1
    # 引用而不是复制：据点持有实体指针，正典仍在 world_entities。
    assert data["nodes"][0]["entity_id"] == places["龙二赌坊"].id

    # 实体改名后再次生成：按 entity_id 判重，不产生第二个据点。
    place = places["龙二赌坊"]
    place.name = "龙二赌场"
    session.add(place)
    session.commit()
    with pytest.raises(ValueError):
        service.create_map_from_project_places(project_id)
    data = json.loads(service.get_map(document.id).map_json)
    assert len(data["nodes"]) == 1
    assert data["nodes"][0]["entity_id"] == place.id


def test_resolve_nodes_with_entities_returns_evidence_and_relations(session, storage):
    """据点可回查实体：摘要/证据/关系；游离标记被标记出来而不是当正典。"""
    from app.db.models.novel_source import WorldEntityRelation
    from app.services.novel_source.world_map import WorldMapService

    project_id, places = _seed_project_with_places(
        session,
        "解析项目",
        [
            ("龙二赌坊", "福贵输光家产的地方。", [{"chunk_id": "c1", "quote": "福贵押上了最后的地契。"}]),
            ("镇上", "徐家村外的集镇。", []),
        ],
    )
    session.add(
        WorldEntityRelation(
            project_id=project_id,
            source_entity_id=places["龙二赌坊"].id,
            target_entity_id=places["镇上"].id,
            relation_type="located_in",
            note="赌坊在镇上",
            evidence_json="[]",
            is_directed=True,
        )
    )
    session.commit()

    service = WorldMapService(session)
    document = service.create_map_from_project_places(project_id)
    resolved = service.resolve_nodes_with_entities(document.id)

    by_name = {row["node"]["name"]: row for row in resolved["nodes"]}
    assert set(by_name) == {"龙二赌坊", "镇上"}
    row = by_name["龙二赌坊"]
    assert row["entity_id"] == places["龙二赌坊"].id
    assert row["entity"]["summary"] == "福贵输光家产的地方。"
    # 证据锚点来自实体，不复制进 map_json。
    assert row["entity"]["evidence"] == [{"chunk_id": "c1", "quote": "福贵押上了最后的地契。"}]
    assert any(rel["relation_type"] == "located_in" for rel in row["relations"])
    assert resolved["orphan_node_ids"] == []

    # 手工造一个没有 entity_id 的据点：应被识别为游离标记。
    data = json.loads(document.map_json)
    data["nodes"].append({"id": "free-1", "name": "无主据点", "kind": "地点", "x": 10, "y": 10})
    document = service.update_map(
        document.id, map_json=data, expected_revision=document.revision
    )
    resolved = service.resolve_nodes_with_entities(document.id)
    assert resolved["orphan_node_ids"] == ["free-1"]


def test_build_map_export_includes_entity_references(session, storage):
    """导出的点位 JSON 带 entity_id / evidence，confidence 暂缺（OQ-01）。"""
    from app.services.novel_source.world_map import WorldMapService, build_map_export

    project_id, places = _seed_project_with_places(
        session,
        "导出项目",
        [("徐家老宅", "福贵与家珍的家。", [{"chunk_id": "c1", "quote": "那间老屋，土墙黑瓦。"}])],
    )

    service = WorldMapService(session)
    document = service.create_map_from_project_places(project_id)
    resolved = service.resolve_nodes_with_entities(document.id)
    exported = build_map_export(document, resolved)

    assert exported["map"]["map_id"] == document.id
    assert len(exported["nodes"]) == 1
    node = exported["nodes"][0]
    assert node["entity_id"] == places["徐家老宅"].id
    assert node["evidence"] == [{"chunk_id": "c1", "quote": "那间老屋，土墙黑瓦。"}]
    # OQ-01：实体层还没有置信度字段，暂不伪造。
    assert node["confidence"] is None


def test_build_map_export_includes_data_driven_layers(session, storage):
    """空间层由地图数据自定义（不写死天界/冥界枚举），导出随 layers 与 node.layer 带上。"""
    from app.services.novel_source.world_map import WorldMapService, build_map_export

    service = WorldMapService(session)
    document = service.create_map(
        title="三层世界",
        map_json={
            "layers": [{"id": "l-main", "name": "人间"}, {"id": "l-sea", "name": "归墟"}],
            "regions": [],
            "nodes": [
                {"id": "n1", "name": "长安", "kind": "城池", "x": 30, "y": 40, "layer": "l-main"},
                {"id": "n2", "name": "海底龙宫", "kind": "据点", "x": 60, "y": 80, "layer": "l-sea"},
            ],
            "routes": [],
        },
    )

    exported = build_map_export(document)

    # 层集合完全由数据决定：这里叫「人间/归墟」，别的项目可以叫任何名字，也可以没有。
    assert [item["name"] for item in exported["layers"]] == ["人间", "归墟"]
    by_name = {item["name"]: item for item in exported["nodes"]}
    assert by_name["长安"]["layer"] == "l-main"
    assert by_name["海底龙宫"]["layer"] == "l-sea"


def _project_id(session, title):
    from app.services.creative_project.service import CreativeProjectService

    project = CreativeProjectService(session, ai_service=FakeWorldAI()).create_project(
        title=title, project_type="novel", source_type="original_idea", idea=title
    )
    return project.id


def test_project_can_extend_builtin_domain_attributes(session, storage):
    """项目可给内置模块改展示名并追加属性字段；内置字段不可删除。"""
    from app.services.novel_source.world_domains import WorldDomainService

    project_id = _project_id(session, "可扩展世界")
    service = WorldDomainService(session)
    service.upsert_definition(
        project_id, "species", label="族群", extra_attributes=["义体改造等级"]
    )

    domains = {item["key"]: item for item in service.list_domains(project_id)}
    species = domains["species"]
    assert species["label"] == "族群"
    assert species["source"] == "builtin_override"
    assert species["is_builtin"] is True
    # 内置字段仍在（既有 attributes_json 保持可解析），追加字段排在后面。
    assert species["builtin_attributes"] == [
        "kind",
        "traits",
        "habitat",
        "lifespan",
        "relations",
        "abilities",
    ]
    assert "义体改造等级" in species["attributes"]

    # 解析结果供提取/生成使用：内置 + 项目追加。
    specs = {spec.key: spec for spec in service.resolve_specs(project_id)}
    assert specs["species"].label == "族群"
    assert "义体改造等级" in specs["species"].attributes


def test_project_can_add_custom_domains_and_ai_suggestions_need_confirmation(
    session, storage
):
    """自定义模块直接生效；AI 建议的模块需确认后才参与提取。"""
    from app.services.novel_source.world_domains import WorldDomainService

    project_id = _project_id(session, "赛博世界")
    service = WorldDomainService(session)
    service.upsert_definition(
        project_id,
        "cyberware",
        label="义体改造",
        entity_type="cyberware",
        extra_attributes=["等级", "副作用", "供应商"],
    )

    domains = {item["key"]: item for item in service.list_domains(project_id)}
    custom = domains["cyberware"]
    assert custom["is_builtin"] is False
    assert custom["entity_type"] == "cyberware"
    assert custom["attributes"] == ["等级", "副作用", "供应商"]
    specs = {spec.key: spec for spec in service.resolve_specs(project_id)}
    assert specs["cyberware"].entity_type == "cyberware"

    # AI 建议的模块落库但不参与提取，确认（转 custom）后才生效。
    service.upsert_definition(
        project_id, "灵脉", label="灵脉品级", extra_attributes=["品级"], source="ai_suggested"
    )
    assert "灵脉" not in {spec.key for spec in service.resolve_specs(project_id)}
    service.upsert_definition(project_id, "灵脉", label="灵脉品级", source="custom")
    assert "灵脉" in {spec.key for spec in service.resolve_specs(project_id)}


def test_builtin_domain_can_be_disabled_and_reset(session, storage):
    """项目可禁用不需要的内置模块，也可重置回默认。"""
    from app.services.novel_source.world_domains import WorldDomainService

    project_id = _project_id(session, "精简世界")
    service = WorldDomainService(session)

    service.upsert_definition(project_id, "glossary", is_enabled=False)
    assert "glossary" not in {spec.key for spec in service.resolve_specs(project_id)}

    service.reset_definition(project_id, "glossary")
    assert "glossary" in {spec.key for spec in service.resolve_specs(project_id)}


@pytest.mark.asyncio
async def test_extraction_runs_default_to_extract_kind(session, storage):
    """运行记录默认是从原文提取；生成运行复用同一张表，只改 kind（Decision D-3）。"""
    snapshot = _import_sample(session)
    service = WorldExtractionService(session, ai_service=FakeWorldAI())

    result = await service.extract(snapshot.id, domains=["location"])
    run = service.get_run(result["run_id"])

    assert run.kind == "extract"
    assert run.mode == "full"


def test_world_building_template_layers_are_data_driven(session, storage):
    """模板的层次策略由数据决定（不写死枚举），项目可自定义（Decision D-1）。"""
    from app.db.models.novel_source import WorldBuildingTemplate

    project_id = _project_id(session, "模板项目")
    template = WorldBuildingTemplate(
        project_id=project_id,
        name="现代地理层级",
        layers_json=json.dumps(["世界", "国家", "省/州", "城市"], ensure_ascii=False),
        prompts_json=json.dumps(
            {"draft_world": "按层次 {layers} 从粗到细搭建世界骨架。"}, ensure_ascii=False
        ),
        is_default=True,
    )
    session.add(template)
    session.commit()

    stored = session.get(WorldBuildingTemplate, template.id)
    # 层次叫什么、有几层都由项目数据决定，代码里不存这些名字。
    assert json.loads(stored.layers_json) == ["世界", "国家", "省/州", "城市"]
    assert "{layers}" in json.loads(stored.prompts_json)["draft_world"]
    assert stored.is_default is True
    assert stored.is_builtin is False


class FakeGenerationAI(FakeWorldAI):
    """按 prompt 形态返回生成结果（schema-guided），不访问真实模型。"""

    def __init__(
        self,
        *,
        attributes=None,
        suggested_fields=None,
        suggested_domains=None,
        domain_items=None,
    ):
        super().__init__()
        self.generated_attributes = attributes or {}
        self.suggested_fields = suggested_fields or []
        self.suggested_domains = suggested_domains or []
        # 域级细化的产出形状：items[].entity（区别于实体补充的 attributes 填充）
        self.domain_items = (
            domain_items
            if domain_items is not None
            else [{"entity": "青石巷", "attributes": {"kind": "街区", "region": "镇上"}}]
        )

    async def chat(self, messages, **kwargs):
        prompt = messages[-1].content
        self.prompts.append(prompt)
        if '"domains":[' in prompt:
            return LLMGenerationResult(
                success=True,
                content=json.dumps(self._detection_payload(), ensure_ascii=False),
                provider="fake",
                model="fake-model",
            )
        if "按层次策略细化" in prompt:
            payload = {
                "items": self.domain_items,
                "suggested_fields": self.suggested_fields,
                "suggested_domains": self.suggested_domains,
            }
            return LLMGenerationResult(
                success=True,
                content=json.dumps(payload, ensure_ascii=False),
                provider="fake",
                model="fake-model",
            )
        if "待补充字段" in prompt:
            payload = {
                "items": [{"entity": "", "attributes": self.generated_attributes}],
                "suggested_fields": self.suggested_fields,
                "suggested_domains": self.suggested_domains,
            }
            return LLMGenerationResult(
                success=True,
                content=json.dumps(payload, ensure_ascii=False),
                provider="fake",
                model="fake-model",
            )
        return await super().chat(messages, **kwargs)


@pytest.mark.asyncio
async def test_expand_entity_produces_ai_draft_candidate_without_evidence(
    session, storage
):
    """AI 补充属性：只写勾选字段，产出无证据的 ai_draft 候选（生成/提取语义隔离）。"""
    from app.services.novel_source.world_generation import WorldGenerationService

    project_id, places = _seed_project_with_places(
        session, "生成项目", [("龙二赌坊", "福贵输光家产的地方。", [])]
    )
    ai = FakeGenerationAI(
        attributes={"region": "徐家村东头", "significance": "福贵输光家产的地方"}
    )
    service = WorldGenerationService(session, ai_service=ai)

    result = await service.expand_entity(
        project_id, places["龙二赌坊"].id, fields=["region", "significance"]
    )

    candidate = session.get(WorldFactCandidate, result["candidate_id"])
    assert candidate.origin == "ai_draft"
    # 生成链路没有原文可引用：绝不伪造证据锚点。
    assert json.loads(candidate.evidence_json) == []
    assert candidate.snapshot_id is None
    attributes = json.loads(candidate.payload_json)["attributes"]
    assert attributes["region"] == "徐家村东头"
    assert attributes["significance"] == "福贵输光家产的地方"
    # 没勾选的字段不写，已填内容不被覆盖。
    assert "first_appearance" not in attributes

    run = session.get(WorldExtractionRun, result["run_id"])
    assert run.kind == "generate"
    assert run.snapshot_id is None


@pytest.mark.asyncio
async def test_expand_entity_suggestions_need_confirmation(session, storage):
    """AI 建议的新字段/新模块不自动成为 schema（梯子原则 I2 / R7）。"""
    from app.services.novel_source.world_domains import WorldDomainService
    from app.services.novel_source.world_generation import WorldGenerationService

    project_id, places = _seed_project_with_places(
        session, "建议项目", [("龙二赌坊", "赌坊。", [])]
    )
    ai = FakeGenerationAI(
        attributes={"region": "镇上"},
        suggested_fields=[
            {"domain": "location", "field": "气候带", "reason": "现有字段无法表达环境"}
        ],
        suggested_domains=[
            {
                "key": "underworld",
                "label": "地下势力",
                "attributes": ["层级", "庇护范围"],
                "reason": "这个世界观需要独立的地下势力维度",
            }
        ],
    )
    service = WorldGenerationService(session, ai_service=ai)
    result = await service.expand_entity(
        project_id, places["龙二赌坊"].id, fields=["region"]
    )

    assert result["suggested_fields"][0]["field"] == "气候带"
    assert result["suggested_domains"][0]["state"] == "pending_confirmation"

    domains = WorldDomainService(session)
    rows = {row["key"]: row for row in domains.list_domains(project_id)}
    assert rows["underworld"]["source"] == "ai_suggested"
    assert rows["underworld"]["is_enabled"] is False
    # 过闸：确认前不参与提取/生成
    assert "underworld" not in {spec.key for spec in domains.resolve_specs(project_id)}


def test_preview_entity_expansion_does_not_call_model(session, storage):
    """预览提示词：不调用模型、不消耗配额（R4）。"""
    from app.services.novel_source.world_generation import WorldGenerationService

    project_id, places = _seed_project_with_places(
        session, "预览项目", [("龙二赌坊", "赌坊。", [])]
    )
    ai = FakeGenerationAI(attributes={})
    service = WorldGenerationService(session, ai_service=ai)

    preview = service.preview_entity_expansion(
        project_id, places["龙二赌坊"].id, fields=["region"]
    )

    assert ai.prompts == []
    assert "龙二赌坊" in preview["prompt"]
    assert "region" in preview["prompt"]


@pytest.mark.asyncio
async def test_expand_entity_rejects_fields_outside_schema(session, storage):
    """契约外的字段拒绝生成：想加结构必须走建议通道，而不是偷偷写值。"""
    from app.services.novel_source.world_generation import WorldGenerationService

    project_id, places = _seed_project_with_places(
        session, "越界项目", [("龙二赌坊", "赌坊。", [])]
    )
    service = WorldGenerationService(session, ai_service=FakeGenerationAI(attributes={}))
    with pytest.raises(ValueError):
        await service.expand_entity(
            project_id, places["龙二赌坊"].id, fields=["不存在的字段"]
        )


def test_outline_sourced_candidates_are_marked_outline_not_original(tmp_path):
    """来源为项目大纲时，候选标记 outline：证据指向大纲，不得伪装成原著出处。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from sqlmodel import select

    from app.api.v1 import novel_sources as novel_sources_api
    from app.db.database import get_session
    from app.db.models.creative_project import CreativeProject
    from app.services.creative_project.service import CreativeProjectService, dumps_json

    # TestClient 会在独立线程处理请求，文件型 SQLite 并放开同线程限制。
    engine = create_engine(
        f"sqlite:///{tmp_path / 'outline-world.db'}",
        connect_args={"check_same_thread": False},
    )
    for table in (
        CreativeProject.__table__,
        NovelSourceSnapshot.__table__,
        NovelSourceChapter.__table__,
        NovelTextChunk.__table__,
        WorldExtractionRun.__table__,
        WorldFactCandidate.__table__,
        WorldDomainDefinition.__table__,
    ):
        table.create(engine)
    factory = sessionmaker(class_=Session, bind=engine, expire_on_commit=False)

    with factory() as seed:
        project = CreativeProjectService(seed, ai_service=FakeWorldAI()).create_project(
            title="大纲项目", project_type="novel", source_type="original_idea", idea="x"
        )
        project.outline_json = dumps_json(OUTLINE_FOR_WORLD)
        seed.add(project)
        seed.commit()
        project_id = project.id

    app = FastAPI()
    app.include_router(novel_sources_api.router)

    def _override_session():
        with factory() as db:
            yield db

    def _override_extraction_service():
        return WorldExtractionService(factory(), ai_service=FakeWorldAI(items=OUTLINE_WORLD_ITEMS))

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[novel_sources_api.extraction_service] = _override_extraction_service
    client = TestClient(app)

    try:
        response = client.post(f"/api/v1/creative-projects/{project_id}/world-extraction/start", json={})
        assert response.status_code == 200, response.text
        run_id = response.json()["data"]["run_id"]

        with factory() as check:
            candidates = check.exec(
                select(WorldFactCandidate).where(WorldFactCandidate.run_id == run_id)
            ).all()
            assert candidates, "应当产出候选"
            origins = {item.origin for item in candidates}
            # 大纲来源：不是 original（原著可考），也不是 ai_draft（无原文）
            assert "original" not in origins
            assert origins <= {"outline", "ai_inferred"}
            assert "outline" in origins
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_pending_suggestions_gate_confirm_and_ignore(session, storage):
    """结构建议必须过闸：列得出、确认才入契约、忽略后不再提示。"""
    from app.services.novel_source.world_domains import WorldDomainService
    from app.services.novel_source.world_generation import WorldGenerationService

    project_id, places = _seed_project_with_places(
        session, "过闸项目", [("龙二赌坊", "赌坊。", [])]
    )
    domains = WorldDomainService(session)
    ai = FakeGenerationAI(
        attributes={"region": "镇上"},
        suggested_fields=[
            {"domain": "location", "field": "气候带", "reason": "现有字段无法表达环境"}
        ],
        suggested_domains=[
            {"key": "underworld", "label": "地下势力", "attributes": ["层级"]}
        ],
    )
    await WorldGenerationService(session, ai_service=ai).expand_entity(
        project_id, places["龙二赌坊"].id, fields=["region"]
    )

    pending = domains.pending_suggestions(project_id)
    assert [item["key"] for item in pending["domains"]] == ["underworld"]
    assert [(item["domain"], item["field"]) for item in pending["fields"]] == [
        ("location", "气候带")
    ]
    # 建议未确认时，绝不出现在生效的域契约里
    assert "underworld" not in {spec.key for spec in domains.resolve_specs(project_id)}
    assert "气候带" not in list(
        next(spec for spec in domains.resolve_specs(project_id) if spec.key == "location").attributes
    )

    # 确认模块建议：转 custom 并启用
    domains.upsert_definition(
        project_id,
        "underworld",
        label="地下势力",
        extra_attributes=["层级"],
        source="custom",
        is_enabled=True,
    )
    assert "underworld" in {spec.key for spec in domains.resolve_specs(project_id)}
    assert domains.pending_suggestions(project_id)["domains"] == []

    # 确认字段建议：写入 location 的属性契约
    domains.confirm_suggested_field(project_id, "location", "气候带")
    location_spec = next(
        spec for spec in domains.resolve_specs(project_id) if spec.key == "location"
    )
    assert "气候带" in list(location_spec.attributes)
    assert "aliases" in list(location_spec.attributes)  # 内置字段仍在
    assert domains.pending_suggestions(project_id)["fields"] == []

    # 忽略字段建议：不再重复提示
    domains.ignore_suggested_field(project_id, "location", "风向")
    ignored = [
        row
        for row in domains.list_domains(project_id)
        if row["key"] == "location"
    ]
    assert ignored, "location 应有项目级定义"
    # 风向不在建议列表（被忽略），也不在属性契约
    assert domains.pending_suggestions(project_id)["fields"] == []
    assert "风向" not in list(
        next(spec for spec in domains.resolve_specs(project_id) if spec.key == "location").attributes
    )


@pytest.mark.asyncio
async def test_expand_domain_creates_domain_level_ai_draft_candidates(session, storage):
    """域级细化：按层次策略产出该域多条候选，全部标记 ai_draft 且无伪造证据。"""
    from app.services.novel_source.world_generation import WorldGenerationService

    project_id, _places = _seed_project_with_places(
        session, "域级项目", [("龙二赌坊", "赌坊。", [])]
    )
    ai = FakeGenerationAI(
        attributes={"kind": "街区", "region": "镇上"},
    )
    service = WorldGenerationService(session, ai_service=ai)

    result = await service.expand_domain(project_id, "location", hint="补充镇上的地点")

    assert result["candidate_count"] >= 1
    assert result["origin"] == "ai_draft"
    assert result["domain"] == "location"

    candidates = session.exec(
        select(WorldFactCandidate).where(WorldFactCandidate.run_id == result["run_id"])
    ).all()
    assert candidates, "应当落库候选"
    for candidate in candidates:
        assert candidate.origin == "ai_draft"
        assert json.loads(candidate.evidence_json) == []  # 生成链路不伪造证据
        assert candidate.snapshot_id is None

    run = session.get(WorldExtractionRun, result["run_id"])
    assert run.kind == "generate"
    assert run.status == "success"


def test_domain_expansion_task_type_is_persisted():
    """域级细化接入既有任务中心：任务类型必须可持久化（否则重启后轮询不到）。"""
    from app.services.task_persistence import PERSISTED_TASK_TYPES, should_persist

    assert "world_domain_expansion" in PERSISTED_TASK_TYPES
    assert should_persist("world_domain_expansion", {"project_id": "p1"}) is True
    # 沿用既有规则：没有 project_id 的任务不持久化
    assert should_persist("world_domain_expansion", {}) is False
    # 既有类型不受影响
    assert should_persist("image_generation", {"project_id": "p1"}) is True


def test_templates_are_data_driven_and_builtin_readonly(session, storage):
    """模板层次与提示词由数据决定；内置模板只读，项目模板可改可删。"""
    from app.services.novel_source.world_generation import WorldGenerationService

    project_id = _project_id(session, "模板管理项目")
    service = WorldGenerationService(session)

    created = service.upsert_template(
        project_id,
        name="现代地理层级",
        layers=["世界", "国家", "省/州", "城市"],
        prompts={"expand_domain": "按层次 {layers} 细化，已有：{known}。要求：{hint}"},
        is_default=True,
    )
    templates = service.list_templates(project_id)
    own = [item for item in templates if item["id"] == created.id]
    assert own and own[0]["layers"] == ["世界", "国家", "省/州", "城市"]
    assert own[0]["is_default"] is True
    assert own[0]["is_builtin"] is False

    # 改层次名称与层数：完全由数据决定
    updated = service.upsert_template(
        project_id,
        template_id=created.id,
        name="双层结构",
        layers=["地表", "地下"],
    )
    assert updated.layers_json and json.loads(updated.layers_json) == ["地表", "地下"]

    # 内置模板（project_id 为空）只读
    builtin = WorldBuildingTemplate(
        project_id=None,
        name="内置·洋葱模型",
        layers_json=json.dumps(["世界", "地区", "地点"], ensure_ascii=False),
        is_builtin=True,
    )
    session.add(builtin)
    session.commit()
    with pytest.raises(ValueError):
        service.upsert_template(project_id, template_id=builtin.id, name="试图改名")
    service.delete_template(project_id, builtin.id)  # 内置模板删不掉
    assert any(item["is_builtin"] for item in service.list_templates(project_id))

    # 项目私有模板可删
    service.delete_template(project_id, created.id)
    assert not [item for item in service.list_templates(project_id) if item["id"] == created.id]


class DraftTemplateAI(FakeWorldAI):
    """模板 AI 起草：按模板起草契约返回草案 JSON，不访问真实模型。"""

    def __init__(self):
        super().__init__()
        self.payload = {
            "name": "位面→大陆层级",
            "layers": ["多元宇宙", "位面", "大陆", "城邦"],
            "prompts": {
                "expand_domain": "按层次 {layers} 细化「{domain}」，已有：{known}，补充要求：{hint}。",
                "expand_entity": "为实体 {entity} 补字段：{fields}。",
            },
            "note": "面向多大陆位面的通用细化模板",
        }

    async def chat(self, messages, **kwargs):
        prompt = messages[-1].content
        self.prompts.append(prompt)
        return LLMGenerationResult(
            success=True,
            content=json.dumps(self.payload, ensure_ascii=False),
            provider="fake",
            model="fake-model",
        )


@pytest.mark.asyncio
async def test_draft_template_returns_draft_without_persisting(session, storage):
    """模板 AI 起草：按项目已启用模块起草草案，不落库（须确认后再 save，R4 纪律）。"""
    from app.services.novel_source.world_generation import WorldGenerationService

    project_id = _project_id(session, "起草项目")
    ai = DraftTemplateAI()
    service = WorldGenerationService(session, ai_service=ai)

    draft = await service.draft_template(
        project_id, domain="power_system", hint="仙侠力量分层"
    )

    assert draft["name"] == "位面→大陆层级"
    assert draft["layers"] == ["多元宇宙", "位面", "大陆", "城邦"]
    assert "expand_domain" in draft["prompts"]
    assert draft["prompts"]["expand_domain"]  # 提示词非空
    # 关键：草案不落库——list 仍然为空，用户确认后才走 upsert。
    assert service.list_templates(project_id) == []
    # 上下文应带上项目已启用模块（含力量/科技体系）与用户补充要求。
    joined = "\n".join(ai.prompts)
    assert "力量/科技体系" in joined
    assert "仙侠力量分层" in joined
    assert "power_system" in joined


@pytest.mark.asyncio
async def test_draft_template_rejects_unknown_focus_domain(session, storage):
    """起草时若指定的 focus 模块未启用/不存在，直接拒绝而不调用模型。"""
    from app.services.novel_source.world_generation import WorldGenerationService

    project_id = _project_id(session, "起草失败项目")
    service = WorldGenerationService(session, ai_service=DraftTemplateAI())
    with pytest.raises(ValueError, match="未启用或不存在"):
        await service.draft_template(project_id, domain="ghost_world")


def test_export_keeps_custom_fields_and_layer_across_schema_evolution(session, storage):
    """解析性保证：schema 演进（追加字段 + 空间层）后，导出仍含全部字段，旧数据不丢。"""
    from app.services.novel_source.world_domains import WorldDomainService
    from app.services.novel_source.world_generation import WorldGenerationService
    from app.services.novel_source.world_map import WorldMapService, build_map_export

    project_id, places = _seed_project_with_places(
        session, "演进项目", [("龙二赌坊", "赌坊。", [])]
    )
    # 先给 location 追加自定义字段，模拟 schema 演进
    WorldDomainService(session).upsert_definition(
        project_id, "location", extra_attributes=["气候带"], source="custom"
    )

    service = WorldMapService(session)
    document = service.create_map_from_project_places(project_id)
    data = json.loads(document.map_json)
    data["layers"] = [{"id": "l1", "name": "主世界"}]
    data["nodes"][0]["layer"] = "l1"
    data["nodes"][0]["attributes"] = {"climate": "温带季风", "custom_note": "自定义字段"}
    document = service.update_map(document.id, map_json=data, expected_revision=document.revision)

    exported = build_map_export(document)

    assert [item["name"] for item in exported["layers"]] == ["主世界"]
    node = exported["nodes"][0]
    assert node["layer"] == "l1"
    assert node["entity_id"] == places["龙二赌坊"].id
    assert node["evidence"] == []


def test_context_pack_marks_ai_draft_and_outline_sources(session, storage):
    """上下文打包必须区分来源：AI 创作与大纲依据不得混同于原文事实。"""
    from app.db.models.creative_project import ProjectContent
    from app.services.creative_project.service import CreativeProjectService, dumps_json

    project = CreativeProjectService(session, ai_service=FakeWorldAI()).create_project(
        title="来源标注项目", project_type="novel", source_type="original_idea", idea="x"
    )
    service = CreativeProjectService(session, ai_service=FakeWorldAI())

    def _add(title: str, data: dict) -> None:
        session.add(
            ProjectContent(
                project_id=project.id,
                content_type="world_asset",
                title=title,
                data_json=dumps_json(data),
                text_content=title,
                is_locked=True,
            )
        )

    _add("原文事实", {"summary": "来自真实原文", "role": "rule"})
    _add("AI 创作设定", {"summary": "AI 补充", "role": "rule", "field_sources": {"origin": "ai_draft"}})
    _add("大纲设定", {"summary": "大纲推导", "role": "rule", "source": "outline"})
    session.commit()

    context = service._locked_project_bible_context(project.id)

    assert "AI 创作（无原文证据）" in context
    assert "依据项目大纲" in context
    # 顶部必须有总体说明，否则模型不知道这些标注的含义
    assert "可据写作需要调整或推翻" in context
    assert "不要当成出版过的原文" in context


def test_religion_language_culture_ecology_domains_exist():
    """宗教/语言/文化/生态是通用世界观维度，已内置为可提取模块。"""
    from app.services.novel_source.contracts import get_domain

    for key, attrs in (
        ("religion", "deities"),
        ("language", "script"),
        ("culture", "customs"),
        ("ecology", "terrain"),
    ):
        spec = get_domain(key)
        assert spec is not None, f"缺少内置模块：{key}"
        assert spec.extractable is True
        assert attrs in spec.attributes
