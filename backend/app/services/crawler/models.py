"""
YLCraft — 爬虫数据模型
支持搜索笔记/用户、获取笔记详情（无水印）
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional, List


# =============================================================================
# 笔记详情模型（无水印）
# =============================================================================

class NoteDetail(BaseModel):
    """笔记详情（无水印）"""
    id: str = Field(..., description="笔记ID")
    platform: str = Field(..., description="平台: xhs/dy/ks")
    title: str = Field("", description="标题")
    desc: str = Field("", description="描述/正文")
    images: List[str] = Field(default_factory=list, description="无水印图片URL列表")
    video: str = Field("", description="无水印视频URL")
    author: str = Field("", description="作者名称")
    author_id: str = Field("", description="作者ID")
    likes: int = Field(0, description="点赞数")
    comments: int = Field(0, description="评论数")
    shares: int = Field(0, description="分享数")
    collect_count: int = Field(0, description="收藏数")
    create_time: str = Field("", description="发布时间")
    tags: List[str] = Field(default_factory=list, description="标签列表")
    raw_data: dict = Field(default_factory=dict, description="原始数据")


# =============================================================================
# 搜索筛选条件
# =============================================================================

class SearchFilter(BaseModel):
    """搜索筛选条件"""
    sort_by: str = Field("default", description="排序方式: default/time/heat")
    time_range: str = Field("all", description="时间范围: all/1d/7d/30d")
    note_type: str = Field("all", description="笔记类型: all/video/image/article")


# =============================================================================
# 请求/响应模型
# =============================================================================

class SearchEnhancedRequest(BaseModel):
    """增强搜索请求"""
    platform: str = Field(..., description="平台: xhs/dy/ks")
    keyword: str = Field(..., description="搜索关键词")
    search_type: str = Field("note", description="搜索类型: note/user")
    max_results: int = Field(20, description="最大结果数", ge=1, le=100)
    filters: dict = Field(default_factory=dict, description="筛选条件")


class NoteDetailResponse(BaseModel):
    """笔记详情响应"""
    success: bool = True
    data: Optional[NoteDetail] = None
    message: str = ""


class FetchNoWatermarkRequest(BaseModel):
    """批量获取无水印资源请求"""
    platform: str = Field(..., description="平台: xhs/dy/ks")
    note_ids: List[str] = Field(..., description="笔记ID列表")
