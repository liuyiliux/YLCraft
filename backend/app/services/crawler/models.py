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
    platform: str = Field(..., description="平台: xhs/dy/ks/bili")
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
    duration: int = Field(0, description="视频时长（秒）")
    create_time: str = Field("", description="发布时间")
    tags: List[str] = Field(default_factory=list, description="标签列表")
    raw_data: dict = Field(default_factory=dict, description="原始数据")


# =============================================================================
# 搜索筛选条件
# =============================================================================

class SearchFilter(BaseModel):
    """搜索筛选条件"""
    sort_by: str = Field("default", description="排序方式")
    time_range: str = Field("all", description="时间范围")
    note_type: str = Field("all", description="笔记类型")


# =============================================================================
# 搜索请求
# =============================================================================

class SearchRequest(BaseModel):
    """搜索请求"""
    keyword: str = Field(..., description="搜索关键词")
    platform: str = Field(..., description="平台")
    search_type: str = Field("search", description="搜索类型")
    page: int = Field(1, description="页码")
    page_size: int = Field(20, description="每页数量")
    filter: Optional[SearchFilter] = None


# =============================================================================
# 搜索结果
# =============================================================================

class CrawlerResult(BaseModel):
    """搜索结果"""
    id: str = Field(..., description="内容ID")
    platform: str = Field(..., description="平台")
    type: str = Field("video", description="类型: video/image/article/user")
    title: str = Field("", description="标题")
    desc: str = Field("", description="描述")
    cover: str = Field("", description="封面图")
    url: str = Field("", description="详情URL")
    author: str = Field("", description="作者")
    author_id: str = Field("", description="作者ID")
    likes: int = Field(0, description="点赞数")
    comments: int = Field(0, description="评论数")
    shares: int = Field(0, description="分享数")
    collect_count: int = Field(0, description="收藏数")
    video_url: str = Field("", description="视频URL（无水印）")
    images: List[str] = Field(default_factory=list, description="图片URL列表（无水印）")
    raw_data: dict = Field(default_factory=dict, description="原始数据")


# =============================================================================
# 增强搜索请求
# =============================================================================

class SearchEnhancedRequest(BaseModel):
    """增强搜索请求（支持 MediaCrawler 多平台）"""
    keyword: str = Field(..., description="搜索关键词")
    platform: str = Field(..., description="平台")
    search_type: str = Field("search", description="搜索类型: search/user/creator")
    page: int = Field(1, description="页码")
    page_size: int = Field(20, description="每页数量")
    sort_by: str = Field("default", description="排序")
    time_range: str = Field("all", description="时间范围")
    note_type: str = Field("all", description="笔记类型")


# =============================================================================
# 笔记详情响应
# =============================================================================

class NoteDetailResponse(BaseModel):
    """笔记详情响应"""
    success: bool = True
    data: Optional[NoteDetail] = None
    message: str = ""


# =============================================================================
# 无水印资源获取请求
# =============================================================================

class FetchNoWatermarkRequest(BaseModel):
    """获取无水印资源请求"""
    platform: str = Field(..., description="平台")
    note_ids: List[str] = Field(..., description="笔记ID列表")
