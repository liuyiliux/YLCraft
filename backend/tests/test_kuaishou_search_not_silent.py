# -*- coding: utf-8 -*-
"""
快手搜索"静默变空"的回归测试（2026-10-02）。

## 现象

    POST /api/v1/crawler/search-enhanced {platform:"kuaishou"}
    → HTTP 200  {"success":true,"results":[],"message":"找到 0 条结果"}

用户以为"这个关键词没内容"，于是反复换关键词 ——
而真相是**登录态失效**（快手 result=2/109，实测登录态约 20 分钟失效）。

## 根因

`_post()` 对搜索路径 `return None`，`search()` 里 `if payload is None: break`
→ 返回空列表 → API 层包装成 200 空结果。

讽刺的是**同一个函数上面的注释已经写清楚了**
（"所以这里给可操作的错误，别让它静默变空白"），
却只对 `profile/*` 路径兑现了，搜索路径照样 `return None`。

## 修复

搜索路径遇到非 1 的 result 抛 `LoginExpiredError`（API 层 → 401），
翻页中途断流且已有结果则保留结果并告警，一条都没有则抛 `NetworkError`。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.platforms.types import LoginExpiredError, NetworkError, PlatformError

CLIENT = (
    Path(__file__).resolve().parents[1]
    / "app" / "services" / "platforms" / "kuaishou" / "client.py"
)


def _src() -> str:
    if not CLIENT.exists():
        pytest.skip("kuaishou client not found")
    return CLIENT.read_text(encoding="utf-8")


def _func(name: str) -> str:
    """抽出指定函数的源码（缩进匹配），便于断言函数内的行为。"""
    src = _src()
    lines = src.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith(f"async def {name}(") or ln.strip().startswith(f"def {name}("):
            start = i
            break
    assert start is not None, f"找不到函数 {name}"
    indent = len(lines[start]) - len(lines[start].lstrip())
    body = [lines[start]]
    for ln in lines[start + 1 :]:
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent and not ln.strip().startswith((")", "]", "}")):
            # 同级缩进且非空 → 函数结束（除非是续行）
            if ln.lstrip().startswith(("async def ", "def ", "@", "class ")):
                break
        body.append(ln)
    return "\n".join(body)


# =============================================================================
# 旧行为必须消失
# =============================================================================

def test_search_path_no_longer_returns_none_silently():
    """`_post` 不能再对搜索路径 `return None`（会被吞成空结果）。"""
    body = _func("_post")
    # 只允许为 profile 路径 return None；不能再有"落到最后 return None"
    assert "if uri in (PROFILE_GET, PROFILE_FEED):" in body, (
        "profile 分支丢失"
    )
    # 搜索路径必须抛异常
    assert "raise LoginExpiredError" in body
    # 不能有「日志打完就 return None」的静默分支
    import re
    tail = body.split("if uri in (PROFILE_GET, PROFILE_FEED):")[-1]
    assert not re.search(r"return\s+None\s*$", tail, re.M), (
        "搜索路径仍会在记录日志后 `return None` —— 会静默变空结果"
    )


def test_search_breaks_only_when_results_exist():
    """翻页中途断流时，只在**已经有结果**时才 break 保留；否则必须报错。"""
    body = _func("search")
    assert "if out:" in body, "翻页失败时应判断已积累的结果"
    assert "raise NetworkError" in body, "一条都没拿到时必须报错，不能返回空列表"


def test_search_does_not_return_empty_list_on_lost_cursor():
    """到目标页前游标就断了 → 返回已积累的结果，而不是 []。"""
    body = _func("search")
    assert "return out[:want]" in body
    # 旧的 `return []`（吞掉已有结果）不能还在
    assert "return []" not in body, (
        "游标断掉时仍 `return []` —— 会丢掉已拿到的结果"
    )


# =============================================================================
# 抛出的异常必须是正确类型
# =============================================================================

def test_login_expired_error_is_platform_error():
    """必须是 PlatformError 的子类，API 层才能按类型映射成 401。

    裸 RuntimeError 会落到 `except Exception` → 500，
    用户看到"服务端故障"而真相是"去重新登录"。
    """
    assert issubclass(LoginExpiredError, PlatformError)
    assert issubclass(NetworkError, PlatformError)


def test_login_expired_not_retryable():
    """登录失效不该重试（重试可能升级为封号），也不该降级兜底。"""
    assert LoginExpiredError.retryable is False
    assert LoginExpiredError.should_fallback is False


def test_platform_error_rejects_unexpected_kwargs():
    """`PlatformError` 不接受自定义具名参数 —— 抛异常时不能凭空加。

    曾写 `LoginExpiredError(..., result=result)`：
    `PlatformError(RuntimeError)` 是 C 层异常，传未定义的关键字
    会直接 `TypeError`，而且发生在**异常路径里**，
    把"登录失效"掩盖成"TypeError"，比原来更糟。
    """
    with pytest.raises(TypeError):
        LoginExpiredError("msg", result=2)
    # 位置参数（一个 message）必须正常
    err = LoginExpiredError("登录态失效")
    assert err.args == ("登录态失效",)
