"""移动端适配的回归测试（2026-10-02）。

## 用户反馈的问题（手机截图）

1. **「去官网搜」盖住搜索框** —— `wrap={false}` + 固定 150px 平台下拉
   + `flex="none"` 按钮挤在一行，手机（~390px）上搜索框被压到几乎不可见
2. **「停用」压在账号下拉上** —— `minWidth: 240` 的下拉 + 按钮挤在一行
3. **搜索类型 tab 溢出** —— 装不下时用户看不出右边还有内容
4. **筛选区铺满半屏** —— 排序/时长/日期铺开占 300+ px

## 修复

新建 `hooks/useResponsive.ts`（`useIsMobile` / `useViewportWidth`），
按平台能力之外**唯一**的屏幕宽度决定换行。
"""

from __future__ import annotations

from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
CRAWLER = FRONTEND / "pages" / "crawler" / "index.tsx"
HOOK = FRONTEND / "hooks" / "useResponsive.ts"


def _crawler() -> str:
    if not CRAWLER.exists():
        pytest.skip("crawler page not found")
    return CRAWLER.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# 响应式 hook 本身
# =============================================================================

def test_responsive_hook_exists():
    """要有响应式 hook（项目原来**完全没有**响应式处理）。"""
    if not HOOK.exists():
        pytest.skip("useResponsive.ts not found")
    src = HOOK.read_text(encoding="utf-8", errors="ignore")
    assert "useIsMobile" in src
    assert "useViewportWidth" in src
    # 要监听 resize（不监听的话旋转屏幕就不更新）
    assert "resize" in src


def test_responsive_hook_has_mobile_breakpoint():
    """手机断点应该是 768px（与 antd 的 xs/sm 上界一致）。"""
    if not HOOK.exists():
        pytest.skip("useResponsive.ts not found")
    src = HOOK.read_text(encoding="utf-8", errors="ignore")
    assert "768" in src, "手机断点应为 768px"


# =============================================================================
# 问题 1：搜索框被按钮遮挡
# =============================================================================

def test_search_row_wraps_on_mobile():
    """**关键**：搜索行在手机端要**允许换行**（`wrap` 不能是 `false`）。

    ## 事故经过

    原来是 `wrap={false}` + 固定 `0 0 150px` 平台下拉 + `flex="none"` 按钮，
    三者挤在一行。手机上：
        150(平台) + 12 + 搜索框 + 12 + ~130(按钮) > 390
    → 搜索框被压到几乎不可见，且「去官网搜」**直接盖在上面**
    （用户截图实测）。
    """
    src = _crawler()
    assert "useIsMobile" in src, "crawler 页没用响应式 hook"
    # 搜索行的 wrap 必须按 isMobile 切换
    assert "wrap={isMobile ? undefined : false}" in src, (
        "搜索行仍固定 wrap={false} —— 手机上会被挤爆"
    )


def test_platform_select_full_width_on_mobile():
    """手机端平台下拉要**独占一行**（否则搜索框没地方放）。"""
    src = _crawler()
    assert "flex={isMobile ? '0 0 100%' : '0 0 150px'}" in src, (
        "手机端平台下拉应占满整行"
    )


def test_search_button_full_width_on_mobile():
    """「去官网搜」在手机端独占一行（否则压在搜索框上）。"""
    src = _crawler()
    assert "flex={isMobile ? '0 0 100%' : 'none'}" in src, (
        "手机端「去官网搜」应占满整行（否则与搜索框重叠）"
    )


# =============================================================================
# 问题 2：停用按钮压住账号下拉
# =============================================================================

def test_secondary_row_wraps_on_mobile():
    """**关键**：账号行（次要行）在手机端也要换行。"""
    src = _crawler()
    assert "wrap={isMobile ? undefined : false}" in src, (
        "次要行仍固定 wrap={false} —— 停用按钮会压在账号下拉上"
    )


def test_account_select_no_fixed_minwidth_on_mobile():
    """手机端账号下拉**不能**固定 `minWidth: 240`（会挤出按钮）。"""
    src = _crawler()
    assert "style={isMobile ? { flex: 1, minWidth: 0 } : { minWidth: 240 }}" in src, (
        "手机端账号下拉不应固定 minWidth: 240"
    )


# =============================================================================
# 问题 3：搜索类型 tab 溢出
# =============================================================================

def test_search_type_tabs_have_overflow_hint():
    """tab 溢出时要**看得出来还能滑**（右侧渐隐 + 惯性滚动）。"""
    src = _crawler()
    assert "WebkitOverflowScrolling" in src, "iOS 需要惯性滚动"
    assert "maskImage" in src or "WebkitMaskImage" in src, (
        "溢出时应有右侧渐隐提示（否则用户以为到头了）"
    )


def test_search_type_tabs_do_not_shrink():
    """tab 按钮不能被 flex 压缩（压缩会竖排）。

    ⚠️ 定位：渲染处是 `<button ... onClick={() => setSearchType(st.value)}`
    （`useState` 那处不是渲染）。判据用**行窗口**而不是 substring，
    避免注释里的文字影响匹配。
    """
    lines = _crawler().splitlines()
    idx = None
    for i, ln in enumerate(lines):
        if "setSearchType(st.value)" in ln and "useState" not in ln:
            idx = i
            break
    assert idx is not None, "找不到搜索类型 tab 的 onClick"
    window = "\n".join(lines[max(0, idx - 20):idx + 20])
    assert "flexShrink: 0" in window, (
        "tab 按钮需要 flexShrink: 0（否则被 flex 压扁、文字竖排）"
    )


def test_search_type_tabs_smaller_on_mobile():
    """手机端 tab 要更紧凑（多塞得下一个）。"""
    src = _crawler()
    assert "isMobile ? '10px 11px' : '10px 16px'" in src, (
        "手机端 tab padding 应更小"
    )


# =============================================================================
# 问题 4：筛选区铺满半屏
# =============================================================================

def test_filter_area_collapses_on_mobile():
    """**关键**：筛选/排序在手机端**默认折叠**（实测铺开占 300+ px 半屏）。"""
    src = _crawler()
    assert "mobileFilterOpen" in src, "没有手机端折叠状态"
    # 默认折叠
    assert "useState(false)" in src, "筛选区应默认折叠（false = 折叠）"


def test_filter_only_rendered_when_expanded_on_mobile():
    """手机端只有展开时才渲染排序/筛选（桌面端始终展开）。"""
    src = _crawler()
    assert "(!isMobile || mobileFilterOpen) && currentTypeConfig.sortOptions" in src, (
        "排序区应受手机端折叠控制"
    )
    assert "(!isMobile || mobileFilterOpen) && currentTypeConfig.filters" in src, (
        "筛选区应受手机端折叠控制"
    )


def test_collapsed_filter_entry_shows_active_badge():
    """折叠后若有"已筛选"要在入口上打点（用户看不到筛选生效了）。"""
    src = _crawler()
    assert "hasActive" in src, "折叠入口应提示'有筛选生效'"
    assert "Badge" in src, "有筛选时应显示角标"


def test_search_panel_tighter_on_mobile():
    """搜索卡片在手机端压缩留白（否则要滚半屏才看到热门词）。"""
    src = _crawler()
    assert "isMobile ? '10px 12px 8px' : '16px 20px 12px'" in src, (
        "手机端搜索区 padding 应更小"
    )
