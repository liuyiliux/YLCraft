"""小红书搜索「page_size 只认 20」的回归测试（本轮的真凶）。

## 用户症状

    "我搜索小红书没搜到东西"

实测：**所有关键词都 0 条**。

## 根因：小红书搜索接口的 `page_size` **只接受 20**

实测矩阵（同一个 cookie、同一个 URL，只有 `page_size` 不同）：

    page_size= 1  → items 为空
    page_size= 5  → items 为空
    page_size=10  → items 为空     ← 前端默认"每页 10 条"，正好踩中
    page_size=15  → items 为空
    page_size=20  → **22 条** ✅    ← 唯一有效值
    page_size=30  → items 为空
    page_size=50  → items 为空

## 为什么这个坑很隐蔽

响应是：

    HTTP 200
    {"msg":"成功","data":{"has_more":false},"code":0,"success":true}

**状态码 200、`success: true`、`msg: "成功"`** —— 完全看不出是参数问题，
只表现为"这个词没有结果"。我为此排查了很久（换端口、怀疑缓存、
怀疑 cookie、怀疑签名…全不是）。

## 教训

**"所有关键词都 0 条" 时，先怀疑参数/凭证，而不是关键词没内容。**
单个词搜不到是正常的；**全部都搜不到一定是 bug**。

## 另一个连带 bug（同轮修的）

`_search_via_platforms` **从来没有把 cookie 传给 `platform_search`**：

    results = await platform_search(..., conn_id=conn_id, **kwargs)
                                                  # ↑ 没有 cookie=

以前小红书走 patchright（浏览器自己注入 cookie）所以没暴露；
改成 api（纯 HTTP）后就断了 —— `[xhs] 搜索需要登录 Cookie`。

而 `_resolve_cookie_for` 第一版也有坑：用
`PlatformConnectionService().get_raw_cookie()` 返回 None，
且 `netscape_to_header(raw, "xhs")` 返回 0 字符
（**必须传 `xiaohongshu`**）。
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# page_size 必须是 20（本轮真凶）
# =============================================================================

def test_page_size_is_fixed_to_20():
    """**回归（最重要）**：`page_size` 必须是 20。

    小红书只认 20，其它值一律返回空 items（但 HTTP 200 + success=true）。
    前端默认"每页 10 条"正好踩中 → "搜什么都没结果"。
    """
    from app.services.platforms.xiaohongshu import search_api

    src = inspect.getsource(search_api.search_via_api)
    assert "page_size = 20" in src, (
        "page_size 必须固定为 20 —— 其它值接口返回空 items（实测）"
    )
    # 不该再出现"按 max_results 算 page_size"的写法
    assert "page_size = max(1, min(" not in src, (
        "不该按 max_results 算 page_size（会踩中只认 20 的坑）"
    )


def test_page_size_20_is_documented():
    """要记录实测矩阵 —— 避免后人"优化"成别的值。"""
    from app.services.platforms.xiaohongshu import search_api

    doc = inspect.getsource(search_api.search_via_api)
    assert "只认 20" in doc or "只能是 20" in doc
    # 至少列出几个实测过的无效值
    assert "10" in doc and "50" in doc


def test_max_results_is_respected_by_truncation():
    """接口固定给 20 条，但调用方要 10 条时应截断到 10。"""
    from app.services.platforms.xiaohongshu import search_api

    src = inspect.getsource(search_api.search_via_api)
    assert "results[:want]" in src or "[:want]" in src, "应按调用方要的条数截断"


# =============================================================================
# cookie 传递（连带 bug）
# =============================================================================

def test_search_passes_cookie_to_platform_search():
    """**回归**：`_search_via_platforms` 必须传 cookie。

    原来只传 `conn_id` —— patchright 模式没暴露问题（浏览器自己注入），
    改 api 后直接 `[xhs] 搜索需要登录 Cookie`，搜索永远 0 条。
    """
    from app.services.crawler import service as crawler_service

    src = inspect.getsource(crawler_service.CrawlerService._search_via_platforms)
    assert "cookie=cookie" in src, "必须把 cookie 传给 platform_search"
    assert "_resolve_cookie_for" in src


def test_popping_duplicate_cookie_kwarg():
    """**回归**：kwargs 里可能已有 cookie，要先剔除。

    否则 `search() got multiple values for keyword argument 'cookie'`
    （实测踩过 —— 路由层会把 cookie 塞进 kwargs）。
    """
    from app.services.crawler import service as crawler_service

    src = inspect.getsource(crawler_service.CrawlerService._search_via_platforms)
    assert 'kwargs.pop("cookie"' in src


def test_cookie_domain_uses_alias():
    """**回归**：`netscape_to_header` 的 domain 要用它认识的别名。

    实测传 `xhs` 返回 **0 字符**，传 `xiaohongshu` 才返回 998 字符。
    """
    from app.services.crawler import service as crawler_service

    src = inspect.getsource(crawler_service.CrawlerService._resolve_cookie_for)
    assert '"xhs": "xiaohongshu"' in src, "应做平台名归一"
    assert "netscape_to_header" in src


def test_cookie_resolver_uses_resolve_connection():
    """**回归**：用 `resolve_connection`（已验证可用），
    不要用 `PlatformConnectionService().get_raw_cookie()`
    —— 后者在该上下文返回 None（实测）。

    注：只检查**代码**，注释里会提到它（说明为什么不用）。
    """
    from app.services.crawler import service as crawler_service

    src = inspect.getsource(crawler_service.CrawlerService._resolve_cookie_for)
    code = "\n".join(
        ln for ln in src.splitlines() if not ln.strip().startswith("#")
    )
    # 去掉 docstring
    import re

    code = re.sub(r'""".*?"""', "", code, flags=re.S)

    assert "resolve_connection" in code
    assert "get_raw_cookie" not in code, (
        "不要用 get_raw_cookie —— 实测在这个上下文返回 None"
    )


# =============================================================================
# 诊断日志（让下次更快定位）
# =============================================================================

def test_logs_items_count_when_empty():
    """**回归**：items 为空时要打出响应结构。

    "请求 200 但 items=0" 时，光看状态码看不出原因；
    有这条日志能立刻区分"平台没给数据"和"参数不对"。
    """
    from app.services.platforms.xiaohongshu import search_api

    src = inspect.getsource(search_api.search_via_api)
    assert "items 为空" in src, "应记录 items 为空的情况"
    assert "resp.text" in src, "应打出响应片段"


def test_logs_items_vs_parsed_count():
    """日志要同时给"items 条数"和"解析出条数"。

    这两个数字不一致 → 是**解析**问题（字段结构变了）；
    都是 0 → 是**参数/凭证**问题。能省很多排查时间。
    """
    from app.services.platforms.xiaohongshu import search_api

    src = inspect.getsource(search_api.search_via_api)
    assert "items=%d" in src or "items=" in src
