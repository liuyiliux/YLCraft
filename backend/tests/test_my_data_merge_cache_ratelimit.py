"""本轮三项改动的回归测试：
  ① 菜单入口合并（B站并入「我的数据」）
  ② 抖音搜博主限流要有可操作提示
  ③ 搜索结果缓存（跨平台）

## ① 菜单合并

原来菜单里有两个「我的数据」：

    /my-data            我的数据            ← B站 + 番茄
    /my-platform-data   我的数据(抖音/小红书) ← 抖音 + 小红书

**都叫"我的数据"**，用户要在两者间来回找。
现在统一到 `/my-platform-data`，B站作为其中一个平台选项
（B站分支**直接复用原组件**，不重写那 1600 行）。
`/my-data` 路由保留（老书签仍可用）。

## ② 抖音搜博主限流

实测：

    count=5 第 1 次  → 4 个 ✅
    紧接着连发多次    → 全 0 ❌
    等 ~60 秒后       → 4 个 ✅

**响应完全正常**（HTTP 200、`status_code=0`、字段齐全），
只是 `user_list` 为空 —— 靠响应字段判断不出被限流。

原来**静默返回 0 个**，用户以为"抖音搜不了博主"。
现在抛 `DouyinSearchRateLimited`（可操作提示），路由转成 **429**。

## ③ 搜索结果缓存

实测各平台单次搜索：B站 ~2s / 小红书 ~2s / 抖音 ~4s /
**X ~15s / 微博 ~21s**。

缓存放**共享入口**（`platforms.search`），所有平台受益：

    小红书  1.7s → 0.4s   提速 5x
    抖音    2.6s → 0.4s   提速 6x
    B站     1.2s → 0.4s   提速 3x

关键设计：
  · **只缓存非空结果** —— 空可能来自限流，缓存它会让"稍后重试"也拿不到
  · **key 含 conn_id** —— 不同账号结果不同，绝不能串
  · **key 含 sort_by** —— 综合/最新排序是不同结果集
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


# =============================================================================
# ① 菜单合并
# =============================================================================

def test_menu_has_single_my_data_entry():
    """**回归**：菜单里「我的数据」只应有一个入口。"""
    p = FRONTEND / "components" / "layout" / "AppLayout.tsx"
    if not p.exists():
        pytest.skip("AppLayout 不在预期位置")
    src = p.read_text(encoding="utf-8", errors="ignore")
    assert "'/my-platform-data'" in src, "应保留合并后的入口"
    assert "{ key: '/my-data'" not in src, (
        "不该再单独列 /my-data 菜单项（已并入 my-platform-data）"
    )


def test_old_my_data_route_still_exists():
    """**回归**：`/my-data` 路由要保留（老书签/深链仍可用）。"""
    p = FRONTEND / "App.tsx"
    if not p.exists():
        pytest.skip("App.tsx 不在预期位置")
    src = p.read_text(encoding="utf-8", errors="ignore")
    assert 'path="my-data"' in src, "老路由应保留"
    assert 'path="my-platform-data"' in src


def test_my_data_page_supports_embedded():
    """**回归**：`MyDataPage` 要支持 embedded 模式（嵌在合并页里）。"""
    p = FRONTEND / "pages" / "my-data" / "index.tsx"
    if not p.exists():
        pytest.skip("my-data 不在预期位置")
    src = p.read_text(encoding="utf-8", errors="ignore")
    assert "embedded" in src, "应支持 embedded 参数"
    # embedded 时不渲染自己的标题栏（否则两个标题/两个平台切换器）
    assert "{!embedded && (" in src


def test_merged_page_includes_bili():
    """合并页要包含 B站选项，并渲染原组件。"""
    p = FRONTEND / "pages" / "my-platform-data" / "index.tsx"
    if not p.exists():
        pytest.skip("my-platform-data 不在预期位置")
    src = p.read_text(encoding="utf-8", errors="ignore")
    assert "value: 'bili'" in src, "应有 B站选项"
    assert "<MyDataPage" in src, "应复用原组件"


# =============================================================================
# ② 抖音搜博主限流
# =============================================================================

def test_douyin_rate_limit_exception_exists():
    """**回归**：要有专门的限流异常类型。"""
    from app.services.platforms.douyin import client as dy

    assert hasattr(dy, "DouyinSearchRateLimited"), "应定义限流异常"


def test_rate_limit_error_is_actionable():
    """**回归**：限流错误要**可操作**（告诉用户等一会儿）。

    原来静默返回 0 个，用户以为"抖音搜不了博主"。
    """
    from app.services.platforms.douyin import client as dy

    src = inspect.getsource(dy.DouyinClient.search_users)
    assert "DouyinSearchRateLimited" in src, "空结果应抛限流异常"
    # 提示里要有"稍等/重试"这类可操作信息
    assert "稍等" in src or "重试" in src


def test_rate_limit_does_not_degrade_to_ytdlp():
    """限流异常要继承 `PlatformUnavailableError` ——
    否则上层会降级到 yt-dlp 再试一次，把限流伪装成"没结果"。"""
    from app.services.platforms.douyin.client import (
        DouyinSearchRateLimited,
        PlatformUnavailableError,
    )

    assert issubclass(DouyinSearchRateLimited, PlatformUnavailableError)


def test_route_maps_rate_limit_to_429():
    """**回归**：限流应返回 **429**（稍后重试），不是 500（服务端故障）。"""
    from app.api.v1 import users as users_api

    src = inspect.getsource(users_api)
    assert "429" in src, "限流应映射为 429"
    assert "DouyinSearchRateLimited" in src


# =============================================================================
# ③ 搜索结果缓存
# =============================================================================

def test_generic_cache_module_exists():
    """通用缓存模块要存在。"""
    from app.services.platforms import cache as pc

    assert hasattr(pc, "SearchCache")
    assert hasattr(pc, "get_search_cache")


def test_cache_key_includes_conn_id_and_sort():
    """**回归**：缓存键必须含 conn_id 与 sort_by。

    · 不含 conn_id → A 账号的结果会给 B 账号看
    · 不含 sort_by → 综合排序和最新排序串了
    """
    from app.services.platforms.cache import SearchCache

    k1 = SearchCache.make_key("xhs", "美食", 1, 10, "note", "connA", "")
    k2 = SearchCache.make_key("xhs", "美食", 1, 10, "note", "connB", "")
    assert k1 != k2, "不同 conn_id 的键必须不同"

    k3 = SearchCache.make_key("xhs", "美食", 1, 10, "note", "connA", "general")
    k4 = SearchCache.make_key("xhs", "美食", 1, 10, "note", "connA", "latest")
    assert k3 != k4, "不同排序的键必须不同"


def test_cache_hit_and_ttl():
    """缓存要能命中，且 TTL 生效。"""
    from app.services.platforms.cache import SearchCache

    c = SearchCache(ttl_seconds=60)
    k = SearchCache.make_key("xhs", "a", 1, 10)
    assert c.get(k) is None, "首次应未命中"
    c.set(k, ["x"])
    assert c.get(k) == ["x"], "应命中"

    # TTL=0 立即过期
    c.set(k, ["y"], ttl=0)
    assert c.get(k) is None, "ttl=0 应立即过期"


def test_cache_not_wired_for_empty_results():
    """**回归**：**不要缓存空结果**。

    空结果可能来自限流/风控（抖音实测：连续请求返回空，等 60 秒又好）。
    缓存它会让"稍后重试"也拿不到数据。
    """
    import app.services.platforms as platforms_pkg

    src = inspect.getsource(platforms_pkg.search)
    assert "if results:" in src, "应只在非空时写缓存"
    assert "cache.set" in src


def test_cache_wired_into_shared_entry():
    """**回归**：缓存放共享入口，所有平台受益。

    （教训：之前小红书的缓存只加在部分路径上，压根没生效。）
    """
    import app.services.platforms as platforms_pkg

    src = inspect.getsource(platforms_pkg.search)
    assert "get_search_cache" in src
    assert "cache.get" in src
    assert "make_key" in src


def test_cache_stats_available():
    """要能看命中率（便于确认缓存真的在工作）。"""
    from app.services.platforms.cache import SearchCache

    c = SearchCache()
    c.set(SearchCache.make_key("x", "k", 1, 10), [1])
    c.get(SearchCache.make_key("x", "k", 1, 10))   # hit
    c.get(SearchCache.make_key("x", "miss", 1, 10))  # miss
    s = c.stats()
    assert s["hits"] == 1 and s["misses"] == 1
    assert s["hit_rate"] == 0.5


def test_cache_evicts_when_full():
    """容量上限要生效（防止长时间运行无限增长）。"""
    from app.services.platforms.cache import SearchCache

    c = SearchCache(ttl_seconds=600, max_entries=10)
    for i in range(30):
        c.set(SearchCache.make_key("x", f"k{i}", 1, 10), [i])
    assert c.stats()["entries"] <= 10, "不应超过容量上限"
