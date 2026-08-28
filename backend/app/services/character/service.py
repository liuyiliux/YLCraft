"""
YLCraft — 角色服务层
"""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.character import Character, CharacterStoryLink, CharacterRelationship, CharacterRole
from app.db.models.creative_project import CreativeProject
from app.services.character.provenance import extract_origin_label, loads_json_mapping, mark_user_edited


def _json_list(value: Any) -> list[Any]:
    """Return a stable list for legacy JSON array columns.

    Older records occasionally contain `{}` or malformed JSON in fields that
    are now consumed as arrays by the Story and character workspaces.
    """
    if not value:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return []
        return parsed if isinstance(parsed, list) else []
    return []


class CharacterService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(
        self,
        keyword: str | None = None,
        source_type: str | None = None,
        workflow_source: str | None = None,
        role: str | None = None,
        tag: str | None = None,
        is_favorite: bool | None = None,
        extract_origin: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ):
        query = select(Character)
        if keyword:
            query = query.where(Character.name.contains(keyword))
        if role:
            query = query.where(Character.role == role)
        if is_favorite:
            query = query.where(Character.is_favorite == True)
        if source_type:
            query = query.where(Character.source_types.contains(source_type))
        if workflow_source:
            query = query.where(Character.workflow_source == workflow_source)
        if extract_origin:
            # 提取来源是「角色 × 项目」维度的标记，需要按关联的 world usage 过滤
            link_result = await self.session.exec(
                select(CharacterStoryLink.character_id).where(
                    CharacterStoryLink.extract_origin == extract_origin
                )
            )
            character_ids = [row for row in link_result.all() if row]
            if not character_ids:
                return [], 0
            query = query.where(Character.id.in_(character_ids))

        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.exec(query)
        characters = result.all()

        count_query = select(Character)
        if keyword:
            count_query = count_query.where(Character.name.contains(keyword))
        count_result = await self.session.exec(count_query)
        total = len(count_result.all())

        return characters, total

    async def get_by_id(self, character_id: str) -> Optional[Character]:
        result = await self.session.exec(select(Character).where(Character.id == character_id))
        return result.first()

    async def create(self, **kwargs) -> Character:
        # Convert list fields to JSON strings
        for field in ["source_types", "tags", "reference_asset_ids", "signature_items", "expressions", "poses"]:
            if field in kwargs and kwargs[field] is not None:
                kwargs[field] = json.dumps(kwargs[field], ensure_ascii=False)
        for api_field, model_field in _BIBLE_FIELD_MAP.items():
            if api_field in kwargs and kwargs[api_field] is not None:
                kwargs[model_field] = json.dumps(kwargs.pop(api_field), ensure_ascii=False)
        if "field_sources" in kwargs and kwargs["field_sources"] is not None:
            kwargs["field_sources_json"] = json.dumps(kwargs.pop("field_sources"), ensure_ascii=False)
        character = Character(**kwargs)
        self.session.add(character)
        await self.session.flush()
        await self.session.refresh(character)
        return character

    async def update(self, character_id: str, **kwargs) -> Optional[Character]:
        character = await self.get_by_id(character_id)
        if not character:
            return None
        # Convert list fields to JSON strings
        for field in ["source_types", "tags", "reference_asset_ids", "signature_items", "expressions", "poses"]:
            if field in kwargs and kwargs[field] is not None:
                kwargs[field] = json.dumps(kwargs[field], ensure_ascii=False)
        for api_field, model_field in _BIBLE_FIELD_MAP.items():
            if api_field in kwargs and kwargs[api_field] is not None:
                kwargs[model_field] = json.dumps(kwargs.pop(api_field), ensure_ascii=False)
        if "field_sources" in kwargs and kwargs["field_sources"] is not None:
            kwargs["field_sources_json"] = json.dumps(kwargs.pop("field_sources"), ensure_ascii=False)
        else:
            # 用户在角色工作区保存的设定字段标记为 user_edited，覆盖提取/推断来源
            edited = [
                field
                for field in _USER_EDITABLE_PROVENANCE_FIELDS
                if kwargs.get(field) is not None
            ]
            if edited:
                kwargs["field_sources_json"] = json.dumps(
                    mark_user_edited(character.field_sources_json, edited),
                    ensure_ascii=False,
                )
        for key, value in kwargs.items():
            if value is not None and hasattr(character, key):
                setattr(character, key, value)
        character.updated_at = datetime.now()
        await self.session.flush()
        await self.session.refresh(character)
        return character

    async def delete(self, character_id: str) -> bool:
        character = await self.get_by_id(character_id)
        if not character:
            return False
        await self.session.delete(character)
        await self.session.flush()
        return True

    async def add_tag(self, character_id: str, tag: str) -> Optional[Character]:
        character = await self.get_by_id(character_id)
        if not character:
            return None
        tags = _json_list(character.tags)
        if tag not in tags:
            tags.append(tag)
            character.tags = json.dumps(tags, ensure_ascii=False)
        await self.session.flush()
        await self.session.refresh(character)
        return character

    async def remove_tag(self, character_id: str, tag: str) -> Optional[Character]:
        character = await self.get_by_id(character_id)
        if not character:
            return None
        tags = _json_list(character.tags)
        if tag in tags:
            tags.remove(tag)
            character.tags = json.dumps(tags, ensure_ascii=False)
        await self.session.flush()
        await self.session.refresh(character)
        return character

    async def get_all_tags(self):
        result = await self.session.exec(select(Character))
        characters = result.all()
        all_tags = set()
        for c in characters:
            tags = _json_list(c.tags)
            for t in tags:
                all_tags.add(t)
        return sorted(all_tags)

    async def list_world_usages(self, character_id: str) -> list[dict[str, Any]]:
        result = await self.session.exec(
            select(CharacterStoryLink).where(CharacterStoryLink.character_id == character_id)
        )
        links = result.all()
        project_ids = [link.story_id for link in links if link.story_id]
        projects_by_id: dict[str, CreativeProject] = {}
        if project_ids:
            project_result = await self.session.exec(
                select(CreativeProject).where(CreativeProject.id.in_(project_ids))
            )
            projects_by_id = {project.id: project for project in project_result.all()}
        return [self.story_link_to_response(link, projects_by_id.get(link.story_id)) for link in links]

    async def link_to_story(
        self,
        character_id: str,
        story_id: str,
        *,
        world_id: str = "",
        world_name: str = "",
        usage_role: str = "",
        local_alias: str = "",
        local_identity: str = "",
        local_faction: str = "",
        local_status: str = "active",
        local_costume: str = "",
        local_prompt_tags: list[str] | None = None,
        ooc_notes: str = "",
        off_model_notes: str = "",
        bible_overrides: dict[str, Any] | None = None,
        visual_overrides: dict[str, Any] | None = None,
    ) -> CharacterStoryLink:
        result = await self.session.exec(
            select(CharacterStoryLink).where(
                CharacterStoryLink.character_id == character_id,
                CharacterStoryLink.story_id == story_id,
                CharacterStoryLink.world_id == (world_id or ""),
            )
        )
        link = result.first()
        is_new = link is None
        if link is None:
            link = CharacterStoryLink(character_id=character_id, story_id=story_id, world_id=world_id or "")
            self.session.add(link)

        link.world_name = world_name or link.world_name or ""
        link.usage_role = usage_role or link.usage_role or ""
        link.local_alias = local_alias or link.local_alias or ""
        link.local_identity = local_identity or link.local_identity or ""
        link.local_faction = local_faction or link.local_faction or ""
        link.local_status = local_status or link.local_status or "active"
        link.local_costume = local_costume or link.local_costume or ""
        if local_prompt_tags is not None:
            link.local_prompt_tags = json.dumps(local_prompt_tags, ensure_ascii=False)
        if ooc_notes:
            link.ooc_notes = ooc_notes
        if off_model_notes:
            link.off_model_notes = off_model_notes
        if bible_overrides is not None:
            link.bible_overrides_json = json.dumps(bible_overrides, ensure_ascii=False)
        if visual_overrides is not None:
            link.visual_overrides_json = json.dumps(visual_overrides, ensure_ascii=False)
        link.updated_at = datetime.now()

        character = await self.get_by_id(character_id)
        if character and is_new:
            character.use_count = (character.use_count or 0) + 1
            character.last_used_at = datetime.now()
        await self.session.flush()
        await self.session.refresh(link)
        return link

    async def update_world_usage(
        self,
        link_id: str,
        *,
        character_id: str | None = None,
        **kwargs,
    ) -> Optional[CharacterStoryLink]:
        query = select(CharacterStoryLink).where(CharacterStoryLink.id == link_id)
        if character_id:
            query = query.where(CharacterStoryLink.character_id == character_id)
        result = await self.session.exec(query)
        link = result.first()
        if not link:
            return None
        json_fields = {
            "local_prompt_tags": "local_prompt_tags",
            "bible_overrides": "bible_overrides_json",
            "visual_overrides": "visual_overrides_json",
        }
        for key, value in kwargs.items():
            if value is None:
                continue
            if key in json_fields:
                setattr(link, json_fields[key], json.dumps(value, ensure_ascii=False))
            elif hasattr(link, key):
                setattr(link, key, value)
        link.updated_at = datetime.now()
        await self.session.flush()
        await self.session.refresh(link)
        return link

    async def delete_world_usage(self, link_id: str, *, character_id: str | None = None) -> bool:
        query = select(CharacterStoryLink).where(CharacterStoryLink.id == link_id)
        if character_id:
            query = query.where(CharacterStoryLink.character_id == character_id)
        result = await self.session.exec(query)
        link = result.first()
        if not link:
            return False
        await self.session.delete(link)
        await self.session.flush()
        return True

    async def list_relationships(self, character_id: str) -> list[CharacterRelationship]:
        result = await self.session.exec(select(CharacterRelationship).where(
            (CharacterRelationship.character_id == character_id) |
            (CharacterRelationship.related_character_id == character_id)
        ))
        return result.all()

    async def create_relationship(self, character_id: str, **kwargs) -> CharacterRelationship:
        if not await self.get_by_id(character_id) or not await self.get_by_id(kwargs.get("related_character_id", "")):
            raise ValueError("角色或关联角色不存在")
        if character_id == kwargs["related_character_id"]:
            raise ValueError("不能与自身建立关系")
        item = CharacterRelationship(character_id=character_id, **kwargs)
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def update_relationship(self, character_id: str, relationship_id: str, **kwargs) -> Optional[CharacterRelationship]:
        result = await self.session.exec(select(CharacterRelationship).where(
            CharacterRelationship.id == relationship_id,
            CharacterRelationship.character_id == character_id,
        ))
        item = result.first()
        if not item:
            return None
        if kwargs.get("related_character_id") and not await self.get_by_id(kwargs["related_character_id"]):
            raise ValueError("关联角色不存在")
        for key, value in kwargs.items():
            if hasattr(item, key):
                setattr(item, key, value)
        item.updated_at = datetime.now()
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def delete_relationship(self, character_id: str, relationship_id: str) -> bool:
        result = await self.session.exec(select(CharacterRelationship).where(
            CharacterRelationship.id == relationship_id,
            CharacterRelationship.character_id == character_id,
        ))
        item = result.first()
        if not item:
            return False
        await self.session.delete(item)
        await self.session.flush()
        return True

    def relationship_to_response(self, item: CharacterRelationship) -> dict[str, Any]:
        return {"id": item.id, "character_id": item.character_id, "related_character_id": item.related_character_id,
                "relation_type": item.relation_type or "", "relation_note": item.relation_note or "",
                "source": item.source or "", "is_directed": bool(item.is_directed),
                "created_at": str(item.created_at), "updated_at": str(item.updated_at)}

    def build_prompt_pack(self, character: Character) -> dict[str, Any]:
        data = self.to_response(character)
        visual = ", ".join(filter(None, [data["appearance"], data["costume_hint"], *data["signature_items"]]))
        identity = data.get("identity") if isinstance(data.get("identity"), dict) else {}
        motivation = data.get("motivation") if isinstance(data.get("motivation"), dict) else {}
        speech = data.get("speech") if isinstance(data.get("speech"), dict) else {}
        behavior = data.get("behavior") if isinstance(data.get("behavior"), dict) else {}
        stable = "；".join(filter(None, [
            f"身份：{identity.get('logline') or identity.get('position') or ''}",
            f"性格：{data.get('personality') or ''}",
            f"动机：{motivation.get('desire') or motivation.get('core_desire') or ''}",
            f"说话方式：{speech.get('tone') or speech.get('style') or ''}",
            f"行为边界：{behavior.get('never_do') or behavior.get('boundary') or ''}",
        ]))
        return {"character_id": character.id, "name": character.name,
                "image_prompt": f"{character.name}，{visual}，{stable}，单人角色立绘，五官清晰，服装与标志物保持一致，适合作为后续分镜参考图".strip("，"),
                "character_sheet_prompt": f"{character.name}角色设定图，{visual}，{stable}，正面、侧面、背面三视图，白色背景，分区展示服装、发型和标志物，保持同一人物面部一致".strip("，"),
                "voice_prompt": f"角色{character.name}的音色与说话方式：{json.dumps(data['speech'], ensure_ascii=False)}",
                "character_json": data}

    async def extract_origins_for(self, character_ids: list[str]) -> dict[str, list[str]]:
        """Batch-load distinct extract origins keyed by character id.

        Returns ``{character_id: [origin, ...]}``. Async on purpose: ``to_response``
        is sync and shared by many helpers, so callers opt in when they need the
        provenance tags.
        """
        clean_ids = [str(value) for value in character_ids if str(value)]
        if not clean_ids:
            return {}
        try:
            result = await self.session.exec(
                select(CharacterStoryLink.character_id, CharacterStoryLink.extract_origin).where(
                    CharacterStoryLink.character_id.in_(clean_ids)
                )
            )
            rows = result.all()
        except Exception:  # pragma: no cover - provenance is best-effort
            return {}

        origins: dict[str, list[str]] = {}
        for row in rows:
            # SQLAlchemy Row 支持下标访问，但不是 tuple 实例
            try:
                character_id = str(row[0] or "")
                value = str(row[1] or "").strip()
            except (TypeError, IndexError, KeyError):
                continue
            if not character_id or not value or value == "unknown":
                continue
            bucket = origins.setdefault(character_id, [])
            if value not in bucket:
                bucket.append(value)
        return origins

    def to_response(
        self,
        character: Character,
        *,
        extract_origins: dict[str, list[str]] | None = None,
    ) -> dict:
        tags = _json_list(character.tags)
        source_types = _json_list(character.source_types)
        reference_asset_ids = _json_list(character.reference_asset_ids)
        signature_items = _json_list(character.signature_items)
        expressions = _json_list(character.expressions)
        poses = _json_list(character.poses)

        role_labels = {
            "protagonist": "主角",
            "antagonist": "反派",
            "supporting": "配角",
            "extra": "路人",
        }
        source_type_labels = {
            "ai_generated": "AI生成",
            "local_material": "本地素材",
            "real_person": "真人对白",
            "anime_reference": "动漫原型",
            "stock_footage": "库存人物",
            "other": "其他",
        }

        return {
            "id": character.id,
            "name": character.name,
            "role": character.role,
            "workflow_source": getattr(character, "workflow_source", "unknown") or "unknown",
            "workflow_source_label": {
                "extract": "小说/正文提取",
                "character_first": "角色先行",
                "asset_import": "素材库导入",
                "unknown": "未标记",
            }.get(getattr(character, "workflow_source", "unknown") or "unknown", "未标记"),
            "extract_origins": extract_origins.get(character.id, []) if extract_origins else [],
            "role_label": role_labels.get(character.role, character.role),
            "source_types": source_types,
            "source_type_labels": [source_type_labels.get(st, st) for st in source_types],
            "appearance": character.appearance or "",
            "personality": character.personality or "",
            "costume_hint": character.costume_hint or "",
            "signature_items": signature_items,
            "expressions": expressions,
            "poses": poses,
            "visual_consistency": character.visual_consistency or "",
            "background": character.background or "",
            "age_range": character.age_range or "",
            "identity": _loads_json(getattr(character, "identity_json", "{}"), {}),
            "motivation": _loads_json(getattr(character, "motivation_json", "{}"), {}),
            "speech": _loads_json(getattr(character, "speech_json", "{}"), {}),
            "behavior": _loads_json(getattr(character, "behavior_json", "{}"), {}),
            "ability": _loads_json(getattr(character, "ability_json", "{}"), {}),
            "arc": _loads_json(getattr(character, "arc_json", "{}"), {}),
            "field_sources": _loads_json(getattr(character, "field_sources_json", "{}"), {}),
            "tags": tags,
            "portrait_url": character.portrait_url or "",
            "portrait_asset_id": character.portrait_asset_id or "",
            "portrait_node_id": character.portrait_node_id or None,
            "reference_asset_ids": reference_asset_ids,
            "is_favorite": character.is_favorite,
            "is_frozen": character.is_frozen,
            "use_count": character.use_count or 0,
            "last_used_at": str(character.last_used_at) if character.last_used_at else None,
            "created_at": str(character.created_at),
            "updated_at": str(character.updated_at) if character.updated_at else None,
        }

    def story_link_to_response(
        self,
        link: CharacterStoryLink,
        project: CreativeProject | None = None,
    ) -> dict[str, Any]:
        return {
            "id": link.id,
            "character_id": link.character_id,
            "story_id": link.story_id,
            "project_id": link.story_id,
            "project_title": project.title if project else "",
            "project_type": project.project_type if project else "",
            "world_id": link.world_id or "",
            "world_name": link.world_name or (project.title if project else ""),
            "usage_role": link.usage_role or "",
            "local_alias": link.local_alias or "",
            "local_identity": link.local_identity or "",
            "local_faction": link.local_faction or "",
            "local_status": link.local_status or "active",
            "local_costume": link.local_costume or "",
            "local_prompt_tags": _loads_json(link.local_prompt_tags, []),
            "ooc_notes": link.ooc_notes or "",
            "off_model_notes": link.off_model_notes or "",
            "bible_overrides": _loads_json(link.bible_overrides_json, {}),
            "visual_overrides": _loads_json(link.visual_overrides_json, {}),
            "extract_origin": getattr(link, "extract_origin", "") or "unknown",
            "extract_origin_label": extract_origin_label(getattr(link, "extract_origin", "") or "unknown"),
            "linked_at": str(link.linked_at) if link.linked_at else None,
            "updated_at": str(link.updated_at) if link.updated_at else None,
        }


from datetime import datetime


# 用户可在角色工作区直接编辑、需要标记为「用户填写」的字段
_USER_EDITABLE_PROVENANCE_FIELDS = (
    "appearance",
    "costume_hint",
    "personality",
    "background",
    "age_range",
    "visual_consistency",
    "identity",
    "motivation",
    "speech",
    "behavior",
    "ability",
    "arc",
)

_BIBLE_FIELD_MAP = {
    "identity": "identity_json",
    "motivation": "motivation_json",
    "speech": "speech_json",
    "behavior": "behavior_json",
    "ability": "ability_json",
    "arc": "arc_json",
}


def _loads_json(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value) if value else fallback
    except Exception:
        return fallback
