"""
YLCraft — 向量库数据模型
用于小说内容语义搜索
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlmodel import SQLModel, Field


class VectorDocument(SQLModel, table=True):
    """向量化文档表"""
    __tablename__ = "vector_docs"
    
    id: str = Field(
        primary_key=True,
        default_factory=lambda: uuid.uuid4().hex,
    )
    
    # 关联的素材ID
    asset_id: str = Field(index=True)
    
    # 文本块索引（用于定位原文）
    chunk_index: int = Field(default=0)
    
    # 原始文本（用于显示匹配片段）
    content: str = Field(default="")
    
    # 向量（JSON数组存储）
    embedding: str = Field(default="")
    
    # 额外元数据（JSON字符串）
    meta_json: str = Field(default="{}")
    
    # 创建时间
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        use_enum_values = True


class VectorIndex(SQLModel, table=True):
    """向量索引元数据表"""
    __tablename__ = "vector_indexes"
    
    id: str = Field(primary_key=True)
    
    # 索引名称
    name: str = Field(index=True)
    
    # 向量维度
    dim: int = Field(default=384)
    
    # Embedding 模型名称
    model_name: str = Field(default="all-MiniLM-L6-v2")
    
    # 已索引文档数
    doc_count: int = Field(default=0)
    
    # 创建时间
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        use_enum_values = True
