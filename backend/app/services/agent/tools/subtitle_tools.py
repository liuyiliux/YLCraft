"""
YLCraft — 字幕工具封装

封装 SubtitleService 为 Agent 可调用的工具
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from app.services.agent.registry import register_tool
from app.services.subtitle.service import SubtitleService, SUBTITLE_STYLES

logger = logging.getLogger("ylcraft.agent.tools.subtitle")

_subtitle_service = SubtitleService()


@register_tool(
    name="extract_subtitle",
    description="提取视频字幕（语音转文字），返回 SRT/ASS 文件路径",
    category="subtitle"
)
async def extract_subtitle(
    video_path: str,
    language: str = "zh",
    style: str = "tiktok",
    output_format: str = "srt",
    model_size: str = "medium",
) -> dict:
    """提取视频字幕"""
    try:
        video_path_obj = Path(video_path)
        if not video_path_obj.exists():
            return {"success": False, "error": f"视频文件不存在: {video_path}"}

        result = await _subtitle_service.extract(
            video_path=video_path_obj,
            language=language,
            model_size=model_size,
            output_format=output_format,
            subtitle_style=style,
        )

        if result.get("success"):
            return {
                "success": True,
                "data": {
                    "subtitle_path": result.get("subtitle_path"),
                    "subtitle_id": result.get("subtitle_id"),
                    "language": result.get("language"),
                    "duration": result.get("duration"),
                    "segments_count": result.get("segments_count"),
                    "output_format": result.get("output_format"),
                }
            }
        else:
            return {"success": False, "error": result.get("error", "字幕提取失败")}
    except Exception as e:
        logger.error(f"extract_subtitle failed: {e}")
        return {"success": False, "error": str(e)}


@register_tool(
    name="get_subtitle_styles",
    description="获取所有可用的字幕样式预设",
    category="subtitle"
)
async def get_subtitle_styles() -> dict:
    """获取所有字幕样式预设"""
    try:
        styles = _subtitle_service.get_styles()
        return {
            "success": True,
            "data": {
                "styles": styles,
                "available_styles": list(SUBTITLE_STYLES.keys()),
            }
        }
    except Exception as e:
        logger.error(f"get_subtitle_styles failed: {e}")
        return {"success": False, "error": str(e)}


@register_tool(
    name="burn_subtitle",
    description="将字幕烧录到视频中（硬字幕）",
    category="subtitle"
)
async def burn_subtitle(
    video_path: str,
    subtitle_path: str,
    output_path: Optional[str] = None,
    style: str = "tiktok",
) -> dict:
    """烧录字幕到视频"""
    try:
        import subprocess

        video_path_obj = Path(video_path)
        subtitle_path_obj = Path(subtitle_path)

        if not video_path_obj.exists():
            return {"success": False, "error": f"视频文件不存在: {video_path}"}
        if not subtitle_path_obj.exists():
            return {"success": False, "error": f"字幕文件不存在: {subtitle_path}"}

        if output_path:
            output_path_obj = Path(output_path)
        else:
            suffix = video_path_obj.suffix
            stem = video_path_obj.stem
            output_path_obj = video_path_obj.parent / f"{stem}_subtitled{suffix}"

        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        is_ass = subtitle_path_obj.suffix.lower() == ".ass"

        if is_ass:
            escaped = str(subtitle_path_obj).replace(':', '\\:')
            vf_filter = f"subtitles='{escaped}'"
        else:
            style_config = SUBTITLE_STYLES.get(style, SUBTITLE_STYLES["tiktok"])
            font_name = style_config.get("font_name", "Microsoft YaHei")
            font_size = style_config.get("font_size", 72)
            primary_color = style_config.get("primary_color", "&H00FFFFFF")
            outline_color = style_config.get("outline_color", "&H00000000")
            outline = style_config.get("outline", 3)
            escaped = str(subtitle_path_obj).replace(':', '\\:')
            vf_filter = (
                f"subtitles='{escaped}':"
                f"force_style='FontName={font_name},FontSize={font_size},"
                f"PrimaryColour={primary_color},OutlineColour={outline_color},Outline={outline}'"
            )

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path_obj),
            "-vf", vf_filter,
            "-c:a", "copy",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
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
                "subtitle_path": str(subtitle_path_obj),
                "style": style if not is_ass else "ass_builtin",
            }
        }
    except Exception as e:
        logger.error(f"burn_subtitle failed: {e}")
        return {"success": False, "error": str(e)}


logger.info("[subtitle_tools] 字幕工具注册完成: extract_subtitle, get_subtitle_styles, burn_subtitle")
