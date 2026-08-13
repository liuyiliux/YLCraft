"""Configuration-driven image-to-3D provider adapter.

This is deliberately separate from the legacy TripoSR helper: providers are
selected from AIConnector records and their request/poll contract is explicit.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from jinja2 import Template
from jsonpath_ng import parse as jsonpath_parse

from app.db.models.ai_connector import AIConnector


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
            headers["Authorization"] = f"Bearer {self.connector.api_key}"
        return headers

    def _parse(self, payload: Any, fallback_task_id: str = "") -> dict[str, Any]:
        config = self.response_config
        task_id = str(self._value(payload, config.get("task_id_path", ""), fallback_task_id) or "")
        raw_status = str(self._value(payload, config.get("status_path", ""), "") or "").lower()
        url = str(self._value(payload, config.get("model_url_path", config.get("result_url_path", "")), "") or "")
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
        return {"task_id": task_id, "status": status, "url": url, "error": error or None, "progress": 100 if status == "done" else progress}

    async def submit(self, *, prompt: str, source_image: str, source_url: str, model: str) -> dict[str, Any]:
        body = self._render({
            "model": model or self.connector.default_model,
            "prompt": prompt,
            "image_url": source_url,
            "image_data": source_image,
            "params": self.default_params,
        })
        async with httpx.AsyncClient(timeout=self.connector.timeout, follow_redirects=True) as client:
            response = await client.post(self._endpoint(), headers=self._headers(), json=body)
            response.raise_for_status()
            return self._parse(response.json())

    async def poll(self, task_id: str) -> dict[str, Any]:
        config = self.response_config
        endpoint = str(config.get("poll_endpoint") or "").replace("{task_id}", task_id)
        if not endpoint:
            raise ValueError("该 3D 连接器未配置 response_config.poll_endpoint")
        method = str(config.get("poll_method") or "GET").upper()
        async with httpx.AsyncClient(timeout=self.connector.timeout, follow_redirects=True) as client:
            if method == "POST":
                response = await client.post(self._endpoint(endpoint), headers=self._headers(), json={"task_id": task_id})
            else:
                response = await client.get(self._endpoint(endpoint), headers=self._headers())
            response.raise_for_status()
            return self._parse(response.json(), fallback_task_id=task_id)

    async def download(self, url: str, task_id: str) -> Path:
        suffix = Path(url.split("?", 1)[0]).suffix.lower() or ".glb"
        if suffix not in {".glb", ".gltf", ".obj", ".fbx", ".usdz"}:
            suffix = ".glb"
        directory = Path(__file__).resolve().parents[3] / "storage" / "model3d"
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{task_id}{suffix}"
        if target.is_file() and target.stat().st_size:
            return target
        async with httpx.AsyncClient(timeout=self.connector.timeout, follow_redirects=True) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {self.connector.api_key}"} if self.connector.api_key else {})
            response.raise_for_status()
            target.write_bytes(response.content)
        return target
