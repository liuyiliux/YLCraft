"""游标翻页与 `search_type` 静默降级的回归测试（2026-10-03）。

## 三个真实 bug（都属于"假支持"：看起来能用，实际走错路径）

### Bug 1：`SearchParams.from_string` 把未知 search_type 降级成 NOTE

```python
try:
    st = SearchType(search_type_str)
except ValueError:
    st = SearchType.NOTE      # ← 静默改写
```

而 Telegram 的三个数据源**都不在 `SearchType` 枚举里**：
`channel` / `dialogs` / `saved` / `joined`。

于是 `search_type="saved"` 被悄悄改成 `NOTE`，
`TelegramClient.search` 走默认分支 `_search_channel("")` →
报「请填写频道 username」——用户看到的是**"我的收藏要填频道名"**。

### Bug 2：缓存键漏了游标

`dialogs` / `saved` 用 MTProto 游标 `offset_id` 翻页（不用页码），
但 `cache.make_key()` 只有 `page` 没有游标 → "首次"和"下一页"算出
**同一个键** → 第二次直接命中首次缓存 → 实测两页返回**完全一样的 10 条**。

### Bug 3：游标取了第一条

`offset_id` 语义是"**从这条开始**往前（更旧的）"，所以传**第一条**
会把它自己**也包含进来**。实测：

    首批 [109393, 109377, 109376, 109375, 109374]
    传 109393 → [109377, 109376, ...]   重叠 4
    传 109374 → [109373, 109372, ...]   重叠 0  ✅

必须取**本页最后一条**。

## 这些断言锁住

  1. 未知 `search_type` 不得被静默改写
  2. 缓存键必须含游标
  3. 游标必须是**最后一条**
  4. 前端必须用后端回的 `next_cursor`，不能自己取
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.services.platforms.cache import get_search_cache
from app.services.platforms.types import SearchParams, SearchType

ROOT = Path(__file__).resolve().parents[1] / "app" / "services" / "platforms"
TYPES = ROOT / "types.py"
CACHE = ROOT / "cache.py"
INIT = ROOT / "__init__.py"
TG_CLIENT = ROOT / "telegram" / "client.py"
TG_DATA = ROOT / "telegram" / "mtproto_data.py"
API = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "crawler.py"
CRAWLER_TSX = (Path(__file__).resolve().parents[2]
               / "frontend" / "src" / "pages" / "crawler" / "index.tsx")


def _src(p: Path) -> str:
    if not p.exists():
        pytest.skip(f"{p.name} not found")
    return p.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# Bug 1：未知 search_type 被静默降级
# =============================================================================

@pytest.mark.parametrize("st", ["saved", "dialogs", "channels", "channel", "joined"])
def test_custom_search_type_not_downgraded(st: str):
    """Telegram 的数据源名不在枚举里，**不能**被改写成 NOTE。"""
    p = SearchParams.from_string(keyword="", search_type_str=st)
    got = getattr(p.search_type, "value", p.search_type)
    assert got == st, (
        f"search_type={st!r} 被改写成 {got!r} —— "
        f"平台会走错分支（实测 saved 被改成 note 后报『请填写频道 username』）"
    )


def test_known_enum_still_works():
    """正常枚举值不受影响（不能为了修 Telegram 把别的平台弄坏）。"""
    p = SearchParams.from_string(keyword="猫", search_type_str="video")
    assert p.search_type == SearchType.VIDEO


def test_no_silent_note_fallback_in_source():
    """源码里不得再有 `except ValueError: st = SearchType.NOTE` 这种**降级**。

    ⚠️ 只查字符串存在是**错的**（第一版就这样误报）——
    现在的实现是 `st = search_type_str or SearchType.NOTE`，
    那个 `SearchType.NOTE` 只是**空串兜底**（`search_type_str=""` 时），
    不是把未知值改写成 NOTE。

    所以这里查的是：**降级赋值**这个形态（右边只有一个枚举成员），
    而不是"文件里有没有出现过 SearchType.NOTE"。
    """
    src = _src(TYPES)
    i = src.find("def from_string")
    j = src.find("\ndef ", i + 10)
    body = src[i:j if j > 0 else i + 1600]
    code_lines = [ln for ln in body.splitlines() if not ln.strip().startswith("#")]
    code = "\n".join(code_lines)
    parts = code.split('"""')
    code_no_doc = "".join(parts[0::2]) if len(parts) > 1 else code

    # 降级形态：赋值右边**只有** SearchType.NONE（没有任何"或原值"的兜底）
    import re
    m = re.search(r"st\s*=\s*SearchType\.NOTE\s*$", code_no_doc, re.M)
    assert not m, (
        "又有『未知值直接降级成 NOTE』的赋值 —— "
        "平台的自定义 search_type 会被改写，走错分支"
    )
    # 正确形态应保留原值
    assert "search_type_str" in code_no_doc, (
        "降级分支必须保留原值（search_type_str），否则平台分派会失效"
    )


# =============================================================================
# Bug 2：缓存键必须含游标
# =============================================================================

def test_cache_key_differs_by_cursor():
    """不同游标必须算出**不同**的缓存键（否则翻页命中首次缓存 = 假翻页）。"""
    c = get_search_cache()
    common = dict(platform="telegram", keyword="", page=1, size=10,
                  search_type="saved", conn_id="", sort_by="")
    k1 = c.make_key(**common)
    k2 = c.make_key(**common, extra="cur109369")
    k3 = c.make_key(**common, extra="cur109358")
    assert k1 != k2, "游标没有进缓存键 —— 翻页会拿到首次的缓存"
    assert k2 != k3, "不同游标算出同一个键"


def test_make_key_accepts_extra():
    import inspect
    sig = inspect.signature(get_search_cache().make_key)
    assert "extra" in sig.parameters, "make_key 没有 extra 参数（游标无处安放）"


def test_search_entry_passes_cursor_into_cache_key():
    """共享入口必须把游标塞进缓存键。"""
    src = _src(INIT)
    i = src.find("cache_key = cache.make_key")
    seg = src[i:i + 700]
    assert "extra=" in seg, "缓存键没带游标 —— Telegram 的翻页会拿到重复数据"


# =============================================================================
# Bug 3：游标取最后一条
# =============================================================================

def test_api_returns_cursor_from_last_item():
    """API 的 `next_cursor` 必须取**最后一条**的 cursor_id。

    ⚠️ 不能全文件搜 `next_cursor` —— 那会先命中 `SearchResponse` 的字段定义
    （第一版因此误报），必须锚到**真正计算它的那段**。
    """
    src = _src(API)
    # 锚点：真正从结果里取游标的代码（含 cands）
    i = src.find("cands = [")
    if i < 0:
        i = src.find("next_cursor = str(")
    assert i > 0, "找不到计算 next_cursor 的代码"
    seg = src[max(0, i - 400):i + 400]
    assert "[-1]" in seg, (
        "游标必须取**最后一条** —— 传第一条会把它自己也包进来（实测重叠 4 条）"
    )


def test_tg_client_exposes_cursor_per_item():
    src = _src(TG_CLIENT)
    i = src.find("async def _list_saved")
    seg = src[i:i + 2200]
    assert 'cursor_id' in seg, "收藏项必须带 cursor_id（前端要拿它翻页）"
    assert "offset_id=cursor" in seg or "offset_id" in seg, (
        "必须把游标传给 list_saved_messages"
    )


def test_list_saved_supports_offset_id():
    """收藏夹读取要支持 offset_id（MTProto 的『取更旧的』）。"""
    src = _src(TG_DATA)
    i = src.find("async def list_saved_messages")
    seg = src[i:i + 2600]
    assert "offset_id" in seg, "list_saved_messages 不支持 offset_id —— 无法翻页"
    ast.parse(src)


def test_saved_limit_equals_want():
    """取数条数必须**正好等于**返回条数。

    多取再截断会让游标"回退"：被丢掉的那批下次又被取回来（实测重叠 9 条）。
    """
    src = _src(TG_CLIENT)
    i = src.find("async def _list_saved")
    seg = src[i:i + 2000]
    assert "limit=max(want, 20)" not in seg, (
        "取了 20 条只返回 10 条 —— 被丢掉的那 10 条下次会被重新取回（假翻页）"
    )
    assert "limit=want" in seg, "取数条数应正好等于 want"


# =============================================================================
# 前端
# =============================================================================

def test_frontend_uses_next_cursor_from_backend():
    """前端必须用后端回的 `next_cursor`，不能自己从结果里取。"""
    src = _src(CRAWLER_TSX)
    assert "nextCursor" in src, "前端没有游标状态"
    assert "next_cursor" in src, "前端没读后端返回的 next_cursor"
    # 追加而不是替换
    assert "appendMode" in src, "「加载更多」应**追加**结果，而不是替换已有列表"
    assert "offset_id" in src, "游标要作为 filters.offset_id 回传"


def test_frontend_shows_load_more_for_cursor_tabs():
    src = _src(CRAWLER_TSX)
    assert "nextCursor" in src
    # 按钮出现的条件要包含 nextCursor（游标型），不能只有 single
    i = src.find("nextCursor) && (")
    assert i > 0, "「加载更多」按钮应同时支持游标型平台（不只是 single）"
