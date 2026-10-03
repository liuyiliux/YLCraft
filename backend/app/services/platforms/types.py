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


# =============================================================================
# 异常
# =============================================================================
#
# ## 为什么要做「类型化异常体系」（2026-10-01 重构）
#
# 原来判断"这个错误该不该降级到 yt-dlp / 该不该重试"靠**字符串匹配**：
#
#     if any(k in msg for k in ("HTTP 461", "未登录", "风控", "antispam", ...)):
#         raise          # 不降级
#     return []          # 否则降级（可能吞成空）
#
# **这是全项目最脆弱的一处**：任何一次改错误文案（比如把"未登录"
# 改成"登录已过期"）都会让判断**静默失效** —— 异常被吞成 `return []`，
# 用户看到"找到 0 条结果"，而真相是被风控/登录失效。
# 本仓库为此反复踩坑（文档里记录了 4 次）。
#
# 改成**类型化异常 + 分类属性**后：
#   · 判断走 `except`，不依赖文案
#   · 每个异常自己声明 `retryable` / `should_fallback`，
#     调用方不用猜（平台最清楚自己抛的是什么）
#
# ⚠️ 新增异常时**必须**声明这两个语义，否则调用方的策略会不明确。


class PlatformError(RuntimeError):
    """所有平台侧错误的基类。

    ## 两个分类属性（调用方据此决策，不靠文案猜）

        retryable        该不该重试？
        should_fallback  该不该降级到 yt-dlp 兜底？

    语义边界：
      · 风控/登录失效 → **不重试**（重试只会更糟：可能升级为封号），
        **不降级**（yt-dlp 只会再空一次，把"被拦"伪装成"没结果"）
      · 网络抖动/超时 → **可重试**，也可降级
    """

    #: 该不该重试（默认不安全：宁可少重试）
    retryable: bool = False
    #: 该不该降级到 yt-dlp 兜底（默认**不降级** —— 降级会伪装成"没搜到"）
    should_fallback: bool = False


class LoginExpiredError(PlatformError):
    """**登录态失效 / 未登录**（2026-09-30 加）。

    ## 为什么需要这个独立异常

    原来各平台 `get_self_profile()` 失败时**静默 `return None`** ——
    用户看到的是**空白**，不知道是登录态失效了。

    实测各平台的"登录态失效"信号都不一样：

        抖音   status_code=8（未登录）/ 0+空 user（风控降级）
        微博   /api/config 的 login=false
        小红书 被重定向到 /login
        X      HTTP 401/403 + TwitterAuthError
        快手   result=2（未登录）/ 109（中间态）

    **统一成一个异常的好处**：
      · API 层可以把它映射成 **401**（而不是 500）
      · 前端可以据此提示"请重新登录"，而不是"加载失败"

    ⚠️ **不要用它表示"风控"** —— 风控要等，登录失效要重新登录。
    """
    retryable = False
    should_fallback = False


class RiskControlError(PlatformError):
    """**风控 / 人机验证 / 账号异常**（2026-10-01 加）。

    实测各平台的风控信号：

        小红书   HTTP 461（Verifytype=217，人机验证）
                 code=300011（账号异常）/ 300012（IP 被封）
        抖音     HTTP 200 + **空 body**（"用空响应表示拒绝"）
                 status_code=0 但 user=null（风控降级）
        微博     ok=-100（缺 session cookie）
        快手     result=2001 + "antispam need captcha"

    ## 为什么**不重试**也不**降级**

      · 重试：风控期越试越糟，可能升级为**封号**。
        正确做法是**等待**或**换 IP/换账号**。
      · 降级到 yt-dlp：yt-dlp 只会再返回一次空 ——
        把"被风控拦了"伪装成"关键词没结果"（本仓库的老毛病）。
    """
    retryable = False
    should_fallback = False


class NetworkError(PlatformError):
    """**网络问题**（超时 / 连不上 / DNS）。

    与风控的**关键区别**：这类**可以重试**，也**可以降级**
    （yt-dlp 可能走另一条路成功）。

    ⚠️ 实测教训：VPN 断开时 t.me / youtube 会超时，
    这**不是**"平台封了我们"，重试/稍后再试是合理的。
    """
    retryable = True
    should_fallback = True


class ContentNotFoundError(PlatformError):
    """内容不存在 / 已删除（笔记、视频、频道）。

    · 重试无意义（它就是不在了）
    · **不降级** —— 降级到 yt-dlp 也找不到，只会浪费一次请求
    """
    retryable = False
    should_fallback = False


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
        """从字符串创建 SearchParams，支持自定义 search_type。

        ## ⚠️ 未知值**不再静默降级**（2026-10-03 修）

        原来是：
            try:
                st = SearchType(search_type_str)
            except ValueError:
                st = SearchType.NOTE      # ← 静默改成"笔记"

        而 Telegram 的三个数据源**都不在枚举里**：
            channel（频道消息） / dialogs（我的频道） / saved（我的收藏）
            joined（已加入搜索）也不是枚举值。

        于是 `search_type="saved"` 被悄悄改成 `NOTE`，
        `TelegramClient.search` 走默认分支 `_search_channel("")`，
        报「请填写频道 username」—— 用户看到的是
        **"我的收藏需要填频道名"**，完全摸不着头脑。

        这正是本仓库反复记录的"假支持"：参数看起来传了、没报错，
        实际走的是另一条完全不同的路径。

        修法：枚举不认识的值**原样保留**成字符串，让平台自己决定怎么处理
        （Telegram 的 `client.search` 就是按字符串分派的）。
        真的非法值由平台自己报 —— 那才是**它该报的错**。
        """
        try:
            st = SearchType(search_type_str)
        except ValueError:
            # ⚠️ 不再降级成 NOTE —— 平台的自定义 search_type 会被静默改写，
            # 导致走错分支（实测 Telegram 的 saved/dialogs 全中招）。
            st = search_type_str or SearchType.NOTE
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

    # 平台连接 ID。用于：
    #   · 缓存键的一部分（不同账号结果不同，不能互相串）
    #   · 浏览器会话复用（同一连接复用同一个浏览器上下文）
    conn_id: str = ""

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
