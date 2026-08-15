"""Configuration-driven image-to-3D provider adapter.

This is deliberately separate from the legacy TripoSR helper: providers are
selected from AIConnector records and their request/poll contract is explicit.
"""

from __future__ import annotations

import io
import json
import logging
import hashlib
import hmac
import time
import zipfile
from pathlib import Path
from typing import Any

import httpx
from jinja2 import Template
from jsonpath_ng import parse as jsonpath_parse

from app.db.models.ai_connector import AIConnector

logger = logging.getLogger("ylcraft.model3d.connector")


class Model3DProviderRequestError(RuntimeError):
    def __init__(self, diagnostics: dict[str, Any]):
        self.diagnostics = diagnostics
        super().__init__(diagnostics.get("exception_repr") or diagnostics.get("response_excerpt") or "3D provider request failed")


class Model3DConnectorBackend:
    def __init__(self, connector: AIConnector):
        self.connector = connector
        try:
            self.response_config = json.loads(connector.response_config or "{}")
        except (TypeError, ValueError):
            self.response_config = {}
        try:
            self.default_params = json.loads(connector.default_params or "{}")
        except (TypeError, ValueError):
            self.default_params = {}

    @property
    def name(self) -> str:
        return self.connector.name

    def _endpoint(self, endpoint: str | None = None) -> str:
        base = (self.connector.base_url or "").rstrip("/")
        path = (endpoint or self.connector.api_endpoint or "").strip()
        if not path:
            return base
        return path if path.startswith("http://") or path.startswith("https://") else f"{base}/{path.lstrip('/')}"

    @staticmethod
    def _value(data: Any, path: str, default: Any = None) -> Any:
        if not path:
            return default
        matches = jsonpath_parse(path).find(data)
        return matches[0].value if matches else default

    def _render(self, values: dict[str, Any]) -> dict[str, Any]:
        template = self.connector.request_template or '{"model":"{{ model }}","prompt":"{{ prompt }}","image_url":"{{ image_url }}"}'
        rendered = Template(template).render(**values)
        parsed = json.loads(rendered)
        if not isinstance(parsed, dict):
            raise ValueError("3D Request 模板必须渲染为 JSON object")
        return parsed

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.connector.api_key:
            # Providers differ on whether an API key uses Bearer auth. Keep
            # the default compatible with existing connectors, while allowing
            # public presets to declare a raw key (for example Tencent 3D).
            header_name = str(self.response_config.get("api_key_header") or "Authorization")
            prefix = self.response_config.get("api_key_prefix", "Bearer")
            value = f"{prefix} {self.connector.api_key}" if prefix else self.connector.api_key
            headers[header_name] = value
        return headers

    def _configured_headers(self, key: str) -> dict[str, str]:
        """Merge provider-defined headers without ever exposing secrets in diagnostics."""
        headers = self._headers()
        configured = self.response_config.get(key) or {}
        if isinstance(configured, dict):
            headers.update({str(name): str(value) for name, value in configured.items()})
        return headers

    def _tencent_tc3_headers(self, action: str, body: dict[str, Any]) -> dict[str, str]:
        """Build Tencent Cloud TC3-HMAC-SHA256 headers from SecretId:SecretKey."""
        try:
            secret_id, secret_key = self.connector.api_key.split(":", 1)
        except ValueError as exc:
            raise ValueError(
                "腾讯云 3D 的 API Key 请填写为 SecretId:SecretKey（腾讯云 CAM 密钥对，例如 AKIDxxxx:yyyy；OpenAI 风格的 sk-... 密钥不适用）"
            ) from exc
        if not secret_id.strip() or not secret_key.strip():
            raise ValueError("腾讯云 3D 的 API Key 请填写为 SecretId:SecretKey（SecretId 与 SecretKey 都不能为空）")
        host = "ai3d.tencentcloudapi.com"
        service = "ai3d"
        version = str(self.response_config.get("tencent_version") or "2025-05-13")
        region = str(self.response_config.get("tencent_region") or "ap-guangzhou")
        timestamp = int(time.time())
        date = time.strftime("%Y-%m-%d", time.gmtime(timestamp))
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        hashed_payload = hashlib.sha256(payload).hexdigest()
        canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{host}\n"
        signed_headers = "content-type;host"
        canonical_request = f"POST\n/\n\n{canonical_headers}\n{signed_headers}\n{hashed_payload}"
        credential_scope = f"{date}/{service}/tc3_request"
        string_to_sign = f"TC3-HMAC-SHA256\n{timestamp}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode()).hexdigest()}"
        def sign(key: bytes, message: str) -> bytes:
            return hmac.new(key, message.encode(), hashlib.sha256).digest()
        secret_date = sign(("TC3" + secret_key).encode(), date)
        secret_service = sign(secret_date, service)
        secret_signing = sign(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()
        authorization = f"TC3-HMAC-SHA256 Credential={secret_id}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"
        return {
            "Content-Type": "application/json; charset=utf-8", "Host": host,
            "Authorization": authorization, "X-TC-Action": action,
            "X-TC-Version": version, "X-TC-Region": region, "X-TC-Timestamp": str(timestamp),
        }

    def _tc3_action(self, config_key: str, default: str) -> str:
        """Resolve a Tencent TC3 action name, allowing presets to override it."""
        value = str(self.response_config.get(config_key) or default).strip()
        return value or default

    @staticmethod
    def _excerpt(value: str, limit: int = 3000) -> str:
        return value if len(value) <= limit else f"{value[:limit]}...(truncated)"

    @staticmethod
    def _redact(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: ("***" if any(token in key.lower() for token in ("authorization", "api_key", "token", "secret")) else Model3DConnectorBackend._redact(item))
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [Model3DConnectorBackend._redact(item) for item in value]
        if isinstance(value, str) and value.startswith("data:"):
            return "<data-uri omitted>"
        return value

    @staticmethod
    def _error_details(exc: Exception) -> dict[str, Any]:
        details: dict[str, Any] = {"exception_type": type(exc).__name__, "exception_repr": repr(exc)}
        if isinstance(exc, httpx.HTTPStatusError):
            details["http_status"] = exc.response.status_code
        return details

    def _resolve_model_url(self, payload: Any, config: dict[str, Any]) -> str:
        """Pick the best result URL.

        Some providers (e.g. Tencent Hunyuan 3D) return several formats under
        one list; prefer a self-contained GLB over a packed archive when the
        connector declares ``result_files_path`` / ``prefer_model_type``.
        """
        files_path = str(config.get("result_files_path") or "")
        if files_path:
            files = self._value(payload, files_path, None)
            if isinstance(files, list):
                preferred = str(config.get("prefer_model_type") or "GLB").upper()
                for item in files:
                    if isinstance(item, dict) and str(item.get("Type", "")).upper() == preferred and item.get("Url"):
                        return str(item["Url"])
                for item in files:
                    if isinstance(item, dict) and item.get("Url"):
                        return str(item["Url"])
        return str(self._value(payload, config.get("model_url_path", config.get("result_url_path", "")), "") or "")

    def _resolve_preview_url(self, payload: Any, config: dict[str, Any]) -> str:
        """Pick the provider's preview image URL (e.g. Tencent PreviewImageUrl)."""
        files_path = str(config.get("result_files_path") or "")
        if files_path:
            files = self._value(payload, files_path, None)
            if isinstance(files, list):
                for item in files:
                    if isinstance(item, dict) and item.get("PreviewImageUrl"):
                        return str(item["PreviewImageUrl"])
        return str(self._value(payload, config.get("preview_url_path", ""), "") or "")

    def _parse(self, payload: Any, fallback_task_id: str = "") -> dict[str, Any]:
        config = self.response_config
        task_id = str(self._value(payload, config.get("task_id_path", ""), fallback_task_id) or "")
        raw_status = str(self._value(payload, config.get("status_path", ""), "") or "").lower()
        url = self._resolve_model_url(payload, config)
        preview_url = self._resolve_preview_url(payload, config)
        error = str(self._value(payload, config.get("error_path", ""), "") or "")
        progress_value = self._value(payload, config.get("progress_path", ""), 0)
        try:
            progress = int(float(progress_value or 0))
        except (TypeError, ValueError):
            progress = 0
        done_values = {str(item).lower() for item in config.get("done_values", ["done", "completed", "success", "succeed"])}
        failed_values = {str(item).lower() for item in config.get("failed_values", ["failed", "error", "cancelled"])}
        if url and not raw_status:
            status = "done"
        elif raw_status in done_values:
            status = "done"
        elif raw_status in failed_values:
            status = "error"
        else:
            status = "pending"
        return {"task_id": task_id, "status": status, "url": url, "preview_url": preview_url, "error": error or None, "progress": 100 if status == "done" else progress}

    async def submit(
        self, *, prompt: str, source_image: str, source_url: str, model: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        image_base64 = source_image.split(",", 1)[1] if source_image.startswith("data:") else source_image
        request_params = {**self.default_params, **(options or {})}
        body = self._render({
            **request_params,
            "model": model or self.connector.default_model,
            "prompt": prompt,
            "image_url": source_url,
            "image_data": source_image,
            "image_base64": image_base64,
            "params": request_params,
        })
        endpoint = self._endpoint()
        submit_action = self._tc3_action("tencent_submit_action", "SubmitHunyuanTo3DProJob")
        headers = self._tencent_tc3_headers(submit_action, body) if self.connector.api_format == "tencent_tc3" else self._configured_headers("request_headers")
        diagnostics = {"operation": "submit", "method": "POST", "endpoint": endpoint,
                       "timeout_seconds": self.connector.timeout, "request_headers": self._redact(headers),
                       "request_body": self._redact(body)}
        try:
            async with httpx.AsyncClient(timeout=self.connector.timeout, follow_redirects=True, trust_env=False) as client:
                response = await client.post(endpoint, headers=headers, json=body)
                diagnostics["http_status"] = response.status_code
                diagnostics["response_excerpt"] = self._excerpt(response.text)
                response.raise_for_status()
                result = self._parse(response.json())
        except Exception as exc:
            diagnostics.update(self._error_details(exc))
            logger.warning("[%s] 3D submit failed: %s", self.name, diagnostics)
            raise Model3DProviderRequestError(diagnostics) from exc
        result["diagnostics"] = diagnostics
        return result

    async def poll(self, task_id: str) -> dict[str, Any]:
        config = self.response_config
        endpoint = str(config.get("poll_endpoint") or "").replace("{task_id}", task_id)
        if not endpoint:
            raise ValueError("该 3D 连接器未配置 response_config.poll_endpoint")
        method = str(config.get("poll_method") or "GET").upper()
        request_url = self._endpoint(endpoint)
        headers = self._configured_headers("poll_headers")
        diagnostics = {"operation": "poll", "method": method, "endpoint": request_url,
                       "timeout_seconds": self.connector.timeout, "request_headers": self._redact(headers)}
        try:
            async with httpx.AsyncClient(timeout=self.connector.timeout, follow_redirects=True, trust_env=False) as client:
                if method == "POST":
                    poll_template = config.get("poll_request_template")
                    if poll_template:
                        poll_body = json.loads(Template(str(poll_template)).render(task_id=task_id))
                    else:
                        poll_body = {"task_id": task_id}
                    if self.connector.api_format == "tencent_tc3":
                        query_action = self._tc3_action("tencent_query_action", "QueryHunyuanTo3DProJob")
                        headers = self._tencent_tc3_headers(query_action, poll_body)
                    diagnostics["request_body"] = self._redact(poll_body)
                    response = await client.post(request_url, headers=headers, json=poll_body)
                else:
                    response = await client.get(request_url, headers=headers)
                diagnostics["http_status"] = response.status_code
                diagnostics["response_excerpt"] = self._excerpt(response.text)
                response.raise_for_status()
                result = self._parse(response.json(), fallback_task_id=task_id)
        except Exception as exc:
            diagnostics.update(self._error_details(exc))
            logger.warning("[%s] 3D poll failed: %s", self.name, diagnostics)
            raise Model3DProviderRequestError(diagnostics) from exc
        result["diagnostics"] = diagnostics
        return result

    async def download(self, url: str, task_id: str) -> Path:
        directory = Path(__file__).resolve().parents[3] / "storage" / "model3d"
        directory.mkdir(parents=True, exist_ok=True)

        def _model_from_directory(base: Path) -> Path | None:
            order = {".glb": 0, ".gltf": 1, ".obj": 2, ".fbx": 3, ".usdz": 4}
            candidates = [p for p in base.rglob("*") if p.is_file() and p.suffix.lower() in order]
            if not candidates:
                return None
            candidates.sort(key=lambda p: (order[p.suffix.lower()], -p.stat().st_size))
            return candidates[0]

        suffix = Path(url.split("?", 1)[0]).suffix.lower()
        if suffix not in {".glb", ".gltf", ".obj", ".fbx", ".usdz", ".zip"}:
            suffix = ".glb"
        target = directory / f"{task_id}{suffix}"
        if target.is_file() and target.stat().st_size:
            return target
        headers = self._headers() if self.connector.api_key else {}
        headers.pop("Content-Type", None)
        try:
            async with httpx.AsyncClient(timeout=self.connector.timeout, follow_redirects=True, trust_env=False) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                content = response.content
        except Exception as exc:
            diagnostics = {"operation": "download", "method": "GET", "endpoint": url,
                           "timeout_seconds": self.connector.timeout, "request_headers": self._redact(headers),
                           **self._error_details(exc)}
            logger.warning("[%s] 3D download failed: %s", self.name, diagnostics)
            raise Model3DProviderRequestError(diagnostics) from exc

        # Tencent and other providers may hand back a ZIP archive; unpack it
        # and return a real model file instead of storing the archive as a model.
        if content[:2] == b"PK" or suffix == ".zip":
            extract_dir = directory / f"{task_id}_extract"
            extract_dir.mkdir(parents=True, exist_ok=True)
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    archive.extractall(extract_dir)
                model = _model_from_directory(extract_dir)
                if model:
                    return model
            except zipfile.BadZipFile:
                logger.warning("[%s] 3D result is not a valid ZIP archive: %s", self.name, url)

        target.write_bytes(content)
        return target

    async def download_preview(self, url: str, task_id: str) -> str:
        """Download the provider's preview image into local storage; empty on failure."""
        if not url:
            return ""
        directory = Path(__file__).resolve().parents[3] / "storage" / "model3d" / "previews"
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{task_id}.png"
        if target.is_file() and target.stat().st_size:
            return str(target)
        headers = self._headers() if self.connector.api_key else {}
        headers.pop("Content-Type", None)
        try:
            async with httpx.AsyncClient(timeout=self.connector.timeout, follow_redirects=True, trust_env=False) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                target.write_bytes(response.content)
        except Exception as exc:
            logger.warning("[%s] 3D preview download failed: %s", self.name, exc)
            return ""
        return str(target)
