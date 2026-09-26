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

## 已排除的可能（都实测过，无改善）

  × Cookie 问题         —— 真实 Chrome 用同一 Cookie 能搜到
  × 登录态问题          —— profile 接口有时返回 user=True
  × UA 版本不匹配       —— 改为真实 Chrome/154 无效
  × 启动参数暴露        —— 换干净参数无效
  × navigator.webdriver —— Patchright 已内置反检测，实测 false
  × languages / chrome.app —— 补齐指纹后仍无效
  × 参数个数            —— 14 个与 32 个都试过，无差别
  × **a_bogus 签名**    —— 见下

## 关于 a_bogus（重要，避免重复劳动）

开源项目（cv-cat/DouYin_Spider、MediaCrawler、TikTokDownloader 等）
**都实现了 a_bogus 签名**，看起来像是缺失的关键。

实测做了完整验证：从 DouYin_Spider 取来 528KB 的 `static/dy_ab.js`
（webpack bundle，导出 `get_ab(query, data)`），用 Node + jsrsasign 跑通，
成功生成 164 字符的合法签名，然后对照调用：

    完整参数 + 不带签名  → count=5  ✅
    完整参数 + 带 a_bogus → count=0  ❌（签名反而画蛇添足）

**结论：a_bogus 不是缺失项，加了没用。** 该 528KB 第三方代码**未采纳**，
不要因为"开源项目都这么做"就再引入一次。

## 真正的规律：不稳定，但成功率约 90%（48 次采样）

同一脚本、同一 Cookie、同一参数，多轮采样：

    run1  6/6   成功（间隔 3s）
    run2  0/6   失败（3 分钟后，同脚本）
    run3  6/20  成功（前 6 成功，之后连续 14 次失败）
    run4  15/15 成功（间隔 1s）
    run5  8/8   成功（不带 webid）
    run6  8/8   成功（带 webid）

共 **48 次里 43 次成功（约 90%）**，失败后隔一会儿能恢复，
**没有稳定复现的失败模式**。所以「空结果 → 稍等重试一次」是有效策略
（已实现在 client.search）。

## 上游权威结论：抖音改了校验方式

TikTokDownloader 的 issue #600 是**完全相同的症状**：
"采集搜索结果数据(抖音)…四个类目均无法使用，输入任何内容都提示搜索结果为空"，
而热榜、用户主页等功能正常。

项目作者（JoeanAmier）的回复：

    「经测试似乎需要新算法，新算法尚未开源。」

Bot 的更详细分析补充：
  - 抖音已**下线或限制部分旧版搜索接口**，**只有综合搜索偶尔还能用**
    （与我们实测的"general 有时成功"完全吻合）
  - xbogus 参数编码方式与新版网页不一致，请求被判无效
  - Cookie 不完整（尤其 msToken）或请求头不全也会被判异常访问

即：**这不是我们实现的问题**，是抖音改了搜索接口的校验方式，
且新算法尚未公开。当前策略（重试 + 如实报错）是合理的工程取舍。

## 附：试过但**无效**的手段（避免重复劳动）

  - a_bogus 签名（见上）
  - 手动注入 secsdk / webmssdk / security-secsdk 脚本（脚本可下载，
    但注入后 window.bdms / byted_acrawler / secsdk 仍为 undefined）
  - 补 webid 查询参数（MediaCrawler 的 get_web_id() 算法，对照测试无差别）
  - 补齐 UA / languages / chrome.app 指纹
  - 调整请求频率（1s 间隔反而 15/15 全成功，2.5s 间隔第 7 次就失败——
    说明与频率无关）

## 当前的取舍

  **不实现签名、不硬试**：
  「空结果重试一次」+ 仍失败则如实报错
  （见 client.py 的 PlatformUnavailableError）。
  用户看到的是"抖音限制了自动化环境…可稍后重试"，
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

# =============================================================================
# 搜索范围（search_channel）——2026-09-26 由 URL 抓包确认
# -----------------------------------------------------------------------------
# 抖音搜索页有四类页签，点击后 URL 变成 ?type=xxx，对应请求的 search_channel：
#     /search/小说?type=general   综合
#     /search/小说?type=video     视频
#     /search/小说?type=user      用户
#     /search/小说?type=live      直播
# 这些是**实测抓到的真实值**，不是猜的。
# =============================================================================

SEARCH_CHANNELS: dict[str, str] = {
    "general": "aweme_general",          # 综合（默认）
    "video": "aweme_video",              # 视频
    "user": "aweme_user",                # 用户
    "live": "aweme_live",                # 直播
}

# 前端传进来的 search_type 别名 → 上述键
SEARCH_TYPE_ALIASES: dict[str, str] = {
    "note": "general",      # 前端「笔记/视频」统称
    "video": "video",
    "user": "user",
    "live": "live",
    "general": "general",
}


def resolve_search_channel(search_type: str | None) -> str:
    """把前端的 search_type 解析成抖音的 search_channel。

    未知值回退到综合（不抛错——用户选了没实现的类型时，
    给"综合"结果比给报错更有用）。
    """
    key = SEARCH_TYPE_ALIASES.get((search_type or "").strip().lower(), "general")
    return SEARCH_CHANNELS.get(key, SEARCH_CHANNELS["general"])


def build_search_params(
    keyword: str,
    offset: int = 0,
    count: int = 10,
    search_channel: str = DEFAULT_SEARCH_CHANNEL,
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
        "search_channel": search_channel or DEFAULT_SEARCH_CHANNEL,
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
