"""图片缩略图与分页「翻不完」的回归测试。

## 问题①：详情里图片"有成功有失败"

用户反馈，截图里缩略图条有几个格子是空的。

**根因：用原图当缩略图。**

小红书原图动辄 **1~2 MB**，而缩略图格子只有 **40×40 px**。
加载慢 → 看起来像"图片失败"。

实测小红书 CDN 支持 `imageView2` 参数：

    原图                    1,657,105 字节
    ?imageView2/2/w/120        8,310 字节   ← **200 倍差距**
    ?imageView2/2/w/240       21,136 字节

修法：`proxyImageUrl(url, width)` 支持传宽度，
小红书图片会加 `imageView2` 拿缩略图。

  · 缩略图条 → 120px
  · 大图预览 → 800px
  · 列表封面 → 240px（列宽 260）

## 问题②：分页「只能到第二页」

分页器 `total: hasMore ? total + maxResults : total`
= 只多留 1 页 → **第 2 页之后又没得翻了**（用户反馈）。

**根因**：`total` 是"本页条数"（10），加一次 `maxResults` = 20，
分页器就认为只有 2 页。而翻到第 2 页时 `hasMore` 仍是 true，
但 `total` 还是 20 —— 所以**永远卡在第 2 页**。

修法：**用"已翻到的页数"累计** —— 每页都可能 has_more，
就让总数随当前页一起增长：

    hasMore ? Math.max(total, currentPage * maxResults) + maxResults : total

并加一条：**某页返回 0 条就停**（`hasMore && rows.length > 0`），
否则分页器会无限往后长。
"""

from __future__ import annotations

from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
PAGE = FRONTEND / "pages" / "crawler" / "index.tsx"


def _src() -> str:
    if not PAGE.exists():
        pytest.skip("搜索页不在预期位置")
    return PAGE.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# 缩略图
# =============================================================================

def test_proxy_image_url_accepts_width():
    """**回归**：`proxyImageUrl` 要支持传宽度生成缩略图。"""
    src = _src()
    assert "function proxyImageUrl(url?: string, width?: number)" in src, (
        "应支持 width 参数"
    )


def test_xhs_uses_image_view2():
    """**回归**：小红书图片要加 `imageView2` 参数取缩略图。

    实测：原图 1.6MB → `imageView2/2/w/120` 只有 8KB（200 倍）。
    """
    src = _src()
    assert "imageView2" in src, "应用 imageView2 取缩略图"
    assert "format/webp" in src


def test_thumbnail_strip_uses_small_width():
    """缩略图条要用小尺寸（120px）。"""
    src = _src()
    i = src.find("previewMediaUrls.map")
    assert i != -1
    seg = src[i:i + 700]
    assert "proxyImageUrl(url, 120)" in seg, "缩略图条应用 120px"


def test_main_preview_uses_medium_width():
    """大图预览用中等尺寸（800px），不是原图。"""
    src = _src()
    assert "proxyImageUrl(previewMediaUrls[detailMediaIdx], 800)" in src


def test_list_cover_uses_thumbnail():
    """列表封面也要用缩略图（24 张原图会很慢）。"""
    src = _src()
    assert "proxyImageUrl(cover, 240)" in src, "列表封面应用 240px"


def test_does_not_double_add_image_view2():
    """已经带了 `imageView2` 的 URL 不要重复加。"""
    src = _src()
    assert "url.includes('imageView2')" in src


# =============================================================================
# 分页：能一直往后翻
# =============================================================================

def test_pagination_grows_with_current_page():
    """**回归**：分页总数要随当前页增长，不能只加一次。

    第一版写成 `total + maxResults`（只多留 1 页）→
    用户**只能翻到第 2 页**就没得翻了（实测反馈）。
    """
    src = _src()
    assert "currentPage * maxResults" in src, (
        "分页总数应随当前页累计，否则只能翻 1 页"
    )


def test_pagination_stops_on_empty_page():
    """**回归**：某页返回 0 条就停，防止无限往后长。

    否则用户能一直点"下一页"却永远看不到内容。
    """
    src = _src()
    assert "rows.length > 0" in src, "空页应停止 hasMore"


def test_has_more_set_from_response():
    """`hasMore` 要从响应里的 `has_more` 读。"""
    src = _src()
    assert "has_more" in src
    assert "setHasMore" in src
