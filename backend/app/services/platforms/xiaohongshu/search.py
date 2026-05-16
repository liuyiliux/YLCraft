"""
YLCraft — 小红书搜索逻辑
"""

from typing import Any, Dict, List, Optional

from ..types import SearchResult, SearchParams, SearchType


async def search_via_api(
    client,
    params: SearchParams,
) -> List[SearchResult]:
    """
    通过 API 搜索
    """
    try:
        http_client = client._http_client
        if not http_client:
            await client._init_http_client()
            http_client = client._http_client

        # 构建请求参数
        payload = {
            "keyword": params.keyword,
            "page": 1,
            "page_size": min(params.max_results, 20),
            "search_id": "",
            "filters": {},
            "sort": params.extra.get("sort", "general"),  # general: 综合, time_descending: 最新
        }

        client._log(f"Searching: {params.keyword}")

        response = await http_client.post(
            "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes",
            json=payload,
        )

        if response.status_code != 200:
            client._log(f"Search failed: HTTP {response.status_code}", "error")
            return []

        data = response.json()

        if data.get("code") != 0:
            client._log(f"Search API error: {data.get('msg')}", "error")
            return []

        # 解析结果
        items = data.get("data", {}).get("items", [])
        results = [parse_search_result(item) for item in items[:params.max_results]]

        client._log(f"Found {len(results)} results")
        return results

    except Exception as e:
        client._log(f"Search error: {e}", "error")
        return []


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
