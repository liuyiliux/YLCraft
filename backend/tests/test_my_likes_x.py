"""「我的点赞」列表的回归测试（2026-10-11 新增）。

## 用户要求

    "我的数据，x平台 增加点赞列表"

## ⚠️ 这个 queryId 是**实测抓的**，不是抄的

`Likes` **不在 twscrape 里** —— 已逐行核对它的 21 个 `OP_*` 常量，
没有 `Likes` / `LikedTweets`。所以只能从已登录的 x.com JS bundle 抓：

    queryId:"mu4us66Q6RRNOywVQhGtRg",operationName:"Likes"

实测（2026-10-11，用自己的号）：

    HTTP 200，单页 ~120KB，20 条/页
    响应路径与 `UserTweets` **完全一致** → 共用 `_parse_user_timeline`
    翻页：第 1 页 vs 第 2 页首条 id 各不相同 ✅（overlap=0）

## ⚠️ 这条测试记的是两个**踩过的坑**（都是"不报错只出错"那种）

1. **`response_model` 会吃掉字段** —— 第一版 `/users/likes` 声明
   `response_model=UserVideosResponse`，于是 `next_cursor` / `has_more`
   被 FastAPI **静默过滤掉**，前端永远拿不到游标 → 「下一页」永远出不来。
2. **`has_more` 恒为 False** —— 第一版首批请求把 `next_cursor` 写死成 `""`，
   于是即使 X 还有更多，前端也不显示下一页。
   （skill 里记的「后端没设 has_more → 前端没有下一页」就是同一个坑。）
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# queryId / variables
# =============================================================================

def test_x_likes_op_and_variables():
    """**回归**：Likes 的 queryId 与 variables 形状（实测值）。"""
    from app.services.platforms.twitter import apis

    assert apis.LIKES_QUERY_ID == "mu4us66Q6RRNOywVQhGtRg"
    assert apis.LIKES_OP == "mu4us66Q6RRNOywVQhGtRg/Likes"

    v = apis.build_likes_variables("123", count=20)
    assert v["userId"] == "123", "用 userId（数字 id），不是 screen_name"
    assert v["count"] == 20
    # ⚠️ 这 6 个字段**少一个就 422 GRAPHQL_VALIDATION_FAILED**（实测）
    for k in (
        "userId", "count", "includePromotedContent", "withClientEventToken",
        "withBirdwatchNotes", "withVoice", "withV2Timeline",
    ):
        assert k in v, f"Likes 的 variables 必须有 {k}（少一个会 422）"
    # 点赞列表没有推广内容
    assert v["includePromotedContent"] is False
    assert v["withClientEventToken"] is False
    assert v["withBirdwatchNotes"] is False
    # cursor 只在传了才带
    assert "cursor" not in v
    assert apis.build_likes_variables("1", cursor="abc")["cursor"] == "abc"


def test_likes_query_id_env_override():
    """queryId 会轮换，必须能用环境变量覆盖（与 TweetDetail 一致）。"""
    from app.services.platforms.twitter import apis

    src = inspect.getsource(apis)
    assert "X_LIKES_QUERY_ID" in src, (
        "Likes 的 queryId 要支持环境变量覆盖 —— 轮换时不用改代码"
    )


# =============================================================================
# 解析（与 UserTweets 共用）
# =============================================================================

def _payload_with(entries: list) -> dict:
    return {
        "data": {
            "user": {
                "result": {
                    "timeline": {
                        "timeline": {"instructions": [{"entries": entries}]}
                    }
                }
            }
        }
    }


def _tweet_entry(tid: str, text: str = "hello", likes: int = 7) -> dict:
    return {
        "entryId": f"tweet-{tid}",
        "content": {
            "itemContent": {
                "tweet_results": {
                    "result": {
                        "rest_id": tid,
                        "legacy": {
                            "full_text": text,
                            "favorite_count": likes,
                            "retweet_count": 1,
                            "reply_count": 2,
                            "created_at": "Mon Sep 28 02:33:36 +0000 2026",
                        },
                        "core": {
                            "user_results": {
                                "result": {
                                    "core": {"screen_name": "someone"},
                                }
                            }
                        },
                    }
                }
            }
        },
    }


def test_likes_parse_reuses_user_timeline_parser():
    """**回归**：Likes 与 UserTweets 必须**共用**一个解析函数。

    两处各写一份的话，X 改结构时要改两个地方 ——
    本仓库「同一个东西两处定义、只改一处」的坑踩过多次
    （如 `TwitterAuthError` 的双定义）。
    """
    from app.services.platforms.twitter import search_http as sh

    assert hasattr(sh, "_parse_user_timeline"), "解析函数应抽成共用"
    # fetch_user_likes 要用它
    src = inspect.getsource(sh.fetch_user_likes)
    assert "_parse_user_timeline" in src
    # fetch_user_tweets 也要用它（否则就是抄了两份）
    src2 = inspect.getsource(sh.fetch_user_tweets)
    assert "_parse_user_timeline" in src2


def test_parse_user_timeline_extracts_tweets_and_cursor():
    """解析：推文项 + 游标项。"""
    from app.services.platforms.twitter.search_http import _parse_user_timeline

    payload = _payload_with([
        _tweet_entry("111", "第一条", 10),
        _tweet_entry("222", "第二条", 20),
        {
            "entryId": "cursor-bottom-999",
            "content": {"cursorType": "Bottom", "value": "CURSOR_ABC"},
        },
    ])
    tweets, cursor = _parse_user_timeline(payload)
    assert [t.id for t in tweets] == ["111", "222"]
    assert tweets[0].likes == 10
    assert tweets[1].likes == 20
    assert cursor == "CURSOR_ABC", "游标要取到 —— 前端靠它翻页"


def test_parse_user_timeline_no_cursor_when_absent():
    """没有游标项时如实返回空串（不编造"还能翻"）。"""
    from app.services.platforms.twitter.search_http import _parse_user_timeline

    payload = _payload_with([_tweet_entry("111")])
    tweets, cursor = _parse_user_timeline(payload)
    assert len(tweets) == 1
    assert cursor == ""


def test_parse_user_timeline_skips_cursor_top():
    """`cursor-top` 不是下一页游标（不能拿它当 next）。"""
    from app.services.platforms.twitter.search_http import _parse_user_timeline

    payload = _payload_with([
        {
            "entryId": "cursor-top-1",
            "content": {"cursorType": "Top", "value": "TOP_CURSOR"},
        },
        _tweet_entry("111"),
    ])
    _, cursor = _parse_user_timeline(payload)
    assert cursor == "", "Top 游标不能当成下一页 —— 否则会原地打转"


# =============================================================================
# 客户端
# =============================================================================

def test_client_exposes_self_likes():
    """X 客户端要有 `get_self_likes` / `get_self_likes_page`。

    ⚠️ 缺方法时 `/users/likes` 会抛 `'TwitterClient' has no attribute`
    → 500（本仓库踩过这个症状）。
    """
    from app.services.platforms.twitter.client import TwitterClient

    assert hasattr(TwitterClient, "get_self_likes")
    assert hasattr(TwitterClient, "get_self_likes_page")
    assert hasattr(TwitterClient, "_own_user_id")


def test_client_self_likes_requires_login():
    """没有 cookie 时要抛**可操作错误**，不能返回空列表。

    空列表会被上层理解成"我没点过赞"（假阴性），排查最费时间。
    """
    import asyncio

    from app.services.platforms.base import ClientConfig
    from app.services.platforms.twitter.client import (
        TwitterAuthError, TwitterClient,
    )
    from app.services.platforms.types import ClientMode

    cl = TwitterClient(
        ClientConfig(platform="twitter", mode=ClientMode.API, cookie="")
    )
    with pytest.raises(TwitterAuthError):
        asyncio.get_event_loop().run_until_complete(cl.get_self_likes(5))


def _mk(tid: str):
    """造一个够用的 SearchResult 替身（只要 id —— 这里测的是翻页/去重）。"""
    from app.services.platforms.types import SearchResult

    return SearchResult(
        id=tid, title="", desc="", author="", author_id="",
        cover="", url="", platform="twitter", type="note",
    )


def test_client_pages_until_enough():
    """`get_self_likes` 要**自动翻页**凑够 max_results，且按 id 去重。"""
    import asyncio

    from app.services.platforms.base import ClientConfig
    from app.services.platforms.twitter.client import TwitterClient
    from app.services.platforms.types import ClientMode

    cl = TwitterClient(
        ClientConfig(platform="twitter", mode=ClientMode.API, cookie="a=b")
    )

    calls = {"n": 0}

    async def fake_page(self, max_results=20, cursor=""):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "tweets": [_mk(f"p1_{i}") for i in range(20)],
                "cursor": "CUR1",
                "has_more": True,
            }
        return {
            "tweets": [_mk(f"p2_{i}") for i in range(20)],
            "cursor": "CUR2",
            "has_more": True,
        }

    orig = TwitterClient.get_self_likes_page
    TwitterClient.get_self_likes_page = fake_page
    try:
        items = asyncio.get_event_loop().run_until_complete(
            cl.get_self_likes(max_results=25)
        )
    finally:
        TwitterClient.get_self_likes_page = orig

    assert len(items) == 25, "要凑够 25 条（翻了 2 页）"
    assert calls["n"] == 2
    ids = [t.id for t in items]
    assert len(set(ids)) == len(ids), "不能有重复 id"


def test_client_stops_when_cursor_missing():
    """游标为空 = 到底了，不能无限翻。"""
    import asyncio

    from app.services.platforms.base import ClientConfig
    from app.services.platforms.twitter.client import TwitterClient
    from app.services.platforms.types import ClientMode

    cl = TwitterClient(
        ClientConfig(platform="twitter", mode=ClientMode.API, cookie="a=b")
    )
    calls = {"n": 0}

    async def fake_page(self, max_results=20, cursor=""):
        calls["n"] += 1
        return {
            "tweets": [_mk("only_one")],
            "cursor": "",   # 没有下一页
            "has_more": False,
        }

    orig = TwitterClient.get_self_likes_page
    TwitterClient.get_self_likes_page = fake_page
    try:
        items = asyncio.get_event_loop().run_until_complete(
            cl.get_self_likes(max_results=100)
        )
    finally:
        TwitterClient.get_self_likes_page = orig

    assert len(items) == 1
    assert calls["n"] == 1, "没有游标就该停，不要空转"


# =============================================================================
# 能力声明 / 路由
# =============================================================================

def test_twitter_meta_declares_self_likes():
    """能力要**声明**在 meta（不用 hasattr 猜）。"""
    from app.services.platforms.meta import get_meta, supports

    m = get_meta("twitter")
    assert m is not None
    assert "self_likes" in m.capabilities, (
        "X 要声明 self_likes —— /users/likes 靠它判断（501 vs 200）"
    )
    assert supports("twitter", "self_likes")
    # 别名也要认
    assert supports("x", "self_likes")
    assert supports("tw", "self_likes")


@pytest.mark.parametrize("pf", ["douyin", "xiaohongshu", "weibo", "bili"])
def test_other_platforms_do_not_claim_self_likes(pf):
    """其他平台**不能**声明 self_likes（否则接口会假装能查，实际空）。"""
    from app.services.platforms.meta import get_meta

    m = get_meta(pf)
    if m is None:
        pytest.skip(f"{pf} 无 meta")
    assert "self_likes" not in m.capabilities, (
        f"{pf} 没实现点赞列表，不该声明 self_likes"
    )


def test_likes_route_exists_and_has_cursor():
    """**回归**：`/users/likes` 必须存在，且返回结构含翻页游标。"""
    from app.api.v1 import users

    routes = {r.path: r for r in users.router.routes}
    assert "/likes" in routes, "缺少 /users/likes 路由"

    # ⚠️ 必须是**专门的** response_model —— 复用 UserVideosResponse 会把
    #    next_cursor / has_more 静默过滤掉（实测踩过）
    assert hasattr(users, "UserLikesResponse"), (
        "要有 UserLikesResponse —— 否则 response_model 会吃掉游标字段"
    )
    fields = users.UserLikesResponse.model_fields
    assert "next_cursor" in fields, "返回里必须有 next_cursor"
    assert "has_more" in fields, "返回里必须有 has_more"


def test_likes_route_does_not_expose_user_id():
    """点赞列表**故意不暴露 user_id**（X 的点赞是私密的）。

    暴露了会让人以为"能查别人赞了什么"，而实际查不到 —— 误导。
    """
    from app.api.v1 import users

    sig = inspect.signature(users.get_my_likes)
    assert "user_id" not in sig.parameters, (
        "/users/likes 不该有 user_id 参数（只能查自己）"
    )
    assert "platform" in sig.parameters
    assert "cursor" in sig.parameters, "要有 cursor（翻页用）"


def test_likes_route_uses_capability_not_hasattr():
    """路由要用 `supports()` 声明判断，**不要 hasattr 猜**。

    这是 `meta.py` 的既定原则（`/users/me` 的 self_profile 已按此改过）。
    """
    from app.api.v1 import users

    src = inspect.getsource(users.get_my_likes)
    assert "supports(" in src, "要用 supports() 判断能力"
    assert "501" in src, "不支持的平台要 501（不是空列表）"


def test_likes_route_propagates_cursor_on_first_page():
    """**回归**：首批（不带 cursor）也要把真实游标透出去。

    第一版把首批的 next_cursor 写死成 "" → has_more 恒 False →
    前端永远不显示「下一页」，尽管 X 明明还有更多。
    """
    from app.api.v1 import users

    src = inspect.getsource(users.get_my_likes)
    # 首批分支里也必须从返回数据里取游标
    assert src.count("data.get(\"cursor\")") >= 2 or \
        src.count("data.get('cursor')") >= 2, (
        "首批和翻页两条路都要取游标 —— 否则 has_more 会恒为 False"
    )


# =============================================================================
# 预览 / 下载（2026-10-11 加）
# =============================================================================
#
# 用户要求："x点赞的列表支持下载和预览 看看查询那里怎么做的"。
#
# 参考「查询」页（`crawler/index.tsx`）的成熟做法：
#   ① 媒体字段只认 `images` / `video_url`（与搜索页同一约定）
#   ② 视频**必须走后端代理**（浏览器 <video> 带 Referer → X CDN 403）
#   ③ 图片走代理并用缩略尺寸


def test_user_video_item_has_media_fields():
    """**回归**：`UserVideoItem` 必须带 `images` / `video_url`。

    没有这两个字段，前端的预览/下载**无从下手** ——
    第一版就没有，于是点赞列表只能"看"，不能播也不能下载。
    """
    from app.api.v1 import users

    fields = users.UserVideoItem.model_fields
    assert "images" in fields, "缺 images（图集直链）—— 预览/下载要用"
    assert "video_url" in fields, "缺 video_url（视频直链）—— 预览/播放要用"


def test_media_helper_does_not_fall_back_to_page_url():
    """**回归**：媒体**不兜底** —— 没有直链就留空。

    ⚠️ 这条是本仓库的铁律：用 `url`（原文链接）兜底会让**所有**条目
    都有 `video_url`，前端据此把**图集误判成视频**、渲染出 0:00 空播放器。
    搜索页已踩过一次（见 crawler 的注释）。
    """
    from app.api.v1 import users

    src = inspect.getsource(users._media_of)
    # 取值只来自 raw_data 的 _images / _video_url
    assert "_images" in src and "_video_url" in src
    # 不能拿 v.url / cover 当媒体兜底
    assert "video_url=v.url" not in src
    assert "raw.get(\"_video_url\") or v.url" not in src
    assert "or v.cover" not in src, "不该用 cover 兜底当图集"


def test_both_likes_and_videos_share_media_helper():
    """作品列表和点赞列表要用**同一个** `_media_of`（避免两处漂移）."""
    from app.api.v1 import users

    assert "_media_of" in inspect.getsource(users.get_my_likes)
    assert "_media_of" in inspect.getsource(users.get_user_videos), (
        "『我的作品』也要能预览/下载 —— 两条路共用同一个组装函数"
    )


def test_media_of_extracts_images_and_video():
    """`_media_of` 真的能取出 `_images` / `_video_url`。"""
    from app.api.v1.users import _media_of

    class _V:
        id = "1"
        title = "t"
        cover = "c"
        url = "https://x.com/a/status/1"
        type = "video"
        likes = 3
        raw_data = {
            "_images": ["https://pbs.twimg.com/a.jpg", "", None],            "_video_url": "https://video.twimg.com/v.mp4",
        }

    item = _media_of(_V())
    assert item.images == ["https://pbs.twimg.com/a.jpg"], "空值要过滤掉"
    assert item.video_url == "https://video.twimg.com/v.mp4"


def test_media_of_no_media_stays_empty():
    """没有媒体时**留空**，不编造、不兜底。"""
    from app.api.v1.users import _media_of

    class _V:
        id = "1"
        title = "纯文字"
        cover = "https://pbs.twimg.com/cover.jpg"
        url = "https://x.com/a/status/1"
        type = "note"
        likes = 0
        raw_data = {}

    item = _media_of(_V())
    assert item.images == []
    assert item.video_url == "", "没有直链就该是空串（不是原文链接）"


def test_likes_response_model_keeps_media_fields():
    """**回归**：`UserLikesResponse` 不能把媒体字段过滤掉。

    这是"response_model 静默吃字段"那个坑的同类 ——
    上一轮 `next_cursor` 就是这么丢的。这里锁住媒体字段。
    """
    from app.api.v1 import users

    fields = users.UserLikesResponse.model_fields
    assert "data" in fields
    # data 的元素类型必须是有媒体字段的 UserVideoItem
    assert users.UserVideoItem.model_fields.get("images") is not None


def test_frontend_panel_uses_proxy_for_media():
    """前端面板：视频/图片走**公共组件**的代理（不用直链）。

    实测：X 的 CDN 带 `Referer` 就 403；浏览器 `<video>` 一定会带。
    所以直链在浏览器里必然失败 —— 必须走后端代理。
    （代理逻辑已在公共组件里，面板本身不再自带。）
    """
    panel = _code_only(_frontend_file("pages", "my-platform-data", "MyLikesPanel.tsx"))
    media = _code_only(
        _frontend_file("components", "platform-detail", "PlatformMediaView.tsx")
    )
    assert "PlatformDetailDrawer" in panel, "面板要用公共组件"
    assert "/api/v1/proxy/video?url=" in media, "公共组件里视频要走代理"


def test_frontend_panel_reads_agreed_media_keys():
    """前端只认 `images` / `video_url` 两个键（与后端/搜索页约定一致）。"""
    media = _code_only(
        _frontend_file("components", "platform-detail", "PlatformMediaView.tsx")
    )
    assert "video_url" in media and "images" in media, (
        "公共组件要读约定的两个媒体键"
    )


def test_frontend_uses_actual_download_contract():
    """**回归**：前端不再自己拼下载 —— 交给**下载页**。

    ⚠️ 演进：第一版自己 fetch blob 并读 `saved` 字段统计成功数；
    现在改成跳 `/download?url=`，**由下载页负责**下载与统计。
    所以这里断言的是"不再自己实现下载"，
    而 `saved` 这个契约仍由后端 `download.py` 保证（另有测试覆盖）。

    ⚠️ 只看**代码**，不看注释 —— 注释里会引用旧实现来说明它错在哪。
    """
    panel = _code_only(_frontend_file("pages", "my-platform-data", "MyLikesPanel.tsx"))
    assert "success_count" not in panel, (
        "success_count 是猜的字段，后端没有 —— 会永远显示 0"
    )
    assert "/download?url=" in panel, "下载交给独立下载页"
    # 不再自己存 blob
    assert "saveBlobAs" not in panel, "不再自己实现下载（交给下载页）"


# =============================================================================
# 「详情/下载」统一为**公共组件**（2026-10-11 重构）
# =============================================================================
#
# 用户原话："和 x 平台搜索不一样，这些详情预览要求、还有调到单独下载
# 页面的，我们应该做成公共组件了吧。"
#
# ## 演进过程（三次，记清楚免得改回去）
#
# ① 把播放地址当下载链接
#      `a.href = proxyVideo(video); a.download = 'x.mp4'`
#      → `proxy/video` 是流且**没有 Content-Disposition**，
#        浏览器按"导航到媒体"处理 → **跳播放页**
#        （用户反馈："你这个下载不是跳下载页面吗？"）
#
# ② 自己 fetch blob 存文件 —— 能存了，但**和查询页不一致**。
#    用户指出："还有调到单独下载页面的"。
#
# ③ **现在**：抽公共组件 + 下载跳 `/download?url=`，与查询页完全一致。
#
# ## 用户明确的一条边界
#
# "b站是单独做的和其他平台不一样" ⇒ 公共组件**不含 B站**，
# B站 继续用 `components/bilibili/VideoDetailDrawer`。


def _frontend_file(*parts: str):
    from pathlib import Path

    return (Path(__file__).resolve().parents[2] / "frontend/src").joinpath(*parts)


def _code_only(path) -> str:
    """读文件并**去掉注释行**（注释里会引用旧实现来说明"它错在哪"）。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(
        ln for ln in lines if not ln.strip().startswith(("//", "*", "/*"))
    )


def test_shared_platform_detail_component_exists():
    """要有**公共**详情组件，且它明确服务"非 B站"多平台。"""
    idx = _frontend_file("components", "platform-detail", "index.ts")
    assert idx.exists(), "缺少公共组件目录 components/platform-detail"

    drawer = _frontend_file("components", "platform-detail", "PlatformDetailDrawer.tsx")
    assert drawer.exists(), "缺少 PlatformDetailDrawer"
    src = drawer.read_text(encoding="utf-8")
    # 必须写明 B站 不归它管（用户明确说过 B站是单独做的）
    assert "B站" in src, "组件要注明 B站不归它管（B站是单独一套）"


def test_shared_component_download_jumps_to_download_page():
    """**回归**：公共组件的下载 = **跳独立下载页**（与查询页一致）。

    查询页就是 `window.location.href = '/download?url=...'`。
    """
    src = _code_only(
        _frontend_file("components", "platform-detail", "PlatformDetailDrawer.tsx")
    )
    assert "/download?url=" in src, "下载要跳 /download?url= （和查询页一致）"
    assert "window.location.href" in src, "用 location.href 整页跳转（与查询页一致）"


def test_likes_panel_uses_shared_component():
    """点赞面板要用**公共组件**，不能自己再写一套。

    用户反馈"和 x 平台搜索不一样"的根因就是两边各写一份。
    """
    src = _code_only(_frontend_file("pages", "my-platform-data", "MyLikesPanel.tsx"))
    assert "PlatformDetailDrawer" in src, "要用公共详情组件"
    assert "resolveMedia" in src, "媒体解析要用公共的 resolveMedia"
    # 不能再自己实现代理函数（公共组件里有）
    assert "function proxyVideo(" not in src, "不要再自己写 proxyVideo"


def test_my_works_uses_shared_component_and_download_jump():
    """「我的作品」也要用公共组件 + 公共列库，下载跳下载页。

    ⚠️ 2026-10-14：下载跳转的实现搬进了公共列库的 `actionsColumn`
       （三个列表共用），所以断言指向列库而不是页面文件。
    """
    src = _code_only(_frontend_file("pages", "my-platform-data", "index.tsx"))
    assert "PlatformDetailDrawer" in src, "作品详情要用公共组件"
    assert "contentColumnsList" in src, "作品列表要用公共列库"

    # 下载跳下载页：现在由公共列库统一实现
    shared = _code_only(
        _frontend_file("components", "content-columns", "index.tsx")
    )
    assert "/download?url=" in shared, "下载要跳独立下载页（与查询页一致）"
    assert "encodeURIComponent(r.url)" in shared, "要传原文链接（不是 CDN 直链）"


def test_download_targets_original_page_url_not_cdn():
    """**回归**：下载传的是**原文链接**（`r.url`），不是 CDN 直链。

    实测（2026-10-11）：下载后端是 **yt-dlp**，它认"网页"不认裸 CDN：

        video.twimg.com/...mp4                 → 下载失败
        https://x.com/<user>/status/<id>       → DONE（真存了 mp4）
    """
    for name in ("MyLikesPanel.tsx", "index.tsx"):
        src = _code_only(_frontend_file("pages", "my-platform-data", name))
        assert "r.video_url as string" not in src, (
            f"{name}: 不能把 CDN 直链交给下载 —— yt-dlp 会失败"
        )
    likes = _code_only(_frontend_file("pages", "my-platform-data", "MyLikesPanel.tsx"))
    assert "encodeURIComponent(r.url)" in likes, "点赞下载要传原文链接"


def test_media_view_uses_proxy_for_video():
    """媒体组件里视频必须走**代理**（X 的 CDN 带 Referer 就 403）。"""
    src = _code_only(
        _frontend_file("components", "platform-detail", "PlatformMediaView.tsx")
    )
    assert "/api/v1/proxy/video?url=" in src, "视频要走后端代理"
    assert "/api/v1/proxy/image?" in src, "图片要走代理"


def test_media_resolve_does_not_fallback_to_page_url():
    """**回归**：媒体**不兜底** —— 没有直链就留空。

    用原文链接兜底会让**图集被判成视频**、渲染 0:00 空播放器
    （搜索页踩过一次）。
    """
    src = _code_only(
        _frontend_file("components", "platform-detail", "PlatformMediaView.tsx")
    )
    # resolveMedia 只从 _video_url / video_url / _images / images 取
    assert "_video_url" in src and "video_url" in src
    assert "_images" in src and "images" in src
    # 不能用 item.url 兜底当视频
    assert "item.url" not in src or "video = item.url" not in src


def test_backend_download_sends_attachment_header():
    """后端下载接口要发 `Content-Disposition: attachment`。

    有它浏览器才会**存文件**而不是内联播放。
    """
    from app.api.v1 import download as dl

    src = inspect.getsource(dl)
    assert "attachment" in src, "下载接口要带 attachment（否则会被内联/跳页）"


def test_bilibili_keeps_its_own_drawer():
    """**边界**：B站 保持自己那套（用户明确说过 B站是单独做的）。

    公共组件**不能**被 B站复用 —— B站有弹幕/字幕/评论/分P 等专属能力。
    """
    p = _frontend_file("components", "bilibili", "VideoDetailDrawer.tsx")
    assert p.exists(), "B站自己的详情组件要保留"
    src = p.read_text(encoding="utf-8")
    # B站那套不应改成引用公共组件
    assert "components/platform-detail" not in src.replace("\\", "/"), (
        "B站 是单独一套，不该被并进公共组件"
    )


# =============================================================================
# 「我的数据」记住平台选择（2026-10-11 用户要求）
# =============================================================================
#
# 用户原话："我就是要加个缓存或者存哪，下次打开还是之前选择的平台。"
#
# 与采集页（`ylcraft_crawler_platform`）**同一套做法**，保持一致。


def test_my_platform_data_remembers_platform():
    """**回归**：平台选择要持久化，下次打开回到上次那个平台。"""
    src = _code_only(_frontend_file("pages", "my-platform-data", "index.tsx"))

    assert "localStorage.setItem" in src, "要保存平台选择"
    assert "localStorage.getItem" in src, "要读回平台选择"
    assert "ylcraft_my_platform_data_platform" in src, (
        "用固定的 storage key（和采集页命名风格一致）"
    )


def test_my_platform_data_storage_is_guarded():
    """**回归**：读写 localStorage 要包 try/catch。

    隐私模式 / 禁用 storage 时 `setItem` 会**抛异常** ——
    不包住的话整个页面白屏（用户只是看个数据，不该因此挂掉）。
    """
    src = _frontend_file("pages", "my-platform-data", "index.tsx")
    text = src.read_text(encoding="utf-8")

    i = text.find("localStorage.setItem(PLATFORM_STORAGE_KEY")
    assert i != -1, "没找到保存平台的调用"
    assert "try {" in text[max(0, i - 500):i], "保存平台要包 try/catch"

    j = text.find("localStorage.getItem(PLATFORM_STORAGE_KEY")
    assert j != -1, "没找到读取平台的调用"
    assert "try {" in text[max(0, j - 400):j], "读取平台要包 try/catch"


def test_url_param_still_wins_over_saved():
    """**回归**：URL 带 `?platform=` 时**优先用 URL**，不被缓存盖掉。

    否则"从别处带 platform 跳进来"会失效 —— 用户会看到
    "我明明点了看微博，进去却是上次的 X"。
    """
    text = _frontend_file("pages", "my-platform-data", "index.tsx").read_text(
        encoding="utf-8"
    )

    i = text.find("function initialPlatform")
    assert i != -1, "应有 initialPlatform 统一决定初始平台"
    seg = text[i:i + 700]
    i_url = seg.find("searchParams.get('platform')")
    i_saved = seg.find("localStorage.getItem")
    assert i_url != -1, "要先看 URL 参数"
    assert i_saved != -1, "再看缓存"
    assert i_url < i_saved, "URL 参数的优先级必须高于缓存"


# =============================================================================
# 「点下一页内容不变」的回归（2026-10-11 用户反馈）
# =============================================================================
#
# 用户原话："点了下一页 页数变了 内容还是之前的"。
#
# ## 根因
#
# `load()` **只有「刷新」按钮在调**：
#
#     点「下一页」→ 游标压栈 → currentCursor 变了 → 重新渲染
#                 → **但没有任何 effect 去请求新游标的数据**
#                 → 列表还是旧的那批，只有"第 N 页"文字在变
#
# ## 浏览器实测（修前 / 修后）
#
#     修前：点下一页 → page="第 2 页"，rows **与第 1 页完全相同** ❌
#     修后：点下一页 → page="第 2 页"，rows **不同** ✅
#           点上一页 → 回到第 1 页，rows 与最初的 P1 一致 ✅
#
# 用的是真实浏览器（bsk）在 http://127.0.0.1:3000 上点的，不是猜。


def test_cursor_change_triggers_reload():
    """**回归**：游标变化必须**触发请求**（否则翻页只改页码不改内容）。"""
    src = _code_only(_frontend_file("pages", "my-platform-data", "MyLikesPanel.tsx"))

    # 必须有一个 effect 依赖 currentCursor 并调用 load
    assert "currentCursor" in src, "要有 currentCursor"
    i = src.find("void load(currentCursor)")
    assert i != -1, "必须有 effect 在游标变化时调用 load(currentCursor) —— 这是翻页的命门"

    # 该 effect 的依赖里要含 currentCursor
    tail = src[i:i + 200]
    assert "currentCursor" in tail, "effect 依赖里要有 currentCursor"


def test_panel_autoloads_without_clicking_refresh():
    """**回归**：进页面/切平台要**自动加载**，不该必须点「刷新」。

    修之前只有「刷新」按钮会调 `load()` ——
    所以第一次进来是空的，用户得先点一下刷新（体验很差）。
    """
    src = _code_only(_frontend_file("pages", "my-platform-data", "MyLikesPanel.tsx"))
    # 至少有一处 effect 自动调用 load（不是只在 onClick 里）
    assert "void load(currentCursor)" in src, "要有自动加载的 effect"


def test_pagination_buttons_keep_their_guards():
    """翻页按钮的**守卫**不能被删（不能谎报能翻 / 不能在首页点上一页）。"""
    src = _code_only(_frontend_file("pages", "my-platform-data", "MyLikesPanel.tsx"))

    # 下一页：必须同时看 hasMore 和 nextCursor
    assert "!hasMore" in src, "下一页按钮要受 hasMore 控制"
    assert "!nextCursor" in src, "下一页按钮要受 nextCursor 控制"
    # 上一页：栈里只有一项时禁用
    assert "cursorStack.length <= 1" in src, "首页时上一页要禁用"


# =============================================================================
# 详情字段缺失的回归（2026-10-11 用户反馈）
# =============================================================================
#
# 用户原话（附搜索页 vs 点赞详情的对比截图）：
#   "第一个是搜索的详情，第二个是我们做的公共组件的我的点赞里面详情，
#    少了评论等数据，看看我的点赞能获取到吗。"
#
# ## 根因：**不是取不到，是最后一步被丢了**
#
# 后端解析器（`_parse_tweet_result`）**早就解析了** comments / shares /
# create_time；但 `_media_of()` 组装响应时**只拷了 likes**，
# 于是这些字段在最后一步被丢掉。
#
# 浏览器实测（修前 / 修后）：
#
#     修前：平台「未知」，无 评论/分享/发布时间
#     修后：平台 X · 作者 BassplayerSerge · 赞 4,129 · 评论 41 ·
#           分享 189 · 发布时间 2天前  ✅（与搜索页一致）


def test_user_video_item_has_detail_fields():
    """**回归**：`UserVideoItem` 要带详情抽屉需要的字段。

    缺一个，详情里就少显示一块 —— 用户一眼就能看出来"和搜索页不一样"。
    """
    from app.api.v1 import users

    fields = users.UserVideoItem.model_fields
    for k in ("comments", "shares", "views", "create_time", "platform",
              "author", "desc"):
        assert k in fields, f"`UserVideoItem` 缺 {k} —— 详情会少一块"


def test_media_of_passes_through_detail_fields():
    """**回归**：`_media_of` 要**真的透出**这些字段（不是只在模型里声明）。

    这是那个 bug 的真正位置：模型/解析器都有，**组装时没拷**。
    """
    from app.api.v1.users import _media_of

    class _V:
        id = "1"
        title = "t"
        cover = "c"
        url = "https://x.com/a/status/1"
        type = "video"
        likes = 4129
        comments = 41
        shares = 189
        views = 0
        create_time = "Sun Oct 11 09:44:40 +0000 2026"
        platform = "twitter"
        author = "BassplayerSerge"
        desc = "正文"
        raw_data = {"_video_url": "https://video.twimg.com/v.mp4"}

    item = _media_of(_V())
    assert item.comments == 41, "评论数被丢了 —— 详情会少显示「评论」"
    assert item.shares == 189, "分享数被丢了"
    assert item.create_time.startswith("Sun Oct 11"), "发布时间被丢了"
    assert item.platform == "twitter", "平台标识被丢了 —— 详情会显示「未知」"
    assert item.author == "BassplayerSerge", "作者被丢了"
    assert item.desc == "正文"


def test_media_of_detail_fields_default_safely():
    """字段缺失时要有**安全默认值**（各平台字段不完全一样，不能炸）。"""
    from app.api.v1.users import _media_of

    class _V:
        id = "1"
        title = "t"
        cover = ""
        url = ""
        type = "note"
        likes = 0
        raw_data = {}

    item = _media_of(_V())          # 没有 comments/shares/... 属性
    assert item.comments == 0
    assert item.shares == 0
    assert item.views == 0
    assert item.create_time == ""
    assert item.platform == ""
    assert item.author == ""


def test_likes_route_returns_detail_fields():
    """接口**返回体**里要有这些键（防止 response_model 又吃掉）。

    这个坑本轮已经踩过一次（`next_cursor` 被 `response_model` 静默过滤）。
    """
    from app.api.v1 import users

    fields = users.UserLikesResponse.model_fields
    assert "data" in fields
    # data 的元素类型要带详情字段
    item_fields = users.UserVideoItem.model_fields
    assert "comments" in item_fields
    assert "platform" in item_fields


# =============================================================================
# 评论（详情抽屉的「评论」页签，2026-10-11 加）
# =============================================================================
#
# 用户要求："加，为什么不加呢？"（指详情里的评论 tab）。
#
# 加的过程中又抓到**两个「数据被丢掉」的 bug**（都不是取不到）：
#
# ① 评论作者全是「匿名」
#    `search_http.py` 只读**旧版扁平** `u.name` / `u.screen_name`，
#    而 X 现在给的是**新版嵌套** `u.core.name` / `u.core.screen_name`
#    （实测扁平字段是 None，嵌套字段有值）。
#
# ② `author_handle` 在归一化白名单里被丢
#    `comments.py::_normalize` 是**白名单式**的，采集端产出了
#    `author_handle` 但白名单没列 → 静默消失。
#    （该函数自己的注释就警告过这个坑。）


def test_comment_author_reads_nested_schema():
    """**回归**：评论作者名要读**新旧两套** schema。

    实测（2026-10-11）：X 的评论 user 对象是
        `u.core.name` / `u.core.screen_name`，
    而旧的 `u.name` / `u.screen_name` 是 **None** ——
    只读旧路径会让**所有评论作者变成「匿名」**。
    """
    from app.services.platforms.twitter import search_http as sh

    src = inspect.getsource(sh.get_replies_via_http)
    assert "core" in src, "要读 u.core（新版嵌套）"
    assert 'ucore.get("name")' in src, "昵称要优先取 u.core.name"
    assert 'ucore.get("screen_name")' in src, "handle 要优先取 u.core.screen_name"
    # 旧字段仍要兜底（X 可能回退或别的端点还是旧版）
    assert 'u.get("name")' in src or "u.get('name')" in src, "旧的扁平字段要兜底"


def test_normalizer_passes_author_handle():
    """**回归**：归一化白名单要透出 `author_handle`。

    ⚠️ 那个函数是**白名单式**的 —— 没列出来的字段会被**静默丢掉**。
    采集端产出了不等于前端拿得到。
    """
    from app.api.v1 import comments as comments_api

    src = inspect.getsource(comments_api._normalize_generic_comment)
    assert "author_handle" in src, (
        "白名单里要有 author_handle —— 否则采到了也会被丢掉，前端只能显示「匿名」"
    )


def test_comment_panel_exists_and_handles_501_429():
    """评论面板要**分开**处理 501 / 429（不能都写「加载失败」）。

        501 = 平台没实现（换谁都没用）
        429 = 平台拒绝了（等一等 / 换网络有救）

    两者混成一个提示，用户就不知道该做什么。
    """
    p = _frontend_file("components", "platform-detail", "CommentPanel.tsx")
    assert p.exists(), "要有评论面板组件"
    src = _code_only(p)

    assert "501" in src, "要单独识别 501（平台没实现）"
    assert "429" in src, "要单独识别 429（平台拒绝，可重试）"
    # 后端给的原因要铺开显示（那是用户唯一能做的事）
    assert "unsupported" in src and "blocked" in src


def test_comment_panel_reloads_when_item_changes():
    """换内容时要**重新拉评论**（否则会把上一条的评论留在面板里）。"""
    p = _frontend_file("components", "platform-detail", "CommentPanel.tsx")
    src = _code_only(p)
    assert "useEffect" in src, "要有 effect 在 itemId 变化时重新加载"
    assert "[itemId, load]" in src or "itemId" in src


def test_drawer_has_comment_tab():
    """抽屉里要有「评论」页签，且换内容时回到「详情」。"""
    src = _code_only(
        _frontend_file("components", "platform-detail", "PlatformDetailDrawer.tsx")
    )
    assert "CommentPanel" in src, "抽屉要挂上评论面板"
    assert "comments" in src, "要有 comments 页签"
    # 换内容回详情页（否则会停在评论页看起来像"没评论"）
    assert "setTab('detail')" in src, "换条目时要回到详情页签"


# =============================================================================
# 子回复 + 「条数对不上」的说明（2026-10-11 用户要求）
# =============================================================================
#
# 用户："要"（指①评论能翻页吗 ②子回复能展开吗）。
#
# ## 实测结论（tweet 2109218616248070654）
#
# **翻页：X 不给更多。** `TweetDetail` 第一页就**没有 Bottom 游标**
# （实测 `cursor=无`）—— max_pages 换 1/3/6 都只有同样的 23 条。
# 所以「加载更多」在这里**取不到东西**，只能如实说明。
#
# X 的计数（41）含二级回复 + 未下发的部分，**天然对不上**。
#
# **子回复：能取，但 X 只给一部分。** 实测：
#
#     reply_count=2  → 拿到 1 条
#     reply_count=1  → 拿到 0 条
#     reply_count=1  → 拿到 0 条
#
# ⇒ 取到 0 时要**说明是平台没下发**，不能留空白
#   （空白看起来像"我们坏了"）。


def test_comment_panel_explains_count_mismatch():
    """**回归**：实取条数 < 原帖显示条数时，要**主动说明原因**。

    用户看到 X 上写「评论 41」、面板里只有 19 条，第一反应是
    **"你们漏抓了"** —— 这正是最该避免的误解。
    """
    src = _code_only(
        _frontend_file("components", "platform-detail", "CommentPanel.tsx")
    )
    assert "expectedCount" in src, "要接收原帖显示的评论数"
    assert "原帖显示" in src, "要显示对比（原帖 N 条 / 实际 M 条）"
    assert "只下发这一批" in src, "要说明是 X 的限制，不是我们没抓到"


def test_drawer_passes_expected_count():
    """抽屉要把原帖的评论数传给评论面板（否则说明不出现）。"""
    src = _code_only(
        _frontend_file("components", "platform-detail", "PlatformDetailDrawer.tsx")
    )
    assert "expectedCount={comments}" in src, "要传原帖评论数"


def test_subreplies_exist_and_explain_empty():
    """**回归**：子回复要能点开；**取到 0 条时如实说明是平台没下发**。

    实测 X 只下发一部分二级回复 —— 显示空白会让用户以为功能坏了。
    """
    src = _code_only(
        _frontend_file("components", "platform-detail", "CommentPanel.tsx")
    )
    assert "SubReplies" in src, "要有子回复组件"
    assert "parent_id" in src, "要按 parent_id 拉子回复"
    assert "没有提供这些回复" in src, (
        "子回复为 0 时要说明是平台没下发，而不是留空白"
    )


def test_subreplies_handles_501_and_429():
    """子回复也要分开处理 501 / 429（与主列表一致）。"""
    src = _code_only(
        _frontend_file("components", "platform-detail", "CommentPanel.tsx")
    )
    i = src.find("function SubReplies")
    assert i != -1, "要有 SubReplies 组件"
    seg = src[i:]
    assert "501" in seg, "子回复要识别 501"
    assert "429" in seg, "子回复要识别 429"


def test_subreplies_do_not_refetch_on_toggle():
    """子回复展开/收起**不要反复打接口**。"""
    src = _code_only(
        _frontend_file("components", "platform-detail", "CommentPanel.tsx")
    )
    assert "loadedOnce" in src, "要记住已经取过，避免重复请求"


def test_backend_get_replies_still_supports_parent():
    """后端要保留按父评论 id 取子回复的能力（前端依赖它）。"""
    from app.services.platforms.twitter.client import TwitterClient

    assert hasattr(TwitterClient, "get_replies")
    src = inspect.getsource(TwitterClient.get_replies)
    assert "root_comment_id" in src, "要支持按父评论 id 取子回复"


# =============================================================================
# 「正在关注」作品流（HomeLatestTimeline，2026-10-11 加）
# =============================================================================
#
# 用户要求："官方x平台有正在关注作品，我们也加下"。
#
# ## ⚠️ 三个与其它 timeline 不同的点（都是实测确认的）
#
# 1. **它是 POST**（搜索/Likes/UserTweets 都是 GET），
#    且 **`queryId` 要放在 JSON body 里**。
# 2. **queryId 抓不到于 JS bundle** —— Likes 能搜到，它**搜不到**，
#    只能抓真实网络请求（browser-skill 的 debug capture）。
# 3. **响应路径不同**：`data.home.home_timeline_urt...`
#
# 实测：HTTP 200，33~35 条，翻页**无重叠**。


def test_home_latest_op_and_variables():
    """**回归**：HomeLatestTimeline 的 queryId 与 variables（实测值）。"""
    from app.services.platforms.twitter import apis

    assert apis.HOME_LATEST_QUERY_ID == "NmDBT3APtNxDpMqIEauu7A"
    assert apis.HOME_LATEST_OP.endswith("/HomeLatestTimeline")

    v = apis.build_home_latest_variables(count=20)
    assert v["count"] == 20
    assert v["enableRanking"] is True
    assert v["requestContext"] == "launch", "实测 requestContext 是 launch"
    assert v["seenTweetIds"] == [], "默认不传已看过的 id"
    assert "cursor" not in v
    assert apis.build_home_latest_variables(cursor="abc")["cursor"] == "abc"


def test_home_latest_features_are_separate_from_tweet_detail():
    """**回归**：HomeLatest 的 features **不能**复用 TweetDetail 的。

    实测两份**不完全一样** —— 混用可能被 X 拒（或字段缺失）。
    """
    from app.services.platforms.twitter import apis

    assert hasattr(apis, "HOME_LATEST_FEATURES")
    assert apis.HOME_LATEST_FEATURES is not apis.GQL_FEATURES
    # 这份里有几个 TweetDetail 没有的键（实测抄自真实请求）
    assert "rweb_cashtags_enabled" in apis.HOME_LATEST_FEATURES


def test_home_latest_uses_post_not_get():
    """**回归**：HomeLatestTimeline 必须走 **POST**（它和别的不一样）。"""
    from app.services.platforms.twitter import search_http as sh

    assert hasattr(sh, "_request_post_op"), "要有 POST 请求函数"
    src = inspect.getsource(sh._request_post_op)
    assert "c.post(" in src, "必须是 POST"
    assert '"queryId"' in src, "queryId 要放进 body（实测真实请求就是这样）"

    # fetch_home_latest 要用它
    fetch_src = inspect.getsource(sh.fetch_home_latest)
    assert "_request_post_op" in fetch_src


def test_home_latest_reads_correct_path():
    """**回归**：响应路径是 `data.home.home_timeline_urt`（不是 user result）。"""
    from app.services.platforms.twitter import search_http as sh

    src = inspect.getsource(sh.fetch_home_latest)
    assert "home_timeline_urt" in src, "要读 home_timeline_urt"
    assert '"home"' in src, "路径在 data.home 下"


def test_home_latest_returns_cursor():
    """翻页要如实返回游标（与 /users/likes 一致）。"""
    from app.services.platforms.twitter import search_http as sh

    src = inspect.getsource(sh.fetch_home_latest)
    assert "has_more" in src and "cursor" in src


def test_twitter_meta_declares_home_feed():
    """能力要声明在 meta（后端用它决定 200 还是 501）。"""
    from app.services.platforms.meta import get_meta, supports

    assert supports("twitter", "home_feed"), "X 要声明 home_feed"
    assert supports("x", "home_feed")
    m = get_meta("douyin")
    if m is not None:
        assert "home_feed" not in m.capabilities, "抖音不该声明 home_feed"


def test_home_feed_route_exists():
    """`/users/home-feed` 路由要存在。"""
    from app.api.v1 import users

    routes = {r.path for r in users.router.routes}
    assert "/home-feed" in routes, "缺少 /users/home-feed 路由"


def test_frontend_panel_supports_both_modes():
    """**回归**：前端用**同一个面板**服务两种数据源（不要复制一份）。

    那正是之前"和查询页不一样"的根因。
    """
    src = _code_only(_frontend_file("pages", "my-platform-data", "MyLikesPanel.tsx"))
    assert "home-feed" in src, "面板要支持 home-feed 模式"
    assert "getMyHomeFeed" in src, "要调用 home-feed 接口"
    assert "getMyPlatformLikes" in src, "也要保留点赞接口"


def test_frontend_shows_interaction_stats():
    """**回归**：列表要显示互动数据（赞 / 评论 / 分享）。

    用户："搜索时候列表有互动这些数据，我的数据里面的列表是不是也得加"。
    """
    for name in ("MyLikesPanel.tsx", "index.tsx"):
        src = _code_only(_frontend_file("pages", "my-platform-data", name))
        assert "CommentOutlined" in src, f"{name}: 要显示评论数"
        assert "ShareAltOutlined" in src, f"{name}: 要显示分享数"


def test_zero_stats_are_not_rendered():
    """**回归**：**为 0 的互动数据不渲染**（不能显示光秃秃的 "0"）。

    ## 为什么（2026-10-11 用户反馈"那些互动数据还没有"）

    原来「赞」是**写死显示**的，于是转推条目全都显示一个 `0` ——
    用户看到"赞 0、评论 0"会以为**数据没取到**。

    实测根因：X 对**转推**只给 `shares`（转推数），
    `likes` / `comments` 一律返回 0（那些数字在**被转的原推**上）。
    「正在关注」33 条里 **25 条是转推**，所以看着"全都没有互动数据"。

    ⇒ 0 一律不显示 + 转推显式标标签。

    ⚠️ 2026-10-11 抽出、2026-10-14 迁入**公共列库**
       （`components/content-columns/index.tsx`）—— 测试跟着指到那里。
    """
    src = _code_only(_frontend_file("components", "content-columns", "index.tsx"))
    assert "stats.filter(([v]) => v > 0)" in src, (
        "互动数据要过滤掉 0 —— 光秃秃的 0 像数据缺失"
    )


def test_retweet_is_labeled():
    """**回归**：转推要**显式标出来**，解释"为什么没有赞/评论"。

    不然用户看到"转推条目 0 互动"会以为是我们的 bug。
    """
    src = _code_only(_frontend_file("components", "content-columns", "index.tsx"))
    assert "isRetweet" in src, "要有转推判断"
    assert "RT @" in src, "判据用正文前缀（X 的转推格式）"
    assert "转推" in src, "要有转推标签"


# =============================================================================
# 补齐缺失的互动数字（2026-10-11 用户对比官方截图）
# =============================================================================
#
# 用户拿 **X 官方**的截图对比："原版是我们对比我们少了哪个数"。
#
# 官方一条推文显示 **5 个数字**，我们原来只有 3 个：
#
#     官方         X 字段                    原来
#     💬 380      legacy.reply_count        ✅
#     🔁 97       legacy.retweet_count      ✅
#     ♡ 3027      legacy.favorite_count     ✅
#     🔖 307      **legacy.bookmark_count**  ❌ 没取
#     👁 1.4万    **t.views.count**          ❌ 写死 0
#     （引用）     **legacy.quote_count**     ❌ 没取
#
# ## ⚠️ 浏览量那个"实测拿不到"的旧结论是**错的**
#
# 代码里原来写着 `views=0  # 实测拿不到 → 0（不编造）`。
# 实际它在**顶层** `t["views"]["count"]`（字符串），
# 只是**不在 `legacy` 里** —— 当初只翻了 legacy 就下了结论。


def test_bookmark_and_quote_count_parsed():
    """**回归**：收藏（bookmark）与引用（quote）数要解析出来。"""
    from app.services.platforms.twitter.search_http import _parse_tweet_result

    tw = {
        "rest_id": "1",
        "legacy": {
            "full_text": "hi",
            "favorite_count": 3027,
            "reply_count": 380,
            "retweet_count": 97,
            "bookmark_count": 307,
            "quote_count": 12,
        },
        "core": {"user_results": {"result": {"core": {"screen_name": "a"}}}},
    }
    r = _parse_tweet_result(tw)
    assert r is not None
    assert r.likes == 3027
    assert r.comments == 380
    assert r.shares == 97
    assert r.collects == 307, "收藏数（bookmark_count）要解析出来"
    assert r.raw_data.get("quote_count") == 12, "引用数要放进 raw_data"


def test_views_parsed_from_top_level():
    """**回归**：浏览量在**顶层** `views.count`（字符串），要能取到。

    ⚠️ 教训：不要因为"某个子对象里没有"就断定"平台不给"。
       这个字段就在隔壁的顶层，原来却写着"实测拿不到"。
    """
    from app.services.platforms.twitter.search_http import (
        _parse_tweet_result, _views_of,
    )

    assert _views_of({"views": {"count": "14478"}}) == 14478
    assert _views_of({"views": {"count": 100}}) == 100
    # 取不到时**仍然不编造**
    assert _views_of({}) == 0
    assert _views_of({"views": None}) == 0
    assert _views_of({"views": {"count": "abc"}}) == 0
    assert _views_of({"views": {"state": "Enabled"}}) == 0

    tw = {
        "rest_id": "1",
        "legacy": {"full_text": "hi", "favorite_count": 1},
        "views": {"count": "14478", "state": "EnabledWithCount"},
        "core": {"user_results": {"result": {"core": {"screen_name": "a"}}}},
    }
    r = _parse_tweet_result(tw)
    assert r is not None and r.views == 14478


def test_both_parsers_agree_on_stats():
    """**回归**：两个解析函数（parse_tweet_http / _parse_tweet_result）
    要给**同样的**统计字段 —— 否则搜索页和我的数据会显示不一样。

    ⚠️ 同一份数据两处解析，是这类"一边有一边没有"的温床。
    """
    import inspect as _inspect

    from app.services.platforms.twitter import search_http as sh

    for fn in (sh.parse_tweet_http, sh._parse_tweet_result):
        src = _inspect.getsource(fn)
        assert "bookmark_count" in src, f"{fn.__name__}: 缺收藏数解析"
        assert "_views_of" in src, f"{fn.__name__}: 缺浏览量解析（不能写死 0）"


def test_api_exposes_collects_and_quote():
    """`UserVideoItem` 要透出收藏/引用（否则前端拿不到）。"""
    from app.api.v1 import users

    fields = users.UserVideoItem.model_fields
    assert "collects" in fields, "缺 collects（收藏数）"
    assert "quote_count" in fields, "缺 quote_count（引用数）"

    # `_media_of` 要真的填
    from app.api.v1.users import _media_of

    class _V:
        id = "1"; title = "t"; cover = ""; url = ""; type = "note"; likes = 0
        comments = 0; shares = 0; views = 14478; collects = 307
        create_time = ""; platform = "twitter"; author = "a"; desc = ""
        raw_data = {"quote_count": 12}

    item = _media_of(_V())
    assert item.collects == 307
    assert item.views == 14478
    assert item.quote_count == 12


def test_frontend_shows_all_five_stats():
    """前端要显示全五个数字（赞/评/转/藏/看）。"""
    src = _code_only(_frontend_file("components", "content-columns", "index.tsx"))
    assert "StarOutlined" in src, "要显示收藏数"
    assert "EyeOutlined" in src, "要显示浏览数"
    for f in ("r.collects", "r.views", "r.likes", "r.comments", "r.shares"):
        assert f in src, f"要读 {f}"


def test_detail_drawer_reads_both_collect_keys():
    """详情抽屉要同时认 `collects` 与 `collect_count`。

    ⚠️ 小红书一直用 `collect_count`，X 用 `collects` ——
       只读一个会让另一边显示不出收藏数。
    """
    src = _code_only(
        _frontend_file("components", "platform-detail", "PlatformDetailDrawer.tsx")
    )
    assert "item.collects" in src and "item.collect_count" in src, (
        "两个键名都要读（各平台不一致）"
    )


# =============================================================================
# 浏览量：各接口不一样，**不要为了补齐而多打请求**（2026-10-11）
# =============================================================================
#
# 用户："我的点赞 列表没有观看数吗" + 之后指出：
# "对当前页每条多请求一次详情 —— 这个不要，容易触发限流吧，
#  我是之前看我的关注列表就有有的"。
#
# ## 实测（**用户是对的**）
#
#     HomeLatestTimeline（正在关注）  ✅ **原生就带 views**（54/54 有键）
#     Likes（我的点赞）               ❌ 16 条里 0 条有
#     UserTweets（我的作品）           ❌ 没有这个键
#     TweetDetail（详情）             ✅ 有
#
# ⇒ 「正在关注」**本来就有**，根本不用补 —— 我一开始只在小样本上测，
#   误判成"都没有"，于是加了逐条补请求（白打 20 个请求 + 限流风险）。
#
# ## 决定：**不补**
#
# 补齐虽可行，但一页 20 条 = 多 20 次请求（~11 秒），
# 且每次都要生成 transaction-id —— 是**显眼的自动化特征**。
# 用户明确反对。**宁可不显示这个数，也不冒被限流的风险。**
#
# 前端为 0 时**不渲染**，所以不会出现误导的 "0"。


def test_home_latest_keeps_native_views():
    """**回归**：「正在关注」的浏览量是**原生带的**，不能丢掉。

    实测 54/54 条都有 `views` 键 —— 解析路径必须保留它。
    """
    from app.services.platforms.twitter import search_http as sh

    # 解析函数要读顶层 views
    src = inspect.getsource(sh._parse_tweet_result)
    assert "_views_of" in src, "解析要保留原生 views"

    # fetch_home_latest 走的是同一个解析 → 天然带 views
    home_src = inspect.getsource(sh.fetch_home_latest)
    assert "_parse_tweet_result" in home_src


def test_no_extra_requests_for_views():
    """**回归**：**不要**为了补浏览量逐条多打请求（限流风险）。

    用户明确说："这个不要 容易触发限流吧"。
    """
    from app.services.platforms.twitter import search_http as sh
    from app.services.platforms.twitter.client import TwitterClient

    assert not hasattr(sh, "enrich_views"), (
        "enrich_views 已删 —— 逐条补请求会触发限流，用户明确反对"
    )

    for fn in (TwitterClient.get_self_likes_page,
               TwitterClient.get_user_videos,
               TwitterClient.get_home_latest):
        src = inspect.getsource(fn)
        assert "enrich_views" not in src, f"{fn.__name__} 不该再补请求"


def test_views_zero_is_honest():
    """取不到就 0，**不编造**（前端为 0 时不渲染）。"""
    from app.services.platforms.twitter.search_http import _views_of

    assert _views_of({}) == 0
    assert _views_of({"views": {"state": "Enabled"}}) == 0, (
        "X 有时只给 state 不给 count —— 这时是 0，不是编造"
    )
    assert _views_of({"views": {"count": "14478"}}) == 14478


# =============================================================================
# 作者 / 发布时间列（2026-10-11 用户反馈）
# =============================================================================
#
# 用户："我的点赞和关注列表有发布时间吗 我看查询的有"、
#      "还有作者 你再检查下"。
#
# **两个字段后端一直都有**（`author` / `create_time`），
# 只是前端**没显示** —— 又一例"数据在、界面缺"。


def test_api_returns_author_and_time():
    """**回归**：接口要带 `author` 与 `create_time`（列表要显示）。"""
    from app.api.v1 import users

    f = users.UserVideoItem.model_fields
    assert "author" in f, "缺 author —— 列表显示不了作者"
    assert "create_time" in f, "缺 create_time —— 列表显示不了发布时间"


def test_both_lists_show_author_and_time():
    """**回归**：三个列表都要有「作者」「发布时间」列。

    用户看「查询」页有这两列，问我们为什么没有 —— **要与查询页对齐**。

    ⚠️ 2026-10-14 重构后，列搬到了**公共列库**
       （`components/content-columns/index.tsx`）——
       「我的数据」与「查询」页都从它取列。
    """
    shared = _code_only(
        _frontend_file("components", "content-columns", "index.tsx")
    )
    # 列库是"工厂函数"，标题通过 `title()` 帮助函数生成，所以断言标题字符串
    assert "title(ctx, '作者', 'author')" in shared, "列库里缺「作者」列"
    assert "title(ctx, '发布时间', 'create_time')" in shared, "列库里缺「发布时间」列"

    # 两个面板都**必须用**这个列库（否则列又会漂移）
    for name in ("MyLikesPanel.tsx", "index.tsx"):
        src = _code_only(_frontend_file("pages", "my-platform-data", name))
        assert "contentColumnsList" in src, (
            f"{name}: 必须用公共列库 —— 各写一份正是「每次都差一点」的根因"
        )

    # 查询页也要用同一个列库
    crawler = _code_only(_frontend_file("pages", "crawler", "index.tsx"))
    assert "contentColumnsList" in crawler or "coverColumn" in crawler, (
        "查询页也必须用公共列库 —— 否则两处列会漂移"
    )


def test_crawler_columns_come_from_shared_library():
    """**回归**：「查询」页的列**来自公共列库**（2026-10-14 收敛）。

    原来查询页有 ~250 行手写列，与「我的数据」那份重复 ——
    这正是"每次都差一点"的根因。现在两边共用同一批列实现。
    """
    crawler = _code_only(_frontend_file("pages", "crawler", "index.tsx"))
    for fn in ("coverColumn(", "titleColumn(", "platformColumn(", "actionsColumn("):
        assert fn in crawler, f"查询页的列应来自公共列库（缺 {fn}）"


def test_lists_use_shared_format_time():
    """**回归**：时间要用**与查询页同一个** `formatTime`。

    各写一份格式化逻辑 → 两边显示规则漂移 →
    又变成"和查询页不一样"（用户最初反馈的就是这类问题）。
    """
    shared = _code_only(
        _frontend_file("components", "content-columns", "index.tsx")
    )
    assert "formatTime" in shared, "公共列要用共享的 formatTime"
    assert "utils/format" in shared, "从 utils/format 引入"

    # 共用同一份实现
    fmt = _frontend_file("utils", "format.ts").read_text(encoding="utf-8")
    assert "export function formatTime" in fmt


def test_time_column_has_nowrap():
    """**回归**：时间列要 `nowrap`。

    ⚠️ 列宽偏窄时中文会**竖排单字**（查询页已踩过这个坑）。
    """
    shared = _code_only(
        _frontend_file("components", "content-columns", "index.tsx")
    )
    assert "nowrap" in shared, "时间列要 nowrap（否则中文竖排）"


# =============================================================================
# 作者显示「昵称 @handle」（2026-10-11 用户要求）
# =============================================================================
#
# 用户："作者能加中文吗 如果原来有昵称的"，
# 随后明确："改成 @那个账号和昵称都显示吧 这样更方便，包括列表和详情"。
#
# ## 根因：后端**一直解析了昵称**，只是没用它
#
# `_parse_tweet_result` 原来写 `author=handle` —— 于是三个列表显示的全是
# **@用户名**，而**查询页**显示昵称。实测同一条推文两个都有：
#
#     name        = '热爱分享'        ← 昵称（中文/emoji）
#     screen_name = 'xiaoma877'      ← handle


def test_backend_returns_nickname_not_handle():
    """**回归**：`author` 要是**昵称**，不是 handle。"""
    from app.services.platforms.twitter.search_http import _parse_tweet_result

    tw = {
        "rest_id": "1",
        "legacy": {"full_text": "hi", "favorite_count": 1},
        "core": {
            "user_results": {
                "result": {
                    "core": {"name": "热爱分享", "screen_name": "xiaoma877"}
                }
            }
        },
    }
    r = _parse_tweet_result(tw)
    assert r is not None
    assert r.author == "热爱分享", "author 要是昵称（中文），不是 handle"
    # handle 仍要保留（前端要显示 @handle）
    assert r.raw_data.get("handle") == "xiaoma877"


def test_author_falls_back_to_handle():
    """取不到昵称时**退回 handle**（不编造、也不留空）。"""
    from app.services.platforms.twitter.search_http import _parse_tweet_result

    tw = {
        "rest_id": "1",
        "legacy": {
            "full_text": "hi",
            "user": {"screen_name": "onlyhandle", "name": ""},
        },
        "core": {"user_results": {"result": {"core": {"screen_name": "onlyhandle"}}}},
    }
    r = _parse_tweet_result(tw)
    assert r is not None
    assert r.author == "onlyhandle", "没有昵称就用 handle"


def test_api_exposes_author_handle():
    """接口要同时给 `author`（昵称）与 `author_handle`。"""
    from app.api.v1 import users
    from app.api.v1.users import _media_of

    f = users.UserVideoItem.model_fields
    assert "author_handle" in f, "缺 author_handle（前端要显示 @handle）"

    class _V:
        id = "1"; title = "t"; cover = ""; url = ""; type = "note"; likes = 0
        comments = 0; shares = 0; views = 0; collects = 0
        create_time = ""; platform = "twitter"
        author = "热爱分享"; desc = ""
        raw_data = {"handle": "xiaoma877"}

    item = _media_of(_V())
    assert item.author == "热爱分享"
    assert item.author_handle == "xiaoma877"


def test_frontend_shows_nickname_and_handle():
    """**回归**：列表和详情都要「昵称 @handle」并列。

    用户："改成 @那个账号和昵称都显示吧 这样更方便，包括列表和详情"。
    """
    shared = _code_only(
        _frontend_file("components", "content-columns", "index.tsx")
    )
    assert "author_handle" in shared, "列表要读 author_handle"
    assert "authorLabel" in shared, "要有作者显示逻辑"

    drawer = _code_only(
        _frontend_file("components", "platform-detail", "PlatformDetailDrawer.tsx")
    )
    assert "author_handle" in drawer, "详情也要显示 handle"

    # 昵称与 handle 相同/缺失时不重复显示（否则会出现 "xx @xx"）
    assert "name === handle" in shared or "!== String(item.author)" in drawer
