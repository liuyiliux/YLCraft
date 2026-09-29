"""小红书**搜索**纯 HTTP API 的回归测试。

## 又一次"端点失效"的误判（2026-09-29 修正）

`search.py` 的模块注释里写着：

    小红书搜索端点已从 `edith.../v1/search/notes` 迁移到
    `so.xiaohongshu.com/api/sns/web/v2/search/notes`（域名+版本都变了）。
    该接口需要 X-s/X-t 签名，签名函数 `window._webmsxyw` 是混淆 JS，
    Python 里重写签名不可行也不必要；用 Patchright 打开搜索页读 DOM。

而且它还自相矛盾地写着 300011 是"**缺 X-s/X-t 签名被风控拒**" ——
**却据此断定"端点迁移了"**。

装上 `xhshow`（纯 Python 签名）后实测：

    POST https://edith.xiaohongshu.com/api/sns/web/v1/search/notes
    body = {keyword, page, page_size, search_id, sort, note_type}
    → HTTP 200, success=True, data.items[20~21]

**端点没迁移，也一直可用。**

## 实测能力

| 能力 | 结果 |
|------|------|
| 分页 `page=1/2/3` | ✅ 三页首条各不相同 |
| 排序 | ✅ general / time_descending / popularity_descending |
| `note_type` 筛选 | ❌ **不生效**（0/1/2 结果相同，`type` 恒为 normal） |
| `search_id` | ⚠️ **必需**（空串返回 0 条） |
| 速度 | ✅ **3 秒**（浏览器路径 ~15 秒） |

## 全链路

搜索返回的 item 上**自带 `xsec_token`** —— 直接喂给详情接口，
搜索 → 详情全程纯 HTTP，**零浏览器**。
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# 端点必须被视为「可用」
# =============================================================================

def test_search_api_is_real_implementation():
    """**回归**：`search_api.search_via_api` 必须是真实实现。"""
    from app.services.platforms.xiaohongshu import search_api

    src = inspect.getsource(search_api.search_via_api)
    assert "search/notes" in src, "应请求 /search/notes"
    assert "sign_post" in src, "必须签名（缺签名会被风控拒）"
    assert "keyword" in src


def test_search_module_is_thin_forwarder():
    """`search.py` 应只做转发，不该再有"已停用"的报错实现。"""
    from app.services.platforms.xiaohongshu import search as search_mod

    src = inspect.getsource(search_mod)
    # 只检查**代码行**（注释/docstring 里会引用历史那句错误结论，说明为什么改）
    code_lines = [
        ln for ln in src.splitlines()
        if not ln.strip().startswith("#")
        and not ln.strip().startswith('"')
        and not ln.strip().startswith("⚠️")
        and not ln.strip().startswith("本文件")
        and not ln.strip().startswith("而 ")
        and not ln.strip().startswith("所以")
        and not ln.strip().startswith("真实")
        and not ln.strip().startswith("**")
        and not ln.strip().startswith("原文")
        and not ln.strip().startswith("等")
    ]
    code = "\n".join(code_lines)
    # 不该再有"抛错当作实现"的写法
    assert "raise RuntimeError" not in code or "Cookie" in code, (
        "不该再用抛错代替实现（现在只该因缺 cookie 而抛）"
    )
    # REAL_ENDPOINT 要指向可用的 v1
    assert "/api/sns/web/v1/search/notes" in search_mod.REAL_ENDPOINT


# =============================================================================
# 参数
# =============================================================================

def test_sort_aliases():
    """排序别名要映射到接口取值（三档实测都可用）。"""
    from app.services.platforms.xiaohongshu.search_api import resolve_sort

    assert resolve_sort("") == "general"
    assert resolve_sort("default") == "general"
    assert resolve_sort("latest") == "time_descending"
    assert resolve_sort("time") == "time_descending"
    assert resolve_sort("hot") == "popularity_descending"
    # 未知值退回 general（不编造）
    assert resolve_sort("不存在") == "general"


def test_search_id_is_generated():
    """`search_id` 必须非空 —— 实测空串返回 0 条。"""
    from app.services.platforms.xiaohongshu.search_api import _make_search_id

    sid = _make_search_id()
    assert sid, "不能为空"
    assert len(sid) >= 10, f"形状要合理，实际 {len(sid)}"


async def test_search_requires_cookie():
    """缺 cookie 要报可操作错误，不静默返回空。"""
    from app.services.platforms.types import SearchParams
    from app.services.platforms.xiaohongshu.search_api import search_via_api

    class _Cfg:
        cookie = ""

    class _Cli:
        config = _Cfg()

    with pytest.raises(RuntimeError) as exc:
        await search_via_api(_Cli(), SearchParams(keyword="x"))
    assert "Cookie" in str(exc.value)


async def test_empty_keyword_returns_empty():
    """空关键词直接返回空（不白跑一次请求）。"""
    from app.services.platforms.types import SearchParams
    from app.services.platforms.xiaohongshu.search_api import search_via_api

    class _Cfg:
        cookie = "a1=x; web_session=y"

    class _Cli:
        config = _Cfg()

    assert await search_via_api(_Cli(), SearchParams(keyword="   ")) == []


# =============================================================================
# 解析
# =============================================================================

def test_parse_item_basic():
    """解析搜索结果项（含 token / 互动数 / 发布时间）。"""
    from app.services.platforms.xiaohongshu.search_api import parse_item

    r = parse_item({
        "id": "abc123",
        "xsec_token": "TOK",
        "note_card": {
            "display_title": "标题",
            "type": "normal",
            "user": {"nickname": "作者", "user_id": "u1"},
            "interact_info": {"liked_count": "58", "collected_count": "12",
                              "comment_count": "45", "shared_count": "7"},
            "corner_tag_info": [{"type": "publish_time", "text": "02-10"}],
        },
    })
    assert r is not None
    assert r.id == "abc123"
    assert r.title == "标题"
    assert r.author == "作者"
    assert r.likes == 58
    assert r.create_time == "02-10"
    # token 必须带出来（详情要用）
    assert r.raw_data["xsec_token"] == "TOK"
    assert r.raw_data["collected_count"] == 12


def test_parse_item_skips_bad_input():
    """缺 id 或 note_card 的项要跳过（不产出空壳）。"""
    from app.services.platforms.xiaohongshu.search_api import parse_item

    assert parse_item({}) is None
    assert parse_item({"id": "x"}) is None
    assert parse_item(None) is None


def test_parse_item_type_is_honest():
    """**不要**把 type 猜成 video —— 搜索接口不下发真实类型。

    实测所有卡片 `note_card.type` 都是 `"normal"`，
    所以这里如实标 `"note"`，不编造。
    """
    from app.services.platforms.xiaohongshu.search_api import parse_item

    r = parse_item({
        "id": "x", "xsec_token": "t",
        "note_card": {"display_title": "d", "type": "normal"},
    })
    assert r is not None
    assert r.type == "note"


def test_cover_is_empty_with_reason():
    """搜索卡片**不含图片 URL** —— cover 留空是如实的，不是漏解析。

    实测 `image_list` 只有宽高、`cover` 也只有尺寸。
    """
    from app.services.platforms.xiaohongshu import search_api

    src = inspect.getsource(search_api.parse_item)
    assert "cover=\"\"" in src or 'cover=""' in src
    # 注释里要说明原因，避免后人以为是 bug
    assert "不含图片" in src or "只有宽高" in src


# =============================================================================
# 接线
# =============================================================================

def test_client_defaults_to_api():
    """client.search 默认走 api（纯 HTTP）。"""
    from app.services.platforms.xiaohongshu import client as xhs_client

    src = inspect.getsource(xhs_client.XiaohongshuClient.search)
    assert "search_via_api" in src
    # patchright 只作兜底
    assert "ClientMode.PATCHRIGHT" in src


def test_crawler_browser_only_excludes_xhs():
    """**回归**：`BROWSER_ONLY` 不该含 xhs。

    硬编码那一步让每次搜索都白开浏览器（15s vs 现在 3s）。
    """
    from app.services.crawler import service as crawler_service

    src = inspect.getsource(crawler_service.CrawlerService._search_via_platforms)
    line = next(
        (ln for ln in src.splitlines() if "BROWSER_ONLY" in ln and "=" in ln), ""
    )
    assert line
    assert "xhs" not in line, f"xhs 不该在 BROWSER_ONLY：{line.strip()}"
    assert "weibo" in line, "微博仍需 Service Worker 上下文"
