"""YouTube 平台元数据。

⚠️ **免登录** —— 公开频道数据用 yt-dlp 直接取，不需要 Cookie。
所以 `no_login=True`，接口层不会去找连接。

## 评论（2026-10-01 加）

走 yt-dlp 的 innertube 实现，**必须设 `max_comments` 上限** ——
不设就是无上限翻页（实测某视频报 ~1063 万条评论，跑了 10 分钟没停）。

没有"子回复"能力：yt-dlp 返回的是**平铺列表**，回复靠 `parent` 字段标识，
我们目前只取顶层（`parent == "root"`）。
"""
PLATFORM_META = {
    "name": "youtube",
    "aliases": [],
    "conn_platform": "YOUTUBE",
    "cookie_domain": "youtube",
    # ⚠️ 免登录（yt-dlp 直接取公开数据）
    "no_login": True,
    "probe_search_type": "video",
    "capabilities": [
        "search", "detail", "search_users", "user_profile", "user_videos",
        "comments",          # yt-dlp innertube（设了硬上限 MAX_SAFE=200）
        # ⚠️ 没有 "replies" / "self_profile" —— 见上方说明
    ],
    # 免登录平台没有"我的账号"概念 → 不进「我的数据」页
    "user_dimension": True,
}
