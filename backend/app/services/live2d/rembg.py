"""
YLCraft — Live2D AI 抠图服务

支持两种处理方式：
1. 本地模式 - 使用 RMBG-1.4 模型（rembg库）
2. API 模式 - 使用 Remove.bg API

模型下载：https://huggingface.co/briaai/RMBG-1.4
API文档：https://www.remove.bg/api
"""

from __future__ import annotations

import os
import asyncio
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import numpy as np
from PIL import Image

# 尝试导入 rembg（可能未安装）
try:
    from rembg import remove, new_session
    REMBG_AVAILABLE = True
except ImportError:
    REMBG_AVAILABLE = False
    new_session = None

# 导入配置和API客户端
from app.core.config import ProcessingMode, get_live2d_config
from app.services.live2d.api_client import RemoveBgClient, APIClientError


# 模型缓存目录
MODEL_CACHE_DIR = Path.home() / ".cache" / "ylcraft" / "models" / "rembg"
MODEL_FILE_NAME = "rmbg-1.4"
MODEL_URL = "https://huggingface.co/briaai/RMBG-1.4/resolve/main/model.onnx"


@dataclass
class RembangResult:
    """抠图结果"""
    original_image: Image.Image  # 原始图片
    mask_image: Image.Image     # 生成的蒙版
    result_image: Image.Image   # 去除背景后的图片（RGBA）
    alpha_matte: Optional[Image.Image] = None  # 阿尔法通道蒙版


class RembangService:
    """RMBG-1.4 抠图服务（支持本地/API切换）"""

    def __init__(
        self,
        model_path: Optional[str] = None,
        mode: str = ProcessingMode.LOCAL.value,
        config=None
    ):
        """
        初始化抠图服务

        Args:
            model_path: 本地模型路径，如果为 None 则自动下载
            mode: 处理模式（local 或 api）
            config: 配置对象（可选，默认使用全局配置）
        """
        self.model_path = model_path or self._get_default_model_path()
        self.session = None
        self.mode = mode
        self.config = config or get_live2d_config()
        self._api_client = None

    async def _get_api_client(self) -> RemoveBgClient:
        """获取API客户端（异步）"""
        if self._api_client is None:
            api_key = await self.config.get_api_key("rembg")
            api_url = self.config.get_api_endpoint("rembg")
            if not api_key:
                raise APIClientError("未配置 Remove.bg API密钥。请在数据库中添加或在 providers.yaml 中设置 REMOVEBG_API_KEY 环境变量。")
            self._api_client = RemoveBgClient(
                api_key=api_key,
                api_url=api_url
            )
        return self._api_client

    def _get_default_model_path(self) -> Path:
        """获取默认模型路径"""
        return MODEL_CACHE_DIR / f"{MODEL_FILE_NAME}.onnx"

    async def _ensure_model(self) -> bool:
        """确保模型已下载"""
        if not REMBG_AVAILABLE:
            raise RuntimeError(
                "rembg 库未安装。请运行: pip install rembg\n"
                "或参考: https://github.com/danielgatis/rembg"
            )

        # 检查本地模型
        if not self.model_path.exists():
            MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

            # 尝试下载模型
            try:
                print(f"正在下载 RMBG-1.4 模型到 {self.model_path}...")
                import urllib.request
                urllib.request.urlretrieve(MODEL_URL, self.model_path)
                print("模型下载完成！")
            except Exception as e:
                raise RuntimeError(
                    f"模型下载失败: {e}\n"
                    f"请手动下载模型到: {self.model_path}\n"
                    f"下载链接: {MODEL_URL}"
                )

        return True

    def _init_session(self):
        """初始化 rembg session"""
        if self.session is None:
            if not self.model_path.exists():
                raise FileNotFoundError(f"模型文件不存在: {self.model_path}")
            self.session = new_session(model_name=MODEL_FILE_NAME)
        return self.session

    async def remove_background(
        self,
        image: Image.Image,
        alpha_matting: bool = True,
        alpha_matting_foreground_threshold: int = 240,
        alpha_matting_background_threshold: int = 10,
        alpha_matting_erode_size: int = 10,
    ) -> RembangResult:
        """
        去除图片背景

        Args:
            image: 输入图片（PIL Image）
            alpha_matting: 是否使用阿尔法通道抠图（更精细）
            alpha_matting_foreground_threshold: 前景阈值
            alpha_matting_background_threshold: 背景阈值
            alpha_matting_erode_size: 腐蚀大小

        Returns:
            RembangResult: 包含原始图、蒙版、结果图的对象
        """
        # 根据模式选择处理方式
        if self.mode == ProcessingMode.API.value:
            return await self._remove_background_api(image)
        else:
            return await self._remove_background_local(
                image,
                alpha_matting,
                alpha_matting_foreground_threshold,
                alpha_matting_background_threshold,
                alpha_matting_erode_size,
            )

    async def _remove_background_local(
        self,
        image: Image.Image,
        alpha_matting: bool = True,
        alpha_matting_foreground_threshold: int = 240,
        alpha_matting_background_threshold: int = 10,
        alpha_matting_erode_size: int = 10,
    ) -> RembangResult:
        """本地模式：使用RMBG-1.4模型抠图"""
        await self._ensure_model()

        # 在线程池中执行 CPU/GPU 推理
        loop = asyncio.get_event_loop()
        session = self._init_session()

        def _do_remove():
            return remove(
                image,
                session=session,
                alpha_matting=alpha_matting,
                alpha_matting_foreground_threshold=alpha_matting_foreground_threshold,
                alpha_matting_background_threshold=alpha_matting_background_threshold,
                alpha_matting_erode_size=alpha_matting_erode_size,
            )

        result_image = await loop.run_in_executor(None, _do_remove)

        # 生成蒙版
        mask_array = np.array(result_image)[:, :, 3]
        mask_image = Image.fromarray(mask_array, mode='L')

        return RembangResult(
            original_image=image,
            mask_image=mask_image,
            result_image=result_image,
        )

    async def _remove_background_api(self, image: Image.Image) -> RembangResult:
        """API模式：使用Remove.bg API抠图"""
        client = await self._get_api_client()

        # 调用API
        result_image = await client.remove_background(image)

        # 生成蒙版
        mask_array = np.array(result_image)[:, :, 3]
        mask_image = Image.fromarray(mask_array, mode='L')

        return RembangResult(
            original_image=image,
            mask_image=mask_image,
            result_image=result_image,
        )

    async def remove_background_file(
        self,
        input_path: str | Path,
        output_path: str | Path,
        return_mask: bool = False,
        **kwargs
    ) -> dict:
        """
        处理图片文件

        Args:
            input_path: 输入图片路径
            output_path: 输出图片路径
            return_mask: 是否返回蒙版路径

        Returns:
            dict: 包含输出路径和可选蒙版路径的字典
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        # 加载图片
        image = Image.open(input_path)

        # 执行抠图
        result = await self.remove_background(image, **kwargs)

        # 保存结果（RGBA 格式）
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.result_image.save(output_path, format='PNG')

        response = {
            "result_path": str(output_path),
            "mode": self.mode,
        }

        # 保存蒙版（可选）
        if return_mask:
            mask_path = output_path.with_suffix('.mask.png')
            result.mask_image.save(mask_path, format='PNG')
            response["mask_path"] = str(mask_path)

        return response


# 全局服务实例
_service_instances: dict[str, RembangService] = {}


def get_rembg_service(mode: str = ProcessingMode.LOCAL.value) -> RembangService:
    """获取全局 RembangService 实例"""
    key = f"{mode}"
    if key not in _service_instances:
        _service_instances[key] = RembangService(mode=mode)
    return _service_instances[key]


async def process_image(
    input_path: str | Path,
    output_dir: str | Path,
    model_path: Optional[str] = None,
) -> dict:
    """
    便捷函数：处理图片去除背景

    Args:
        input_path: 输入图片路径
        output_dir: 输出目录
        model_path: 可选的模型路径

    Returns:
        dict: 处理结果
    """
    service = RembangService(model_path) if model_path else get_rembg_service()

    input_path = Path(input_path)
    output_dir = Path(output_dir)

    # 输出文件名：原名_rmbg.png
    output_name = f"{input_path.stem}_rmbg.png"
    output_path = output_dir / output_name

    return await service.remove_background_file(
        input_path=input_path,
        output_path=output_path,
        return_mask=True,
    )
