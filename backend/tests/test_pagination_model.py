"""翻页模型（paged / single）的回归测试（2026-10-03）。

## 为什么需要这个模型

**不是所有平台都支持翻页。** 实测（每页 20 条、连翻 4 页、关键词「沈阳」）：

    平台      p1  p2  p3  p4  累计唯一  结论
    bili      20  20  20  20   77      PAGED（total=1000 真实总数）
    weibo     20  17  20  20   52      PAGED
    kuaishou  20  20  20  20   65      PAGED
    twitter   20  20  20  20   77      PAGED
    youtube   20  20  20  20   74      PAGED
    douyin     0   0   0   0    0      SINGLE（offset>0 服务端返空）

所以前端**不能一套分页器打天下**：抖音点"第 2 页"必然失败，
必须换成「加载更多」。模型声明在 `platforms/<平台>/meta.py`（单一事实来源），
API 通过 `pagination` 字段透出，前端不自己判断（判断了会和后端漂移）。

## 这些断言锁住
  1. 模型只能取 paged/single 两种值（拼错会静默退化成默认）
  2. 单页型平台必须声明 `single_page_max`（前端要显示"单次上限"）
  3. 未知平台按 paged 处理（保守：多一个分页器好过退化成加载更多）
  4. 别名（dy）必须能查到同一个模型
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.services.platforms.meta import (
    PAGED,
    PAGINATION_MODELS,
    SINGLE,
    all_metas,
    get_meta,
    pagination_info,
    single_page_platforms,
    supports_pagination,
)

PLATFORMS_DIR = Path(__file__).resolve().parents[1] / "app" / "services" / "platforms"


# =============================================================================
# 模型的取值合法性
# =============================================================================

def test_only_two_models():
    assert PAGINATION_MODELS == frozenset({PAGED, SINGLE})
    assert PAGED == "paged" and SINGLE == "single"


@pytest.mark.parametrize("m", all_metas(), ids=lambda m: m.name)
def test_meta_pagination_value_valid(m):
    """每个平台的 pagination 必须是合法值（拼错会静默走默认）。"""
    assert m.pagination in PAGINATION_MODELS, (
        f"{m.name} 的 pagination={m.pagination!r} 不合法"
    )


@pytest.mark.parametrize("m", all_metas(), ids=lambda m: m.name)
def test_single_page_model_declares_limit(m):
    """声明 single 的平台必须给出单次上限（前端要显示"单次上限 N 条"）。"""
    if m.pagination == SINGLE:
        assert m.single_page_max > 0, (
            f"{m.name} 声明为单页型但没给 single_page_max —— "
            f"前端无法显示单次上限，只能含糊说'没有更多'"
        )
    else:
        # paged 平台不该有多余的 single_page_max（避免误用）
        assert m.single_page_max == 0, (
            f"{m.name} 是分页型却声明了 single_page_max={m.single_page_max}"
        )


# =============================================================================
# 查询 API
# =============================================================================

def test_douyin_is_single():
    """抖音实测单页型（2026-10-03 复测三次：offset>0 始终返空）。"""
    assert get_meta("douyin").pagination == SINGLE
    assert supports_pagination("douyin") is False
    assert "douyin" in single_page_platforms()


def test_douyin_alias_same_model():
    """别名 `dy` 必须查到同一个模型（前端用 `dy` 也能拿到）。"""
    assert get_meta("dy").pagination == SINGLE
    assert supports_pagination("dy") is False


@pytest.mark.parametrize("pf", ["bili", "weibo", "kuaishou", "twitter", "youtube"])
def test_measured_paged_platforms(pf: str):
    """实测能翻 4 页的平台必须声明 paged。"""
    assert supports_pagination(pf) is True, f"{pf} 实测支持翻页，不该是单页型"


def test_unknown_platform_defaults_to_paged():
    """未知平台保守按 paged —— 猜错的后果只是多一个分页器。"""
    assert supports_pagination("no_such_platform") is True
    assert pagination_info("no_such_platform") == {"model": PAGED, "single_page_max": 0}


def test_pagination_info_shape():
    """API 透出的结构固定（前端按 model 分支，不看别的字段）。"""
    info = pagination_info("douyin")
    assert set(info) == {"model", "single_page_max"}
    assert info["model"] == SINGLE
    assert info["single_page_max"] == 18  # 实测 17~18


# =============================================================================
# 实测日期必须写在声明里（平台行为会变）
# =============================================================================

def test_douyin_meta_documents_measurement_date():
    """断言"平台不支持翻页"必须带实测日期。

    抖音 09-27 还能翻页、09-28 就不能、10-03 复测仍不能。
    没写日期的话，下一个维护者会当成永久事实。
    """
    f = PLATFORMS_DIR / "douyin" / "meta.py"
    if not f.exists():
        pytest.skip("douyin/meta.py not found")
    src = f.read_text(encoding="utf-8")
    import re
    assert re.search(r"20\d{2}-\d{2}-\d{2}", src), (
        "douyin/meta.py 断言了单页型但没写实测日期 —— 平台行为会变"
    )


# =============================================================================
# API 层透出
# =============================================================================

def test_search_response_exposes_pagination():
    """`SearchResponse` 必须带 pagination 字段（前端靠它选分页器）。"""
    from app.api.v1.crawler import SearchResponse
    assert "pagination" in SearchResponse.model_fields
    r = SearchResponse(success=True, pagination={"model": SINGLE, "single_page_max": 18})
    assert r.pagination["model"] == SINGLE


def test_crawler_api_passes_pagination():
    """API 层必须真的调用 pagination_info 填这个字段。"""
    f = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "crawler.py"
    src = f.read_text(encoding="utf-8")
    assert "pagination=pagination_info(" in src, (
        "SearchResponse(pagination=...) 没传值 —— 前端永远拿不到翻页模型"
    )


# =============================================================================
# 前端：必须按模型切换分页器 / 加载更多
# =============================================================================

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "crawler" / "index.tsx"


def test_frontend_switches_pagination_by_model():
    """前端按 model 切换：single 关闭页码分页器，改用「加载更多」。"""
    if not FRONTEND.exists():
        pytest.skip("crawler page not found")
    src = FRONTEND.read_text(encoding="utf-8", errors="ignore")
    assert "paginationModel" in src, "前端没有翻页模型状态"
    assert "pagination={paginationModel === 'single' ? false" in src or \
           "paginationModel === 'single' ? false" in src, (
        "单页型平台必须关闭页码分页器（抖音点第2页必然失败）"
    )
    assert "loadMore" in src, "缺少「加载更多」处理"
    assert "setPaginationModel" in src, "前端没有接收后端给的翻页模型"
