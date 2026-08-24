"""
YLCraft — 资产中枢核心模型
三层架构：AssetNode → AssetVersion → AssetRepresentation
树形标签系统 + 向量搜索 + 谱系追踪
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from pgvector.sqlalchemy import Vector

if TYPE_CHECKING:
    from app.db.models import (
        Character, CharacterStoryLink,
        Live2DModel, Live2DBone, Live2DMotion,
        WorkflowTemplate, WorkflowPreset, ComfyUITask, ComfyUINode,
        PlatformConnection, AIConnector, BookSource, Novel, NovelChapter
    )


class AssetType(str, Enum):
    """资产类型枚举"""
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    TEXT = "text"
    MODEL = "model"
    CHARACTER = "character"
    WORLD_SETTING = "world_setting"
    WORKFLOW = "workflow"
    THREE_D_MODEL = "3d_model"
    ANIMATION = "animation"
    SUBTITLE = "subtitle"
    COLLECTION = "collection"
    JIANYING_DRAFT = "jianying_draft"


class RelationType(str, Enum):
    """资产关系类型枚举"""
    DERIVED_FROM = "derived_from"
    USES = "uses"
    REFERENCES = "references"
    CONTAINS = "contains"
    VARIANT_OF = "variant_of"


class AssetNode(SQLModel, table=True):
    """资产根节点"""
    __tablename__ = "asset_nodes"

    id: str = Field(primary_key=True, sa_type=PGUUID(as_uuid=True))
    name: str = Field(index=True)
    asset_type: AssetType = Field(index=True)
    parent_id: Optional[str] = Field(None, foreign_key="asset_nodes.id", index=True, sa_type=PGUUID(as_uuid=True))

    thumbnail_url: Optional[str] = None
    metadata_json: dict = Field(default_factory=dict, sa_type=JSONB)
    tags_json: List[str] = Field(default_factory=list, sa_type=JSONB)

    use_count: int = Field(default=0, index=True)
    quality_score: Optional[float] = None
    phash: Optional[str] = Field(None, index=True)

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    authorized_source: str = Field(default="", max_length=64, description="授权来源标记，如 user_upload / platform_authorized")


class AssetVersion(SQLModel, table=True):
    """资产版本快照"""
    __tablename__ = "asset_versions"

    id: str = Field(primary_key=True, sa_type=PGUUID(as_uuid=True))
    asset_node_id: str = Field(foreign_key="asset_nodes.id", index=True, sa_type=PGUUID(as_uuid=True))
    version_number: int = Field(index=True)

    prompt_used: Optional[str] = None
    model_used: Optional[str] = None
    params_json: dict = Field(default_factory=dict, sa_type=JSONB)
    lineage_json: dict = Field(default_factory=dict, sa_type=JSONB)

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class AssetRepresentation(SQLModel, table=True):
    """资产文件表示"""
    __tablename__ = "asset_representations"

    id: str = Field(primary_key=True, sa_type=PGUUID(as_uuid=True))
    asset_version_id: str = Field(foreign_key="asset_versions.id", index=True, sa_type=PGUUID(as_uuid=True))

    file_path: str
    mime_type: str
    file_size: int
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None
    format: Optional[str] = None
    extra_json: dict = Field(default_factory=dict, sa_type=JSONB)


class AssetEmbedding(SQLModel, table=True):
    """资产向量嵌入"""
    __tablename__ = "asset_embeddings"

    id: str = Field(primary_key=True, sa_type=PGUUID(as_uuid=True))
    asset_node_id: str = Field(foreign_key="asset_nodes.id", index=True, unique=True, sa_type=PGUUID(as_uuid=True))
    embedding: Optional[List[float]] = Field(sa_type=Vector(1024))  # 默认 1024 维向量
    embedding_model: str = Field(default="paraphrase-multilingual-MiniLM-L12-v2")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AssetRelation(SQLModel, table=True):
    """资产谱系关系"""
    __tablename__ = "asset_relations"

    id: str = Field(primary_key=True, sa_type=PGUUID(as_uuid=True))
    source_id: str = Field(foreign_key="asset_nodes.id", index=True, sa_type=PGUUID(as_uuid=True))
    target_id: str = Field(foreign_key="asset_nodes.id", index=True, sa_type=PGUUID(as_uuid=True))
    relation_type: RelationType = Field(index=True)
    context_json: dict = Field(default_factory=dict, sa_type=JSONB)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Tag(SQLModel, table=True):
    """树形标签模型"""
    __tablename__ = "tags"

    id: str = Field(primary_key=True, sa_type=PGUUID(as_uuid=True))
    name: str = Field(index=True)
    parent_id: Optional[str] = Field(None, foreign_key="tags.id", index=True, sa_type=PGUUID(as_uuid=True))
    level: int = Field(0, index=True)
    path: str = Field(index=True)
    color: Optional[str] = None
    category: Optional[str] = Field(None, index=True)
    asset_count: int = Field(default=0, index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AssetTagLink(SQLModel, table=True):
    """资产-标签关联表"""
    __tablename__ = "asset_tag_links"

    id: str = Field(primary_key=True, sa_type=PGUUID(as_uuid=True))
    asset_node_id: str = Field(foreign_key="asset_nodes.id", index=True, sa_type=PGUUID(as_uuid=True))
    tag_id: str = Field(foreign_key="tags.id", index=True, sa_type=PGUUID(as_uuid=True))
    confidence: Optional[float] = None
    source: str = Field(default="manual")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AIModel(SQLModel, table=True):
    """AI 模型资产（扩展自 AssetNode）"""
    __tablename__ = "ai_models"

    id: str = Field(primary_key=True, sa_type=PGUUID(as_uuid=True))
    asset_node_id: str = Field(foreign_key="asset_nodes.id", index=True, sa_type=PGUUID(as_uuid=True))

    model_type: str = Field(index=True)
    base_model: str = Field(index=True)

    file_hash: str = Field(index=True)
    civitai_model_id: str = Field(default="", index=True)
    civitai_version_id: str = Field(default="")

    trigger_words: str = Field(default="")
    recommended_weight: float = Field(default=1.0)
    training_resolution: str = Field(default="")

    file_path: str
    file_size: int = Field(default=0)
    preview_urls: str = Field(default="[]")

