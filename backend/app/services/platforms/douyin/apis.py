"""
YLCraft — 抖音 Web API 端点定义

所有端点均由 **browser-skill 接管用户已登录 Chrome 抓包确认**（2026-09-26）。
证据导出在 `.local/douyin-xhs-search-capture.json`（已脱敏，不入库）。

搜到的真实端点：
  - GET /aweme/v1/web/general/search/single/    综合搜索（列表页，本次实现用它）
  - GET /aweme/v1/web/general/search/stream/    搜索（流式，页面首屏用）

⚠️ 抓包前不要猜端点。番茄那次就是因为只抓了一个入口，
   得出"没有建章接口"的错误否定结论（详见 ADDING_A_PLATFORM 陷阱⓪）。

=============================================================================
⚠️ 重要限制：抖音搜索在**自动化浏览器**里拿不到数据（2026-09-26 实测）
=============================================================================

同一账号、同一 Cookie、同一时刻的对照实验：

    用户真实 Chrome（非自动化）    → count=5，有真实结果
    Patchright 自动化浏览器        → count=0（data=[]，status_msg 为空）
                                     且**账号接口可能是正常的**（user=True）

即抖音限制的是「自动化环境的搜索接口」，不是 Cookie 失效。

已排除的可能（都实测过，无改善）：
  × Cookie 问题        —— 真实 Chrome 用同一 Cookie 能搜到
  × 登录态问题         —— profile 接口有时返回 user=True
  × UA 版本不匹配      —— 改成真实 Chrome/154 无效
  × 启动参数暴露       —— 换成干净参数无效
  × navigator.webdriver —— Patchright 已内置反检测，实测为 false
  × navigator.languages / window.chrome.app —— 补齐后仍无效

开源项目的做法（搜索结果，供后续参考）：
  - MediaCrawler / TikTokDownloader 等都在实现 **a_bogus 签名**
    （另有 x-bogus、X-Gnarly 等变体）
  - 抖音前端把签名函数藏在闭包里，页面 window 上**取不到**
    （实测 `window.byted_acrawler` 等均为 undefined）
  - 因此要绕过需自行移植签名算法（数百行的 JS 逆向），
    且算法会随版本变化，维护成本高

当前的取舍：
  **不实现签名，而是如实报错**（见 client.py 的 PlatformUnavailableError）。
  用户看到的是"抖音限制了自动化环境的搜索接口，可稍后重试/改用其它平台"，
  而不是误导性的"找到 0 条结果"。
"""
from __future__ import annotations

# 抖音 Web 基础域名
BASE_URL = "https://www.douyin.com"

# =============================================================================
# 搜索 API（2026-09-26 抓包确认）
# =============================================================================

# 综合搜索（单次返回一页）
# 实测：keyword="小说" → status_code=0，has_more=1，cursor=5
SEARCH_SINGLE = "/aweme/v1/web/general/search/single/"

# 搜索流（页面首屏使用，响应结构与 single 类似）
SEARCH_STREAM = "/aweme/v1/web/general/search/stream/"

# =============================================================================
# 登录态 / 账号（2026-09-26 实测确认）
# =============================================================================

# 当前登录用户（GET）
# 实测：未登录 → {"status_code": 8, "status_msg": "用户未登录", "user": null}
#       已登录 → {"status_code": 0, "user": {"uid": ..., "nickname": ...}}
# 这是比"URL 含某字符串"可靠得多的登录判据（见 cookies/platforms/douyin.py）。
PROFILE_SELF = "/aweme/v1/web/user/profile/self/"

# =============================================================================
# 固定请求参数（抓包得到的稳定值，非签名）
# -----------------------------------------------------------------------------
# 与番茄不同：抖音这组搜索接口实测**不需要** msToken / a_bogus / X-Bogus 签名，
# 带上 Cookie 即可返回 status_code=0。下面这些是设备/浏览器指纹类的常量，
# 用抓包时的真实值即可；若后续服务端收紧，再改为动态提取。
# =============================================================================

DEFAULT_AID = "6383"                    # 抖音 Web 端固定 aid
DEFAULT_CHANNEL = "channel_pc_web"
DEFAULT_DEVICE_PLATFORM = "webapp"
DEFAULT_SEARCH_CHANNEL = "aweme_general"
DEFAULT_SEARCH_SOURCE = "normal_search"
DEFAULT_LIST_TYPE = "single"
DEFAULT_PLATFORM = "PC"
DEFAULT_PC_CLIENT_TYPE = "1"

# 搜索类型：1=综合（视频+图文混合，页面默认）
SEARCH_TYPE_GENERAL = 1


def build_search_params(
    keyword: str,
    offset: int = 0,
    count: int = 10,
) -> dict[str, str]:
    """构造搜索查询参数（抓包确认的最小可用集）。

    抓包时浏览器还带了一堆指纹参数（screen_width/cpu_core_num/engine_name…），
    实测**不带也能返回 status_code=0**，所以这里只保留必要的几个，
    避免把一堆无关指纹硬编码进仓库。
    """
    return {
        "aid": DEFAULT_AID,
        "device_platform": DEFAULT_DEVICE_PLATFORM,
        "channel": DEFAULT_CHANNEL,
        "search_channel": DEFAULT_SEARCH_CHANNEL,
        "search_source": DEFAULT_SEARCH_SOURCE,
        "keyword": keyword,
        "search_type": str(SEARCH_TYPE_GENERAL),
        "list_type": DEFAULT_LIST_TYPE,
        "pc_client_type": DEFAULT_PC_CLIENT_TYPE,
        "platform": DEFAULT_PLATFORM,
        "query_correct_type": "1",
        "need_filter_settings": "1",
        "is_filter_search": "0",
        "enable_history": "1",
        "offset": str(offset),
        "count": str(count),
    }
