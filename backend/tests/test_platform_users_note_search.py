"""博主中心的「作品搜索」契约测试。

## 背景（2026-09-27）

用户要求"都要"：把作品搜索也加到博主中心。

**不需要新后端** —— `/api/v1/crawler/search-enhanced` 已经支持作品搜索，
只是博主中心页面没提供入口（用户得去「内容搜索」页）。

## 实测发现的关键坑：`conn_id` 必须传

我在博主中心页第一次调用 `searchEnhanced` 时**没传 `conn_id`** →
后端拿不到 Cookie → 抖音返回 `status_code=2483`（游客态）→
**结果恒为空**，日志是 `No results via platforms module for douyin`。

表现是"找到 0 条结果"，**看起来像关键词没内容**，
实际是没带登录态 —— 属于很容易误判的一类。

⚠️ 注意两个接口的**连接来源不同**（这个差异容易踩）：

| 接口 | 连接从哪来 |
|------|-----------|
| `/api/v1/users/*` | 后端**自己**用 `resolve_connection("", ...)` 取 |
| `/api/v1/crawler/search-enhanced` | **必须前端传 `conn_id`** |

所以 `/users/*` 不传 conn_id 也能用，但作品搜索不传就不行。

## 实测结果

    抖音  「穿搭」→ 共 18 个（Twins 下班look… 15.7万赞 / #蕾系穿搭 5.0万赞）
    小红书「美食」→ 共 30 个（红油火锅 445 / 麻辣烫 1314 …）
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _read(rel: str) -> str:
    p = FRONTEND / rel
    if not p.exists():
        pytest.skip(f"前端源码不在预期位置: {rel}")
    return p.read_text(encoding="utf-8", errors="ignore")


def _strip_line_comments(src: str) -> str:
    return "\n".join(
        line for line in src.splitlines() if not line.strip().startswith("//")
    )


# =============================================================================
# 作品搜索入口
# =============================================================================

def test_page_has_search_mode_switch():
    """博主中心要有「搜博主 / 搜作品」两个维度。"""
    src = _read("pages/platform-users/index.tsx")
    assert "searchMode" in src, "缺少搜索维度 state"
    assert "搜博主" in src and "搜作品" in src, "应有维度切换"


def test_note_search_reuses_existing_endpoint():
    """作品搜索复用 /crawler/search-enhanced（不需要新后端接口）。"""
    src = _read("pages/platform-users/index.tsx")
    assert "searchEnhanced" in src, "应调用 searchEnhanced"
    assert "search_type: 'note'" in src


def test_note_search_passes_conn_id():
    """**回归**：作品搜索必须传 conn_id。

    不传的话后端拿不到 Cookie，抖音返回 status_code=2483（游客态），
    结果恒为空 —— 表现为"找到 0 条结果"，看起来像关键词没内容。
    """
    src = _read("pages/platform-users/index.tsx")
    code = _strip_line_comments(src)
    # 两处调用（首次搜索 + 翻页）都要传
    assert code.count("conn_id: connId") >= 2, "首次搜索与翻页都要传 conn_id"


def test_note_search_platform_alias():
    """小红书在 crawler 接口里叫 `xhs`（不是 xiaohongshu）。"""
    src = _read("pages/platform-users/index.tsx")
    assert "platform === 'xiaohongshu' ? 'xhs' : platform" in src, (
        "作品搜索要把 xiaohongshu 换成 crawler 接口认识的 xhs"
    )


def test_note_pagination_passes_total():
    """**回归**：作品列表分页必须传 total。

    不传 total 时 antd 用当前页条数当总数 → 永远 1 页
    （B站 UP主搜索踩过同一个坑）。
    """
    src = _read("pages/platform-users/index.tsx")
    i = src.find("columns={noteColumns}")
    assert i != -1, "应找到作品结果表"
    seg = _strip_line_comments(src[i:i + 900])
    assert "total: noteTotal" in seg, "作品分页必须传 total"


def test_note_state_exists():
    src = _read("pages/platform-users/index.tsx")
    assert "const [notes, setNotes]" in src
    assert "const [noteTotal, setNoteTotal]" in src
    assert "const [notePage, setNotePage]" in src


def test_notes_cleared_on_search():
    """新搜索要清掉上一次的结果，避免两个维度的数据混在一起。"""
    src = _read("pages/platform-users/index.tsx")
    assert "setNotes([])" in src, "搜索时应清空作品结果"


def test_dependencies_include_conn_id():
    """**回归**：useCallback 依赖数组要包含 connId。

    否则切换连接后拿到的是闭包里的旧值，搜索仍用旧连接。
    """
    src = _read("pages/platform-users/index.tsx")
    assert "[platform, keyword, searchMode, connId]" in src, "handleSearch 依赖缺 connId"
    assert "[platform, keyword, connId]" in src, "handleNotePage 依赖缺 connId"


# =============================================================================
# 批量导入素材库（本轮新增）
# =============================================================================

def test_import_uses_same_endpoint_as_crawler():
    """导入复用 /crawler/import（与「内容搜索」页同一套，不新造接口）。"""
    src = _read("pages/platform-users/index.tsx")
    assert "importCrawler" in src, "应调用 importCrawler"


def test_import_sends_required_fields():
    """导入要带齐字段（id/platform/title/cover/url…），否则入库后缺信息。"""
    src = _read("pages/platform-users/index.tsx")
    i = src.find("importCrawler({")
    assert i != -1, "缺少 importCrawler 调用"
    seg = src[i:i + 450]
    for f in ("id:", "platform:", "title:", "cover:", "url:"):
        assert f in seg, f"导入载荷缺 {f}"


def test_row_selection_enabled():
    """要有行多选（否则没法批量选作品）。"""
    src = _read("pages/platform-users/index.tsx")
    assert "rowSelection" in src, "作品表应支持多选"


def test_import_button_exists():
    src = _read("pages/platform-users/index.tsx")
    assert "导入素材库" in src, "缺少导入按钮"
    assert "DatabaseOutlined" in src, "应有图标"


def test_import_disabled_without_selection():
    """没勾选时按钮要禁用（避免误触导入空列表）。"""
    src = _read("pages/platform-users/index.tsx")
    assert "selectedNotes.length === 0" in src, "空选时应禁用"


def test_selection_cleared_on_new_search_and_platform_switch():
    """**回归**：新搜索 / 切平台要清掉勾选。

    否则会导入上一次（已不在当前结果里）的行。
    """
    src = _read("pages/platform-users/index.tsx")
    code = _strip_line_comments(src)
    assert code.count("setSelectedNotes([])") >= 2, (
        "handleSearch 与切平台 effect 都要清空勾选"
    )


# =============================================================================
# 后端连接来源差异（钉住，避免误解）
# =============================================================================

def test_users_api_resolves_connection_itself():
    """`/users/*` 由后端自己取连接（前端不必传 conn_id）。"""
    from app.api.v1 import users as users_api

    src = inspect.getsource(users_api._client_for)
    assert "resolve_connection" in src, "后端应自己解析连接"


def test_crawler_search_requires_conn_id_from_caller():
    """`/crawler/search-enhanced` 需要前端传 conn_id（与 /users/* 不同）。"""
    from app.api.v1 import crawler as crawler_api

    src = inspect.getsource(crawler_api.search_enhanced)
    assert "conn_id" in src, "应从请求里取 conn_id"
    assert "_get_conn_cookie" in src, "应据此取 Cookie"
