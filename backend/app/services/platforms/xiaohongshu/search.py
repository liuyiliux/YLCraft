"""
YLCraft — 小红书搜索逻辑（API 模式）

⚠️ 2026-09-26 实测结论：**API 模式对小红书搜索已不可用**。
   本文件曾用 `edith.xiaohongshu.com/api/sns/web/v1/search/notes`，实测返回
   `{"code":300011,"msg":"当前账号存在异常…"}`（本质是缺 X-s/X-t 签名被风控拒，
   不是账号真有问题）。真实端点已迁移到 `so.xiaohongshu.com/api/sns/web/v2/search/notes`，
   但同样要签名，且签名函数 `window._webmsxyw` 是混淆 JS、跨域调用实测 406。

   所以小红书搜索请走 `search_patchright.py`（浏览器打开搜索页读渲染结果）。
   这里保留 `search_via_api` 只是为了不改动既有调用面，并让它**明确报错**——
   原实现把所有失败都吞成 `return []`，用户只会看到"没搜到"，
   属于最费时间的那类假阴性。
"""

from typing import Any, Dict, List, Optional

from ..types import SearchResult, SearchParams, SearchType

# 旧端点，仅作历史记录；不要用于新代码（见模块 docstring）
DEAD_V1_ENDPOINT = "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes"

# 真实端点（需签名，Python 侧不可直接用）
REAL_V2_ENDPOINT = "https://so.xiaohongshu.com/api/sns/web/v2/search/notes"


async def search_via_api(
    client,
    params: SearchParams,
) -> List[SearchResult]:
    """API 模式搜索——**已停用**，调用它必然失败。

    与其静默返回空列表让调用方以为"没搜到"，不如明确抛出可读错误。
    要搜小红书请用 patchright 模式（见模块 docstring）。
    """
    raise RuntimeError(
        "[xhs] 小红书搜索的 API 模式已停用：真实端点迁移到 "
        "so.xiaohongshu.com/api/sns/web/v2/search/notes 且需要 X-s/X-t 签名，"
        "旧端点已返回 code:300011。请改用 patchright 模式"
        "（crawler/service.py 已按平台自动选择）。"
    )


async def search_via_patchright(
    client,
    params: SearchParams,
) -> List[SearchResult]:
    """
    通过 Patchright 搜索（绕过反爬）
    """
    client._log("Patchright mode not yet implemented", "warning")
    # TODO: 实现 Patchright 浏览器自动化
    return []


def parse_search_result(item: Dict[str, Any]) -> SearchResult:
    """
    解析搜索结果项
    """
    note_card = item.get("note_card", {})
    note_id = note_card.get("note_id", "")
    title = note_card.get("display_title", "")
    desc = note_card.get("desc", "")

    # 作者信息
    user = note_card.get("user", {})
    author = user.get("nickname", "")
    author_id = str(user.get("user_id", ""))

    # 封面图
    cover = note_card.get("cover", {}).get("url_default", "")

    # 互动数据
    interact_info = note_card.get("interact_info", {})
    likes = parse_count(interact_info.get("liked_count", "0"))
    comments = parse_count(interact_info.get("comment_count", "0"))
    shares = parse_count(interact_info.get("share_count", "0"))
    collects = parse_count(interact_info.get("collected_count", "0"))

    # 类型
    type_str = note_card.get("type", "normal")  # normal: 图文, video: 视频

    return SearchResult(
        id=note_id,
        title=title,
        author=author,
        author_id=author_id,
        cover=cover,
        url=f"https://www.xiaohongshu.com/explore/{note_id}",
        platform="xiaohongshu",
        type=type_str,
        likes=likes,
        comments=comments,
        shares=shares,
        collects=collects,
        views=0,  # 搜索结果没有浏览数
        desc=desc,
        create_time="",
        raw_data=item,
    )


def parse_count(count_str: str) -> int:
    """
    解析数量字符串（如 '1.2万' -> 12000）
    """
    if not count_str:
        return 0

    count_str = str(count_str).strip()

    try:
        if '万' in count_str:
            return int(float(count_str.replace('万', '')) * 10000)
        elif 'k' in count_str.lower():
            return int(float(count_str.lower().replace('k', '')) * 1000)
        else:
            return int(count_str)
    except (ValueError, AttributeError):
        return 0
