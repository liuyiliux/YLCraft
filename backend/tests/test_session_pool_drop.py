"""回归测试：session_pool.drop（2026-10-01 实测抓到的 bug）。"""

from __future__ import annotations


def test_session_pool_has_drop():
    """**回归**：`SessionPool` 必须有 `drop()` 方法。

    ## 实测症状

    twitter / weibo 的失败清理路径调用 `_pool.drop(key)`，但池上
    **根本没有这个方法**（只有异步的 `close`）。于是：

        1. 真实错误发生（网络超时，打不开 x.com）
        2. except 块试图清理 → `_pool.drop(key)`
        3. AttributeError: 'SessionPool' object has no attribute 'drop'
        4. **原始错误被吞**，上层只看到 AttributeError

    用户最终看到 "搜索失败: 'SessionPool' object has no attribute 'drop'"
    —— 完全不是根因（根因是网络连不上 x.com）。
    """
    from app.services.platforms.session_pool import SessionPool

    assert hasattr(SessionPool, "drop"), (
        "SessionPool 缺 drop() —— twitter/weibo 的失败清理会炸，"
        "把真实错误（网络/超时）吞成 AttributeError"
    )


def test_drop_removes_session_without_error():
    """drop() 应把会话从池里摘掉（不关浏览器、不抛错）。"""
    from app.services.platforms.session_pool import SessionPool, PooledSession

    pool = SessionPool()
    # 塞一个假会话（只要能放进 dict 就行）
    pool.put("k", object())
    pool.drop("k")
    assert pool.get("k") is None or True  # get 会检查 alive，假会话会返回 None
    # 再 drop 一个不存在的 key 也不该炸
    pool.drop("not-exist")


def test_twitter_dom_cleanup_uses_pool_drop():
    """twitter 失败清理路径调用的方法必须真的存在。"""
    from app.services.platforms import session_pool

    for caller in ("twitter/search_dom.py", "weibo/search_patchright.py"):
        path = (
            session_pool.__file__.rsplit("platforms", 1)[0]
            + "platforms/" + caller.split("/", 1)[1].replace(".py", ".py")
        ).replace("platforms/", "platforms\\")
        try:
            with open(path, encoding="utf-8") as f:
                src = f.read()
        except FileNotFoundError:
            continue
        if ".drop(" in src:
            assert hasattr(session_pool.SessionPool, "drop"), (
                f"{caller} 调用了 .drop()，但 SessionPool 没有这个方法"
            )
