"""
YLCraft — 视频剪辑 API

提供视频剪辑、合并、字幕等操作的 REST API。
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from app.services.ffmpeg_service import get_ffmpeg_service

router = APIRouter()
logger = logging.getLogger("ylcraft.clip")


class TrimRequest(BaseModel):
    video_path: str
    start_time: float
    end_time: float
    reencode: bool = False


class ConcatRequest(BaseModel):
    video_paths: list[str]
    reencode: bool = False


class SubtitleRequest(BaseModel):
    video_path: str
    subtitle_path: str
    font_name: str = "Arial"
    font_size: int = 24
    font_color: str = "white"


class AudioRequest(BaseModel):
    video_path: str
    audio_path: str
    audio_volume: float = 1.0
    replace_original: bool = False


class WatermarkRequest(BaseModel):
    video_path: str
    watermark_path: str
    position: str = "bottom_right"
    opacity: float = 0.8
    margin: int = 20


class ResizeRequest(BaseModel):
    video_path: str
    width: int
    height: int
    maintain_aspect: bool = True


class VideoInfoResponse(BaseModel):
    success: bool = True
    width: int = 0
    height: int = 0
    duration: float = 0.0
    fps: float = 0.0
    codec: str = ""
    file_size: int = 0
    error: Optional[str] = None


class OperationResponse(BaseModel):
    success: bool = True
    output_path: Optional[str] = None
    error: Optional[str] = None


@router.get("/info/{video_path:path}", response_model=VideoInfoResponse, summary="获取视频信息")
async def get_video_info(video_path: str):
    """获取视频的详细信息（分辨率、时长、帧率等）"""
    try:
        ffmpeg = get_ffmpeg_service()
        info = await ffmpeg.get_video_info(Path(video_path))

        return VideoInfoResponse(
            success=True,
            width=info["width"],
            height=info["height"],
            duration=info["duration"],
            fps=info["fps"],
            codec=info["codec"],
            file_size=info["file_size"],
        )
    except Exception as e:
        logger.error(f"Failed to get video info: {e}")
        return VideoInfoResponse(success=False, error=str(e))


@router.post("/trim", response_model=OperationResponse, summary="裁剪视频")
async def trim_video(req: TrimRequest):
    """
    裁剪视频片段。

    - **video_path**: 输入视频路径
    - **start_time**: 开始时间（秒）
    - **end_time**: 结束时间（秒）
    - **reencode**: 是否重新编码（用于精确裁剪）
    """
    try:
        ffmpeg = get_ffmpeg_service()

        # 生成输出路径
        input_path = Path(req.video_path)
        output_path = input_path.parent / f"{input_path.stem}_trimmed{input_path.suffix}"

        result = await ffmpeg.trim_video(
            video_path=input_path,
            output_path=output_path,
            start_time=req.start_time,
            end_time=req.end_time,
            reencode=req.reencode,
        )

        return OperationResponse(success=True, output_path=str(result))
    except Exception as e:
        logger.error(f"Trim failed: {e}")
        return OperationResponse(success=False, error=str(e))


@router.post("/concat", response_model=OperationResponse, summary="合并视频")
async def concat_videos(req: ConcatRequest):
    """
    合并多个视频文件。

    - **video_paths**: 视频文件路径列表
    - **reencode**: 是否重新编码（用于不同编码格式）
    """
    try:
        if len(req.video_paths) == 0:
            raise HTTPException(status_code=400, detail="video_paths cannot be empty")

        ffmpeg = get_ffmpeg_service()

        # 生成输出路径
        first_path = Path(req.video_paths[0])
        output_path = first_path.parent / f"concat_{len(req.video_paths)}_videos{first_path.suffix}"

        result = await ffmpeg.concat_videos(
            video_paths=[Path(p) for p in req.video_paths],
            output_path=output_path,
            reencode=req.reencode,
        )

        return OperationResponse(success=True, output_path=str(result))
    except Exception as e:
        logger.error(f"Concat failed: {e}")
        return OperationResponse(success=False, error=str(e))


@router.post("/subtitle", response_model=OperationResponse, summary="添加字幕")
async def add_subtitles(req: SubtitleRequest):
    """
    添加字幕（硬字幕，烧录到视频中）。

    - **video_path**: 输入视频路径
    - **subtitle_path**: 字幕文件路径（SRT/ASS 格式）
    - **font_name**: 字体名称
    - **font_size**: 字体大小
    - **font_color**: 字体颜色
    """
    try:
        ffmpeg = get_ffmpeg_service()

        # 生成输出路径
        video_path = Path(req.video_path)
        output_path = video_path.parent / f"{video_path.stem}_subtitled{video_path.suffix}"

        result = await ffmpeg.add_subtitles(
            video_path=video_path,
            subtitle_path=Path(req.subtitle_path),
            output_path=output_path,
            font_name=req.font_name,
            font_size=req.font_size,
            font_color=req.font_color,
        )

        return OperationResponse(success=True, output_path=str(result))
    except Exception as e:
        logger.error(f"Add subtitles failed: {e}")
        return OperationResponse(success=False, error=str(e))


@router.post("/audio", response_model=OperationResponse, summary="添加音频")
async def add_audio(req: AudioRequest):
    """
    添加音频轨道。

    - **video_path**: 输入视频路径
    - **audio_path**: 音频文件路径
    - **audio_volume**: 音量（1.0 = 原音量）
    - **replace_original**: 是否替换原音频
    """
    try:
        ffmpeg = get_ffmpeg_service()

        # 生成输出路径
        video_path = Path(req.video_path)
        output_path = video_path.parent / f"{video_path.stem}_with_audio{video_path.suffix}"

        result = await ffmpeg.add_audio(
            video_path=video_path,
            audio_path=Path(req.audio_path),
            output_path=output_path,
            audio_volume=req.audio_volume,
            replace_original=req.replace_original,
        )

        return OperationResponse(success=True, output_path=str(result))
    except Exception as e:
        logger.error(f"Add audio failed: {e}")
        return OperationResponse(success=False, error=str(e))


@router.post("/watermark", response_model=OperationResponse, summary="添加水印")
async def add_watermark(req: WatermarkRequest):
    """
    添加水印。

    - **video_path**: 输入视频路径
    - **watermark_path**: 水印图片路径
    - **position**: 水印位置（top_left/top_right/bottom_left/bottom_right/center）
    - **opacity**: 不透明度（0.0-1.0）
    - **margin**: 边距
    """
    try:
        ffmpeg = get_ffmpeg_service()

        # 生成输出路径
        video_path = Path(req.video_path)
        output_path = video_path.parent / f"{video_path.stem}_watermarked{video_path.suffix}"

        result = await ffmpeg.add_watermark(
            video_path=video_path,
            watermark_path=Path(req.watermark_path),
            output_path=output_path,
            position=req.position,
            opacity=req.opacity,
            margin=req.margin,
        )

        return OperationResponse(success=True, output_path=str(result))
    except Exception as e:
        logger.error(f"Add watermark failed: {e}")
        return OperationResponse(success=False, error=str(e))


@router.post("/resize", response_model=OperationResponse, summary="调整分辨率")
async def resize_video(req: ResizeRequest):
    """
    调整视频分辨率。

    - **video_path**: 输入视频路径
    - **width**: 目标宽度
    - **height**: 目标高度
    - **maintain_aspect**: 是否保持宽高比
    """
    try:
        ffmpeg = get_ffmpeg_service()

        # 生成输出路径
        video_path = Path(req.video_path)
        output_path = video_path.parent / f"{video_path.stem}_{req.width}x{req.height}{video_path.suffix}"

        result = await ffmpeg.resize_video(
            video_path=video_path,
            output_path=output_path,
            width=req.width,
            height=req.height,
            maintain_aspect=req.maintain_aspect,
        )

        return OperationResponse(success=True, output_path=str(result))
    except Exception as e:
        logger.error(f"Resize failed: {e}")
        return OperationResponse(success=False, error=str(e))


@router.post("/extract-audio", response_model=OperationResponse, summary="提取音频")
async def extract_audio(video_path: str, audio_format: str = "mp3"):
    """
    从视频中提取音频。

    - **video_path**: 输入视频路径
    - **audio_format**: 音频格式（mp3/wav/aac）
    """
    try:
        ffmpeg = get_ffmpeg_service()

        # 生成输出路径
        video_p = Path(video_path)
        audio_path = video_p.parent / f"{video_p.stem}.{audio_format}"

        result = await ffmpeg.extract_audio(
            video_path=video_p,
            audio_path=audio_path,
            audio_format=audio_format,
        )

        return OperationResponse(success=True, output_path=str(result))
    except Exception as e:
        logger.error(f"Extract audio failed: {e}")
        return OperationResponse(success=False, error=str(e))


@router.post("/thumbnail", response_model=OperationResponse, summary="生成缩略图")
async def create_thumbnail(video_path: str, time: float = 0, width: int = 320):
    """
    生成视频缩略图。

    - **video_path**: 输入视频路径
    - **time**: 截取时间点（秒）
    - **width**: 缩略图宽度
    """
    try:
        ffmpeg = get_ffmpeg_service()

        # 生成输出路径
        video_p = Path(video_path)
        thumbnail_path = video_p.parent / f"{video_p.stem}_thumb.jpg"

        result = await ffmpeg.create_thumbnail(
            video_path=video_p,
            thumbnail_path=thumbnail_path,
            time=time,
            width=width,
        )

        return OperationResponse(success=True, output_path=str(result))
    except Exception as e:
        logger.error(f"Create thumbnail failed: {e}")
        return OperationResponse(success=False, error=str(e))


@router.post("/upload", response_model=OperationResponse, summary="上传视频文件")
async def upload_video(file: UploadFile = File(...)):
    """
    上传视频文件到服务器临时目录。
    返回文件路径供后续操作使用。
    """
    try:
        # 创建临时目录
        temp_dir = Path(tempfile.gettempdir()) / "ylcraft_uploads"
        temp_dir.mkdir(exist_ok=True)

        # 保存文件
        file_path = temp_dir / file.filename
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        logger.info(f"Uploaded video: {file_path}")
        return OperationResponse(success=True, output_path=str(file_path))
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return OperationResponse(success=False, error=str(e))
