"""
YLCraft - Gemini Image Backend

使用 google-genai SDK 调用 Gemini 2.5 Flash Image（NanoBanana2）等图像生成模型。
支持文生图 + 图生图（参考图多模态输入）。
"""

from __future__ import annotations

import logging
import mimetypes
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import httpx
from google import genai  # noqa: PIE804
from google.genai import types

from app.core.contracts.types import (
    ImageCapability,
    ImageGenerationRequest,
    ImageGenerationResult,
)
from app.db.models.ai_connector import AIConnector

logger = logging.getLogger("ylcraft.gemini_image")


class GeminiImageBackend:
    """
    基于 google-genai SDK 的图像生成后端。

    适用于 Gemini 2.5 Flash Image 等原生图片生成模型。
    API 使用 models.generate_content()，返回 inlineData（base64 图片数据）。
    """

    def __init__(self, connector: AIConnector):
        self.connector = connector
        self._name = connector.name
        self._model = connector.default_model or "gemini-2.5-flash-image"

        # 创建 genai.Client
        http_options: dict = {}
        if connector.base_url:
            http_options["base_url"] = connector.base_url

        self._client = genai.Client(
            api_key=connector.api_key or None,
            http_options=types.HttpOptions(**http_options) if http_options else None,
        )

        # 能力集：文生图 + 图生图（Gemini 原生多模态支持参考图）
        self._capabilities = {
            ImageCapability.TEXT_TO_IMAGE,
        }

        # 存储目录
        backend_dir = Path(__file__).parent.parent.parent.parent
        self._save_dir = backend_dir / "storage" / "images"

        logger.info(
            f"[Gemini-Image] 初始化: name={connector.name}, "
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

    async def generate(
        self,
        req: ImageGenerationRequest,
    ) -> ImageGenerationResult:
        """
        使用 Gemini SDK 生成图像。

        Args:
            req: 图像生成请求，支持：
                - prompt: 描述文本
                - reference_images: 参考图路径/URL 列表（图生图）
                - size: 图片尺寸（Gemini 模型自动处理）
                - model: 动态模型（覆盖默认）

        Returns:
            ImageGenerationResult
        """
        start_time = time.perf_counter()
        model = req.model or self._model

        try:
            # 构建 contents：文本 prompt + 可选参考图
            contents = self._build_contents(req)

            # 调用 Gemini generate_content API
            response = await self._client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                ),
            )

            latency_ms = (time.perf_counter() - start_time) * 1000

            # 提取图片数据
            saved_paths = self._extract_and_save_images(response)

            if not saved_paths:
                # 提取文本响应用于调试
                text_parts: list[str] = []
                for part in response.candidates[0].content.parts:
                    if part.text:
                        text_parts.append(part.text)
                debug_text = " ".join(text_parts).strip()[:200]

                return ImageGenerationResult(
                    success=False,
                    error=f"API 未返回图片数据。文本响应: {debug_text}" if debug_text else "API 未返回任何图片数据",
                    provider=self._name,
                    model=model,
                    latency_ms=latency_ms,
                )

            return ImageGenerationResult(
                success=True,
                url=saved_paths[0] if saved_paths else None,
                urls=saved_paths,
                local_path=saved_paths[0] if saved_paths else None,
                all_local_paths=saved_paths if saved_paths else None,
                provider=self._name,
                model=model,
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            error_msg = f"Gemini API 错误: {e}"
            logger.error(f"[Gemini-Image] {error_msg}")
            return ImageGenerationResult(
                success=False,
                error=error_msg,
                provider=self._name,
                model=model,
                latency_ms=latency_ms,
            )

    def _build_contents(self, req: ImageGenerationRequest) -> list:
        """
        构建 Gemini API 的 contents 参数。

        返回格式：
        - 无参考图：[prompt_text]
        - 有参考图：[prompt_text, Part.from_bytes(...), ...]
        """
        contents: list = [req.prompt]

        if req.reference_images:
            for ref_path in req.reference_images:
                try:
                    img_data = self._read_image_bytes(ref_path)
                    mime_type = self._guess_mime_type(ref_path)
                    contents.append(
                        types.Part.from_bytes(data=img_data, mime_type=mime_type)
                    )
                    logger.info(
                        f"[Gemini-Image] 添加参考图: {ref_path} "
                        f"({len(img_data)} bytes, {mime_type})"
                    )
                except Exception as e:
                    logger.warning(
                        f"[Gemini-Image] 读取参考图失败，跳过: {ref_path}, 错误: {e}"
                    )

        return contents

    def _read_image_bytes(self, ref_path: str) -> bytes:
        """读取参考图字节数据（支持 URL 和本地路径）"""
        if ref_path.startswith(("http://", "https://")):
            resp = httpx.get(ref_path, follow_redirects=True, timeout=30)
            resp.raise_for_status()
            return resp.content
        else:
            return Path(ref_path).read_bytes()

    @staticmethod
    def _guess_mime_type(ref_path: str) -> str:
        """推断图片 MIME 类型"""
        mime, _ = mimetypes.guess_type(ref_path)
        if mime and mime.startswith("image/"):
            return mime
        # 默认为 PNG
        return "image/png"

    def _extract_and_save_images(self, response) -> list[str]:
        """
        从 Gemini API 响应中提取 inlineData 图片并保存到本地。

        Returns:
            本地文件路径列表
        """
        saved_paths: list[str] = []

        if not response.candidates:
            logger.warning("[Gemini-Image] 响应中没有 candidates")
            return saved_paths

        candidate = response.candidates[0]
        if not candidate.content or not candidate.content.parts:
            logger.warning("[Gemini-Image] response.candidates[0].content.parts 为空")
            return saved_paths

        for idx, part in enumerate(candidate.content.parts):
            if part.inline_data and part.inline_data.data:
                mime_type = part.inline_data.mime_type or "image/png"
                img_bytes = part.inline_data.data
                local_path = self._save_image_bytes(
                    img_bytes=img_bytes,
                    mime_type=mime_type,
                    index=idx,
                )
                if local_path:
                    saved_paths.append(local_path)
                    logger.info(
                        f"[Gemini-Image] 已保存第 {idx} 张图片: {local_path} "
                        f"({len(img_bytes)} bytes, {mime_type})"
                    )

        return saved_paths

    def _save_image_bytes(
        self,
        img_bytes: bytes,
        mime_type: str,
        index: int = 0,
    ) -> Optional[str]:
        """将字节数据保存为本地图片文件"""
        try:
            self._save_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ext = self._ext_from_mime(mime_type)
            filename = f"{timestamp}_gemini_{index}{ext}"
            local_path = self._save_dir / filename

            local_path.write_bytes(img_bytes)
            return str(local_path)

        except Exception as e:
            logger.error(f"[Gemini-Image] 保存图片失败 #{index}: {e}")
            return None

    @staticmethod
    def _ext_from_mime(mime_type: str) -> str:
        """从 MIME 类型推断文件扩展名"""
        ext = mimetypes.guess_extension(mime_type)
        if ext:
            return ext
        # 兜底：从 mime_type 直接提取
        parts = mime_type.split("/")
        if len(parts) == 2:
            return f".{parts[1]}"
        return ".png"

    async def health_check(self) -> bool:
        """可达性检查：尝试列出模型（轻量请求）"""
        try:
            await self._client.aio.models.get(model=self._model)
            return True
        except Exception as e:
            logger.warning(f"[Gemini-Image] 健康检查失败: {e}")
            return False

    async def close(self):
        """关闭客户端连接"""
        # google-genai Client 基于 httpx，调用 aclose 清理资源
        if hasattr(self._client, "aclose"):
            await self._client.aclose()
