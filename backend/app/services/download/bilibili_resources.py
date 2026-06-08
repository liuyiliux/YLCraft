from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable


def safe_bilibili_filename(value: str, fallback: str = "untitled") -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n]+', "_", (value or "").strip())
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name or fallback)[:120]


async def download_bilibili_sidecar_files(
    *,
    client: Any,
    target_dir: Path,
    base_name: str,
    aid: int = 0,
    cid: int = 0,
    download_subtitles: bool = True,
    download_danmaku: bool = True,
    progress_callback: Callable[[int, str], None] | None = None,
) -> dict[str, Any]:
    def report(progress: int, message: str) -> None:
        if progress_callback:
            progress_callback(progress, message)

    target_dir.mkdir(parents=True, exist_ok=True)
    safe_base = safe_bilibili_filename(base_name)
    subtitle_paths: list[str] = []
    danmaku_path = ""
    subtitle_status = "skipped"
    danmaku_status = "skipped"

    if download_subtitles:
        if aid and cid:
            report(25, "获取字幕列表")
            subtitles = await client.get_subtitles_by_aid_cid(aid=aid, cid=cid)
            if subtitles:
                for subtitle in subtitles:
                    lan = safe_bilibili_filename(
                        subtitle.get("lan") or subtitle.get("lan_doc") or subtitle.get("id") or "subtitle",
                        "subtitle",
                    )
                    subtitle_path = target_dir / f"{safe_base}.{lan}.srt"
                    if not subtitle_path.exists():
                        subtitle_url = subtitle.get("subtitle_url") or ""
                        content = await client.download_subtitle(subtitle_url, "srt") if subtitle_url else ""
                        if content:
                            subtitle_path.write_text(content, encoding="utf-8")
                    if subtitle_path.exists() and subtitle_path.stat().st_size > 0:
                        subtitle_paths.append(str(subtitle_path))
                subtitle_status = "ready" if subtitle_paths else "empty"
            else:
                subtitle_status = "empty"
        else:
            report(25, "缺少 aid/cid，跳过字幕")
            subtitle_status = "missing_ids"

    if download_danmaku:
        if cid:
            report(65, "下载弹幕")
            target_danmaku_path = target_dir / f"{safe_base}.danmaku.json"
            if not target_danmaku_path.exists():
                content = await client.download_danmaku_by_cid(cid=cid, format="json")
                if content:
                    target_danmaku_path.write_text(content, encoding="utf-8")
            if target_danmaku_path.exists() and target_danmaku_path.stat().st_size > 0:
                danmaku_path = str(target_danmaku_path)
                danmaku_status = "ready"
            else:
                danmaku_status = "empty"
        else:
            report(65, "缺少 cid，跳过弹幕")
            danmaku_status = "missing_ids"

    return {
        "subtitle_paths": subtitle_paths,
        "subtitle_status": subtitle_status,
        "danmaku_path": danmaku_path,
        "danmaku_status": danmaku_status,
    }
