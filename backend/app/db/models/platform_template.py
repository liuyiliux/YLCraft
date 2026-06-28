"""
平台生成模板模型

借鉴 yiliu/yiliu 的 platform_templates.yaml，用 DB 存储平台提示词模板。
每个平台（小红书/抖音/微信/头条）有两套模板：
- outline_template: LLM 将 topic 分析为结构化大纲
- image_template: 将大纲每页渲染为生图提示词

后续也复用这张表管理创作项目 prompt 模板：
- template_scope: image_platform / creative_project
- template_stage: platform / outline / chapter_plan / script / storyboard
- system_template: 可选 system 角色提示词，创作项目生成时优先使用

page_structure（JSONB）定义平台默认页面结构，驱动空白大纲创建和前端渲染：
  { "default_pages": [{"type":"封面"}, {"type":"内容"}, {"type":"内容"}, {"type":"总结"}] }
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlmodel import SQLModel, Field


class PlatformTemplate(SQLModel, table=True):
    """平台生成模板

    模板变量说明（outline_template）：
        {topic} - 用户输入的主题
        {page_structure} - 平台默认页面结构（JSON 文本，供 LLM 参考）

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
    platform: str = Field(max_length=30, unique=True, index=True, description="模板标识: xiaohongshu/douyin/creative_outline")
    name: str = Field(max_length=50, description="模板名称: 小红书/抖音/故事大纲")
    template_scope: str = Field(default="image_platform", max_length=40, index=True, description="模板用途: image_platform/creative_project")
    template_stage: str = Field(default="platform", max_length=40, index=True, description="模板阶段: platform/outline/chapter_plan/script/storyboard")
    description: Optional[str] = Field(default=None, description="模板说明")
    system_template: str = Field(
        default="",
        sa_column=Column(Text, nullable=False, server_default=""),
        description="System 角色提示词；为空时使用业务默认 system prompt",
    )
    outline_template: str = Field(description="LLM 大纲模板, 变量 {topic}{page_structure}")
    image_template: str = Field(default="", description="生图提示词模板, 变量 {user_topic}{topic}{page_content}{page_type}{full_outline}{copywriting}")
    page_structure: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB)
    )
    variables: dict = Field(
        default_factory=dict,
        sa_column=Column(JSONB),
        description="模板可用变量说明",
    )
    video_template: Optional[str] = Field(default=None, description="视频模板（可选）")
    default_size: str = Field(default="1024x1024", max_length=20)
    is_active: bool = Field(default=True)
    sort_order: int = Field(default=0)
    created_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"server_default": "now()"},
    )
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"server_default": "now()", "onupdate": "now()"},
    )
