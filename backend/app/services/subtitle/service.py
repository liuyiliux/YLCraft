"""
YLCraft — 字幕提取服务
基于 faster-whisper 实现视频语音转录，支持多语言、多格式输出。

参考 NarratoAI 的字幕提取逻辑，增加异步支持和进度回调。
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("ylcraft.subtitle")

# 字幕样式预设（用于 ASS 格式烧录）
SUBTITLE_STYLES = {
    "tiktok": {
        "name": "TikTok 大字",
        "font_name": "Microsoft YaHei",
        "font_size": 72,
        "primary_color": "&H00FFFFFF",      # 白色
        "outline_color": "&H00000000",       # 黑色描边
        "outline": 3,
        "shadow": 1,
        "alignment": 2,                       # 底部居中
        "margin_v": 60,
        "bold": -1,
    },
    "minimal": {
        "name": "Minimal 简约",
        "font_name": "Arial",
        "font_size": 42,
        "primary_color": "&H00FFFFFF",
        "outline_color": "&H80000000",        # 半透明描边
        "outline": 1,
        "shadow": 0,
        "alignment": 2,
        "margin_v": 30,
        "bold": 0,
    },
    "bold": {
        "name": "Bold 粗体",
        "font_name": "Microsoft YaHei",
        "font_size": 80,
        "primary_color": "&H00FFFF00",        # 黄色
        "outline_color": "&H00000000",
        "outline": 4,
        "shadow": 2,
        "alignment": 5,                        # 居中
        "margin_v": 0,
        "bold": -1,
    },
    "cinematic": {
        "name": "Cinematic 电影",
        "font_name": "Arial",
        "font_size": 48,
        "primary_color": "&H00FFFFFF",
        "outline_color": "&HAA000000",
        "outline": 2,
        "shadow": 1,
        "alignment": 2,
        "margin_v": 40,
        "bold": 0,
    },
}


def _format_timestamp_srt(seconds: float) -> str:
    """将秒数转为 SRT 时间戳格式 HH:MM:SS,mmm"""
    td = timedelta(seconds=seconds)
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    ms = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _format_timestamp_ass(seconds: float) -> str:
    """将秒数转为 ASS 时间戳格式 H:MM:SS.cc"""
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    cs = int((seconds - int(seconds)) * 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _segments_to_srt(segments: list) -> str:
    """将 Whisper segments 转为 SRT 字幕内容"""
    lines = []
    for i, seg in enumerate(segments, 1):
        start = _format_timestamp_srt(seg["start"])
        end = _format_timestamp_srt(seg["end"])
        text = seg["text"].strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def _segments_to_ass(segments: list, style: str = "tiktok") -> str:
    """将 Whisper segments 转为 ASS 字幕内容（支持样式）"""
    s = SUBTITLE_STYLES.get(style, SUBTITLE_STYLES["tiktok"])

    header = f"""[Script Info]
Title: YLCraft Subtitle
ScriptType: v4.00+
Collisions: Normal
PlayResX: 1920
PlayResY: 1080
Timer: 100.0000

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{s['font_name']},{s['font_size']},{s['primary_color']},&H000000FF,{s['outline_color']},&H00000000,{s['bold']},0,0,0,100,100,0,0,1,{s['outline']},{s['shadow']},{s['alignment']},10,10,{s['margin_v']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    dialogue_lines = []
    for seg in segments:
        start = _format_timestamp_ass(seg["start"])
        end = _format_timestamp_ass(seg["end"])
        text = seg["text"].strip().replace("\n", "\\N")
        dialogue_lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    return header + "\n".join(dialogue_lines)


def _segments_to_vtt(segments: list) -> str:
    """将 Whisper segments 转为 WebVTT 格式"""
    lines = ["WEBVTT\n"]
    for seg in segments:
        start = _format_timestamp_srt(seg["start"]).replace(",", ".")
        end = _format_timestamp_srt(seg["end"]).replace(",", ".")
        text = seg["text"].strip()
        lines.append(f"{start} --> {end}\n{text}\n")
    return "\n".join(lines)


class SubtitleService:
    """
    字幕提取服务 — 基于 faster-whisper
    """

    _model_cache: dict = {}  # 复用已加载的模型，避免重复加载
    _output_dir: Path = Path("data/subtitles")

    def __init__(self):
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def extract(
        self,
        video_path: Path,
        language: str = "zh",
        model_size: str = "medium",
        output_format: str = "srt",
        word_timestamps: bool = False,
        subtitle_style: str = "tiktok",
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> dict:
        """
        提取视频字幕

        Args:
            video_path:      视频文件路径
            language:        语言代码（zh/en/ja/ko/auto）
            model_size:      Whisper 模型大小（tiny/base/small/medium/large）
            output_format:   输出格式（srt/ass/vtt）
            word_timestamps: 是否输出逐词时间戳
            subtitle_style:  ASS 字幕样式（tiktok/minimal/bold/cinematic）
            on_progress:     进度回调 (progress: float, message: str)

        Returns:
            {
                success: bool,
                subtitle_path: str,    # 字幕文件路径
                language: str,         # 检测到的语言
                duration: float,       # 视频时长
                segments_count: int,   # 片段数量
                error: str             # 错误信息（失败时）
            }
        """
        try:
            if on_progress:
                on_progress(0.05, "正在加载 Whisper 模型...")

            model = await asyncio.to_thread(self._load_model, model_size)

            if on_progress:
                on_progress(0.15, "模型加载完成，开始转录...")

            # 转录（在线程池中执行，避免阻塞）
            lang_param = None if language == "auto" else language
            segments_raw, info = await asyncio.to_thread(
                self._transcribe,
                model,
                str(video_path),
                lang_param,
                word_timestamps,
            )

            if on_progress:
                on_progress(0.85, f"转录完成，共 {len(segments_raw)} 段，正在生成字幕文件...")

            # 转换为统一格式
            segments = [
                {"start": seg.start, "end": seg.end, "text": seg.text}
                for seg in segments_raw
            ]

            # 生成输出文件名
            subtitle_id = uuid.uuid4().hex[:12]
            base_name = Path(video_path).stem
            output_file = self._output_dir / f"{base_name}_{subtitle_id}.{output_format}"

            # 生成字幕内容
            if output_format == "srt":
                content = _segments_to_srt(segments)
            elif output_format == "ass":
                content = _segments_to_ass(segments, style=subtitle_style)
            elif output_format == "vtt":
                content = _segments_to_vtt(segments)
            else:
                content = _segments_to_srt(segments)

            output_file.write_text(content, encoding="utf-8")

            if on_progress:
                on_progress(1.0, "字幕提取完成！")

            return {
                "success": True,
                "subtitle_id": subtitle_id,
                "subtitle_path": str(output_file),
                "language": info.language,
                "duration": info.duration,
                "segments_count": len(segments),
                "output_format": output_format,
            }

        except ImportError:
            logger.error("faster-whisper 未安装，请运行: pip install faster-whisper")
            return {
                "success": False,
                "error": "faster-whisper 未安装，请运行: pip install faster-whisper",
            }
        except Exception as e:
            logger.exception(f"字幕提取失败: {e}")
            return {"success": False, "error": str(e)}

    def _load_model(self, model_size: str):
        """加载（并缓存）Whisper 模型"""
        from faster_whisper import WhisperModel  # type: ignore

        cache_key = model_size
        if cache_key not in self._model_cache:
            logger.info(f"正在加载 Whisper {model_size} 模型...")
            # 优先使用 CUDA，降级到 CPU
            try:
                model = WhisperModel(model_size, device="cuda", compute_type="float16")
                logger.info("使用 CUDA 加速")
            except Exception:
                model = WhisperModel(model_size, device="cpu", compute_type="int8")
                logger.info("使用 CPU 转录")
            self._model_cache[cache_key] = model
            logger.info(f"Whisper {model_size} 模型加载完成")

        return self._model_cache[cache_key]

    def _transcribe(self, model, audio_path: str, language, word_timestamps: bool):
        """执行转录"""
        segments, info = model.transcribe(
            audio_path,
            language=language,
            word_timestamps=word_timestamps,
            vad_filter=True,             # 使用 VAD 过滤静音
            vad_parameters={"min_silence_duration_ms": 500},
        )
        # segments 是生成器，需要消费
        return list(segments), info

    def get_styles(self) -> list[dict]:
        """获取所有可用字幕样式"""
        return [
            {
                "id": key,
                "name": val["name"],
                "font_name": val["font_name"],
                "font_size": val["font_size"],
            }
            for key, val in SUBTITLE_STYLES.items()
        ]

    def get_subtitle_content(self, subtitle_path: str) -> str:
        """读取字幕文件内容"""
        p = Path(subtitle_path)
        if not p.exists():
            raise FileNotFoundError(f"字幕文件不存在: {subtitle_path}")
        return p.read_text(encoding="utf-8")

    def delete_subtitle(self, subtitle_path: str) -> bool:
        """删除字幕文件"""
        p = Path(subtitle_path)
        if p.exists():
            p.unlink()
            return True
        return False


# 全局单例
subtitle_service = SubtitleService()
