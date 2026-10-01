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


# =============================================================================
# ⚠️ 搜索路径也要映射成 401（2026-10-01 补）
# =============================================================================

def test_search_route_maps_login_expired_to_401():
    """**回归**：`/crawler/search-enhanced` 也要把登录失效映射成 **401**。

    ## 为什么补这条

    这个异常最早只映射在 `/users/me`（账号中心）那条路径上，
    **搜索路径漏了** —— 又是"守卫只加在一个入口"的老毛病。

    实测（快手 cookie 过期后搜索）：

        日志：[kuaishou] 未能获取 /rest/v/search/feed 的接口签名 ...
        响应：HTTP **500** "搜索失败: ..."

    **500 是错的** —— 服务端没坏，是登录态过期了。
    用户看到"搜索失败"只会以为是 bug，不会想到该重新登录。

    所以搜索路径也要走同一个 401 分支。
    """
    from app.api.v1 import crawler

    src = inspect.getsource(crawler.search_enhanced)
    assert "LoginExpiredError" in src, "搜索路径要识别登录失效"
    assert "401" in src, "要映射成 401（不是 500）"
    # 提示要可操作
    assert "账号中心" in src


def test_search_route_checks_login_expired_before_generic_rejection():
    """**回归**：401 分支要放在 429（风控）分支**之前**。

    顺序错了的话，登录失效可能被 429 抢走 ——
    提示会变成"稍后重试/去登录"，而正确答案是**必须**重新登录。
    """
    from app.api.v1 import crawler

    src = inspect.getsource(crawler.search_enhanced)
    i_login = src.find("LoginExpiredError")
    i_antispam = src.find('"antispam"')
    assert i_login != -1 and i_antispam != -1
    assert i_login < i_antispam, "401 判断必须在 429（风控）判断之前"


def test_both_search_routes_map_login_expired_to_401():
    """**回归**：`/search` **和** `/search-enhanced` 都要映射 401。

    又是"守卫只加在一个入口"的毛病：
    `search_enhanced` 加了 401 分支，但 `/crawler/search`
    （画布 platform_search 节点 + 博主中心"作品搜索"走它）
    **漏了** —— 快手登录过期时那个端点仍是
    `HTTP 500 "搜索失败: ..."`。
    """
    from app.api.v1 import crawler

    for fn in (crawler.search_enhanced, crawler.search_materials):
        src = inspect.getsource(fn)
        assert "LoginExpiredError" in src, f"{fn.__name__} 缺 401（登录失效）分支"
        assert "401" in src, f"{fn.__name__} 要映射成 401"
        assert "账号中心" in src, f"{fn.__name__} 的提示要可操作"


def test_crawler_service_does_not_swallow_login_expired():
    """**回归**：service 层不能把 `LoginExpiredError` 吞成 `return []`。

    `_search_via_platforms` 的兜底 `except Exception` 会 `return []`
    （→ "找到 0 条结果"），而快手的报错文本
    （`未能获取 /rest/v/search/feed 的接口签名`）
    **不含** 461/403/风控 那组关键词，所以原来一定会被吞掉。

    修法：用**类型判断**（`except LoginExpiredError: raise`），
    不靠猜关键词。`search_videos` 里也要拦住，免得降级到 yt-dlp
    再空一次、把"该重新登录"伪装成"没搜到"。
    """
    from app.services.crawler import service as svc

    for fn in (svc.CrawlerService._search_via_platforms, svc.CrawlerService.search_videos):
        src = inspect.getsource(fn)
        assert "LoginExpiredError" in src, (
            f"{fn.__name__} 没拦住 LoginExpiredError（会被吞成空/降级 yt-dlp）"
        )


def test_kuaishou_signature_failure_is_login_expired():
    """**回归（关键）**：快手"拿不到签名"要抛 `LoginExpiredError`，不能抛裸 `RuntimeError`。

    ## 实测症状（2026-10-01）

    cookie 过期后搜索：

        [kuaishou] 未能获取 /rest/v/search/feed 的接口签名
        → HTTP **500** "搜索失败: ..."

    **两处都错**：

      ① 异常类型是 `RuntimeError` → API 层的 `except LoginExpiredError`
         抓不到 → 落到 `except Exception` → 500
      ② 语义该是 **401**（登录过期，用户能自己解决），不是 500

    而该函数自己的文档就写着"可能原因 1：浏览器会话**没有登录态**" ——
    首选原因明明就是登录失效，异常类型却表达不出来。

    这条测试锁住：**一律不能退回裸 `RuntimeError`**。
    """
    from app.services.platforms.kuaishou import client as ks

    src = inspect.getsource(ks.KuaishouClient._post)
    assert "LoginExpiredError" in src, "拿不到签名要抛 LoginExpiredError"
    assert "未能获取" in src, "要保留原始症状描述"
    assert "账号中心" in src, "提示要可操作"


def test_xhs_login_expired_code_is_login_expired_error():
    """**回归（关键）**：小红书 code=-100（登录已过期）要抛 `LoginExpiredError`。

    ## 实测症状（2026-10-01 全平台矩阵）

    小红书连接过期后搜索：

        HTTP 200 {"success": false, "code": -100, "msg": "登录已过期"}

    原来 `search_api.py` 抛**普通 RuntimeError** —— 错误文本不含
    service 层那组关键词（461/403/风控…），被**吞成 return []**：

        HTTP 200 {"results": [], "message": "找到 0 条结果"}

    **用户完全不知道是登录过期了**（假阴性）——
    正确行为是 401 + "请到账号中心重新登录"。
    """
    from app.services.platforms.xiaohongshu import search_api, user

    for mod, marker in ((search_api, "code == -100"), (user, "code == -100")):
        src = inspect.getsource(mod)
        assert marker in src, f"{mod.__name__} 要识别 code=-100"
        assert "LoginExpiredError" in src, (
            f"{mod.__name__} 的 -100 必须抛 LoginExpiredError（否则被吞成空）"
        )


def test_douyin_detail_empty_body_is_not_notfound():
    """**回归（关键）**：抖音详情"空 body"不能伪装成 404"笔记不存在"。

    ## 实测症状（2026-10-01 全平台矩阵）

    搜索正常（3 条），但点详情：

        GET www-hj.douyin.com/aweme/v1/web/aweme/detail/ → HTTP 200
        body 长度 0 → resp.json() 抛
        Expecting value: line 1 column 1 (char 0)
        → API 层 404 "笔记不存在或获取失败"

    **404 是错的** —— 作品存在，是请求被拒（风控/UA/登录态）。
    `_call`（搜索路径）早就识别了空 body，但 `_call_absolute`
    （详情路径）漏了 —— 又是"守卫只加在一个入口"。

    修后抛 `PlatformUnavailableError`（可读原因）。
    """
    from app.services.platforms.douyin import client as dy

    src = inspect.getsource(dy.DouyinClient._call_absolute)
    assert "空响应体" in src, "_call_absolute 要识别空 body（不能 json() 直接炸）"
    assert "PlatformUnavailableError" in src, "空 body 抛 PlatformUnavailableError"
    # 提示要点明"不是作品不存在"
    assert "不是「作品不存在」" in src or "不是「作品不存在」" in src
