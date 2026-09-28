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


def test_crawler_does_not_force_browser_for_twitter():
    """**回归**：crawler 层**不应**把 twitter 放进 BROWSER_ONLY。

    推特已改为**纯 HTTP 优先**（补上 `x-client-transaction-id` 后
    SearchTimeline 实测 200，不开浏览器）。

    ⚠️ 如果把它放回 BROWSER_ONLY，`mode=patchright` 会让
    `BasePlatformClient` 在 `search()` **之前**就为注入 cookie 而**启动浏览器**
    —— 实测看到 9 个 chrome 进程白起，而 HTTP 路径根本不需要它。
    """
    import inspect

    from app.services.crawler import service as crawler_service

    src = inspect.getsource(crawler_service.CrawlerService._search_via_platforms)
    # 找到 BROWSER_ONLY 那一行
    line = next(
        (ln for ln in src.splitlines() if "BROWSER_ONLY" in ln and "=" in ln), ""
    )
    assert line, "未找到 BROWSER_ONLY 定义"
    for name in ("twitter", '"x"', '"tw"'):
        assert name not in line, (
            f"twitter 别名 {name} 不该在 BROWSER_ONLY 里（会让浏览器白起）"
        )
    # 小红书/微博仍必须走浏览器
    assert "xhs" in line and "weibo" in line, "小红书/微博仍应走浏览器"


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
# 纯 HTTP 路径（2026-09-28 实现，替代/优先于 DOM）
# =============================================================================

def test_http_endpoints_and_bearer():
    """端点与 Bearer 要来自 twscrape 的当前值（实测可用）。"""
    from app.services.platforms.twitter import apis

    assert apis.SEARCH_OP == "hyPfJYJ_XAtDYoslQc-Rgg/SearchTimeline"
    assert apis.GQL_URL == "https://x.com/i/api/graphql"
    assert apis.WEB_BEARER.startswith("AAAAAAAAAAAAAAAAAAAAANRILg")
    assert apis.REQUIRED_COOKIES == ("auth_token", "ct0")


@pytest.mark.parametrize("alias,expected", [
    ("note", "Top"), ("all", "Top"), ("top", "Top"), ("hot", "Top"),
    ("latest", "Latest"), ("realtime", "Latest"),
    ("video", "Media"), ("image", "Media"), ("media", "Media"),
])
def test_product_aliases(alias: str, expected: str):
    from app.services.platforms.twitter.apis import resolve_product

    assert resolve_product(alias) == expected


def test_unknown_product_falls_back():
    from app.services.platforms.twitter.apis import resolve_product

    assert resolve_product("不存在") == "Top"
    assert resolve_product(None) == "Top"


def test_build_search_variables():
    from app.services.platforms.twitter.apis import build_search_variables

    v = build_search_variables("美食", count=20, product="Top")
    assert v["rawQuery"] == "美食"
    assert v["count"] == 20
    assert v["querySource"] == "typed_query"
    assert v["product"] == "Top"
    assert "cursor" not in v, "首页不应带 cursor"

    v2 = build_search_variables("美食", cursor="ABC")
    assert v2["cursor"] == "ABC"


def test_http_search_requires_both_cookies():
    """**回归**：缺 auth_token 或 ct0 要报**可操作错误**。

    X 搜索必须有这两个；缺了要提示去账号中心登录，
    **不能**返回"0 条结果"（那会让人以为关键词没内容）。
    """
    import asyncio
    import inspect

    from app.services.platforms.twitter import search_http

    src = inspect.getsource(search_http._request_page)
    assert "REQUIRED_COOKIES" in src
    assert "TwitterAuthError" in src
    assert "账号中心" in src, "错误信息要告诉用户去哪登录"

    # 真的抛（只有 ct0、没有 auth_token）
    with pytest.raises(search_http.TwitterAuthError) as ei:
        asyncio.run(search_http._request_page(
            "ct0=abc; twid=x", {"rawQuery": "x"}
        ))
    assert "auth_token" in str(ei.value)


def test_http_retries_once_on_404():
    """**回归**：404 要重新生成 transaction-id 并重试一次。

    404 是"缺/过期 transaction-id"的典型症状（不是"没有结果"）。
    twscrape 同款策略：
        # if code 404 on first try then generate new
        # x-client-transaction-id and retry
    """
    import inspect

    from app.services.platforms.twitter import search_http

    src = inspect.getsource(search_http._request_page)
    assert "404" in src, "应处理 404"
    assert "invalidate_xclid" in src or "invalidate" in src, "应清缓存"
    assert "force_refresh" in src, "重试要强制重新生成"
    # 有两次尝试
    assert "for attempt in (1, 2)" in src


def test_http_error_messages_are_actionable():
    """401/403 要报"登录态失效，去重新登录"，不是"没有结果"。"""
    import inspect

    from app.services.platforms.twitter import search_http

    src = inspect.getsource(search_http._request_page)
    assert "401" in src and "403" in src
    assert "重新登录" in src or "账号中心" in src


def test_parse_tweet_http_fields():
    """HTTP 路径的字段解析（实测形状）。"""
    from app.services.platforms.twitter.search_http import parse_tweet_http

    t = {
        "__typename": "Tweet",
        "rest_id": "1933074517922099614",
        "core": {"user_results": {"result": {"core": {"screen_name": "paiisnobody"}}}},
        "legacy": {
            "full_text": "美食是健康的水煮菠菜",
            "created_at": "Thu Jun 12 08:10:54 +0000 2025",
            "favorite_count": 68,
            "retweet_count": 1,
            "reply_count": 3,
            "lang": "ja",
            "id_str": "1933074517922099614",
            "extended_entities": {"media": [
                {"type": "photo", "media_url_https": "https://pbs.twimg.com/media/A.jpg"},
            ]},
        },
    }
    r = parse_tweet_http(t)
    assert r is not None
    assert r.id == "1933074517922099614"
    assert r.author == "paiisnobody"
    assert r.desc == "美食是健康的水煮菠菜"
    assert r.likes == 68 and r.shares == 1 and r.comments == 3
    assert r.create_time.startswith("Thu Jun 12")
    assert r.raw_data["lang"] == "ja"
    assert r.raw_data["_images"] == ["https://pbs.twimg.com/media/A.jpg"]
    assert r.url == "https://x.com/paiisnobody/status/1933074517922099614"


def test_parse_tweet_http_video_picks_highest_bitrate():
    """视频要从 variants 里挑**码率最高**的 mp4。"""
    from app.services.platforms.twitter.search_http import parse_tweet_http

    t = {
        "rest_id": "999",
        "legacy": {
            "full_text": "v", "id_str": "999",
            "extended_entities": {"media": [{
                "type": "video",
                "media_url_https": "https://pbs.twimg.com/thumb.jpg",
                "video_info": {"variants": [
                    {"content_type": "video/mp4", "bitrate": 256000,
                     "url": "https://video.twimg.com/low.mp4"},
                    {"content_type": "video/mp4", "bitrate": 2176000,
                     "url": "https://video.twimg.com/high.mp4"},
                    {"content_type": "application/x-mpegURL",
                     "url": "https://video.twimg.com/playlist.m3u8"},
                ]},
            }]},
        },
    }
    r = parse_tweet_http(t)
    assert r.type == "video"
    assert r.raw_data["_video_url"] == "https://video.twimg.com/high.mp4"


def test_parse_tweet_http_views_not_fabricated():
    """**回归**：`views` GraphQL 拿不到时留 0，**不编造**。"""
    from app.services.platforms.twitter.search_http import parse_tweet_http

    t = {"rest_id": "1", "legacy": {"full_text": "x", "id_str": "1"}}
    r = parse_tweet_http(t)
    assert r.views == 0


@pytest.mark.parametrize("bad", [{}, {"legacy": "字符串"}, None, {"legacy": {}}])
def test_parse_tweet_http_tolerates_bad_input(bad):
    from app.services.platforms.twitter.search_http import parse_tweet_http

    assert parse_tweet_http(bad) is None


def test_bottom_cursor_extraction():
    """翻页游标：找 `cursorType == "Bottom"` 的 value。"""
    from app.services.platforms.twitter.search_http import _get_bottom_cursor

    payload = {"data": {"x": {"instructions": [
        {"entries": [{"content": {"cursorType": "Top", "value": "T"}}]},
        {"entries": [{"content": {"cursorType": "Bottom", "value": "B123"}}]},
    ]}}}
    assert _get_bottom_cursor(payload) == "B123"
    assert _get_bottom_cursor({"data": {}}) is None


def test_client_prefers_http_then_falls_back_to_dom():
    """**回归**：客户端要**优先 HTTP**，失败才回退 DOM。

    HTTP 不开浏览器、能翻页、字段全；
    DOM 是兜底（transaction-id 生成失败或接口结构变化时用）。
    """
    import inspect

    from app.services.platforms.twitter.client import TwitterClient

    src = inspect.getsource(TwitterClient.search)
    assert "search_via_http" in src, "应优先 HTTP"
    assert "search_via_patchright" in src, "应有 DOM 回退"
    i_http = src.find("search_via_http")
    i_dom = src.find("search_via_patchright")
    assert i_http < i_dom, "HTTP 应在 DOM 之前"


def test_auth_error_does_not_fall_back_to_dom():
    """凭证错误**不该**回退 DOM（回退也是同样结果，还更慢）。"""
    import inspect

    from app.services.platforms.twitter.client import TwitterClient

    src = inspect.getsource(TwitterClient.search)
    assert "except TwitterAuthError:" in src
    i = src.find("except TwitterAuthError:")
    seg = src[i:i + 200]
    assert "raise" in seg, "凭证错误应直接抛出去"


def test_xclid_generator_exists():
    """transaction-id 生成器（缺它一切 404）。"""
    from app.services.platforms.twitter import xclid

    assert callable(xclid.make_transaction_id)
    assert callable(xclid.get_generator)
    assert callable(xclid.invalidate)

    # 只检查**代码**（去掉注释/docstring）—— 文档里会提到 create() 这个坑
    src = inspect.getsource(xclid)
    lines = [ln for ln in src.splitlines() if not ln.strip().startswith("#")]
    code = "\n".join(lines)
    first = code.find('"""')
    if first != -1:
        second = code.find('"""', first + 3)
        if second != -1:
            code = code[:first] + code[second + 3:]

    assert "XClIdGen.create" not in code, "不应调用 create()（本机报 ConnectError）"
    assert "load_keys" in code, "应复用 load_keys 解析"


def test_xclid_uses_fixed_user_agent():
    """**回归**：必须用固定 UA。

    twscrape 的 `XClIdGen.create()` 内部用动态 UA（`"@chrome"`），
    实测在本机报 `ConnectError`；固定 UA 抓页面则正常（HTTP 200）。
    """
    from app.services.platforms.twitter import xclid

    assert "Mozilla/5.0" in xclid.UA, "应是固定 UA 字符串"


def test_xclid_documents_404_cause():
    """文档要写清"缺这个头会 404" —— 这是最容易误判的点。"""
    from app.services.platforms.twitter import xclid

    doc = xclid.__doc__ or ""
    assert "404" in doc, "应说明 404 的原因"
    assert "ConnectError" in doc, "应记录 create() 不可用的坑"


def test_search_respects_page_parameter():
    """**回归**：X 没有 `page` 参数，必须用 cursor 模拟。

    原实现忽略 `page`，于是前端点"第 2 页"会拿到和第 1 页
    **完全相同**的数据（实测：两页首条 id 一样）。

    现在 page=N 会**先翻过前 N-1 页**（丢弃），再返回第 N 页的结果。
    """
    import inspect

    from app.services.platforms.twitter import search_http

    src = inspect.getsource(search_http.search_via_http)
    assert "skip_remaining" in src, "应有跳过前 N-1 页的逻辑"
    assert "page_no" in src, "应读取 page"
    # 跳过时不能收进结果
    assert "continue" in src


def test_max_page_guard():
    """page 太大要报可操作错误，**而不是默默返回第 1 页**。

    X 只能顺序翻，page 越大越慢，所以要设上限并明确告知。
    """
    import inspect

    from app.services.platforms.twitter import search_http

    assert search_http.MAX_PAGE >= 3, "上限太小"
    src = inspect.getsource(search_http.search_via_http)
    assert "MAX_PAGE" in src
    assert "max_results" in src, "错误提示应给出替代方案（调大 max_results）"


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
