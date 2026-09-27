"""小红书搜索缓存与会话复用的契约测试。

## 用户需求（2026-09-27）

"小红书应该加个缓存，这样切换分页再切回来时候不用重新打开浏览器查询"

## 实测效果

    1) 首次搜索        16.0 s   开浏览器 + 预热 + 搜
    2) 同页再搜         0.38 s   命中结果缓存（42 倍）
    3) 第 2 页         22.2 s   复用会话（仍需滚动加载）
    4) 换关键词        14.4 s   复用会话（省掉预热）
    5) 切回第 1 页      0.40 s   命中结果缓存（40 倍）

## 踩过的两个坑（都要钉住）

1. 缓存最初只加在 `search_with_runtime`，但实际调用走的是**注入页分支**
   （base._init_patchright 先建好 page），缓存压根没生效——三次搜索都是 16 秒。
   所以缓存必须在 `search_via_patchright` 这个共享入口。

2. `__aexit__` 的所有权判断写反了：自建的跳过关闭（对），
   复用的反而去关（错），把池里的会话关死 → 第 3 次搜索报 TargetClosedError。
"""

from __future__ import annotations

import inspect
import time

import pytest


# =============================================================================
# 结果缓存
# =============================================================================

def test_cache_key_separates_accounts():
    """不同连接的缓存必须隔离——不同账号看到的结果不同。"""
    from app.services.platforms.xiaohongshu.cache import SearchResultCache

    k1 = SearchResultCache.make_key("xhs", "美食", 1, 10, "note", "conn-A")
    k2 = SearchResultCache.make_key("xhs", "美食", 1, 10, "note", "conn-B")
    assert k1 != k2


def test_cache_key_separates_pages():
    """不同页码必须分开缓存，否则第 2 页会拿到第 1 页的数据。"""
    from app.services.platforms.xiaohongshu.cache import SearchResultCache

    k1 = SearchResultCache.make_key("xhs", "美食", 1, 10, "note", "c")
    k2 = SearchResultCache.make_key("xhs", "美食", 2, 10, "note", "c")
    assert k1 != k2


def test_cache_key_separates_keywords():
    from app.services.platforms.xiaohongshu.cache import SearchResultCache

    k1 = SearchResultCache.make_key("xhs", "美食", 1, 10, "note", "c")
    k2 = SearchResultCache.make_key("xhs", "旅行", 1, 10, "note", "c")
    assert k1 != k2


def test_cache_hit_and_miss():
    from app.services.platforms.xiaohongshu.cache import SearchResultCache

    cache = SearchResultCache(ttl_seconds=60)
    key = cache.make_key("xhs", "美食", 1, 10, "note", "c")
    assert cache.get(key) is None, "未写入应 miss"
    cache.set(key, ["r1"])
    assert cache.get(key) == ["r1"], "写入后应命中"
    assert cache.stats()["hits"] == 1


def test_cache_expires():
    """过期后应 miss（避免看到太旧的数据）。"""
    import time

    from app.services.platforms.xiaohongshu.cache import SearchResultCache

    cache = SearchResultCache(ttl_seconds=1)
    key = "k"
    cache.set(key, ["old"], ttl=1)
    assert cache.get(key) == ["old"], "未过期应命中"
    time.sleep(1.05)
    assert cache.get(key) is None, "过期后应 miss"


def test_cache_ttl_is_reasonable():
    """TTL 要覆盖"翻页/切回"这类连续操作（几分钟），但不能长到看到旧数据。"""
    from app.services.platforms.xiaohongshu.cache import DEFAULT_TTL_SECONDS

    assert 60 <= DEFAULT_TTL_SECONDS <= 3600


def test_cache_invalidate_by_conn():
    """按连接清缓存（重新登录后调用）。"""
    from app.services.platforms.xiaohongshu.cache import SearchResultCache

    cache = SearchResultCache()
    cache.set(cache.make_key("xhs", "a", 1, 10, "note", "conn-A"), ["x"])
    cache.set(cache.make_key("xhs", "b", 1, 10, "note", "conn-B"), ["y"])
    n = cache.invalidate("conn-A")
    assert n == 1
    assert cache.get(cache.make_key("xhs", "b", 1, 10, "note", "conn-B")) == ["y"]


# =============================================================================
# 缓存接线位置（踩过的坑）
# =============================================================================

def test_cache_is_at_shared_entry():
    """缓存必须加在共享入口 search_via_patchright。

    只加在 search_with_runtime 是错的——实际调用走注入页分支，缓存不生效。
    """
    from app.services.platforms.xiaohongshu import search_patchright as sp

    src = inspect.getsource(sp.search_via_patchright)
    assert "get_result_cache" in src, "共享入口应有缓存"
    assert "cache.get" in src
    assert "cache.set" in src


# =============================================================================
# 浏览器会话复用
# =============================================================================

def test_session_pool_get_put():
    from app.services.platforms.session_pool import PooledSession, SessionPool

    pool = SessionPool()
    session = PooledSession(ctx=object(), page=object())
    pool.put("k", session)
    assert pool.get("k") is session


def test_session_pool_reclaims_idle():
    """空闲超时应回收，不长期占着浏览器。"""
    from app.services.platforms.session_pool import PooledSession, SessionPool

    pool = SessionPool(idle_seconds=0)
    session = PooledSession(ctx=object(), page=object())
    session.last_used = time.monotonic() - 10
    pool.put("k", session)
    assert pool.get("k") is None, "过期的会话应被回收"


def test_session_pool_idle_default_is_reasonable():
    from app.services.platforms.session_pool import DEFAULT_IDLE_SECONDS

    assert 60 <= DEFAULT_IDLE_SECONDS <= 7200


def test_base_never_closes_pooled_context():
    """**关键回归**：客户端退出时不能关池里的会话。

    踩过：所有权判断写反 → 复用的会话被关死 → 第 3 次搜索
    报 TargetClosedError（实测 0 条）。

    用 AST 检查真实语句顺序（避开注释里的 'close()' 字样）。
    """
    import ast
    import textwrap

    from app.services.platforms.base import BasePlatformClient

    src = textwrap.dedent(inspect.getsource(BasePlatformClient.__aexit__))
    tree = ast.parse(src.replace("async def ", "def "))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))

    # 找到 `if ... _patchright_pooled ...: return` 的位置，
    # 以及第一个真实的 .close() 调用的位置
    guard_line = None
    close_line = None
    for node in ast.walk(fn):
        if isinstance(node, ast.If) and "_patchright_pooled" in ast.unparse(node.test):
            guard_line = node.lineno
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "close" and close_line is None:
                close_line = node.lineno

    assert guard_line is not None, "应有基于 _patchright_pooled 的保护"
    assert close_line is not None, "应存在 close 调用"
    assert guard_line < close_line, "已入池的会话必须在任何 close 之前 return"


def test_base_uses_shared_pool():
    """base 必须用跨平台的 session_pool（与 xhs 模块同一个池）。"""
    from app.services.platforms import base as base_mod

    src = inspect.getsource(base_mod)
    assert "platforms.session_pool" in src or "from .session_pool" in src


def test_session_key_format_consistent():
    """base 与 xhs 模块的 session key 必须一致，否则各自建会话、复用失效。"""
    from app.services.platforms import base as base_mod
    from app.services.platforms.xiaohongshu import search_patchright as sp

    base_src = inspect.getsource(base_mod)
    xhs_src = inspect.getsource(sp.search_with_runtime)
    assert 'f"{self.config.platform}|{conn_id or \'-\'}"' in base_src
    assert 'f"xhs|{conn_id or \'-\'}"' in xhs_src
