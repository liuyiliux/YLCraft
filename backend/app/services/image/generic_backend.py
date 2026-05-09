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

from app.core.contracts.types import (
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
        """
        初始化通用图像后端
        
        Args:
            connector: AIConnector 数据库记录
            session: SQLAlchemy session (用于更新使用统计)
        """
        # 先调用父类初始化，传入 name 和 model
        super().__init__(name=connector.name, model=connector.default_model)
        
        self.connector = connector
        self.session = session
        # 不要直接设置 self.model，已经在 super().__init__() 中设置了

        # 解析配置
        self.request_template = None
        if connector.request_template:
            self.request_template = Template(connector.request_template)

        # 解析 response_config
        self.response_config = {}
        if connector.response_config:
            try:
                self.response_config = json.loads(connector.response_config)
            except Exception as e:
                logger.error(f"解析 response_config 失败: {e}")

        # 解析 parameter_transforms
        self.parameter_transforms = {}
        if connector.parameter_transforms:
            try:
                self.parameter_transforms = json.loads(connector.parameter_transforms)
            except Exception as e:
                logger.error(f"解析 parameter_transforms 失败: {e}")

        # 解析 supported_sizes
        self.supported_sizes = []
        if connector.supported_sizes:
            try:
                self.supported_sizes = json.loads(connector.supported_sizes)
            except Exception:
                pass

        # 解析 default_params
        self.default_params = {}
        if connector.default_params:
            try:
                self.default_params = json.loads(connector.default_params)
            except Exception as e:
                logger.error(f"解析 default_params 失败: {e}")

        # 参考图配置
        self.support_reference_image = connector.support_reference_image
        self.support_multiple_reference_images = connector.support_multiple_reference_images
        self.reference_image_field = connector.reference_image_field or "image"
        self.reference_image_array_field = connector.reference_image_array_field  # 数组模式字段名

        # 创建 HTTP 客户端
        headers = {}
        if connector.api_key:
            headers["Authorization"] = f"Bearer {connector.api_key}"
        if connector.base_url and "openai.com" in connector.base_url:
            # OpenAI 需要 Content-Type
            headers["Content-Type"] = "application/json"

        self.client = httpx.AsyncClient(
            base_url=connector.base_url or "",
            headers=headers,
            timeout=120.0,
            follow_redirects=True,
        )

        logger.info(f"✅ 初始化 GenericImageBackend: {self.name} (model={self.model})")

    @property
    def capabilities(self) -> set:
        """返回能力集"""
        caps = {"text_to_image"}
        if self.connector.support_reference_image:
            caps.add("image_to_image")
        return caps

    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        """
        生成图像

        Args:
            req: 图像生成请求（支持 req.model 动态指定模型）

        Returns:
            ImageGenerationResult
        """
        try:
            # 1. 准备请求参数（支持动态模型选择控制花费）
            params = self._prepare_params(req)

            # 2. 渲染请求体
            request_body = self._render_request(params)

            logger.debug(f"请求体: {json.dumps(request_body, ensure_ascii=False)[:200]}...")

            # 3. 发送请求
            response = await self.client.post("", json=request_body)

            logger.info(f"响应状态码: {response.status_code}")
            logger.debug(f"响应体: {response.text[:500]}...")

            # 4. 解析响应
            result = self._parse_response(response)

            # 5. 更新使用统计
            self._update_usage(result.get("cost", 0.0))
            
            # 获取实际使用的模型（支持动态模型选择）
            actual_model = params.get("model", self.model)

            # 6. 下载图片到本地
            local_path = None
            image_url = result.get("url")
            if image_url:
                local_path = await self._download_image(image_url, req.prompt)

            return ImageGenerationResult(
                success=result.get("success", False),
                url=image_url,
                urls=result.get("urls", []),
                local_path=local_path,
                cost=result.get("cost", 0.0),
                provider=self.name,
                model=actual_model,
                error=result.get("error"),
            )

        except Exception as e:
            logger.error(f"图像生成失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return ImageGenerationResult(
                success=False,
                error=str(e),
                provider=self.name,
                model=self.model,
            )

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 简单测试请求
            test_params = {
                "model": self.model,
                "prompt": "test",
                "n": 1,
            }
            request_body = self._render_request(test_params)
            response = await self.client.post("", json=request_body)
            return response.status_code == 200
        except Exception:
            return False

    def _prepare_params(self, req: ImageGenerationRequest) -> Dict[str, Any]:
        """
        准备请求参数
        
        支持动态模型选择：
        - 优先使用 req.model（调用时指定）
        - 其次使用 self.model（Connector 默认模型）
        """
        # 支持动态模型选择控制花费
        model = getattr(req, 'model', None) or self.model
        
        params = {
            "model": model,
            "prompt": req.prompt,
            **self.default_params,
        }

        # 添加可选参数
        if req.negative_prompt:
            params["negative_prompt"] = req.negative_prompt

        if req.size:
            params["size"] = req.size

        if req.n and req.n > 0:
            params["n"] = req.n

        if req.seed is not None:
            params["seed"] = req.seed

        # 处理图生图：添加参考图（支持多张）
        reference_images = []
        
        # 收集所有参考图 URL
        image_urls = []
        if req.source_image:
            image_urls.append(req.source_image)
        if req.reference_images:
            image_urls.extend(req.reference_images)
        
        # 转换所有参考图为 base64
        for url in image_urls:
            try:
                base64_image = self._url_to_base64(url)
                reference_images.append(base64_image)
                logger.info(f"[GenericImageBackend] 转换参考图成功: {url[:50]}...")
            except Exception as e:
                logger.warning(f"[GenericImageBackend] 转换参考图失败: {e}")
        
        if reference_images:
            params["reference_images"] = reference_images
            params["reference_image_field"] = self.reference_image_field
            logger.info(f"[GenericImageBackend] 添加 {len(reference_images)} 张参考图，字段名: {self.reference_image_field}")

        # 应用参数转换规则
        params = self._apply_parameter_transforms(params)

        return params

    def _url_to_base64(self, url_or_path: str) -> str:
        """
        将 URL 或本地路径转换为 base64 数据 URI
        
        Args:
            url_or_path: 图片 URL 或本地路径
            
        Returns:
            base64 数据 URI 字符串
        """
        import base64
        from pathlib import Path
        
        # 如果是本地文件路径
        if url_or_path.startswith('/') or url_or_path.startswith('.'):
            file_path = Path(url_or_path)
            if file_path.exists():
                with open(file_path, 'rb') as f:
                    data = f.read()
                ext = file_path.suffix.lower().lstrip('.')
                mime = {
                    'jpg': 'image/jpeg',
                    'jpeg': 'image/jpeg',
                    'png': 'image/png',
                    'gif': 'image/gif',
                    'webp': 'image/webp',
                }.get(ext, 'image/png')
                return f"data:{mime};base64,{base64.b64encode(data).decode()}"
        
        # 如果是 HTTP URL，下载后转换
        if url_or_path.startswith('http://') or url_or_path.startswith('https://'):
            try:
                import asyncio
                # 创建临时文件
                import tempfile
                import os
                import httpx
                
                with httpx.SyncClient(timeout=30.0) as client:
                    response = client.get(url_or_path)
                    response.raise_for_status()
                    data = response.content
                
                # 检测 MIME 类型
                content_type = response.headers.get('content-type', 'image/png')
                ext = content_type.split('/')[-1].split(';')[0]
                if ext == 'jpeg':
                    ext = 'jpeg'
                
                # 返回 base64
                return f"data:{content_type};base64,{base64.b64encode(data).decode()}"
            except Exception as e:
                logger.error(f"下载图片失败: {url_or_path}, 错误: {e}")
                raise
        
        # 如果已经是 base64 数据 URI，直接返回
        if url_or_path.startswith('data:'):
            return url_or_path
        
        raise ValueError(f"不支持的图片格式: {url_or_path}")

    def _apply_parameter_transforms(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """应用参数转换规则"""
        if not self.parameter_transforms:
            return params

        transformed = params.copy()
        for key, transform_template in self.parameter_transforms.items():
            if key in transformed:
                template = Template(transform_template)
                transformed[key] = template.render(**params)
        return transformed

    def _render_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """渲染请求体"""
        if not self.request_template:
            # 默认 OpenAI 格式
            return params

        rendered = self.request_template.render(**params)

        # 解析为 JSON
        try:
            request_body = json.loads(rendered)
        except json.JSONDecodeError as e:
            logger.error(f"请求模板渲染失败: {e}")
            logger.error(f"渲染结果: {rendered}")
            raise

        # 处理参考图：支持两种模式
        # 模式1: 数组模式 - 所有图片放入同一数组字段 (如 {"images": []} 或 {"reference": {"images": []}})
        # 模式2: 占位符模式 - 替换模板中的空占位符 (如 "image1,image2,image")
        reference_images = params.get("reference_images", [])
        
        if reference_images:
            # 优先使用数组模式
            if self.reference_image_array_field:
                # 数组模式：支持嵌套路径，如 "reference.images"
                path_parts = self.reference_image_array_field.split(".")
                
                if len(path_parts) == 1:
                    # 扁平结构: images
                    request_body[self.reference_image_array_field] = reference_images
                else:
                    # 嵌套结构: reference.images → request_body["reference"]["images"]
                    current = request_body
                    for part in path_parts[:-1]:
                        if part not in current:
                            current[part] = {}
                        elif not isinstance(current[part], dict):
                            logger.warning(f"[GenericImageBackend] 嵌套路径 {part} 已存在且非 dict，无法设置")
                            break
                        current = current[part]
                    else:
                        current[path_parts[-1]] = reference_images
                        
                logger.info(f"[GenericImageBackend] 使用数组模式，字段: {self.reference_image_array_field}, 图片数: {len(reference_images)}")
            elif self.reference_image_field:
                # 占位符模式
                reference_image_field = params.get("reference_image_field", self.reference_image_field)
                field_names = [f.strip() for f in reference_image_field.split(",")]
                
                image_field_mapping = []
                for i, img in enumerate(reference_images):
                    field = field_names[i] if i < len(field_names) else field_names[-1]
                    image_field_mapping.append((field, img))
                    logger.info(f"[GenericImageBackend] 参考图 {i + 1} 使用字段: {field}")
                
                self._replace_reference_image_placeholders(
                    request_body, 
                    image_field_mapping
                )

        return request_body

    def _replace_reference_image_placeholders(
        self, 
        obj: Any, 
        image_field_mapping: list,
        replaced_by_field: dict = None
    ) -> dict:
        """
        递归遍历 JSON 对象，替换空的参考图占位符
        
        Args:
            obj: JSON 对象（dict 或 list）
            image_field_mapping: [(字段名, base64图片), ...] 列表
            replaced_by_field: 已替换过的字段及使用次数
            
        Returns:
            已替换的字段统计
        """
        if replaced_by_field is None:
            replaced_by_field = {}
            
        if isinstance(obj, dict):
            for key, value in obj.items():
                # 检查是否是参考图字段且值为空字符串
                for field_name, base64_image in image_field_mapping:
                    if key == field_name and isinstance(value, str) and value == "":
                        # 获取该字段已使用的次数
                        used_count = replaced_by_field.get(field_name, 0)
                        # 使用对应索引的图片
                        if used_count < len([f for f, _ in image_field_mapping if f == field_name]):
                            logger.info(f"[GenericImageBackend] 替换字段 {field_name} 为参考图")
                            obj[key] = base64_image
                            replaced_by_field[field_name] = used_count + 1
                        break
                
                if isinstance(value, (dict, list)):
                    self._replace_reference_image_placeholders(
                        value, image_field_mapping, replaced_by_field
                    )
        elif isinstance(obj, list):
            for item in obj:
                self._replace_reference_image_placeholders(
                    item, image_field_mapping, replaced_by_field
                )
        
        return replaced_by_field

    def _parse_response(self, response: httpx.Response) -> Dict[str, Any]:
        """解析响应"""
        if response.status_code != 200:
            error_msg = self._extract_error(response)
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {error_msg}",
            }

        try:
            data = response.json()
        except Exception:
            return {
                "success": False,
                "error": "响应不是有效的 JSON",
            }

        # 提取图像 URL 或 base64
        images_path = self.response_config.get("images_path", "$.data[*].url")
        response_format = self.response_config.get("response_format", "url")
        
        if response_format == "base64":
            # 处理 base64 格式
            b64_data = self._extract_by_jsonpath(data, images_path, is_list=True)
            if not b64_data:
                return {
                    "success": False,
                    "error": "未能从响应中提取 base64 图像数据",
                }
            
            # TODO: 将 base64 保存为文件，返回 URL
            # 暂时返回 base64 字符串
            return {
                "success": True,
                "url": None,
                "urls": b64_data,  # base64 字符串列表
                "cost": 0.0,
                "format": "base64",
            }
        else:
            # 处理 URL 格式
            urls = self._extract_by_jsonpath(data, images_path, is_list=True)

            if not urls:
                return {
                    "success": False,
                    "error": "未能从响应中提取图像 URL",
                }

            return {
                "success": True,
                "url": urls[0],
                "urls": urls,
                "cost": 0.0,
                "format": "url",
            }

    def _extract_error(self, response: httpx.Response) -> str:
        """提取错误信息"""
        error_path = self.response_config.get("error_path")
        if not error_path:
            return response.text[:200]

        try:
            data = response.json()
            return self._extract_by_jsonpath(data, error_path, is_list=False)
        except Exception:
            return response.text[:200]

    def _extract_by_jsonpath(self, data: Any, path: str, is_list: bool = False):
        """使用 JSONPath 提取数据"""
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
        """更新使用统计"""
        try:
            self.connector.last_used = __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            )
            self.connector.usage_count += 1
            self.connector.total_cost += cost
            self.session.add(self.connector)
            self.session.commit()
        except Exception as e:
            logger.error(f"更新使用统计失败: {e}")

    def __del__(self):
        """清理资源（同步方式）"""
        if hasattr(self, 'client') and self.client:
            # 不要在 __del__ 中尝试关闭异步客户端
            # 应该显式调用 close() 方法
            pass

    async def _download_image(self, url: str, prompt: str) -> Optional[Path]:
        """
        下载图片到本地存储目录
        
        Args:
            url: 图片 URL
            prompt: 提示词（用于生成文件名）
            
        Returns:
            本地文件路径，如果下载失败返回 None
        """
        try:
            # 获取存储目录（优先从配置文件读取 media_storage_path）
            from app.api.v1.settings import _load_settings
            settings = _load_settings()
            
            media_storage_path = settings.get("media_storage_path")
            if media_storage_path and Path(media_storage_path).exists():
                save_dir = Path(media_storage_path) / "images"
            else:
                # 默认路径
                backend_dir = Path(__file__).parent.parent.parent.parent
                save_dir = backend_dir / "storage" / "images"
            
            save_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成文件名（基于时间戳和提示词）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # 从提示词提取一部分作为文件名
            safe_prompt = "".join(c for c in prompt[:20] if c.isalnum() or c in " -_").strip()
            if not safe_prompt:
                safe_prompt = "image"
            
            # 获取文件扩展名
            ext = ".png"
            if url.lower().endswith(".jpg") or url.lower().endswith(".jpeg"):
                ext = ".jpg"
            elif url.lower().endswith(".webp"):
                ext = ".webp"
            elif url.lower().endswith(".gif"):
                ext = ".gif"
            
            filename = f"{timestamp}_{safe_prompt}{ext}"
            local_path = save_dir / filename
            
            # 下载图片
            response = await self.client.get(url)
            response.raise_for_status()
            
            # 保存到本地
            with open(local_path, "wb") as f:
                f.write(response.content)
            
            logger.info(f"图片已保存到本地: {local_path}")
            return local_path
            
        except Exception as e:
            logger.error(f"下载图片失败: {e}")
            return None
