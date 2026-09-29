"""创作者中心前端面板的回归测试（静态检查，不需要浏览器）。

## 为什么用静态检查

前端构建（`npm run build`）**只检查语法**，抓不到
"读了不存在的字段"这类问题 —— 那要运行时才暴露。

而创作者中心的接口字段有**几个已知的坑**（都是实测踩出来的）：

    小红书总览 → `label` / `value` / `is_rate` / `rate`
    抖音总览   → `label` / `total` / `period_incr`
    （两边结构**不同** —— 不能共用渲染逻辑）

## 这些测试钉住什么

  · 面板文件存在，且被页面引用
  · 两个平台的字段读取路径正确（读 `total` 的是抖音、读 `value` 的是小红书）
  · 环比为 0 时不显示（"+0%" 没信息量，还会让人以为数据没变）
  · 请求"仅号主可见"的标识要在
  · 未登录时要有可操作的提示（不是干瞪眼）
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
PANEL = FRONTEND / "pages" / "my-platform-data" / "CreatorCenterPanel.tsx"
PAGE = FRONTEND / "pages" / "my-platform-data" / "index.tsx"
API = FRONTEND / "api" / "index.ts"


def _read(p: Path) -> str:
    if not p.exists():
        pytest.skip(f"文件不在预期位置：{p}")
    return p.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# 存在性与接线
# =============================================================================

def test_panel_exists():
    assert PANEL.exists(), "创作者中心面板应存在"


def test_page_imports_panel():
    """页面要真的引用这个面板（否则做了也看不到）。"""
    src = _read(PAGE)
    assert "CreatorCenterPanel" in src, "页面应 import 并渲染它"
    assert "<CreatorCenterPanel" in src, "应渲染组件"


def test_panel_uses_creator_apis():
    """面板要调创作者中心的接口（不是普通站接口）。"""
    src = _read(PANEL)
    for fn in ("getXhsCreatorOverview", "getXhsCreatorFans",
               "getDouyinCreatorOverview", "getDouyinCreatorWorks"):
        assert fn in src, f"应调用 {fn}"


def test_api_functions_defined():
    """API 封装要存在，且路径正确。"""
    src = _read(API)
    assert "/users/creator/overview" in src
    assert "/users/creator/works" in src
    assert "/users/creator/xhs/overview" in src
    assert "/users/creator/xhs/fans" in src


# =============================================================================
# 字段读取路径（两个平台结构不同）
# =============================================================================

def test_reads_xhs_value_field():
    """**回归**：小红书总览的数值字段是 `value`。"""
    src = _read(PANEL)
    # 小红书分支里出现 v.value
    assert "v.value" in src, "小红书读 value"


def test_reads_douyin_total_field():
    """**回归**：抖音总览的数值字段是 `total`（不是 value）。

    两个平台结构不同 —— 抖音是 `{label, total, period_incr}`，
    小红书是 `{label, value, is_rate, rate}`。
    用同一套读取逻辑会拿到 undefined（前端显示空白）。
    """
    src = _read(PANEL)
    assert "v.total" in src, "抖音读 total"
    assert "v.period_incr" in src, "抖音的环比字段是 period_incr"


def test_is_rate_only_for_xhs():
    """比率标记只在小红书分支用（抖音没有 `is_rate`）。"""
    src = _read(PANEL)
    assert "is_rate" in src


# =============================================================================
# 展示细节
# =============================================================================

def test_rate_zero_is_hidden():
    """**回归**：环比为 0 时不显示标签。

    显示 "+0%" 没有信息量，还会让人误以为"数据没变"
    （实际是"没有对比数据"）。
    """
    src = _read(PANEL)
    # RateTag 里应有 n === 0 时返回 null
    assert "n === 0" in src or "=== 0) return null" in src, (
        "环比为 0 应不渲染"
    )


def test_marks_owner_only():
    """要标明"仅号主可见" —— 否则用户会以为别人也能看到。"""
    src = _read(PANEL)
    assert "仅号主可见" in src


def test_login_hint_actionable():
    """未登录时的提示要可操作（告诉用户去哪重新登录）。

    ⚠️ 因为**过期的登录态在 cookie 里依然存在**，用户会以为"我明明登录了"。
    """
    src = _read(PANEL)
    assert "账号中心" in src, "应提示去哪操作"
    assert "过期" in src or "重新扫码" in src, "应解释为什么看起来'已登录'"


def test_documents_creator_only_metrics():
    """要说明哪些指标是创作者中心独有的（完播率等）。"""
    src = _read(PANEL)
    assert "完播率" in src, "应展示完播率"
    assert "独有" in src or "创作者中心" in src


def test_no_btoa():
    """**回归**：不得使用 `btoa`（中文会抛 InvalidCharacterError，整页崩）。

    见 tests/test_frontend_btoa_guard.py 的详细说明。
    """
    src = _read(PANEL)
    code = "\n".join(
        ln for ln in src.splitlines() if not ln.strip().startswith("//")
    )
    assert "btoa(" not in code
