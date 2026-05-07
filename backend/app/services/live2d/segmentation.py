"""
YLCraft — Live2D AI 自动分层服务

支持两种处理方式：
1. 本地模式 - 使用 BiRefNet、U-2-Net、SAM 等模型
2. API 模式 - 使用 Hugging Face Inference API

支持的模型：
- BiRefNet - 人像抠图（适合 Coser 照片）
- U-2-Net - 通用显著性检测
- RMBG-1.4 - 背景移除
- Segment Anything (SAM) - 全景分割
- Hugging Face Inference API - 云端模型

模型下载：
- BiRefNet: https://huggingface.co/ZigBread/BiRefNet
- SAM: https://github.com/facebookresearch/segment-anything
- Hugging Face: https://api-inference.huggingface.co/models
"""

from __future__ import annotations

import os
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
from PIL import Image

# 尝试导入相关库
try:
    import torch
    from transformers import AutoModelForSemanticSegmentation, AutoImageProcessor
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    torch = None

# 导入配置和API客户端
from app.core.config import ProcessingMode, get_live2d_config
from app.services.live2d.api_client import HuggingFaceClient, APIClientError


# 模型缓存目录
MODEL_CACHE_DIR = Path.home() / ".cache" / "ylcraft" / "models" / "segmentation"


class SegmentationModelType(str, Enum):
    """分割模型类型"""
    BIREFNET = "birefnet"      # 人像分割（推荐 Coser 场景）
    U2NET = "u2net"            # 通用显著性检测
    SAM = "sam"               # 全景分割（SAM）


@dataclass
class LayerInfo:
    """分层信息"""
    name: str           # 图层名称（如 "hair_front", "eye_left"）
    mask: Image.Image   # 蒙版图片
    category: str       # 类别（如 "hair", "face", "body"）
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)  # 边界框 (x, y, w, h)
    confidence: float = 1.0  # 置信度


@dataclass
class SegmentationResult:
    """分割结果"""
    original_image: Image.Image     # 原始图片
    layers: List[LayerInfo]        # 各图层信息
    combined_mask: Image.Image     # 合并的蒙版
    metadata: Dict[str, Any] = field(default_factory=dict)  # 附加元数据


class PersonPartCategory:
    """人物部件类别定义"""

    # 标准 Live2D 分层顺序（从后到前）
    CATEGORIES = {
        # 身体部件
        "body_back": {"z_index": 0, "part_type": "body"},
        "body": {"z_index": 1, "part_type": "body"},

        # 服装
        "clothes_back": {"z_index": 2, "part_type": "clothes"},
        "clothes": {"z_index": 3, "part_type": "clothes"},

        # 头发
        "hair_back": {"z_index": 4, "part_type": "hair"},
        "hair_middle": {"z_index": 5, "part_type": "hair"},
        "hair_front": {"z_index": 6, "part_type": "hair"},

        # 脸部和五官
        "face": {"z_index": 10, "part_type": "face"},
        "eye_white": {"z_index": 11, "part_type": "eye"},
        "eye_pupil": {"z_index": 12, "part_type": "eye"},
        "eye_highlight": {"z_index": 13, "part_type": "eye"},
        "eyebrow": {"z_index": 14, "part_type": "face"},
        "nose": {"z_index": 15, "part_type": "face"},
        "mouth": {"z_index": 16, "part_type": "face"},

        # 装饰
        "hat": {"z_index": 20, "part_type": "accessory"},
        "accessory": {"z_index": 21, "part_type": "accessory"},

        # 手部
        "hand": {"z_index": 25, "part_type": "body"},
    }

    @classmethod
    def get_z_index(cls, layer_name: str) -> int:
        """获取图层的 Z 轴顺序"""
        return cls.CATEGORIES.get(layer_name, {}).get("z_index", 99)


class SegmentationService:
    """图像分割服务（支持本地/API切换）"""

    def __init__(
        self,
        model_type: SegmentationModelType = SegmentationModelType.BIREFNET,
        device: Optional[str] = None,
        mode: str = ProcessingMode.LOCAL.value,
        config=None
    ):
        """
        初始化分割服务

        Args:
            model_type: 分割模型类型（本地模式使用）
            device: 运行设备（"cuda", "cpu", "mps"）
            mode: 处理模式（local 或 api）
            config: 配置对象（可选，默认使用全局配置）
        """
        self.model_type = model_type
        self.device = device or ("cuda" if torch and torch.cuda.is_available() else "cpu")
        self.model = None
        self.processor = None
        self.mode = mode
        self.config = config or get_live2d_config()
        self._api_client = None

    async def _get_api_client(self) -> HuggingFaceClient:
        """获取API客户端（异步）"""
        if self._api_client is None:
            api_key = await self.config.get_api_key("segmentation")
            base_url = self.config.get_api_endpoint("segmentation")
            if not api_key:
                raise APIClientError("未配置 Hugging Face API密钥。请在数据库中添加或在 providers.yaml 中设置 HUGGINGFACE_API_KEY 环境变量。")
            self._api_client = HuggingFaceClient(
                api_key=api_key,
                base_url=base_url
            )
        return self._api_client

    def _get_model_name(self) -> str:
        """获取模型名称"""
        models = {
            SegmentationModelType.BIREFNET: "ZigBread/BiRefNet",
            SegmentationModelType.U2NET: "UFA-CFA/U-2-Net",
        }
        return models.get(self.model_type, "ZigBread/BiRefNet")

    def _get_cache_dir(self) -> Path:
        """获取模型缓存目录"""
        return MODEL_CACHE_DIR / self.model_type.value

    async def _ensure_model_loaded(self):
        """确保模型已加载"""
        if not TRANSFORMERS_AVAILABLE:
            raise RuntimeError(
                "transformers 库未安装。请运行: pip install transformers torch\n"
                "推荐 GPU 加速：pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118"
            )

        if self.model is not None:
            return

        model_name = self._get_model_name()
        cache_dir = self._get_cache_dir()

        print(f"正在加载分割模型 {model_name} 到 {self.device}...")

        try:
            # 加载处理器
            self.processor = AutoImageProcessor.from_pretrained(
                model_name,
                cache_dir=cache_dir,
            )

            # 加载模型
            self.model = AutoModelForSemanticSegmentation.from_pretrained(
                model_name,
                cache_dir=cache_dir,
            )

            self.model = self.model.to(self.device)
            self.model.eval()

            print(f"模型加载完成！")
        except Exception as e:
            raise RuntimeError(
                f"模型加载失败: {e}\n"
                f"请确保已安装 transformers 库并能访问 HuggingFace Hub。\n"
                f"模型: {model_name}"
            )

    def _classify_part(self, mask: np.ndarray, original: Image.Image) -> str:
        """
        根据蒙版特征分类部件

        这是一个简化的分类逻辑，实际可能需要更复杂的处理。
        完整的分类需要：
        1. 检测部件位置（眼睛在脸上半部分等）
        2. 分析部件形状（头发是细长的等）
        3. 使用专门的部件检测模型
        """
        h, w = mask.shape[:2]

        # 计算蒙版中心
        moments = cv2.moments(mask if len(mask.shape) == 2 else mask[:, :, 0])
        if moments["m00"] == 0:
            return "unknown"

        cx = moments["m10"] / moments["m00"]
        cy = moments["m01"] / moments["m00"]

        # 根据位置分类（简化版本）
        # 图像尺寸归一化
        norm_y = cy / h
        norm_x = cx / w

        # 在图像上半部分，可能是头发或面部
        if norm_y < 0.3:
            if norm_y < 0.15:
                return "hair_front"
            return "face"
        # 眼睛区域
        elif 0.3 <= norm_y < 0.45:
            if norm_x < 0.4:
                return "eye_left"
            elif norm_x > 0.6:
                return "eye_right"
            return "eye"
        # 嘴巴区域
        elif 0.45 <= norm_y < 0.55:
            return "mouth"
        # 身体区域
        elif norm_y > 0.55:
            if norm_y > 0.85:
                return "body"
            return "clothes"

        return "unknown"

    def _split_layers(self, combined_mask: Image.Image, original: Image.Image) -> List[LayerInfo]:
        """
        将组合蒙版拆分为多个图层

        实际应用中，这里可能需要：
        1. 使用实例分割模型区分同类部件
        2. 使用部件检测模型精确定位
        3. 使用线条检测分离不同区域
        """
        # 简化版本：将整个蒙版作为一个图层返回
        # 完整实现需要更复杂的分割逻辑

        layers = []
        mask_array = np.array(combined_mask)

        # 简单阈值处理
        binary_mask = (mask_array > 127).astype(np.uint8) * 255

        # 查找连通区域
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
            binary_mask, connectivity=8
        )

        # 跳过背景（label=0）
        for i in range(1, min(num_labels, 20)):  # 限制最多20个图层
            component_mask = (labels == i).astype(np.uint8) * 255
            component_image = Image.fromarray(component_mask, mode='L')

            # 计算边界框
            x, y, w, h = stats[i, cv2.CC_STAT_LEFT:cv2.CC_STAT_HEIGHT + 1]

            # 分类
            category = self._classify_part(component_mask, original)

            layers.append(LayerInfo(
                name=f"{category}_{i}",
                mask=component_image,
                category=category,
                bbox=(x, y, w, h),
                confidence=0.8,
            ))

        # 按 Z 轴顺序排序
        layers.sort(key=lambda x: PersonPartCategory.get_z_index(x.name))

        return layers

    async def segment(
        self,
        image: Image.Image,
        return_layers: bool = True,
    ) -> SegmentationResult:
        """
        图像分割

        Args:
            image: 输入图片（PIL Image）
            return_layers: 是否返回分层蒙版

        Returns:
            SegmentationResult: 分割结果
        """
        # 根据模式选择处理方式
        if self.mode == ProcessingMode.API.value:
            return await self._segment_api(image, return_layers)
        else:
            return await self._segment_local(image, return_layers)

    async def _segment_local(
        self,
        image: Image.Image,
        return_layers: bool,
    ) -> SegmentationResult:
        """本地模式：使用BiRefNet/U-2-Net模型"""
        await self._ensure_model_loaded()

        # 预处理
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # 执行推理（在线程池中）
        loop = asyncio.get_event_loop()

        def _do_inference():
            inputs = self.processor(
                images=image,
                return_tensors="pt"
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self.model(**inputs)

            # 后处理获取蒙版
            predicted_mask = self.processor.post_process_semantic_segmentation(
                outputs,
                target_sizes=[image.size[::-1]]
            )[0]

            return predicted_mask

        predicted_mask = await loop.run_in_executor(None, _do_inference)

        # 转换为 PIL Image
        mask_array = predicted_mask.cpu().numpy().astype(np.uint8)

        # 二值化（取最大概率类别）
        binary_mask = (mask_array > 0).astype(np.uint8) * 255
        combined_mask = Image.fromarray(binary_mask, mode='L')

        # 拆分图层（可选）
        layers = []
        if return_layers:
            try:
                import cv2
                layers = self._split_layers(combined_mask, image)
            except ImportError:
                print("Warning: cv2 not available, skipping layer splitting")

        return SegmentationResult(
            original_image=image,
            layers=layers,
            combined_mask=combined_mask,
            metadata={
                "model_type": self.model_type.value,
                "device": self.device,
                "mode": "local",
            }
        )

    async def _segment_api(
        self,
        image: Image.Image,
        return_layers: bool,
    ) -> SegmentationResult:
        """API模式：使用Hugging Face Inference API"""
        client = await self._get_api_client()

        # 调用API
        model_name = self.config.get_local_model("segmentation_model") or "ZigBread/BiRefNet"
        result_mask = await client.segment_image(image, model=model_name)

        # 拆分图层（可选）
        layers = []
        if return_layers:
            try:
                import cv2
                layers = self._split_layers(result_mask, image)
            except ImportError:
                print("Warning: cv2 not available, skipping layer splitting")

        return SegmentationResult(
            original_image=image,
            layers=layers,
            combined_mask=result_mask,
            metadata={
                "model_type": model_name,
                "mode": "api",
                "service": "huggingface",
            }
        )

    async def segment_file(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        save_layers: bool = True,
    ) -> dict:
        """
        处理图片文件

        Args:
            input_path: 输入图片路径
            output_dir: 输出目录
            save_layers: 是否保存各图层蒙版

        Returns:
            dict: 处理结果
        """
        input_path = Path(input_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 加载图片
        image = Image.open(input_path)

        # 执行分割
        result = await self.segment(image, return_layers=save_layers)

        # 保存组合蒙版
        combined_path = output_dir / f"{input_path.stem}_mask.png"
        result.combined_mask.save(combined_path, format='PNG')

        # 保存各图层（如果有）
        layer_paths = []
        if save_layers and result.layers:
            layers_dir = output_dir / f"{input_path.stem}_layers"
            layers_dir.mkdir(exist_ok=True)

            for layer in result.layers:
                layer_path = layers_dir / f"{layer.name}.png"
                layer.mask.save(layer_path, format='PNG')
                layer_paths.append({
                    "name": layer.name,
                    "category": layer.category,
                    "path": str(layer_path),
                    "bbox": layer.bbox,
                    "confidence": layer.confidence,
                })

        return {
            "original_path": str(input_path),
            "mask_path": str(combined_path),
            "layers": layer_paths,
            "layer_count": len(layer_paths),
            "metadata": result.metadata,
            "mode": self.mode,
        }


# 尝试导入 cv2（用于连通组件分析）
try:
    import cv2
except ImportError:
    cv2 = None


# 全局服务实例
_service_instance: Optional[SegmentationService] = None


def get_segmentation_service(
    model_type: SegmentationModelType = SegmentationModelType.BIREFNET,
    mode: str = ProcessingMode.LOCAL.value
) -> SegmentationService:
    """获取全局分割服务实例"""
    global _service_instance
    if _service_instance is None:
        _service_instance = SegmentationService(model_type=model_type, mode=mode)
    return _service_instance


async def process_image(
    input_path: str | Path,
    output_dir: str | Path,
    model_type: str = "birefnet",
    **kwargs
) -> dict:
    """
    便捷函数：处理图片分割

    Args:
        input_path: 输入图片路径
        output_dir: 输出目录
        model_type: 模型类型

    Returns:
        dict: 处理结果
    """
    service = get_segmentation_service(
        model_type=SegmentationModelType(model_type)
    )

    return await service.segment_file(
        input_path=input_path,
        output_dir=output_dir,
        **kwargs
    )
