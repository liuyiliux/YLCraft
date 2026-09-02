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
