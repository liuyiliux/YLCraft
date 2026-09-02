"""项目级世界模块（域）与属性扩展。

内置模块由 ``contracts.DOMAIN_SPECS`` 提供稳定默认值；每个项目在此基础上可以：

- 覆盖展示名与提取提示词（留空表示沿用内置）
- **追加**属性字段（内置字段不可删除——既有 ``attributes_json`` 需保持可解析）
- 禁用不需要的模块
- 新增自定义模块（赛博朋克的「义体改造」、修仙的「灵脉品级」等）

解析结果供提取、生成与 UI 共用，保证「看到什么模块」与「按什么 schema 产出」一致。
自定义模块的实体仍写入 ``world_entities``（``entity_type`` 取定义值），无需新表。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from app.db.models.novel_source import (
    DomainDefinitionSource,
    WorldDomainDefinition,
)
from app.services.creative_project.service import loads_json
from app.services.novel_source.contracts import DOMAIN_SPECS, DomainSpec

BUILTIN_SOURCE = "builtin"


def _extra_attributes(row: WorldDomainDefinition | None) -> list[str]:
    """项目追加的属性字段（相对内置）。"""
    if not row:
        return []
    raw = loads_json(row.extra_attributes_json, [])
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _ignored_suggestions(row: WorldDomainDefinition | None) -> list[str]:
    """被用户忽略的 AI 建议字段。"""
    if not row:
        return []
    raw = loads_json(row.ignored_suggestions_json, [])
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _dump_list(values: list[str]) -> str:
    return json.dumps(
        [str(item).strip() for item in values if str(item).strip()], ensure_ascii=False
    )


class WorldDomainService:
    """解析并维护项目级世界模块定义。"""

    def __init__(self, session: Session):
        self.session = session

    def _definitions(self, project_id: str) -> dict[str, WorldDomainDefinition]:
        rows = self.session.exec(
            select(WorldDomainDefinition).where(
                WorldDomainDefinition.project_id == project_id
            )
        ).all()
        return {row.domain_key: row for row in rows}

    def list_domains(self, project_id: str) -> list[dict[str, Any]]:
        """解析后的全量模块视图（内置含覆盖 + 项目自定义），供 UI 与能力发现使用。"""
        defs = self._definitions(project_id)
        builtin_keys = {spec.key for spec in DOMAIN_SPECS}
        items: list[dict[str, Any]] = []

        for spec in DOMAIN_SPECS:
            row = defs.get(spec.key)
            extra = _extra_attributes(row)
            items.append(
                {
                    "key": spec.key,
                    "label": (row.label if row and row.label else spec.label),
                    "entity_type": spec.entity_type,
                    # 内置字段在前，项目追加在后；内置字段不可删除。
                    "attributes": list(spec.attributes)
                    + [item for item in extra if item not in spec.attributes],
                    "builtin_attributes": list(spec.attributes),
                    "is_builtin": True,
                    "is_enabled": bool(row.is_enabled) if row else True,
                    "source": row.source if row else BUILTIN_SOURCE,
                    "prompt_hint": (row.prompt_hint if row and row.prompt_hint else spec.prompt_hint),
                }
            )

        for key, row in defs.items():
            if key in builtin_keys:
                continue
            items.append(
                {
                    "key": key,
                    "label": row.label or key,
                    "entity_type": row.entity_type or key,
                    "attributes": _extra_attributes(row),
                    "builtin_attributes": [],
                    "is_builtin": False,
                    "is_enabled": bool(row.is_enabled),
                    "source": row.source,
                    "prompt_hint": row.prompt_hint,
                }
            )
        return items

    def resolve_specs(self, project_id: str) -> list[DomainSpec]:
        """提取/生成实际使用的模块契约：只含启用中的模块。"""
        defs = self._definitions(project_id)
        builtin_keys = {spec.key for spec in DOMAIN_SPECS}
        specs: list[DomainSpec] = []

        for spec in DOMAIN_SPECS:
            row = defs.get(spec.key)
            if row and not row.is_enabled:
                continue
            extra = _extra_attributes(row)
            specs.append(
                DomainSpec(
                    key=spec.key,
                    label=(row.label if row and row.label else spec.label),
                    basic=spec.basic,
                    extractable=spec.extractable,
                    entity_type=spec.entity_type,
                    prompt_hint=(
                        row.prompt_hint if row and row.prompt_hint else spec.prompt_hint
                    ),
                    attributes=tuple(spec.attributes)
                    + tuple(item for item in extra if item not in spec.attributes),
                )
            )

        for key, row in defs.items():
            if key in builtin_keys or not row.is_enabled:
                continue
            # AI 建议的模块需用户确认（转 custom 并启用）后才参与提取。
            if row.source == DomainDefinitionSource.AI_SUGGESTED.value:
                continue
            specs.append(
                DomainSpec(
                    key=key,
                    label=row.label or key,
                    basic=False,
                    extractable=True,
                    entity_type=row.entity_type or key,
                    prompt_hint=row.prompt_hint,
                    attributes=tuple(_extra_attributes(row)),
                )
            )
        return specs

    def pending_suggestions(self, project_id: str) -> dict[str, Any]:
        """聚合待确认的 AI 结构建议（模块级 + 字段级）。

        模块级：``world_domain_definitions`` 中 ``source=ai_suggested`` 且未启用的定义。
        字段级：该项目最近生成运行 ``diagnostics_json.suggested_fields`` 中，既不在
        属性契约内、也未被忽略的字段。

        确认与忽略复用既有 ``upsert_definition`` / ``reset_definition``，不新增并行通道。
        """
        from app.db.models.novel_source import WorldExtractionRun

        domain_items: list[dict[str, Any]] = []
        for row in self._definitions(project_id).values():
            if row.source != DomainDefinitionSource.AI_SUGGESTED.value or row.is_enabled:
                continue
            domain_items.append(
                {
                    "key": row.domain_key,
                    "label": row.label or row.domain_key,
                    "attributes": _extra_attributes(row),
                    "reason": row.prompt_hint,
                    "state": "pending_confirmation",
                }
            )

        specs = {spec.key: spec for spec in self.resolve_specs(project_id)}
        definitions = self._definitions(project_id)
        field_items: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        runs = self.session.exec(
            select(WorldExtractionRun)
            .where(
                WorldExtractionRun.project_id == project_id,
                WorldExtractionRun.kind == "generate",
            )
            .order_by(WorldExtractionRun.created_at.desc())
        ).all()
        for run in runs:
            diagnostics = loads_json(run.diagnostics_json, {})
            if not isinstance(diagnostics, dict):
                continue
            for item in diagnostics.get("suggested_fields") or []:
                if not isinstance(item, dict):
                    continue
                domain = str(item.get("domain") or "").strip()
                field = str(item.get("field") or "").strip()
                if not domain or not field or (domain, field) in seen:
                    continue
                seen.add((domain, field))
                spec = specs.get(domain)
                row = definitions.get(domain)
                contract = list(spec.attributes) if spec else []
                extra = _extra_attributes(row)
                if field in contract or field in extra:
                    continue  # 已确认进契约
                ignored = _ignored_suggestions(row)
                if field in ignored:
                    continue  # 用户已忽略
                field_items.append(
                    {
                        "domain": domain,
                        "domain_label": (spec.label if spec else domain),
                        "field": field,
                        "reason": str(item.get("reason") or "")[:300],
                        "state": "pending_confirmation",
                    }
                )

        return {"domains": domain_items, "fields": field_items}

    def confirm_suggested_field(self, project_id: str, domain_key: str, field: str) -> None:
        """确认字段建议：写入该模块的属性契约（只追加，内置字段不动）。"""
        field = str(field or "").strip()
        if not field:
            raise ValueError("字段名不能为空")
        specs = {spec.key: spec for spec in self.resolve_specs(project_id)}
        spec = specs.get(domain_key)
        if spec is None:
            raise ValueError(f"模块未启用或不存在：{domain_key}")
        if field in list(spec.attributes):
            return  # 已在契约内，幂等
        row = self._definitions(project_id).get(domain_key)
        extra = [item for item in _extra_attributes(row) if item != field]
        extra.append(field)
        ignored = [item for item in _ignored_suggestions(row) if item != field]
        ignored_json = _dump_list(ignored)
        self.upsert_definition(
            project_id,
            domain_key,
            extra_attributes=extra,
            source=DomainDefinitionSource.CUSTOM.value,
        )
        # upsert 会重新落库，忽略清单需随后写回（保持与 extra 一致）。
        if row is not None:
            row.ignored_suggestions_json = ignored_json
            self.session.add(row)
            self.session.commit()

    def ignore_suggested_field(self, project_id: str, domain_key: str, field: str) -> None:
        """忽略字段建议：记入忽略清单，不再重复提示。"""
        field = str(field or "").strip()
        if not field:
            raise ValueError("字段名不能为空")
        row = self._definitions(project_id).get(domain_key)
        if row is None:
            # 该模块还没有项目级定义，建一条只记录忽略项的定义（不启用）。
            ignored = [field]
            self.upsert_definition(
                project_id,
                domain_key,
                is_enabled=False,
                source=DomainDefinitionSource.AI_SUGGESTED.value,
            )
            row = self._definitions(project_id).get(domain_key)
        else:
            ignored = [item for item in _ignored_suggestions(row) if item != field]
            ignored.append(field)
        if row is not None:
            row.ignored_suggestions_json = _dump_list(ignored)
            self.session.add(row)
            self.session.commit()

    def upsert_definition(
        self,
        project_id: str,
        domain_key: str,
        *,
        label: str = "",
        entity_type: str = "",
        extra_attributes: list[str] | None = None,
        prompt_hint: str = "",
        is_enabled: bool = True,
        source: str | None = None,
    ) -> WorldDomainDefinition:
        """新增或更新一个项目级定义（覆盖内置 / 新增自定义）。"""
        key = str(domain_key or "").strip()
        if not key:
            raise ValueError("模块 key 不能为空")
        is_builtin = any(spec.key == key for spec in DOMAIN_SPECS)

        row = self._definitions(project_id).get(key)
        if row is None:
            row = WorldDomainDefinition(
                project_id=project_id,
                domain_key=key,
                source=(
                    source
                    or (
                        DomainDefinitionSource.BUILTIN_OVERRIDE.value
                        if is_builtin
                        else DomainDefinitionSource.CUSTOM.value
                    )
                ),
            )
        elif source:
            if not is_builtin and source == DomainDefinitionSource.BUILTIN_OVERRIDE.value:
                raise ValueError("自定义模块不能使用 builtin_override 来源")
            row.source = source

        row.label = str(label or "")
        # 内置模块的 entity_type 由契约固定（实体层按 entity_type 归一存储），不允许改。
        row.entity_type = "" if is_builtin else str(entity_type or "")
        row.extra_attributes_json = json.dumps(
            [str(item).strip() for item in (extra_attributes or []) if str(item).strip()],
            ensure_ascii=False,
        )
        row.prompt_hint = str(prompt_hint or "")
        row.is_enabled = bool(is_enabled)
        row.updated_at = datetime.now()

        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def reset_definition(self, project_id: str, domain_key: str) -> None:
        """删除项目级定义：内置模块恢复默认，自定义模块彻底移除。"""
        row = self._definitions(project_id).get(str(domain_key or "").strip())
        if not row:
            return
        self.session.delete(row)
        self.session.commit()
