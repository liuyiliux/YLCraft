"""Subtitle tools exposed to the Agent Center."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from app.services.agent.registry import register_tool
from app.services.subtitle.service import SUBTITLE_STYLES, SubtitleService

logger = logging.getLogger("ylcraft.agent.tools.subtitle")

_subtitle_service = SubtitleService()


@register_tool(
    name="extract_subtitle",
    description="从本地视频中提取字幕或语音转文字，生成 SRT/ASS 字幕文件。",
    category="subtitle",
    input_schema_note="必须提供本地 video_path；language 默认 zh；style 为字幕样式；output_format 支持 srt/ass；model_size 控制识别模型大小。",
    output_schema_note="返回 subtitle_path、subtitle_id、language、duration、segments_count、output_format。",
    risk_level="costly",
    output_type="subtitle_extract_result",
    cost_hint="会运行语音识别模型并读取视频文件，长视频耗时更高，执行前需要确认。",
)
async def extract_subtitle(
    video_path: str,
    language: str = "zh",
    style: str = "tiktok",
    output_format: str = "srt",
    model_size: str = "medium",
) -> dict:
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
                },
            }
        return {"success": False, "error": result.get("error", "字幕提取失败")}
    except Exception as exc:
        logger.error("extract_subtitle failed: %s", exc)
        return {"success": False, "error": str(exc)}


@register_tool(
    name="get_subtitle_styles",
    description="获取所有可用的字幕样式预设。",
    category="subtitle",
    input_schema_note="无参数。",
    output_schema_note="返回 styles 和 available_styles，可用于 burn_subtitle 或 extract_subtitle 的 style 参数。",
    risk_level="read",
    output_type="subtitle_style_list",
)
async def get_subtitle_styles() -> dict:
    try:
        styles = _subtitle_service.get_styles()
        return {
            "success": True,
            "data": {
                "styles": styles,
                "available_styles": list(SUBTITLE_STYLES.keys()),
            },
        }
    except Exception as exc:
        logger.error("get_subtitle_styles failed: %s", exc)
        return {"success": False, "error": str(exc)}


@register_tool(
    name="burn_subtitle",
    description="把字幕硬烧录到视频中，生成一个带字幕的新视频文件。",
    category="subtitle",
    input_schema_note="必须提供 video_path 和 subtitle_path；output_path 可为空自动生成；style 需来自 get_subtitle_styles。",
    output_schema_note="返回 output_path、video_path、subtitle_path、style；会生成一个新视频文件。",
    risk_level="write",
    output_type="video_file_result",
)
async def burn_subtitle(
    video_path: str,
    subtitle_path: str,
    output_path: Optional[str] = None,
    style: str = "tiktok",
) -> dict:
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
            output_path_obj = video_path_obj.parent / f"{video_path_obj.stem}_subtitled{video_path_obj.suffix}"

        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        is_ass = subtitle_path_obj.suffix.lower() == ".ass"
        escaped = str(subtitle_path_obj).replace(":", "\\:")

        if is_ass:
            vf_filter = f"subtitles='{escaped}'"
        else:
            style_config = SUBTITLE_STYLES.get(style, SUBTITLE_STYLES["tiktok"])
            font_name = style_config.get("font_name", "Microsoft YaHei")
            font_size = style_config.get("font_size", 72)
            primary_color = style_config.get("primary_color", "&H00FFFFFF")
            outline_color = style_config.get("outline_color", "&H00000000")
            outline = style_config.get("outline", 3)
            vf_filter = (
                f"subtitles='{escaped}':"
                f"force_style='FontName={font_name},FontSize={font_size},"
                f"PrimaryColour={primary_color},OutlineColour={outline_color},Outline={outline}'"
            )

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path_obj),
            "-vf",
            vf_filter,
            "-c:a",
            "copy",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
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
            },
        }
    except Exception as exc:
        logger.error("burn_subtitle failed: %s", exc)
        return {"success": False, "error": str(exc)}


logger.info("[subtitle_tools] registered: extract_subtitle, get_subtitle_styles, burn_subtitle")
