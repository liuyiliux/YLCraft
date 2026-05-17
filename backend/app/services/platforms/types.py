"""
YLCraft — 平台爬虫基础类型定义
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any


# =============================================================================
# 枚举定义
# =============================================================================

class ClientMode(str, Enum):
    """客户端模式"""
    API = "api"           # 直接 HTTP API 调用（快速，但可能被反爬）
    PATCHRIGHT = "patchright"  # 使用 Patchright 浏览器（慢，但能绕过反爬）


class SearchType(str, Enum):
    """搜索类型"""
    NOTE = "note"         # 笔记/视频
    VIDEO = "video"       # 视频（B站等平台专用，等同于 NOTE）
    USER = "user"         # 用户
    ARTICLE = "article"   # 文章/专栏
    SERIES = "series"     # 合集/系列
    BANGUMI = "bangumi"   # 番剧
    MOVIE = "movie"       # 影视
    LIVE = "live"         # 直播
    TOPIC = "topic"       # 话题


# =============================================================================
# 数据模型
# =============================================================================

@dataclass
class SearchResult:
    """通用搜索结果"""
    id: str
    title: str
    author: str
    author_id: str
    cover: str
    url: str
    platform: str
    type: str  # "note", "video", "user", "article", "series"
    
    # 统计信息
    likes: int = 0
    coins: int = 0
    comments: int = 0
    shares: int = 0
    collects: int = 0
    views: int = 0
    
    # 其他
    desc: str = ""
    create_time: str = ""
    duration: int = 0  # 视频时长（秒）
    followers: int = 0  # 粉丝数（用户搜索用）
    videos: int = 0  # 视频数（用户搜索用）

    # 原始数据
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NoteDetail:
    """通用笔记/视频详情（无水印）"""
    id: str
    title: str
    desc: str
    author: str
    author_id: str
    platform: str
    type: str  # "note", "video", "article"
    
    # 媒体资源（无水印）
    images: List[str] = field(default_factory=list)
    video: str = ""  # 无水印视频 URL
    video_cover: str = ""
    duration: int = 0  # 视频时长（秒）
    
    # 统计
    likes: int = 0
    coins: int = 0        # 投币（B站特有）
    comments: int = 0
    shares: int = 0
    collects: int = 0
    views: int = 0
    
    # 元数据
    tags: List[str] = field(default_factory=list)
    create_time: str = ""
    location: Optional[str] = None
    
    # 评论（可选）
    comments_list: List[Dict[str, Any]] = field(default_factory=list)
    
    # 原始数据
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UserProfile:
    """用户主页信息"""
    id: str
    name: str
    avatar: str
    platform: str
    
    # 统计
    followers: int = 0
    following: int = 0
    total_likes: int = 0
    total_videos: int = 0
    
    # 其他
    desc: str = ""
    verified: bool = False
    
    # 原始数据
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SeriesInfo:
    """合集/系列信息（B站等平台）"""
    id: str
    title: str
    cover: str
    platform: str
    author: str
    author_id: str
    
    # 视频列表
    video_ids: List[str] = field(default_factory=list)
    
    # 统计
    total_videos: int = 0
    total_play: int = 0
    
    # 原始数据
    raw_data: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# 搜索参数（平台特定）
# =============================================================================

@dataclass
class SearchParams:
    """通用搜索参数"""
    keyword: str
    max_results: int = 20
    search_type: SearchType = SearchType.NOTE
    sort_by: str = ""  # 排序方式，各平台自定义
    page: int = 1  # 页码

    # 平台特定参数（用 dict 传递）
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_string(cls, keyword: str, max_results: int = 20, search_type_str: str = "note", sort_by: str = "", page: int = 1, extra: Dict[str, Any] = None):
        """从字符串创建 SearchParams，支持自定义 search_type"""
        # 尝试匹配枚举，否则使用 NOTE
        try:
            st = SearchType(search_type_str)
        except ValueError:
            st = SearchType.NOTE
        return cls(
            keyword=keyword,
            max_results=max_results,
            search_type=st,
            sort_by=sort_by,
            page=page,
            extra=extra or {},
        )


# =============================================================================
# 客户端配置
# =============================================================================

@dataclass
class ClientConfig:
    """客户端配置"""
    platform: str
    mode: ClientMode = ClientMode.API
    cookie: str = ""
    
    # Patchright 特定
    use_patchright: bool = False
    patchright_headless: bool = False
    
    # 请求配置
    timeout: int = 30
    proxy: Optional[str] = None
    user_agent: str = ""
    
    # 重试配置
    max_retries: int = 3
    retry_delay: float = 1.0
