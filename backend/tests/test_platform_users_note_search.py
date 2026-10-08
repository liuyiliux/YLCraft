"""博主中心的**后端连接来源**差异（钉住，避免误解）。

## 为什么还留着这个文件（2026-10-07）

原本这里有 16 个测试：13 个测「博主中心搜作品」（`/crawler/search-enhanced`），
3 个测批量导入素材库。**这些功能在 2026-10-07 16:42（`0980f001`）被删除了**
（那次改动的标题是「去掉三个『点了没反应』的 tab」）。

删功能时**测试没跟着删**，于是 `pytest -k "users or user_"` 一律变红 ——
红得没有意义（不是回归，是测试在断言一个**已经不存在的东西**）。
⇒ 已按用户确认删除该功能，把对应断言一并移除。

保留下面两条：它们与那个功能**无关**，且记录了一个很容易误解的点
（`/users/*` 与 `/crawler/*` 的连接来源不一样），
删掉的话以后还会有人把两者搞混。
"""

from __future__ import annotations

import inspect

import pytest


def test_users_api_resolves_connection_itself():
    """`/users/*` 由后端自己取连接（前端不必传 conn_id）。"""
    from app.api.v1 import users as users_api

    src = inspect.getsource(users_api._client_for)
    assert "resolve_connection" in src, "后端应自己解析连接"


def test_crawler_search_requires_conn_id_from_caller():
    """`/crawler/search-enhanced` 需要前端传 conn_id（与 /users/* 不同）。

    ⚠️ 这条差异曾经坑过人：不传 `conn_id` 时后端拿不到 Cookie，
    抖音返回 `status_code=2483`（游客态），**结果恒为空**，
    看起来像"关键词没内容"，实际是没带登录态。
    """
    from app.api.v1 import crawler as crawler_api

    src = inspect.getsource(crawler_api.search_enhanced)
    assert "conn_id" in src, "应从请求里取 conn_id"
    assert "_get_conn_cookie" in src, "应据此取 Cookie"
