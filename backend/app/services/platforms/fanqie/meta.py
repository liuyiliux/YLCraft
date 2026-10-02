"""番茄小说平台元数据。

⚠️ 它是**小说站**，不是社交平台：
  · **没有评论**（章节式发布，没有"评论"这个概念）
  · **没有用户维度**（作家后台是另一套，`user_dimension=False`）
  · 所以 `probe_search_type=""` → 体检**跳过搜索探针**
    （它没有内容搜索接口）
"""
PLATFORM_META = {
    "name": "fanqie",
    "aliases": [],
    "conn_platform": "FANQIE",
    "cookie_domain": "fanqie",
    "no_login": False,
    # ⚠️ 空字符串 = 没有内容搜索 → 体检跳过探针（见 health_routes 的处理）
    "probe_search_type": "",
    "capabilities": [
        "search", "detail",
        # ⚠️ 没有评论 / 没有用户维度 —— 见上方说明
    ],
    # 不进「博主中心」/「我的数据」（它是作家后台，语义不同）
    "user_dimension": False,
}
