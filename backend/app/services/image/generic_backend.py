"""
YLCraft - Generic Image Backend

配置驱动的图像生成后端，支持所有 OpenAI 兼容 API
通过数据库中的 request_template 和 response_config 配置
"""
from __future__ import annotations

import json
import logging
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

            return ImageGenerationResult(
                success=result.get("success", False),
                url=result.get("url"),
                urls=result.get("urls", []),
                local_path=None,
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

        # 应用参数转换规则
        params = self._apply_parameter_transforms(params)

        return params

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
            return json.loads(rendered)
        except json.JSONDecodeError as e:
            logger.error(f"请求模板渲染失败: {e}")
            logger.error(f"渲染结果: {rendered}")
            raise

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
