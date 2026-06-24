"""
YLCraft - OpenAI SDK Image Backend

Uses the OpenAI Python SDK for OpenAI-compatible image generation APIs.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx
import openai

from app.db.models.ai_connector import AIConnector
from app.services.ai.types import (
    ImageCapability,
    ImageGenerationRequest,
    ImageGenerationResult,
)

logger = logging.getLogger("ylcraft.openai_sdk_image")


class OpenAISDKImageBackend:
    """Image backend powered by openai.AsyncOpenAI.images.generate."""

    def __init__(self, connector: AIConnector):
        self.connector = connector
        self._name = connector.name
        self._model = connector.default_model or "dall-e-3"
        self._default_params = self._parse_json_object(connector.default_params)

        self._client = openai.AsyncOpenAI(
            api_key=connector.api_key,
            base_url=connector.base_url or None,
            max_retries=2,
            timeout=connector.timeout,
        )

        self._capabilities = {
            ImageCapability.TEXT_TO_IMAGE,
        }

        backend_dir = Path(__file__).parent.parent.parent.parent.parent
        self._save_dir = backend_dir / "storage" / "images"

        logger.info(
            "[OpenAISDK-Image] initialized: name=%s, model=%s",
            connector.name,
            self._model,
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
            params = self._build_generation_params(
                model=model,
                prompt=req.prompt,
                size=size,
                n=n,
            )
            logger.info(
                "[OpenAISDK-Image] request images.generate: %s",
                json.dumps(self._safe_log_params(params), ensure_ascii=False),
            )

            response = await self._client.images.generate(**params)
            latency_ms = (time.perf_counter() - start_time) * 1000

            urls = [img.url for img in response.data if getattr(img, "url", None)]
            b64_images = [img.b64_json for img in response.data if getattr(img, "b64_json", None)]

            if not urls and not b64_images:
                return ImageGenerationResult(
                    success=False,
                    error="API returned an empty image result",
                    provider=self._name,
                    model=model,
                    latency_ms=latency_ms,
                )

            all_local_paths: List[str] = []
            first_local_path: Optional[str] = None
            preview_urls: List[str] = []

            for idx, url in enumerate(urls):
                local_path = await self._download_image(url=url, prompt=req.prompt[:30], index=idx)
                if local_path:
                    all_local_paths.append(local_path)
                    preview_urls.append(self._local_file_url(local_path))
                    if first_local_path is None:
                        first_local_path = local_path

            output_format = (
                self._default_params.get("output_format")
                or self._default_params.get("format")
                or "png"
            )
            for idx, b64_data in enumerate(b64_images):
                local_path = self._save_base64_image(
                    b64_data=b64_data,
                    prompt=req.prompt[:30],
                    index=idx,
                    output_format=output_format,
                )
                if local_path:
                    all_local_paths.append(local_path)
                    preview_urls.append(self._local_file_url(local_path))
                    if first_local_path is None:
                        first_local_path = local_path

            returned_urls = urls or preview_urls
            return ImageGenerationResult(
                success=len(all_local_paths) > 0,
                url=returned_urls[0] if returned_urls else None,
                urls=returned_urls,
                local_path=first_local_path,
                all_local_paths=all_local_paths if all_local_paths else None,
                provider=self._name,
                model=model,
                latency_ms=latency_ms,
                error=None
                if all_local_paths
                else f"Image save failed, urls={urls}, base64_count={len(b64_images)}",
            )

        except openai.APIError as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            error_msg = (
                f"OpenAI API error: status={e.status_code if hasattr(e, 'status_code') else 'N/A'}, "
                f"message={e.message if hasattr(e, 'message') else str(e)}"
            )
            logger.error("[OpenAISDK-Image] %s", error_msg)
            return ImageGenerationResult(
                success=False,
                error=error_msg,
                provider=self._name,
                model=model,
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.error("[OpenAISDK-Image] unknown error: %s", e)
            return ImageGenerationResult(
                success=False,
                error=str(e),
                provider=self._name,
                model=model,
                latency_ms=latency_ms,
            )

    def _build_generation_params(self, *, model: str, prompt: str, size: str, n: int) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": n,
            "size": size,
        }

        allowed_sdk_params = {"quality", "response_format", "style", "user"}
        for key in allowed_sdk_params:
            value = self._default_params.get(key)
            if value is not None and value != "":
                params[key] = value

        extra_body = self._default_params.get("extra_body")
        if isinstance(extra_body, dict) and extra_body:
            params["extra_body"] = extra_body

        return params

    async def _download_image(self, url: str, prompt: str, index: int = 0) -> Optional[str]:
        try:
            self._save_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_prompt = (
                "".join(c for c in prompt[:20] if c.isalnum() or c in " -_")
                .strip()
                .replace(" ", "_")
                or "image"
            )
            ext = ".png"
            url_lower = url.lower()
            if url_lower.endswith(".jpg") or url_lower.endswith(".jpeg"):
                ext = ".jpg"
            elif url_lower.endswith(".webp"):
                ext = ".webp"
            filename = f"{timestamp}_{safe_prompt}_{index}{ext}"
            local_path = self._save_dir / filename

            async with httpx.AsyncClient(timeout=self.connector.timeout, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                local_path.write_bytes(resp.content)

            logger.info("[OpenAISDK-Image] saved: %s", local_path)
            return str(local_path)
        except Exception as e:
            logger.error("[OpenAISDK-Image] download failed url=%s: %s", url, e)
            return None

    def _save_base64_image(
        self,
        b64_data: str,
        prompt: str,
        index: int = 0,
        output_format: str = "png",
    ) -> Optional[str]:
        try:
            self._save_dir.mkdir(parents=True, exist_ok=True)
            ext = self._ext_from_output_format(output_format)
            data = b64_data
            if b64_data.startswith("data:"):
                header, data = b64_data.split(",", 1)
                mime_type = header.split(";")[0].replace("data:", "") or ""
                ext = self._ext_from_output_format(mime_type)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_prompt = (
                "".join(c for c in prompt[:20] if c.isalnum() or c in " -_")
                .strip()
                .replace(" ", "_")
                or "image"
            )
            filename = f"{timestamp}_{safe_prompt}_{index}{ext}"
            local_path = self._save_dir / filename
            local_path.write_bytes(base64.b64decode(data))
            logger.info("[OpenAISDK-Image] base64 image saved: %s", local_path)
            return str(local_path)
        except Exception as e:
            logger.error("[OpenAISDK-Image] save base64 image failed: %s", e)
            return None

    async def health_check(self) -> bool:
        try:
            await self._client.models.list()
            return True
        except Exception as e:
            logger.warning("[OpenAISDK-Image] health check failed: %s", e)
            return False

    async def close(self):
        await self._client.close()

    @staticmethod
    def _parse_json_object(value: Any) -> Dict[str, Any]:
        if not value:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
                return parsed if isinstance(parsed, dict) else {}
            except Exception as e:
                logger.warning("[OpenAISDK-Image] failed to parse default_params: %s", e)
                return {}
        return {}

    @staticmethod
    def _ext_from_output_format(output_format: str) -> str:
        value = (output_format or "png").strip().lower()
        if "/" in value:
            guessed = mimetypes.guess_extension(value)
            if guessed:
                return ".jpg" if guessed == ".jpe" else guessed
            value = value.split("/", 1)[1]
        value = value.lstrip(".")
        if value == "jpeg":
            value = "jpg"
        if value not in {"png", "jpg", "webp", "gif"}:
            value = "png"
        return f".{value}"

    @staticmethod
    def _local_file_url(path: str) -> str:
        return f"/api/v1/assets/download?path={quote(path, safe='')}"

    @staticmethod
    def _safe_log_params(params: Dict[str, Any]) -> Dict[str, Any]:
        safe = dict(params)
        if isinstance(safe.get("extra_body"), dict):
            safe["extra_body"] = {
                key: ("***" if "key" in key.lower() else value)
                for key, value in safe["extra_body"].items()
            }
        return safe
