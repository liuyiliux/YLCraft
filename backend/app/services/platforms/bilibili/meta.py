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
        # ⚠️ 2026-10-04 修正：以前这里没声明 `replies`，注释写的是
        # 「B站子回复随顶层评论的 replies 字段返回，没有独立接口」。
        # **那是错的**，实测（BV1UAaS6KEgs，20 条顶层评论）：
        #   · 6 条带 reply_count（16/8/13/1/4/7…），但 `replies` 数组**全空**
        #   · 原因：项目走 WBI 接口 `x/v2/reply/wbi/main?mode=3`，
        #     该模式**不内嵌** replies（那是老接口 mode=1 的行为）
        #   · 老接口 `x/v2/reply/main?root=<rpid>` → **能取到**（实测 20 条）
        #   · 而 `wbi/main?root=` → code=-403「访问权限不足」
        # 所以补了 `get_replies`（走老接口），这里如实声明能力。
        "replies",
        "danmaku",           # 弹幕（仅 B站有）
        "subtitles",         # 字幕（仅 B站有）
        "download",          # 有专用下载器
    ],
}
