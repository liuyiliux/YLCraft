"""博主中心前端页面的契约测试。

## 背景（2026-09-27）

用户要求做抖音/小红书的 UP主搜索 + 个人中心。后端接口已就绪
（`/api/v1/users/*`），本轮补前端面板 `/platform-users`。

## 用真实浏览器实测过（bsk + 用户已登录 Chrome）

    抖音：搜索「李子柒」→ 19 个用户，首个 5657.0万粉
          详情面板 → 4830.7万粉 / 1 关注 / 2.55亿获赞 / 774 作品
          作品 Tab → 20 条（1168.9万赞 / 703.0万赞 / 1251.2万赞…）
    小红书：搜索「美食」→ 20 个用户（吕小厨爱美食 140.9万粉、
            妞妞儿美食 195.3万粉、铭哥说美食 226.0万粉…）
            并正确显示「小红书号」

## 实测发现并修掉的两个前端 bug

### 1. 小红书连接识别不到（平台标识不一致）

`/api/v1/platforms` 返回小红书连接时用的是 **`xhs`**，
而 `/users/*` 接口的 platform 参数是 **`xiaohongshu`**。
页面只按 `xiaohongshu` 筛 → 显示"未找到小红书连接"，
**但连接其实是好的**（接口实测能搜到用户）。

修法：给每个平台声明 `connKeys`，两种标识都接受。

### 2. 切换平台没清空上次结果

切到小红书后表格里还是抖音搜出来的"李子柒"——
标签是小红书、数据是抖音，属于错位展示。
修法：切换平台时清空 users/selected/profile/videos/keyword。
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
    """去掉 // 行注释（注释里会提到曾经写错的写法，直接断言会被误伤）。"""
    return "\n".join(
        line for line in src.splitlines() if not line.strip().startswith("//")
    )


# =============================================================================
# 页面与路由
# =============================================================================

def test_page_exists():
    src = _read("pages/platform-users/index.tsx")
    assert "博主中心" in src
    assert "PLATFORMS" in src


def test_route_registered():
    src = _read("App.tsx")
    assert "platform-users" in src, "路由未注册"
    assert "PlatformUsersPage" in src, "未导入页面组件"


def test_menu_entry_registered():
    src = _read("components/layout/AppLayout.tsx")
    assert "/platform-users" in src, "菜单未加入"


def test_api_functions_exist():
    src = _read("api/index.ts")
    for fn in ("searchPlatformUsers", "getPlatformUserProfile", "getPlatformUserVideos"):
        assert fn in src, f"缺少 {fn}"


# =============================================================================
# 两个实测修掉的 bug（回归）
# =============================================================================

def test_platform_conn_keys_accept_xhs_alias():
    """**回归**：小红书连接在连接表里叫 `xhs`，用户接口参数叫 `xiaohongshu`。

    只按 `xiaohongshu` 筛会显示"未找到小红书连接"，但连接其实是好的。
    """
    src = _read("pages/platform-users/index.tsx")
    assert "connKeys" in src, "应声明连接标识别名"
    i = src.find("const PLATFORMS")
    seg = src[i:i + 500]
    assert "'xhs'" in seg, "小红书必须接受 xhs 这个连接标识"
    assert "'xiaohongshu'" in seg, "也要支持完整名"


def test_platform_switch_clears_previous_results():
    """**回归**：切换平台要清空上次结果。

    否则会"用小红书标签展示抖音用户"，属于错位展示。
    """
    src = _read("pages/platform-users/index.tsx")
    # 找到监听 platform 的 effect
    i = src.find("}, [platform])")
    assert i != -1, "应有依赖 platform 的 effect"
    seg = _strip_line_comments(src[max(0, i - 1200):i])
    for setter in ("setUsers([])", "setSelected(null)", "setVideos([])"):
        assert setter in seg, f"切平台时应调用 {setter}"


def test_reads_connections_not_data():
    """**回归**：连接要从 `res.connections` 读（不是 res.data）。

    番茄灵感页曾因读 res.data 导致"未找到连接"。
    """
    src = _read("pages/platform-users/index.tsx")
    i = src.find("listPlatformConnections()")
    assert i != -1
    seg = _strip_line_comments(src[i:i + 900])
    assert "connections" in seg
    assert "res?.data" not in seg


def test_filters_active_connections_only():
    src = _read("pages/platform-users/index.tsx")
    assert "status === 'active'" in src, "应只取 active 连接"


# =============================================================================
# 抖音/小红书差异（关键正确性）
# =============================================================================

def test_douyin_uses_sec_uid():
    """**回归**：抖音必须用 sec_uid。

    实测数字 uid 打开主页是空页面；sec_uid 才正常。
    """
    src = _read("pages/platform-users/index.tsx")
    assert "sec_uid" in src, "应传 sec_uid"
    # 加载详情时优先用搜索结果里的 sec_uid
    assert "user.sec_uid" in src


def test_theme_destructuring_is_correct():
    """**回归**：`useTheme()` 返回 `{ theme, themeId }`。

    解构成 `{ THEME }` 会得到 undefined（实测编译报
    `Property 'THEME' does not exist`）。
    """
    src = _read("pages/platform-users/index.tsx")
    assert "const { theme: THEME }" in src, "应解构 theme 并重命名为 THEME"


def test_images_go_through_proxy():
    """图片要走 /api/v1/proxy/image（图床有防盗链）。"""
    src = _read("pages/platform-users/index.tsx")
    assert "/api/v1/proxy/image" in src
