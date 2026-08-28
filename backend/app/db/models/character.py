"""
YLCraft — 角色数据模型
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import SQLModel, Field


class CharacterSourceType(str, Enum):
    AI_GENERATED = "ai_generated"
    LOCAL_MATERIAL = "local_material"
    REAL_PERSON = "real_person"
    ANIME_REFERENCE = "anime_reference"
    STOCK_FOOTAGE = "stock_footage"
    OTHER = "other"

    @classmethod
    def all(cls):
        return [e.value for e in cls]

    @classmethod
    def label(cls, value: str) -> str:
        labels = {
            "ai_generated": "AI生成",
            "local_material": "本地素材",
            "real_person": "真人对白",
            "anime_reference": "动漫原型",
            "stock_footage": "库存人物",
            "other": "其他",
        }
        return labels.get(value, value)


class CharacterRole(str, Enum):
    PROTAGONIST = "protagonist"
    ANTAGONIST = "antagonist"
    SUPPORTING = "supporting"
    EXTRA = "extra"


class CharacterWorkflowSource(str, Enum):
    """How a reusable character card entered YLCraft."""
    EXTRACT = "extract"
    CHARACTER_FIRST = "character_first"
    ASSET_IMPORT = "asset_import"
    UNKNOWN = "unknown"


class Character(SQLModel, table=True):
    """角色主表"""
    __tablename__ = "characters"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    name: str = Field(default="", index=True)
    role: str = Field(default=CharacterRole.SUPPORTING.value)
    workflow_source: str = Field(default=CharacterWorkflowSource.UNKNOWN.value, index=True, description="角色进入系统的流程来源")

    # 来源标签（JSON 数组存储）
    source_types: str = Field(default="[]")

    # 外观描述（重点区域，冻结后禁止修改）
    appearance: str = Field(default="", description="外貌描述，用于 AI 生图提示词")
    costume_hint: str = Field(default="", description="服装提示")
    signature_items: str = Field(default="[]", description="角色标志性物品/符号（JSON 数组）")
    expressions: str = Field(default="[]", description="角色常用表情（JSON 数组）")
    poses: str = Field(default="[]", description="角色常用姿态/动作（JSON 数组）")
    visual_consistency: str = Field(default="", description="立绘、分镜和漫画生图的一致性规则")

    # 其他描述
    personality: str = Field(default="", description="性格特点")
    background: str = Field(default="", description="背景故事")
    age_range: str = Field(default="", description="年龄范围，如 20-25岁")

    # Character Bible 分区（JSON 对象）
    identity_json: str = Field(default="{}", description="基础身份档案：别名、性别、种族、身高、组织、职位等")
    motivation_json: str = Field(default="{}", description="动机心理：欲望、恐惧、目标、价值观、执念等")
    speech_json: str = Field(default="{}", description="语言语态：口头禅、句式、语速、禁用话术、方言等")
    behavior_json: str = Field(default="{}", description="行为与 OOC 边界：习惯、应激反应、底线、绝不会做的事")
    ability_json: str = Field(default="{}", description="能力体系：技能、短板、限制、代价、知识特长等")
    arc_json: str = Field(default="{}", description="人物弧光：前中后期变化、高光、退场、剧情雷点")
    field_sources_json: str = Field(default="{}", description="字段来源标记：original / ai_inferred / unset")

    # 立绘
    portrait_url: str = Field(default="", description="立绘图片 URL")
    portrait_asset_id: str = Field(default="", description="关联素材资产 ID（旧版 Asset 表）")
    portrait_node_id: Optional[str] = Field(default=None, description="资产中枢 AssetNode ID（新版三层架构）", index=True)

    # 关联的参考素材
    reference_asset_ids: str = Field(default="[]", description="关联素材资产 ID 列表（JSON）")

    # 自定义标签（JSON 数组）
    tags: str = Field(default="[]")

    # 收藏/冻结
    is_favorite: bool = Field(default=False)
    is_frozen: bool = Field(default=False, description="冻结后禁止修改外观描述，保持一致性")

    # 引用统计
    use_count: int = Field(default=0)
    last_used_at: Optional[datetime] = Field(default=None)

    # 时间戳
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        use_enum_values = True


class CharacterStoryLink(SQLModel, table=True):
    """角色在某个创作项目/世界中的使用配置。"""
    __tablename__ = "character_story_links"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    character_id: str = Field(index=True)
    story_id: str = Field(index=True)
    world_id: str = Field(default="", index=True)
    world_name: str = Field(default="", index=True)
    usage_role: str = Field(default="", index=True)
    local_alias: str = Field(default="")
    local_identity: str = Field(default="")
    local_faction: str = Field(default="", index=True)
    local_status: str = Field(default="active", index=True)
    local_costume: str = Field(default="")
    local_prompt_tags: str = Field(default="[]")
    ooc_notes: str = Field(default="")
    off_model_notes: str = Field(default="")
    bible_overrides_json: str = Field(default="{}")
    visual_overrides_json: str = Field(default="{}")
    extract_origin: str = Field(
        default="unknown",
        index=True,
        description="角色在该项目中的提取来源：uploaded_novel / imported_novel / original_outline",
    )
    linked_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class CharacterRelationship(SQLModel, table=True):
    """角色之间的显式关系，供角色册与关系图谱复用。"""
    __tablename__ = "character_relationships"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    character_id: str = Field(foreign_key="characters.id", index=True)
    related_character_id: str = Field(foreign_key="characters.id", index=True)
    relation_type: str = Field(default="", index=True)
    relation_note: str = Field(default="")
    source: str = Field(default="")
    is_directed: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
