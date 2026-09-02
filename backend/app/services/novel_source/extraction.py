"""世界提取服务：模块检测、分域提取、证据校验与确认写入。

流程遵循 design.md 的四层事实模型：

    原文观察（逐字引文 + 锚点）
      -> 提取草稿（归并后的候选）
      -> 用户/Agent 预览与决策
      -> 已确认正典（项目 world_asset / Character）

模型输出永远先落到候选，只有显式 accept 之后才写项目事实。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy import or_
from sqlmodel import Session, select

from app.db.models.character import Character, CharacterStoryLink
from app.db.models.creative_project import ProjectContent
from app.db.models.novel_source import (
    DERIVATION_LABELS,
    CandidateOrigin,
    CandidateStatus,
    DerivationKind,
    DomainDetectionState,
    DomainRunState,
    ExtractionRunMode,
    ExtractionRunStatus,
    NovelSourceSnapshot,
    NovelTextChunk,
    SourceStatus,
    WorldEntity,
    WorldEntityRelation,
    WorldExtractionRun,
    WorldFactCandidate,
)
from app.services.ai.types import LLMMessage
from app.services.creative_project.service import (
    CHARACTER_SOURCE_MAX_CHARS,
    CreativeProjectService,
    dumps_json,
    loads_json,
)
from app.services.novel_source.contracts import (
    BASIC_DOMAINS,
    CONTRADICTION_CONFLICTING,
    DETECTABLE_DOMAINS,
    DETECTION_UNCERTAIN,
    DOMAIN_HISTORICAL_EVENT,
    ESTIMATED_COSTS,
    VALID_CONTRADICTION_VERDICTS,
    VALID_DETECTIONS,
    ContradictionVerdictSchema,
    DomainDetectionSchema,
    DomainExtractionSchema,
    ExtractedFactItem,
    build_candidate_fingerprint,
    domain_label,
    get_domain,
    normalize_entity_name,
)
from app.services.novel_source.service import NovelSourceService

logger = logging.getLogger("ylcraft.novel_source.extraction")

TModel = TypeVar("TModel", bound=BaseModel)

PIPELINE_VERSION = "v1"
DETECTION_SAMPLE_CHUNKS = 6
DEFAULT_BATCH_CHARS = 6000
DEFAULT_MAX_CHUNKS = 60
DEFAULT_MAX_ITEMS_PER_DOMAIN = 60

#: 复杂实体间类型化关系的物化规则：domain -> [(attribute_field, relation_type, target_entity_type)]。
#: 目标类型用 contracts 里的 ``entity_type``（location 域对应 "place"）。只物化复杂实体间
#: （非角色）关系；涉及角色的关系继续由 CharacterRelationship 承载。
RELATION_HINTS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "faction": (("rivals", "rival", "faction"), ("territory", "controls", "place")),
    "location": (("region", "part_of", "place"),),
    "historical_event": (("location", "occurred_at", "place"),),
    "species": (("relations", "related_to", "species"), ("habitat", "inhabits", "place")),
    "item": (("origin", "originated_from", "place"),),
    "economy": (("institutions", "operated_by", "faction"),),
    "world_rule": (("enforced_by", "enforced_by", "faction"),),
}


def _as_name_list(value: Any) -> list[str]:
    """把关系字段值归一化成实体名列表（支持单个字符串与列表）。"""
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,，、;；/]", value)
        return [part.strip() for part in parts if part.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


class WorldExtractionService:
    """多域世界提取与候选审阅。"""

    def __init__(self, session: Session, ai_service: Any | None = None):
        self.session = session
        self.sources = NovelSourceService(session)
        if ai_service is not None:
            self.ai_service = ai_service
        else:
            from app.services.ai import get_ai_service

            self.ai_service = get_ai_service()

    # ------------------------------------------------------------------
    # Domain planning
    # ------------------------------------------------------------------

    async def plan_domains(
        self,
        snapshot_id: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        requested_domains: list[str] | None = None,
        sample_chunks: int = DETECTION_SAMPLE_CHUNKS,
    ) -> dict[str, Any]:
        """让 AI 逐模块判断存在性，而不是套用一个整体题材开关。

        用户显式指定的模块标记为 ``user_requested``，跳过模型判断。
        """
        snapshot = self._require_snapshot(snapshot_id)
        chunks = self.sources.list_chunks(snapshot.id, limit=max(1, min(int(sample_chunks or 6), 30)))
        if not chunks:
            raise ValueError("来源还没有文本块，无法评估世界模块")

        requested = {
            str(item).strip()
            for item in (requested_domains or [])
            if str(item).strip() in set(DETECTABLE_DOMAINS)
        }
        sample = "\n\n".join(
            f"[块 {chunk.ordinal}] {chunk.content}" for chunk in chunks
        )[:20000]

        normalized: list[dict[str, Any]] = []
        if requested:
            model_statuses = await self._detect_domains(
                snapshot=snapshot,
                sample=sample,
                provider=provider,
                model=model,
                skip=set(),
            )
            for item in model_statuses:
                if item["domain"] in requested:
                    item["status"] = DomainDetectionState.USER_REQUESTED.value
                    item["reason"] = f"{item['reason']}（用户显式指定）".strip("；; ")
            normalized = model_statuses
        else:
            normalized = await self._detect_domains(
                snapshot=snapshot,
                sample=sample,
                provider=provider,
                model=model,
                skip=set(),
            )

        for item in normalized:
            domain = str(item.get("domain") or "")
            spec = get_domain(domain)
            item["label"] = spec.label if spec else domain
            item["basic"] = bool(spec.basic) if spec else False
            item["extractable"] = bool(spec.extractable) if spec else False
            item["enabled"] = bool(spec.extractable) if spec else False

        return {
            "snapshot_id": snapshot.id,
            "title": snapshot.title,
            "provider": provider or "",
            "model": model or "",
            "domains": normalized,
            "recommended": [
                item["domain"]
                for item in normalized
                if item.get("extractable") and item.get("status") in {
                    DomainDetectionState.DETECTED.value,
                    DomainDetectionState.USER_REQUESTED.value,
                }
            ],
        }

    async def _detect_domains(
        self,
        *,
        snapshot: NovelSourceSnapshot,
        sample: str,
        provider: str | None,
        model: str | None,
        skip: set[str],
    ) -> list[dict[str, Any]]:
        prompt = self._detection_prompt(snapshot, sample, skip)
        data = await self._generate_json(
            prompt=prompt,
            system_prompt="你是小说世界设定的模块评估器。只输出严格 JSON，不按题材标签猜测。",
            schema_model=DomainDetectionSchema,
            provider=provider,
            model=model,
            max_tokens=2500,
        )
        raw_items = data.get("domains") or []
        by_domain: dict[str, dict[str, Any]] = {}
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            domain = str(item.get("domain") or "").strip()
            if domain not in set(DETECTABLE_DOMAINS) or domain in skip:
                continue
            status = str(item.get("status") or DETECTION_UNCERTAIN).strip()
            if status not in VALID_DETECTIONS:
                status = DETECTION_UNCERTAIN
            cost = str(item.get("estimated_cost") or "low").strip()
            signals = [
                str(value).strip()[:60]
                for value in (item.get("signals") or [])
                if str(value).strip()
            ][:3]
            by_domain[domain] = {
                "domain": domain,
                "status": status,
                "reason": str(item.get("reason") or "").strip()[:400],
                "signals": signals,
                "estimated_cost": cost if cost in ESTIMATED_COSTS else "low",
            }
        # 模型漏掉的模块补为 uncertain，保证前端总能看到完整清单。
        for domain in DETECTABLE_DOMAINS:
            if domain in skip:
                continue
            by_domain.setdefault(
                domain,
                {
                    "domain": domain,
                    "status": DETECTION_UNCERTAIN,
                    "reason": "模型未给出判断，需人工确认",
                    "signals": [],
                    "estimated_cost": "low",
                },
            )
        return [by_domain[domain] for domain in DETECTABLE_DOMAINS if domain in by_domain]

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    async def extract(
        self,
        snapshot_id: str,
        *,
        domains: list[str] | None = None,
        domain_plan: list[dict[str, Any]] | None = None,
        project_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        mode: str = ExtractionRunMode.FULL.value,
        max_chunks: int = DEFAULT_MAX_CHUNKS,
        candidate_origin: str = CandidateOrigin.ORIGINAL.value,
    ) -> dict[str, Any]:
        """按域提取世界事实并落为待确认候选。

        任一域失败只让整体变 ``partial``，其他域的候选照常保留。

        ``candidate_origin`` 声明**本运行来源的性质**：真实原文为 ``original``；
        来源由项目大纲序列化而来时为 ``outline``——证据仍逐字命中，但命中对象是
        大纲文本而非原著，UI 必须据此说明「依据来自你的大纲」。
        """
        snapshot = self._require_snapshot(snapshot_id)
        requested = self._resolve_domains(domains, domain_plan)
        if not requested:
            raise ValueError("没有可提取的世界模块")

        run_mode = (
            ExtractionRunMode.DELTA.value
            if str(mode) == ExtractionRunMode.DELTA.value
            else ExtractionRunMode.FULL.value
        )
        from_ordinal = 0
        if run_mode == ExtractionRunMode.DELTA.value:
            from_ordinal = self._last_checkpoint_ordinal(snapshot.id, requested)
            if from_ordinal <= 0:
                raise ValueError("没有可用的增量游标，请先对该来源执行一次完整提取")

        run = WorldExtractionRun(
            snapshot_id=snapshot.id,
            project_id=project_id or snapshot.project_id,
            mode=run_mode,
            status=ExtractionRunStatus.RUNNING.value,
            pipeline_version=PIPELINE_VERSION,
            provider=provider or "",
            model=model or "",
        )
        self.session.add(run)
        self.session.flush()

        source_text = self.sources.load_source_text(snapshot.id)
        chunks = self.sources.list_chunks(
            snapshot_id,
            after_ordinal=from_ordinal or None,
            limit=max(1, min(int(max_chunks or DEFAULT_MAX_CHUNKS), 400)),
        )
        if not chunks:
            run.status = ExtractionRunStatus.FAILED.value
            self._finish_run(
                run,
                error="没有新的文本块" if run_mode == ExtractionRunMode.DELTA.value else "来源没有可提取的文本块",
            )
            raise ValueError(
                "没有新的文本块，来源已经是最新"
                if run_mode == ExtractionRunMode.DELTA.value
                else "来源没有可提取的文本块"
            )

        plan_states: list[dict[str, Any]] = []
        trace: list[dict[str, Any]] = []
        total_candidates = 0
        total_updated = 0
        successful_domains = 0
        failures: list[dict[str, str]] = []

        for domain in requested:
            spec = get_domain(domain)
            plan_state = self._initial_plan_state(domain, domain_plan)
            plan_state["run_state"] = DomainRunState.EXTRACTING.value
            plan_states.append(plan_state)
            try:
                items = await self._extract_domain(
                    snapshot=snapshot,
                    domain=domain,
                    chunks=chunks,
                    provider=provider,
                    model=model,
                )
                created, updated = self._persist_candidates(
                    run=run,
                    snapshot=snapshot,
                    domain=domain,
                    items=items,
                    source_text=source_text,
                    chunks=chunks,
                    delta=run_mode == ExtractionRunMode.DELTA.value,
                    source_origin=candidate_origin,
                )
                plan_state["run_state"] = DomainRunState.DRAFT.value
                plan_state["items"] = created
                plan_state["updated"] = updated
                successful_domains += 1
                total_candidates += created
                total_updated += updated
                trace.append(
                    {
                        "domain": domain,
                        "status": "success",
                        "candidates": created,
                        "updated": updated,
                        "chunks": len(chunks),
                        "from_chunk_ordinal": from_ordinal,
                    }
                )
            except Exception as exc:  # noqa: BLE001 - 单域失败不能影响其他域
                logger.warning("世界提取域失败 domain=%s run=%s: %s", domain, run.id, exc)
                plan_state["run_state"] = DomainRunState.FAILED.value
                plan_state["error"] = str(exc)[:500]
                failures.append({"domain": domain, "error": str(exc)[:300]})
                trace.append({"domain": domain, "status": "failed", "error": str(exc)[:300]})

        run.domains_json = dumps_json(plan_states)
        run.trace_json = dumps_json(trace)
        run.checkpoint_json = dumps_json(
            {
                "last_chunk_ordinal": max((chunk.ordinal for chunk in chunks), default=0),
                "last_run_at": datetime.now().isoformat(),
            }
        )
        run.status = (
            ExtractionRunStatus.SUCCESS.value
            if not failures
            else (
                ExtractionRunStatus.PARTIAL.value
                if successful_domains
                else ExtractionRunStatus.FAILED.value
            )
        )
        self._finish_run(run, error="; ".join(f"{f['domain']}: {f['error']}" for f in failures))

        return {
            "run_id": run.id,
            "snapshot_id": snapshot.id,
            "project_id": run.project_id,
            "status": run.status,
            "mode": run.mode,
            "domains": plan_states,
            "candidate_count": total_candidates,
            "updated_count": total_updated,
            "from_chunk_ordinal": from_ordinal,
            "failures": failures,
            "provider": run.provider,
            "model": run.model,
        }

    def _resolve_domains(
        self,
        domains: list[str] | None,
        domain_plan: list[dict[str, Any]] | None,
    ) -> list[str]:
        """从显式 domains 或检测结果里挑出真正可提取的域。

        两者都未提供时回落到基础层（角色/地点/势力/历史事件），避免出现
        “没传参数就报没有可提取模块”的死路；显式给了 ``domain_plan`` 却一个
        都没选中时，尊重用户关闭所有模块的意图，不偷偷补跑。
        """
        requested: list[str] = []
        if domains:
            for value in domains:
                key = str(value or "").strip()
                spec = get_domain(key)
                if spec and spec.extractable and key not in requested:
                    requested.append(key)
            return requested
        for item in domain_plan or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("domain") or "").strip()
            spec = get_domain(key)
            if not spec or not spec.extractable:
                continue
            status = str(item.get("status") or "")
            enabled = item.get("enabled")
            if enabled is True or status in {
                DomainDetectionState.DETECTED.value,
                DomainDetectionState.USER_REQUESTED.value,
            }:
                if key not in requested:
                    requested.append(key)
        if not requested and not domain_plan:
            # 既没指定域也没有检测结果：回落到基础层，而不是让调用方无从下手。
            for key in BASIC_DOMAINS:
                spec = get_domain(key)
                if spec and spec.extractable and key not in requested:
                    requested.append(key)
        return requested

    async def _extract_domain(
        self,
        *,
        snapshot: NovelSourceSnapshot,
        domain: str,
        chunks: list[NovelTextChunk],
        provider: str | None,
        model: str | None,
    ) -> list[ExtractedFactItem]:
        spec = get_domain(domain)
        if spec is None:
            raise ValueError(f"未知世界模块：{domain}")

        merged: dict[str, ExtractedFactItem] = {}
        for batch in self._iter_batches(chunks):
            prompt = self._extraction_prompt(snapshot, spec.key, spec.label, spec.prompt_hint, spec.attributes, batch)
            data = await self._generate_json(
                prompt=prompt,
                system_prompt="你是小说设定的摘录器。只输出严格 JSON，不补写原文没有的内容。",
                schema_model=DomainExtractionSchema,
                provider=provider,
                model=model,
                max_tokens=4000,
            )
            for raw in data.get("items") or []:
                if not isinstance(raw, dict):
                    continue
                name = str(raw.get("name") or "").strip()
                if not name:
                    continue
                item = ExtractedFactItem(
                    name=name,
                    aliases=[str(value).strip() for value in (raw.get("aliases") or []) if str(value).strip()][:12],
                    summary=str(raw.get("summary") or "").strip()[:400],
                    attributes=raw.get("attributes") if isinstance(raw.get("attributes"), dict) else {},
                    quotes=[str(value).strip() for value in (raw.get("quotes") or []) if str(value).strip()][:6],
                    confidence=_clamp_confidence(raw.get("confidence")),
                    uncertain=bool(raw.get("uncertain")),
                )
                self._merge_item(merged, item)
            if len(merged) >= DEFAULT_MAX_ITEMS_PER_DOMAIN:
                break
        return list(merged.values())[:DEFAULT_MAX_ITEMS_PER_DOMAIN]

    @staticmethod
    def _merge_item(target: dict[str, ExtractedFactItem], item: ExtractedFactItem) -> None:
        key = normalize_entity_name(item.name)
        existing = target.get(key)
        if existing is None:
            target[key] = item
            return
        existing.aliases = list(dict.fromkeys([*existing.aliases, *item.aliases]))[:12]
        existing.quotes = list(dict.fromkeys([*existing.quotes, *item.quotes]))[:6]
        existing.confidence = max(existing.confidence, item.confidence)
        existing.uncertain = existing.uncertain and item.uncertain
        if len(item.summary) > len(existing.summary):
            existing.summary = item.summary
        for field_name, value in item.attributes.items():
            if field_name not in existing.attributes or not existing.attributes[field_name]:
                existing.attributes[field_name] = value
            elif isinstance(value, str) and isinstance(existing.attributes[field_name], str):
                if value and value not in existing.attributes[field_name]:
                    existing.attributes[field_name] = f"{existing.attributes[field_name]}；{value}"

    @staticmethod
    def _iter_batches(chunks: list[NovelTextChunk]) -> list[list[NovelTextChunk]]:
        batches: list[list[NovelTextChunk]] = []
        current: list[NovelTextChunk] = []
        current_chars = 0
        for chunk in chunks:
            current.append(chunk)
            current_chars += len(chunk.content)
            if current_chars >= DEFAULT_BATCH_CHARS:
                batches.append(current)
                current = []
                current_chars = 0
        if current:
            batches.append(current)
        return batches

    def _persist_candidates(
        self,
        *,
        run: WorldExtractionRun,
        snapshot: NovelSourceSnapshot,
        domain: str,
        items: list[ExtractedFactItem],
        source_text: str,
        chunks: list[NovelTextChunk],
        delta: bool = False,
        source_origin: str = CandidateOrigin.ORIGINAL.value,
    ) -> tuple[int, int]:
        existing = self._active_candidates(snapshot.id, domain)
        created = 0
        updated = 0
        for item in items:
            fingerprint = build_candidate_fingerprint(snapshot.id, domain, item.name)
            evidence: list[dict[str, Any]] = []
            for quote in item.quotes:
                anchor = self.sources.locate_quote(
                    snapshot.id, quote, source_text=source_text, chunks=chunks
                )
                if anchor is None:
                    continue
                evidence.append(anchor.model_dump())
            if not evidence:
                # 没有任何逐字证据的条目不进入候选，避免把模型想象当成原文事实。
                continue

            current = existing.get(fingerprint)
            if current is not None:
                # 已存在的候选不再重复生成；增量运行把新证据和字段并回同一条，
                # 被用户忽略的候选保持忽略，不复活。
                if delta and current.status == CandidateStatus.PENDING.value:
                    updated += 1 if self._append_evidence(current, run.id, evidence, item) else 0
                continue

            # 推断内容一律标记 ai_inferred；其余按本次运行的来源性质：
            # 真实原文为 original，来源为项目大纲时为 outline（证据指向大纲，不是原著）。
            origin = (
                CandidateOrigin.AI_INFERRED.value
                if item.uncertain or item.confidence < 0.7
                else source_origin
            )
            candidate = WorldFactCandidate(
                run_id=run.id,
                snapshot_id=snapshot.id,
                project_id=run.project_id,
                domain=domain,
                entity_name=item.name,
                normalized_key=normalize_entity_name(item.name),
                fingerprint=fingerprint,
                payload_json=dumps_json(
                    {
                        "summary": item.summary,
                        "aliases": item.aliases,
                        "attributes": item.attributes,
                    }
                ),
                evidence_json=dumps_json(evidence),
                confidence=item.confidence,
                origin=origin,
                status=CandidateStatus.PENDING.value,
            )
            self.session.add(candidate)
            existing[fingerprint] = candidate
            created += 1
        self.session.flush()
        return created, updated

    def _append_evidence(
        self,
        candidate: WorldFactCandidate,
        run_id: str,
        evidence: list[dict[str, Any]],
        item: ExtractedFactItem,
    ) -> bool:
        """把增量运行的新证据并回既有候选，不重建候选本身。"""
        current = loads_json(candidate.evidence_json, [])
        if not isinstance(current, list):
            current = []
        known_quotes = {str(entry.get("quote") or "") for entry in current if isinstance(entry, dict)}
        additions = [entry for entry in evidence if str(entry.get("quote") or "") not in known_quotes]
        if not additions:
            return False

        payload = loads_json(candidate.payload_json, {})
        if not isinstance(payload, dict):
            payload = {}
        aliases = list(dict.fromkeys([*(payload.get("aliases") or []), *item.aliases]))[:12]
        attributes = dict(payload.get("attributes") or {})
        for key, value in item.attributes.items():
            if key not in attributes or not attributes[key]:
                attributes[key] = value

        candidate.evidence_json = dumps_json((current + additions)[-12:])
        candidate.payload_json = dumps_json(
            {
                **payload,
                "aliases": aliases,
                "attributes": attributes,
                "summary": item.summary if len(item.summary) > len(str(payload.get("summary") or "")) else payload.get("summary"),
            }
        )
        candidate.confidence = max(float(candidate.confidence or 0.0), item.confidence)
        candidate.last_run_id = run_id
        candidate.updated_at = datetime.now()
        self.session.add(candidate)
        return True

    def _active_candidates(self, snapshot_id: str, domain: str) -> dict[str, WorldFactCandidate]:
        rows = self.session.exec(
            select(WorldFactCandidate).where(
                WorldFactCandidate.snapshot_id == snapshot_id,
                WorldFactCandidate.domain == domain,
                WorldFactCandidate.status.in_(  # type: ignore[attr-defined]
                    [CandidateStatus.PENDING.value, CandidateStatus.ACCEPTED.value]
                ),
            )
        ).all()
        return {str(row.fingerprint): row for row in rows}

    def _active_fingerprints(self, snapshot_id: str, domain: str) -> set[str]:
        return set(self._active_candidates(snapshot_id, domain).keys())

    def _last_checkpoint_ordinal(self, snapshot_id: str, domains: list[str]) -> int:
        """返回每个目标域都已成功覆盖过的共同游标。

        不能把一次只提取了角色域的运行当作地点域的基线，否则后续地点
        增量提取会跳过尚未处理的旧正文。每域分别找到最近一次成功处理它
        的运行，再取最小游标，以保证所有目标域都不会漏掉来源文本。
        """
        runs = self.session.exec(
            select(WorldExtractionRun)
            .where(WorldExtractionRun.snapshot_id == snapshot_id)
            .order_by(WorldExtractionRun.created_at.desc())  # type: ignore[attr-defined]
            .limit(20)
        ).all()
        checkpoints: list[int] = []
        for domain in domains:
            for run in runs:
                plan = loads_json(run.domains_json, [])
                domain_completed = any(
                    isinstance(item, dict)
                    and item.get("domain") == domain
                    and item.get("run_state")
                    in {DomainRunState.DRAFT.value, DomainRunState.CONFIRMED.value}
                    for item in plan
                )
                if not domain_completed:
                    continue
                checkpoint = loads_json(run.checkpoint_json, {})
                if not isinstance(checkpoint, dict):
                    continue
                try:
                    value = int(checkpoint.get("last_chunk_ordinal") or 0)
                except (TypeError, ValueError):
                    continue
                if value > 0:
                    checkpoints.append(value)
                    break
            else:
                return 0
        return min(checkpoints, default=0)

    # ------------------------------------------------------------------
    # Review
    # ------------------------------------------------------------------

    def get_run(self, run_id: str) -> WorldExtractionRun | None:
        return self.session.get(WorldExtractionRun, run_id)

    def list_candidates(
        self,
        run_id: str,
        *,
        domain: str | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> list[WorldFactCandidate]:
        """列出本次运行产生或更新过的候选。

        增量运行会把新证据并回既有候选（候选保持原 run_id），所以这里同时
        匹配 ``run_id`` 和 ``last_run_id``，保证审阅界面能看到全部相关条目。
        """
        statement = select(WorldFactCandidate).where(
            or_(
                WorldFactCandidate.run_id == run_id,
                WorldFactCandidate.last_run_id == run_id,
            )
        )
        if domain:
            statement = statement.where(WorldFactCandidate.domain == domain)
        if status:
            statement = statement.where(WorldFactCandidate.status == status)
        statement = statement.order_by(
            WorldFactCandidate.domain, WorldFactCandidate.confidence.desc()  # type: ignore[attr-defined]
        ).limit(max(1, min(int(limit or 200), 1000)))
        return list(self.session.exec(statement).all())

    def decide_candidates(
        self,
        run_id: str,
        decisions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """批量把候选标记为待写入、忽略或合并进另一条候选。

        决策只改变候选状态，不写项目事实；真正落库在 ``apply_run``。
        ``merge`` 把源候选的证据与设定并入 ``merge_into`` 指向的目标候选，
        源候选进入 ``merged`` 终态，不再参与后续写入。
        """
        run = self.session.get(WorldExtractionRun, run_id)
        if not run:
            raise ValueError("提取运行不存在")
        accepted = 0
        ignored = 0
        merged = 0
        skipped = 0
        for decision in decisions:
            candidate_id = str(decision.get("candidate_id") or "").strip()
            action = str(decision.get("action") or "").strip()
            note = str(decision.get("note") or "").strip()[:500]
            candidate = self.session.get(WorldFactCandidate, candidate_id)
            reachable = candidate is not None and run_id in {candidate.run_id, candidate.last_run_id}
            if not reachable or candidate.status != CandidateStatus.PENDING.value:
                skipped += 1
                continue
            if action == "accept":
                candidate.status = CandidateStatus.ACCEPTED.value
                accepted += 1
            elif action == "ignore":
                candidate.status = CandidateStatus.IGNORED.value
                ignored += 1
            elif action == "merge":
                target_id = str(decision.get("merge_into") or "").strip()
                target = self.session.get(WorldFactCandidate, target_id) if target_id else None
                target_reachable = (
                    target is not None
                    and target.id != candidate.id
                    and run_id in {target.run_id, target.last_run_id}
                    and target.status
                    in {CandidateStatus.PENDING.value, CandidateStatus.ACCEPTED.value}
                )
                if not target_reachable:
                    skipped += 1
                    continue
                self._merge_candidate_into(candidate, target, run_id, note)  # type: ignore[arg-type]
                merged += 1
                continue
            else:
                skipped += 1
                continue
            candidate.review_note = note
            candidate.updated_at = datetime.now()
            self.session.add(candidate)
        self.session.commit()
        return {
            "run_id": run_id,
            "accepted": accepted,
            "ignored": ignored,
            "merged": merged,
            "skipped": skipped,
        }

    def _merge_candidate_into(
        self,
        source: WorldFactCandidate,
        target: WorldFactCandidate,
        run_id: str,
        note: str,
    ) -> None:
        """把源候选的证据、别名与设定并入目标候选；源候选进入 merged 终态。

        只合并逐字校验过的证据锚点；同名引文不重复追加。目标保持自己的
        去重指纹与既有状态，合并动作用 ``review_note`` 留痕。
        """
        source_payload = loads_json(source.payload_json, {})
        if not isinstance(source_payload, dict):
            source_payload = {}
        target_payload = loads_json(target.payload_json, {})
        if not isinstance(target_payload, dict):
            target_payload = {}

        target_evidence = loads_json(target.evidence_json, [])
        if not isinstance(target_evidence, list):
            target_evidence = []
        known_quotes = {
            str(entry.get("quote") or "") for entry in target_evidence if isinstance(entry, dict)
        }
        for entry in loads_json(source.evidence_json, []):
            if not isinstance(entry, dict):
                continue
            quote = str(entry.get("quote") or "")
            if quote and quote not in known_quotes:
                target_evidence.append(entry)
                known_quotes.add(quote)

        aliases = list(
            dict.fromkeys(
                [
                    *(target_payload.get("aliases") or []),
                    *(source_payload.get("aliases") or []),
                ]
            )
        )[:12]
        attributes = dict(target_payload.get("attributes") or {})
        for key, value in (source_payload.get("attributes") or {}).items():
            if key not in attributes or not attributes[key]:
                attributes[key] = value

        target.evidence_json = dumps_json(target_evidence[-12:])
        target.payload_json = dumps_json(
            {
                **target_payload,
                "aliases": aliases,
                "attributes": attributes,
                "summary": source_payload.get("summary")
                if len(str(source_payload.get("summary") or ""))
                > len(str(target_payload.get("summary") or ""))
                else target_payload.get("summary"),
            }
        )
        target.confidence = max(float(target.confidence or 0.0), float(source.confidence or 0.0))
        target.review_note = (
            f"merged from {source.id}"
            + (f"：{note}" if note else "")
        )[:500]
        target.updated_at = datetime.now()
        self.session.add(target)

        source.status = CandidateStatus.MERGED.value
        source.review_note = (f"merged into {target.id}" + (f"：{note}" if note else ""))[:500]
        source.target_entity_type = target.target_entity_type
        source.target_entity_id = target.id
        source.updated_at = datetime.now()
        self.session.add(source)

    async def apply_run(
        self,
        run_id: str,
        *,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """把已接受的候选写入项目事实。

        角色域复用既有角色提取的写入通道（角色库 + CharacterStoryLink），
        其他域写入锁定的 ``world_asset`` 事实卡。
        """
        run = self.session.get(WorldExtractionRun, run_id)
        if not run:
            raise ValueError("提取运行不存在")
        target_project_id = project_id or run.project_id or self._snapshot(run.snapshot_id).project_id
        if not target_project_id:
            target_project_id = self._create_project_for_snapshot(run.snapshot_id)

        creative = CreativeProjectService(self.session, ai_service=self.ai_service)
        self._ensure_project_source_sample(creative, target_project_id, run.snapshot_id)
        accepted = self.list_candidates(run_id, status=CandidateStatus.ACCEPTED.value)
        if not accepted:
            raise ValueError("没有已确认的候选，请先预览并选择要写入的条目")

        character_cards: list[dict[str, Any]] = []
        character_candidates: list[WorldFactCandidate] = []
        world_written: list[dict[str, Any]] = []
        entity_ids_by_candidate: dict[str, str] = {}

        for candidate in accepted:
            if candidate.domain == "character":
                character_cards.append(self._character_card(candidate))
                character_candidates.append(candidate)
            else:
                world_asset = self._write_world_asset(candidate, target_project_id)
                if world_asset.get("created", True):
                    world_written.append(world_asset)
                # 物化类型化独立实体（与事实卡并存，作为结构化索引）。
                entity_ids_by_candidate[candidate.id] = self._upsert_world_entity(
                    candidate, target_project_id
                )

        # 所有实体落库后，再物化复杂实体间的类型化关系（需要完整 name->id 映射）。
        relations_written = self._materialize_relations(
            accepted, target_project_id, entity_ids_by_candidate
        )

        if character_cards:
            await creative.extract_character_cards(
                target_project_id,
                apply=True,
                cards=character_cards,
                max_characters=len(character_cards),
            )
            self._link_characters(character_candidates, target_project_id)

        run.project_id = target_project_id
        run.status = ExtractionRunStatus.SUCCESS.value
        run.updated_at = datetime.now()
        self._mark_domain_state(run, DomainRunState.CONFIRMED.value)
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)

        return {
            "run_id": run.id,
            "project_id": target_project_id,
            "characters_written": len(character_cards),
            "world_assets_written": len(world_written),
            "world_entities_written": len(entity_ids_by_candidate),
            "world_relations_written": relations_written,
            "world_assets": world_written,
        }

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------

    def reconcile_run(self, run_id: str) -> dict[str, Any]:
        """跨域调和：找出重复候选、别名交叉、证据重叠与时序问题。

        全部是确定性计算，不调用模型。结论只作为审阅提示，**不会**自动
        合并、改名或删除任何候选；合并与取舍始终由真人或 Agent 显式决策。
        """
        run = self.session.get(WorldExtractionRun, run_id)
        if not run:
            raise ValueError("提取运行不存在")
        candidates = self.list_candidates(run_id, limit=1000)
        if not candidates:
            return {
                "run_id": run_id,
                "snapshot_id": run.snapshot_id,
                "candidate_count": 0,
                "duplicate_groups": [],
                "evidence_overlaps": [],
                "timeline": [],
                "conflict_count": 0,
            }

        duplicate_groups = self._duplicate_groups(candidates)
        evidence_overlaps = self._evidence_overlaps(candidates)
        timeline = self._timeline_entries(candidates)
        return {
            "run_id": run_id,
            "snapshot_id": run.snapshot_id,
            "candidate_count": len(candidates),
            "duplicate_groups": duplicate_groups,
            "evidence_overlaps": evidence_overlaps,
            "timeline": timeline,
            "conflict_count": len(duplicate_groups) + len(evidence_overlaps),
        }

    async def detect_contradictions(
        self,
        run_id: str,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """对调和发现的重复组做语义判断。

        调用一次模型逐组判断：同一实体且一致（consistent）、同一实体但矛盾
        （conflicting）、还是同名不同实体（distinct）。结果只作审阅提示，
        不自动合并；取舍仍由真人或 Agent 决策。
        """
        report = self.reconcile_run(run_id)
        groups = report["duplicate_groups"]
        if not groups:
            return {"run_id": run_id, "snapshot_id": report["snapshot_id"], "groups": [], "conflicting": 0}

        judged: list[dict[str, Any]] = []
        conflicting = 0
        for group in groups:
            verdict = await self._judge_group(group, provider, model)
            if verdict.get("verdict") == CONTRADICTION_CONFLICTING:
                conflicting += 1
            judged.append(
                {
                    **group,
                    "verdict": verdict.get("verdict") or "distinct",
                    "reason": str(verdict.get("reason") or ""),
                    "recommended_action": str(verdict.get("recommended_action") or "keep_separate"),
                }
            )
        return {
            "run_id": run_id,
            "snapshot_id": report["snapshot_id"],
            "groups": judged,
            "conflicting": conflicting,
        }

    async def _judge_group(
        self,
        group: dict[str, Any],
        provider: str | None,
        model: str | None,
    ) -> dict[str, Any]:
        candidates = group.get("candidates") or []
        if len(candidates) < 2:
            return {"verdict": "consistent", "reason": "", "recommended_action": "keep_separate"}
        lines = "\n".join(
            f"- [{item.get('domain_label') or item.get('domain')}] {item.get('entity_name')}：{item.get('summary') or ''}"
            for item in candidates
        )
        prompt = (
            "判断以下几条世界设定候选是否指向同一实体，以及它们的描述是否一致或矛盾。\n\n"
            f"{lines}\n\n"
            "只输出 JSON：\n"
            '{"verdict":"consistent|conflicting|distinct","reason":"一句话理由",'
            '"recommended_action":"merge|resolve|keep_separate"}\n\n'
            "规则：consistent=同一实体且描述一致，建议 merge；"
            "conflicting=同一实体但描述互相矛盾，建议 resolve（需人工取舍）；"
            "distinct=其实是不同实体，建议 keep_separate。"
        )
        data = await self._generate_json(
            prompt=prompt,
            system_prompt="你是小说设定的一致性判官。只输出严格 JSON，不做提取。",
            schema_model=ContradictionVerdictSchema,
            provider=provider,
            model=model,
            max_tokens=400,
        )
        verdict = str(data.get("verdict") or "").strip()
        if verdict not in VALID_CONTRADICTION_VERDICTS:
            verdict = "distinct"
        return {
            "verdict": verdict,
            "reason": str(data.get("reason") or "").strip()[:400],
            "recommended_action": str(data.get("recommended_action") or "").strip(),
        }

    def propagate_affected_facts(
        self,
        run_id: str,
        *,
        verdicts: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """把合并与重复/矛盾结论传播到**已写入**的项目事实。

        候选被 merge 或判定为冲突时，它们此前写入的 `world_asset` 事实卡
        可能已不完整或不可信：这里把这些事实标记为待复核（``review_required``）
        并附上原因，供真人或 Agent 回头修订。传播只打标记，不改写事实内容。
        """
        run = self.session.get(WorldExtractionRun, run_id)
        if not run:
            raise ValueError("提取运行不存在")
        candidates = self.list_candidates(run_id, limit=1000)
        if not candidates:
            return {"run_id": run_id, "affected_facts": [], "affected_candidates": 0}

        by_id = {item.id: item for item in candidates}
        affected: dict[str, str] = {}

        # 1) 被合并掉的源候选：它写入的事实只含合并前的证据。
        for item in candidates:
            if item.status == CandidateStatus.MERGED.value:
                affected[item.id] = (
                    f"该候选已并入另一条候选（{item.target_entity_id or '目标候选'}），"
                    "已写入的事实可能缺少并入后的证据"
                )
        # 2) 重复组：同名/别名交叉的候选写入后可能重复或矛盾。
        for group in self._duplicate_groups(candidates):
            for member in group["candidates"]:
                affected.setdefault(member["id"], group["reason"])
        # 3) 语义矛盾判定为 conflicting 的组，原因更明确。
        for group in verdicts or []:
            if str(group.get("verdict") or "") != CONTRADICTION_CONFLICTING:
                continue
            for member in group.get("candidates") or []:
                member_id = str(member.get("id") or "")
                if member_id in by_id:
                    affected[member_id] = str(group.get("reason") or "") or "描述矛盾，需人工取舍"

        facts: list[dict[str, Any]] = []
        touched = 0
        for candidate_id, reason in affected.items():
            candidate = by_id.get(candidate_id)
            if candidate is None or candidate.target_entity_type != "world_asset":
                continue
            if not candidate.target_entity_id:
                continue
            content = self.session.get(ProjectContent, candidate.target_entity_id)
            if content is None or content.content_type != "world_asset":
                continue
            self._mark_fact_for_review(content, reason)
            touched += 1
            facts.append(
                {
                    "fact_id": content.id,
                    "title": content.title,
                    "candidate_id": candidate.id,
                    "entity_name": candidate.entity_name,
                    "domain": candidate.domain,
                    "reason": reason,
                }
            )
        self.session.flush()
        return {
            "run_id": run_id,
            "affected_facts": facts,
            "affected_candidates": len(affected),
        }

    @staticmethod
    def _mark_fact_for_review(content: ProjectContent, reason: str) -> None:
        """给已写事实打待复核标记，保留原文内容不动。"""
        payload = loads_json(content.data_json, {})
        if not isinstance(payload, dict):
            payload = {}
        payload["review_required"] = True
        payload["affected_reason"] = str(reason)[:400]
        content.data_json = dumps_json(payload)
        content.updated_at = datetime.now()
        # review_required 只影响审阅，不改变事实锁定的语义。

    def _duplicate_groups(self, candidates: list[WorldFactCandidate]) -> list[dict[str, Any]]:
        """按规范化名与别名归并，找出跨模块重复和别名交叉。

        分组键同时来自正名和别名：别名命中另一条候选的正名时，两条候选会
        因为分组有交集而被合并到同一组，从而暴露「A 的别名就是 B」。
        """
        by_id = {item.id: item for item in candidates}
        groups: dict[str, set[str]] = {}
        for candidate in candidates:
            groups.setdefault(candidate.normalized_key, set()).add(candidate.id)
            for alias in self._aliases_of(candidate):
                key = normalize_entity_name(alias)
                if key:
                    groups.setdefault(key, set()).add(candidate.id)

        merged: list[set[str]] = []
        for ids in groups.values():
            hit = [group for group in merged if group & ids]
            if not hit:
                merged.append(set(ids))
                continue
            combined = set(ids)
            for group in hit:
                combined |= group
                merged.remove(group)
            merged.append(combined)

        result: list[dict[str, Any]] = []
        for ids in merged:
            if len(ids) < 2:
                continue
            members = sorted(
                (by_id[item] for item in ids if item in by_id),
                key=lambda row: (row.domain, row.entity_name),
            )
            kinds: list[str] = []
            if len({row.domain for row in members}) > 1:
                kinds.append("cross_domain_name")
            if self._has_alias_cross(members):
                kinds.append("alias_overlap")
            if not kinds:
                # 同域同名理论上已在提取阶段合并，出现在这里说明规范化后重名。
                kinds.append("same_domain_name")
            result.append(
                {
                    "kinds": kinds,
                    "reason": self._duplicate_reason(kinds, members),
                    "candidates": [self._candidate_snapshot(row) for row in members],
                }
            )
        result.sort(key=lambda item: (-len(item["candidates"]), item["candidates"][0]["entity_name"]))
        return result

    def _evidence_overlaps(self, candidates: list[WorldFactCandidate]) -> list[dict[str, Any]]:
        """两条候选引用了同一段原文，可能是同一事实的重复摘录。"""
        by_id = {item.id: item for item in candidates}
        owners: dict[tuple[str, int, int], list[str]] = {}
        quotes: dict[tuple[str, int, int], str] = {}
        for candidate in candidates:
            for anchor in loads_json(candidate.evidence_json, []):
                if not isinstance(anchor, dict):
                    continue
                chunk_id = str(anchor.get("chunk_id") or "")
                if not chunk_id:
                    continue
                key = (
                    chunk_id,
                    int(anchor.get("start_offset") or 0),
                    int(anchor.get("end_offset") or 0),
                )
                owners.setdefault(key, []).append(candidate.id)
                quotes.setdefault(key, str(anchor.get("quote") or ""))

        result: list[dict[str, Any]] = []
        for key, ids in owners.items():
            unique = list(dict.fromkeys(ids))
            if len(unique) < 2:
                continue
            members = [by_id[item] for item in unique if item in by_id]
            if len(members) < 2:
                continue
            result.append(
                {
                    "chunk_id": key[0],
                    "start_offset": key[1],
                    "end_offset": key[2],
                    "quote": quotes.get(key, ""),
                    "reason": f"同一段原文被 {len(members)} 条候选同时引用，请确认是否重复摘录。",
                    "candidates": [self._candidate_snapshot(row) for row in members],
                }
            )
        result.sort(key=lambda item: (item["chunk_id"], item["start_offset"]))
        return result

    def _timeline_entries(self, candidates: list[WorldFactCandidate]) -> list[dict[str, Any]]:
        """把历史事件的相对时间解析成可比较的偏移，供人工核对时序。"""
        entries: list[dict[str, Any]] = []
        for candidate in candidates:
            if candidate.domain != DOMAIN_HISTORICAL_EVENT:
                continue
            payload = loads_json(candidate.payload_json, {})
            attributes = payload.get("attributes") if isinstance(payload, dict) else {}
            raw = str((attributes or {}).get("time_expression") or "")
            entries.append(
                {
                    "candidate_id": candidate.id,
                    "entity_name": candidate.entity_name,
                    "raw": raw,
                    "parsed": parse_relative_time(raw),
                }
            )
        entries.sort(key=lambda item: _timeline_sort_key(item["parsed"]))
        return entries

    @staticmethod
    def _aliases_of(candidate: WorldFactCandidate) -> list[str]:
        payload = loads_json(candidate.payload_json, {})
        if not isinstance(payload, dict):
            return []
        aliases = payload.get("aliases") or []
        return [str(value) for value in aliases if str(value).strip()]

    @staticmethod
    def _has_alias_cross(members: list[WorldFactCandidate]) -> bool:
        """组内是否存在「某条的别名等于另一条的正名」。"""
        names = {row.normalized_key for row in members}
        for row in members:
            for alias in WorldExtractionService._aliases_of(row):
                key = normalize_entity_name(alias)
                if key and key in names and key != row.normalized_key:
                    return True
        return False

    @staticmethod
    def _duplicate_reason(kinds: list[str], members: list[WorldFactCandidate]) -> str:
        names = "、".join(dict.fromkeys(row.entity_name for row in members))
        if "cross_domain_name" in kinds:
            domains = "、".join(dict.fromkeys(domain_label(row.domain) for row in members))
            return f"「{names}」同时出现在{domains}等多个模块，请确认是否为同一实体，避免重复写入。"
        if "alias_overlap" in kinds:
            return f"「{names}」中某条的别名与另一条的正名相同，可能指向同一实体。"
        return f"「{names}」规范化之后重名，请复核是否为同一实体。"

    @staticmethod
    def _candidate_snapshot(candidate: WorldFactCandidate) -> dict[str, Any]:
        payload = loads_json(candidate.payload_json, {})
        if not isinstance(payload, dict):
            payload = {}
        return {
            "id": candidate.id,
            "domain": candidate.domain,
            "domain_label": domain_label(candidate.domain),
            "entity_name": candidate.entity_name,
            "summary": str(payload.get("summary") or ""),
            "aliases": payload.get("aliases") or [],
            "confidence": candidate.confidence,
            "status": candidate.status,
            "origin": candidate.origin,
        }

    # ------------------------------------------------------------------
    # Derivation
    # ------------------------------------------------------------------

    def derive_project(
        self,
        snapshot_id: str,
        *,
        derivation_kind: str,
        title: str = "",
        project_type: str = "novel",
    ) -> dict[str, Any]:
        """从完本来源创建改编/续写/同人派生项目。

        原作正典——已确认的世界事实与角色项目关联——复制进新项目并标记
        ``fact_layer=source_canon``，来源快照始终只读；新项目后续写入的
        事实不带该标记，构成派生层，与原作正典分层存放。
        """
        snapshot = self._require_snapshot(snapshot_id)
        kind = str(derivation_kind or "").strip()
        if kind not in DERIVATION_LABELS:
            raise ValueError("派生模式必须是 adaptation / continuation / fan_work")
        if snapshot.source_status != SourceStatus.COMPLETED.value:
            raise ValueError("只有完本来源支持创建派生项目；连载来源请使用增量同步")

        label = DERIVATION_LABELS[kind]
        creative = CreativeProjectService(self.session, ai_service=self.ai_service)
        project = creative.create_project(
            title=(title or "").strip() or f"{snapshot.title or '未命名小说'}{label}项目",
            project_type=project_type or "novel",
            source_type="novel",
            source_ref={"novel_snapshot_id": snapshot.id, "derivation_kind": kind},
            idea=f"基于《{snapshot.title or '未命名小说'}》的{label}项目（原作正典只读）",
            metadata={
                "novel_snapshot_id": snapshot.id,
                "derivation_kind": kind,
                "source_project_id": snapshot.project_id or "",
            },
        )

        canon_count = self._copy_source_canon(snapshot, project.id)
        character_count = self._copy_character_links(snapshot, project.id)
        entity_count = self._copy_source_entities(snapshot, project.id)
        return {
            "project_id": project.id,
            "derivation_kind": kind,
            "source_snapshot_id": snapshot.id,
            "source_canon_assets": canon_count,
            "characters_linked": character_count,
            "entities_linked": entity_count,
        }

    def _copy_source_canon(
        self, snapshot: NovelSourceSnapshot, project_id: str
    ) -> int:
        """把原作正典复制进派生项目，统一标记 ``fact_layer=source_canon``。"""
        copied = 0
        if snapshot.project_id:
            rows = self.session.exec(
                select(ProjectContent).where(
                    ProjectContent.project_id == snapshot.project_id,
                    ProjectContent.content_type == "world_asset",
                )
            ).all()
            for row in rows:
                payload = loads_json(row.data_json, {})
                # A creative project can accumulate manual facts and facts from
                # other imported sources after this snapshot is applied.  Only
                # facts with this snapshot's provenance are source canon.
                if (
                    not isinstance(payload, dict)
                    or payload.get("source_snapshot_id") != snapshot.id
                ):
                    continue
                if self._canon_copy_exists(project_id, row.id):
                    continue
                data = {
                    **payload,
                    "fact_layer": "source_canon",
                    "source_content_id": row.id,
                }
                self.session.add(
                    ProjectContent(
                        project_id=project_id,
                        content_type="world_asset",
                        title=row.title,
                        data_json=dumps_json(data),
                        text_content=row.text_content,
                        version=1,
                        is_locked=True,
                    )
                )
                copied += 1
            self.session.flush()
            return copied

        # 没有原项目时，从该来源已接受的候选直接落原作正典。
        accepted = self.session.exec(
            select(WorldFactCandidate).where(
                WorldFactCandidate.snapshot_id == snapshot.id,
                WorldFactCandidate.status == CandidateStatus.ACCEPTED.value,
            )
        ).all()
        for candidate in accepted:
            if candidate.domain == "character":
                continue
            asset = self._write_world_asset(candidate, project_id)
            if not asset.get("created", False):
                continue
            content = self.session.get(ProjectContent, asset["id"])
            if content is not None:
                payload = loads_json(content.data_json, {})
                if isinstance(payload, dict):
                    payload["fact_layer"] = "source_canon"
                    content.data_json = dumps_json(payload)
                    self.session.add(content)
                copied += 1
        self.session.flush()
        return copied

    def _canon_copy_exists(self, project_id: str, source_content_id: str) -> bool:
        rows = self.session.exec(
            select(ProjectContent).where(
                ProjectContent.project_id == project_id,
                ProjectContent.content_type == "world_asset",
            )
        ).all()
        for row in rows:
            payload = loads_json(row.data_json, {})
            if isinstance(payload, dict) and payload.get("source_content_id") == source_content_id:
                return True
        return False

    def _copy_source_entities(
        self, snapshot: NovelSourceSnapshot, project_id: str
    ) -> int:
        """把原项目的类型化实体与关系复制进派生项目，标记 ``source_canon``。"""
        if not snapshot.project_id:
            return 0
        entities = self.session.exec(
            select(WorldEntity).where(
                WorldEntity.project_id == snapshot.project_id,
                WorldEntity.snapshot_id == snapshot.id,
            )
        ).all()
        if not entities:
            return 0

        id_map: dict[str, str] = {}
        for entity in entities:
            copied = WorldEntity(
                project_id=project_id,
                snapshot_id=snapshot.id,
                domain=entity.domain,
                entity_type=entity.entity_type,
                name=entity.name,
                normalized_key=entity.normalized_key,
                summary=entity.summary,
                attributes_json=entity.attributes_json,
                evidence_json=entity.evidence_json,
                fact_layer="source_canon",
                source_candidate_id=entity.source_candidate_id,
                is_locked=True,
            )
            self.session.add(copied)
            self.session.flush()
            id_map[entity.id] = copied.id

        relations = self.session.exec(
            select(WorldEntityRelation).where(
                WorldEntityRelation.project_id == snapshot.project_id
            )
        ).all()
        for relation in relations:
            source_id = id_map.get(relation.source_entity_id)
            target_id = id_map.get(relation.target_entity_id)
            if not source_id or not target_id:
                continue
            self.session.add(
                WorldEntityRelation(
                    project_id=project_id,
                    source_entity_id=source_id,
                    target_entity_id=target_id,
                    relation_type=relation.relation_type,
                    note=relation.note,
                    evidence_json=relation.evidence_json,
                    is_directed=relation.is_directed,
                )
            )
        return len(entities)

    def _copy_character_links(
        self, snapshot: NovelSourceSnapshot, project_id: str
    ) -> int:
        """只复制由该来源快照确认的角色项目关联。"""
        if not snapshot.project_id:
            return 0
        source_character_ids = {
            str(candidate.target_entity_id)
            for candidate in self.session.exec(
                select(WorldFactCandidate).where(
                    WorldFactCandidate.snapshot_id == snapshot.id,
                    WorldFactCandidate.domain == "character",
                    WorldFactCandidate.status == CandidateStatus.ACCEPTED.value,
                    WorldFactCandidate.target_entity_type == "character",
                )
            ).all()
            if candidate.target_entity_id
        }
        if not source_character_ids:
            return 0
        existing = {
            link.character_id
            for link in self.session.exec(
                select(CharacterStoryLink).where(CharacterStoryLink.story_id == project_id)
            ).all()
        }
        copied = 0
        for link in self.session.exec(
            select(CharacterStoryLink).where(
                CharacterStoryLink.story_id == snapshot.project_id
            )
        ).all():
            if link.character_id not in source_character_ids or link.character_id in existing:
                continue
            if self.session.get(Character, link.character_id) is None:
                continue
            self.session.add(
                CharacterStoryLink(
                    story_id=project_id,
                    character_id=link.character_id,
                    aliases_json=link.aliases_json,
                    evidence_json=link.evidence_json,
                    extraction_notes=link.extraction_notes,
                )
            )
            copied += 1
        self.session.flush()
        return copied

    def _ensure_project_source_sample(
        self,
        creative: CreativeProjectService,
        project_id: str,
        snapshot_id: str,
    ) -> None:
        """保证角色写入通道能读到来源正文。

        既有角色提取会校验证据是否出现在项目来源文本里。世界项目通常由来源
        快照驱动，但用户也可以指定一个没有正文的项目；此时补一份来源采样，
        否则复用通道会因为没有来源文本直接失败。
        """
        project = creative.get_project(project_id)
        if not project:
            raise ValueError("目标创作项目不存在")
        try:
            existing = creative._project_character_source_text(project)
        except Exception:  # noqa: BLE001 - 读取失败按“没有来源”处理
            existing = ""
        if existing.strip():
            return
        source_text = self.sources.load_source_text(snapshot_id)[:CHARACTER_SOURCE_MAX_CHARS]
        metadata = loads_json(project.metadata_json, {})
        if not isinstance(metadata, dict):
            metadata = {}
        metadata["source_sample"] = source_text
        metadata["novel_snapshot_id"] = snapshot_id
        project.metadata_json = dumps_json(metadata)
        project.updated_at = datetime.now()
        self.session.add(project)
        self.session.flush()

    def _link_characters(self, candidates: list[WorldFactCandidate], project_id: str) -> None:
        """把候选回指到角色库实体，并把别名与逐字证据写入项目关联。

        角色写入复用了既有提取通道，但那条通道按项目来源文本过滤证据；
        这里用候选自身已校验过的锚点回写，保证证据不会因为项目缺少正文而丢失。
        """
        links = self.session.exec(
            select(CharacterStoryLink).where(CharacterStoryLink.story_id == project_id)
        ).all()
        name_to_character: dict[str, Character] = {}
        for link in links:
            character = self.session.get(Character, link.character_id)
            if character:
                name_to_character[str(character.name).strip()] = character
        for candidate in candidates:
            character = name_to_character.get(str(candidate.entity_name).strip())
            if character is None:
                normalized = candidate.normalized_key
                character = next(
                    (
                        item
                        for name, item in name_to_character.items()
                        if normalize_entity_name(name) == normalized
                    ),
                    None,
                )
            if character is None:
                continue
            payload = loads_json(candidate.payload_json, {})
            evidence = [
                str(item.get("quote") or "")
                for item in loads_json(candidate.evidence_json, [])
                if isinstance(item, dict) and str(item.get("quote") or "").strip()
            ]
            link = next(
                (
                    item
                    for item in links
                    if item.character_id == character.id
                ),
                None,
            )
            if link is not None:
                link.aliases_json = dumps_json(payload.get("aliases") or [])
                link.evidence_json = dumps_json(evidence)
                link.extraction_notes = str(payload.get("summary") or "")
                self.session.add(link)
            candidate.target_entity_type = "character"
            candidate.target_entity_id = character.id
            candidate.updated_at = datetime.now()
            self.session.add(candidate)
        self.session.flush()

    def _write_world_asset(self, candidate: WorldFactCandidate, project_id: str) -> dict[str, Any]:
        existing = self._find_existing_world_asset(candidate, project_id)
        if existing is not None:
            candidate.target_entity_type = "world_asset"
            candidate.target_entity_id = existing.id
            candidate.updated_at = datetime.now()
            self.session.add(candidate)
            return {
                "id": existing.id,
                "title": existing.title,
                "domain": candidate.domain,
                "created": False,
            }

        payload = loads_json(candidate.payload_json, {})
        evidence = loads_json(candidate.evidence_json, [])
        spec = get_domain(candidate.domain)
        data = {
            "asset_kind": "novel_source_fact",
            "domain": candidate.domain,
            "domain_label": spec.label if spec else candidate.domain,
            "entity_type": spec.entity_type if spec else candidate.domain,
            "entity_name": candidate.entity_name,
            "summary": str(payload.get("summary") or ""),
            "aliases": payload.get("aliases") or [],
            "attributes": payload.get("attributes") or {},
            "evidence": evidence,
            "confidence": candidate.confidence,
            "origin": candidate.origin,
            "source_candidate_id": candidate.id,
            "source_snapshot_id": candidate.snapshot_id,
            "source_run_id": candidate.run_id,
        }
        content = ProjectContent(
            project_id=project_id,
            content_type="world_asset",
            title=candidate.entity_name or (spec.label if spec else candidate.domain),
            data_json=dumps_json(data),
            text_content=str(payload.get("summary") or ""),
            version=1,
            is_locked=True,
        )
        self.session.add(content)
        self.session.flush()
        self.session.refresh(content)
        candidate.target_entity_type = "world_asset"
        candidate.target_entity_id = content.id
        candidate.updated_at = datetime.now()
        self.session.add(candidate)
        return {"id": content.id, "title": content.title, "domain": candidate.domain, "created": True}

    def _find_existing_world_asset(
        self,
        candidate: WorldFactCandidate,
        project_id: str,
    ) -> ProjectContent | None:
        """Find a prior write for this candidate within the target project."""
        if candidate.target_entity_type == "world_asset" and candidate.target_entity_id:
            linked = self.session.get(ProjectContent, candidate.target_entity_id)
            if linked and linked.project_id == project_id and linked.content_type == "world_asset":
                return linked

        rows = self.session.exec(
            select(ProjectContent).where(
                ProjectContent.project_id == project_id,
                ProjectContent.content_type == "world_asset",
            )
        ).all()
        for row in rows:
            payload = loads_json(row.data_json, {})
            if isinstance(payload, dict) and payload.get("source_candidate_id") == candidate.id:
                return row
        return None

    def _upsert_world_entity(self, candidate: WorldFactCandidate, project_id: str) -> str:
        """把候选物化为类型化独立实体（幂等 upsert，返回实体 id）。"""
        spec = get_domain(candidate.domain)
        entity_type = spec.entity_type if spec else candidate.domain
        normalized_key = normalize_entity_name(candidate.entity_name)
        existing = self.session.exec(
            select(WorldEntity).where(
                WorldEntity.project_id == project_id,
                WorldEntity.entity_type == entity_type,
                WorldEntity.normalized_key == normalized_key,
            )
        ).first()
        payload = loads_json(candidate.payload_json, {})
        evidence = loads_json(candidate.evidence_json, [])
        if existing is not None:
            existing.summary = str(payload.get("summary") or "") or existing.summary
            existing.attributes_json = dumps_json(payload.get("attributes") or {})
            existing.evidence_json = dumps_json(evidence)
            existing.source_candidate_id = candidate.id
            existing.snapshot_id = existing.snapshot_id or candidate.snapshot_id
            existing.updated_at = datetime.now()
            self.session.add(existing)
            return existing.id

        entity = WorldEntity(
            project_id=project_id,
            snapshot_id=candidate.snapshot_id,
            domain=candidate.domain,
            entity_type=entity_type,
            name=candidate.entity_name,
            normalized_key=normalized_key,
            summary=str(payload.get("summary") or ""),
            attributes_json=dumps_json(payload.get("attributes") or {}),
            evidence_json=dumps_json(evidence),
            fact_layer="project",
            source_candidate_id=candidate.id,
            is_locked=True,
        )
        self.session.add(entity)
        self.session.flush()
        self.session.refresh(entity)
        return entity.id

    def _materialize_relations(
        self,
        accepted: list[WorldFactCandidate],
        project_id: str,
        entity_ids_by_candidate: dict[str, str],
    ) -> int:
        """把候选 payload 里显式声明的复杂实体关系物化为类型化关系。

        只物化非角色实体间关系；解析不到目标实体（名字对不上）时静默跳过，
        不阻塞写入。返回写入的关系条数。
        """
        entities = self.session.exec(
            select(WorldEntity).where(WorldEntity.project_id == project_id)
        ).all()
        index: dict[tuple[str, str], str] = {}
        for entity in entities:
            key = normalize_entity_name(entity.name)
            index[(entity.entity_type, key)] = entity.id
            # 顺带用 domain 建索引，兼容名字落在不同 domain 命名下的情况。
            index[(entity.domain, key)] = entity.id

        written = 0
        seen: set[tuple[str, str, str]] = set()
        for candidate in accepted:
            if candidate.domain == "character":
                continue
            source_id = entity_ids_by_candidate.get(candidate.id)
            if not source_id:
                continue
            payload = loads_json(candidate.payload_json, {})
            attributes = payload.get("attributes")
            if not isinstance(attributes, dict):
                continue
            for field_name, relation_type, target_type in RELATION_HINTS.get(
                candidate.domain, ()
            ):
                names = _as_name_list(attributes.get(field_name))
                for name in names:
                    key = normalize_entity_name(name)
                    if not key:
                        continue
                    target_id = index.get((target_type, key)) or index.get(
                        (candidate.domain, key)
                    )
                    if not target_id or target_id == source_id:
                        continue
                    dedupe = (source_id, target_id, relation_type)
                    if dedupe in seen:
                        continue
                    seen.add(dedupe)
                    relation = WorldEntityRelation(
                        project_id=project_id,
                        source_entity_id=source_id,
                        target_entity_id=target_id,
                        relation_type=relation_type,
                        note=name,
                        evidence_json=candidate.evidence_json or "[]",
                        is_directed=False,
                    )
                    self.session.add(relation)
                    written += 1
        return written

    def list_world_entities(
        self,
        project_id: str,
        *,
        domain: str | None = None,
        entity_type: str | None = None,
        limit: int = 200,
    ) -> list[WorldEntity]:
        """列出项目的类型化世界实体（可按域或实体类型过滤）。"""
        statement = select(WorldEntity).where(WorldEntity.project_id == project_id)
        if domain:
            statement = statement.where(WorldEntity.domain == domain)
        if entity_type:
            statement = statement.where(WorldEntity.entity_type == entity_type)
        statement = statement.order_by(WorldEntity.entity_type, WorldEntity.name).limit(
            max(1, min(int(limit or 200), 1000))
        )
        return list(self.session.exec(statement).all())

    def list_world_entity_relations(
        self, project_id: str, *, limit: int = 500
    ) -> list[WorldEntityRelation]:
        """列出项目的类型化实体关系（用于关系图谱）。"""
        statement = (
            select(WorldEntityRelation)
            .where(WorldEntityRelation.project_id == project_id)
            .order_by(WorldEntityRelation.relation_type, WorldEntityRelation.created_at)
            .limit(max(1, min(int(limit or 500), 2000)))
        )
        return list(self.session.exec(statement).all())

    def _character_card(self, candidate: WorldFactCandidate) -> dict[str, Any]:
        payload = loads_json(candidate.payload_json, {})
        attributes = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {}
        summary = str(payload.get("summary") or "")
        traits = attributes.get("traits")
        card = {
            "name": candidate.entity_name,
            "aliases": payload.get("aliases") or [],
            "role": str(attributes.get("role") or ""),
            "background": summary,
            "personality": "、".join(traits) if isinstance(traits, list) else str(traits or ""),
            "identity": {"summary": summary, "affiliation": str(attributes.get("affiliation") or "")},
            "motivation": {},
            "speech": {},
            "behavior": {},
            "arc": {},
            "evidence": [
                str(item.get("quote") or "")
                for item in loads_json(candidate.evidence_json, [])
                if isinstance(item, dict) and str(item.get("quote") or "").strip()
            ],
            "extraction_notes": summary,
            "field_sources": {
                "origin": candidate.origin,
                "snapshot_id": candidate.snapshot_id,
                "run_id": candidate.run_id,
                "candidate_id": candidate.id,
            },
        }
        return card

    def _create_project_for_snapshot(self, snapshot_id: str) -> str:
        snapshot = self._snapshot(snapshot_id)
        creative = CreativeProjectService(self.session, ai_service=self.ai_service)
        project = creative.create_project(
            title=f"{snapshot.title or '未命名小说'} 世界项目",
            project_type="novel",
            source_type="novel",
            source_ref={"novel_snapshot_id": snapshot.id},
            idea=f"基于来源《{snapshot.title or '未命名小说'}》建立世界设定",
            metadata={"novel_snapshot_id": snapshot.id},
        )
        snapshot.project_id = project.id
        snapshot.updated_at = datetime.now()
        self.session.add(snapshot)
        self.session.commit()
        return project.id

    def _mark_domain_state(self, run: WorldExtractionRun, state: str) -> None:
        domains = loads_json(run.domains_json, [])
        if not isinstance(domains, list):
            return
        for item in domains:
            if isinstance(item, dict) and item.get("run_state") in {
                DomainRunState.DRAFT.value,
                DomainRunState.EXTRACTING.value,
            }:
                item["run_state"] = state
        run.domains_json = dumps_json(domains)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _snapshot(self, snapshot_id: str) -> NovelSourceSnapshot:
        snapshot = self.session.get(NovelSourceSnapshot, snapshot_id)
        if not snapshot:
            raise ValueError("来源快照不存在")
        return snapshot

    def _require_snapshot(self, snapshot_id: str) -> NovelSourceSnapshot:
        return self._snapshot(snapshot_id)

    def _finish_run(self, run: WorldExtractionRun, *, error: str = "") -> None:
        run.updated_at = datetime.now()
        diagnostics = loads_json(run.diagnostics_json, {})
        if not isinstance(diagnostics, dict):
            diagnostics = {}
        if error:
            diagnostics["error"] = error[:1000]
        run.diagnostics_json = dumps_json(diagnostics)
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)

    @staticmethod
    def _initial_plan_state(domain: str, domain_plan: list[dict[str, Any]] | None) -> dict[str, Any]:
        spec = get_domain(domain)
        base = {
            "domain": domain,
            "label": spec.label if spec else domain,
            "detection": DETECTION_UNCERTAIN,
            "reason": "",
            "signals": [],
            "estimated_cost": "low",
            "run_state": DomainRunState.ENABLED.value,
            "items": 0,
        }
        for item in domain_plan or []:
            if isinstance(item, dict) and str(item.get("domain") or "") == domain:
                base.update(
                    {
                        "detection": str(item.get("status") or DETECTION_UNCERTAIN),
                        "reason": str(item.get("reason") or "")[:400],
                        "signals": item.get("signals") or [],
                        "estimated_cost": str(item.get("estimated_cost") or "low"),
                    }
                )
                break
        return base

    async def _generate_json(
        self,
        *,
        prompt: str,
        system_prompt: str,
        schema_model: type[TModel],
        provider: str | None,
        model: str | None,
        max_tokens: int,
    ) -> dict[str, Any]:
        response = await self.ai_service.chat(
            messages=[
                LLMMessage(role="system", content=system_prompt),
                LLMMessage(role="user", content=prompt),
            ],
            provider=provider,
            model=model,
            temperature=0.2,
            max_tokens=max_tokens,
        )
        if not _response_success(response):
            raise ValueError(_response_error(response) or "LLM 生成失败")
        raw = _response_content(response)
        data = _extract_json_object(raw)
        try:
            return schema_model.model_validate(data).model_dump()
        except ValidationError as exc:
            raise ValueError(f"模型输出不符合契约：{exc}") from exc

    @staticmethod
    def _detection_prompt(snapshot: NovelSourceSnapshot, sample: str, skip: set[str]) -> str:
        domains = [
            f"{spec.key}（{spec.label}）" for spec in _all_specs() if spec.key not in skip
        ]
        return (
            f"作品：《{snapshot.title or '未命名'}》\n"
            f"作者：{snapshot.author or '未知'}\n\n"
            "下面是按章节顺序摘出的正文片段。请对下列每个模块**独立**判断："
            "这部作品里是否存在足够可提取的内容。\n"
            f"模块：{'、'.join(domains)}\n\n"
            "只输出 JSON：\n"
            '{"domains":[{"domain":"character","status":"detected|not_detected|uncertain",'
            '"reason":"一句话理由","signals":["原文中出现过的词或短语"],'
            '"estimated_cost":"low|medium|high"}]}\n\n'
            "规则：\n"
            "1. 只依据文本信号判断，不要根据题材标签猜测；\n"
            "2. 原文有明显且可引用的内容才判 detected；完全没有痕迹判 not_detected；"
            "痕迹少或模糊判 uncertain；\n"
            "3. signals 必须是原文里出现过的词或短语，每个模块最多 3 条；\n"
            "4. estimated_cost 按该模块内容体量估计。\n\n"
            f"正文片段：\n{sample}"
        )

    @staticmethod
    def _extraction_prompt(
        snapshot: NovelSourceSnapshot,
        domain: str,
        label: str,
        hint: str,
        attributes: tuple[str, ...],
        batch: list[NovelTextChunk],
    ) -> str:
        body = "\n\n".join(f"[块 {chunk.ordinal}] {chunk.content}" for chunk in batch)
        return (
            f"作品：《{snapshot.title or '未命名'}》\n"
            f"模块：{label}（{domain}）\n"
            f"收录范围：{hint}\n\n"
            "下面是从原文按章节顺序摘出的片段。只从中提取本模块的内容，"
            "不要生成原文没有的设定。\n\n"
            f"{body}\n\n"
            "只输出 JSON：\n"
            '{"items":[{"name":"原文最常用称呼","aliases":["别名/称谓"],'
            '"summary":"不超过 80 字的客观描述","attributes":{...},'
            '"quotes":["逐字复制的原文片段"],"confidence":0.8,"uncertain":false}]}\n\n'
            f"attributes 建议字段：{'、'.join(attributes) or '按需填写'}\n\n"
            "规则：\n"
            "1. name 用原文最常用称呼，aliases 只填原文出现过的称谓；\n"
            "2. quotes 必须逐字复制原文片段，每条 8-80 字，每个条目 1-3 条，"
            "不能翻译、拼接或改写；\n"
            "3. 无法确定或属于推断时把 uncertain 设为 true 并调低 confidence；\n"
            "4. 只输出本模块真正存在且影响理解的条目，没有就返回空数组。\n"
        )


def _all_specs():
    from app.services.novel_source.contracts import DOMAIN_SPECS

    return DOMAIN_SPECS


def _clamp_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, number))


_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

#: 相对时间换算到「天」，只为排序服务，不声称精确历法。
_TIME_UNIT_DAYS = {"year": 365, "month": 30, "day": 1}

_TIME_PATTERN = re.compile(r"([0-9零一二两三四五六七八九十百千]+)\s*(年|载|岁|月|日|天)")


def _parse_cn_number(text: str) -> int | None:
    """把「三」「十二」「二十」这类中文数字转成整数，无法解析时返回 None。"""
    raw = str(text or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    if "十" in raw:
        left, _, right = raw.partition("十")
        tens = _CN_DIGITS.get(left, 1) if left else 1
        ones = _CN_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    total = 0
    for char in raw:
        if char not in _CN_DIGITS:
            return None
        total = total * 10 + _CN_DIGITS[char]
    return total or None


def parse_relative_time(expression: str) -> dict[str, Any]:
    """把「三年前」「十年后」这类相对时间解析成可比较的偏移。

    只做确定性的模式匹配。无法解析时返回 ``unknown`` 由人工核对，
    绝不猜测具体年份，也不把「开篇」「很久以前」这类模糊表述当精确时间。
    """
    raw = str(expression or "").strip()
    if not raw:
        return {"kind": "unknown", "raw": raw, "note": "未填写时间表述"}
    match = _TIME_PATTERN.search(raw)
    if not match:
        return {"kind": "unknown", "raw": raw, "note": "未识别到时间单位"}
    amount = _parse_cn_number(match.group(1))
    unit_char = match.group(2)
    unit = (
        "year"
        if unit_char in {"年", "载", "岁"}
        else "month"
        if unit_char == "月"
        else "day"
    )
    if amount is None:
        return {"kind": "unknown", "raw": raw, "unit": unit, "note": "数量无法解析"}
    if any(token in raw for token in ("前", "之前", "以前")):
        direction = -1
    elif any(token in raw for token in ("后", "之后", "以后")):
        direction = 1
    else:
        direction = 0
    return {
        "kind": "relative",
        "raw": raw,
        "amount": amount,
        "unit": unit,
        "direction": direction,
        "offset_days": direction * amount * _TIME_UNIT_DAYS[unit],
    }


def _timeline_sort_key(parsed: dict[str, Any]) -> tuple[int, int, str]:
    """相对时间按偏移升序（越早越前），无法解析的统一排在最后。"""
    if parsed.get("kind") == "relative":
        return (0, int(parsed.get("offset_days") or 0), str(parsed.get("raw") or ""))
    return (1, 0, str(parsed.get("raw") or ""))


def _response_success(response: Any) -> bool:
    if isinstance(response, dict):
        return bool(response.get("success", True))
    return bool(getattr(response, "success", True))


def _response_content(response: Any) -> str:
    if isinstance(response, dict):
        return str(response.get("content") or "")
    return str(getattr(response, "content", "") or "")


def _response_error(response: Any) -> str:
    if isinstance(response, dict):
        return str(response.get("error") or response.get("message") or "")
    return str(getattr(response, "error", "") or "")


def _extract_json_object(raw: str) -> dict[str, Any]:
    """从模型输出里取出第一个完整 JSON 对象。

    容忍代码块围栏和前后说明文字；不做语义补全，解析失败直接抛错，
    由调用方记录为域失败。
    """
    text = str(raw or "").strip()
    if not text:
        raise ValueError("模型返回为空")
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("{")
    if start < 0:
        raise ValueError("模型输出中没有 JSON 对象")
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : index + 1])
    raise ValueError("模型输出的 JSON 对象未闭合")
