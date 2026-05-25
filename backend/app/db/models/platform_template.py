"""
平台生成模板模型

借鉴 yiliu/yiliu 的 platform_templates.yaml，用 DB 存储平台提示词模板。
每个平台（小红书/抖音/微信/头条）有两套模板：
- outline_template: LLM 将 topic 分析为结构化大纲
- image_template: 将大纲每页渲染为生图提示词
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.dialects.postgresql import UUID
from sqlmodel import SQLModel, Field


class PlatformTemplate(SQLModel, table=True):
    """平台生成模板
    
    模板变量说明（outline_template）：
        {topic} - 用户输入的主题
    
    模板变量说明（image_template）：
        {user_topic} - 用户原始输入主题
        {topic} - 当前平台的大纲标题
        {page_content} - 当前页面的内容描述
        {page_type} - 页面类型（封面/内容/总结）
        {full_outline} - 完整的大纲文本（包含标题+文案+所有页面）
        {copywriting} - 总文案（如果有的话）
    """
    __tablename__ = "platform_templates"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        sa_type=UUID(as_uuid=True),
    )
    platform: str = Field(max_length=30, unique=True, index=True, description="平台标识: xiaohongshu/douyin/wechat/toutiao")
    name: str = Field(max_length=50, description="平台中文名: 小红书/抖音/微信/头条")
    outline_template: str = Field(description="LLM 大纲模板, 变量 {topic}")
    image_template: str = Field(description="生图提示词模板, 变量 {user_topic}{topic}{page_content}{page_type}{full_outline}{copywriting}")
    video_template: Optional[str] = Field(default=None, description="视频模板（可选）")
    default_size: str = Field(default="1024x1024", max_length=20)
    is_active: bool = Field(default=True)
    sort_order: int = Field(default=0)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"server_default": "now()"},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"server_default": "now()", "onupdate": "now()"},
    )
