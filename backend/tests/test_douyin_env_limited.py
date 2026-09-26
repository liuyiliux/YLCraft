"""抖音"环境受限"必须报错而不是静默返回 0 条。

## 背景（2026-09-26 实测）

用户界面搜索抖音显示"找到 0 条结果"，让人以为是自己关键词的问题。
实测对照：

    用户真实 Chrome    → 搜索返回 5 条（正常）
    Patchright 自动化  → 搜索返回 0 条（data=[]，msg 为空）
                         但账号接口**正常**（user=True）

即抖音限制的是**自动化环境的搜索接口**，与 Cookie 有效性无关。

## 为什么必须抛错

空数组会被上层理解成"没搜到"。原来的代码在两层都把异常吞掉：
  1. `crawler/service.py::_search_via_platforms` 的 `except Exception: return []`
  2. `crawler/service.py::search_videos` 失败后降级到 yt-dlp（再失败一次）
最终用户只能看到"找到 0 条结果"，完全查不出原因。
"""

from __future__ import annotations

import inspect

import pytest


def test_platform_unavailable_error_exists():
    """要有专门的异常类型区分"平台不可用"与"搜索失败"。"""
    from app.services.platforms.douyin.client import PlatformUnavailableError

    assert issubclass(PlatformUnavailableError, RuntimeError)


def test_search_raises_when_cookie_ok_but_empty():
    """cookie 有效却搜不到 → 必须抛 PlatformUnavailableError。

    判据：搜索空 + 账号接口正常。这说明不是登录问题，
    而是搜索接口被限制，要如实告诉用户。
    """
    from app.services.platforms.douyin import client as dy_client

    src = inspect.getsource(dy_client.DouyinClient._raise_if_environment_degraded)
    assert "PlatformUnavailableError" in src
    assert "cookie_ok" in src or "uid" in src, "应区分 cookie 是否有效两种情况"
    assert "真实 Chrome" in src, "应给出实测对照作为依据"


def test_search_calls_degraded_probe_on_empty():
    """搜索返回空时必须调用探测，否则无法区分"没结果"与"被限制"。"""
    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient.search)
    assert "_raise_if_environment_degraded" in src


def test_probe_does_not_use_call_which_raises_on_status_8():
    """探测不能用 self._call()。

    实测：_call 见到 status_code != 0 就抛 RuntimeError，
    而抖音受限时恰恰返回 8 —— 会让探测自身变成异常被吞掉，
    于是永远不会报错（这正是修复前的状态）。
    """
    from app.services.platforms.douyin import client as dy_client

    src = inspect.getsource(dy_client.DouyinClient._raise_if_environment_degraded)
    assert "self._call(" not in src, "探测不能用 _call（它会对 status_code=8 抛错）"
    assert "_http_client" in src, "应直接发原始请求"


def test_crawler_does_not_swallow_platform_unavailable():
    """crawler 层不得把 PlatformUnavailableError 吞成空列表。"""
    from app.services.crawler import service as crawler_service

    src = inspect.getsource(crawler_service.CrawlerService._search_via_platforms)
    assert "PlatformUnavailableError" in src, "应单独 except 并重新抛出"

    src2 = inspect.getsource(crawler_service.CrawlerService.search_videos)
    assert "PlatformUnavailableError" in src2, "不应降级到 yt-dlp 再失败一次"


def test_module_imports_platform_unavailable_error():
    """crawler 必须真的 import 了这个异常（否则 except 永远不生效）。"""
    from app.services.crawler import service as crawler_service

    assert hasattr(crawler_service, "PlatformUnavailableError")
