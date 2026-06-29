"""
YLCraft - Generic Image Backend

配置驱动的图像生成后端，支持所有 OpenAI 兼容 API
通过数据库中的 request_template 和 response_config 配置
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
from datetime import datetime
from typing import Optional, Any, Dict
from pathlib import Path
from urllib.parse import quote

import httpx
from jinja2 import Template
from jsonpath_ng import parse as jsonpath_parse

from app.services.ai.types import (
    ImageBackend,
    ImageGenerationRequest,
    ImageGenerationResult,
)
from app.db.models.ai_connector import AIConnector

logger = logging.getLogger("ylcraft.generic_image_backend")


class GenericImageBackend(ImageBackend):
    """
    通用图像生成后端

    通过数据库配置驱动，支持任意 OpenAI 兼容的图像生成 API
    无需为每个 Provider 写代码，只需在数据库中配置：
    - request_template (Jinja2 模板)
    - response_config (JSON 解析配置，含 async_config 异步轮询配置)
    - parameter_transforms (参数转换规则)

    异步生成支持（通过 response_config.async_config 配置）：
    适用于 ModelScope 等先返回 task_id 再轮询结果的 API。
    """

    def __init__(self, connector: AIConnector, session):
        self._name = connector.name
        self._model = connector.default_model or ""
        
        self.connector = connector
        self.session = session

        logger.info(f"[GenericImageBackend] 初始化 connector: {connector.name}, request_template: {connector.request_template}")

        self.request_template = None
        if connector.request_template and connector.request_template.strip():
            self.request_template = Template(connector.request_template)
            logger.info(f"[GenericImageBackend] 成功加载 request_template: {connector.request_template[:200]}...")

        self.response_config = {}
        if connector.response_config:
            try:
                self.response_config = json.loads(connector.response_config)
            except Exception as e:
                logger.error(f"解析 response_config 失败: {e}")

        # 异步轮询配置
        self.async_config = self.response_config.get("async_config") or {}
        self._async_mode = bool(self.async_config)

        self.parameter_transforms = {}
        if connector.parameter_transforms:
            try:
                self.parameter_transforms = json.loads(connector.parameter_transforms)
            except Exception as e:
                logger.error(f"解析 parameter_transforms 失败: {e}")

        self.supported_sizes = []
        if connector.supported_sizes:
            try:
                self.supported_sizes = json.loads(connector.supported_sizes)
            except Exception:
                pass

        self.default_params = {}
        if connector.default_params:
            try:
                parsed_default_params = json.loads(connector.default_params)
                self.default_params = parsed_default_params if isinstance(parsed_default_params, dict) else {}
            except Exception as e:
                logger.error(f"解析 default_params 失败: {e}")

        self.support_reference_image = connector.support_reference_image
        self.support_multiple_reference_images = connector.support_multiple_reference_images
        self.reference_image_field = connector.reference_image_field or "image"
        self.reference_image_array_field = connector.reference_image_array_field
        
        logger.info(f"[GenericImageBackend] 参考图配置: reference_image_field={self.reference_image_field}, reference_image_array_field={self.reference_image_array_field}")

        headers = {}
        if connector.api_key:
            headers["Authorization"] = f"Bearer {connector.api_key}"
        if connector.base_url and "openai.com" in connector.base_url:
            headers["Content-Type"] = "application/json"

        base_url = connector.base_url or ""
        if base_url:
            base_url = base_url.rstrip("/")

        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=connector.timeout,
            follow_redirects=True,
            max_redirects=5,
        )

        logger.info(f"✅ 初始化 GenericImageBackend: {self.name} (model={self.model})")

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    @property
    def capabilities(self) -> set:
        caps = {"text_to_image"}
        if self.connector.support_reference_image:
            caps.add("image_to_image")
        return caps

    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        try:
            params = self._prepare_params(req)
            request_body = self._render_request(params)

            def truncate_base64(obj, max_len=200):
                if isinstance(obj, dict):
                    return {k: truncate_base64(v, max_len) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [truncate_base64(item, max_len) for item in obj]
                elif isinstance(obj, str) and len(obj) > max_len and ("data:image" in obj or len(obj) > 500):
                    return f"{obj[:max_len]}... (base64 已截断，总长度 {len(obj)})"
                return obj

            safe_request_body = truncate_base64(request_body, 200)
            logger.info(f"[GENERIC IMAGE] 请求体: {json.dumps(safe_request_body, ensure_ascii=False)}")

            final_url = self.connector.base_url or ""
            if final_url:
                final_url = final_url.rstrip("/")
            # 拼接 api_endpoint（如果有配置）
            api_endpoint = (self.connector.api_endpoint or "").strip()
            if api_endpoint:
                if not api_endpoint.startswith("/"):
                    api_endpoint = "/" + api_endpoint
                final_url = final_url + api_endpoint

            max_retries = 3
            response = None
            # 异步模式额外请求头（如 ModelScope 的 X-ModelScope-Async-Mode）
            extra_headers = self.async_config.get("request_headers", {}) or {}
            for attempt in range(max_retries):
                try:
                    logger.info(f"[GenericImageBackend] 发送请求到 {final_url} (尝试 {attempt + 1}/{max_retries})")
                    headers = {
                        "Authorization": f"Bearer {self.connector.api_key}",
                        "Content-Type": "application/json",
                        **extra_headers,
                    }
                    temp_client = httpx.AsyncClient(
                        headers=headers,
                        timeout=self.connector.timeout,
                        follow_redirects=True,
                        max_redirects=5,
                    )
                    response = await temp_client.post(final_url, json=request_body)
                    await temp_client.aclose()
                    
                    try:
                        resp_json = response.json()
                        safe_resp = truncate_base64(resp_json, 200)
                        logger.info(f"[GENERIC IMAGE] 响应状态码: {response.status_code}, 内容: {json.dumps(safe_resp, ensure_ascii=False)}")
                    except Exception:
                        logger.info(f"[GENERIC IMAGE] 响应状态码: {response.status_code}, 内容: {response.text[:500]}")

                    if response.status_code in [200, 201, 202]:
                        break
                    if response.status_code == 400:
                        break
                except Exception as e:
                    logger.warning(f"请求异常 (尝试 {attempt + 1}/{max_retries}): {e}")
                    if attempt == max_retries - 1:
                        raise
                    import asyncio
                    await asyncio.sleep(2 ** attempt)

            # 判断是否需要异步轮询
            if self._async_mode:
                task_result = await self._handle_async_response(response, final_url)
                if task_result is not None:
                    # 异步响应：可能是 pending 任务，也可能首次响应已经完成
                    parsed = task_result
                else:
                    # 同步完成或非异步响应，走正常解析
                    parsed = self._parse_response(response)
            else:
                parsed = self._parse_response(response)

            result = parsed
            call_cost = self.connector.price_per_call if self.connector.price_per_call is not None else result.get("cost", 0.0)
            self._update_usage(call_cost)
            
            actual_model = params.get("model", self.model)

            if result.get("task_id") and result.get("status") == "pending":
                return ImageGenerationResult(
                    success=True,
                    task_id=result.get("task_id", ""),
                    cost=result.get("cost", 0.0),
                    provider=self.name,
                    model=actual_model,
                    status="pending",
                    progress=result.get("progress", 0.0),
                    error=result.get("error"),
                )

            local_path = None
            image_url = result.get("url")
            image_urls = result.get("urls", []) or []
            all_local_paths = []

            if result.get("format") == "base64":
                preview_urls = []
                output_format = result.get("output_format") or "png"
                for idx, b64_data in enumerate(image_urls):
                    path = self._save_base64_image(
                        b64_data=b64_data,
                        prompt=req.prompt,
                        index=idx,
                        output_format=output_format,
                    )
                    if path:
                        path_str = str(path)
                        all_local_paths.append(path_str)
                        preview_urls.append(self._local_file_url(path_str))
                        if local_path is None:
                            local_path = path_str

                image_url = preview_urls[0] if preview_urls else None
                image_urls = preview_urls
                if result.get("success") and not all_local_paths:
                    result["success"] = False
                    result["error"] = "base64 image save failed"
            else:
                if image_url:
                    downloaded_path = await self._download_image(image_url, req.prompt)
                    if downloaded_path:
                        local_path = str(downloaded_path)
                        all_local_paths.append(str(downloaded_path))

                for idx, url in enumerate(image_urls):
                    if url != image_url and url:
                        path = await self._download_image(url, f"{req.prompt}_{idx}")
                        if path:
                            all_local_paths.append(str(path))

            return ImageGenerationResult(
                success=result.get("success", False),
                url=image_url,
                urls=image_urls,
                local_path=local_path,
                all_local_paths=all_local_paths,
                cost=result.get("cost", 0.0),
                provider=self.name,
                model=actual_model,
                task_id=result.get("task_id", ""),
                status=result.get("status", "done" if result.get("success", False) else "error"),
                progress=result.get("progress", 100.0 if result.get("success", False) else 0.0),
                error=result.get("error"),
            )

        except Exception as e:
            logger.error(f"图像生成失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return ImageGenerationResult(success=False, error=str(e), provider=self.name, model=self.model)

    # -------------------------------------------------------------------------
    # 异步轮询支持（ModelScope 等先返回 task_id 再轮询结果的 API）
    # -------------------------------------------------------------------------

    def _has_async_response(self, data: dict) -> str | None:
        """检测响应是否包含异步任务 task_id。

        返回 task_id（有异步任务）或 None（无异步任务/同步完成）。
        如果 status 已经是终态（done/failed），仍返回 task_id，由调用方判断。
        """
        task_id_path = self.async_config.get("task_id_path", "")
        if not task_id_path:
            return None
        task_id = self._extract_single_jsonpath(data, task_id_path)
        return task_id if task_id else None

    def _is_async_done(self, data: dict) -> bool:
        """检查异步任务是否已完成。"""
        status_path = self.async_config.get("status_path", "")
        done_value = self.async_config.get("done_value", "SUCCEED")
        if not status_path:
            return False
        status = self._extract_single_jsonpath(data, status_path)
        return status is not None and str(status).upper() == str(done_value).upper()

    def _is_async_failed(self, data: dict) -> str | None:
        """检查异步任务是否失败，返回错误信息。"""
        status_path = self.async_config.get("status_path", "")
        failed_value = self.async_config.get("failed_value", "FAILED")
        if not status_path:
            return None
        status = self._extract_single_jsonpath(data, status_path)
        if status is not None and str(status).upper() == str(failed_value).upper():
            return self._extract_async_error(data)
        return None

    def _extract_async_error(self, data: dict) -> str:
        """从异步任务响应中提取失败原因。"""
        error_path = self.async_config.get("error_path", "")
        if error_path:
            value = self._extract_single_jsonpath(data, error_path)
            if value:
                return str(value)
        for key in ("message", "error", "error_message", "err_msg"):
            value = data.get(key)
            if value:
                return str(value)
        return "任务失败"

    def _extract_async_images(self, data: dict) -> list[str]:
        """从异步任务完成响应中提取图片 URL 列表。"""
        images_path = self.async_config.get("images_path", "")
        if not images_path:
            return []
        return self._extract_by_jsonpath(data, images_path, is_list=True)

    async def _handle_async_response(
        self, response: httpx.Response, base_url: str
    ) -> dict | None:
        """
        处理首次请求的响应，如果检测到异步任务则返回任务状态。

        返回 None 表示响应不是异步任务（回退到普通 _parse_response）。
        返回 dict 表示异步任务已处理，包含 pending 任务或已完成结果。
        """
        try:
            data = response.json()
        except Exception:
            return None  # 非 JSON 响应，回退普通处理

        task_id = self._has_async_response(data)
        if not task_id:
            logger.info("[GenericImageBackend] 未检测到异步任务，按同步响应处理")
            return None

        logger.info(f"[GenericImageBackend] 检测到异步任务 task_id={task_id}")

        # 检查首次响应是否已经完成（简单 prompt 可能立即返回结果）
        if self._is_async_done(data):
            logger.info(f"[GenericImageBackend] 首次响应即完成 task_id={task_id}")
            images = self._extract_async_images(data)
            if images:
                return {
                    "success": True,
                    "url": images[0],
                    "urls": images,
                    "cost": 0.0,
                    "format": "url",
                    "task_id": task_id,
                    "status": "done",
                    "progress": 100.0,
                }
            # 使用普通解析作为回退
            return None

        # 检查是否失败
        error_msg = self._is_async_failed(data)
        if error_msg:
            logger.error(f"[GenericImageBackend] 任务创建失败 task_id={task_id}: {error_msg}")
            return {"success": False, "error": error_msg, "task_id": task_id, "status": "error"}

        logger.info(f"[GenericImageBackend] 异步任务已创建 task_id={task_id}")
        return {
            "success": True,
            "task_id": task_id,
            "status": "pending",
            "progress": 0.0,
            "cost": 0.0,
        }

    async def poll(self, task_id: str) -> ImageGenerationResult:
        """轮询异步图像生成任务状态。

        由 generate() 内部调用，也可由 API 层直接调用供前端手动轮询。
        """
        if not self._async_mode:
            return ImageGenerationResult(
                success=False, error="当前 Backend 未启用异步模式",
                task_id=task_id, provider=self.name, model=self.model,
            )

        poll_endpoint_template = self.async_config.get("poll_endpoint", "")
        if not poll_endpoint_template:
            return ImageGenerationResult(
                success=False, error="未配置 poll_endpoint",
                task_id=task_id, provider=self.name, model=self.model,
            )

        poll_endpoint = poll_endpoint_template.replace("{task_id}", task_id)
        poll_method = self.async_config.get("poll_method", "GET").upper()
        poll_headers = self.async_config.get("poll_headers", {}) or {}

        # 拼接完整 URL
        base = (self.connector.base_url or "").rstrip("/")
        if not poll_endpoint.startswith("http"):
            poll_endpoint = poll_endpoint.lstrip("/")
            poll_url = f"{base}/{poll_endpoint}"
        else:
            poll_url = poll_endpoint

        headers = {
            "Authorization": f"Bearer {self.connector.api_key}",
            "Content-Type": "application/json",
            **poll_headers,
        }

        try:
            async with httpx.AsyncClient(
                headers=headers,
                timeout=self.connector.timeout,
                follow_redirects=True,
            ) as client:
                if poll_method == "GET":
                    resp = await client.get(poll_url)
                elif poll_method == "POST":
                    resp = await client.post(poll_url, json={})
                else:
                    return ImageGenerationResult(
                        success=False, error=f"不支持的轮询方法: {poll_method}",
                        task_id=task_id, provider=self.name, model=self.model,
                    )

            if resp.status_code not in (200, 201, 202):
                return ImageGenerationResult(
                    success=False, error=f"轮询失败 HTTP {resp.status_code}: {resp.text[:200]}",
                    task_id=task_id, provider=self.name, model=self.model,
                )

            data = resp.json()
            logger.info(f"[GenericImageBackend] 轮询响应 task_id={task_id}: {self._truncate_debug(data)}")

            done_value = self.async_config.get("done_value", "SUCCEED")
            failed_value = self.async_config.get("failed_value", "FAILED")
            status_path = self.async_config.get("status_path", "")

            status = "pending"
            if status_path:
                raw_status = self._extract_single_jsonpath(data, status_path)
                if raw_status is not None:
                    raw_status = str(raw_status).upper()
                    if raw_status == str(done_value).upper():
                        status = "done"
                    elif raw_status == str(failed_value).upper():
                        status = "error"
                    else:
                        status = "pending"

            if status == "error":
                error_msg = self._extract_async_error(data)
                return ImageGenerationResult(
                    success=False, error=error_msg or "任务失败", status="error",
                    task_id=task_id, provider=self.name, model=self.model,
                )

            if status == "done":
                images = self._extract_async_images(data)
                url = images[0] if images else None
                local_path = None
                all_local_paths = []
                for idx, image_url in enumerate(images):
                    downloaded_path = await self._download_image(image_url, f"{task_id}_{idx}")
                    if downloaded_path:
                        path_str = str(downloaded_path)
                        all_local_paths.append(path_str)
                        if local_path is None:
                            local_path = path_str
                return ImageGenerationResult(
                    success=True,
                    url=url,
                    urls=images,
                    local_path=local_path,
                    all_local_paths=all_local_paths,
                    status="done",
                    progress=100.0,
                    task_id=task_id, provider=self.name, model=self.model,
                )

            return ImageGenerationResult(
                success=True, status="pending",
                task_id=task_id, provider=self.name, model=self.model,
            )

        except Exception as e:
            logger.error(f"[GenericImageBackend] 轮询异常 task_id={task_id}: {e}")
            return ImageGenerationResult(
                success=False, error=str(e),
                task_id=task_id, provider=self.name, model=self.model,
            )

    @staticmethod
    def _extract_single_jsonpath(data: dict, path: str) -> str | None:
        """从 JSON 中提取单个值。"""
        try:
            expr = jsonpath_parse(path)
            matches = expr.find(data)
            return str(matches[0].value) if matches else None
        except Exception:
            return None

    @staticmethod
    def _truncate_debug(obj, max_len=300) -> str:
        """截断调试输出，避免过长。"""
        s = json.dumps(obj, ensure_ascii=False)
        if len(s) > max_len:
            s = s[:max_len] + "..."
        return s

    async def health_check(self) -> bool:
        if self._async_mode:
            return True
        try:
            test_params = {"model": self.model, "prompt": "test", "n": 1}
            request_body = self._render_request(test_params)
            # 拼接 api_endpoint（如果有配置）
            api_endpoint = (self.connector.api_endpoint or "").strip()
            if api_endpoint and not api_endpoint.startswith("/"):
                api_endpoint = "/" + api_endpoint
            response = await self.client.post(api_endpoint, json=request_body)
            return response.status_code == 200
        except Exception:
            return False

    def _prepare_params(self, req: ImageGenerationRequest) -> Dict[str, Any]:
        model = getattr(req, 'model', None) or self.model or ""
        
        params = {
            "model": model,
            "prompt": req.prompt,
            **(self.default_params or {}),
        }

        if req.negative_prompt:
            params["negative_prompt"] = req.negative_prompt
        if req.size:
            params["size"] = req.size
        if req.n and req.n > 0:
            params["n"] = req.n
        if req.seed is not None:
            params["seed"] = req.seed

        reference_images = []
        image_urls = []
        if req.source_image:
            image_urls.append(req.source_image)
        if req.reference_images:
            image_urls.extend(req.reference_images)
        
        for url in image_urls:
            try:
                base64_image = self._url_to_base64(url)
                reference_images.append(base64_image)
            except Exception as e:
                logger.warning(f"[GenericImageBackend] 转换参考图失败: {e}")
        
        if reference_images:
            params["reference_images"] = reference_images
            params["reference_image_field"] = self.reference_image_field

        raw_size = params.get("size")
        params = self._apply_parameter_transforms(params)
        if raw_size != params.get("size") or self.parameter_transforms:
            logger.info(
                "[GenericImageBackend] size 参数诊断 | provider=%s | model=%s | req_size=%s | params_size=%s | transforms=%s",
                self.name,
                model,
                raw_size,
                params.get("size"),
                self.parameter_transforms,
            )
        return params

    def _url_to_base64(self, url_or_path: str) -> str:
        import base64
        from pathlib import Path
        
        if url_or_path.startswith('data:'):
            return url_or_path
        
        if url_or_path.startswith('/api/') or url_or_path.startswith('api/'):
            try:
                import httpx, os
                base_url = os.environ.get('BASE_URL', 'http://localhost:8000')
                full_url = f"{base_url.rstrip('/')}/{url_or_path.lstrip('/')}" if not url_or_path.startswith('http') else url_or_path
                with httpx.SyncClient(timeout=30.0, follow_redirects=True) as client:
                    response = client.get(full_url)
                    response.raise_for_status()
                    data = response.content
                content_type = response.headers.get('content-type', 'image/png')
                return f"data:{content_type};base64,{base64.b64encode(data).decode()}"
            except Exception as e:
                raise ValueError(f"通过代理下载图片失败: {e}")
        
        if url_or_path.startswith('/') or url_or_path.startswith('.'):
            file_path = Path(url_or_path)
            if file_path.exists():
                with open(file_path, 'rb') as f:
                    data = f.read()
                ext = file_path.suffix.lower().lstrip('.')
                mime = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'gif': 'image/gif', 'webp': 'image/webp'}.get(ext, 'image/png')
                return f"data:{mime};base64,{base64.b64encode(data).decode()}"
        
        if url_or_path.startswith('http://') or url_or_path.startswith('https://'):
            try:
                import httpx
                with httpx.SyncClient(timeout=30.0, follow_redirects=True) as client:
                    response = client.get(url_or_path)
                    response.raise_for_status()
                    data = response.content
                content_type = response.headers.get('content-type', 'image/png')
                return f"data:{content_type};base64,{base64.b64encode(data).decode()}"
            except Exception as e:
                raise
        
        raise ValueError(f"不支持的图片格式: {url_or_path}")

    def _apply_parameter_transforms(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.parameter_transforms:
            return params
        transformed = params.copy()
        for key, transform_template in self.parameter_transforms.items():
            if key in transformed:
                template = Template(transform_template)
                transformed[key] = template.render(**params)
        return transformed

    def _render_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.request_template:
            if params.get("reference_images") and len(params.get("reference_images", [])) > 0:
                params["image"] = params["reference_images"][0]
            return params

        rendered = self.request_template.render(**params)
        try:
            request_body = json.loads(rendered)
        except json.JSONDecodeError as e:
            logger.error(f"请求模板渲染失败: {e}")
            raise

        param_mapping = {
            "size": self.default_params.get("size_param", "size"),
            "seed": self.default_params.get("seed_param", "seed"),
            "n": self.default_params.get("n_param", "n"),
            "negative_prompt": self.default_params.get("negative_prompt_param", "negative_prompt"),
        }
        for internal_key, api_key in param_mapping.items():
            if internal_key in params and params[internal_key] and api_key not in request_body:
                request_body[api_key] = params[internal_key]

        if params.get("size") or request_body.get(param_mapping["size"]):
            logger.info(
                "[GenericImageBackend] request size 诊断 | provider=%s | params_size=%s | body_key=%s | body_size=%s",
                self.name,
                params.get("size"),
                param_mapping["size"],
                request_body.get(param_mapping["size"]),
            )

        reference_images = params.get("reference_images", [])
        if reference_images:
            if self.reference_image_array_field:
                path_parts = self.reference_image_array_field.split(".")
                if len(path_parts) == 1:
                    request_body[self.reference_image_array_field] = reference_images
                else:
                    current = request_body
                    for part in path_parts[:-1]:
                        if part not in current:
                            current[part] = {}
                        elif not isinstance(current[part], dict):
                            break
                        current = current[part]
                    else:
                        current[path_parts[-1]] = reference_images
            elif self.reference_image_field:
                reference_image_field = params.get("reference_image_field", self.reference_image_field)
                field_names = [f.strip() for f in reference_image_field.split(",")]
                image_field_mapping = [(field_names[i] if i < len(field_names) else field_names[-1], img) for i, img in enumerate(reference_images)]
                self._replace_reference_image_placeholders(request_body, image_field_mapping)
            if reference_images and ("image" not in request_body or not request_body["image"]):
                request_body["image"] = reference_images[0]

        return request_body

    def _replace_reference_image_placeholders(self, obj: Any, image_field_mapping: list, replaced_by_field: dict = None) -> dict:
        if replaced_by_field is None:
            replaced_by_field = {}
        if isinstance(obj, dict):
            for key, value in obj.items():
                for field_name, base64_image in image_field_mapping:
                    if key == field_name and isinstance(value, str) and value == "":
                        used_count = replaced_by_field.get(field_name, 0)
                        if used_count < len([f for f, _ in image_field_mapping if f == field_name]):
                            obj[key] = base64_image
                            replaced_by_field[field_name] = used_count + 1
                            break
                if isinstance(value, (dict, list)):
                    self._replace_reference_image_placeholders(value, image_field_mapping, replaced_by_field)
        elif isinstance(obj, list):
            for item in obj:
                self._replace_reference_image_placeholders(item, image_field_mapping, replaced_by_field)
        return replaced_by_field

    def _parse_response(self, response: httpx.Response) -> Dict[str, Any]:
        if response.status_code not in (200, 201, 202):
            error_msg = self._extract_error(response)
            return {"success": False, "error": f"HTTP {response.status_code}: {error_msg}"}
        try:
            data = response.json()
        except Exception:
            return {"success": False, "error": "响应不是有效的 JSON"}

        images_path = self.response_config.get("images_path", "$.data[*].url")
        response_format = self.response_config.get("response_format", "url")
        output_format = self.response_config.get("output_format") or data.get("output_format") or "png"
        
        if response_format == "base64":
            b64_data = self._extract_by_jsonpath(data, images_path, is_list=True)
            if not b64_data:
                b64_path = self.response_config.get("base64_images_path", "$.data[*].b64_json")
                if b64_path != images_path:
                    b64_data = self._extract_by_jsonpath(data, b64_path, is_list=True)
            if not b64_data:
                return {"success": False, "error": "未能从响应中提取 base64 图像数据"}
            return {
                "success": True,
                "url": None,
                "urls": b64_data,
                "cost": 0.0,
                "format": "base64",
                "output_format": output_format,
            }
        else:
            urls = self._extract_by_jsonpath(data, images_path, is_list=True)
            if urls:
                return {"success": True, "url": urls[0], "urls": urls, "cost": 0.0, "format": "url"}

            b64_path = self.response_config.get("base64_images_path", "$.data[*].b64_json")
            b64_data = self._extract_by_jsonpath(data, b64_path, is_list=True)
            if b64_data:
                return {
                    "success": True,
                    "url": None,
                    "urls": b64_data,
                    "cost": 0.0,
                    "format": "base64",
                    "output_format": output_format,
                }
            if not urls:
                return {"success": False, "error": "未能从响应中提取图像 URL"}
            return {"success": True, "url": urls[0], "urls": urls, "cost": 0.0, "format": "url"}

    def _extract_error(self, response: httpx.Response) -> str:
        error_path = self.response_config.get("error_path")
        if not error_path:
            return response.text[:200]
        try:
            data = response.json()
            return self._extract_by_jsonpath(data, error_path, is_list=False)
        except Exception:
            return response.text[:200]

    def _extract_by_jsonpath(self, data: Any, path: str, is_list: bool = False):
        try:
            expr = jsonpath_parse(path)
            matches = expr.find(data)
            if is_list:
                return [match.value for match in matches]
            else:
                return matches[0].value if matches else None
        except Exception as e:
            logger.error(f"JSONPath 解析失败: {path}, 错误: {e}")
            return None

    def _update_usage(self, cost: float = 0.0):
        try:
            from app.db.database import get_session
            db_session = next(get_session())
            from app.db.models.ai_connector import AIConnector
            fresh_conn = db_session.query(AIConnector).filter(AIConnector.id == self.connector.id).first()
            if fresh_conn:
                fresh_conn.last_used = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                fresh_conn.usage_count += 1
                fresh_conn.total_cost += cost
                db_session.add(fresh_conn)
                db_session.commit()
                logger.info(f"[GenericImageBackend] 已更新使用统计 | id={fresh_conn.id} | 次数+1 | 本次花费={cost} | 累计总花费={fresh_conn.total_cost}")
        except Exception as e:
            logger.error(f"更新使用统计失败: {e}")

    def _save_base64_image(
        self,
        b64_data: str,
        prompt: str,
        index: int = 0,
        output_format: str = "png",
    ) -> Optional[Path]:
        try:
            backend_dir = Path(__file__).parent.parent.parent.parent.parent
            save_dir = backend_dir / "storage" / "images"
            save_dir.mkdir(parents=True, exist_ok=True)

            ext = self._ext_from_output_format(output_format)
            data = b64_data
            if b64_data.startswith("data:"):
                header, data = b64_data.split(",", 1)
                mime_type = header.split(";")[0].replace("data:", "") or ""
                ext = self._ext_from_output_format(mime_type)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_prompt = "".join(c for c in prompt[:20] if c.isalnum() or c in " -_").strip().replace(" ", "_") or "image"
            filename = f"{timestamp}_{safe_prompt}_{index}{ext}"
            local_path = save_dir / filename
            local_path.write_bytes(base64.b64decode(data))
            logger.info(f"base64 图片已保存到本地: {local_path}")
            return local_path
        except Exception as e:
            logger.error(f"保存 base64 图片失败: {e}")
            return None

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

    async def _download_image(self, url: str, prompt: str) -> Optional[Path]:
        try:
            backend_dir = Path(__file__).parent.parent.parent.parent.parent
            save_dir = backend_dir / "storage" / "images"
            save_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_prompt = "".join(c for c in prompt[:20] if c.isalnum() or c in " -_").strip() or "image"
            
            ext = ".png"
            if url.lower().endswith(".jpg") or url.lower().endswith(".jpeg"):
                ext = ".jpg"
            elif url.lower().endswith(".webp"):
                ext = ".webp"
            elif url.lower().endswith(".gif"):
                ext = ".gif"
            
            filename = f"{timestamp}_{safe_prompt}{ext}"
            local_path = save_dir / filename
            
            async with httpx.AsyncClient(timeout=self.connector.timeout, follow_redirects=True) as temp_download_client:
                response = await temp_download_client.get(url)
                response.raise_for_status()
                with open(local_path, "wb") as f:
                    f.write(response.content)
            
            logger.info(f"图片已保存到本地: {local_path}")
            return local_path
            
        except Exception as e:
            logger.error(f"下载图片失败: {e}")
            return None
