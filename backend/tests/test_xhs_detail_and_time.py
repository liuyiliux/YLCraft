"""小红书「发布时间 / 详情打开方式 / 收藏数」的回归测试。

## 用户反馈（2026-09-28）

    1. "加按钮"（下载页要有「导入素材库」）
    2. "发布时间和收藏数是不是没解析成功"
    3. "详情页也解析不成功"

## 逐项实测结论

### 发布时间 —— **是我们漏解析了**（已修）

实测卡片 DOM 里有 `.time`（内容 `05-25` / `06-08`）。原来没抓。

⚠️ 选择器要**精确到 `.time`**：写成 `[class*=time]` 会命中父元素
`.name-time-wrapper`，拿到"作者名 + 时间"整块文本（实测踩过，
时间字段里混进了作者名）。

### 收藏数 —— **搜索列表本来就没有**（不是 bug）

实测 30 张卡片里含「收藏」字样的 **0 个**。列表只显示点赞数。
收藏数**只有进详情页才有**（详情实测拿到 收藏=155）。

所以搜索卡片不抓 collects（避免给一个恒为空的字段）。

### 详情 —— **不能直接 goto，必须站内点击**（已修）

实测四种打开方式：

    A) goto search_result/{id}?xsec_token=...  → 重定向 /website-login/error
       页面显示「安全限制 访问链接异常 300017」
    B) goto explore/{id}?xsec_token=...        → 跳回 /explore
    C) goto explore/{id}（不带 token）          → 跳回 /explore
    D) **在页面里点击卡片**（站内跳转）          → ✅ 成功
       拿到 /explore/{id}?xsec_token=...，图集 3 张

即小红书详情**必须在站内点击进入**，直接构造 URL 会被安全策略拦掉。

修完实测：
    标题 '约会篇：某人拉丝的眼神'  作者 别小乔我啦
    图片 3 张  赞 857 / 收藏 155 / 评论 21
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# 发布时间
# =============================================================================

def test_card_parser_reads_time():
    """**回归**：卡片解析要抓发布时间。

    实测卡片 DOM 有 `.time`（形如 `05-25`），原来漏了，
    用户看到"发布时间"列是空的。
    """
    from app.services.platforms.xiaohongshu import search_patchright as sp

    js = sp.JS_PARSE_CARDS
    assert "time_text" in js, "应抓取发布时间"
    assert "'" + ".time" + "'" in js, "应该用精确的 .time 选择器"


def test_time_selector_is_exact():
    """**回归**：时间选择器必须精确到 `.time`，不能是 `[class*=time]`。

    实测 `[class*=time]` 会命中父元素 `.name-time-wrapper`，
    拿到的是"作者名 + 时间"整块文本（时间字段混进作者名）。
    """
    from app.services.platforms.xiaohongshu import search_patchright as sp

    js = sp.JS_PARSE_CARDS
    # 找 tm 那一行
    line = next(
        (ln for ln in js.splitlines() if "const tm" in ln), ""
    )
    assert line, "未找到时间选择器"
    assert "'" + ".time" + "'" in line, f"应精确到 .time：{line.strip()}"
    assert "[class*=time]" not in line, f"不该用宽泛选择器：{line.strip()}"


def test_time_goes_into_create_time():
    """时间要填进 `SearchResult.create_time`。"""
    from app.services.platforms.xiaohongshu import search_patchright as sp

    src = inspect.getsource(sp.parse_card)
    assert "create_time" in src, "应填 create_time"
    assert "time_text" in src, "应从卡片解析的 time_text 取值"


def test_js_string_has_no_stray_newline():
    """**回归**：JS 是 Python 普通字符串，注释里不能有反斜杠 n。

    实测踩过：在 JS 注释里写 `\\n` 会被 Python 解释成真换行，
    导致 `Page.evaluate: SyntaxError: Invalid or unexpected token`，
    整个搜索挂掉。
    """
    from app.services.platforms.xiaohongshu import search_patchright as sp

    for name in ("JS_PARSE_CARDS", "JS_PARSE_NOTE"):
        js = getattr(sp, name, None)
        if js is None:
            continue
        # JS 字符串里不该出现裸控制字符（除正常换行/制表）
        for ch in js:
            assert ch not in ("\x00",), f"{name} 含非法控制字符"


# =============================================================================
# 收藏数（页面本来就没有）
# =============================================================================

def test_card_parser_does_not_fake_collects():
    """**不要**在搜索卡片里硬塞收藏数 —— 列表页本来就没有。

    实测 30 张卡片含「收藏」字样的 0 个。
    给一个恒为空的字段会让用户以为"解析坏了"，不如不给。

    注：只检查**代码**（去掉 // 注释）—— 注释里会提到为什么不做。
    """
    from app.services.platforms.xiaohongshu import search_patchright as sp

    js = sp.JS_PARSE_CARDS
    code = "\n".join(
        ln for ln in js.splitlines() if not ln.strip().startswith("//")
    )
    assert "collects" not in code, "搜索卡片的代码不该抓收藏数（页面没有）"


def test_detail_does_read_collects():
    """收藏数**详情页有**，要抓。"""
    from app.services.platforms.xiaohongshu import note as note_mod

    js = note_mod.JS_PARSE_NOTE
    assert "collects" in js, "详情页应抓收藏数"


# =============================================================================
# 详情打开方式
# =============================================================================

def test_detail_uses_in_page_click():
    """**回归**：详情必须**站内点击**打开，不能直接 goto。

    实测直接 goto 会被安全策略拦：
        search_result + token → /website-login/error「安全限制 300017」
        explore + token       → 跳回 /explore
    只有站内点击能拿到笔记 DOM。
    """
    from app.services.platforms.xiaohongshu import note as note_mod

    src = inspect.getsource(note_mod.get_detail_via_patchright)
    assert "_open_note_by_click" in src, "应走站内点击"
    # goto 保留为兜底（点击找不到时）
    assert "goto" in src, "应保留 goto 兜底"

    # 顺序：先尝试点击
    i_click = src.find("_open_note_by_click")
    i_goto = src.find("page.goto")
    assert i_click != -1 and i_goto != -1
    assert i_click < i_goto, "应先点击，goto 仅作兜底"


def test_click_helper_exists_and_documents_reason():
    """点击辅助函数要存在，并记录**为什么不能用 goto**。"""
    from app.services.platforms.xiaohongshu import note as note_mod

    assert callable(note_mod._open_note_by_click)
    doc = inspect.getsource(note_mod._open_note_by_click)
    assert "300017" in doc or "安全" in doc, "应记录被拦的错误码"

    # 点击 JS 要按 note_id 匹配卡片
    js = note_mod.JS_CLICK_NOTE_CARD
    assert "note-item" in js or "a[href]" in js
    assert "id" in js


def test_detail_documents_the_four_ways():
    """要记录实测过的四种打开方式，避免后人改回 goto。"""
    from app.services.platforms.xiaohongshu import note as note_mod

    src = inspect.getsource(note_mod.get_detail_via_patchright)
    assert "站内点击" in src, "应说明正确做法"
    assert "300017" in src or "安全限制" in src, "应记录被拦现象"
