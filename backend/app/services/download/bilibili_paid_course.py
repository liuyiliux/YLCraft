from __future__ import annotations

import asyncio
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import httpx

from app.core.config import ensure_download_path, get_ffmpeg_path
from app.services.download.bilibili_resources import download_bilibili_sidecar_files


def safe_filename(value: str, fallback: str = "untitled") -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n]+', "_", (value or "").strip())
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name or fallback)[:120]


def get_paid_course_dir(season_id: int = 0, course_title: str = "") -> Path:
    prefix = f"ss{season_id}_" if season_id else ""
    course_name = safe_filename(course_title, "unknown_course")
    course_dir = ensure_download_path("bilibili") / "paid_courses" / f"{prefix}{course_name}"
    course_dir.mkdir(parents=True, exist_ok=True)
    (course_dir / ".tmp").mkdir(parents=True, exist_ok=True)
    return course_dir


def write_course_index(
    course_dir: Path,
    *,
    season_id: int = 0,
    course_title: str = "",
    course_cover: str = "",
    course_desc: str = "",
    course_author: str = "",
    ep_count: int = 0,
    update_info: str = "",
    episode: dict[str, Any],
) -> None:
    index_path = course_dir / "course.json"
    data: dict[str, Any] = {
        "platform": "bilibili",
        "type": "paid_course",
        "season_id": season_id,
        "title": course_title,
        "cover": course_cover,
        "desc": course_desc,
        "author": course_author,
        "ep_count": ep_count,
        "update_info": update_info,
        "episodes": [],
        "updated_at": "",
    }
    if index_path.exists():
        try:
            data.update(json.loads(index_path.read_text(encoding="utf-8")))
        except Exception:
            pass

    episodes = data.setdefault("episodes", [])
    existing = next((item for item in episodes if item.get("ep_id") == episode.get("ep_id")), None)
    if existing:
        existing.update(episode)
    else:
        episodes.append(episode)

    episodes.sort(key=lambda item: (item.get("index") or 999999, item.get("ep_id") or 0))
    data["season_id"] = season_id or data.get("season_id", 0)
    data["title"] = course_title or data.get("title", "")
    data["cover"] = course_cover or data.get("cover", "")
    data["desc"] = course_desc or data.get("desc", "")
    data["author"] = course_author or data.get("author", "")
    data["ep_count"] = ep_count or data.get("ep_count", 0)
    data["update_info"] = update_info or data.get("update_info", "")
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def download_bili_stream(url: str, output_path: Path, cookie: str, max_retries: int = 5) -> None:
    base_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.bilibili.com/",
        "Origin": "https://www.bilibili.com",
        "Accept": "*/*",
    }
    if cookie:
        base_headers["Cookie"] = cookie

    output_path.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    retryable_errors = (
        httpx.RemoteProtocolError,
        httpx.ReadError,
        httpx.TimeoutException,
        httpx.TransportError,
    )

    for attempt in range(max_retries + 1):
        existing_size = output_path.stat().st_size if output_path.exists() else 0
        headers = dict(base_headers)
        if existing_size > 0:
            headers["Range"] = f"bytes={existing_size}-"

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=300.0), follow_redirects=True) as http:
                async with http.stream("GET", url, headers=headers) as resp:
                    if resp.status_code == 416 and existing_size > 0:
                        return
                    if existing_size > 0 and resp.status_code == 200:
                        # CDN ignored Range; restart this fragment from the beginning.
                        existing_size = 0
                    resp.raise_for_status()

                    expected_remaining = int(resp.headers.get("content-length") or 0)
                    mode = "ab" if existing_size > 0 and resp.status_code == 206 else "wb"
                    downloaded = 0
                    with output_path.open(mode) as file:
                        async for chunk in resp.aiter_bytes(1024 * 1024):
                            if chunk:
                                file.write(chunk)
                                downloaded += len(chunk)

                    if expected_remaining and downloaded < expected_remaining:
                        raise httpx.RemoteProtocolError(
                            f"incomplete response body (received {downloaded} bytes, expected {expected_remaining})"
                        )
                    return
        except retryable_errors as exc:
            last_error = exc
            if attempt >= max_retries:
                raise
            await asyncio.sleep(min(2 ** attempt, 10))

    if last_error:
        raise last_error


def merge_streams(video_path: Path, audio_path: Path, output_path: Path) -> None:
    result = subprocess.run(
        [
            str(get_ffmpeg_path()),
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-c",
            "copy",
            str(output_path),
        ],
        capture_output=True,
        timeout=900,
    )
    if result.returncode != 0:
        stderr = (result.stderr or b"").decode("utf-8", errors="replace")
        stdout = (result.stdout or b"").decode("utf-8", errors="replace")
        raise RuntimeError(stderr or stdout or "ffmpeg merge failed")


async def download_paid_course_episode(
    *,
    client: Any,
    ep_id: int,
    aid: int = 0,
    cid: int = 0,
    qn: int = 80,
    title: str = "",
    episode_index: int = 0,
    season_id: int = 0,
    course_title: str = "",
    course_cover: str = "",
    course_desc: str = "",
    course_author: str = "",
    ep_count: int = 0,
    update_info: str = "",
    progress_callback: Callable[[int, str], None] | None = None,
) -> Path:
    def report(progress: int, message: str) -> None:
        if progress_callback:
            progress_callback(progress, message)

    report(10, "准备课程目录")
    course_dir = get_paid_course_dir(season_id=season_id, course_title=course_title)
    episode_prefix = f"{episode_index:02d}_" if episode_index else ""
    base_name = safe_filename(f"{episode_prefix}{title}", f"ep_{ep_id}")
    output_path = course_dir / f"{base_name}.mp4"

    write_course_index(
        course_dir,
        season_id=season_id,
        course_title=course_title,
        course_cover=course_cover,
        course_desc=course_desc,
        course_author=course_author,
        ep_count=ep_count,
        update_info=update_info,
        episode={
            "ep_id": ep_id,
            "aid": aid,
            "cid": cid,
            "index": episode_index,
            "title": title,
            "quality": qn,
            "file_path": str(output_path),
            "status": "ready" if output_path.exists() else "downloading",
        },
    )

    if output_path.exists() and output_path.stat().st_size > 0:
        report(100, "章节已存在，已跳过")
        return output_path

    report(20, "获取课程播放地址")
    play = await client.get_paid_course_playurl(ep_id=ep_id, qn=qn)
    video_url = play.get("video_url") if play else ""
    audio_url = play.get("audio_url") if play else ""
    if not video_url:
        raise ValueError("无法获取章节视频下载地址")

    tmp_dir = course_dir / ".tmp"
    video_path = tmp_dir / f"{base_name}.video.m4s"
    audio_path = tmp_dir / f"{base_name}.audio.m4s"

    report(30, "下载视频流")
    await download_bili_stream(video_url, video_path, client.config.cookie)
    if audio_url:
        report(60, "下载音频流")
        await download_bili_stream(audio_url, audio_path, client.config.cookie)
        report(85, "合并音视频")
        await asyncio.to_thread(merge_streams, video_path, audio_path, output_path)
        for temp_path in (video_path, audio_path):
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
    else:
        report(85, "保存视频文件")
        video_path.replace(output_path)

    report(95, "更新课程索引")
    write_course_index(
        course_dir,
        season_id=season_id,
        course_title=course_title,
        course_cover=course_cover,
        course_desc=course_desc,
        course_author=course_author,
        ep_count=ep_count,
        update_info=update_info,
        episode={
            "ep_id": ep_id,
            "aid": aid,
            "cid": cid,
            "index": episode_index,
            "title": title,
            "quality": qn,
            "file_path": str(output_path),
            "status": "ready",
        },
    )
    report(100, "下载完成")
    return output_path


async def download_paid_course_episode_extras(
    *,
    client: Any,
    ep_id: int,
    aid: int = 0,
    cid: int = 0,
    title: str = "",
    episode_index: int = 0,
    season_id: int = 0,
    course_title: str = "",
    course_cover: str = "",
    course_desc: str = "",
    course_author: str = "",
    ep_count: int = 0,
    update_info: str = "",
    progress_callback: Callable[[int, str], None] | None = None,
) -> dict[str, Any]:
    def report(progress: int, message: str) -> None:
        if progress_callback:
            progress_callback(progress, message)

    report(5, "准备课程目录")
    course_dir = get_paid_course_dir(season_id=season_id, course_title=course_title)
    episode_prefix = f"{episode_index:02d}_" if episode_index else ""
    base_name = safe_filename(f"{episode_prefix}{title}", f"ep_{ep_id}")
    output_path = course_dir / f"{base_name}.mp4"

    extras = await download_bilibili_sidecar_files(
        client=client,
        target_dir=course_dir,
        base_name=base_name,
        aid=aid,
        cid=cid,
        progress_callback=progress_callback,
    )

    report(90, "更新课程索引")
    write_course_index(
        course_dir,
        season_id=season_id,
        course_title=course_title,
        course_cover=course_cover,
        course_desc=course_desc,
        course_author=course_author,
        ep_count=ep_count,
        update_info=update_info,
        episode={
            "ep_id": ep_id,
            "aid": aid,
            "cid": cid,
            "index": episode_index,
            "title": title,
            "file_path": str(output_path) if output_path.exists() else "",
            "subtitle_paths": extras["subtitle_paths"],
            "subtitle_status": extras["subtitle_status"],
            "danmaku_path": extras["danmaku_path"],
            "danmaku_status": extras["danmaku_status"],
            "status": "ready" if output_path.exists() else "metadata_ready",
        },
    )
    report(100, "字幕/弹幕补全完成")
    return {
        **extras,
    }


async def register_paid_course_asset(
    *,
    season_id: int = 0,
    course_title: str = "",
    course_cover: str = "",
    course_desc: str = "",
    course_author: str = "",
    ep_count: int = 0,
    update_info: str = "",
) -> str:
    from app.db.database import get_async_session

    course_dir = get_paid_course_dir(season_id=season_id, course_title=course_title)
    index_path = course_dir / "course.json"
    metadata: dict[str, Any] = {
        "platform": "bilibili",
        "type": "paid_course",
        "season_id": season_id,
        "desc": course_desc,
        "author": course_author,
        "ep_count": ep_count,
        "update_info": update_info,
        "course_dir": str(course_dir),
        "index_file": str(index_path),
        "episodes": [],
    }
    if index_path.exists():
        try:
            metadata.update(json.loads(index_path.read_text(encoding="utf-8")))
        except Exception:
            pass
    metadata["desc"] = course_desc or metadata.get("desc", "")
    metadata["author"] = course_author or metadata.get("author", "")
    metadata["ep_count"] = ep_count or metadata.get("ep_count", 0)
    metadata["update_info"] = update_info or metadata.get("update_info", "")

    file_size = sum(path.stat().st_size for path in course_dir.glob("*.mp4") if path.is_file())
    source_url = f"bilibili:paid_course:ss{season_id}" if season_id else f"bilibili:paid_course:{safe_filename(course_title)}"

    async with get_async_session() as session:
        from sqlalchemy import text

        from app.db.models.asset_hub import AssetType
        from app.services.asset_hub import AssetHubFacade
        from app.services.asset_hub.representation_service import AssetRepresentationService
        from app.services.asset_hub.version_service import AssetVersionService

        if not index_path.exists():
            index_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        metadata.update(
            {
                "source": "bilibili_paid_course",
                "source_type": "download",
                "source_url": source_url,
                "cover_url": course_cover or metadata.get("cover", ""),
                "file_size": file_size,
                "status": "READY",
            }
        )

        existing = await session.execute(
            text(
                """
                SELECT id
                FROM asset_nodes
                WHERE metadata_json ->> 'source_url' = :source_url
                LIMIT 1
                """
            ),
            {"source_url": source_url},
        )
        existing_id = existing.scalar_one_or_none()
        if existing_id:
            from app.services.asset_hub.node_service import AssetNodeService

            node_id = str(existing_id)
            await AssetNodeService(session).update(
                node_id=node_id,
                name=course_title or metadata.get("title") or f"B站课程 ss{season_id}",
                thumbnail_url=course_cover or metadata.get("cover", "") or None,
                metadata=metadata,
            )
            version = await AssetVersionService(session).create(
                asset_node_id=node_id,
                params=metadata,
                lineage={"source": "bilibili_paid_course", "source_url": source_url},
            )
            await AssetRepresentationService(session).create(
                asset_version_id=str(version.id),
                file_path=str(index_path),
                mime_type="application/json",
                file_size=index_path.stat().st_size if index_path.exists() else 0,
                format="json",
                extra={
                    "course_dir": str(course_dir),
                    "source_url": source_url,
                    "file_size": file_size,
                },
            )
            return node_id

        result = await AssetHubFacade(session).create_imported_file(
            file_path=str(index_path),
            title=course_title or metadata.get("title") or f"B站课程 ss{season_id}",
            asset_type=AssetType.COLLECTION,
            source="bilibili_paid_course",
            source_url=source_url,
            thumbnail_url=course_cover or metadata.get("cover", ""),
            metadata=metadata,
            lineage={"source": "bilibili_paid_course", "source_url": source_url},
            tags=["B站", "付费课程"],
        )
        return result.node_id
