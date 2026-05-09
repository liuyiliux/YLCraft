"""
YLCraft — MiniMax/Seedance 图像生成后端

API 文档：https://api.minimax.chat/document/Image
参考 ArcReel 的 image_backends/ark.py 设计。
"""

from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from pathlib import Path

import httpx

from app.services.image.base import BaseImageBackend, image_to_base64_data_uri
from app.core.contracts.types import (
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageCapability,
)

logger = logging.getLogger("ylcraft.image.minimax")


class MinimaxImageBackend(BaseImageBackend):
    """
    MiniMax 图像生成后端（支持 Seedance 2.0）

    模型：
    - seedance-2.0（默认）
    - minimax/Image-01
    """

    DEFAULT_MODEL = "seedance-2.0"

    def __init__(
        self,
        api_key: str,
        api_base: str = "https://api.minimax.chat/v1",
        model: str | None = None,
        support_img2img: bool = True,
    ):
        """
        初始化 MiniMax 图像后端

        Args:
            api_key: API 密钥
            api_base: API 基础 URL
            model: 默认模型
            support_img2img: 是否支持图生图（默认 True，MiniMax 原生支持）
        """
        super().__init__(
            name="minimax-image",
            model=model or self.DEFAULT_MODEL,
            api_key=api_key,
            api_base=api_base,
            cost_per_call=0.1,
        )
        self._capabilities = {ImageCapability.TEXT_TO_IMAGE}
        if support_img2img:
            self._capabilities.add(ImageCapability.IMAGE_TO_IMAGE)

    async def health_check(self) -> bool:
        """探测 /v1/models 接口"""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    f"{self._api_base}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def _generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        """
        调用 MiniMax 图像生成 API。

        请求：POST https://api.minimax.chat/v1/image/generation
        Body: { model, prompt, image_size, ... }

        Returns:
            ImageGenerationResult
        """
        # 构建请求体
        payload = {
            "model": req.model or self._model,
            "prompt": req.prompt,
        }

        if req.negative_prompt:
            payload["negative_prompt"] = req.negative_prompt

        if req.size:
            payload["image_size"] = self._normalize_size(req.size)

        if req.n and req.n > 1:
            payload["n"] = req.n

        # I2I: 参考图片
        if req.reference_images:
            data_uris = [image_to_base64_data_uri(Path(p)) for p in req.reference_images]
            payload["image"] = data_uris[0] if len(data_uris) == 1 else data_uris

        if req.seed is not None:
            payload["seed"] = req.seed

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._api_base}/image/generation",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        # 解析响应 —— MiniMax 返回 { data: [{ url, base64 }] }
        images = data.get("data", [])
        if not images:
            raise ValueError(f"MiniMax 返回空图像数据: {data}")

        first = images[0]
        image_url = first.get("url")
        b64_data = first.get("b64_json") or first.get("base64")

        # 确定输出路径
        output_path = req.output_path
        if output_path is None:
            output_dir = Path("F:/PycharmProjects/YLCraft/storage/images")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"{uuid.uuid4().hex[:8]}.png"

        # 下载或解码保存
        if image_url:
            await self._download(image_url, output_path)
        elif b64_data:
            await asyncio.to_thread(self._save_base64, b64_data, output_path)

        urls = [img.get("url") for img in images if img.get("url")]

        return ImageGenerationResult(
            success=True,
            image_path=output_path,
            url=image_url,
            urls=urls if len(urls) > 1 else None,
            seed=data.get("seed"),
        )

    def _normalize_size(self, size: str) -> str:
        """将 "1024x1024" 转换为 MiniMax 接受的 "1024:1024" 格式"""
        if not size:
            return "1024:1024"
        return size.replace("x", ":")

    def _save_base64(self, b64_data: str, output_path: Path) -> None:
        """保存 base64 图片到文件"""
        image_data = base64.b64decode(b64_data)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(image_data)

    async def _download(self, url: str, output_path: Path) -> None:
        """下载图像到本地"""
        from app.core.contracts.types import download_file
        await download_file(url, output_path, timeout=30)
