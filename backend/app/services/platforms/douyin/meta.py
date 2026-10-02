"""抖音平台元数据。

⚠️ 评论**必须 a_bogus 签名**（与**搜索**不同）：
    不带 → HTTP 200 + **0 字节**（不是错误码！）
    带   → HTTP 200 + 19 条评论
签名用 MediaCrawler 的 `libs/douyin.js`（已做**安全审查**，
见 `douyin/sign.py` 的 docstring）。
"""
PLATFORM_META = {
    "name": "douyin",
    "aliases": ["dy"],
    "conn_platform": "DOUYIN",
    "cookie_domain": "douyin",
    "no_login": False,
    "probe_search_type": "video",
    "capabilities": [
        "search", "detail", "search_users", "user_profile", "user_videos",
        "self_profile",
        "comments",          # /aweme/v1/web/comment/list/（需 a_bogus）
        "replies",           # /comment/list/reply/（需 sign_reply —— 不同签名函数）
        "download",          # 有专用下载器
    ],
}
