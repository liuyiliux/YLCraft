"""
YLCraft - OpenAI SDK Image Backend

使用 OpenAI Python SDK 调用 DALL-E 等图像生成 API。
适用于标准 OpenAI 兼容平台的图像生成（DALL-E 2/3）。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import httpx
import openai

from app.services.ai.types import (
    ImageCapability,
    ImageGenerationRequest,
    ImageGenerationResult,
)
from app.db.models.ai_connector import AIConnector

logger = logging.getLogger("ylcraft.openai_sdk_image")


class OpenAISDKImageBackend:
    """
    基于 OpenAI Python SDK 的图像生成后端。

    适用于 OpenAI DALL-E 等标准图像生成 API。
    """

    def __init__(self, connector: AIConnector):
        self.connector = connector
        self._name = connector.name
        self._model = connector.default_model or "dall-e-3"

        self._client = openai.AsyncOpenAI(
            api_key=connector.api_key,
            base_url=connector.base_url or None,
            max_retries=2,
        )

        self._capabilities = {
            ImageCapability.TEXT_TO_IMAGE,
        }

        backend_dir = Path(__file__).parent.parent.parent.parent.parent
        self._save_dir = backend_dir / "storage" / "images"

        logger.info(
            f"[OpenAISDK-Image] 初始化: name={connector.name}, "
            f"model={self._model}"
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set:
        return self._capabilities

    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        start_time = time.perf_counter()
        model = req.model or self._model
        size = req.size or "1024x1024"
        n = req.n if req.n > 0 else 1

        try:
            response = await self._client.images.generate(
                model=model,
                prompt=req.prompt,
                n=n,
                size=size,
                quality="standard",
            )

            latency_ms = (time.perf_counter() - start_time) * 1000
            urls = [img.url for img in response.data if img.url]

            if not urls:
                return ImageGenerationResult(
                    success=False,
                    error="API 返回空结果，未生成任何图片",
                    provider=self._name,
                    model=model,
                    latency_ms=latency_ms,
                )

            all_local_paths: List[str] = []
            first_local_path: Optional[str] = None

            for idx, url in enumerate(urls):
                local_path = await self._download_image(url=url, prompt=req.prompt[:30], index=idx)
                if local_path:
                    all_local_paths.append(local_path)
                    if first_local_path is None:
                        first_local_path = local_path

            return ImageGenerationResult(
                success=len(all_local_paths) > 0,
                url=urls[0] if urls else None,
                urls=urls,
                local_path=first_local_path,
                all_local_paths=all_local_paths if all_local_paths else None,
                provider=self._name,
                model=model,
                latency_ms=latency_ms,
                error=None if all_local_paths else f"图片下载失败，URLs={urls}",
            )

        except openai.APIError as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            error_msg = (
                f"OpenAI API 错误: status={e.status_code if hasattr(e, 'status_code') else 'N/A'}, "
                f"message={e.message if hasattr(e, 'message') else str(e)}"
            )
            logger.error(f"[OpenAISDK-Image] {error_msg}")
            return ImageGenerationResult(success=False, error=error_msg, provider=self._name, model=model, latency_ms=latency_ms)

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"[OpenAISDK-Image] 未知错误: {e}")
            return ImageGenerationResult(success=False, error=str(e), provider=self._name, model=model, latency_ms=latency_ms)

    async def _download_image(self, url: str, prompt: str, index: int = 0) -> Optional[str]:
        try:
            self._save_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_prompt = "".join(c for c in prompt[:20] if c.isalnum() or c in " -_").strip().replace(" ", "_") or "image"
            ext = ".png"
            url_lower = url.lower()
            if url_lower.endswith(".jpg") or url_lower.endswith(".jpeg"):
                ext = ".jpg"
            elif url_lower.endswith(".webp"):
                ext = ".webp"
            filename = f"{timestamp}_{safe_prompt}_{index}{ext}"
            local_path = self._save_dir / filename
            async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                with open(local_path, "wb") as f:
                    f.write(resp.content)
            logger.info(f"[OpenAISDK-Image] 已保存: {local_path}")
            return str(local_path)
        except Exception as e:
            logger.error(f"[OpenAISDK-Image] 下载失败 url={url}: {e}")
            return None

    async def health_check(self) -> bool:
        try:
            await self._client.models.list()
            return True
        except Exception as e:
            logger.warning(f"[OpenAISDK-Image] 健康检查失败: {e}")
            return False

    async def close(self):
        await self._client.close()
