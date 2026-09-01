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
    WorldEntity,
    WorldEntityRelation,
    WorldExtractionRun,
    WorldFactCandidate,
    WorldMapDocument,
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
        WorldEntity.__table__,
        WorldEntityRelation.__table__,
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
    assert "霜岭关—北岭城" in prompt
    assert "水墨" in prompt

    # 空地图也能生成兜底 prompt，不抛错。
    empty = service.create_map(title="空白图", map_json={"regions": [], "nodes": [], "routes": []})
    assert "空白图" in build_map_visual_prompt(empty)


def test_world_map_visual_prompt_preview_endpoint(tmp_path):
    """地图生图支持先预览 prompt 再生成，不消耗生图配额。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.api.v1 import novel_sources as novel_sources_api
    from app.db.database import get_session
    from app.db.models.novel_source import WorldMapDocument
    from app.services.novel_source.world_map import WorldMapService

    # TestClient 在独立线程运行 ASGI 应用，用文件型库并放开同线程限制。
    engine = create_engine(
        f"sqlite:///{tmp_path / 'maps.db'}", connect_args={"check_same_thread": False}
    )
    WorldMapDocument.__table__.create(engine)
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
