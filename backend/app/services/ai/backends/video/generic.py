"""Configuration-driven asynchronous video backend for AIConnector records."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
from jinja2 import Template
from jsonpath_ng import parse as jsonpath_parse

from app.db.models.ai_connector import AIConnector
from app.services.ai.backends.video.base import BaseVideoBackend
from app.services.ai.types import (
    VideoCapability,
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
        self._capabilities = {VideoCapability.TEXT_TO_VIDEO}
        if connector.support_reference_image:
            self._capabilities.add(VideoCapability.IMAGE_TO_VIDEO)
        try:
            self.config = json.loads(connector.response_config or "{}")
        except (TypeError, ValueError):
            self.config = {}
        try:
            self.default_params = json.loads(connector.default_params or "{}")
        except (TypeError, ValueError):
            self.default_params = {}

    @property
    def available_models(self) -> list[str]:
        return self._available_models

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
    def _size(resolution: str, aspect_ratio: str, separator: str = "x") -> str:
        """Translate workspace resolution/ratio controls to common API sizes."""
        height = {"720p": 720, "1080p": 1080, "2k": 1440}.get(str(resolution).lower(), 720)
        ratio = str(aspect_ratio or "16:9")
        if ratio == "9:16":
            return f"{round(height * 9 / 16)}{separator}{height}"
        if ratio == "1:1":
            return f"{height}{separator}{height}"
        return f"{round(height * 16 / 9)}{separator}{height}"

    def _status(self, payload, task_id: str) -> VideoGenerationResult:
        status = str(self._find(payload, self.config.get("status_path", ""), "pending")).lower()
        done = {str(item).lower() for item in self.config.get("done_values", ["succeeded", "completed", "done", "success"])}
        failed = {str(item).lower() for item in self.config.get("failed_values", ["failed", "error", "cancelled"])}
        url = str(self._find(payload, self.config.get("video_url_path", ""), "") or "")
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

    async def _generate(self, req: VideoGenerationRequest) -> VideoGenerationResult:
        template = self.connector.request_template or '{"model":"{{ model }}","input":{"prompt":"{{ prompt }}"},"parameters":{}}'
        body = json.loads(Template(template).render(
            model=req.model or self.model, prompt=req.prompt, duration=req.duration,
            aspect_ratio=req.aspect_ratio, resolution=req.resolution, seed=req.seed,
            size=self._size(req.resolution, req.aspect_ratio, str(self.default_params.get("size_separator") or "x")),
            generate_audio=req.generate_audio,
            start_image=image_to_base64_data_uri(req.start_image) if req.start_image else "",
            reference_image_base64=image_to_base64_data_uri(req.start_image) if req.start_image else "",
            reference_image_url=image_to_base64_data_uri(req.start_image) if req.start_image else "",
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
