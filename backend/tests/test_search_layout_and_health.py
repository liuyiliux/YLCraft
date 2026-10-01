"""搜索区布局 + 统一体检的回归测试（2026-10-01）。

## 两个用户实测反馈

### 1. "为啥几个平台搜索输入框长度不一样"

根因：搜索框宽度按 `showSearchConnectionPicker` **动态计算**，
而这个变量取决于**该平台有没有建过连接**：

  · 有连接（小红书/抖音）→ 搜索框窄（md=14）+ 右侧塞连接下拉
    → 「去官网搜」被挤到**第二行**
  · 没连接（YouTube/Telegram 免登录）→ 搜索框宽（md=21）
    → 「去官网搜」留在**第一行**

**布局宽度不该取决于业务状态**（有没有连接），只该取决于屏幕宽度 ——
否则用户切平台时看到按钮位置乱跳、搜索框忽宽忽窄，会以为界面坏了。

### 2. "为什么只有 B站有体检按钮"

查证发现：**抖音 / 小红书早就有 `/login-health` 接口**
（`platforms/douyin/health.py`、`platforms/xiaohongshu/routes.py`），
**是前端只接了 B站那个** —— 又是"后端实现了但前端没接"。

现在统一成 `/api/v1/platforms/{platform}/health`（最小搜索探针），
**所有平台都有体检按钮**。
"""

from __future__ import annotations

from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _crawler() -> str:
    p = FRONTEND / "pages" / "crawler" / "index.tsx"
    if not p.exists():
        pytest.skip("搜索页不在预期位置")
    return p.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# 布局：宽度不能依赖业务状态
# =============================================================================

def test_search_input_width_not_business_dependent():
    """**回归（关键）**：搜索框宽度**不得**再按 `showSearchConnectionPicker` 计算。

    这是"几个平台搜索框长度不一样"的直接原因 ——
    宽度取决于"有没有建连接"这个业务状态，导致切平台时跳动。
    """
    src = _crawler()
    # 找到搜索框那一行附近的 Col 定义
    i = src.find("<Input.Search")
    assert i != -1
    # 往前找它所属的 Col
    seg = src[max(0, i - 900):i]
    bad = "showSearchConnectionPicker ? 12" in seg or "showSearchConnectionPicker ? 14" in seg
    assert not bad, (
        "搜索框宽度仍在按 showSearchConnectionPicker 动态计算 —— "
        "这会让宽度取决于'有没有连接'（业务状态），切平台时跳动。"
        "应改为固定 flex（如 flex='1 1 auto'）"
    )


def test_search_row_uses_flex_layout():
    """搜索行要用 **flex 定宽**（平台选择固定宽、搜索框自动撑满）。"""
    src = _crawler()
    i = src.find("<Input.Search")
    seg = src[max(0, i - 1200):i]
    assert 'flex="1 1 auto"' in seg or 'flex="0 0' in seg, (
        "搜索行应使用 flex 布局（平台选择定宽 + 搜索框自动撑满）"
    )


def test_secondary_row_is_separate():
    """连接选择/体检要在**独立的次要行**（不再挤进主搜索行）。"""
    src = _crawler()
    assert "renderSecondaryRow" in src, "要有独立的次要行渲染函数"


# =============================================================================
# 体检：所有平台一致
# =============================================================================

def test_health_button_rendered_for_all_platforms():
    """**回归（关键）**：体检按钮不得只在 B站分支里渲染。

    用户实测反馈："为什么只有 B站有体检按钮"。
    而抖音/小红书**早就有**后端接口 —— 是前端没接。
    """
    src = _crawler()
    # 找 renderSecondaryRow 的**完整函数体**（到下一个顶层 const/函数为止）
    i = src.find("const renderSecondaryRow = ")
    assert i != -1, "要有次要行渲染函数"
    # 取到下一个同级定义（`\n  const ` 或 `\n  // =====`）
    rest = src[i:]
    end = len(rest)
    for marker in ("\n  // ===== 搜索", "\n  const handleSearch"):
        j = rest.find(marker)
        if j != -1:
            end = min(end, j)
    body = rest[:end]
    assert "体检" in body, "次要行里要有体检按钮"

    # ⚠️ 不能有 `platform === 'bili' &&` 把**体检按钮本身**包起来。
    # 注意：B站**额外调用**详细体检是允许的（runBiliHealthCheck），
    # 要检查的是"按钮是否被条件渲染包住"。
    j = body.find("体检\n")
    if j == -1:
        j = body.find("体检<")
    if j == -1:
        j = body.find("体检")
    assert j != -1
    window = body[max(0, j - 800):j]
    assert "platform === 'bili' && (" not in window, (
        "体检按钮被 B站条件包住了 —— 所有平台都该有"
    )


def test_frontend_calls_unified_health_api():
    """前端要调**统一**体检接口（而不是各平台各调一个）。"""
    src = _crawler()
    assert "getPlatformHealth" in src, "要调 /platforms/{platform}/health"
    # B站的详细体检要保留（它更细：6 个分项）
    assert "getBiliLoginHealth" in src, "B站的详细体检要保留"


def test_health_result_cleared_on_platform_switch():
    """切平台要清空体检结果（否则会张冠李戴）。"""
    src = _crawler()
    i = src.find("setHealth(null)")
    assert i != -1, "切平台要 setHealth(null)"
    # 要在依赖 platform 的 useEffect 里
    seg = src[max(0, i - 200):i + 200]
    assert "platform" in seg


# =============================================================================
# 后端：统一体检接口
# =============================================================================

def test_unified_health_route_exists():
    """后端要有统一的体检路由。"""
    from app.services.platforms import health_routes

    assert hasattr(health_routes, "router")
    src = __import__("inspect").getsource(health_routes)
    assert "/{platform}/health" in src


def test_health_covers_no_login_platforms():
    """**免登录平台也要能体检**。

    YouTube/Telegram 没有"登录态"，但"搜索是否可用"依然有意义
    （VPN 断了就搜不到）—— 不能因为"免登录"就跳过体检。
    """
    import inspect

    from app.services.platforms import health_routes

    src = inspect.getsource(health_routes.platform_health)
    assert "no_login" in src
    # 免登录平台要标记为"登录态正常"（而不是"没有凭证=失败"）
    assert "免登录" in src


def test_health_uses_exception_types_not_strings():
    """**回归**：体检的错误分类要用**异常类型**，不能字符串匹配。

    （与 `test_error_taxonomy.py` 同一个原则 —— 改文案不该让分类失效）
    """
    import inspect

    from app.services.platforms import health_routes

    src = inspect.getsource(health_routes.platform_health)
    for name in ("LoginExpiredError", "RiskControlError", "NetworkError"):
        assert name in src, f"体检要按类型识别 {name}"
    # 不允许 `"461" in msg` 这类匹配
    assert 'in msg for k in' not in src


def test_health_reports_unimplemented_platform_clearly():
    """未实现平台要明确说"不是搜不到"（铁律）。"""
    import inspect

    from app.services.platforms import health_routes

    src = inspect.getsource(health_routes.platform_health)
    assert "尚未实现" in src
    assert "不是「搜不到」" in src or "不是搜不到" in src
