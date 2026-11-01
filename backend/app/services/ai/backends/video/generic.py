"""Configuration-driven asynchronous video backend for AIConnector records."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
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

# 供应商「暂时没容量」而不是「拒绝这次请求」的响应：这些可以短重试，
# 并且要用能给用户看懂的话报出来（2026-10-31 Agnes 返回 503 video_queue_full）。
_TRANSIENT_SUBMIT_STATUSES = {429, 500, 502, 503, 504}
_TRANSIENT_SUBMIT_CODES = {
    "video_queue_full",
    "queue_full",
    "rate_limit_exceeded",
    "server_overloaded",
    "overloaded",
}
_DEFAULT_SUBMIT_ATTEMPTS = 3
_DEFAULT_SUBMIT_RETRY_DELAYS = [3.0, 8.0]


class VideoProviderRequestError(RuntimeError):
    def __init__(self, diagnostics: dict, message: str = ""):
        self.diagnostics = diagnostics
        super().__init__(message or diagnostics.get("exception_repr") or "Video provider request failed")


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
    def _completion_timestamp(value) -> float | None:
        """Coerce a provider terminal timestamp to POSIX seconds.

        Providers are inconsistent here: Agnes returns epoch seconds while Wan
        returns an ISO timestamp under ``output.end_time``. A missing or
        malformed value must stay missing so the API can fall back to its local
        observation time instead of inventing a completion instant.
        """
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            timestamp = float(value)
            if abs(timestamp) >= 1_000_000_000_000:
                timestamp /= 1000.0
            return timestamp if timestamp > 0 else None
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text:
            return None
        try:
            timestamp = float(text)
        except ValueError:
            timestamp = None
        if timestamp is not None:
            return GenericVideoBackend._completion_timestamp(timestamp)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            # Provider timestamps without an offset are interpreted in the
            # server's local timezone, matching how they are displayed here.
            return parsed.astimezone().timestamp()
        return parsed.timestamp()

    def _completed_at(self, payload) -> float | None:
        """Read the first configured or common provider completion timestamp."""
        paths = [self.config.get("completed_at_path")]
        paths.extend([
            "$.completed_at",
            "$.finished_at",
            "$.end_time",
            "$.output.end_time",
            "$.output.completed_at",
        ])
        for path in paths:
            if not path:
                continue
            timestamp = self._completion_timestamp(self._find(payload, path, None))
            if timestamp is not None:
                return timestamp
        return None

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
        completed_at = self._completed_at(payload)
        try:
            progress = int(float(progress))
        except (TypeError, ValueError):
            progress = 0
        if status in failed:
            return VideoGenerationResult(
                False,
                task_id=task_id,
                status="error",
                error=error or "视频任务失败",
                completed_at=completed_at,
            )
        if status in done or url:
            return VideoGenerationResult(
                True,
                task_id=task_id,
                status="done",
                url=url,
                progress=100,
                completed_at=completed_at,
            )
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

    def _template_values(self, req: VideoGenerationRequest, start_image_value: str) -> dict:
        width, height = self._dimensions(req.resolution, req.aspect_ratio)
        return {
            "model": req.model or self.model,
            "prompt": req.prompt,
            "duration": req.duration,
            "aspect_ratio": req.aspect_ratio,
            "resolution": req.resolution,
            "seed": req.seed,
            "size": self._size(req.resolution, req.aspect_ratio, str(self.default_params.get("size_separator") or "x")),
            "width": width,
            "height": height,
            "fps": req.fps,
            "num_frames": self._frame_count(req.duration, req.fps),
            "generate_audio": req.generate_audio,
            "start_image": start_image_value,
            "reference_image_base64": start_image_value,
            "reference_image_url": start_image_value,
            "params": self.default_params,
        }

    def _build_template_params(self, values: dict) -> dict:
        """Expose ``{{ key }}`` plus ``{{ key_json }}`` / ``{{ key_json_str }}``.

        ``*_json`` renders a complete JSON literal (quotes included, use it
        unquoted: ``"prompt":{{ prompt_json }}``); ``*_json_str`` renders the
        escaped content only, for placeholders already inside a quoted string.
        """
        template_params = dict(values)
        for key, value in values.items():
            template_params[f"{key}_json"] = json.dumps(value, ensure_ascii=False)
            if isinstance(value, str):
                template_params[f"{key}_json_str"] = self._json_string_escape(value)
        return template_params

    @staticmethod
    def _json_string_escape(value: str) -> str:
        return json.dumps(value or "", ensure_ascii=False)[1:-1]

    def _render_request_body(self, req: VideoGenerationRequest, start_image_value: str) -> dict:
        """Render ``request_template`` into the JSON body sent to the provider.

        Connector templates are JSON documents with Jinja placeholders such as
        ``"prompt":"{{ prompt }}"``. Jinja interpolates values verbatim, so a
        prompt containing a newline, a tab, a quote or a backslash used to make
        the rendered document invalid JSON (``Invalid control character at:
        line 1 column 147``) and the generation failed before any request was
        sent. Prefer ``{{ prompt_json }}`` in connector templates; when a
        template interpolates a raw value inside a quoted string, retry once
        with JSON-escaped strings so the document stays valid and the provider
        still receives the original text after it decodes the body.
        """
        template = self.connector.request_template or '{"model":"{{ model }}","input":{"prompt":"{{ prompt }}"},"parameters":{}}'
        values = self._template_values(req, start_image_value)
        template_params = self._build_template_params(values)
        rendered = Template(template).render(**template_params)
        try:
            return json.loads(rendered)
        except json.JSONDecodeError as exc:
            safe_params = {
                **template_params,
                **{
                    key: self._json_string_escape(value) if isinstance(value, str) else value
                    for key, value in values.items()
                },
            }
            try:
                body = json.loads(Template(template).render(**safe_params))
            except json.JSONDecodeError:
                preview = " ".join(rendered.split())[:300]
                raise ValueError(
                    "视频连接器「%s」的 request_template 渲染后不是合法 JSON：%s。"
                    "请在模板里对文本字段使用 {{ prompt_json }}（或 {{ prompt_json_str }}），"
                    "或修正模板本身。渲染片段：%s" % (self.name, exc, preview)
                ) from exc
            logger.warning(
                "[%s] request_template 直接内插文本导致 JSON 非法，已用 JSON 转义重试；"
                "建议模板改用 {{ prompt_json }}",
                self.name,
            )
            return body

    def _submit_attempts(self) -> int:
        """Total submit attempts, including the first one."""
        try:
            return max(1, min(5, int(self.default_params.get("submit_retry_attempts", _DEFAULT_SUBMIT_ATTEMPTS))))
        except (TypeError, ValueError):
            return _DEFAULT_SUBMIT_ATTEMPTS

    def _submit_retry_delays(self) -> list[float]:
        raw = self.default_params.get("submit_retry_delays")
        delays: list[float] = []
        if isinstance(raw, (list, tuple)):
            for item in raw:
                try:
                    delays.append(max(0.0, float(item)))
                except (TypeError, ValueError):
                    continue
        return delays or list(_DEFAULT_SUBMIT_RETRY_DELAYS)

    @staticmethod
    def _provider_error_fields(response) -> tuple[str, str]:
        """Read (code, message) out of the provider's JSON error envelope."""
        try:
            payload = response.json()
        except ValueError:
            return "", ""
        if not isinstance(payload, dict):
            return "", ""
        code = payload.get("code") or ""
        message = payload.get("message") or ""
        error = payload.get("error")
        if isinstance(error, dict):
            code = code or error.get("code") or ""
            message = message or error.get("message") or ""
        return str(code or ""), str(message or "")

    @classmethod
    def _transient_submit_reason(cls, response) -> str:
        """Non-empty when the provider is temporarily out of capacity.

        Such a response must not be reported as a raw ``HTTPStatusError``: the
        connector is fine, the provider just has no slot for the job.
        """
        code, message = cls._provider_error_fields(response)
        if code.lower() in _TRANSIENT_SUBMIT_CODES:
            return message or code
        if response.status_code in _TRANSIENT_SUBMIT_STATUSES:
            return message or "HTTP %s" % response.status_code
        return ""

    def _busy_message(self, reason: str) -> str:
        return (
            "视频供应商当前繁忙，任务没有创建（%s）。这不是连接器配置问题："
            "请稍后重试，或先换一个视频模型。" % (reason or "队列已满")
        )

    def _rejected_message(self, response) -> str:
        code, message = self._provider_error_fields(response)
        detail = " ".join(part for part in (code, message) if part)
        suffix = ("：" + detail) if detail else "，请检查模型名和请求参数。"
        return "视频供应商拒绝了请求（HTTP %s）%s" % (response.status_code, suffix)

    async def _generate(self, req: VideoGenerationRequest) -> VideoGenerationResult:
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

        body = self._render_request_body(req, start_image_value)
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
        attempts = self._submit_attempts()
        delays = self._submit_retry_delays()
        payload: dict = {}
        for attempt in range(1, attempts + 1):
            diagnostics["submit_attempt"] = attempt
            try:
                async with httpx.AsyncClient(timeout=self.connector.timeout, trust_env=False) as client:
                    response = await client.post(endpoint, headers=headers, json=body)
            except Exception as exc:
                diagnostics.update(self._error_details(exc))
                logger.warning("[%s] video submit failed: %s", self.name, diagnostics)
                raise VideoProviderRequestError(diagnostics) from exc

            diagnostics["http_status"] = response.status_code
            diagnostics["response_excerpt"] = self._excerpt(response.text)
            busy_reason = self._transient_submit_reason(response)
            if busy_reason and attempt < attempts:
                delay = delays[min(attempt - 1, len(delays) - 1)]
                retry_after = str(response.headers.get("retry-after", "") or "").strip()
                try:
                    delay = max(delay, min(float(retry_after), 30.0))
                except ValueError:
                    pass
                diagnostics.setdefault("retries", []).append({
                    "attempt": attempt,
                    "http_status": response.status_code,
                    "reason": busy_reason,
                    "delay_seconds": delay,
                })
                logger.warning(
                    "[%s] 视频供应商繁忙（%s），%.0f 秒后重试（第 %s/%s 次提交）",
                    self.name, busy_reason, delay, attempt + 1, attempts,
                )
                await asyncio.sleep(delay)
                continue
            if busy_reason:
                logger.warning("[%s] 视频供应商繁忙，已重试 %s 次仍无容量: %s", self.name, attempts, busy_reason)
                raise VideoProviderRequestError(diagnostics, self._busy_message(busy_reason))
            if response.status_code >= 400:
                logger.warning("[%s] video submit rejected: %s", self.name, diagnostics)
                raise VideoProviderRequestError(diagnostics, self._rejected_message(response))
            try:
                payload = response.json()
            except ValueError as exc:
                diagnostics.update(self._error_details(exc))
                raise VideoProviderRequestError(diagnostics) from exc
            break
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
