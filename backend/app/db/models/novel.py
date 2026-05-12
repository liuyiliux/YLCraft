"""
YLCraft — 小说章节数据模型
存储小说章节信息，支持按章节下载
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlmodel import SQLModel, Field


class NovelChapter(SQLModel, table=True):
    """小说章节表"""
    __tablename__ = "novel_chapters"
    
    id: str = Field(
        primary_key=True,
        default_factory=lambda: uuid.uuid4().hex,
    )
    
    # 关联的素材ID（Asset）
    asset_id: str = Field(index=True)
    
    # 章节序号
    chapter_index: int = Field(index=True)
    
    # 章节标题
    chapter_title: str = Field(default="")
    
    # 章节链接（用于下载）
    chapter_url: str = Field(default="")
    
    # 本地内容文件路径
    content_path: str = Field(default="")
    
    # 章节内容长度（字符数）
    content_length: int = Field(default=0)
    
    # 是否已下载到本地
    is_downloaded: bool = Field(default=False)
    
    # 创建时间
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        use_enum_values = True
