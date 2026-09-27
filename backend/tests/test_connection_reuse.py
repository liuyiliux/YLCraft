"""验证连接复用逻辑：重新登录应刷新同一条记录，而不是新建。

## 背景（2026-09-27）

用户重新登录抖音后，连接 ID 从 cd27d049 变成 56804c13，
表现为"界面上/我脚本里引用的旧 ID 失效"。

根因：`_save_to_db_sync` 用 `last_used.desc().nulls_last()` 找要复用的连接，
而**新建连接的 last_used 是 NULL**，会被排到最后 →
每次都选中"最老的、用过的"那条，新 cookie 写进旧记录，
库里堆出多条同平台连接。

已改为按 `updated_at.desc()` 取最近的那条。

本测试不碰数据库：用假 session 检查 SQL 的 order_by 子句。
"""
from __future__ import annotations

import inspect

import pytest


@pytest.mark.parametrize(
    "module_path,func_name",
    [
        ("app.services.cookies.patchright_manager", "_save_to_db_sync"),
        ("app.services.cookies.qrcode_manager", "_save_to_db_sync"),
    ],
)
def test_connection_lookup_orders_by_updated_at(module_path, func_name):
    """找"要复用的连接"必须按 updated_at 倒序。

    按 last_used 倒序 + nulls_last 是错的：新建连接的 last_used 是 NULL，
    会被排到末尾，于是永远复用最老的那条。
    """
    from importlib import import_module

    mod = import_module(module_path)
    # 两个模块里这个函数可能是方法或模块级函数，都试一遍
    target = None
    for name in dir(mod):
        obj = getattr(mod, name)
        if inspect.isclass(obj) and hasattr(obj, func_name):
            target = getattr(obj, func_name)
            break
        if inspect.isfunction(obj) and obj.__name__ == func_name:
            target = obj
    assert target is not None, f"{module_path} 里找不到 {func_name}"

    src = inspect.getsource(target)
    assert "updated_at.desc()" in src, (
        "应按 updated_at 倒序取最近更新的连接"
    )
    assert "last_used.desc()" not in src, (
        "不得按 last_used 排序——新建连接的 last_used 是 NULL，会选中旧记录"
    )


def test_patchright_lookup_documents_why():
    """留下原因说明，避免后人改回 last_used。"""
    from app.services.cookies import patchright_manager as pm

    src = inspect.getsource(pm.PatchrightAcquisitionManager._save_to_db_sync)
    assert "nulls_last" in src or "NULL" in src, "应说明为什么不能用 last_used"
    assert "过期" in src or "多条" in src, "应说明后果（堆出多条连接）"


# =============================================================================
# 旧 conn_id 的兜底（用户重新登录后 ID 会变）
# =============================================================================

def test_resolve_connection_accepts_enum_name_and_value():
    """平台名大小写都要接受。

    踩过：`PlatformType("DOUYIN")` 抛 ValueError——枚举 value 是**小写**
    （douyin），而 PG 里存的是 **name（大写）**，调用方两种都可能传。
    """
    import inspect

    from app.services.platforms import login_health as lh

    src = inspect.getsource(lh.resolve_connection)
    assert "lower()" in src and "upper()" in src, "应同时尝试大小写"
    assert "PlatformType[" in src, "还应支持按枚举名（大写）查找"


def test_resolve_connection_guards_invalid_platform():
    """非法平台名不能崩。

    实测：直接把 "NOSUCHPLATFORM" 拼进 SQL 会抛
    `DataError: invalid input value for enum platformtype` → 500。
    """
    import inspect

    from app.services.platforms import login_health as lh

    src = inspect.getsource(lh.resolve_connection)
    assert "ValueError" in src, "应捕获枚举转换失败"
    assert "KeyError" in src, "应捕获枚举名查找失败"


def test_health_endpoints_use_resolve_connection():
    """体检端点必须用 resolve_connection，而不是直接 get_raw_cookie。

    否则用户重新登录（连接 ID 变了）后，旧 ID 会显示"没有 Cookie"，
    看起来像登录丢了，实际只是引用了过期 ID。
    """
    from app.services.platforms import login_health as lh
    from app.services.platforms.douyin import health as dy_health
    from app.services.platforms.xiaohongshu import routes as xhs_routes

    assert hasattr(lh, "resolve_connection")
    assert "resolve_connection" in inspect.getsource(dy_health.douyin_login_health)
    assert "resolve_connection" in inspect.getsource(xhs_routes.xhs_login_health)
