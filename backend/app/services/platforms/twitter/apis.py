"""YLCraft — X（原 Twitter）GraphQL 端点定义。

## 来源与验证（2026-09-28 实测跑通）

| 项 | 来源 | 我方验证 |
|----|------|---------|
| Bearer | twscrape `account.py::TOKEN` | ✅ 实测可用 |
| SearchTimeline queryId | twscrape `api.py::OP_SearchTimeline` | ✅ 实测 200 |
| 请求头组合 | twscrape `account.py` + Scweet `account_session.py` | ✅ 实测 200 |
| cursor 翻页 | twscrape `api.py::_get_cursor` | ✅ 4 页 85 条 |
| 响应字段 | —— | ✅ 实测确认 |

## ⚠️ 最关键的一条：缺 `x-client-transaction-id` 会 404

这是之前把 404 误判成"queryId 失效"的真正原因。
两个独立项目都在代码里记录：

    twscrape/queue_client.py:
        # if code 404 on first try then generate new
        # x-client-transaction-id and retry
    Scweet/transaction.py:
        "A request without the x-client-transaction-id header answers 404."

生成方式见 `xclid.py`。

## ⚠️ queryId 会轮换

历史上见过的几个值：
  · `4fpceYZ6-YQCx_JSl_Cn_A`（gallery-dl 硬编码）→ 实测 **404**
  · `uGB-gNd5HE4TkpO70OcFNw`（我方 bsk 从浏览器网络捕获）
  · `hyPfJYJ_XAtDYoslQc-Rgg`（twscrape 当前值）→ **实测可用** ✅

所以这里**不做自动抓取更新**（太脆弱），而是：
  · 用 twscrape 的当前值作为默认
  · 提供 `X_SEARCH_QUERY_ID` 环境变量覆盖
  · 404 时给出明确的可操作提示（告诉用户去更新 queryId，
    而不是报"没有结果"）
"""

# GraphQL 基础地址
GQL_URL = "https://x.com/i/api/graphql"

# 搜索操作（`queryId/operationName`）
#
# 来源：twscrape `twscrape/api.py::OP_SearchTimeline`
# 实测 2026-09-28 可用（HTTP 200，20 条/页）
SEARCH_QUERY_ID = "hyPfJYJ_XAtDYoslQc-Rgg"
SEARCH_OPERATION = "SearchTimeline"
SEARCH_OP = f"{SEARCH_QUERY_ID}/{SEARCH_OPERATION}"

# 按 handle 取用户资料
#
# 来源：twscrape `api.py::OP_UserByScreenName` + `user_by_login_raw`
#     kv = {"screen_name": login, "withSafetyModeUserFields": True}
#     ft = {...9 个 fieldToggles...}
#     响应路径：data.user_result_by_screen_name.result
USER_BY_SCREEN_NAME_QUERY_ID = "Gb-d6r0vxPOADdG62OEBpQ"
USER_BY_SCREEN_NAME_OP = f"{USER_BY_SCREEN_NAME_QUERY_ID}/UserByScreenName"

# ⚠️ UserByScreenName **必须带 fieldToggles**（来源 twscrape `user_by_login_raw`）
USER_BY_SCREEN_NAME_FIELD_TOGGLES: dict = {
    "highlights_tweets_tab_ui_enabled": True,
    "hidden_profile_likes_enabled": True,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "hidden_profile_subscriptions_enabled": True,
    "subscriptions_verification_info_verified_since_enabled": True,
    "subscriptions_verification_info_is_identity_verified_enabled": False,
    "responsive_web_twitter_article_notes_tab_enabled": False,
    "subscriptions_feature_can_gift_premium": False,
    "profile_label_improvements_pcf_label_in_post_enabled": False,
}

# =============================================================================
# 用户推文列表（UserTweets）—— 2026-09-29 实测打通
# =============================================================================
#
# 来源：twscrape `api.py::OP_UserTweets` + `user_tweets_raw`
#
#     kv = {
#         "userId": str(uid),
#         "count": 40,
#         "includePromotedContent": True,
#         "withQuickPromoteEligibilityTweetFields": True,
#         "withVoice": True,
#         "withV2Timeline": True,
#     }
#
# ⚠️ 用的是 **`userId`（数字 id）**，不是 handle ——
# 所以要先用 `UserByScreenName` 拿 `rest_id`。
#
# 实测响应路径（与 twscrape 文档说的略不同）：
#     data.user.result.timeline.timeline.instructions[].entries[]
#     推文项  entryId 以 `tweet-` 开头，content.entryType=TimelineTimelineItem
#     游标项  entryId 以 `cursor-bottom-` 开头，content.cursorType=Bottom
#
# 实测（自己的账号）：解析出 2 条推文，正文/互动数/时间都对。
USER_TWEETS_QUERY_ID = "SXVCYB8XHSS25nzIljNtZA"
USER_TWEETS_OP = f"{USER_TWEETS_QUERY_ID}/UserTweets"

# 带回复的（暂未使用，留着备用）
USER_TWEETS_AND_REPLIES_OP = "qUpkZU6eN8MbtQb7rC_pYg/UserTweetsAndReplies"
# 只看媒体
USER_MEDIA_OP = "VyudDWQnr9vJNw7GasFz2g/UserMedia"


def build_user_tweets_variables(uid: str, count: int = 20,
                                cursor: str = "") -> dict:
    """构造 UserTweets 的 variables（来源 twscrape `user_tweets_raw`）。"""
    v = {
        "userId": str(uid),
        "count": max(1, min(int(count), 40)),
        "includePromotedContent": True,
        "withQuickPromoteEligibilityTweetFields": True,
        "withVoice": True,
        "withV2Timeline": True,
    }
    if cursor:
        v["cursor"] = cursor
    return v

# 网页端公开 Bearer（非用户凭证，是 X 网页版固定值）
#
# 来源：twscrape `account.py::TOKEN`
# 注意末尾的 `%3D` 是 URL 编码的 `=`，**照抄即可**（实测这样能用）
WEB_BEARER = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

# 搜索必需的两个 cookie（domain=.x.com）
REQUIRED_COOKIES = ("auth_token", "ct0")

# 抓取 transaction-id 素材用的页面
#
# ⚠️ twscrape 用 `https://x.com/tesla`，实测该页面能拿到含
#    INDICES 的 JS bundle。`/home` 也行（同样 304KB）。
XCLID_SOURCE_URL = "https://x.com/tesla"

# 搜索产物（product）
#   实测 "Top" 可用；"Latest" 是另一档（按时间）；"People" 搜**用户**
PRODUCT_TOP = "Top"
PRODUCT_LATEST = "Latest"
PRODUCT_MEDIA = "Media"
# 搜用户。来源：twscrape `api.py::search_user`：
#     kv = {"product": "People", **(kv or {})}
# 并复现其 `search_raw`，**用同一个 SearchTimeline operation** ——
# 调研确认：X **不存在**独立的 SearchUser/UserSearch operation
# （已逐行核对 twscrape 全部 OP_* 常量 + Scweet manifest）。
PRODUCT_PEOPLE = "People"

PRODUCT_ALIASES: dict[str, str] = {
    "note": PRODUCT_TOP,
    "all": PRODUCT_TOP,
    "default": PRODUCT_TOP,
    "top": PRODUCT_TOP,
    "hot": PRODUCT_TOP,
    "latest": PRODUCT_LATEST,
    "realtime": PRODUCT_LATEST,
    "video": PRODUCT_MEDIA,
    "image": PRODUCT_MEDIA,
    "media": PRODUCT_MEDIA,
    # 搜用户
    "user": PRODUCT_PEOPLE,
    "people": PRODUCT_PEOPLE,
    "users": PRODUCT_PEOPLE,
}


def resolve_product(search_type: str | None) -> str:
    """把前端的 search_type 解析成 X 的 product。

    未知值回退到 Top（给结果比报错有用）。
    """
    key = (search_type or "").strip().lower()
    return PRODUCT_ALIASES.get(key, PRODUCT_TOP)


def build_user_lookup_variables(screen_name: str) -> dict:
    """构造 UserByScreenName 的 variables。

    来源：twscrape `api.py::user_by_login_raw`
        kv = {"screen_name": login, "withSafetyModeUserFields": True}
    """
    return {
        "screen_name": screen_name.lstrip("@"),
        "withSafetyModeUserFields": True,
    }


def build_search_variables(
    keyword: str,
    count: int = 20,
    product: str = PRODUCT_TOP,
    cursor: str | None = None,
) -> dict:
    """构造 SearchTimeline 的 variables。

    来源：twscrape `api.py::search_raw`
        kv = {"rawQuery": q, "count": 20, "querySource": "typed_query", ...}

    翻页时把上一页的 `cursor.bottom.value` 放进 `cursor`。
    """
    variables: dict = {
        "rawQuery": keyword,
        "count": count,
        "querySource": "typed_query",
        "product": product,
        "withGrokTranslatedBio": False,
    }
    if cursor:
        variables["cursor"] = cursor
    return variables
