"""YLCraft — 小红书搜索（API 模式）**转发层**

## 历史：这个文件曾经记录了错误的结论（2026-09-29 修正）

原文：

    ⚠️ 2026-09-26 实测结论：**API 模式对小红书搜索已不可用**。
       本文件曾用 `edith.../api/sns/web/v1/search/notes`，实测返回
       `{"code":300011,"msg":"当前账号存在异常…"}`（**本质是缺 X-s/X-t
       签名被风控拒**，不是账号真有问题）。真实端点已迁移到
       `so.xiaohongshu.com/.../v2/search/notes`，但同样要签名，
       且签名函数 `window._webmsxyw` 是混淆 JS、跨域调用实测 406。

**这段话自相矛盾**：它承认 300011 是"缺签名被风控拒"，
却又据此断定"端点迁移了、Python 侧不可用"。

**真相（2026-09-29 实测）**：

    POST https://edith.xiaohongshu.com/api/sns/web/v1/search/notes
    body = {keyword, page, page_size, search_id, sort, note_type}
    → HTTP 200, success=True, data.items[20~21]

**端点没迁移，也一直可用** —— 当时缺的是签名能力，
而我们现在有 `xhshow`（纯 Python 复现）。

所以本文件现在只做**转发**，真实实现在 `search_api.py`。

## ⚠️ 教训

"缺签名" ≠ "端点废弃"。遇到风控拒绝时，
先把"签名/凭证"补齐再下结论 —— 否则会把一个可用端点误判成死的，
并因此绕远路（我们用浏览器 DOM 走了好几天）。
"""

from typing import Any, Dict, List

from ..types import SearchParams, SearchResult

# 真正的端点（**可用**，2026-09-29 实测）
REAL_ENDPOINT = "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes"


async def search_via_api(
    client,
    params: SearchParams,
) -> List[SearchResult]:
    """纯 HTTP 搜索（转发到 `search_api.search_via_api`）。

    保留这个模块名是为了不改动既有调用面（`client.py` 从这里导入）。
    """
    from .search_api import search_via_api as _impl

    return await _impl(client, params)


def parse_search_result(item: Dict[str, Any]) -> SearchResult:
    """解析搜索结果项（转发到 `search_api.parse_item`）。"""
    from .search_api import parse_item

    parsed = parse_item(item)
    if parsed is None:
        raise ValueError("搜索结果项缺少 id 或 note_card")
    return parsed


def parse_count(count_str: Any) -> int:
    """解析数量字符串（如 '1.2万' -> 12000）。"""
    from .search_api import _to_int

    if isinstance(count_str, (int, float)):
        return int(count_str)
    s = str(count_str or "").strip()
    if not s:
        return 0
    try:
        if "万" in s:
            return int(float(s.replace("万", "")) * 10000)
        if "亿" in s:
            return int(float(s.replace("亿", "")) * 100000000)
        if s.lower().endswith("k"):
            return int(float(s[:-1]) * 1000)
        return _to_int(s)
    except (ValueError, TypeError):
        return 0
