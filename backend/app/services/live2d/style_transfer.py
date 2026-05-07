"""
YLCraft — Live2D 风格转换服务

支持两种处理方式：
1. 本地模式 - 使用 AnimeGANv2 或 Stable Diffusion + ControlNet
2. API 模式 - 使用 Replicate API（SDXL）

实现方案：
- 本地 AnimeGANv2 - 轻量级实时转换（优先）
- 本地 SD + ControlNet - 高质量转换（备选）
- API Replicate - 云端高质量转换

模型下载：
- AnimeGAN: https://github.com/TachibanaYoshino/AnimeGANv2
- ControlNet: https://huggingface.co/lllyasviel/ControlNet
- Replicate: https://replicate.com
"""

from __future__ import annotations

import os
import asyncio
import tempfile
from pathlib import Path
from typing import Optional, Literal
from dataclasses import dataclass

import numpy as np
from PIL import Image

# 尝试导入相关库
try:
    import torch
    from diffusers import StableDiffusionControlNetPipeline, ControlNetModel
    from controlnet_aux import CannyDetector, OpenposeDetector
    DIFFUSERS_AVAILABLE = True
except ImportError:
    DIFFUSERS_AVAILABLE = False
    torch = None
    StableDiffusionControlNetPipeline = None

# 导入配置和API客户端
from app.core.config import ProcessingMode, get_live2d_config
from app.services.live2d.api_client import ReplicateClient, APIClientError


# 模型缓存目录
MODEL_CACHE_DIR = Path.home() / ".cache" / "ylcraft" / "models" / "style_transfer"


@dataclass
class StyleTransferResult:
    """风格转换结果"""
    original_image: Image.Image  # 原始图片
    stylized_image: Image.Image  # 风格化后的图片
    style_type: str  # 风格类型
    processing_time: float  # 处理时间（秒）


class StyleTransferMode:
    """风格转换模式（本地模式）"""
    ANIMEGAN = "animegan"           # AnimeGAN 快速转换
    SD_CONTROLNET = "sd_controlnet"  # SD + ControlNet 高质量

    @classmethod
    def all(cls):
        return [cls.ANIMEGAN, cls.SD_CONTROLNET]


class StyleTransferService:
    """风格转换服务（支持本地/API切换）"""

    def __init__(
        self,
        mode: str = ProcessingMode.LOCAL.value,
        local_mode: str = "sd_controlnet",
        config=None
    ):
        """
        初始化风格转换服务

        Args:
            mode: 处理模式（local 或 api）
            local_mode: 本地模式类型（animegan 或 sd_controlnet）
            config: 配置对象（可选，默认使用全局配置）
        """
        self.mode = mode
        self.local_mode = local_mode
        self.pipe = None
        self.device = "cuda" if torch and torch.cuda.is_available() else "cpu"
        self.config = config or get_live2d_config()
        self._api_client = None

    async def _get_api_client(self) -> ReplicateClient:
        """获取API客户端（异步）"""
        if self._api_client is None:
            api_key = await self.config.get_api_key("style_transfer")
            api_url = self.config.get_api_endpoint("style_transfer")
            if not api_key:
                raise APIClientError("未配置 Replicate API密钥。请在数据库中添加或在 providers.yaml 中设置 REPLICATE_API_KEY 环境变量。")
            self._api_client = ReplicateClient(
                api_key=api_key,
                api_url=api_url
            )
        return self._api_client

    def _load_animegan(self):
        """加载 AnimeGAN 模型"""
        # TODO: 实现 AnimeGAN 加载
        # 可用开源实现：
        # - https://github.com/TachibanaYoshino/AnimeGANv2
        # - https://github.com/忍受黎明/AnimeGANv3
        raise NotImplementedError(
            "AnimeGAN 模式尚未实现。\n"
            "请使用 sd_controlnet 模式，或手动实现 AnimeGAN。\n"
            "开源实现参考：https://github.com/TachibanaYoshino/AnimeGANv2"
        )

    async def _load_sd_controlnet(self):
        """加载 Stable Diffusion + ControlNet 模型"""
        if not DIFFUSERS_AVAILABLE:
            raise RuntimeError(
                "diffusers 库未安装。请运行: pip install diffusers transformers accelerate\n"
                "并安装 ControlNet 相关模型。"
            )

        if self.pipe is not None:
            return

        print(f"正在加载 Stable Diffusion + ControlNet 模型到 {self.device}...")

        # 加载 ControlNet（使用 Canny 边缘检测）
        controlnet = ControlNetModel.from_pretrained(
            "lllyasviel/sd-controlnet-canny",
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
        )

        # 加载 Stable Diffusion v1.5
        pipe = StableDiffusionControlNetPipeline.from_pretrained(
            "runwayml/stable-diffusion-v1-5",
            controlnet=controlnet,
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
        )

        if self.device == "cuda":
            pipe = pipe.to("cuda")
            # 启用内存优化
            try:
                pipe.enable_attention_slicing()
            except Exception:
                pass
        else:
            pipe = pipe.to("cpu")

        self.pipe = pipe
        print("模型加载完成！")

    def _ensure_model_loaded(self):
        """确保模型已加载"""
        if self.mode == StyleTransferMode.ANIMEGAN:
            if self.pipe is None:
                self._load_animegan()
        else:
            if self.pipe is None:
                asyncio.create_task(self._load_sd_controlnet())

    async def _preprocess_image(self, image: Image.Image) -> np.ndarray:
        """预处理图片"""
        # 调整图片大小到合理范围
        max_size = 1024
        if max(image.size) > max_size:
            ratio = max_size / max(image.size)
            new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
            image = image.resize(new_size, Image.Resampling.LANCZOS)

        return np.array(image)

    async def _generate_canny_edge(self, image: Image.Image) -> Image.Image:
        """生成 Canny 边缘图"""
        import cv2

        # 转换为 numpy 数组
        img_array = np.array(image.convert('RGB'))

        # 边缘检测
        img_gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        img_canny = cv2.Canny(img_gray, 100, 200)

        # 转换回 PIL Image
        result = Image.fromarray(img_canny)
        return result

    async def transfer_style(
        self,
        image: Image.Image,
        prompt: str = "anime style, high quality, detailed face, vibrant colors",
        negative_prompt: str = "realistic, photo, low quality, blurry, deformed",
        num_inference_steps: int = 20,
        guidance_scale: float = 7.5,
        seed: Optional[int] = None,
    ) -> StyleTransferResult:
        """
        风格转换

        Args:
            image: 输入图片
            prompt: 正向提示词
            negative_prompt: 反向提示词
            num_inference_steps: 推理步数
            guidance_scale: 引导强度
            seed: 随机种子

        Returns:
            StyleTransferResult: 转换结果
        """
        import time
        start_time = time.time()

        # 根据模式选择处理方式
        if self.mode == ProcessingMode.API.value:
            return await self._transfer_style_api(
                image, prompt, negative_prompt
            )
        else:
            return await self._transfer_style_local(
                image, prompt, negative_prompt,
                num_inference_steps, guidance_scale, seed,
                start_time
            )

    async def _transfer_style_local(
        self,
        image: Image.Image,
        prompt: str,
        negative_prompt: str,
        num_inference_steps: int,
        guidance_scale: float,
        seed: Optional[int],
        start_time: float,
    ) -> StyleTransferResult:
        """本地模式：使用SD+ControlNet或AnimeGAN"""
        if self.local_mode == "animegan":
            self._load_animegan()
            raise NotImplementedError("AnimeGAN mode not implemented yet")
        else:
            await self._load_sd_controlnet()

            # 预处理
            image = image.convert('RGB')
            if max(image.size) > 1024:
                ratio = 1024 / max(image.size)
                image = image.resize(
                    (int(image.size[0] * ratio), int(image.size[1] * ratio)),
                    Image.Resampling.LANCZOS
                )

            # 生成边缘图
            control_image = await self._generate_canny_edge(image)

            # 设置种子
            if seed is None:
                seed = np.random.randint(0, 2**32 - 1)

            generator = torch.Generator(device=self.device).manual_seed(seed)

            # 执行推理（在线程池中）
            loop = asyncio.get_event_loop()

            def _do_inference():
                return self.pipe(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    image=control_image,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                    generator=generator,
                ).images[0]

            result_image = await loop.run_in_executor(None, _do_inference)

        processing_time = time.time() - start_time

        return StyleTransferResult(
            original_image=image,
            stylized_image=result_image,
            style_type=self.local_mode,
            processing_time=processing_time,
        )

    async def _transfer_style_api(
        self,
        image: Image.Image,
        prompt: str,
        negative_prompt: str,
    ) -> StyleTransferResult:
        """API模式：使用Replicate API"""
        import time
        start_time = time.time()

        client = await self._get_api_client()

        # 调用API
        result_image = await client.style_transfer(
            image=image,
            prompt=prompt,
            negative_prompt=negative_prompt,
        )

        processing_time = time.time() - start_time

        return StyleTransferResult(
            original_image=image,
            stylized_image=result_image,
            style_type="api",
            processing_time=processing_time,
        )

    async def transfer_style_file(
        self,
        input_path: str | Path,
        output_path: str | Path,
        **kwargs
    ) -> dict:
        """
        处理图片文件

        Args:
            input_path: 输入图片路径
            output_path: 输出图片路径

        Returns:
            dict: 处理结果
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        # 加载图片
        image = Image.open(input_path)

        # 执行转换
        result = await self.transfer_style(image, **kwargs)

        # 保存结果
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.stylized_image.save(output_path, format='PNG')

        return {
            "result_path": str(output_path),
            "style_type": result.style_type,
            "processing_time": result.processing_time,
            "mode": self.mode,
        }


# 全局服务实例
_service_instances: dict[str, StyleTransferService] = {}


def get_style_transfer_service(
    mode: str = ProcessingMode.LOCAL.value,
    local_mode: str = "sd_controlnet"
) -> StyleTransferService:
    """获取风格转换服务实例"""
    key = f"{mode}_{local_mode}"
    if key not in _service_instances:
        _service_instances[key] = StyleTransferService(mode=mode, local_mode=local_mode)
    return _service_instances[key]


async def process_image(
    input_path: str | Path,
    output_dir: str | Path,
    mode: str = "sd_controlnet",
    **kwargs
) -> dict:
    """
    便捷函数：处理图片风格转换

    Args:
        input_path: 输入图片路径
        output_dir: 输出目录
        mode: 转换模式

    Returns:
        dict: 处理结果
    """
    service = get_style_transfer_service(mode=mode)

    input_path = Path(input_path)
    output_dir = Path(output_dir)

    # 输出文件名
    style_suffix = "anime" if mode == "animegan" else "anime_hq"
    output_name = f"{input_path.stem}_{style_suffix}.png"
    output_path = output_dir / output_name

    return await service.transfer_style_file(
        input_path=input_path,
        output_path=output_path,
        **kwargs
    )
