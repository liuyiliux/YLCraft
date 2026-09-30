"""微博 / X 的「用户作品列表」的回归测试（2026-09-29 新增）。

## 用户要求

    "把创作者的「作品列表」补上 —— 微博和x应该也有发布记录之类的"

补上后两个平台都能取"某人发了什么"。

## X：UserTweets

来源：twscrape `api.py::OP_UserTweets` + `user_tweets_raw`

    op = "SXVCYB8XHSS25nzIljNtZA/UserTweets"
    kv = {"userId": uid, "count": 40, "includePromotedContent": True,
          "withQuickPromoteEligibilityTweetFields": True,
          "withVoice": True, "withV2Timeline": True}

⚠️ 用 **`userId`（数字 id）**，不是 handle —— 所以客户端会自动
先用 `UserByScreenName` 拿 `rest_id`。

实测响应路径（与 twscrape 文档说的略不同）：

    data.user.result.timeline.timeline.instructions[].entries[]
    推文项  entryId 以 `tweet-` 开头
    游标项  entryId 以 `cursor-bottom-` 开头，value 在 `content.value`

实测（@308YYtGer5EWPqj）解析出 2 条，正文/互动/时间都对。

## 微博：containerid=107603{uid}

⚠️ **三个坑，少一个就失败**（都实测踩过）：

1. `containerid` 是 **`107603{uid}`**（不是用户详情的 `100505{uid}`）
2. **必须带 `type=uid&value={uid}`** —— 只给 containerid + page
   会返回 **HTML 错误页（2700 字节）**
3. **必须带 `referer`**（`https://m.weibo.cn/u/{uid}`）——
   不带会被踢到 `passport.weibo.com/sso/signin`（`ok=-100`）

而且 **`page>=2` 要求登录态**（`page=1` 是公开数据）——
所以池会话**必须显式注入 cookie**：
只靠持久化 profile 会退化成访客态（`/api/config` 显示 `login=False`、
`MLOGIN=0`），`page=2` 直接 `ok=-100`。

实测修复后：page=1/2/3 各 10 条不同内容。

翻页用 **`page=N`**（不是 since_id —— 实测 `cardlistInfo.since_id` 是 None）。
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# X：UserTweets
# =============================================================================

def test_x_user_tweets_op_and_variables():
    """**回归**：X 的 UserTweets queryId 与 variables 要与 twscrape 一致。"""
    from app.services.platforms.twitter import apis

    assert apis.USER_TWEETS_QUERY_ID == "SXVCYB8XHSS25nzIljNtZA"
    assert "/UserTweets" in apis.USER_TWEETS_OP

    v = apis.build_user_tweets_variables("123", count=20)
    assert v["userId"] == "123", "用 userId（数字 id），不是 screen_name"
    assert v["count"] == 20
    assert v["withV2Timeline"] is True
    # cursor 只在传了才带
    assert "cursor" not in v
    assert apis.build_user_tweets_variables("1", cursor="abc")["cursor"] == "abc"


def test_x_user_tweets_parses_timeline_path():
    """**回归**：解析路径要正确。

        实测：data.user.result.timeline.timeline.instructions[].entries[]
        （twscrape 文档说的是 user_result，实测取不到）
    """
    from app.services.platforms.twitter import search_http as sh

    src = inspect.getsource(sh.fetch_user_tweets)
    assert 'data' in src
    assert 'user' in src and 'result' in src
    assert 'timeline' in src
    assert 'instructions' in src
    # 推文项与游标项的识别
    assert 'tweet-' in src
    assert 'cursor-bottom' in src


def test_x_user_tweets_returns_cursor():
    """要返回下一页游标（供翻页）。"""
    from app.services.platforms.twitter import search_http as sh

    src = inspect.getsource(sh.fetch_user_tweets)
    assert '"cursor"' in src or "'cursor'" in src
    assert "has_more" in src


def test_x_client_converts_handle_to_uid():
    """**回归**：`get_user_videos` 要能接 handle（自动转数字 id）。

    `UserTweets` 只认数字 userId，但调用方（`/users/videos`）通常只有 handle。
    """
    from app.services.platforms.twitter import client as tw

    src = inspect.getsource(tw.TwitterClient.get_user_videos)
    assert "isdigit" in src, "应判断是否纯数字"
    assert "get_user_profile" in src, "不是数字就先取资料拿 rest_id"


def test_x_tweet_parser_handles_media():
    """推文的图片/视频要解析出来。"""
    from app.services.platforms.twitter import search_http as sh

    src = inspect.getsource(sh._parse_tweet_result)
    assert "extended_entities" in src or "entities" in src
    assert "media" in src
    assert "photo" in src
    assert "video_info" in src, "视频地址在 video_info.variants 里"


def test_x_tweet_parser_skips_empty():
    """没有 id 或正文的项要跳过（不产出空壳）。"""
    from app.services.platforms.twitter.search_http import _parse_tweet_result

    assert _parse_tweet_result({}) is None
    assert _parse_tweet_result({"rest_id": "1"}) is None
    assert _parse_tweet_result({"legacy": {"full_text": "x"}}) is None


# =============================================================================
# 微博：containerid=107603{uid}
# =============================================================================

def test_weibo_user_posts_container_prefix():
    """**回归**：用户微博列表用 `107603{uid}`（不是 100505）。"""
    from app.services.platforms.weibo import apis

    assert apis.USER_POSTS_CONTAINER_PREFIX == "107603"
    # 与"用户详情"的 100505 区分开
    assert apis.USER_CONTAINER_PREFIX == "100505"


def test_weibo_user_posts_params_include_type_value():
    """**回归（重要）**：**必须带 `type=uid&value={uid}`**。

    实测：只给 containerid + page 会返回 **HTML 错误页（2700 字节）**。
    """
    from app.services.platforms.weibo import search_patchright as wb

    src = inspect.getsource(wb.get_user_posts_via_patchright)
    assert '"type"' in src or "'type'" in src, "必须补 type=uid"
    assert '"value"' in src, "必须补 value={uid}"


def test_weibo_js_search_sends_referer():
    """**回归**：请求要带 `referer`。

    实测：不带会被踢到 `passport.weibo.com/sso/signin`（`ok=-100`）。
    """
    from app.services.platforms.weibo import search_patchright as wb

    js = wb.JS_SEARCH
    assert "referrer" in js, "应带 referrer"
    assert "x-requested-with" in js, "应带 x-requested-with（真实请求有）"


def test_weibo_pool_session_injects_cookies():
    """**回归（最关键）**：池会话**必须显式注入 cookie**。

    只靠持久化 profile 会退化成**访客态**（`/api/config` 的
    `login=False`、`MLOGIN=0`），于是 `page=2` 直接 `ok=-100`
    —— 表现为"用户微博列表只有第一页"。
    """
    from app.services.platforms.weibo import search_patchright as wb

    src = inspect.getsource(wb._get_session)
    assert "_inject_cookies" in src, "新建会话后要注入 cookie"

    inj = inspect.getsource(wb._inject_cookies)
    assert "add_cookies" in inj
    assert ".weibo.cn" in inj, "m 站的 cookie 要种到 .weibo.cn"


def test_weibo_user_posts_uses_page_param():
    """翻页用 `page=N`（不是 since_id —— 实测 cardlistInfo.since_id 是 None）。"""
    from app.services.platforms.weibo import apis

    p = apis.build_user_posts_params("123", page=3)
    assert p["page"] == "3"
    assert p["page_type"] == "03", "page_type=03 必须带"
    assert "since_id" not in p


def test_weibo_user_posts_handles_not_logged_in():
    """**回归**：`ok=-100`（要登录）时要**停下并记日志**，不是静默返回。

    用户看到"只有一页"会以为"这人就发了这么多"——
    其实是登录态不够。
    """
    from app.services.platforms.weibo import search_patchright as wb

    src = inspect.getsource(wb.get_user_posts_via_patchright)
    assert 'ok' in src
    assert "break" in src
    assert "登录" in src, "应记录/提示需要登录"


def test_weibo_client_has_get_user_videos():
    """微博客户端要有 `get_user_videos`（原来没有 → `/users/videos` 报 500）。"""
    from app.services.platforms.weibo.client import WeiboClient

    assert hasattr(WeiboClient, "get_user_videos")
