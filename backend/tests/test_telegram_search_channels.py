"""Telegram「搜频道」（contacts.Search）的回归测试（2026-10-03）。

## 为什么要有这个功能

用户在「频道消息」tab 输中文必然失败 —— 那是**路径不同**，不是 bug：

| 操作 | 输入 | 走的路 | 支持中文？ |
|---|---|---|---|
| 搜频道 | 频道**标题**（中文） | `contacts.Search` | ✅ |
| 频道消息 | 频道 **username** | `t.me/s/<username>` 公开预览 | ❌ 只认 username |

客户端里能用中文搜到频道，是因为它按**标题**匹配，
走的是 `contacts.Search` —— 之前项目**没有实现这条**，
于是「频道消息」成了唯一入口，输中文必然报错。

实测（2026-10-03，真实 MTProto 会话）：

    搜「沈阳」→ 2 条，均为中文标题频道
        长春会馆/ktv/大连/沈阳/哈尔滨/东北频道
        沈阳外围【猫猫】

## ⚠️ 与 `channels.SearchPosts` 的区别（不要混）

真正"搜所有公开频道的**内容**"要 `channels.SearchPosts`，
它需要 **Premium 且按 Stars 计费** —— 本项目**不做**（过度承诺）。

本功能搜的是**频道实体**（名字/标题），不搜内容、不收费。

## 这些断言锁住
  1. `contacts.SearchRequest` 必须带 `broadcasts=True`（只要频道，不要私聊用户）
  2. 必须有独立的 search_type（不能与「频道消息」混）
  3. `defaultSearchType` 应是 `find`（先搜频道是更常见的入口）
  4. 不得引入 `channels.SearchPosts`（要 Premium + 计费）
  5. 空关键词要给出可操作提示（而不是静默返回空）
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

TG_CLIENT = (Path(__file__).resolve().parents[1]
             / "app" / "services" / "platforms" / "telegram" / "client.py")
TG_DATA = (Path(__file__).resolve().parents[1]
           / "app" / "services" / "platforms" / "telegram" / "mtproto_data.py")
CRAWLER_TSX = (Path(__file__).resolve().parents[2]
               / "frontend" / "src" / "pages" / "crawler" / "index.tsx")


def _src(p: Path) -> str:
    if not p.exists():
        pytest.skip(f"{p.name} not found")
    return p.read_text(encoding="utf-8", errors="ignore")


def _method(name: str) -> str:
    """从 client.py 抽出方法体。"""
    lines = _src(TG_CLIENT).splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith(f"async def {name}(") or ln.strip().startswith(f"def {name}("):
            start = i
            break
    assert start is not None, f"找不到 {name}"
    indent = len(lines[start]) - len(lines[start].lstrip())
    out = [lines[start]]
    for ln in lines[start + 1:]:
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent and \
           ln.strip().startswith(("async def ", "def ", "@")):
            break
        out.append(ln)
    return "\n".join(out)


# =============================================================================
# 后端：contacts.Search
# =============================================================================

def test_search_channels_exists():
    assert "async def search_channels" in _src(TG_DATA)


def test_uses_contacts_search():
    src = _src(TG_DATA)
    i = src.find("async def search_channels")
    seg = src[i:i + 2200]
    assert "SearchRequest" in seg, "必须用 contacts.Search（客户端同款路径）"
    assert "contacts" in seg, "必须从 telethon.tl.functions.contacts 导入"


def test_broadcasts_true():
    """`broadcasts=True` = 只要频道/超级群，不要私聊用户。

    ⚠️ 断言必须落到**实参**上：源码里写的是
        `q=kw, limit=..., broadcasts=True,`（带换行），
    只查子串 `"broadcasts"` 会漏掉 `=True` 被删掉的情况
    （第一版就这样被变异测试放过了）。
    """
    import re
    src = _src(TG_DATA)
    i = src.find("async def search_channels")
    seg = _code_only(src[i:i + 2400])
    assert re.search(r"broadcasts\s*=\s*True", seg), (
        "必须限定 broadcasts=True —— 否则会搜出一堆私聊用户"
    )


def _code_only(src: str) -> str:
    """去掉注释与 docstring —— 否则我写的说明文字会让断言误报。

    （第一版就栽在 `SearchPosts` 上：它只出现在**注释**里，
      而那条注释恰恰是在解释"我们为什么不用它"。）
    """
    lines = [ln for ln in src.splitlines() if not ln.strip().startswith("#")]
    code = "\n".join(lines)
    parts = code.split('"""')
    return "".join(parts[0::2]) if len(parts) > 1 else code


def test_does_not_use_premium_api():
    """`channels.SearchPosts` 要 Premium + Stars 计费，本项目**不做**。

    ⚠️ 必须去掉注释再查 —— 解释"为什么不用它"的注释里就有这个类名。
    """
    for p in (TG_CLIENT, TG_DATA):
        assert "SearchPosts" not in _code_only(_src(p)), (
            "引入了 channels.SearchPosts —— 它需要 Premium 且按 Stars 计费，"
            "属于本项目明确不做的过度承诺"
        )


def test_empty_keyword_gives_actionable_error():
    """空关键词要给出可操作提示，不是静默返回空列表。"""
    seg = _method("_search_channel_names")
    assert "请输入" in seg, "空关键词应给出提示"
    # 提示要说清"搜的是频道本身，不是内容"
    assert "频道" in seg


def test_client_dispatches_find():
    seg = _method("search")
    # 分派写成 `st in ("find", "find_channel", ...)`，不能只匹配 `== "find"`
    assert '"find"' in seg, "必须按 search_type=find 分派到搜频道"
    assert "_search_channel_names" in seg


# =============================================================================
# 前端
# =============================================================================

def test_frontend_has_find_tab():
    src = _src(CRAWLER_TSX)
    assert "value: 'find'" in src, "缺「搜频道」tab"
    assert "搜频道" in src, "tab 要有中文标签"


def test_frontend_default_is_find():
    """默认落在「搜频道」—— 它是更常用的入口（用户只想搜点什么）。

    ⚠️ 必须锚到 `PLATFORM_SEARCH_CONFIG` 里的那个 `telegram` ——
    文件里另有一个 `telegram: {}`（别的映射表），按 `  telegram: {`
    首个匹配会取错对象（第一版就因此误报）。
    """
    src = _src(CRAWLER_TSX)
    i = src.find("const PLATFORM_SEARCH_CONFIG")
    seg = src[i:]
    j = seg.find("\n  telegram: {")
    assert j > 0, "找不到 PLATFORM_SEARCH_CONFIG 里的 telegram"
    body = seg[j:j + 2600]
    assert "defaultSearchType: 'find'" in body, (
        "Telegram 默认 tab 应是 find（搜频道），"
        "否则用户一进来看到的是只认 username 的『频道消息』，输中文必失败"
    )


def test_find_and_channel_are_separate_tabs():
    """两个 tab 必须都在且语义不同（一个是搜标题，一个是读消息）。"""
    src = _src(CRAWLER_TSX)
    assert "value: 'find'" in src and "value: 'channel'" in src
    assert "label: '频道消息'" in src


def test_channel_placeholder_says_username():
    """「频道消息」占位符要说清只认 username（避免用户输中文）。"""
    src = _src(CRAWLER_TSX)
    assert "频道 username，如 durov" in src, (
        "「频道消息」占位符应写明只认 username —— 这是用户输中文失败的主因"
    )


def test_syntax_valid():
    ast.parse(_src(TG_CLIENT))
    ast.parse(_src(TG_DATA))
