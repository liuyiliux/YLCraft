"""X (Twitter) 平台元数据。

⚠️ **cookie_domain 必须是 `"x.com"`**（**不是** `"twitter"`）——
实测 `netscape_to_header` 认这个名字，写错会返回 0 字符。

## 双路径搜索

X 的搜索有**两条路**（`search_http.py` + `search_dom.py`）：
  · HTTP 优先（需 auth_token + ct0 + x-client-transaction-id）
  · DOM 回退（transaction-id 生成失败 / X 改结构时用）

评论（`TweetDetail`）**只走 HTTP** —— 实测够用，且响应 176KB，
用浏览器反而更慢。
"""
PLATFORM_META = {
    "name": "twitter",
    "aliases": ["x", "tw"],
    "conn_platform": "TWITTER",
    # ⚠️ 是 "x.com" 不是 "twitter"（见上方说明）
    "cookie_domain": "x.com",
    "no_login": False,
    "probe_search_type": "note",
    "capabilities": [
        "search", "detail", "search_users", "user_profile", "user_videos",
        "self_profile",
        "comments",          # TweetDetail GraphQL
        # ⚠️ 2026-10-04 实测：声明了，但**常常取不到** ——
        #    二级回复虽然在同一棵 TweetDetail 树里（靠
        #    `in_reply_to_status_id_str` == 父评论 id 筛），
        #    但 X **不一定把它下发给客户端**。
        #    实测（tweet 2104992402851422363）：顶层 9 条里 3 条 `reply_count=1`，
        #    打 parent_id → 200 但 0 条；加诊断日志确认
        #    **原始树里被引用 0 次** —— 数据压根没来，不是我们过滤掉了。
        #    （已删 / 折叠 / 需额外请求展开，都可能）
        #
        #    所以：代码保留（X 改了就能用），但**当前不能对外宣称支持**。
        #    ⚠️ 抽样教训：不能用「这页有没有 reply_count>0」来判断
        #       平台支不支持 —— 快手实测 reply_count 全 0，
        #       直接打接口却返回了真实数据。**字段是提示，接口才是事实。**
        "replies",           # 二级回复在同一棵树里，靠父 id 筛（但 X 未必下发）
        # ⚠️ 2026-10-11 加：**自己点赞过**的推文列表。
        #
        # 与 `user_videos`（UserTweets，查**别人**发的）不同：
        # 这是 `Likes` 操作，且 X 的点赞是**私密**的 —— 只对自己有效。
        # queryId 实测抓取（twscrape 里没有这个操作），见 `apis.LIKES_QUERY_ID`。
        "self_likes",
        # ⚠️ 2026-10-11 加：「**正在关注**」作品流（我关注的账号发的推文）。
        #
        # 与 `self_likes` 一样是"我视角"的数据，但内容来自**别人**。
        # 走 `HomeLatestTimeline`（**POST**；queryId 实测抓的 ——
        # 它**不在 JS bundle 里**，是抓真实网络请求拿到的）。
        "home_feed",
        "download",          # 有专用下载器
    ],
}
