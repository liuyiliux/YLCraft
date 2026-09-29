"""采集架构文档与代码一致性的回归测试。

## 为什么测文档

`docs/platform/COLLECTION_ARCHITECTURE.md` 描述的是**各平台走哪条路、
为什么**。这类文档最容易过时 —— 代码改了、文档没改，
后来的人会按错误的地图走。

**所以把文档里的关键事实钉进测试** —— 代码变了测试就会红，
提醒更新文档。

## 钉住什么

  · 传输层归属（哪些平台纯 HTTP、哪个必须浏览器）
  · 能力矩阵（哪些平台有哪些方法）
  · 三个"实测结论"（page_size=20 / image_formats / xsec_token）

注：测试只检查**文档里是否写了**关键事实，不追求逐字一致。
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "platform" / "COLLECTION_ARCHITECTURE.md"


def _doc() -> str:
    if not DOC.exists():
        pytest.skip("架构文档不存在")
    return DOC.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# 文档存在性与结构
# =============================================================================

def test_doc_exists():
    assert DOC.exists(), (
        "docs/platform/COLLECTION_ARCHITECTURE.md 应存在 —— "
        "采集架构的地图，缺了后人只能读代码猜"
    )


def test_doc_covers_all_platforms():
    """文档要覆盖全部平台。"""
    doc = _doc()
    for p in ("B站", "抖音", "小红书", "微博", "X", "番茄"):
        assert p in doc, f"文档应覆盖 {p}"


def test_doc_has_transport_section():
    """要有"传输层选择"章节 —— 这是最容易搞错的部分。"""
    doc = _doc()
    assert "传输层" in doc
    assert "httpx" in doc and "Patchright" in doc and "yt-dlp" in doc


def test_doc_has_pitfall_list():
    """要有踩坑清单（改代码前必读）。"""
    doc = _doc()
    assert "踩坑" in doc
    assert "必修" in doc or "必读" in doc or "正确做法" in doc


# =============================================================================
# 关键事实（与代码对齐）
# =============================================================================

def test_doc_says_weibo_needs_browser():
    """**微博必须浏览器** —— 这是唯一在 BROWSER_ONLY 里的平台。

    代码：`BROWSER_ONLY = ("weibo", "wb")`
    原因：微博注册了 Service Worker，httpx 直连一律 ok=-100。
    """
    import inspect

    from app.services.crawler import service as cs

    src = inspect.getsource(cs.CrawlerService._search_via_platforms)
    line = next(
        (ln for ln in src.splitlines() if "BROWSER_ONLY" in ln and "=" in ln), ""
    )
    assert "weibo" in line, "微博应在 BROWSER_ONLY"
    assert "xhs" not in line, "小红书不该在 BROWSER_ONLY（已纯 HTTP）"

    doc = _doc()
    assert "Service Worker" in doc or "service worker" in doc.lower(), (
        "文档应解释**为什么**微博特殊（Service Worker）"
    )


def test_doc_lists_xhs_three_facts():
    """小红书三个实测结论要在文档里（都踩过坑）。"""
    doc = _doc()
    assert "page_size" in doc and "20" in doc, "应写 page_size 只认 20"
    assert "image_formats" in doc, "应写必须带 image_formats"
    assert "xsec_token" in doc, "应写 xsec_token 必需"


def test_doc_mentions_creator_center():
    """要有创作者中心章节（与公开数据的区别）。"""
    doc = _doc()
    assert "创作者中心" in doc
    assert "仅号主" in doc or "只有号主" in doc


def test_doc_distinguishes_download_and_import():
    """要说明「下载」与「导入素材库」是两件事。

    用户踩过：点了"全部下载"却以为素材库会有。
    """
    doc = _doc()
    assert "导入素材库" in doc
    assert "不落盘" in doc or "只存 URL" in doc


# =============================================================================
# 能力矩阵准确性
# =============================================================================

def test_doc_capability_matrix_matches_code():
    """文档里的能力矩阵要与代码一致（抽查关键项）。"""
    from app.services.platforms import create_client

    doc = _doc()

    # 抖音/小红书有 get_self_profile
    for p in ("douyin", "xiaohongshu"):
        c = create_client(p, mode="api", cookie="a1=x")
        assert c is not None and hasattr(c, "get_self_profile"), (
            f"{p} 应有 get_self_profile"
        )

    # B站/番茄 没有
    for p in ("bili", "fanqie"):
        c = create_client(p, mode="api", cookie="a1=x")
        assert c is not None
        assert not hasattr(c, "get_self_profile"), (
            f"{p} 不该有 get_self_profile —— 文档写的是 B站走 /bilibili/* 专有路由"
        )

    # 文档要写明这个差异
    assert "B站「我的数据」是另一条路" in doc or "/bilibili/*" in doc


def test_doc_mentions_cookie_alias_trap():
    """要写域名别名坑（`xhs` → 0 字符，必须 `xiaohongshu`）。"""
    doc = _doc()
    assert "别名" in doc or "netscape_to_header" in doc
