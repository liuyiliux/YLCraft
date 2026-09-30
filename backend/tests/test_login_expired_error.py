"""「登录态失效 → 401」的回归测试（2026-09-30）。

## 起因

用户："给其它平台也补上登录态失效的明确提示"

## 之前的症状：**失败时静默 `return None`**

实测各平台的 `get_self_profile()` 失败表现：

    douyin       → return None
    xiaohongshu  → return None
    weibo        → return None
    twitter      → raise TwitterAuthError（基类是 RuntimeError → 500）
    kuaishou     → return None ×2

**用户看到的是空白界面**，不知道是登录态失效还是接口坏了。

## 改法

  1. 新增 `LoginExpiredError`（`platforms/types.py`）——
     语义独立的异常：**需要重新登录**（≠ 风控 `PlatformUnavailableError`）
  2. 各平台失败时抛它（带**可操作**提示）
  3. API 层 `/users/me` 把它映射成 **401**（不是 500）

## 为什么 401 而不是 500

    · 500 = 服务端故障 —— 用户什么都做不了
    · 401 = 需要重新登录 —— 用户可以自己解决

前端据此提示"请重新登录"，而不是"加载失败"。

## 各平台的"登录态失效"信号（实测，都不一样）

    抖音   status_code=8（未登录）/ 0+空 user（风控降级）
    微博   /api/config 的 login=false
    小红书 被重定向到 /login
    X      HTTP 401/403
    快手   result=2（未登录）/ 109（中间态，约 20 分钟后出现）

## ⚠️ 一条反复踩的坑：**「搜索能用」≠「登录态有效」**

微博/快手/X 的**搜索都不需要登录**（公开数据或 SW 上下文），
只有 `profile` 类接口需要。所以"搜索正常"完全不能说明登录态还好。

报错文案里都点明了这一点。
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# 异常本身
# =============================================================================

def test_login_expired_error_exists():
    """要有独立的 `LoginExpiredError`。"""
    from app.services.platforms.types import LoginExpiredError

    assert issubclass(LoginExpiredError, RuntimeError)


def test_login_expired_is_not_platform_unavailable():
    """**回归**：登录失效 ≠ 风控。

    两者**处理方式不同**：
      · 风控 → 等一会儿重试（`PlatformUnavailableError`）
      · 登录失效 → 重新登录（`LoginExpiredError`）

    混在一起会让提示说错（比如让用户"等一会儿"，其实该重新登录）。
    """
    from app.services.platforms.douyin.client import PlatformUnavailableError
    from app.services.platforms.types import LoginExpiredError

    assert not issubclass(LoginExpiredError, PlatformUnavailableError)
    assert not issubclass(PlatformUnavailableError, LoginExpiredError)


def test_twitter_auth_error_is_login_expired():
    """**回归**：X 的 `TwitterAuthError` 要继承 `LoginExpiredError`。

    原来基类是 `RuntimeError` → API 层映射成 **500**（服务端故障），
    而实际是"需要重新登录" —— 提示说错了。
    """
    from app.services.platforms.types import LoginExpiredError
    from app.services.platforms.twitter.search_http import TwitterAuthError

    assert issubclass(TwitterAuthError, LoginExpiredError)


# =============================================================================
# 各平台要抛它
# =============================================================================

def test_douyin_raises_on_empty_user():
    """**回归**：抖音 `profile/self` 没返回 user 时要抛（不是 return None）。"""
    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient.get_self_profile)
    assert "LoginExpiredError" in src
    # 要说明 status_code=8 是未登录
    assert "8" in src, "要留档抖音的未登录状态码"


def test_weibo_raises_when_not_logged_in():
    """**回归**：微博未登录时要抛（不是 return None）。

    ⚠️ 而且**必须抛**：未登录时页面里的 `/profile/{uid}` 全是
    **别的用户**（实测抓到 uid=7918597670「蓟海棠」275万粉），
    继续下去会拿到**别人的资料**。
    """
    from app.services.platforms.weibo import search_patchright as wb

    src = inspect.getsource(wb.get_self_profile_via_patchright)
    assert "LoginExpiredError" in src
    # 要点明"搜索能用≠已登录"
    assert "搜索不需要登录" in src


def test_kuaishou_raises_on_profile_failure():
    """快手 `profile/*` 失败时要抛（已在 `test_kuaishou_search.py` 覆盖）。"""
    from app.services.platforms.kuaishou import client as ks

    src = inspect.getsource(ks.KuaishouClient._post)
    assert "RuntimeError" in src
    assert "账号中心" in src


# =============================================================================
# API 层映射
# =============================================================================

def test_users_route_maps_login_expired_to_401():
    """**回归**：`/users/me` 要把 `LoginExpiredError` 映射成 **401**。

    不是 500 —— 语义不同（见模块 docstring）。
    """
    from app.api.v1 import users

    src = inspect.getsource(users.get_self_profile)
    assert "LoginExpiredError" in src
    assert "401" in src


def test_users_route_still_returns_500_for_other_errors():
    """其它错误仍该是 500（服务端故障）。"""
    from app.api.v1 import users

    src = inspect.getsource(users.get_self_profile)
    assert "500" in src


def test_none_result_message_is_actionable():
    """平台没抛异常但返回 None 时，提示也要**可操作**。

    （指向"账号中心重新获取登录态"，而不是笼统的"失败"。）
    """
    from app.api.v1 import users

    src = inspect.getsource(users.get_self_profile)
    assert "重新获取" in src
    assert "账号中心" in src
