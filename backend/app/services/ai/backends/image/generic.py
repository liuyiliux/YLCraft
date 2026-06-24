"""
YLCraft - Generic Image Backend

配置驱动的图像生成后端，支持所有 OpenAI 兼容 API
通过数据库中的 request_template 和 response_config 配置
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional, Any, Dict
from pathlib import Path

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
    - response_config (JSON 解析配置)
    - parameter_transforms (参数转换规则)
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
                self.default_params = json.loads(connector.default_params)
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
            for attempt in range(max_retries):
                try:
                    logger.info(f"[GenericImageBackend] 发送请求到 {final_url} (尝试 {attempt + 1}/{max_retries})")
                    temp_client = httpx.AsyncClient(
                        headers={
                            "Authorization": f"Bearer {self.connector.api_key}",
                            "Content-Type": "application/json",
                        },
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

                    if response.status_code in [200, 201]:
                        break
                    if response.status_code == 400:
                        break
                except Exception as e:
                    logger.warning(f"请求异常 (尝试 {attempt + 1}/{max_retries}): {e}")
                    if attempt == max_retries - 1:
                        raise
                    import asyncio
                    await asyncio.sleep(2 ** attempt)

            result = self._parse_response(response)
            call_cost = self.connector.price_per_call if self.connector.price_per_call is not None else result.get("cost", 0.0)
            self._update_usage(call_cost)
            
            actual_model = params.get("model", self.model)

            local_path = None
            image_url = result.get("url")
            all_local_paths = []
            if image_url:
                local_path = await self._download_image(image_url, req.prompt)
                if local_path:
                    all_local_paths.append(str(local_path))

            for idx, url in enumerate(result.get("urls", [])):
                if url != image_url and url:
                    path = await self._download_image(url, f"{req.prompt}_{idx}")
                    if path:
                        all_local_paths.append(str(path))

            return ImageGenerationResult(
                success=result.get("success", False),
                url=image_url,
                urls=result.get("urls", []),
                local_path=local_path,
                all_local_paths=all_local_paths,
                cost=result.get("cost", 0.0),
                provider=self.name,
                model=actual_model,
                error=result.get("error"),
            )

        except Exception as e:
            logger.error(f"图像生成失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return ImageGenerationResult(success=False, error=str(e), provider=self.name, model=self.model)

    async def health_check(self) -> bool:
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
            **self.default_params,
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

        params = self._apply_parameter_transforms(params)
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
        if response.status_code != 200:
            error_msg = self._extract_error(response)
            return {"success": False, "error": f"HTTP {response.status_code}: {error_msg}"}
        try:
            data = response.json()
        except Exception:
            return {"success": False, "error": "响应不是有效的 JSON"}

        images_path = self.response_config.get("images_path", "$.data[*].url")
        response_format = self.response_config.get("response_format", "url")
        
        if response_format == "base64":
            b64_data = self._extract_by_jsonpath(data, images_path, is_list=True)
            if not b64_data:
                return {"success": False, "error": "未能从响应中提取 base64 图像数据"}
            return {"success": True, "url": None, "urls": b64_data, "cost": 0.0, "format": "base64"}
        else:
            urls = self._extract_by_jsonpath(data, images_path, is_list=True)
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
