"""
YLCraft — TTS API

POST /api/v1/tts/speak — 文本转语音
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import ensure_download_path

router = APIRouter()
logger = logging.getLogger("ylcraft.tts")


class TTSSpeakRequest(BaseModel):
    text: str
    voice: Optional[str] = None
    speed: Optional[float] = 1.0
    provider: Optional[str] = None


class TTSResponse(BaseModel):
    success: bool
    file_path: Optional[str] = None
    audio_url: Optional[str] = None
    error: Optional[str] = None


@router.post("/speak", response_model=TTSResponse, summary="文本转语音")
async def tts_speak(req: TTSSpeakRequest):
    """
    将文本转换为语音并保存到下载目录。
    目前为占位实现，后续接入真实 TTS Provider。
    """
    if not req.text:
        return TTSResponse(success=False, error="文本不能为空")

    try:
        # TODO: 接入真实 TTS Provider（如 Azure TTS、CosyVoice 等）
        # 目前返回占位响应
        download_dir = ensure_download_path()
        filename = f"tts_{uuid.uuid4().hex[:8]}.mp3"
        file_path = download_dir / filename

        # 占位：创建空文件
        file_path.write_bytes(b"")
        logger.warning(f"TTS placeholder: text='{req.text[:20]}...' saved to {file_path}")

        return TTSResponse(
            success=True,
            file_path=str(file_path),
            audio_url=f"/api/v1/tts/files/{filename}",
        )
    except Exception as e:
        logger.error(f"TTS failed: {e}")
        return TTSResponse(success=False, error=str(e))


@router.get("/files/{filename}", summary="获取 TTS 音频文件")
async def get_tts_file(filename: str):
    """返回 TTS 生成的音频文件"""
    download_dir = ensure_download_path()
    file_path = download_dir / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    return FileResponse(
        path=str(file_path),
        media_type="audio/mpeg",
        filename=filename,
    )
