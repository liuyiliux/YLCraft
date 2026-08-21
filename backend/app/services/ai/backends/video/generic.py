"""Configuration-driven asynchronous video backend for AIConnector records."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import uuid4

import httpx
from jinja2 import Template
from jsonpath_ng import parse as jsonpath_parse

from app.db.models.ai_connector import AIConnector
from app.services.ai.backends.video.base import BaseVideoBackend
from app.services.ai.types import (
    VideoCapability,
    VideoCapabilities,
    VideoGenerationRequest,
    VideoGenerationResult,
    download_file,
    image_to_base64_data_uri,
)

logger = logging.getLogger("ylcraft.video.generic")


class VideoProviderRequestError(RuntimeError):
    def __init__(self, diagnostics: dict):
        self.diagnostics = diagnostics
        super().__init__(diagnostics.get("exception_repr") or "Video provider request failed")


class GenericVideoBackend(BaseVideoBackend):
    """Generic JSON task API. Connector response_config defines JSONPath fields."""

    def __init__(self, connector: AIConnector, session=None):
        super().__init__(connector.name, connector.default_model or "", connector.api_key or "", connector.base_url or "")
        self.connector = connector
        self.session = session
        self._available_models = connector.get_available_models() or [self.model]
        try:
            self.config = json.loads(connector.response_config or "{}")
        except (TypeError, ValueError):
            self.config = {}
        try:
            self.default_params = json.loads(connector.default_params or "{}")
        except (TypeError, ValueError):
            self.default_params = {}
        self._video_capability_config = self.default_params.get("video_capabilities") or {}
        if not isinstance(self._video_capability_config, dict):
            self._video_capability_config = {}
        self._capabilities = {VideoCapability.TEXT_TO_VIDEO}
        if self._video_capability_config.get("text_to_video") is False:
            self._capabilities.discard(VideoCapability.TEXT_TO_VIDEO)
        template_supports_start_image = any(
            variable in (connector.request_template or "")
            for variable in ("{{ start_image", "{{ reference_image_base64", "{{ reference_image_url")
        )
        if (connector.support_reference_image or template_supports_start_image) and self._video_capability_config.get("image_to_video") is not False:
            self._capabilities.add(VideoCapability.IMAGE_TO_VIDEO)
        if self._video_capability_config.get("seed_control") is True:
            self._capabilities.add(VideoCapability.SEED_CONTROL)
        if self._video_capability_config.get("generate_audio") is True:
            self._capabilities.add(VideoCapability.GENERATE_AUDIO)

    @property
    def available_models(self) -> list[str]:
        return self._available_models

    @property
    def video_capabilities(self) -> VideoCapabilities:
        config = self._video_capability_config

        def string_values(key: str) -> list[str]:
            values = config.get(key) or []
            return [str(value) for value in values] if isinstance(values, list) else []

        def integer_values(key: str) -> list[int]:
            values = config.get(key) or []
            if not isinstance(values, list):
                return []
            result: list[int] = []
            for value in values:
                try:
                    result.append(int(value))
                except (TypeError, ValueError):
                    continue
            return result

        max_duration = config.get("max_duration", 10)
        try:
            max_duration = int(max_duration)
        except (TypeError, ValueError):
            max_duration = 10
        max_reference_images = config.get("max_reference_images", 0)
        try:
            max_reference_images = int(max_reference_images)
        except (TypeError, ValueError):
            max_reference_images = 0
        return VideoCapabilities(
            first_frame=VideoCapability.IMAGE_TO_VIDEO in self._capabilities,
            last_frame=bool(config.get("last_frame", False)),
            reference_images=bool(config.get("reference_images", False)),
            max_reference_images=max(0, max_reference_images),
            max_duration=max(1, max_duration),
            supported_resolutions=string_values("resolutions"),
            supported_aspect_ratios=string_values("aspect_ratios"),
            supported_durations=integer_values("durations"),
        )

    @property
    def enforce_video_capabilities(self) -> bool:
        # Existing generic connections often predate video_capabilities. Keep
        # their permissive request behavior until the owner declares limits.
        return bool(self._video_capability_config)

    def _endpoint(self, path: str = "") -> str:
        path = path or self.connector.api_endpoint or ""
        if path.startswith(("http://", "https://")):
            return path
        return f"{(self.connector.base_url or '').rstrip('/')}/{path.lstrip('/')}"

    def _headers(self, extra: dict | None = None) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.connector.api_key:
            headers["Authorization"] = f"Bearer {self.connector.api_key}"
        headers.update(extra or {})
        return headers

    @staticmethod
    def _redact(value, limit: int = 2000):
        sensitive = {"authorization", "api_key", "apikey", "token", "secret", "password"}
        if isinstance(value, dict):
            return {str(key): "***" if str(key).lower() in sensitive else GenericVideoBackend._redact(item, limit) for key, item in value.items()}
        if isinstance(value, list):
            return [GenericVideoBackend._redact(item, limit) for item in value[:50]]
        if isinstance(value, str):
            if value.startswith("data:"):
                return "<data-uri omitted>"
            return value if len(value) <= limit else value[:limit] + "...(truncated)"
        return value

    @classmethod
    def _excerpt(cls, value, limit: int = 4000) -> str:
        try:
            text = json.dumps(cls._redact(value), ensure_ascii=False, default=str)
        except Exception:
            text = repr(value)
        return text if len(text) <= limit else text[:limit] + "...(truncated)"

    @classmethod
    def _error_details(cls, exc: Exception) -> dict:
        details = {"exception_type": exc.__class__.__name__, "exception_repr": repr(exc)}
        if isinstance(exc, httpx.HTTPStatusError):
            details["http_status"] = exc.response.status_code
            details["response_excerpt"] = cls._excerpt(exc.response.text)
        return details

    @staticmethod
    def _find(payload, path: str, default=None):
        if not path:
            return default
        matches = jsonpath_parse(path).find(payload)
        return matches[0].value if matches else default

    @staticmethod
    def _decode_payload(payload):
        """Unwrap providers that return a JSON-encoded object as a JSON string."""
        value = payload
        for _ in range(2):
            if not isinstance(value, str):
                break
            try:
                decoded = json.loads(value)
            except (TypeError, ValueError, json.JSONDecodeError):
                break
            if decoded == value:
                break
            value = decoded
        return value

    @staticmethod
    def _size(resolution: str, aspect_ratio: str, separator: str = "x") -> str:
        """Translate workspace resolution/ratio controls to common API sizes."""
        width, height = GenericVideoBackend._dimensions(resolution, aspect_ratio)
        return f"{width}{separator}{height}"

    @staticmethod
    def _dimensions(resolution: str, aspect_ratio: str) -> tuple[int, int]:
        """Return numeric dimensions for providers which do not accept a size string."""
        height = {"480p": 480, "720p": 720, "1080p": 1080, "2k": 1440}.get(str(resolution).lower(), 720)
        ratio = str(aspect_ratio or "16:9")
        if ratio == "9:16":
            return round(height * 9 / 16), height
        if ratio == "1:1":
            return height, height
        if ratio == "4:3":
            return round(height * 4 / 3), height
        if ratio == "3:4":
            return round(height * 3 / 4), height
        return round(height * 16 / 9), height

    @staticmethod
    def _frame_count(duration: int, fps: int) -> int:
        """Use the common 8n+1 video-frame contract when a provider requires it."""
        return max(1, 8 * round(max(1, duration) * max(1, fps) / 8) + 1)

    def _status(self, payload, task_id: str) -> VideoGenerationResult:
        payload = self._decode_payload(payload)
        # Some providers changed their poll schema over time. Keep the
        # configured JSONPath authoritative, but accept the common Agnes
        # aliases so a completed response cannot lose its playable URL.
        status = self._find(payload, self.config.get("status_path", ""), None)
        if status is None:
            status = self._find(payload, "$.internal_status", None)
        if status is None:
            status = "pending"
        status = str(status).lower()
        done = {str(item).lower() for item in self.config.get("done_values", ["succeeded", "completed", "done", "success"])}
        failed = {str(item).lower() for item in self.config.get("failed_values", ["failed", "error", "cancelled"])}
        url = self._find(payload, self.config.get("video_url_path", ""), None)
        if not url:
            url = self._find(payload, "$.url", "")
        url = str(url or "")
        error = str(self._find(payload, self.config.get("error_path", ""), "") or "")
        progress = self._find(payload, self.config.get("progress_path", ""), 0)
        try:
            progress = int(float(progress))
        except (TypeError, ValueError):
            progress = 0
        if status in failed:
            return VideoGenerationResult(False, task_id=task_id, status="error", error=error or "视频任务失败")
        if status in done or url:
            return VideoGenerationResult(True, task_id=task_id, status="done", url=url, progress=100)
        return VideoGenerationResult(True, task_id=task_id, status="processing", progress=progress)

    async def _upload_start_image_to_cos(self, start_image: Path) -> str:
        """Upload the first-frame image to COS and return a public URL.

        Only used when the connector declares ``image_requires_public_url``
        (e.g. Agnes image-to-video needs a reachable URL, not a data URI).
        """
        try:
            from app.services.cos_storage import load_cos_service

            service = await load_cos_service()
            if not service:
                return ""
            ext = start_image.suffix.lower() or ".png"
            key = f"video/start/{uuid4().hex}{ext}"
            return await service.upload_file(key, start_image)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[%s] COS upload for start image failed: %s", self.name, exc)
            return ""

    async def _generate(self, req: VideoGenerationRequest) -> VideoGenerationResult:
        template = self.connector.request_template or '{"model":"{{ model }}","input":{"prompt":"{{ prompt }}"},"parameters":{}}'
        width, height = self._dimensions(req.resolution, req.aspect_ratio)

        start_image_value = ""
        if req.start_image:
            if isinstance(req.start_image, str) and str(req.start_image).startswith(("http://", "https://")):
                # 公网 URL 直接透传（前端素材库「来源 URL」选择，供应商要求公网链接时无需再传 COS）
                start_image_value = req.start_image
            else:
                start_path = Path(req.start_image) if isinstance(req.start_image, str) else req.start_image
                start_image_value = image_to_base64_data_uri(start_path)
                if self.default_params.get("image_requires_public_url"):
                    cos_url = await self._upload_start_image_to_cos(start_path)
                    if cos_url:
                        start_image_value = cos_url

        body = json.loads(Template(template).render(
            model=req.model or self.model, prompt=req.prompt, duration=req.duration,
            aspect_ratio=req.aspect_ratio, resolution=req.resolution, seed=req.seed,
            size=self._size(req.resolution, req.aspect_ratio, str(self.default_params.get("size_separator") or "x")),
            width=width, height=height, fps=req.fps,
            num_frames=self._frame_count(req.duration, req.fps),
            generate_audio=req.generate_audio,
            start_image=start_image_value,
            reference_image_base64=start_image_value,
            reference_image_url=start_image_value,
            params=self.default_params,
        ))
        headers = self._headers(self.config.get("request_headers") or {})
        endpoint = self._endpoint()
        diagnostics = {
            "operation": "submit",
            "method": "POST",
            "endpoint": endpoint,
            "timeout_seconds": self.connector.timeout,
            "request_headers": self._redact(headers),
            "request_body": self._redact(body),
        }
        try:
            async with httpx.AsyncClient(timeout=self.connector.timeout, trust_env=False) as client:
                response = await client.post(endpoint, headers=headers, json=body)
                diagnostics["http_status"] = response.status_code
                diagnostics["response_excerpt"] = self._excerpt(response.text)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            diagnostics.update(self._error_details(exc))
            logger.warning("[%s] video submit failed: %s", self.name, diagnostics)
            raise VideoProviderRequestError(diagnostics) from exc
        task_id = str(self._find(payload, self.config.get("task_id_path", ""), "") or "")
        if not task_id:
            raise ValueError("视频供应商未返回 task_id；请检查 response_config.task_id_path")
        return VideoGenerationResult(
            True,
            task_id=task_id,
            status="pending",
            duration_seconds=req.duration,
            diagnostics=diagnostics,
        )

    async def _poll(self, task_id: str) -> VideoGenerationResult:
        endpoint = str(self.config.get("poll_endpoint") or "").replace("{task_id}", task_id)
        if not endpoint:
            raise ValueError("视频连接器未配置 response_config.poll_endpoint")
        headers = self._headers(self.config.get("poll_headers") or {})
        request_url = self._endpoint(endpoint)
        diagnostics = {
            "operation": "poll",
            "method": "GET",
            "endpoint": request_url,
            "timeout_seconds": self.connector.timeout,
            "request_headers": self._redact(headers),
        }
        try:
            async with httpx.AsyncClient(timeout=self.connector.timeout, trust_env=False) as client:
                response = await client.get(request_url, headers=headers)
                diagnostics["http_status"] = response.status_code
                diagnostics["response_excerpt"] = self._excerpt(response.text)
                response.raise_for_status()
                result = self._status(response.json(), task_id)
        except Exception as exc:
            diagnostics.update(self._error_details(exc))
            logger.warning("[%s] video poll failed: %s", self.name, diagnostics)
            raise VideoProviderRequestError(diagnostics) from exc
        result.diagnostics = diagnostics
        if result.status == "done" and result.url:
            output = Path(__file__).resolve().parents[5] / "storage" / "videos" / f"{task_id}.mp4"
            await download_file(result.url, output, timeout=self.connector.timeout)
            result.video_path = output
        return result
