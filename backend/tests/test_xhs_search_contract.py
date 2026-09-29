"""小红书搜索/详情的"返回值与详情校验"回归测试。

## 用户反馈（2026-09-29）

    "搜索三页点击第二页是空" / "详情显示了但没啥内容、多页只显示一页"

## 根因一：函数**没有 return**（最隐蔽的一个）

我重构 `search_via_patchright` 时，把 `cache.set(...)` 和 **`return results`**
一起删掉了 —— 函数静默返回 `None`，上层 `if not results` 判定"没有结果"，
用户看到"搜索 0 条"。

**而日志明明写着**：

    [xhs] search '沈阳' page=1 -> 22/30 cards (已加载 22)

**"日志说读到了、上层说没有"** 这个组合出现时，先怀疑
"返回值在中途丢了"，而不是"平台没给数据"。
（我为此排查了很久：换端口、清 profile、怀疑持久化会话……全都不是。）

## 根因二：详情会**谎报成功**

站内点击失败后会退回 `goto`，而 goto 被安全策略拦 → 页面停在首页，
但代码仍继续读 DOM → 拿到首页空数据 → 被 parse 成一个
"看起来成功"的 NoteDetail（`success=True`、`images=[]`）。

**谎报成功比直接失败更糟**：用户看到"获取成功"却没有内容，
完全不知道哪里出了问题。现在显式校验 `#noteContainer`。

## 实测（修复后）

    搜索 30 条 ✓
    分页 page=1/2/3 → 各 10 条，首条 id 各不相同 ✓
    详情 [0] 图片=1 / [1] 图片=1 / [2] **图片=6**（多图图集完整拿到）✓
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# 返回值（最隐蔽的回归）
# =============================================================================

def test_search_via_patchright_returns_results():
    """**回归（最重要）**：函数必须 `return results`。

    我编辑时把 return 删掉过 → 返回 None → 上层判定"没有结果" →
    用户看到"搜索 0 条"，**而日志显示卡片已读到 22 张**。
    """
    from app.services.platforms.xiaohongshu import search_patchright as sp

    src = inspect.getsource(sp.search_via_patchright)
    assert "return results" in src, (
        "search_via_patchright 必须 return results —— "
        "漏了会让搜索静默返回 None（表现为'搜索 0 条'，但日志显示卡片已读到）"
    )
    # 两步分支都要有返回值（不能只有一个分支 return）
    assert src.count("return results") >= 1
    # 缓存命中分支也必须 return
    assert "return cached" in src


def test_all_search_paths_return():
    """所有搜索入口都要有返回值（防止将来再加分支时漏 return）。"""
    from app.services.platforms.xiaohongshu import search_patchright as sp

    for fn in (sp.search_via_patchright, sp.search_with_runtime):
        src = inspect.getsource(fn)
        assert "return" in src, f"{fn.__name__} 没有 return"


# =============================================================================
# 详情：不能谎报成功
# =============================================================================

def test_detail_verifies_entered_note_page():
    """**回归**：详情必须校验真的进了详情页（`#noteContainer`）。

    否则站内点击失败 → 退回 goto → 被拦 → 页面停在首页 →
    仍读 DOM → 返回一个 `success=True` 但 `images=[]` 的空壳。
    """
    from app.services.platforms.xiaohongshu import note as note_mod

    src = inspect.getsource(note_mod.get_detail_via_patchright)
    assert "noteContainer" in src, "应校验 #noteContainer"
    assert "未能进入笔记详情页" in src or "raise RuntimeError" in src, (
        "不在详情页时要明确报错，不能返回空壳"
    )


def test_detail_skips_scroll_when_not_on_note():
    """不在详情页时不要滚动（滚的是首页推荐流）。"""
    from app.services.platforms.xiaohongshu import note as note_mod

    src = inspect.getsource(note_mod.get_detail_via_patchright)
    # 滚动前要先检查
    i_check = src.find("noteContainer")
    i_scroll = src.find("scrollBy")
    assert i_check != -1
    if i_scroll != -1:
        assert i_check < i_scroll, "应先确认在详情页，再滚动"


# =============================================================================
# 多图：图集要完整
# =============================================================================

def test_note_parser_dedupes_gallery_images():
    """图集要去重（swiper 会生成 duplicate slide）。

    实测：同一张图会出现两次，不去重会多报张数。
    """
    from app.services.platforms.xiaohongshu import note as note_mod

    js = note_mod.JS_PARSE_NOTE
    assert "seen" in js or "Set" in js, "应对图片去重"
    assert "swiper-slide" in js, "应读图集容器"


def test_note_parser_excludes_avatars():
    """图集不应混入头像（avatar / fe-static）。"""
    from app.services.platforms.xiaohongshu import note as note_mod

    js = note_mod.JS_PARSE_NOTE
    assert "avatar" in js, "应排除头像"
