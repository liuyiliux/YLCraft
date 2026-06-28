"""
YLCraft — 角色服务层
"""

from __future__ import annotations

import json
from typing import Optional

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.character import Character, CharacterStoryLink, CharacterRole


class CharacterService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(
        self,
        keyword: str | None = None,
        source_type: str | None = None,
        role: str | None = None,
        tag: str | None = None,
        is_favorite: bool | None = None,
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
        for field in ["source_types", "tags", "reference_asset_ids"]:
            if field in kwargs and kwargs[field] is not None:
                kwargs[field] = json.dumps(kwargs[field], ensure_ascii=False)
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
        for field in ["source_types", "tags", "reference_asset_ids"]:
            if field in kwargs and kwargs[field] is not None:
                kwargs[field] = json.dumps(kwargs[field], ensure_ascii=False)
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
        tags = json.loads(character.tags) if character.tags else []
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
        tags = json.loads(character.tags) if character.tags else []
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
            tags = json.loads(c.tags) if c.tags else []
            for t in tags:
                all_tags.add(t)
        return sorted(all_tags)

    async def link_to_story(self, character_id: str, story_id: str):
        link = CharacterStoryLink(character_id=character_id, story_id=story_id)
        self.session.add(link)
        character = await self.get_by_id(character_id)
        if character:
            character.use_count = (character.use_count or 0) + 1
            from datetime import datetime
            character.last_used_at = datetime.now()
        await self.session.flush()

    def to_response(self, character: Character) -> dict:
        tags = json.loads(character.tags) if character.tags else []
        source_types = json.loads(character.source_types) if character.source_types else []
        reference_asset_ids = json.loads(character.reference_asset_ids) if character.reference_asset_ids else []

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
            "role_label": role_labels.get(character.role, character.role),
            "source_types": source_types,
            "source_type_labels": [source_type_labels.get(st, st) for st in source_types],
            "appearance": character.appearance or "",
            "personality": character.personality or "",
            "costume_hint": character.costume_hint or "",
            "background": character.background or "",
            "age_range": character.age_range or "",
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


from datetime import datetime
