"""「我的数据」（抖音/小红书）契约测试。

## 背景（2026-09-27）

B站有 `/my-data` 页（看自己账号的数据）。抖音/小红书没有 ——
用户能搜到**别人**的资料，却看不到**自己**账号的。
接口其实都有，只是没接线：

    抖音   GET /aweme/v1/web/user/profile/self/
    小红书 GET /api/sns/web/v2/user/me

## 实测（2026-09-27）

    抖音   逸流AI | 粉丝122 关注3 获赞2735 作品22
    小红书 逸流AI | 粉丝195 关注2 获赞2930 作品73 | 小红书号95645311698 | IP辽宁

## 小红书的坑：一个接口拿不到统计

`v2/user/me` **只返回基础资料**：

    {user_id, nickname, desc, gender, imageb, red_id, guest, xsec_token}

**没有粉丝数/关注数/作品数**。所以 `get_self_profile` 要**两步走**：
先 `v2/user/me` 拿 user_id → 再用 `user/otherinfo` 补统计。

（对比：抖音的 `profile/self` 一次就给全，含 follower_count/aweme_count。）
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
# 后端
# =============================================================================

def test_douyin_has_self_profile():
    from app.services.platforms.douyin.client import DouyinClient

    assert hasattr(DouyinClient, "get_self_profile"), "抖音缺 get_self_profile"
    src = inspect.getsource(DouyinClient.get_self_profile)
    assert "PROFILE_SELF" in src, "应调 profile/self"


def test_douyin_self_uses_profile_self_endpoint():
    """抖音自查走 profile/self（不需要 sec_uid）。"""
    from app.services.platforms.douyin.apis import PROFILE_SELF

    assert PROFILE_SELF == "/aweme/v1/web/user/profile/self/"


def test_xhs_has_self_profile():
    from app.services.platforms.xiaohongshu.user import get_self_profile

    assert callable(get_self_profile)
    src = inspect.getsource(get_self_profile)
    # 两步：先 v2/user/me，再 otherinfo 补统计
    assert "USER_SELFINFO" in src, "应调 v2/user/me"
    assert "get_user_profile" in src, "应用 otherinfo 补统计"


def test_xhs_selfinfo_endpoint_is_v2_me():
    """小红书自查端点是 `/api/sns/web/v2/user/me`。

    ⚠️ 注意这个接口**不含粉丝数** —— 这是要两步走的原因。
    """
    from app.services.platforms.xiaohongshu.apis_user import USER_SELFINFO

    assert USER_SELFINFO == "/api/sns/web/v2/user/me"


def test_xhs_self_documents_two_step():
    """要记录"一个接口拿不到统计"这个坑，避免后人以为漏了字段。"""
    from app.services.platforms.xiaohongshu import apis_user

    src = inspect.getsource(apis_user)
    assert "不含粉丝数" in src or "没有粉丝数" in src, "应说明 v2/user/me 缺统计"
    assert "两步" in src or "补统计" in src, "应说明要补一次查询"


def test_users_me_route_mounted():
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/v1/users/me" in paths, "/users/me 未挂载"


def test_users_me_route_does_not_require_id():
    """`/users/me` 不需要 user_id / sec_uid（用连接里的登录态）。"""
    from app.api.v1 import users as users_api

    sig = inspect.signature(users_api.get_self_profile)
    assert "platform" in sig.parameters
    assert "user_id" not in sig.parameters, "自查不该要求 user_id"
    assert "sec_uid" not in sig.parameters, "自查不该要求 sec_uid"


# =============================================================================
# 前端
# =============================================================================

def test_page_exists_and_registered():
    src = _read("pages/my-platform-data/index.tsx")
    assert "我的数据" in src
    app = _read("App.tsx")
    assert "my-platform-data" in app, "路由未注册"
    assert "MyPlatformDataPage" in app, "未导入组件"


def test_menu_entry_registered():
    src = _read("components/layout/AppLayout.tsx")
    assert "/my-platform-data" in src, "菜单未加入"


def test_api_function_exists():
    src = _read("api/index.ts")
    assert "getMyPlatformProfile" in src
    assert "/users/me" in src


def test_platform_conn_alias_accepts_xhs():
    """**回归**：小红书连接在连接表里叫 `xhs`（与番茄页同一类坑）。"""
    src = _read("pages/my-platform-data/index.tsx")
    i = src.find("const PLATFORMS")
    seg = src[i:i + 400]
    assert "'xhs'" in seg, "要接受 xhs 这个连接标识"


def test_reads_connections_not_data():
    """**回归**：从 `res.connections` 读（不是 res.data）。"""
    src = _read("pages/my-platform-data/index.tsx")
    i = src.find("listPlatformConnections()")
    assert i != -1
    seg = _strip_line_comments(src[i:i + 800])
    assert "connections" in seg
    assert "res?.data" not in seg


def test_switch_platform_clears_results():
    """切平台要清空上次结果，避免"小红书标签 + 抖音数据"。"""
    src = _read("pages/my-platform-data/index.tsx")
    i = src.find("}, [platform])")
    assert i != -1
    seg = _strip_line_comments(src[max(0, i - 900):i])
    assert "setProfile(null)" in seg
    assert "setVideos([])" in seg


def test_videos_use_sec_uid():
    """抖音拉自己作品要用 sec_uid（数字 uid 会得到空列表/空页面）。"""
    src = _read("pages/my-platform-data/index.tsx")
    assert "secUid: me.sec_uid" in src, "应传 sec_uid"


def test_images_go_through_proxy():
    src = _read("pages/my-platform-data/index.tsx")
    assert "/api/v1/proxy/image" in src


def test_theme_destructuring_correct():
    """**回归**：useTheme() 返回 { theme }，不是 { THEME }。"""
    src = _read("pages/my-platform-data/index.tsx")
    assert "const { theme: THEME }" in src
