"""
Twitter 平台独立解析器 - 参考 yby6-video-parser-skill 实现。
用途：syndication API 作为 yt-dlp + Cookie 主流程失败后的备用方案。
"""
import math
import logging
import httpx
from typing import Optional

logger = logging.getLogger("ylcraft.parser.twitter")


async def parse_twitter_syndication(tweet_id: str) -> dict:
    """
    使用 Twitter syndication API 解析推文（不需要 Cookie）。
    这只是 yt-dlp + 用户配置 Cookie 主流程失败后的备用方案。
    主流程优先使用带完整认证 Cookie 的 yt-dlp，才能解锁登录可见的内容。
    """
    logger.info(f"[twitter.syndication] 备用解析 tweet_id={tweet_id}")

    try:
        token = str((int(tweet_id) / 1e15) * math.pi).replace("0", "").replace(".", "")

        api_url = f"https://cdn.syndication.twimg.com/tweet-result?id={tweet_id}&token={token}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": "https://platform.twitter.com/",
        }

        async with httpx.AsyncClient(timeout=15.0, headers=headers, follow_redirects=True) as client:
            response = await client.get(api_url)
            response.raise_for_status()
            data = response.json()

        if not data:
            return {"parse_method": "twitter_syndication_empty"}

        logger.info(f"[twitter.syndication] API 返回 keys: {list(data.keys())[:20]}")

        user_data = data.get("user", {})
        author_name = user_data.get("name", "")
        author_uid = user_data.get("screen_name", "")
        author_avatar = user_data.get("profile_image_url_https", "")
        title = data.get("text", "") or ""

        video_url = ""
        cover_url = ""
        images = []

        media_details = data.get("mediaDetails", [])
        if media_details:
            for media in media_details:
                media_type = media.get("type", "")
                if media_type in ("video", "animated_gif"):
                    cover_url = media.get("media_url_https", "")
                    video_info = media.get("video_info", {})
                    variants = video_info.get("variants", [])
                    max_bitrate = 0
                    for variant in variants:
                        content_type = variant.get("content_type", "")
                        if content_type != "video/mp4":
                            continue
                        bitrate = variant.get("bitrate", 0)
                        url = variant.get("url", "")
                        if bitrate > max_bitrate or not video_url:
                            max_bitrate = bitrate
                            video_url = url
                    break

        if not video_url:
            top_video_variants = data.get("video", {}).get("variants", [])
            if top_video_variants:
                cover_url = data.get("video", {}).get("poster", "")
                max_bitrate = 0
                for variant in top_video_variants:
                    content_type = variant.get("content_type", "")
                    if content_type != "video/mp4":
                        continue
                    bitrate = variant.get("bitrate", 0)
                    url = variant.get("url", "")
                    if bitrate > max_bitrate or not video_url:
                        max_bitrate = bitrate
                        video_url = url

        if not video_url and media_details:
            for media in media_details:
                if media.get("type") == "photo":
                    image_url = media.get("media_url_https", "")
                    if image_url and image_url not in images:
                        images.append(image_url)
            if images:
                cover_url = images[0]

        if not video_url and not images:
            return {"parse_method": "twitter_syndication_no_media"}

        content_type = "video" if video_url else "image"
        logger.info(f"[twitter.syndication] 成功，video_url={bool(video_url)}, images={len(images)}")
        return {
            "video_url": video_url,
            "cover_url": cover_url,
            "images": images,
            "title": title,
            "author_name": author_name,
            "author_uid": author_uid,
            "author_avatar": author_avatar,
            "content_type": content_type,
            "parse_method": "twitter_syndication",
            "raw": data,
        }

    except Exception as e:
        logger.warning(f"[twitter.syndication] 失败: {e}")
        return {"parse_method": f"twitter_syndication_error:{e}"}
