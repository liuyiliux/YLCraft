"""「我的数据」全平台打通的回归测试。

## 用户要求

    "要"（撤掉微博/X 的作品列表静默跳过 —— 现在两边都实现了）

## 背景

之前微博 `WeiboClient` **没有 `get_user_videos`**，后端抛 500
（`'WeiboClient' object has no attribute ...`），
所以前端对 `weibo` / `twitter` **直接跳过**作品列表。

现在两边都打通了：

    微博  containerid=107603{uid} → cards[].mblog
    X     UserTweets（handle 自动转数字 id）

所以撤掉跳过逻辑，正常请求。

## 实测（四个平台端到端）

    抖音      资料 ✅ 逸流AI      作品 10 条
    小红书    资料 ✅ 逸流AI      作品 10 条
    微博      资料 ✅ 想见雪-     作品 10 条
    X         资料 ✅ 6          作品  2 条

## 各平台 `user_id` 的含义（不一样，容易搞错）

    抖音     sec_uid（**必须**，用 user_id 会失败）
    小红书   数字 id
    微博     数字 uid
    X        数字 userId **或 handle**（后端自动转）
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


# =============================================================================
# 前端：撤掉跳过
# =============================================================================

def test_frontend_no_longer_skips_weibo_twitter():
    """**回归**：前端不该再对微博/X 跳过作品列表。

    跳过是**临时措施**（当时后端没实现）。现在实现了，跳过会让
    用户以为"这两个平台没有作品列表"。
    """
    p = FRONTEND / "pages" / "my-platform-data" / "index.tsx"
    if not p.exists():
        pytest.skip("页面不在预期位置")
    src = p.read_text(encoding="utf-8", errors="ignore")
    assert "NO_VIDEO_PLATFORMS" not in src, (
        "不该再有 NO_VIDEO_PLATFORMS 跳过名单（微博/X 已实现）"
    )


def test_frontend_still_tolerates_unsupported():
    """但仍要容忍"后端确实不支持"（如番茄）—— 静默而非报错。"""
    p = FRONTEND / "pages" / "my-platform-data" / "index.tsx"
    if not p.exists():
        pytest.skip("页面不在预期位置")
    src = p.read_text(encoding="utf-8", errors="ignore")
    assert "has no attribute" in src or "不支持" in src, (
        "应保留对'能力缺失'的容忍（不弹错误）"
    )


def test_frontend_has_weibo_option():
    """**回归**：平台下拉要有微博（之前漏了）。"""
    p = FRONTEND / "pages" / "my-platform-data" / "index.tsx"
    if not p.exists():
        pytest.skip("页面不在预期位置")
    src = p.read_text(encoding="utf-8", errors="ignore")
    assert "value: 'weibo'" in src, "应有微博选项"


# =============================================================================
# 后端：各平台都有 get_user_videos
# =============================================================================

def test_all_main_platforms_have_get_user_videos():
    """**回归**：四个主力平台都要有 `get_user_videos`。"""
    from app.services.platforms import create_client

    for p in ("douyin", "xiaohongshu", "weibo", "twitter"):
        c = create_client(p, mode="api", cookie="a1=x")
        assert c is not None, f"{p} 客户端未注册"
        assert hasattr(c, "get_user_videos"), f"{p} 缺 get_user_videos"


def test_route_documents_platform_differences():
    """路由要说明各平台 `user_id` 含义不同（容易搞错）。"""
    from app.api.v1 import users as users_api

    src = inspect.getsource(users_api.get_user_videos)
    assert "sec_uid" in src, "抖音用 sec_uid"
    assert "微博" in src or "weibo" in src
    assert "X" in src or "twitter" in src


def test_route_no_longer_claims_only_two_platforms():
    """路由的 summary 不该再说"只支持抖音/小红书"。"""
    from app.api.v1 import users as users_api

    src = inspect.getsource(users_api.get_user_videos)
    # 之前的 summary 是 "获取用户作品列表（抖音/小红书）"
    assert "抖音/小红书）" not in src, "summary 已过时"
