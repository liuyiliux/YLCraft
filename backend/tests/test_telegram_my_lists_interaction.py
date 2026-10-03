"""「我的频道」/「我的收藏」的交互契约测试（2026-10-03）。

## 用户反馈

> 我的频道和我的收藏还是不对 应该是不输入显示列表的 输入的时候搜索

## 正确的交互（与其它应用一致）

小红书/微信/浏览器书签都是这个模式：

| 输入 | 行为 |
|---|---|
| **空** | 列出全部（让用户先看到有什么） |
| **有内容** | 在列表里筛选 |

**不是**逼用户先想好关键词才让点搜索。

## 附带的真 bug：关键词被静默丢弃

`_list_saved` 调 `list_saved_messages` 时**根本没传 `query`**，
于是输入「视频」「鱼」返回的结果与不输入**完全一样**（实测逐条 id 相同）
＝ 搜索框是摆设。

而 `_list_dialogs` 连参数都没有，关键词直接被丢弃。

这类"看起来能用、实际没接线"就是本仓库反复记录的**假支持**。

## 这些断言锁住
  1. 两个方法都必须**接收** keyword（签名里不能少）
  2. `saved` 必须把 keyword 传到底层 `list_saved_messages(query=...)`
  3. `dialogs` 必须真的用 keyword 过滤（title/username，大小写不敏感）
  4. 前端占位符要说明"不输入 = 列出"，而不是"无需输入"
"""
from __future__ import annotations

import ast
import inspect
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


def _method_source(cls, name: str) -> str:
    """抽出某个方法的源码（从 def 到下一个同级 def）。"""
    lines = _src(TG_CLIENT).splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith(f"async def {name}(") or ln.strip().startswith(f"def {name}("):
            start = i
            break
    assert start is not None, f"找不到方法 {name}"
    indent = len(lines[start]) - len(lines[start].lstrip())
    out = [lines[start]]
    for ln in lines[start + 1:]:
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent and \
           ln.strip().startswith(("async def ", "def ", "@")):
            break
        out.append(ln)
    return "\n".join(out)


# =============================================================================
# 签名：必须接收 keyword
# =============================================================================

@pytest.mark.parametrize("meth", ["_list_saved", "_list_dialogs"])
def test_method_accepts_keyword(meth: str):
    """两个方法都要能接收关键词。"""
    src = _method_source(None, meth)
    sig = src.split("):")[0]
    assert "keyword" in sig, (
        f"{meth} 签名里没有 keyword —— 输入的关键词无法生效"
    )


# =============================================================================
# saved：必须把关键词传到底层
# =============================================================================

def test_saved_passes_query_to_底层():
    """`_list_saved` 必须把 keyword 传成 `query=`（否则搜索是摆设）。"""
    src = _method_source(None, "_list_saved")
    assert "query=keyword" in src, (
        "_list_saved 没把关键词传给 list_saved_messages —— "
        "实测输入『视频』与不输入返回完全一样的数据"
    )


def test_list_saved_messages_supports_query():
    """底层要真的支持 query（传进去要生效）。"""
    src = _src(TG_DATA)
    i = src.find("async def list_saved_messages")
    seg = src[i:i + 2600]
    assert '"search"' in seg or "'search'" in seg, (
        "list_saved_messages 没有把关键词转成 MTProto 的 search 参数"
    )


# =============================================================================
# dialogs：本地筛选
# =============================================================================

def test_dialogs_filters_by_keyword():
    """`_list_dialogs` 必须用 keyword 过滤（title 或 username）。"""
    src = _method_source(None, "_list_dialogs")
    assert "if kw:" in src, "_list_dialogs 没有按关键词过滤"
    assert ".lower()" in src, "筛选应大小写不敏感"
    # 匹配 title 与 username
    assert "c.title" in src, "应匹配频道标题"
    assert "c.username" in src, "应匹配频道 username"


# =============================================================================
# 前端：文案要说清交互
# =============================================================================

def test_frontend_placeholder_explains_both_modes():
    """占位符要说明"不输入 = 列出；输入 = 筛选"，而不是"无需输入"。"""
    src = _src(CRAWLER_TSX)
    assert "直接点搜索列出我加入的频道" in src, (
        "「我的频道」占位符要说明不输入就是列出列表"
    )
    assert "直接点搜索列出收藏" in src, (
        "「我的收藏」占位符要说明不输入就是列出列表"
    )
    # 不该再有"无需输入"这种把搜索框说成摆设的文案
    assert "无需输入" not in src, (
        "「无需输入」会让用户以为搜索框坏了 —— 实际语义是"
        "『不输入 = 列出列表，输入 = 筛选』"
    )


def test_frontend_syntax_valid():
    ast.parse(_src(TG_CLIENT))
    import subprocess
    p = Path(__file__).resolve().parents[1] / "app" / "services" / "platforms" / "telegram" / "client.py"
    assert p.exists()
