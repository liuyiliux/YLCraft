"""详情面板「内容太少」与分页「还有更多点不了」的回归测试。

## 问题①：详情面板内容太少

用户反馈，截图里详情只有标题/作者/一张图。

**排查结果：后端数据是全的**（实测同一条笔记）：

    标题: 把吊带穿成抹胸
    描述: 那就是变成一只小猫咪        ← 正文有
    图片: 3 张（原图）
    互动: 赞2316 评论55 分享131 收藏53
    时间: 2026-05-29 10:59:14
    话题: ['没有小猫这个地球怎么转', '吊带穿搭', ...]

但前端**只渲染了**：标题、作者、平台、原文链接。

**根因**：互动数那段代码的条件是 `platform === 'bili'` ——
非 B 站平台（小红书/抖音）**明明拿到了 likes/comments/collect_count
却不显示**。话题和发布时间也从来没展示过。

## 问题②：「还有更多」点不了

分页器 `total: total`，而平台不给真实总数时 `total` = 本页条数
（10 条）。分页器算下来只有 1 页 → **"下一页"按钮不可点**。
用户看到"还有更多"却翻不了页。

修法：`hasMore` 时给分页器多留一页（`total + pageSize`），
让它渲染出可点的下一页。
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
# 详情面板：互动数 / 话题 / 时间
# =============================================================================

def test_detail_shows_interaction_for_non_bili():
    """**回归**：非 B 站平台也要显示互动数。

    原来只有 `platform === 'bili'` 分支渲染互动，
    小红书/抖音的点赞、收藏、评论、分享**拿到了却不显示** ——
    用户看到详情"没什么内容"（实测反馈）。
    """
    src = _src()
    # 应有一个"非 bili"的互动分支
    assert "detailNote.platform !== 'bili'" in src, (
        "应有非 B 站平台的互动数分支"
    )
    assert "收藏" in src and "分享" in src, "应显示收藏与分享"


def test_detail_shows_collect_count():
    """要显示 `collect_count`（小红书/抖音的收藏数）。

    ⚠️ 字段名是 `collect_count`（不是 `collects`）——
    传错会被 pydantic 静默忽略，前端拿到 undefined。
    """
    src = _src()
    assert "collect_count" in src


def test_detail_shows_tags():
    """要显示话题标签（小红书的 `tags`）。"""
    src = _src()
    assert "话题" in src or "tags" in src, "应展示话题标签"


def test_detail_shows_create_time():
    """要显示发布时间（API 路径能拿到，之前没展示）。"""
    src = _src()
    assert "发布时间" in src or "create_time" in src


def test_interaction_uses_truthy_guard():
    """互动数要"有值才显示"——避免显示一堆 0。

    用 `Boolean(...)` 或 `&&` 做守卫，不要无条件渲染。
    """
    src = _src()
    assert "Boolean(detailNote.likes)" in src or "detailNote.likes &&" in src


# =============================================================================
# 分页：「还有更多」要能翻
# =============================================================================

def test_pagination_adds_page_when_has_more():
    """**回归**：`hasMore` 时给分页器多留一页。

    否则 `total` = 本页条数（10），分页器只有 1 页，
    **"下一页"按钮不可点** —— 用户看到"还有更多"却翻不了页。
    """
    src = _src()
    assert "hasMore ? total + maxResults : total" in src, (
        "hasMore 时应给分页器多留一页，否则翻不了页"
    )


def test_show_total_uses_real_count_when_has_more():
    """`hasMore` 时 showTotal 显示的是**本页条数**，不是 `t`。

    因为 `t` 已经被我们加了 `pageSize`（虚拟页），
    直接显示 `t` 会变成"20 条"（实际只有 10 条），误导用户。
    """
    src = _src()
    # hasMore 分支里应该用 total（真实本页条数）
    assert "`${total} 条（还有更多）`" in src or "${total} 条（还有更多）" in src
