"""
YLCraft — 小红书笔记详情逻辑
"""

from typing import Any, Dict, List, Optional

from ..types import NoteDetail


async def get_detail_via_api(
    client,
    item_id: str,
) -> Optional[NoteDetail]:
    """
    通过 API 获取笔记详情
    """
    try:
        http_client = client._http_client
        if not http_client:
            await client._init_http_client()
            http_client = client._http_client

        payload = {
            "source_note_id": item_id,
        }

        client._log(f"Getting detail: {item_id}")

        response = await http_client.post(
            "https://edith.xiaohongshu.com/api/sns/web/v1/feed",
            json=payload,
        )

        if response.status_code != 200:
            client._log(f"Get detail failed: HTTP {response.status_code}", "error")
            return None

        data = response.json()

        if data.get("code") != 0:
            client._log(f"Get detail API error: {data.get('msg')}", "error")
            return None

        # 解析详情
        items = data.get("data", {}).get("items", [])
        if not items:
            client._log(f"Note not found: {item_id}", "warning")
            return None

        detail = parse_note_detail(items[0])
        return detail

    except Exception as e:
        client._log(f"Get detail error: {e}", "error")
        return None


async def get_detail_via_patchright(
    client,
    item_id: str,
) -> Optional[NoteDetail]:
    """
    通过 Patchright 获取笔记详情（绕过反爬）
    """
    client._log("Patchright mode not yet implemented", "warning")
    # TODO: 实现 Patchright 浏览器自动化
    return None


def parse_note_detail(data: Dict[str, Any]) -> NoteDetail:
    """
    解析笔记详情
    """
    note_card = data.get("note_card", {})
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
    type_str = note_card.get("type", "normal")

    # 图片列表
    images = []
    image_list = note_card.get("image_list", [])
    for img in image_list:
        url = img.get("url_default", "")
        if url:
            images.append(url)

    # 视频URL
    video_url = ""
    video_info = note_card.get("video", {})
    if video_info:
        video_url = video_info.get("url", "")

    return NoteDetail(
        id=note_id,
        title=title,
        desc=desc,
        author=author,
        author_id=author_id,
        platform="xiaohongshu",
        type=type_str,
        images=images,
        video=video_url,
        video_cover=cover,
        likes=likes,
        comments=comments,
        shares=shares,
        collects=collects,
        views=0,
        tags=[],
        create_time="",
        location=None,
        comments_list=[],
        raw_data=data,
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
