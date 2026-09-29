"""小红书搜索「封面 URL」与「总数措辞」的回归测试。

## 问题①：搜索列表封面全空

用户反馈："搜索列表小红书的图片不显示了"。

**根因**：小红书搜索接口**不传 `image_formats` 参数时，`cover` 里
只有宽高、没有 URL**：

    不带:              cover = {"height":1600, "width":1200}
    带 image_formats:  cover = {..., "url_default": "http://sns-webpic-qc..."}

加上参数后实测 **20/20 条都有封面**。

⚠️ 这个坑我上一轮**碰到过但没解决** —— 当时只在注释里写了
"搜索卡片不含图片 URL，这是接口限制"，就放过了。
**"接口限制"这个结论下得太早** —— 差一个参数而已。
教训：说"平台不给"之前，先把常见可选参数试一遍。

## 问题②：「共20条」是误导

用户问："这个二十页是写死的吗"。

接口固定一页给 20 条，而我第一版把 `_total` 设成**本页条数**：

    results[0].raw_data["_total"] = len(results)   # ← 错

前端于是显示"共 20 条"，但翻到第 2、3 页**明明还有内容**。

**小红书不给真实 total**，只给 `has_more`。所以：
  · 后端**不再设** `_total`（不编造）
  · 新增 `has_more` 字段透出
  · 前端据此说"10 条（还有更多）"而不是"共 10 条"

## 教训汇总

1. **"接口限制"下结论前，把可选参数试一遍**（差一个 `image_formats`）
2. **别把"本页条数"当"总数"** —— 措辞会误导用户
"""

from __future__ import annotations

import inspect

import pytest

FRONTEND = None


def _frontend_src(rel: str) -> str:
    from pathlib import Path

    p = Path(__file__).resolve().parents[2] / "frontend" / "src" / rel
    if not p.exists():
        pytest.skip(f"文件不在预期位置：{p}")
    return p.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# 封面（image_formats）
# =============================================================================

def test_request_includes_image_formats():
    """**回归**：请求必须带 `image_formats`，否则封面没有 URL。

    实测：不带时 `cover` 只有 `{height, width}`；带上才有 `url_default`。
    """
    from app.services.platforms.xiaohongshu import search_api

    src = inspect.getsource(search_api.search_via_api)
    assert "image_formats" in src, (
        "必须带 image_formats —— 否则搜索列表封面全空（实测）"
    )


def test_image_formats_documented():
    """要记录"差这个参数封面就没了"—— 避免后人删掉它。"""
    from app.services.platforms.xiaohongshu import search_api

    doc = inspect.getsource(search_api.search_via_api)
    assert "url_default" in doc or "封面" in doc
    # 应写明不带会怎样
    assert "不带" in doc or "否则" in doc


def test_parse_item_reads_cover_url():
    """**回归**：`parse_item` 要从 `cover.url_default` 取封面。"""
    from app.services.platforms.xiaohongshu.search_api import parse_item

    r = parse_item({
        "id": "n1", "xsec_token": "t",
        "note_card": {
            "display_title": "标题",
            "cover": {
                "url_default": "http://sns-webpic-qc.xhscdn.com/abc",
                "height": 1600, "width": 1200,
            },
        },
    })
    assert r is not None
    assert r.cover.startswith("http"), f"应取到封面 URL，实际 {r.cover!r}"


def test_parse_item_falls_back_to_url_pre():
    """没有 `url_default` 时退回 `url_pre`。"""
    from app.services.platforms.xiaohongshu.search_api import parse_item

    r = parse_item({
        "id": "n1", "xsec_token": "t",
        "note_card": {
            "display_title": "t",
            "cover": {"url_pre": "http://x/pre.webp", "height": 1, "width": 1},
        },
    })
    assert r is not None
    assert r.cover == "http://x/pre.webp"


def test_parse_item_tolerates_cover_without_url():
    """封面只有宽高（没带 image_formats 时）不能崩，cover 留空。"""
    from app.services.platforms.xiaohongshu.search_api import parse_item

    r = parse_item({
        "id": "n1", "xsec_token": "t",
        "note_card": {"display_title": "t", "cover": {"height": 1, "width": 1}},
    })
    assert r is not None
    assert r.cover == ""
    # 尺寸仍要保留（前端可能用）
    assert r.raw_data["cover_size"]["width"] == 1


# =============================================================================
# 总数措辞（has_more）
# =============================================================================

def test_does_not_fake_total():
    """**回归**：**不要**把本页条数当 `_total`。

    小红书不给真实 total，只给 `has_more`。
    设 `_total = len(results)` 会让前端说"共 20 条"，
    但翻页明明还有内容 —— 误导用户。
    """
    from app.services.platforms.xiaohongshu import search_api

    src = inspect.getsource(search_api.search_via_api)
    assert '_total"] = len(results)' not in src, (
        "不该把本页条数当总数（会显示成'共 N 条'误导用户）"
    )
    assert "_has_more" in src, "应透出 has_more"


def test_search_response_has_has_more_field():
    """API 响应模型要有 `has_more` 字段。"""
    from app.api.v1.crawler import SearchResponse

    assert "has_more" in SearchResponse.model_fields


def test_router_passes_has_more():
    """路由层要从 raw_data 取出 `_has_more` 并透传。"""
    import inspect as _inspect

    from app.api.v1 import crawler as crawler_api

    src = _inspect.getsource(crawler_api.search_enhanced)
    assert "has_more" in src, "路由应透出 has_more"
    assert "_has_more" in src


def test_frontend_shows_more_hint():
    """**回归**：前端有 hasMore 时应说"还有更多"，不是"共 N 条"。"""
    src = _frontend_src("pages/crawler/index.tsx")
    assert "hasMore" in src, "应有 hasMore 状态"
    assert "还有更多" in src, "应显示'还有更多'"


def test_frontend_reads_has_more_from_response():
    """前端要从响应里读 `has_more`。"""
    src = _frontend_src("pages/crawler/index.tsx")
    assert "has_more" in src, "应读 data.has_more"
