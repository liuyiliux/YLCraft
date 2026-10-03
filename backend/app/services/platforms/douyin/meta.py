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

    # ⚠️ **单页型平台** —— 前端必须用「加载更多」，不能用页码分页器
    # （2026-10-03 实测，关键词「沈阳」）
    #
    #     每页10条 ->  9 条（count=10 抖音只给 9）
    #     每页20条 -> 17 条（count=20 抖音给 17）
    #     每页50条 -> 17 条（仍被 count 上限 20 截住）
    #     page=2   -> HTTP 429 / data=[]   ← offset>0 服务端不给数据
    #
    # 所以「点第 2 页」在抖音上必然失败，只能"一次取满 18 条"。
    #
    # ⚠️ **平台行为会变**，所以标了日期，改之前先复验：
    #     2026-09-27  实测 offset 翻页**有效**（cursor 依次 0/40/60）
    #     2026-09-28  复测 offset=20 **返回 0 条**（真实浏览器里也一样）
    #     2026-10-03  复测**仍然**返回空 → 结论未变
    "pagination": "single",
    # 单次上限实测 17~18 条（count 上限是 20，抖音自己少给 2 条）
    "single_page_max": 18,
}
