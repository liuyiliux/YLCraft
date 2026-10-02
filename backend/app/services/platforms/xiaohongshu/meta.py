"""小红书平台元数据。

## ⚠️ 评论**没做**（所以 capabilities 里没有 `comments`）

原因：小红书评论接口需要 `xsec_token` + `X-s` 签名，
且风控期极易失败。**用户也明确要求排除**（风控期做了也无法验证）。

## 风控很敏感

实测 461 是常态。前端有"去官网搜"的降级出口。
"""
PLATFORM_META = {
    "name": "xiaohongshu",
    "aliases": ["xhs"],
    "conn_platform": "XHS",
    "cookie_domain": "xiaohongshu",
    "no_login": False,
    "probe_search_type": "note",
    "capabilities": [
        "search", "detail", "search_users", "user_profile", "user_videos",
        "self_profile",
        # ⚠️ 没有 "comments" —— 见上方说明
    ],
}
