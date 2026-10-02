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
        "replies",           # 二级回复在同一棵树里，靠父 id 筛
        "download",          # 有专用下载器
    ],
}
