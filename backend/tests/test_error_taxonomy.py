"""类型化异常体系的回归测试（2026-10-01 重构）。

## 为什么做这个重构

原来判断"错误该不该降级到 yt-dlp / 该不该重试"靠**字符串匹配**：

    if any(k in msg for k in ("HTTP 461", "未登录", "风控", "antispam", ...)):
        raise          # 不降级
    return []          # 否则降级（可能吞成空）

**这是全项目最脆弱的一处**：改一次错误文案（比如把"未登录"改成
"登录已过期"）就让判断**静默失效** —— 异常被吞成 `return []`，
用户看到"找到 0 条结果"，而真相是被风控/登录失效。

本仓库为此**反复踩坑 4 次**（每次都"又发现一个不含关键词的报错文本"）：
  1. 快手签名失败文本不含关键词 → 吞成空
  2. 小红书 `code=-100 登录已过期` → 吞成空
  3. 抖音空 body → 变成 404"笔记不存在"
  4. 快手 `result=2` → 500 而非 401

**说明匹配文案这条路本身走不通**。

重构后：异常自己声明语义（`retryable` / `should_fallback`），
上层看类型决策，不依赖文案。
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# 类型体系本身
# =============================================================================

def test_all_platform_errors_share_base():
    """所有平台侧异常都要继承 `PlatformError`（上层才能统一 except）。"""
    from app.services.platforms.douyin.client import (
        DouyinSearchRateLimited,
        PlatformUnavailableError,
    )
    from app.services.platforms.types import (
        ContentNotFoundError,
        LoginExpiredError,
        NetworkError,
        PlatformError,
        RiskControlError,
    )

    for cls in (LoginExpiredError, RiskControlError, NetworkError,
                ContentNotFoundError, PlatformUnavailableError,
                DouyinSearchRateLimited):
        assert issubclass(cls, PlatformError), f"{cls.__name__} 应继承 PlatformError"


@pytest.mark.parametrize("name,retry,fallback", [
    # 登录失效：重试无用（要先重新登录），降级只会伪装成"没搜到"
    ("LoginExpiredError", False, False),
    # 风控：重试会升级为封号；降级会把"被拦"伪装成"没结果"
    ("RiskControlError", False, False),
    # 网络：这两个都可以（yt-dlp 可能走另一条路成功）
    ("NetworkError", True, True),
    # 内容不存在：重试无意义
    ("ContentNotFoundError", False, False),
])
def test_semantics(name, retry, fallback):
    """**核心**：每个异常的 `retryable` / `should_fallback` 语义要对。

    这两个属性就是**上层唯一的判据** —— 它们错了，
    降级/重试策略就错了（要么把风控伪装成没结果，
    要么对网络问题不重试）。
    """
    from app.services.platforms import types as t

    cls = getattr(t, name)
    assert cls.retryable is retry, f"{name}.retryable 应为 {retry}"
    assert cls.should_fallback is fallback, f"{name}.should_fallback 应为 {fallback}"


def test_douyin_unavailable_is_risk_control():
    """抖音的 `PlatformUnavailableError` 本质是**风控**，要归到 `RiskControlError`。

    它的场景（抖音对自动化环境整体降级、空 body 表示拒绝）
    就是风控，不是"平台坏了"。
    """
    from app.services.platforms.douyin.client import PlatformUnavailableError
    from app.services.platforms.types import RiskControlError

    assert issubclass(PlatformUnavailableError, RiskControlError)
    assert PlatformUnavailableError.should_fallback is False


def test_rate_limited_is_retryable():
    """**限流可重试**（等一会儿就好）—— 与"账号异常"不同。

    实测（2026-09-29）：抖音搜博主连发多次全 0，等 ~60 秒恢复。
    这类**应该**允许退避重试；而人机验证/账号异常重试会升级为封号。
    """
    from app.services.platforms.douyin.client import DouyinSearchRateLimited

    assert DouyinSearchRateLimited.retryable is True
    # 但仍不该降级（yt-dlp 也搜不到抖音，降级只会再空一次）
    assert DouyinSearchRateLimited.should_fallback is False


# =============================================================================
# ⚠️ 关键：不能再靠字符串匹配
# =============================================================================

def _code_only(fn) -> str:
    """取函数源码的**可执行部分**（去掉注释与 docstring）。

    ⚠️ 必须这样：这些函数的注释里**特意写了**历史教训
    （"原来靠 `any(k in msg ...)` 匹配"），那是说明不是用法。
    直接 grep 源码会把注释也算进去，导致误报
    （我在 youtube 的测试里踩过同一个坑）。
    """
    import ast
    import textwrap

    src = textwrap.dedent(inspect.getsource(fn))
    tree = ast.parse(src)
    # 去掉 docstring
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body.pop(0)
    return ast.unparse(tree)


def test_crawler_service_does_not_match_error_strings():
    """**回归（关键）**：`CrawlerService` 不得再用关键词匹配判错误。

    这是 4 次踩坑的根源。改成类型判断后，改文案不会再让策略失效。
    """
    from app.services.crawler import service as svc

    for fn in (svc.CrawlerService.search_videos,
               svc.CrawlerService._search_via_platforms):
        code = _code_only(fn)
        # 不允许再出现这些关键词匹配
        for bad in ('any(k in msg', 'in msg for k', '"461"', '"antispam"', '"风控"'):
            assert bad not in code, (
                f"{fn.__name__} 的**可执行代码**仍在用字符串匹配（{bad}）—— "
                "这正是 4 次踩坑的根源，应改用 PlatformError 类型判断"
            )
        # 必须用类型判断
        assert "PlatformError" in code, f"{fn.__name__} 应捕获 PlatformError"


def test_crawler_service_uses_should_fallback():
    """降级决策要看异常自己声明的 `should_fallback`。"""
    from app.services.crawler import service as svc

    code = _code_only(svc.CrawlerService.search_videos)
    assert "should_fallback" in code, "降级决策应读 should_fallback"


def test_search_routes_do_not_match_error_strings():
    """API 层同样不得用字符串匹配。"""
    from app.api.v1 import crawler

    for fn in (crawler.search_materials, crawler.search_enhanced):
        code = _code_only(fn)
        for bad in ('any(k in msg', 'in msg for k', '"461"', '"antispam"'):
            assert bad not in code, f"{fn.__name__} 的代码仍在字符串匹配（{bad}）"


def test_search_route_maps_types_to_status_codes():
    """API 层要按异常**类型**映射状态码。

    映射表（前端据此提示不同的话）：
      LoginExpiredError    → 401（重新登录）
      RiskControlError     → 429（风控，稍后重试）
      ContentNotFoundError → 404（内容不存在）
      NetworkError         → 503（网络问题）
    """
    from app.api.v1 import crawler

    src = inspect.getsource(crawler.search_enhanced)
    for name, code in (("LoginExpiredError", "401"),
                       ("RiskControlError", "429"),
                       ("ContentNotFoundError", "404"),
                       ("NetworkError", "503")):
        assert name in src, f"search_enhanced 要处理 {name}"
        assert code in src, f"{name} 要映射成 {code}"


# =============================================================================
# 平台侧要抛对类型
# =============================================================================

def test_xhs_risk_raises_risk_control():
    """小红书风控（461/300011）要抛 `RiskControlError`（→ 429）。"""
    from app.services.platforms.xiaohongshu import search_api

    src = inspect.getsource(search_api.search_via_api)
    assert "RiskControlError" in src, "风控要抛 RiskControlError（原来抛裸 RuntimeError）"


def test_telegram_network_error_is_distinct():
    """**回归**：Telegram 的网络失败要与"频道不存在"区分开。

    两者混在一起的话，"VPN 断了"会被当成"频道名拼错了" ——
    用户会去反复检查一个没拼错的名字。
    """
    from app.services.platforms.telegram import web_preview as wp

    src = inspect.getsource(wp.TelegramPublicClient.fetch_page)
    assert "NetworkError" in src, "网络问题要抛 NetworkError（可重试）"
    assert "TelegramPublicError" in src, "频道不存在/结构变化仍走 TelegramPublicError"

    # 两者语义必须不同
    from app.services.platforms.types import NetworkError
    assert wp.TelegramPublicError.should_fallback is False
    assert NetworkError.should_fallback is True


def test_youtube_network_error_typed():
    """YouTube 的"连不上"要抛 `NetworkError`（VPN 断了可重试）。"""
    from app.services.platforms.youtube import client as yc

    src = inspect.getsource(yc.YoutubeClient._extract_entries)
    assert "NetworkError" in src
    # 内容不存在要单独区分
    src2 = inspect.getsource(yc.YoutubeClient.get_detail)
    assert "ContentNotFoundError" in src2


# =============================================================================
# ⚠️ 用了但没导入（只在异常路径才暴露的隐蔽 bug）
# =============================================================================

def test_exception_types_are_imported_where_used():
    """**回归**：用到的异常类型必须在本文件**导入**过。

    ## 为什么单独测这个

    这类错误的特征是：**正常路径完全正常**，只有走到那条
    `except` / `raise` 分支才炸 `NameError`。测试不覆盖那条分支
    就发现不了。

    实测（2026-10-01 重构时我自己犯的）：在 `crawler/service.py`
    写了 `except PlatformError:` 但忘了 import ——
    结果**所有平台的错误路径**都变成
    `HTTP 500 "搜索失败: name 'PlatformError' is not defined"`，
    把本来能说清楚的 401/429 全吞成了 500。

    ⚠️ 这与仓库里 `users.py` 犯过的 `LoginExpiredError` NameError
    是**同一类错误**（当时也是只在异常路径暴露）。
    """
    import ast
    import glob

    names = {
        "PlatformError", "LoginExpiredError", "RiskControlError",
        "NetworkError", "ContentNotFoundError",
    }
    problems = []
    for py in glob.glob("app/**/*.py", recursive=True):
        try:
            tree = ast.parse(open(py, encoding="utf-8").read())
        except Exception:
            continue
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for a in node.names:
                    imported.add(a.asname or a.name)
            elif isinstance(node, ast.Import):
                for a in node.names:
                    imported.add((a.asname or a.name).split(".")[0])
        used = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is not None:
                for n in ast.walk(node.type):
                    if isinstance(n, ast.Name) and n.id in names:
                        used.add(n.id)
            if isinstance(node, ast.Raise) and node.exc is not None:
                for n in ast.walk(node.exc):
                    if isinstance(n, ast.Name) and n.id in names:
                        used.add(n.id)
        missing = used - imported
        if missing:
            problems.append(f"{py}: 缺 {sorted(missing)}")

    assert not problems, (
        "以下文件用了异常类型但没导入（只会在异常路径炸 NameError）：\n  "
        + "\n  ".join(problems)
    )
