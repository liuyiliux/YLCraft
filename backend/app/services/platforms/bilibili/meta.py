"""B站平台元数据。

⚠️ 关于 `cookie_domain`：必须是 `"bili"`（**不是** `"bilibili"`）——
实测 `netscape_to_header` 认这个名字，写错会返回 0 字符 cookie。
"""
PLATFORM_META = {
    "name": "bili",
    "aliases": ["bilibili"],
    "conn_platform": "BILIBILI",
    "cookie_domain": "bili",
    "no_login": False,
    # B站体检探针用视频搜索（它有 video/article 等多种搜索类型）
    "probe_search_type": "video",
    "capabilities": [
        "search", "detail", "search_users", "user_profile", "user_videos",
        "comments",          # /x/v2/reply
        # ⚠️ B站有比基类**更完整**的游标分页方法（get_comments_paged，
        #    含排序/总数）—— 接口层据此走专用分支，不靠硬编码平台名。
        "comments_paged",
        # ⚠️ 没有 "replies" —— B站子回复**随顶层评论的 `replies` 字段返回**，
        #    没有独立的"取子回复"接口（见 comments.py 的说明）
        "danmaku",           # 弹幕（仅 B站有）
        "subtitles",         # 字幕（仅 B站有）
        "download",          # 有专用下载器
    ],
}
