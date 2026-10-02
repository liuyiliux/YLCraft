"""微博平台元数据。

## ⚠️ 两个实测坑（都写在这里，避免各处重复踩）

1. **cookie_domain 必须是 `"weibo"`**，不是 `"weibo.com"` ——
   实测主站 weibo.com 的 cookie 在 `m.weibo.cn` **无效**
   （`api/config` 返回 `login:false`）。

2. **评论的楼中楼拿不到** —— 所以 capabilities 里**没有** `replies`：
   · 顶层评论的 `comments` 字段：实测 20 条里 0 条带
   · `/comments/hotFlowChild`：返回 `ok=0`（需额外参数）
   交叉验证 MediaCrawler（★66k）同样只读 `comments` 字段且默认关着开关。
"""
PLATFORM_META = {
    "name": "weibo",
    "aliases": ["wb"],
    "conn_platform": "WEIBO",
    # ⚠️ 是 "weibo" 不是 "weibo.com"（见上方说明）
    "cookie_domain": "weibo",
    "no_login": False,
    "probe_search_type": "note",
    "capabilities": [
        "search", "detail", "search_users", "user_profile", "user_videos",
        "self_profile",      # 「我的数据」
        "comments",          # /comments/hotflow（纯 HTTP）
        # ⚠️ 没有 "replies" —— 见上方说明
    ],
}
