"""
YLCraft — BGM 工具封装

封装 BGMService 为 Agent 可调用的工具
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from app.services.agent.registry import register_tool
from app.services.bgm.service import BGMService, bgm_service

logger = logging.getLogger("ylcraft.agent.tools.bgm")


@register_tool(
    name="list_bgm_tracks",
    description="列出所有可用的 BGM 曲目，支持按风格/情绪过滤和关键词搜索",
    category="bgm"
)
async def list_bgm_tracks(
    genre: Optional[str] = None,
    mood: Optional[str] = None,
    search: Optional[str] = None,
    include_unavailable: bool = True,
) -> dict:
    """列出所有 BGM 曲目"""
    try:
        tracks = bgm_service.list_tracks(
            genre=genre,
            mood=mood,
            search=search,
            include_unavailable=include_unavailable,
        )
        return {
            "success": True,
            "data": {
                "tracks": tracks,
                "total": len(tracks),
                "genres": bgm_service.get_genres(),
                "moods": bgm_service.get_moods(),
            }
        }
    except Exception as e:
        logger.error(f"list_bgm_tracks failed: {e}")
        return {"success": False, "error": str(e)}


@register_tool(
    name="add_bgm_to_video",
    description="添加 BGM 到视频（混音，支持淡入淡出和音量控制）",
    category="bgm"
)
async def add_bgm_to_video(
    video_path: str,
    bgm_track_id: str,
    output_path: Optional[str] = None,
    volume: float = 0.3,
    fade_in: float = 2.0,
    fade_out: float = 2.0,
    loop: bool = True,
) -> dict:
    """添加 BGM 到视频"""
    try:
        video_path_obj = Path(video_path)
        if not video_path_obj.exists():
            return {"success": False, "error": f"视频文件不存在: {video_path}"}

        track = bgm_service.get_track(bgm_track_id)
        if not track:
            return {"success": False, "error": f"BGM 曲目不存在: {bgm_track_id}"}

        bgm_file_path = track.get("file_path")
        if not bgm_file_path or not Path(bgm_file_path).exists():
            return {"success": False, "error": f"BGM 文件不可用: {bgm_file_path}"}

        if output_path:
            output_path_obj = Path(output_path)
        else:
            output_path_obj = video_path_obj.parent / f"{video_path_obj.stem}_with_bgm{video_path_obj.suffix}"

        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        # 获取视频时长
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(video_path_obj)],
                capture_output=True, text=True, timeout=10,
            )
            video_duration = float(result.stdout.strip()) if result.returncode == 0 else 60.0
        except Exception:
            video_duration = 60.0

        # 获取 BGM 时长
        try:
            bgm_duration_result = await bgm_service.get_audio_duration(bgm_file_path)
            bgm_duration = bgm_duration_result if bgm_duration_result > 0 else 120.0
        except Exception:
            bgm_duration = 120.0

        # 构建音频滤镜
        audio_filter_parts = [f"volume={volume}"]
        if fade_in > 0:
            audio_filter_parts.append(f"afade=t=in:ss=0:d={fade_in}")
        if fade_out > 0:
            fade_out_start = max(0, video_duration - fade_out)
            audio_filter_parts.append(f"afade=t=out:st={fade_out_start}:d={fade_out}")
        if loop and bgm_duration < video_duration:
            loop_count = int(video_duration / bgm_duration) + 1
            audio_filter_parts.append(f"aloop=loop={loop_count}:size={int(bgm_duration * 48000)}")
        audio_filter_parts.append(f"atrim=0:{video_duration}")
        audio_filter_parts.append("asetpts=PTS-STARTPTS")
        audio_filter = ",".join(audio_filter_parts)

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path_obj),
            "-i", bgm_file_path,
            "-filter_complex",
            f"[1:a]{audio_filter}[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            str(output_path_obj),
        ]

        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )

        if result.returncode != 0:
            return {"success": False, "error": f"FFmpeg 执行失败: {result.stderr}"}

        return {
            "success": True,
            "data": {
                "output_path": str(output_path_obj),
                "video_path": str(video_path_obj),
                "bgm_track": {"id": track.get("id"), "name": track.get("name"), "artist": track.get("artist")},
                "volume": volume,
                "fade_in": fade_in,
                "fade_out": fade_out,
            }
        }
    except Exception as e:
        logger.error(f"add_bgm_to_video failed: {e}")
        return {"success": False, "error": str(e)}


@register_tool(
    name="upload_bgm",
    description="上传自定义 BGM 到曲库",
    category="bgm"
)
async def upload_bgm(
    file_path: str,
    title: Optional[str] = None,
    artist: str = "",
    genre: str = "other",
    mood: str = "neutral",
) -> dict:
    """上传自定义 BGM"""
    try:
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            return {"success": False, "error": f"音频文件不存在: {file_path}"}

        valid_extensions = {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg"}
        if file_path_obj.suffix.lower() not in valid_extensions:
            return {"success": False, "error": f"不支持的音频格式: {file_path_obj.suffix}"}

        bgm_dir = Path("data/bgm")
        bgm_dir.mkdir(parents=True, exist_ok=True)

        dest_path = bgm_dir / file_path_obj.name
        counter = 1
        while dest_path.exists():
            dest_path = bgm_dir / f"{file_path_obj.stem}_{counter}{file_path_obj.suffix}"
            counter += 1

        shutil.copy2(file_path_obj, dest_path)

        try:
            duration = await bgm_service.get_audio_duration(str(dest_path))
        except Exception:
            duration = 0.0

        track_name = title or file_path_obj.stem
        track = bgm_service.add_track(
            file_path=str(dest_path),
            name=track_name,
            artist=artist,
            genre=genre,
            mood=mood,
            duration=duration,
            license_info="自定义上传",
        )

        return {
            "success": True,
            "data": {
                "track": track,
                "file_path": str(dest_path),
                "message": f"BGM '{track_name}' 上传成功",
            }
        }
    except Exception as e:
        logger.error(f"upload_bgm failed: {e}")
        return {"success": False, "error": str(e)}


logger.info("[bgm_tools] BGM 工具注册完成: list_bgm_tracks, add_bgm_to_video, upload_bgm")
