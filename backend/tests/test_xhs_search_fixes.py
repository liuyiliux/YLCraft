"""小红书搜索的两个关键修复（2026-09-26 实测）。

## 修复 1：用 add_cookies 注入，不能用请求头传 Cookie

对照实测（同一 Cookie、同一时刻）：

    fetch_page(headers={"Cookie": ...})  → 0 张卡片
    ctx.add_cookies(...)                 → 27~30 张卡片

小红书的登录态判断依赖浏览器 cookie jar 里的域属性，
光在请求头带 Cookie 不够。

## 修复 2：必须先访问首页"预热"，不能直接开搜索页

对照实测：

    先 goto /explore 再 goto 搜索页 → ✅ 27 张卡片
    直接 goto 搜索页               → ❌ 超时 / 0 张

搜索页依赖首页建立的会话上下文，直接进拿不到数据。
这是最隐蔽的一条——单看搜索页的请求/响应完全正常，
只是数据永远不回来。
"""

from __future__ import annotations

import inspect

import pytest


def test_search_uses_add_cookies_not_header():
    """必须用 ctx.add_cookies 注入，不能用 headers 传 Cookie。"""
    import ast

    from app.services.platforms.xiaohongshu import search_patchright as sp

    src = inspect.getsource(sp.search_with_runtime)
    assert "add_cookies" in src, "应显式注入 cookie jar（Header 方式实测无效）"

    # 用 AST 判断真实调用，避开 docstring/注释里的字样
    tree = ast.parse(src.replace("async def ", "def "))
    calls = [
        n.func.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    ]
    assert "fetch_page" not in calls, "不应再实际调用 fetch_page（实测 0 张卡片）"


def test_warmup_failure_is_tolerated():
    """预热失败只告警不中断——要走到搜索那一步才知道到底行不行。"""
    import ast

    from app.services.platforms.xiaohongshu import search_patchright as sp

    func = sp.search_with_runtime
    tree = ast.parse(inspect.getsource(func).replace("async def ", "def "))

    # 找到含 /explore 的 try 语句，确认它有 except（即失败被捕获）
    found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        seg = ast.unparse(node)
        if "/explore" in seg:
            assert node.handlers, "预热失败应被 except 捕获（只告警）"
            found = True
            break
    assert found, "应存在包含 /explore 预热的 try 块"


def test_search_warms_up_explore_first():
    """必须先访问首页预热。"""
    from app.services.platforms.xiaohongshu import search_patchright as sp

    src = inspect.getsource(sp.search_with_runtime)
    assert "/explore" in src, "应先访问首页预热（实测直接搜会 0 张/超时）"
    # 预热必须发生在打开搜索页之前
    i_explore = src.find("/explore")
    i_search = src.find("SEARCH_URL.format")
    assert i_explore < i_search, "预热必须在打开搜索页之前"


def test_search_uses_headful_mode():
    """不能用无头——实测无头会被甩到验证码/登录页。"""
    from app.services.platforms.xiaohongshu import search_patchright as sp

    src = inspect.getsource(sp.search_with_runtime)
    assert "headless=False" in src
    assert "headless=True" not in src


def test_search_reads_dom_cards():
    """要通过 DOM 读卡片（section.note-item），不是解析 HTML 正则。"""
    from app.services.platforms.xiaohongshu import search_patchright as sp

    src = inspect.getsource(sp.search_with_runtime)
    assert "JS_PARSE_CARDS" in src or "evaluate" in src
    assert "note-item" in inspect.getsource(sp)


def test_search_raises_on_login_redirect():
    """被重定向到登录页要明确报错，不能返回空列表。"""
    from app.services.platforms.xiaohongshu import search_patchright as sp

    src = inspect.getsource(sp.search_with_runtime)
    assert "/login" in src
    assert "RuntimeError" in src


def test_search_raises_readable_error_on_goto_timeout():
    """打开搜索页超时要给可读原因（实测直接搜会超时）。"""
    from app.services.platforms.xiaohongshu import search_patchright as sp

    src = inspect.getsource(sp.search_with_runtime)
    assert "超时" in src, "超时应说明原因与下一步"
    assert "重新获取" in src or "Cookie" in src


def test_warmup_failure_is_tolerated():
    """预热失败只告警不中断——要走到搜索那一步才知道到底行不行。

    只认"try 体里直接 goto /explore、且有 except"的那一个：
    外层 try/finally（无 handlers）也会 unparse 出 /explore，必须排除。
    """
    import ast

    from app.services.platforms.xiaohongshu import search_patchright as sp

    tree = ast.parse(
        inspect.getsource(sp.search_with_runtime).replace("async def ", "def ")
    )

    warmup_try = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try) or not node.handlers:
            continue
        body_src = "".join(ast.unparse(st) for st in node.body)
        if "goto('https://www.xiaohongshu.com/explore'" in body_src:
            warmup_try = node
            break

    assert warmup_try is not None, "应存在专门的预热 try 块（直接 goto /explore）"
    assert warmup_try.handlers, "预热失败应被 except 捕获（只告警不中断）"
    # 确认是"告警"而不是"抛出"
    handler_src = "".join(ast.unparse(h) for h in warmup_try.handlers)
    assert "warning" in handler_src, "预热失败应只告警"
