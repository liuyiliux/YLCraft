"""
YLCraft — MiniMax/Seedance 视频生成后端

API 文档：https://api.minimax.chat/document/Video
参考 ArcReel 的 video_backends/ark.py 设计。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

import httpx

from app.services.video_gen.base import BaseVideoBackend, VideoCapabilities
from app.core.contracts.types import (
    VideoGenerationRequest,
    VideoGenerationResult,
    VideoCapability,
    download_file,
)
from app.services.image.base import image_to_base64_data_uri

logger = logging.getLogger("ylcraft.video.minimax")


class MinimaxVideoBackend(BaseVideoBackend):
    """
    MiniMax 视频生成后端（支持 Seedance）

    模型：
    - seedance-2.0（默认）
    - seedance-1.5-pro
    """

    DEFAULT_MODEL = "seedance-2.0"

    def __init__(
        self,
        api_key: str,
        api_base: str = "https://api.minimax.chat/v1",
        model: str | None = None,
    ):
        super().__init__(
            name="minimax-video",
            model=model or self.DEFAULT_MODEL,
            api_key=api_key,
            api_base=api_base,
            cost_per_second=0.05,
        )
        self._capabilities = {
            VideoCapability.TEXT_TO_VIDEO,
            VideoCapability.IMAGE_TO_VIDEO,
            VideoCapability.SEED_CONTROL,
            VideoCapability.GENERATE_AUDIO,
        }

    @property
    def video_capabilities(self) -> VideoCapabilities:
        return VideoCapabilities(
            first_frame=True,
            last_frame=False,
            reference_images=False,
            max_duration=10,
        )

    async def health_check(self) -> bool:
        """探测 /v1/models 接口"""
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    f"{self._api_base}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def _generate(self, req: VideoGenerationRequest) -> VideoGenerationResult:
        """
        创建 MiniMax 视频生成任务。

        API: POST /v1/video/generation
        """
        # 构建 content 列表
        content = [{"type": "text", "text": req.prompt}]

        # I2V: 首帧图片
        if req.start_image:
            data_uri = image_to_base64_data_uri(req.start_image)
            content.append({
                "type": "image_url",
                "image_url": {"url": data_uri},
                "role": "first_frame",
            })

        # 构建请求体
        payload = {
            "model": req.model or self._model,
            "content": content,
            "duration": req.duration,
            "ratio": req.aspect_ratio,
            "generate_audio": req.generate_audio,
            "watermark": False,
        }

        if req.seed is not None:
            payload["seed"] = req.seed

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self._api_base}/video/generation",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        task_id = data.get("task_id") or data.get("id")
        if not task_id:
            raise ValueError(f"MiniMax 未返回 task_id: {data}")

        logger.info(f"[MinimaxVideo] 任务已创建: {task_id}")

        return VideoGenerationResult(
            success=True,
            task_id=task_id,
            status="pending",
            duration_seconds=req.duration,
        )

    async def _poll(self, task_id: str) -> VideoGenerationResult:
        """
        轮询 MiniMax 视频生成任务状态。

        API: GET /v1/video/generation/{task_id}
        """
        headers = {
            "Authorization": f"Bearer {self._api_key}",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{self._api_base}/video/generation/{task_id}",
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        status = data.get("status", "pending")

        # 状态映射
        status_map = {
            "pending": "pending",
            "processing": "processing",
            "running": "processing",
            "succeeded": "done",
            "completed": "done",
            "failed": "error",
            "expired": "error",
        }
        mapped_status = status_map.get(status, status)

        if mapped_status == "error":
            error_msg = data.get("error") or data.get("message") or "Unknown error"
            return VideoGenerationResult(
                success=False,
                task_id=task_id,
                status="error",
                error=f"MiniMax 视频生成失败: {error_msg}",
            )

        if mapped_status == "done":
            video_url = data.get("video_url") or data.get("url")
            output_path = Path("F:/PycharmProjects/YLCraft/storage/videos") / f"{task_id}.mp4"

            if video_url:
                await download_file(video_url, output_path, timeout=120)

            return VideoGenerationResult(
                success=True,
                task_id=task_id,
                status="done",
                url=video_url,
                video_path=output_path,
                duration_seconds=data.get("duration", 5),
                seed=data.get("seed"),
            )

        # 进行中
        progress = data.get("progress", 0)
        return VideoGenerationResult(
            success=True,
            task_id=task_id,
            status="processing",
            progress=progress,
            progress_message=f"视频生成中... {progress}%",
        )
