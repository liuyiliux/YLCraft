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
    # ⚠️ **不声明 search/detail**（2026-10-02 修）
    #
    # 原来这里写了 `["search", "detail"]`，但 `client.py` 里这两个方法
    # 都只 `raise NotImplementedError`（番茄是章节式发布，没有通用搜索）。
    # **声明了却没实现 = 假支持**（仓库铁律：假选项比没有更糟）——
    # 任何依据 `capabilities` 判断的下游都会把番茄显示成"支持搜索"，
    # 用户一点就炸。
    #
    # `test_platform_meta_single_source.py::test_fanqie_does_not_fake_support`
    # 守着这条：以后真实现了记得同步加回来。
    "capabilities": [],
    # 不进「博主中心」/「我的数据」（它是作家后台，语义不同）
    "user_dimension": False,
}
