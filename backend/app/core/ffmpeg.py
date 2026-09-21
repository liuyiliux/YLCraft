"""
YLCraft — FFmpeg 视频处理服务

提供视频剪辑、合并、字幕、转码等核心功能。
参考 CutClaw render_video.py 的实现。

本模块是视频处理基础设施，位于 core/ 目录。
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ylcraft.core.ffmpeg")


class FFmpegService:
    """FFmpeg 视频处理服务"""

    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        self.ffmpeg = ffmpeg_path
        self.ffprobe = ffprobe_path

    async def get_video_info(self, video_path: Path) -> dict:
        """
        获取视频信息（时长、分辨率、帧率等）

        Args:
            video_path: 视频文件路径

        Returns:
            dict: 视频信息
        """
        cmd = [
            self.ffprobe, "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration,r_frame_rate,codec_name",
            "-show_entries", "format=duration,size",
            "-of", "json",
            str(video_path)
        ]

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                raise RuntimeError(f"ffprobe failed: {result.stderr}")

            data = json.loads(result.stdout)

            stream = data.get("streams", [{}])[0]
            format_info = data.get("format", {})

            fps_str = stream.get("r_frame_rate", "30/1")
            if "/" in fps_str:
                num, den = map(int, fps_str.split("/"))
                fps = num / den if den > 0 else 30
            else:
                fps = float(fps_str)

            return {
                "width": int(stream.get("width", 0)),
                "height": int(stream.get("height", 0)),
                "duration": float(stream.get("duration") or format_info.get("duration", 0)),
                "fps": fps,
                "codec": stream.get("codec_name", "h264"),
                "file_size": int(format_info.get("size", 0)),
            }

        except Exception as e:
            logger.error(f"Failed to get video info: {e}")
            raise

    async def concat_videos(
        self,
        video_paths: list[Path],
        output_path: Path,
        reencode: bool = False,
    ) -> Path:
        """
        合并多个视频文件。

        Args:
            video_paths: 视频文件列表
            output_path: 输出路径
            reencode: 是否重新编码（用于不同编码格式的视频）

        Returns:
            Path: 输出文件路径
        """
        if len(video_paths) == 0:
            raise ValueError("video_paths cannot be empty")

        if len(video_paths) == 1:
            import shutil
            shutil.copy(video_paths[0], output_path)
            return output_path

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            for path in video_paths:
                escaped_path = str(path).replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{escaped_path}'\n")
            concat_list = f.name

        try:
            if reencode:
                cmd = [
                    self.ffmpeg, "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", concat_list,
                    "-c:v", "libx264", "-preset", "fast",
                    "-c:a", "aac",
                    str(output_path)
                ]
            else:
                cmd = [
                    self.ffmpeg, "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", concat_list,
                    "-c", "copy",
                    str(output_path)
                ]

            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg concat failed: {result.stderr}")

            logger.info(f"Concatenated {len(video_paths)} videos to {output_path}")
            return output_path

        finally:
            try:
                Path(concat_list).unlink()
            except Exception:
                pass

    async def trim_video(
        self,
        video_path: Path,
        output_path: Path,
        start_time: float,
        end_time: float,
        reencode: bool = False,
    ) -> Path:
        """
        裁剪视频片段。

        Args:
            video_path: 输入视频路径
            output_path: 输出路径
            start_time: 开始时间（秒）
            end_time: 结束时间（秒）
            reencode: 是否重新编码

        Returns:
            Path: 输出文件路径
        """
        duration = end_time - start_time

        if reencode:
            cmd = [
                self.ffmpeg, "-y",
                "-ss", str(start_time),
                "-i", str(video_path),
                "-t", str(duration),
                "-c:v", "libx264", "-preset", "fast",
                "-c:a", "aac",
                str(output_path)
            ]
        else:
            cmd = [
                self.ffmpeg, "-y",
                "-ss", str(start_time),
                "-i", str(video_path),
                "-t", str(duration),
                "-c", "copy",
                str(output_path)
            ]

        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg trim failed: {result.stderr}")

        logger.info(f"Trimmed video: {video_path} [{start_time}s - {end_time}s]")
        return output_path

    async def add_subtitles(
        self,
        video_path: Path,
        subtitle_path: Path,
        output_path: Path,
        font_name: str = "Arial",
        font_size: int = 24,
        font_color: str = "white",
        margin_bottom: int = 50,
    ) -> Path:
        """
        添加字幕（硬字幕，烧录到视频中）。

        Args:
            video_path: 输入视频路径
            subtitle_path: 字幕文件路径（SRT/ASS 格式）
            output_path: 输出路径
            font_name: 字体名称
            font_size: 字体大小
            font_color: 字体颜色
            margin_bottom: 底部边距

        Returns:
            Path: 输出文件路径
        """
        subtitle_escaped = str(subtitle_path).replace("\\", "/").replace(":", "\\:")

        filter_str = (
            f"subtitles='{subtitle_escaped}':"
            f"force_style='FontName={font_name},FontSize={font_size},"
            f"PrimaryColour=&H{self._color_to_ass(font_color)},MarginV={margin_bottom}'"
        )

        cmd = [
            self.ffmpeg, "-y",
            "-i", str(video_path),
            "-vf", filter_str,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "copy",
            str(output_path)
        ]

        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg add_subtitles failed: {result.stderr}")

        logger.info(f"Added subtitles to {video_path}")
        return output_path

    async def add_audio(
        self,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
        audio_volume: float = 1.0,
        replace_original: bool = False,
    ) -> Path:
        """
        添加音频轨道。

        Args:
            video_path: 输入视频路径
            audio_path: 音频文件路径
            output_path: 输出路径
            audio_volume: 音量（1.0 = 原音量）
            replace_original: 是否替换原音频

        Returns:
            Path: 输出文件路径
        """
        filter_parts = []

        if replace_original:
            filter_parts.append(f"[1:a]volume={audio_volume}[audio]")
            map_opts = ["-map", "0:v", "-map", "1:a"]
        else:
            filter_parts.append(f"[0:a]volume=1[a0];[1:a]volume={audio_volume}[a1];[a0][a1]amix=inputs=2[audio]")
            map_opts = ["-map", "0:v", "-map", "[audio]"]

        cmd = [
            self.ffmpeg, "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-filter_complex", ";".join(filter_parts),
        ] + map_opts + [
            "-c:v", "copy",
            "-c:a", "aac",
            str(output_path)
        ]

        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg add_audio failed: {result.stderr}")

        logger.info(f"Added audio to {video_path}")
        return output_path

    async def add_watermark(
        self,
        video_path: Path,
        watermark_path: Path,
        output_path: Path,
        position: str = "bottom_right",
        opacity: float = 0.8,
        margin: int = 20,
    ) -> Path:
        """
        添加水印。

        Args:
            video_path: 输入视频路径
            watermark_path: 水印图片路径
            output_path: 输出路径
            position: 水印位置（top_left/top_right/bottom_left/bottom_right/center）
            opacity: 不透明度（0.0-1.0）
            margin: 边距

        Returns:
            Path: 输出文件路径
        """
        positions = {
            "top_left": f"{margin}:{margin}",
            "top_right": f"W-w-{margin}:{margin}",
            "bottom_left": f"{margin}:H-h-{margin}",
            "bottom_right": f"W-w-{margin}:H-h-{margin}",
            "center": "(W-w)/2:(H-h)/2",
        }
        overlay_pos = positions.get(position, positions["bottom_right"])

        filter_str = f"[1:v]format=rgba,colorchannelmixer=aa={opacity}[wm];[0:v][wm]overlay={overlay_pos}"

        cmd = [
            self.ffmpeg, "-y",
            "-i", str(video_path),
            "-i", str(watermark_path),
            "-filter_complex", filter_str,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "copy",
            str(output_path)
        ]

        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg add_watermark failed: {result.stderr}")

        logger.info(f"Added watermark to {video_path}")
        return output_path

    async def resize_video(
        self,
        video_path: Path,
        output_path: Path,
        width: int,
        height: int,
        maintain_aspect: bool = True,
    ) -> Path:
        """
        调整视频分辨率。

        Args:
            video_path: 输入视频路径
            output_path: 输出路径
            width: 目标宽度
            height: 目标高度
            maintain_aspect: 是否保持宽高比

        Returns:
            Path: 输出文件路径
        """
        if maintain_aspect:
            filter_str = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
        else:
            filter_str = f"scale={width}:{height}"

        cmd = [
            self.ffmpeg, "-y",
            "-i", str(video_path),
            "-vf", filter_str,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "copy",
            str(output_path)
        ]

        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg resize failed: {result.stderr}")

        logger.info(f"Resized video to {width}x{height}")
        return output_path

    async def extract_audio(
        self,
        video_path: Path,
        audio_path: Path,
        audio_format: str = "mp3",
    ) -> Path:
        """
        从视频中提取音频。

        Args:
            video_path: 输入视频路径
            audio_path: 音频输出路径
            audio_format: 音频格式（mp3/wav/aac）

        Returns:
            Path: 音频文件路径
        """
        cmd = [
            self.ffmpeg, "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "libmp3lame" if audio_format == "mp3" else "copy",
            str(audio_path)
        ]

        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg extract_audio failed: {result.stderr}")

        logger.info(f"Extracted audio from {video_path}")
        return audio_path

    async def create_thumbnail(
        self,
        video_path: Path,
        thumbnail_path: Path,
        time: float = 0,
        width: int = 320,
    ) -> Path:
        """
        生成视频缩略图。

        Args:
            video_path: 输入视频路径
            thumbnail_path: 缩略图输出路径
            time: 截取时间点（秒）
            width: 缩略图宽度

        Returns:
            Path: 缩略图路径
        """
        cmd = [
            self.ffmpeg, "-y",
            "-ss", str(time),
            "-i", str(video_path),
            "-vframes", "1",
            "-vf", f"scale={width}:-1",
            str(thumbnail_path)
        ]

        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg create_thumbnail failed: {result.stderr}")

        logger.info(f"Created thumbnail from {video_path}")
        return thumbnail_path

    async def images_to_video(
        self,
        frames_dir: Path,
        output_path: Path,
        fps: float = 24,
        pattern: str = "frame_%04d.jpg",
        start_number: int = 1,
        crf: int = 18,
        preset: str = "fast",
    ) -> Path:
        """把图片序列合成为视频（预演台确定性导出的最后一环）。

        为什么必须由服务端做（`docs/research/research_report_previs_export_feasibility.md`）：
        浏览器实时录制按**墙上时钟**打时间戳，视口稳定不了 24fps 就会录出时长漂移的视频；
        而这里每一帧都来自调用方指定的帧号，配 `-framerate` 后输出必然是准确的固定帧率。

        Args:
            frames_dir: 帧序列所在目录
            output_path: 输出视频路径
            fps: 帧率，直接作为 `-framerate`（不重采样、不丢帧）
            pattern: 帧文件名模式，默认 `frame_%04d.jpg`
            start_number: 序列起始编号，必须与落盘时的命名一致
            crf: x264 质量（0-51，越小越清晰），18 接近视觉无损
            preset: x264 预设

        Returns:
            Path: 输出文件路径
        """
        source = frames_dir / pattern
        if not frames_dir.exists():
            raise ValueError(f"帧序列目录不存在：{frames_dir}")
        if not list(frames_dir.glob(pattern.replace("%04d", "*"))):
            raise ValueError(f"帧序列为空：{source}")

        # 两条不可省的输出约束：
        # 1) `-pix_fmt yuv420p`——保证色度是 4:2:0。实测一个细节：输入是 JPEG 时
        #    ffprobe 会读成 `yuvj420p`（full range，JPEG 的取值范围），仍是 4:2:0、
        #    现代播放器与剪辑软件都能正常读取；这里要防的是 yuv444p 那一类，
        #    它的色度采样不通用，部分播放器会直接解不出来。
        # 2) 宽高取偶数——4:2:0 的色度是 2×2 下采样，奇数尺寸会让编码器报错，
        #    而 canvas 视口尺寸（如 1441×901）完全可能是奇数，所以在这里兜底。
        cmd = [
            self.ffmpeg, "-y",
            "-framerate", str(fps),
            "-start_number", str(start_number),
            "-i", str(source),
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264",
            "-preset", preset,
            "-crf", str(crf),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_path),
        ]

        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=1800,
        )

        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg images_to_video failed: {result.stderr}")

        logger.info(f"Composed sequence to video: {output_path} @ {fps}fps")
        return output_path

    @staticmethod
    def _color_to_ass(color: str) -> str:
        """将颜色名称转换为 ASS 格式（BGR）"""
        color_map = {
            "white": "FFFFFF",
            "black": "000000",
            "red": "0000FF",
            "green": "00FF00",
            "blue": "FF0000",
            "yellow": "00FFFF",
        }
        return color_map.get(color.lower(), "FFFFFF")


_ffmpeg_service: Optional[FFmpegService] = None


def get_ffmpeg_service() -> FFmpegService:
    """获取 FFmpeg 服务实例"""
    global _ffmpeg_service
    if _ffmpeg_service is None:
        _ffmpeg_service = FFmpegService()
    return _ffmpeg_service
