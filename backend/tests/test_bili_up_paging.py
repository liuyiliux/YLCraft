"""B站 UP主搜索分页的契约测试。

## 用户反馈（2026-09-27）

"b站Up搜索没有分页" —— 截图显示"共 20 个用户 < 1 >"，只有 1 页。

## 排查结论：**后端是好的，前端漏传 total**

后端实测（`/api/v1/crawler/search-enhanced?platform=bili&search_type=user`）：

    page=1 → 20 条, total=1000
    page=2 → 20 条, total=1000    ← 翻页生效，返回不同用户
    B站原始响应: numResults=1000, numPages=50

数据链其实完整（`client.search_users` 把 `numResults` 写进
`results[0].raw_data["_total"]`，crawler 层再转成响应里的 `total`）。

**问题在前端** `/up-analytics`：

    pagination={{
      pageSize: 20,
      showTotal: (t) => `共 ${t} 个用户`,   // 没传 total！
    }}

antd 的 Pagination 不传 `total` 时用 `dataSource.length`（=当前页条数）
当总数 → 永远只渲染 1 页。

而且 `page` 原来只是 `handleSearchUp(page = 1)` 的**函数默认参数**，
没有 state，所以即使有分页器也翻不了页。

## 修法

  · 新增 `upTotal` state，从 `data.total` 读
  · 新增 `upPage` state，`pagination.current` 绑它
  · `pagination.onChange` **重新发起搜索**（结果分页在服务端，
    不是前端切片）
  · 新关键词搜索从第 1 页开始（搜索按钮传 1）

## 实测验证（bsk + 用户已登录 Chrome）

修复前：`共 20 个用户 < 1 >`
修复后：`共 1000 个用户 1 2 3 4 5 … 50`
点第 2 页 → 显示完全不同的 UP 主（优锐科技/松盛优住/家培优/优尚美艺…）
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
# 后端（本来就是好的，钉住别退化）
# =============================================================================

def test_backend_returns_total_for_user_search():
    """后端 user 搜索要把 B 站的 numResults 带出来。

    `client.search_users` 把总数写进 `results[0].raw_data["_total"]`，
    crawler 层再转成响应里的 `total`。
    """
    from app.services.platforms.bilibili.client import BilibiliClient

    src = inspect.getsource(BilibiliClient.search_users)
    assert "numResults" in src, "应读 B 站的 numResults"
    assert "numPages" in src, "应支持 numPages 兜底"
    assert "_total" in src, "应把总数放进 raw_data 供上层读"


def test_backend_accepts_page_param():
    """`search_users` 要接受 page 参数（否则翻页请求都返回第 1 页）。"""
    from app.services.platforms.bilibili.client import BilibiliClient

    sig = inspect.signature(BilibiliClient.search_users)
    assert "page" in sig.parameters, "应接受 page"


def test_backend_passes_page_from_search():
    """`search()` 分派到 search_users 时要把 params.page 传下去。"""
    from app.services.platforms.bilibili.client import BilibiliClient

    src = inspect.getsource(BilibiliClient.search)
    assert "page=params.page" in src, "应透传页码"


def test_crawler_service_exposes_total():
    """crawler 层要把 `_total` 转成响应里的 total。"""
    from app.services.crawler import service as svc

    src = inspect.getsource(svc.CrawlerService._search_via_platforms)
    assert "_total" in src, "应读取平台给的 _total"


# =============================================================================
# 前端（bug 在这里）
# =============================================================================

def test_pagination_passes_total():
    """**回归**：pagination 必须传 total。

    不传时 antd 用 dataSource.length 当总数 → 永远 1 页
    （实测表现："共 20 个用户 < 1 >"，而后端返回的是 1000）。
    """
    src = _read("pages/up-analytics/index.tsx")
    i = src.find("columns={upColumns}")
    assert i != -1, "应找到 UP主结果表"
    seg = _strip_line_comments(src[i:i + 900])
    assert "total: upTotal" in seg, "pagination 必须传 total"
    assert "current: upPage" in seg, "应绑定当前页"


def test_up_total_state_exists():
    """要有 upTotal state 并接住 data.total。"""
    src = _read("pages/up-analytics/index.tsx")
    assert "const [upTotal, setUpTotal]" in src, "缺少 upTotal state"
    assert "setUpTotal(Number(data.total)" in src, "没从 data.total 读总数"


def test_up_page_state_exists():
    """要有 upPage state。

    原来 `page` 只是 handleSearchUp 的函数默认参数（恒为 1），
    没有 state，分页器翻不动。
    """
    src = _read("pages/up-analytics/index.tsx")
    assert "const [upPage, setUpPage]" in src, "缺少 upPage state"


def test_pagination_change_triggers_server_search():
    """翻页要重新请求（结果分页在服务端，不是前端切片）。"""
    src = _read("pages/up-analytics/index.tsx")
    src = _strip_line_comments(src)
    assert "handleSearchUp(p)" in src, "翻页应重新发起搜索"


def test_new_search_starts_from_page_one():
    """新关键词搜索要从第 1 页开始，否则会停在上次的页码。"""
    src = _read("pages/up-analytics/index.tsx")
    assert "handleSearchUp(1)" in src, "搜索按钮应从第 1 页开始"
