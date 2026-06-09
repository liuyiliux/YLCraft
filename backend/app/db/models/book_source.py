"""
YLCraft — 书源数据模型
存储阅读App格式的书源配置
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, Text
from sqlmodel import SQLModel, Field


class BookSource(SQLModel, table=True):
    """书源表（兼容阅读App格式）"""
    __tablename__ = "book_sources"
    
    id: str = Field(
        primary_key=True,
        default_factory=lambda: uuid.uuid4().hex,
    )
    
    # 书源名称
    book_source_name: str = Field(index=True)
    
    # 书源URL（域名）
    book_source_url: str = Field(index=True, unique=True)
    
    # 书源类型：0=文本，1=音频，2=图片
    book_source_type: int = Field(default=0)
    
    # 是否启用（阅读App格式）
    enabled: bool = Field(default=True)
    
    # 自定义排序权重
    custom_order: int = Field(default=0)
    
    # 搜索URL
    search_url: str = Field(default="")
    
    # 书源分组
    book_source_group: str = Field(default="")

    # 是否支持发现
    explore: bool = Field(default=False)

    # HTTP 相关
    cookie: str = Field(default="")
    header: str = Field(default="")

    # 登录相关
    login_url: str = Field(default="")
    login_ui: str = Field(default="")
    login_check_js: str = Field(default="")

    # 书源元数据
    cover_url: str = Field(default="")
    book_source_comment: str = Field(default="")
    weight: int = Field(default=0)
    respond_time: int = Field(default=0)
    last_update_time: str = Field(default="")

    # 规则JSON（存储为字符串）
    rule_search: str = Field(default="")   # JSON字符串
    rule_book_info: str = Field(default="") # JSON字符串
    rule_toc: str = Field(default="")       # JSON字符串
    rule_content: str = Field(default="")   # JSON字符串
    rule_explore: str = Field(default="")   # JSON字符串

    # YLCraft 规则格式元数据
    rule_format: str = Field(default="legado", index=True)
    rule_version: str = Field(default="")
    ylcraft_rule: str = Field(default="", sa_column=Column(Text, nullable=False, default=""))
    original_format: str = Field(default="")
    original_source: str = Field(default="", sa_column=Column(Text, nullable=False, default=""))
    migration_log: str = Field(default="", sa_column=Column(Text, nullable=False, default=""))
    
    # 用户是否启用（我们的扩展字段）
    enabled_by_user: bool = Field(default=True)
    
    # 创建/更新时间
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        use_enum_values = True
