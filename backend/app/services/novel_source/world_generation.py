"""渐进式世界构建：AI 在平台梯子上生成内容（结构上只有提议权）。

与提取链路（``extraction.py``）并列且**语义隔离**：

- 提取：有原文 → 逐字证据校验 → 无证据丢弃 → ``origin=original``
- 生成：无原文 → **不产出证据、禁止伪造** → ``origin=ai_draft`` → 同样需确认后 apply

梯子原则（见 change proposal）：

- I1 平台持有梯子：域与属性 schema 由平台解析（``WorldDomainService.resolve_specs``）
- I2 AI 只能踩梯子上加：填值可以；想加结构必须走 ``suggested_fields`` / ``suggested_domains``
  提议，落库为 ``source=ai_suggested`` 且默认**不启用**，需用户确认（R7）
- I3 平台永远能解析：候选落在既有 ``WorldFactCandidate``，结构落在既有定义表
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import or_
from sqlmodel import Session, select

from app.db.models.novel_source import (
    CandidateOrigin,
    CandidateStatus,
    DomainDefinitionSource,
    ExtractionRunKind,
    ExtractionRunMode,
    ExtractionRunStatus,
    WorldBuildingTemplate,
    WorldDomainDefinition,
    WorldEntity,
    WorldExtractionRun,
    WorldFactCandidate,
)
from app.services.ai.service import get_ai_service
from app.services.ai.types import LLMMessage
from app.services.creative_project.service import dumps_json, loads_json
from app.services.novel_source.world_domains import WorldDomainService

DEFAULT_EXPAND_DOMAIN_PROMPT = (
    "按层次策略细化「{domain}」这个设定模块。\n\n"
    "层次：{layers}\n"
    "已有条目：{known}\n"
    "补充要求：{hint}\n\n"
    "要求：\n"
    "1. 只补充尚未出现、且对该世界观有实际作用的条目，不要重复已有条目。\n"
    "2. 每个条目给出名称与字段值（字段按该模块的属性契约），名称用原文用词。\n"
    "3. 严格 JSON，符合给定 schema。\n"
    "4. 若现有字段无法表达关键设定，用 suggested_fields 提出新字段名与原因。"
)

GENERATION_SYSTEM_PROMPT = (
    "你是世界观设定助手。只输出严格 JSON：不编造原文引用、不输出解释性文字、"
    "不改动已知字段的值。结构变更只能用 suggested_fields / suggested_domains 提议。"
)

DEFAULT_EXPAND_ENTITY_PROMPT = (
    "为世界观实体补充设定字段。\n\n"
    "实体：{entity}\n"
    "所属模块：{domain}\n"
    "层次：{layers}\n"
    "已知信息：{known}\n"
    "待补充字段：{fields}\n\n"
    "要求：\n"
    "1. 只输出待补充字段的值；无法确定时留空字符串，不要编造。\n"
    "2. 严格 JSON，符合给定 schema 的字段结构。\n"
    "3. 不要输出证据、注释或解释性文字。\n"
    "4. 若现有字段无法表达该实体的关键设定，用 suggested_fields 提出新字段名与原因，"
    "不要塞进已有字段，也不要改动已有字段的值。"
)

TEMPLATE_DRAFT_SYSTEM_PROMPT = (
    "你是世界构建模板设计师。模板 = 层次策略 + 每档提示词，服务于 AI 渐进式世界构建。"
    "只输出严格 JSON，不编造、不解释。"
)

DEFAULT_TEMPLATE_DRAFT_PROMPT = (
    "按补充要求起草一份「世界构建模板」。\n\n"
    "该项目当前启用的设定模块：\n{domains}"
    "{focus}"
    "补充要求：{hint}\n\n"
    "模板字段说明：\n"
    "1. layers：层次策略，名称与层数由项目决定（例如「世界→大陆→国家→地点」或"
    "「能量来源→修炼流派→境界」），2~6 层、每层用名词短语。\n"
    "2. prompts.expand_domain：按层次细化某个模块的提示词模板，支持占位"
    " {domain}/{layers}/{known}/{hint}。\n"
    "3. prompts.expand_entity：给单个实体补充字段的提示词模板，支持占位"
    " {entity}/{domain}/{layers}/{known}/{fields}。\n\n"
    "要求：\n"
    "1. name 用简短、贴合该项目世界观风格的名字，不出现「模板」二字。\n"
    "2. 提示词必须要求模型只输出严格 JSON（items / suggested_fields / "
    "suggested_domains），不得编造原文证据。\n"
    "3. 只输出严格 JSON，形如："
    '{"name":"...","layers":[...],"prompts":{"expand_domain":"...","expand_entity":"..."},'
    '"note":"一句话设计说明"}'
)


def _dump_list(values: list[str]) -> str:
    """把字符串列表落成 JSON（与 world_domains 的同名 helper 用途一致）。"""
    return json.dumps(
        [str(item).strip() for item in values if str(item).strip()], ensure_ascii=False
    )


class GeneratedEntityItem(BaseModel):
    entity: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)


class SuggestedField(BaseModel):
    domain: str = ""
    field: str = ""
    reason: str = ""


class SuggestedDomain(BaseModel):
    key: str = ""
    label: str = ""
    attributes: list[str] = Field(default_factory=list)
    reason: str = ""


class WorldGenerationSchema(BaseModel):
    """生成动作的产出契约：**内容**与**结构建议**在响应里就分开。"""

    items: list[GeneratedEntityItem] = Field(default_factory=list)
    suggested_fields: list[SuggestedField] = Field(default_factory=list)
    suggested_domains: list[SuggestedDomain] = Field(default_factory=list)


class DraftTemplateSchema(BaseModel):
    """模板起草产出契约：只回显草案、不落库，用户确认后走 upsert 保存。"""

    name: str = ""
    layers: list[str] = Field(default_factory=list)
    prompts: dict[str, Any] = Field(default_factory=dict)
    note: str = ""


def _extract_json_object(text: str) -> dict[str, Any]:
    """从模型输出里取出第一个 JSON 对象（容忍前后包裹的说明文字）。"""
    raw = str(text or "").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        parsed = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class WorldGenerationService:
    """三档生成动作的服务层：draft_world / expand_domain / expand_entity。

    本轮先落地 ``expand_entity``（最小闭环），另两档沿用同一套契约与流水线。
    真人与智能体共用本服务（双使用者约束）。
    """

    def __init__(self, session: Session, ai_service: Any | None = None):
        self.session = session
        # AI 服务按需获取：模板管理与提示词组装不需要模型，
        # 避免在未初始化 AI 服务时连这些只读操作都用不了。
        self.ai_service = ai_service
        self.domains = WorldDomainService(session)

    def _ensure_ai(self) -> Any:
        if self.ai_service is None:
            self.ai_service = get_ai_service()
        return self.ai_service

    # ------------------------------------------------------------------
    # 提示词
    # ------------------------------------------------------------------
    def build_entity_prompt(
        self,
        entity: WorldEntity,
        spec: Any,
        fields: list[str],
        *,
        template: WorldBuildingTemplate | None = None,
        prompt_override: str = "",
    ) -> str:
        known = loads_json(entity.attributes_json, {})
        if not isinstance(known, dict):
            known = {}
        known_text = "；".join(f"{k}={v}" for k, v in known.items() if v) or "（暂无）"
        layers: list[str] = []
        if template:
            raw_layers = loads_json(template.layers_json, [])
            if isinstance(raw_layers, list):
                layers = [str(item) for item in raw_layers]

        prompt = str(prompt_override or "").strip()
        if not prompt and template:
            prompts = loads_json(template.prompts_json, {})
            if isinstance(prompts, dict):
                prompt = str(prompts.get("expand_entity") or "").strip()
        if not prompt:
            prompt = DEFAULT_EXPAND_ENTITY_PROMPT

        return (
            prompt.replace("{entity}", entity.name or "")
            .replace("{domain}", (spec.label if spec else entity.domain) or "")
            .replace("{fields}", "、".join(fields))
            .replace("{known}", known_text)
            .replace("{layers}", " → ".join(layers) if layers else "（未定义层次）")
        )

    def preview_entity_expansion(
        self,
        project_id: str,
        entity_id: str,
        *,
        fields: list[str],
        template_id: str | None = None,
        prompt_override: str = "",
    ) -> dict[str, Any]:
        """只组装提示词，**不调用模型**、不消耗配额（R4）。"""
        entity, spec, picked, template = self._prepare(
            project_id, entity_id, fields=fields, template_id=template_id
        )
        return {
            "entity_id": entity.id,
            "entity": entity.name,
            "domain": entity.domain,
            "fields": picked,
            "prompt": self.build_entity_prompt(
                entity, spec, picked, template=template, prompt_override=prompt_override
            ),
        }

    # ------------------------------------------------------------------
    # expand_entity：按域 schema 补齐勾选的字段
    # ------------------------------------------------------------------
    async def expand_entity(
        self,
        project_id: str,
        entity_id: str,
        *,
        fields: list[str],
        template_id: str | None = None,
        prompt_override: str = "",
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        entity, spec, picked, template = self._prepare(
            project_id, entity_id, fields=fields, template_id=template_id
        )
        prompt = self.build_entity_prompt(
            entity, spec, picked, template=template, prompt_override=prompt_override
        )

        run = WorldExtractionRun(
            snapshot_id=None,
            project_id=project_id,
            kind=ExtractionRunKind.GENERATE.value,
            mode=ExtractionRunMode.FULL.value,
            status=ExtractionRunStatus.RUNNING.value,
            pipeline_version="v1",
            provider=provider or "",
            model=model or "",
        )
        self.session.add(run)
        self.session.flush()

        try:
            data = await self._generate(prompt, provider=provider, model=model)
        except Exception as exc:  # noqa: BLE001 - 运行需落失败态
            run.status = ExtractionRunStatus.FAILED.value
            run.diagnostics_json = dumps_json({"error": str(exc)[:500]})
            run.updated_at = datetime.now()
            self.session.add(run)
            self.session.commit()
            raise

        values: dict[str, Any] = {}
        for item in data.get("items") or []:
            for key, value in (item.get("attributes") or {}).items():
                # 只接受勾选且在属性契约内的字段（I2：schema 之外的只能提议）
                if key in picked and str(value).strip():
                    values[key] = str(value).strip()[:500]
        if not values:
            run.status = ExtractionRunStatus.FAILED.value
            run.diagnostics_json = dumps_json({"error": "模型没有产出任何可用字段值"})
            run.updated_at = datetime.now()
            self.session.add(run)
            self.session.commit()
            raise ValueError("模型没有产出任何可用字段值")

        candidate = WorldFactCandidate(
            run_id=run.id,
            snapshot_id=None,
            project_id=project_id,
            domain=entity.domain,
            entity_name=entity.name,
            normalized_key=entity.normalized_key,
            fingerprint=f"gen:{project_id}:{entity.id}",
            payload_json=dumps_json(
                {
                    "name": entity.name,
                    "entity_id": entity.id,
                    "attributes": values,
                    "action": "expand_entity",
                }
            ),
            # 生成链路没有原文可引用：留空，绝不伪造证据（R6）。
            evidence_json="[]",
            origin=CandidateOrigin.AI_DRAFT.value,
            status=CandidateStatus.PENDING.value,
            last_run_id=run.id,
        )
        self.session.add(candidate)

        suggested_fields = [
            {
                "domain": str(item.get("domain") or "")[:60],
                "field": str(item.get("field") or "")[:60],
                "reason": str(item.get("reason") or "")[:300],
            }
            for item in (data.get("suggested_fields") or [])
            if str(item.get("field") or "").strip()
        ]
        suggested_domains = self._persist_suggested_domains(
            project_id, data.get("suggested_domains") or []
        )

        run.status = ExtractionRunStatus.SUCCESS.value
        run.trace_json = dumps_json(
            [{"action": "expand_entity", "entity": entity.name, "fields": picked}]
        )
        run.diagnostics_json = dumps_json(
            {
                "suggested_fields": suggested_fields,
                "suggested_domains": suggested_domains,
                "entity_id": entity.id,
            }
        )
        run.updated_at = datetime.now()
        self.session.add(run)
        self.session.commit()
        self.session.refresh(candidate)

        return {
            "run_id": run.id,
            "candidate_id": candidate.id,
            "entity_id": entity.id,
            "entity": entity.name,
            "domain": entity.domain,
            "fields": picked,
            "values": values,
            "origin": CandidateOrigin.AI_DRAFT.value,
            "suggested_fields": suggested_fields,
            "suggested_domains": suggested_domains,
        }

    # ------------------------------------------------------------------
    # 世界构建模板：层次策略 + 每档提示词（名称与层数由项目决定）
    # ------------------------------------------------------------------
    def list_templates(self, project_id: str) -> list[dict[str, Any]]:
        """内置种子模板 + 本项目私有模板。"""
        rows = self.session.exec(
            select(WorldBuildingTemplate).where(
                or_(
                    WorldBuildingTemplate.project_id.is_(None),  # type: ignore[union-attr]
                    WorldBuildingTemplate.project_id == project_id,
                )
            )
        ).all()
        return [self._serialize_template(row) for row in rows]

    def upsert_template(
        self,
        project_id: str,
        *,
        template_id: str = "",
        name: str = "",
        layers: list[str] | None = None,
        prompts: dict[str, Any] | None = None,
        is_default: bool = False,
    ) -> WorldBuildingTemplate:
        """新建或更新模板。内置模板（project_id 为空）只读，不允许改。"""
        row: WorldBuildingTemplate | None = None
        if template_id:
            found = self.session.get(WorldBuildingTemplate, str(template_id))
            if found and (found.project_id is None or found.project_id == project_id):
                row = found
        if row is None:
            row = WorldBuildingTemplate(project_id=project_id)
        if row.project_id is None:
            raise ValueError("内置模板只读，请复制为项目模板后再修改")

        row.name = str(name or row.name or "未命名模板")
        if layers is not None:
            row.layers_json = _dump_list(layers)
        if prompts is not None:
            row.prompts_json = json.dumps(prompts or {}, ensure_ascii=False)
        if is_default:
            # 同一项目只保留一个默认模板
            for other in self.session.exec(
                select(WorldBuildingTemplate).where(
                    WorldBuildingTemplate.project_id == project_id
                )
            ).all():
                if other.id != row.id:
                    other.is_default = False
                    self.session.add(other)
        row.is_default = bool(is_default)
        row.updated_at = datetime.now()
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def delete_template(self, project_id: str, template_id: str) -> None:
        """删除项目私有模板（内置模板不可删）。"""
        row = self.session.get(WorldBuildingTemplate, str(template_id or ""))
        if not row or row.project_id != project_id:
            return
        self.session.delete(row)
        self.session.commit()

    @staticmethod
    def _serialize_template(row: WorldBuildingTemplate) -> dict[str, Any]:
        layers = loads_json(row.layers_json, [])
        prompts = loads_json(row.prompts_json, {})
        return {
            "id": row.id,
            "name": row.name,
            "layers": layers if isinstance(layers, list) else [],
            "prompts": prompts if isinstance(prompts, dict) else {},
            "is_default": row.is_default,
            "is_builtin": row.project_id is None,
        }

    async def draft_template(
        self,
        project_id: str,
        *,
        domain: str = "",
        hint: str = "",
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        """按项目已启用模块与补充要求起草一份模板草案（**不落库**）。

        草案供用户/智能体预览确认，随后显式走 ``upsert_template`` 才会保存；
        模板草案不是事实候选，不进入候选/审阅流水线。真人（``world-templates/draft``）
        与智能体（``manage_world_building_template`` action=draft）共用本方法。
        """
        specs = self.domains.resolve_specs(project_id)
        if not specs:
            raise ValueError("项目还没有启用的设定模块，先启用或添加模块再起草模板")
        lines: list[str] = []
        for spec in specs:
            attrs = "、".join(spec.attributes) if spec.attributes else "（无属性契约）"
            lines.append(f"- {spec.label}（{spec.key}）：{attrs}")
        focus = ""
        if domain:
            spec = next((s for s in specs if s.key == str(domain or "").strip()), None)
            if spec is None:
                raise ValueError(f"模块未启用或不存在：{domain}")
            focus = (
                f"本次模板主要用于「{spec.label}」({spec.key})：\n"
                f"  属性契约：{'、'.join(spec.attributes) or '（无）'}\n"
                f"  模块说明：{spec.prompt_hint or '（无）'}\n"
            )
        prompt = (
            DEFAULT_TEMPLATE_DRAFT_PROMPT.replace("{domains}", "\n".join(lines) or "（暂无）")
            .replace("{focus}", focus)
            .replace("{hint}", hint or "无")
        )
        response = await self._ensure_ai().chat(
            messages=[
                LLMMessage(role="system", content=TEMPLATE_DRAFT_SYSTEM_PROMPT),
                LLMMessage(role="user", content=prompt),
            ],
            provider=provider,
            model=model,
            temperature=0.6,
            max_tokens=2000,
        )
        success = getattr(response, "success", True)
        if success is False:
            raise ValueError(getattr(response, "error", "") or "LLM 生成失败")
        raw = getattr(response, "content", None) or ""
        data = _extract_json_object(raw)
        try:
            draft = DraftTemplateSchema.model_validate(data).model_dump()
        except ValidationError as exc:
            raise ValueError(f"模型输出不符合模板契约：{exc}") from exc

        name = str(draft.get("name") or "").strip()
        layers = [
            str(item).strip()
            for item in (draft.get("layers") or [])
            if str(item).strip()
        ]
        known_prompt_keys = ("draft_world", "expand_domain", "expand_entity")
        prompts = {
            key: str(val).strip()
            for key, val in (draft.get("prompts") or {}).items()
            if key in known_prompt_keys and str(val).strip()
        }
        if not name:
            raise ValueError("模型没有产出模板名称")
        if not layers:
            raise ValueError("模型没有产出有效的层次策略")
        return {
            "name": name[:60],
            "layers": [str(item)[:40] for item in layers[:8]],
            "prompts": prompts,
            "note": str(draft.get("note") or "").strip()[:200],
        }

    # ------------------------------------------------------------------
    # expand_domain：按层次策略细化整个域
    # ------------------------------------------------------------------
    def build_domain_prompt(
        self,
        spec: Any,
        known_names: list[str],
        *,
        template: WorldBuildingTemplate | None = None,
        prompt_override: str = "",
        hint: str = "",
    ) -> str:
        """域级细化的提示词：层次策略 + 已有条目 + 可选补充要求。"""
        layers: list[str] = []
        if template:
            raw_layers = loads_json(template.layers_json, [])
            if isinstance(raw_layers, list):
                layers = [str(item) for item in raw_layers]

        prompt = str(prompt_override or "").strip()
        if not prompt and template:
            prompts = loads_json(template.prompts_json, {})
            if isinstance(prompts, dict):
                prompt = str(prompts.get("expand_domain") or "").strip()
        if not prompt:
            prompt = DEFAULT_EXPAND_DOMAIN_PROMPT

        known_text = "、".join(known_names[:60]) or "（暂无）"
        return (
            prompt.replace("{domain}", (spec.label if spec else "") or "")
            .replace("{layers}", " → ".join(layers) if layers else "（未定义层次）")
            .replace("{known}", known_text)
            .replace("{hint}", hint or "无")
        )

    async def expand_domain(
        self,
        project_id: str,
        domain: str,
        *,
        template_id: str | None = None,
        prompt_override: str = "",
        hint: str = "",
        limit: int = 12,
        provider: str | None = None,
        model: str | None = None,
        run: WorldExtractionRun | None = None,
    ) -> dict[str, Any]:
        """按层次策略细化一个域，产出该域的新候选（全部标记 ``ai_draft``）。

        与 ``expand_entity`` 的差别：这里是**域级批量**产出，成本更高，因此设计为
        由 API 层提交到既有任务中心后异步执行；本方法只负责业务本身，可被后台任务调用。
        """
        specs = {spec.key: spec for spec in self.domains.resolve_specs(project_id)}
        spec = specs.get(str(domain or "").strip())
        if spec is None:
            raise ValueError(f"模块未启用或不存在：{domain}")

        known = self.session.exec(
            select(WorldEntity).where(
                WorldEntity.project_id == project_id,
                WorldEntity.domain == domain,
            )
        ).all()
        known_names = [str(item.name or "").strip() for item in known if str(item.name or "").strip()]

        template: WorldBuildingTemplate | None = None
        if template_id:
            found = self.session.get(WorldBuildingTemplate, template_id)
            if found and (found.project_id is None or found.project_id == project_id):
                template = found
        prompt = self.build_domain_prompt(
            spec, known_names, template=template, prompt_override=prompt_override, hint=hint
        )

        owns_run = run is None
        if owns_run:
            run = WorldExtractionRun(
                snapshot_id=None,
                project_id=project_id,
                kind=ExtractionRunKind.GENERATE.value,
                mode=ExtractionRunMode.FULL.value,
                status=ExtractionRunStatus.RUNNING.value,
                pipeline_version="v1",
                provider=provider or "",
                model=model or "",
            )
            self.session.add(run)
            self.session.flush()

        try:
            data = await self._generate(prompt, provider=provider, model=model)
        except Exception as exc:  # noqa: BLE001 - 运行需落失败态
            run.status = ExtractionRunStatus.FAILED.value
            run.diagnostics_json = dumps_json({"error": str(exc)[:500], "domain": domain})
            run.updated_at = datetime.now()
            self.session.add(run)
            self.session.commit()
            raise

        created: list[str] = []
        for item in (data.get("items") or [])[: max(1, min(int(limit or 12), 40))]:
            name = str(item.get("entity") or item.get("name") or "").strip()
            if not name:
                continue
            attributes = {
                str(key): str(value)[:500]
                for key, value in (item.get("attributes") or {}).items()
                if str(value).strip()
            }
            normalized = re.sub(r"\s+", "", name).lower()
            candidate = WorldFactCandidate(
                run_id=run.id,
                snapshot_id=None,
                project_id=project_id,
                domain=domain,
                entity_name=name,
                normalized_key=normalized,
                fingerprint=f"gen:{project_id}:{domain}:{normalized}",
                payload_json=dumps_json(
                    {
                        "name": name,
                        "attributes": attributes,
                        "action": "expand_domain",
                        "layers": loads_json(template.layers_json, []) if template else [],
                    }
                ),
                # 生成链路没有原文：不伪造证据（R6）。
                evidence_json="[]",
                origin=CandidateOrigin.AI_DRAFT.value,
                status=CandidateStatus.PENDING.value,
                last_run_id=run.id,
            )
            self.session.add(candidate)
            created.append(name)

        suggested_domains = self._persist_suggested_domains(
            project_id, data.get("suggested_domains") or []
        )
        suggested_fields = [
            {
                "domain": str(item.get("domain") or "")[:60],
                "field": str(item.get("field") or "")[:60],
                "reason": str(item.get("reason") or "")[:300],
            }
            for item in (data.get("suggested_fields") or [])
            if str(item.get("field") or "").strip()
        ]

        run.status = ExtractionRunStatus.SUCCESS.value
        run.trace_json = dumps_json(
            [{"action": "expand_domain", "domain": domain, "items": len(created)}]
        )
        run.diagnostics_json = dumps_json(
            {
                "domain": domain,
                "created": created,
                "suggested_fields": suggested_fields,
                "suggested_domains": suggested_domains,
            }
        )
        run.updated_at = datetime.now()
        self.session.add(run)
        self.session.commit()

        return {
            "run_id": run.id,
            "domain": domain,
            "created": created,
            "candidate_count": len(created),
            "origin": CandidateOrigin.AI_DRAFT.value,
            "suggested_fields": suggested_fields,
            "suggested_domains": suggested_domains,
        }

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _prepare(
        self,
        project_id: str,
        entity_id: str,
        *,
        fields: list[str],
        template_id: str | None,
    ) -> tuple[WorldEntity, Any, list[str], WorldBuildingTemplate | None]:
        entity = self.session.get(WorldEntity, entity_id)
        if not entity or entity.project_id != project_id:
            raise ValueError("实体不存在")
        specs = {spec.key: spec for spec in self.domains.resolve_specs(project_id)}
        spec = specs.get(entity.domain)
        if spec is None:
            raise ValueError(f"模块未启用或不存在：{entity.domain}")
        picked = [str(item) for item in (fields or []) if str(item) in list(spec.attributes)]
        if not picked:
            raise ValueError(
                "请指定待补充字段，且字段必须属于该模块的属性契约："
                + "、".join(list(spec.attributes))
            )
        template: WorldBuildingTemplate | None = None
        if template_id:
            found = self.session.get(WorldBuildingTemplate, template_id)
            if found and (found.project_id is None or found.project_id == project_id):
                template = found
        return entity, spec, picked, template

    def _persist_suggested_domains(
        self, project_id: str, suggestions: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """AI 建议的新模块：落库但**默认不启用**，需用户确认（R7 / I2）。"""
        builtin_and_active = {spec.key for spec in self.domains.resolve_specs(project_id)}
        stored: list[dict[str, Any]] = []
        for item in suggestions:
            key = str(item.get("key") or "").strip()[:60]
            if not key or key in builtin_and_active:
                continue
            exists = self.session.exec(
                select(WorldDomainDefinition).where(
                    WorldDomainDefinition.project_id == project_id,
                    WorldDomainDefinition.domain_key == key,
                )
            ).first()
            if exists:
                continue
            attributes = [
                str(attr).strip()[:60]
                for attr in (item.get("attributes") or [])
                if str(attr).strip()
            ]
            self.domains.upsert_definition(
                project_id,
                key,
                label=str(item.get("label") or "")[:60],
                extra_attributes=attributes,
                prompt_hint=str(item.get("reason") or "")[:400],
                is_enabled=False,  # 过闸：确认后才参与提取/生成
                source=DomainDefinitionSource.AI_SUGGESTED.value,
            )
            stored.append(
                {
                    "key": key,
                    "label": str(item.get("label") or ""),
                    "attributes": attributes,
                    "state": "pending_confirmation",
                }
            )
        return stored

    async def _generate(
        self, prompt: str, *, provider: str | None, model: str | None
    ) -> dict[str, Any]:
        response = await self._ensure_ai().chat(
            messages=[
                LLMMessage(role="system", content=GENERATION_SYSTEM_PROMPT),
                LLMMessage(role="user", content=prompt),
            ],
            provider=provider,
            model=model,
            temperature=0.4,
            max_tokens=2000,
        )
        success = getattr(response, "success", True)
        if success is False:
            raise ValueError(getattr(response, "error", "") or "LLM 生成失败")
        raw = getattr(response, "content", None) or ""
        data = _extract_json_object(raw)
        try:
            return WorldGenerationSchema.model_validate(data).model_dump()
        except ValidationError as exc:
            raise ValueError(f"模型输出不符合契约：{exc}") from exc
