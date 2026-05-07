"""
YLCraft — Live2D API 客户端封装

为抠图、风格转换、图像分割提供统一的API调用接口。
支持多个API服务商：Remove.bg、Replicate、Hugging Face等。
"""
from __future__ import annotations

import os
import json
import base64
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
from io import BytesIO

import requests
from PIL import Image


class APIClientError(Exception):
    """API客户端错误"""
    pass


class RemoveBgClient:
    """Remove.bg API 客户端（抠图）"""

    def __init__(self, api_key: str, api_url: str = "https://api.remove.bg/v1.0/removebg"):
        """
        初始化客户端

        Args:
            api_key: Remove.bg API密钥
            api_url: API端点URL
        """
        self.api_key = api_key
        self.api_url = api_url

    async def remove_background(
        self,
        image: Image.Image,
        size: str = "auto",
        format: str = "png"
    ) -> Image.Image:
        """
        去除图片背景

        Args:
            image: 输入图片（PIL Image）
            size: 输出尺寸（auto, preview, full）
            format: 输出格式（png, jpg）

        Returns:
            去除背景后的图片（RGBA模式）
        """
        # 将图片转换为bytes
        buffer = BytesIO()
        image.convert('RGB').save(buffer, format='PNG')
        buffer.seek(0)

        # 构建请求
        headers = {"X-Api-Key": self.api_key}
        files = {"image_file": ("image.png", buffer, "image/png")}
        data = {"size": size, "format": format}

        # 发送请求（在线程池中执行）
        loop = asyncio.get_event_loop()

        def _do_request():
            response = requests.post(
                self.api_url,
                headers=headers,
                files=files,
                data=data,
                timeout=60
            )

            if response.status_code == 200:
                return response.content
            else:
                raise APIClientError(
                    f"Remove.bg API 错误 {response.status_code}: {response.text}"
                )

        result_bytes = await loop.run_in_executor(None, _do_request)

        # 将结果转换为PIL Image
        result_buffer = BytesIO(result_bytes)
        result_image = Image.open(result_buffer)
        return result_image.convert('RGBA')

    async def remove_background_file(
        self,
        input_path: str | Path,
        output_path: str | Path,
    ) -> Dict[str, Any]:
        """
        处理图片文件

        Args:
            input_path: 输入图片路径
            output_path: 输出图片路径

        Returns:
            处理结果字典
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        # 加载图片
        image = Image.open(input_path)

        # 调用API
        result_image = await self.remove_background(image)

        # 保存结果
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result_image.save(output_path, format='PNG')

        return {
            "result_path": str(output_path),
            "mode": "api",
            "service": "remove.bg"
        }


class ReplicateClient:
    """Replicate API 客户端（风格转换、图像生成）"""

    def __init__(self, api_key: str, api_url: str = "https://api.replicate.com/v1/predictions"):
        """
        初始化客户端

        Args:
            api_key: Replicate API密钥
            api_url: API端点URL
        """
        self.api_key = api_key
        self.api_url = api_url

    async def style_transfer(
        self,
        image: Image.Image,
        prompt: str = "anime style, high quality, detailed face",
        negative_prompt: str = "realistic, photo, low quality",
        model_version: str = "stability-ai/sdxl:7762fd07cf94fe5929fae8bf3b1b78ad6eb85b0b4e3afc9d5ccd6b95a85f6d2",
    ) -> Image.Image:
        """
        风格转换（使用SDXL）

        Args:
            image: 输入图片
            prompt: 正向提示词
            negative_prompt: 反向提示词
            model_version: 模型版本

        Returns:
            风格转换后的图片
        """
        # 将图片转换为base64
        buffer = BytesIO()
        image.convert('RGB').save(buffer, format='PNG')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        image_data_url = f"data:image/png;base64,{image_base64}"

        # 构建请求
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "version": model_version,
            "input": {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "image": image_data_url,
                "num_inference_steps": 20,
            }
        }

        # 发送请求（在线程池中执行）
        loop = asyncio.get_event_loop()

        def _do_request():
            # 创建预测
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code != 201:
                raise APIClientError(
                    f"Replicate API 错误 {response.status_code}: {response.text}"
                )

            prediction = response.json()

            # 轮询预测结果
            get_url = prediction["urls"]["get"]

            while True:
                status_response = requests.get(get_url, headers=headers, timeout=30)
                prediction = status_response.json()

                if prediction["status"] == "succeeded":
                    return prediction["output"]
                elif prediction["status"] == "failed":
                    raise APIClientError(f"Replicate API 处理失败: {prediction.get('error')}")
                else:
                    import time
                    time.sleep(2)

        output_url = await loop.run_in_executor(None, _do_request)

        # 下载结果图片
        if isinstance(output_url, list):
            output_url = output_url[0]

        def _download_image():
            response = requests.get(output_url, timeout=30)
            if response.status_code == 200:
                return response.content
            else:
                raise APIClientError(f"下载结果图片失败: {response.status_code}")

        image_bytes = await loop.run_in_executor(None, _download_image)

        # 转换为PIL Image
        result_buffer = BytesIO(image_bytes)
        result_image = Image.open(result_buffer)
        return result_image.convert('RGB')

    async def style_transfer_file(
        self,
        input_path: str | Path,
        output_path: str | Path,
        **kwargs
    ) -> Dict[str, Any]:
        """
        处理图片文件

        Args:
            input_path: 输入图片路径
            output_path: 输出图片路径
            **kwargs: 传递给style_transfer的参数

        Returns:
            处理结果字典
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        # 加载图片
        image = Image.open(input_path)

        # 调用API
        result_image = await self.style_transfer(image, **kwargs)

        # 保存结果
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result_image.save(output_path, format='PNG')

        return {
            "result_path": str(output_path),
            "mode": "api",
            "service": "replicate",
            "style_type": "anime"
        }


class HuggingFaceClient:
    """Hugging Face Inference API 客户端"""

    def __init__(self, api_key: str, base_url: str = "https://api-inference.huggingface.co/models"):
        """
        初始化客户端

        Args:
            api_key: Hugging Face API密钥
            base_url: API基础URL
        """
        self.api_key = api_key
        self.base_url = base_url

    async def segment_image(
        self,
        image: Image.Image,
        model: str = "ZigBread/BiRefNet"
    ) -> Image.Image:
        """
        图像分割

        Args:
            image: 输入图片
            model: 模型名称

        Returns:
            分割蒙版图片
        """
        # 将图片转换为bytes
        buffer = BytesIO()
        image.convert('RGB').save(buffer, format='PNG')
        buffer.seek(0)
        image_bytes = buffer.read()

        # 构建请求
        headers = {"Authorization": f"Bearer {self.api_key}"}
        api_url = f"{self.base_url}/{model}"

        # 发送请求（在线程池中执行）
        loop = asyncio.get_event_loop()

        def _do_request():
            response = requests.post(
                api_url,
                headers=headers,
                data=image_bytes,
                timeout=60
            )

            if response.status_code == 200:
                return response.content
            elif response.status_code == 503:
                # 模型正在加载
                raise APIClientError("模型正在加载，请稍后重试")
            else:
                raise APIClientError(
                    f"Hugging Face API 错误 {response.status_code}: {response.text}"
                )

        result_bytes = await loop.run_in_executor(None, _do_request)

        # 将结果转换为PIL Image
        result_buffer = BytesIO(result_bytes)
        result_image = Image.open(result_buffer)
        return result_image.convert('L')  # 蒙版是灰度图

    async def segment_file(
        self,
        input_path: str | Path,
        output_path: str | Path,
        model: str = "ZigBread/BiRefNet"
    ) -> Dict[str, Any]:
        """
        处理图片文件

        Args:
            input_path: 输入图片路径
            output_path: 输出图片路径
            model: 模型名称

        Returns:
            处理结果字典
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        # 加载图片
        image = Image.open(input_path)

        # 调用API
        result_image = await self.segment_image(image, model)

        # 保存结果
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result_image.save(output_path, format='PNG')

        return {
            "result_path": str(output_path),
            "mode": "api",
            "service": "huggingface",
            "model": model
        }


async def get_api_client(service: str, config=None):
    """
    获取 API 客户端实例

    Args:
        service: 服务名称（rembg, style_transfer, segmentation）
        config: 配置对象（可选，默认使用全局配置）

    Returns:
        对应的 API 客户端实例
    """
    if config is None:
        from app.core.config import get_live2d_config
        config = get_live2d_config()

    if service == "rembg":
        api_key = await config.get_api_key("rembg")
        api_url = config.get_api_endpoint("rembg")
        model = config.get_api_model("rembg")

        if not api_key:
            raise APIClientError("未配置 Remove.bg API密钥。请在数据库中添加或在 providers.yaml 中设置 REMOVEBG_API_KEY 环境变量。")

        return RemoveBgClient(api_key=api_key, api_url=api_url)

    elif service == "style_transfer":
        api_key = await config.get_api_key("style_transfer")
        api_url = config.get_api_endpoint("style_transfer")
        model = config.get_api_model("style_transfer")

        if not api_key:
            raise APIClientError("未配置 Replicate API密钥。请在数据库中添加或在 providers.yaml 中设置 REPLICATE_API_KEY 环境变量。")

        return ReplicateClient(api_key=api_key, api_url=api_url)

    elif service == "segmentation":
        api_key = await config.get_api_key("segmentation")
        api_url = config.get_api_endpoint("segmentation")
        model = config.get_api_model("segmentation")

        if not api_key:
            raise APIClientError("未配置 Hugging Face API密钥。请在数据库中添加或在 providers.yaml 中设置 HUGGINGFACE_API_KEY 环境变量。")

        return HuggingFaceClient(api_key=api_key, base_url=api_url)

    else:
        raise APIClientError(f"未知的服务: {service}")
