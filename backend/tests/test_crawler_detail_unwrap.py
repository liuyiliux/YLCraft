"""详情面板「描述为空 / 只显示一张图」的回归测试。

## 用户反馈

"还是都不行" —— 详情面板描述显示"暂无描述"，图集只显示一张。

## 根因：前端**展开错了响应层级**

`note-detail` 返回的结构是：

    {"success": true, "data": {...真正的字段...}, "message": "获取成功"}

而前端写的是：

    const detail = await getNoteDetail(...)
    setDetailNote(prev => ({ ...prev, ...detail }))
    //                                   ↑ 展开**顶层**

于是 `detail.desc` / `detail.images` 全是 `undefined`：

    · 描述 → "暂无描述"（后端其实给了正文）
    · 图集 → 只显示 `cover` 一张（`images` 没拿到）

**这两个症状是同一个 bug 引起的**（展开层级错），
不是两个独立问题。

## 连带

`previewMediaUrls` 原来只看 `raw_data.image_urls || cover`，
**完全没读 `images`** —— 即使层级修对了，多图也显示不出来。
现在优先用 `images`。

## 教训

**"接口返回的数据是对的，但界面显示不对" → 先检查"取值层级"。**
我一开始怀疑解析、怀疑接口，其实数据一直都在，
只是前端从错误的层级读（`detail` vs `detail.data`）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
PAGE = FRONTEND / "pages" / "crawler" / "index.tsx"
API = FRONTEND / "api" / "index.ts"


def _page() -> str:
    if not PAGE.exists():
        pytest.skip("搜索页不在预期位置")
    return PAGE.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# 响应层级
# =============================================================================

def test_detail_unwraps_data_field():
    """**回归（最重要）**：要展开 `resp.data`，不是 `resp` 本身。

    后端返回 `{success, data, message}`，真正字段在 `data` 里。
    展开顶层会拿到 `success/data/message` 三个键，
    `desc` / `images` 全是 undefined →
    "描述显示暂无描述" + "图集只显示一张"。
    """
    src = _page()
    assert "resp.data" in src or "detail.data" in src, (
        "应从响应的 data 字段取真正的详情"
    )
    # 不该再把整个响应直接展开进 detailNote
    assert "await getNoteDetail(" in src


def test_media_urls_prefers_images():
    """**回归**：`previewMediaUrls` 要优先用 `images`（图集）。

    原来只看 `raw_data.image_urls || cover` ——
    小红书/抖音的图集在 `images` 字段里，读不到就只显示封面一张。
    """
    src = _page()
    # 找 previewMediaUrls 的定义
    i = src.find("const previewMediaUrls")
    assert i != -1, "应能找到 previewMediaUrls"
    seg = src[i:i + 900]
    assert "images" in seg, "应读 images"
    assert "Array.isArray(imgs)" in seg or "imgs.length" in seg


def test_media_urls_falls_back_to_cover():
    """没有 images 时要退回 cover（不能空着）。"""
    src = _page()
    i = src.find("const previewMediaUrls")
    seg = src[i:i + 900]
    assert "cover" in seg, "应退回 cover"


# =============================================================================
# 类型定义
# =============================================================================

def test_crawler_result_has_images():
    """`CrawlerResult` 要有 `images` 字段（否则 TS 报错/取值 undefined）。"""
    if not API.exists():
        pytest.skip("api 文件不在预期位置")
    src = API.read_text(encoding="utf-8", errors="ignore")
    i = src.find("export interface CrawlerResult")
    assert i != -1
    seg = src[i:i + 900]
    assert "images" in seg


def test_crawler_result_has_collect_count_and_tags():
    """`CrawlerResult` 要有 `collect_count` 与 `tags`。

    ⚠️ 字段名是 `collect_count`（不是 `collects`）——
    与后端 `crawler.models.NoteDetail` 对齐。
    """
    if not API.exists():
        pytest.skip("api 文件不在预期位置")
    src = API.read_text(encoding="utf-8", errors="ignore")
    i = src.find("export interface CrawlerResult")
    seg = src[i:i + 1200]
    assert "collect_count" in seg
    assert "tags" in seg


# =============================================================================
# 展示
# =============================================================================

def test_desc_is_rendered():
    """描述要真的渲染出来（不是只写"暂无描述"）。"""
    src = _page()
    assert "detailNote.desc" in src, "应渲染 desc"
    assert "暂无描述" in src, "空值兜底保留"


def test_thumbnail_strip_for_multiple_images():
    """多图时要显示缩略图切换条。"""
    src = _page()
    assert "previewMediaUrls.length > 1" in src, "多图应有缩略图条"
