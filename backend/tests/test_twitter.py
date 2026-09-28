"""推特/X 平台契约测试。

## 调研与实测结论（2026-09-28）

### 1. 推特**搜索强制要求登录**（与微博相反）

初步实测**差点误判**：看到 `document.cookie` 里没有 `auth_token`，
就以为"免登录可搜"。**实际是误判** —— `auth_token` 是 httpOnly，
`document.cookie` 本来就看不到。该浏览器其实**已登录**
（页面上有只有登录后才有的元素：发帖 / 账号菜单 / 私信 / 历史）。

**决定性证据**：Patchright 全新 profile（真·未登录）打开
`https://x.com/search?q=美食&src=typed_query`：

    → 重定向 https://x.com/i/jf/onboarding/web?redirect_after_login=%2Fsearch...
    → article 数 = 0

即使先访问首页"入境"拿到 `gt`（guest token）cookie，搜索页**仍被重定向**。

### 2. 四种直连方案全失败，只有浏览器 DOM 可用

| 方案 | 实测 |
|------|------|
| httpx + guest token + queryId | **404** |
| 页面内 fetch（无额外头） | **403** |
| 页面内 fetch + `x-csrf-token`(ct0) | **仍 403** |
| 从 JS bundle 动态提取 queryId | 不可行（懒加载分散） |
| **打开搜索页 + 读 DOM** | ✅ 可读到推文 |

queryId 会轮换：gallery-dl 里硬编码的 `4fpceYZ6-YQCx_JSl_Cn_A`
实测 **404**，当前真实值是 `uGB-gNd5HE4TkpO70OcFNw`（bsk network 捕获）。
**硬编码必然失效**，所以不采用 GraphQL 路径。

### 3. 方法论教训

判断登录态**不能只看 `document.cookie`**，要看**只有登录后才出现的
界面元素**（`SideNav_NewTweet_Button` / `SideNav_AccountSwitcher_Button`），
或者**用全新 profile 复现**（那才是真·未登录）。

这已是同一类误判的第二次（微博那次是把"缺 Service Worker"
误读成"平台做不了"）。
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# 注册
# =============================================================================

@pytest.mark.parametrize("name", ["twitter", "x", "tw"])
def test_client_registered(name: str):
    from app.services.platforms import PlatformClientFactory

    assert name in PlatformClientFactory._registry, f"{name} 未注册"


def test_client_instantiable_via_aliases():
    from app.services.platforms import create_client

    for name in ("twitter", "x", "tw"):
        client = create_client(name, mode="patchright")
        assert type(client).__name__ == "TwitterClient", name


def test_crawler_dispatches_twitter_to_browser():
    """twitter/x/tw 在 crawler 层要分派到 patchright。"""
    from app.services.crawler import service as crawler_service

    src = inspect.getsource(crawler_service.CrawlerService._search_via_platforms)
    assert "twitter" in src, "分派表应含 twitter"
    assert "BROWSER_ONLY" in src


# =============================================================================
# 解析
# =============================================================================

TWEET = {
    "id": "2101202430444675082",
    "handle": "TaoSeDao",
    "media": ["https://pbs.twimg.com/media/ABC123?format=jpg&name=large"],
    "video": [],
    "aria": "36 回复、1,468 喜欢、2 次转帖、12,345 次观看",
    "text": "桃色岛TaoSeDao @TaoSeDao · 9月19日 胖胖de奇妙旅行",
}

TWEET_VIDEO = {
    "id": "9999",
    "handle": "someone",
    "media": [],
    "video": ["https://video.twimg.com/amplify_video/9999/vid/720x1280/abc.mp4"],
    "aria": "3 replies, 10 likes, 500 views",
    "text": "a video tweet",
}


def test_parse_tweet_basic():
    from app.services.platforms.twitter import parse_tweet

    r = parse_tweet(TWEET)
    assert r is not None
    assert r.id == "2101202430444675082"
    assert r.author == "TaoSeDao"
    assert r.platform == "twitter"
    assert r.url == "https://x.com/TaoSeDao/status/2101202430444675082"
    assert r.type == "note"


def test_parse_tweet_counts_from_aria():
    """互动数从 aria-label 里取（实测中文是"36 回复、1,468 喜欢…"）。

    注意千分位逗号要处理。
    """
    from app.services.platforms.twitter import parse_tweet

    r = parse_tweet(TWEET)
    assert r.likes == 1468, f"喜欢数（含千分位）：{r.likes}"
    assert r.comments == 36
    assert r.shares == 2
    assert r.views == 12345


def test_parse_aria_counts_english():
    from app.services.platforms.twitter import parse_aria_counts

    c = parse_aria_counts("3 replies, 10 likes, 500 views")
    assert c["comments"] == 3 and c["likes"] == 10 and c["views"] == 500


def test_parse_aria_counts_missing_is_zero():
    """取不到就留 0（**不编造**）。"""
    from app.services.platforms.twitter import parse_aria_counts

    c = parse_aria_counts("")
    assert c == {"comments": 0, "likes": 0, "shares": 0, "views": 0}


def test_parse_tweet_video_type():
    from app.services.platforms.twitter import parse_tweet

    r = parse_tweet(TWEET_VIDEO)
    assert r.type == "video"
    assert "video.twimg.com" in r.raw_data["_video_url"]


def test_images_and_video_go_into_raw_data():
    """**约定**：SearchResult 没有 images/video 字段，
    所以放 raw_data._images / _video_url（crawler 层会取出来）。"""
    from app.services.platforms.twitter import parse_tweet

    r = parse_tweet(TWEET)
    assert r.raw_data["_images"], "应有 _images"
    assert "_video_url" in r.raw_data


def test_image_upgraded_to_orig():
    """图片升到原图（name=orig，gallery-dl 规则）。"""
    from app.services.platforms.twitter import parse_tweet

    r = parse_tweet(TWEET)
    assert "name=orig" in r.raw_data["_images"][0]
    assert "name=large" not in r.raw_data["_images"][0]


def test_upgrade_image_url_rules():
    from app.services.platforms.twitter import upgrade_image_url

    # 已是 name=xxx → 换成 orig
    assert upgrade_image_url(
        "https://pbs.twimg.com/media/X?format=jpg&name=large"
    ) == "https://pbs.twimg.com/media/X?format=jpg&name=orig"
    # 没有 name → 追加
    assert upgrade_image_url(
        "https://pbs.twimg.com/media/X?format=jpg"
    ) == "https://pbs.twimg.com/media/X?format=jpg&name=orig"
    assert upgrade_image_url(
        "https://pbs.twimg.com/media/X"
    ) == "https://pbs.twimg.com/media/X?name=orig"
    # 头像不动（profile_images 不是推文配图）
    avatar = "https://pbs.twimg.com/profile_images/1/abc.jpg"
    assert upgrade_image_url(avatar) == avatar
    # 非推特域名不动
    assert upgrade_image_url("https://example.com/a.jpg") == "https://example.com/a.jpg"
    assert upgrade_image_url("") == ""


@pytest.mark.parametrize("bad", [{}, {"text": "无 id"}, None, "字符串"])
def test_parse_tweet_tolerates_bad_input(bad):
    from app.services.platforms.twitter import parse_tweet

    assert parse_tweet(bad) is None


# =============================================================================
# 分页：必须"边滚边收集"（用户反馈"只有 9 个"）
# =============================================================================

def test_scroll_collects_while_scrolling():
    """**回归**：必须**边滚边收集**，不能"滚到底再读一次 DOM"。

    推特是**虚拟列表** —— 滚动时回收离屏节点。
    实测 DOM 里 article 数量会波动：

        滚1: 5→10   滚2: 10→9   滚4: 9→6   滚8: 9→15

    所以最后读一次 DOM 会丢掉中间滚过的推文
    （实测表现为"最多只有 9 条"，用户反馈就是这个问题）。

    正确做法：每滚一次就把当时 DOM 里的推文抓下来、按 id 去重累积。
    """
    from app.services.platforms.twitter import search_dom

    src = inspect.getsource(search_dom._scroll_and_collect)
    # 循环内要 evaluate 抓取
    assert "JS_PARSE_TWEETS" in src, "循环内要读 DOM"
    assert "merged" in src, "要有累积容器"
    # 必须有去重（按 id）
    assert 'tid not in merged' in src or "not in merged" in src, "要按 id 去重"


def test_scroll_goes_to_bottom_not_scrollby():
    """**回归**：滚动要**滚到底**（`scrollTo(0, scrollHeight)`）。

    实测 `scrollBy(0, 1600)` 几乎没用（5→6 条），
    因为一屏推文就 ~900px，推特是在**接近底部**时才触发下一批。
    """
    from app.services.platforms.twitter import search_dom

    src = inspect.getsource(search_dom._scroll_and_collect)
    assert "scrollTo(0, document.body.scrollHeight)" in src, "应滚到底"
    assert "scrollBy" not in src, "不应只 scrollBy（实测无效）"


def test_scroll_has_termination():
    """滚动要有终止条件，不能无限滚。"""
    from app.services.platforms.twitter import search_dom

    src = inspect.getsource(search_dom._scroll_and_collect)
    assert "max_rounds" in src, "应有轮次上限"
    assert "stagnant" in src, "应检测停滞（连续无新增就停）"
    assert "want" in src, "应够量就停"


def test_scroll_uses_collect_function():
    """搜索主流程要用 `_scroll_and_collect`（不是旧的"滚完再读"）。"""
    from app.services.platforms.twitter import search_dom

    src = inspect.getsource(search_dom.search_via_patchright)
    assert "_scroll_and_collect" in src
    # 不应再出现旧的"滚完单独读一次"的模式
    assert "_scroll_until_enough" not in src


# =============================================================================
# 「必须登录」这个结论要被钉住
# =============================================================================

def test_login_check_does_not_use_cookie():
    """**回归**：登录检测**不能**依赖 `document.cookie`。

    `auth_token` 是 httpOnly，`document.cookie` 看不到它 ——
    据此判断会得出"未登录"的错误结论（实测踩过这个误判）。
    必须看只有登录后才出现的界面元素。
    """
    from app.services.platforms.twitter import search_dom

    src = inspect.getsource(search_dom.check_logged_in)
    assert "cookie" not in src.lower(), "不应依赖 cookie 判断登录态"
    assert "hasCompose" in src or "hasAccount" in src, "应看登录后才有的元素"

    js = search_dom.JS_CHECK_LOGIN
    assert "SideNav_NewTweet_Button" in js, "应检测发帖按钮"
    assert "SideNav_AccountSwitcher_Button" in js, "应检测账号菜单"
    assert "cookie" not in js.lower()


def test_login_error_message_is_actionable():
    """未登录要报可操作提示，而不是"0 条结果"。"""
    from app.services.platforms.twitter import TwitterLoginRequiredError, search_dom

    assert issubclass(TwitterLoginRequiredError, RuntimeError)
    src = inspect.getsource(search_dom.check_logged_in)
    assert "账号中心" in src, "应告诉用户去哪里登录"
    assert "登录" in src


def test_search_checks_login_before_searching():
    """搜索前要校验登录态（否则未登录会静默返回 0 条）。"""
    from app.services.platforms.twitter import search_dom

    src = inspect.getsource(search_dom.search_via_patchright)
    assert "check_logged_in" in src
    idx = src.find("check_logged_in")
    assert idx < src.find("await session.page.goto(url"), "应在打开搜索页前校验"


def test_does_not_use_hardcoded_graphql_query_id():
    """**回归**：不要硬编码 GraphQL queryId。

    实测：gallery-dl 里那个已 404，且 queryId 会轮换。
    所以走 DOM 而不是 GraphQL。

    只检查**代码**（去掉注释/说明文字），因为文档里会提到那个失效值。
    """
    from app.services.platforms.twitter import search_dom

    src = inspect.getsource(search_dom)
    code_lines = [
        ln for ln in src.splitlines()
        if not ln.strip().startswith("#")
    ]
    # 去掉模块 docstring（它在最前面，用三引号包裹）
    code = "\n".join(code_lines)
    first_doc = code.find('"""')
    if first_doc != -1:
        second_doc = code.find('"""', first_doc + 3)
        if second_doc != -1:
            code = code[:first_doc] + code[second_doc + 3:]

    assert "SearchTimeline" not in code, "代码里不应走 GraphQL SearchTimeline"
    assert "4fpceYZ6" not in code, "代码里不应硬编码已失效的 queryId"
    assert "/graphql/" not in code, "不应调用 GraphQL"


def test_uses_media_filter_for_video_search():
    """搜视频/图片时用 `f=media`（推特的媒体筛选参数）。"""
    from app.services.platforms.twitter import search_dom

    assert "f=media" in search_dom.SEARCH_MEDIA_URL_TMPL
    src = inspect.getsource(search_dom.search_via_patchright)
    assert "use_media" in src


def test_dom_parser_excludes_profile_images():
    """DOM 提取要排除头像（profile_images），只取推文配图。

    踩过：不排除的话每条推文的"第一张图"都是头像。
    """
    from app.services.platforms.twitter import search_dom

    js = search_dom.JS_PARSE_TWEETS
    assert "pbs.twimg.com/media" in js, "应只取 media 路径的图片"
