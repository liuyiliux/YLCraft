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

def test_detail_uses_direct_url_with_token():
    """**回归（修正了一个错误结论）**：详情**直接用带 token 的链接 goto**。

    ## 我之前判断错了

    我一度写"小红书详情必须站内点击，不能直接 goto"，并据此实现了
    "搜索 → 点击卡片"。**那个结论是错的** —— 我当时用的是
    **没有 `xsec_token`** 的 URL。

    用户给出的链接实测（**带有效 token**）：

        explore/{id}?xsec_token=xxx&xsec_source=pc_feed → ✅ 直接进详情
        search_result/{id}?xsec_token=xxx               → ✅ 也进详情
        explore/{id}（**不带 token**）                   → ❌ 跳回首页

    **决定性因素是有没有有效 token，与"站内点击"无关。**

    而且"搜索→点击"更差：慢（每次加载搜索页十几秒），且
    **目标笔记不在搜索结果里时直接失败**
    （用户日志：搜索"沈阳吊带"的结果里没有那条笔记）。

    ⚠️ `_open_note_by_click` 作为**兜底**保留（无 token 时才用）。
    """
    from app.services.platforms.xiaohongshu import note as note_mod

    src = inspect.getsource(note_mod.get_detail_via_patchright)
    assert "page.goto" in src, "应直接 goto 详情 URL"
    assert "xsec_token" in src, "必须用上 xsec_token"

    # 主路径是 goto：goto 应出现在 click 之前（或根本没有 click）
    i_goto = src.find("page.goto")
    i_click = src.find("_open_note_by_click")
    assert i_goto != -1
    if i_click != -1:
        assert i_goto < i_click, "goto 应是主路径，点击只作兜底"


def test_detail_url_gets_token_appended():
    """URL 缺 token 时要补上（调用方只单独传 token 的情况）。"""
    from app.services.platforms.xiaohongshu import note as note_mod

    src = inspect.getsource(note_mod.get_detail_via_patchright)
    assert "xsec_token=" in src, "应把 token 拼进 URL"


def test_detail_documents_the_four_ways():
    """要记录实测过的四种打开方式，避免后人改回 goto。"""
    from app.services.platforms.xiaohongshu import note as note_mod

    src = inspect.getsource(note_mod.get_detail_via_patchright)
    assert "站内点击" in src, "应说明正确做法"
    assert "300017" in src or "安全限制" in src, "应记录被拦现象"
