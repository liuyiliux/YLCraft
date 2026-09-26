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
    """必须先访问首页预热。

    重构后预热被抽成共享的 _warmup()，两条入口（注入页 / 自建浏览器）
    都调用它——这样才不会出现"一条路径预热、另一条不预热"的不一致
    （实测踩过：注入页那条少了预热，表现为 Page.goto 超时）。
    """
    from app.services.platforms.xiaohongshu import search_patchright as sp

    warm_src = inspect.getsource(sp._warmup)
    assert "/explore" in warm_src, "预热应访问首页"

    # 两条入口都必须调用 _warmup
    assert "_warmup" in inspect.getsource(sp.search_via_patchright)
    assert "_warmup" in inspect.getsource(sp.search_with_runtime)

    # 且预热发生在搜索之前
    run_src = inspect.getsource(sp.search_with_runtime)
    assert run_src.find("_warmup") < run_src.find("_search_on_page")


def test_search_reads_dom_cards():
    """要通过 DOM 读卡片（section.note-item）。"""
    from app.services.platforms.xiaohongshu import search_patchright as sp

    src = inspect.getsource(sp._search_on_page)
    assert "JS_PARSE_CARDS" in src or "evaluate" in src
    assert "note-item" in src


def test_search_uses_headful_mode():
    """不能用无头——实测无头会被甩到验证码/登录页。"""
    from app.services.platforms.xiaohongshu import search_patchright as sp

    src = inspect.getsource(sp.search_with_runtime)
    assert "headless=False" in src
    assert "headless=True" not in src


def test_search_reads_dom_cards():
    """要通过 DOM 读卡片（section.note-item），不是解析 HTML 正则。"""
    from app.services.platforms.xiaohongshu import search_patchright as sp

    src = inspect.getsource(sp._search_on_page)
    assert "JS_PARSE_CARDS" in src or "evaluate" in src
    assert "note-item" in src


def test_search_raises_on_login_redirect():
    """被重定向到登录页要明确报错，不能返回空列表。"""
    from app.services.platforms.xiaohongshu import search_patchright as sp

    src = inspect.getsource(sp._search_on_page)
    assert "/login" in src
    assert "RuntimeError" in src


def test_search_raises_readable_error_on_goto_timeout():
    """打开搜索页超时要给可读原因（实测直接搜会超时）。"""
    from app.services.platforms.xiaohongshu import search_patchright as sp

    src = inspect.getsource(sp._search_on_page)
    assert "超时" in src, "超时应说明原因与下一步"
    assert "重新获取" in src or "Cookie" in src


def test_warmup_failure_is_tolerated():
    """预热失败只告警不中断——要走到搜索那一步才知道到底行不行。

    重构后预热是独立的 _warmup()，直接查它的 try/except 即可。
    """
    import ast

    from app.services.platforms.xiaohongshu import search_patchright as sp

    tree = ast.parse(inspect.getsource(sp._warmup).replace("async def ", "def "))

    tries = [n for n in ast.walk(tree) if isinstance(n, ast.Try)]
    assert tries, "预热应包在 try 里（失败不能中断）"

    warm = next(
        (t for t in tries if "explore" in "".join(ast.unparse(s) for s in t.body)),
        None,
    )
    assert warm is not None, "应有包住 goto /explore 的 try 块"
    assert warm.handlers, "预热失败应被 except 捕获（只告警不中断）"

    handler_src = "".join(ast.unparse(h) for h in warm.handlers)
    assert "warning" in handler_src, "预热失败应只告警，不抛错"
