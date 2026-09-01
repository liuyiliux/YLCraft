"""Agent tools for the novel-source → world-project workflow.

These mirror the human `/novel-world` flow exactly: inspect the source snapshot,
plan which world modules are evidenced, extract candidates with verbatim
evidence, preview them, then explicitly decide and apply.  Extraction never
writes project facts; ``apply`` is the single, confirm-gated write point.
"""

from __future__ import annotations

from typing import Any

from app.db.database import SessionLocal
from app.services.agent.registry import register_tool
from app.services.creative_project.service import loads_json
from app.services.novel_source.contracts import DETECTABLE_DOMAINS, EXTRACTABLE_DOMAINS
from app.services.novel_source.extraction import WorldExtractionService
from app.services.novel_source.service import NovelSourceService


def _snapshot_summary(snapshot: Any) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "title": snapshot.title,
        "author": snapshot.author,
        "source_kind": snapshot.source_kind,
        "source_status": snapshot.source_status,
        "project_id": snapshot.project_id,
        "chapter_count": snapshot.chapter_count,
        "char_count": snapshot.char_count,
        "revision": snapshot.revision,
        "indexing_status": snapshot.indexing_status,
    }


def _candidate_summary(candidate: Any) -> dict[str, Any]:
    payload = loads_json(candidate.payload_json, {})
    evidence = loads_json(candidate.evidence_json, [])
    return {
        "id": candidate.id,
        "domain": candidate.domain,
        "entity_name": candidate.entity_name,
        "summary": str(payload.get("summary") or "")[:200],
        "aliases": payload.get("aliases") or [],
        "confidence": candidate.confidence,
        "origin": candidate.origin,
        "status": candidate.status,
        "evidence_count": len(evidence),
        "evidence_quotes": [str(item.get("quote") or "")[:120] for item in evidence][:3],
    }


@register_tool(
    name="list_novel_source_snapshots",
    description="列出已导入的小说来源快照（TXT 或书架），供后续世界提取选择来源。",
    category="novel_source",
    examples=["列出我导入的小说来源快照", "看看有哪些小说可以提取世界观"],
    input_schema_note="project_id 和 source_kind（txt/bookshelf）可选；limit 最大 100。只读本地快照，不访问外部网站。",
    output_schema_note="返回 snapshots；每项含 id/title/author/source_kind/source_status/chapter_count/char_count。",
    risk_level="read",
    output_type="novel_source_snapshot_list",
)
def list_novel_source_snapshots(project_id: str = "", source_kind: str = "", limit: int = 50) -> dict[str, Any]:
    with SessionLocal() as session:
        service = NovelSourceService(session)
        snapshots = service.list_snapshots(
            project_id=project_id or None,
            source_kind=source_kind or None,
            limit=max(1, min(int(limit or 50), 100)),
        )
        return {"success": True, "total": len(snapshots), "snapshots": [_snapshot_summary(item) for item in snapshots]}


@register_tool(
    name="inspect_novel_source_snapshot",
    description="查看小说来源快照的章节结构和世界模块能力：章节清单、已实现提取的模块与可检测模块。",
    category="novel_source",
    examples=["看看这个来源快照有哪些章节", "这个小说能提取哪些世界模块"],
    input_schema_note="必须提供 snapshot_id；chapter_limit 最大 200。",
    output_schema_note="返回 snapshot、chapters、extractable_domains、detectable_domains。",
    risk_level="read",
    output_type="novel_source_snapshot_detail",
)
def inspect_novel_source_snapshot(snapshot_id: str, chapter_limit: int = 50) -> dict[str, Any]:
    with SessionLocal() as session:
        service = NovelSourceService(session)
        snapshot = service.get_snapshot(snapshot_id)
        if not snapshot:
            return {"success": False, "error": "来源快照不存在"}
        chapters = service.list_chapters(snapshot_id)[: max(1, min(int(chapter_limit or 50), 200))]
        return {
            "success": True,
            "snapshot": _snapshot_summary(snapshot),
            "chapters": [
                {"ordinal": item.ordinal, "title": item.title, "char_count": item.char_count}
                for item in chapters
            ],
            "extractable_domains": list(EXTRACTABLE_DOMAINS),
            "detectable_domains": list(DETECTABLE_DOMAINS),
        }


@register_tool(
    name="plan_novel_source_domains",
    description="让 AI 逐模块判断这部小说里存在哪些可提取的世界设定，返回 detected/not_detected/uncertain 与理由，不使用整体题材开关。",
    category="novel_source",
    examples=["判断这部小说有哪些世界模块可提取", "检测这本小说的物种和力量体系是否存在"],
    input_schema_note="必须提供 snapshot_id；requested_domains 可选（显式指定的模块标为 user_requested）。只检测，不提取。",
    output_schema_note="返回 domains；每项含 domain/label/status/reason/signals/estimated_cost/basic/extractable/enabled，以及 recommended 列表。",
    risk_level="costly",
    output_type="novel_source_domain_plan",
    cost_hint="会调用一次模型评估全部模块。",
)
async def plan_novel_source_domains(
    snapshot_id: str,
    requested_domains: list[str] | None = None,
    provider: str = "",
    model: str = "",
) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WorldExtractionService(session)
        try:
            plan = await service.plan_domains(
                snapshot_id,
                provider=provider or None,
                model=model or None,
                requested_domains=requested_domains,
            )
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "plan": plan}


@register_tool(
    name="extract_novel_source_world",
    description="按选定模块从来源快照提取世界事实候选（角色/地点/势力/历史事件），默认只预览，不写项目事实。",
    category="novel_source",
    examples=["从这部小说提取角色、地点和势力，先给我预览", "提取这部小说的历史事件"],
    input_schema_note="必须提供 snapshot_id；domains 传要提取的模块（默认按 plan 的 detected/user_requested 模块）；provider/model 可选；mode=full|delta。",
    output_schema_note="返回 run_id/status/mode/domains（每域 run_state/items/error）/candidate_count/failures。候选需经 list_world_extraction_candidates 查看证据。",
    risk_level="costly",
    output_type="novel_source_world_extraction",
    cost_hint="会按模块和文本块多次调用模型；单个模块失败不影响其他模块。",
)
async def extract_novel_source_world(
    snapshot_id: str,
    domains: list[str] | None = None,
    project_id: str = "",
    provider: str = "",
    model: str = "",
    mode: str = "full",
) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WorldExtractionService(session)
        try:
            result = await service.extract(
                snapshot_id,
                domains=domains,
                project_id=project_id or None,
                provider=provider or None,
                model=model or None,
                mode=mode,
            )
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "extraction": result}


@register_tool(
    name="list_world_extraction_candidates",
    description="预览一次世界提取运行产生的候选，每条带逐字原文证据，供智能体或用户审阅后决定接受或忽略。",
    category="novel_source",
    examples=["查看这次提取的世界候选", "看看角色候选有没有证据"],
    input_schema_note="必须提供 run_id；domain/status 可选；limit 最大 200。",
    output_schema_note="返回 candidates；每项含 id/domain/entity_name/summary/aliases/confidence/origin/status/evidence_count/evidence_quotes。",
    risk_level="read",
    output_type="novel_source_world_candidates",
)
def list_world_extraction_candidates(run_id: str, domain: str = "", status: str = "", limit: int = 100) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WorldExtractionService(session)
        candidates = service.list_candidates(
            run_id,
            domain=domain or None,
            status=status or None,
            limit=max(1, min(int(limit or 100), 200)),
        )
        return {
            "success": True,
            "total": len(candidates),
            "candidates": [_candidate_summary(item) for item in candidates],
        }


@register_tool(
    name="sync_novel_source_chapters",
    description="为连载来源快照追加新章节和新文本块。只追加，不重建；已导入章节的偏移与既有证据锚点保持不变。",
    category="novel_source",
    examples=["把新章节同步进这个来源快照", "连载更新了，追加新章节"],
    input_schema_note="必须提供 snapshot_id，且快照 source_status 必须是 serial；chapters 为 [{title, content, chapter_id?}]，重复标题会被跳过。",
    output_schema_note="返回更新后的快照摘要（chapter_count/char_count/last_chapter_ordinal）。",
    risk_level="write",
    output_type="novel_source_snapshot_sync",
)
def sync_novel_source_chapters(snapshot_id: str, chapters: list[dict[str, Any]]) -> dict[str, Any]:
    with SessionLocal() as session:
        service = NovelSourceService(session)
        try:
            snapshot = service.append_bookshelf_chapters(snapshot_id, chapters=chapters or [])
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "snapshot": _snapshot_summary(snapshot)}


@register_tool(
    name="decide_world_extraction_candidates",
    description="把世界提取候选标记为接受或忽略。只改候选状态，不写项目事实；确认写入需再调用 apply_world_extraction_run。",
    category="novel_source",
    examples=["接受这些角色候选，忽略那条地点候选", "标记候选决策"],
    input_schema_note="必须提供 run_id；decisions 为 [{candidate_id, action: accept|ignore, note?}]。",
    output_schema_note="返回 accepted/ignored/skipped 计数。",
    risk_level="write",
    output_type="novel_source_world_decision",
)
def decide_world_extraction_candidates(run_id: str, decisions: list[dict[str, Any]]) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WorldExtractionService(session)
        result = service.decide_candidates(run_id, decisions or [])
        return {"success": True, "decision": result}


@register_tool(
    name="apply_world_extraction_run",
    description="把已接受的候选写入项目：角色进入角色库并建立项目关联，其余域写入锁定的 world_asset 事实卡。这是唯一写入点。",
    category="novel_source",
    examples=["确认把已接受的候选写入项目", "把这个世界提取写入创作项目"],
    input_schema_note="必须提供 run_id；project_id 可选，不传则按来源快照自动创建世界项目。",
    output_schema_note="返回 project_id/characters_written/world_assets_written。",
    risk_level="write",
    output_type="novel_source_world_apply",
    cost_hint="会写入角色库、项目关联和锁定的世界事实卡。",
)
async def apply_world_extraction_run(run_id: str, project_id: str = "") -> dict[str, Any]:
    with SessionLocal() as session:
        service = WorldExtractionService(session)
        try:
            result = await service.apply_run(run_id, project_id=project_id or None)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "applied": result}


@register_tool(
    name="index_novel_source_chunks",
    description="为小说来源文本块建立可选向量索引；失败时不影响后续精确检索。",
    category="novel_source",
    examples=["给这本小说建立语义索引", "准备长篇小说检索"],
    input_schema_note="必须提供 snapshot_id；provider 可选；max_chunks 最大 2000。",
    output_schema_note="返回 indexed/failed/total。",
    risk_level="costly",
    output_type="novel_source_chunk_index",
    cost_hint="会调用 embedding 模型，按文本块产生费用或本地计算成本。",
)
async def index_novel_source_chunks(snapshot_id: str, provider: str = "", max_chunks: int = 2000) -> dict[str, Any]:
    from app.services.embedding.service import EmbeddingService
    with SessionLocal() as session:
        service = NovelSourceService(session)
        if not service.get_snapshot(snapshot_id):
            return {"success": False, "error": "来源快照不存在"}
        # Agent 工具使用同步数据库会话；EmbeddingService 的调用在独立异步会话中完成。
        from app.db.database import AsyncSessionLocal
        async with AsyncSessionLocal() as embedding_session:
            embedding_service = EmbeddingService(embedding_session, provider_name=provider or None)
            async def embedder(values):
                return await embedding_service.embed_texts(values)
            result = await service.index_chunk_embeddings(
                snapshot_id,
                embedder=embedder,
                model_name=await embedding_service._get_effective_text_model_name(),
                max_chunks=max_chunks,
            )
        return {"success": True, "index": result}


@register_tool(
    name="search_novel_source_chunks",
    description="在小说来源中检索相关文本块，返回章节、字符偏移和原文，供证据复核或后续提取使用。",
    category="novel_source",
    examples=["查找主角第一次觉醒的原文", "检索关于北岭的描述"],
    input_schema_note="必须提供 snapshot_id 和 query；query_embedding 可选；top_k 最大 100。只读。",
    output_schema_note="返回带 chunk_id/start_offset/end_offset/content/score 的 results。",
    risk_level="read",
    output_type="novel_source_chunk_search",
)
def search_novel_source_chunks(
    snapshot_id: str,
    query: str,
    query_embedding: list[float] | None = None,
    top_k: int = 10,
    with_neighbors: int = 0,
) -> dict[str, Any]:
    with SessionLocal() as session:
        service = NovelSourceService(session)
        if not service.get_snapshot(snapshot_id):
            return {"success": False, "error": "来源快照不存在"}
        return {
            "success": True,
            "results": service.search_chunks(
                snapshot_id,
                query,
                query_embedding=query_embedding,
                top_k=top_k,
                with_neighbors=with_neighbors,
            ),
        }


@register_tool(
    name="propagate_affected_world_facts",
    description="候选被合并或判定为矛盾后，把它此前已写入的 world_asset 事实标记为待复核（review_required）并附原因；只打标记，不改写事实内容。",
    category="novel_source",
    examples=["这些合并过的候选举事实还有哪些要复核", "把冲突候选已写入的事实标为待复核"],
    input_schema_note="必须提供 run_id；verdicts 可选（传入 detect_world_extraction_contradictions 的结果以附带矛盾原因）。",
    output_schema_note="返回 affected_facts（fact_id/title/candidate_id/entity_name/domain/reason）与 affected_candidates 计数。",
    risk_level="write",
    output_type="novel_source_affected_facts",
)
def propagate_affected_world_facts(
    run_id: str,
    verdicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WorldExtractionService(session)
        try:
            result = service.propagate_affected_facts(run_id, verdicts=verdicts or None)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "affected": result}


@register_tool(
    name="derive_project_from_novel_source",
    description="从完本小说来源创建改编（adaptation）/续写（continuation）/同人（fan_work）派生项目；原作已确认的世界事实与角色关联会复制进新项目并标记为只读参考层。",
    category="novel_source",
    examples=["用这本完本小说开一个续写项目", "基于这部作品做同人创作"],
    input_schema_note="必须提供 snapshot_id 和 derivation_kind（adaptation/continuation/fan_work）；title/project_type 可选。只有完本来源支持；连载来源请用 sync_novel_source_chapters。",
    output_schema_note="返回 project_id/derivation_kind/source_canon_assets/characters_linked。",
    risk_level="write",
    output_type="novel_source_project_derive",
    cost_hint="会创建创作项目并复制原作正典事实与角色关联。",
)
def derive_project_from_novel_source(
    snapshot_id: str,
    derivation_kind: str,
    title: str = "",
    project_type: str = "novel",
) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WorldExtractionService(session)
        try:
            result = service.derive_project(
                snapshot_id,
                derivation_kind=derivation_kind,
                title=title,
                project_type=project_type,
            )
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "derived": result}


@register_tool(
    name="detect_world_extraction_contradictions",
    description="对调和发现的重复候选做语义判断：同一实体且一致（consistent）、同一实体但矛盾（conflicting）、还是不同实体（distinct）。只读提示，不自动合并。",
    category="novel_source",
    examples=["这几条重复候选是不是同一个东西", "检查候选描述有没有矛盾"],
    input_schema_note="必须提供 run_id；provider/model 可选。会调用一次模型逐组判断。",
    output_schema_note="返回 groups（每组合 verdict/reason/recommended_action）与 conflicting 计数。",
    risk_level="costly",
    output_type="novel_source_world_contradictions",
    cost_hint="会调用一次模型对重复组做一致性判断。",
)
async def detect_world_extraction_contradictions(
    run_id: str, provider: str = "", model: str = ""
) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WorldExtractionService(session)
        try:
            result = await service.detect_contradictions(
                run_id, provider=provider or None, model=model or None
            )
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "contradictions": result}


@register_tool(
    name="reconcile_world_extraction_run",
    description="检查一次世界提取的候选是否存在跨模块重名、别名交叉、证据重叠与时序问题。只读提示，不自动合并或删除候选。",
    category="novel_source",
    examples=["检查这次提取有没有重复的候选", "看看有没有跨模块重名"],
    input_schema_note="必须提供 run_id。确定性计算，不调用模型，不修改任何候选。",
    output_schema_note="返回 candidate_count/duplicate_groups（含 kinds 与 reason）/evidence_overlaps/timeline（含 parsed 偏移）/conflict_count。",
    risk_level="read",
    output_type="novel_source_world_reconcile",
)
def reconcile_world_extraction_run(run_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WorldExtractionService(session)
        try:
            report = service.reconcile_run(run_id)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "reconcile": report}
