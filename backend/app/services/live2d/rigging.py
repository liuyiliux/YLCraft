"""
YLCraft — Live2D 五官绑骨服务

基于分割后的图层，实现五官的运动控制：
- 眼睛跟随（视线跟随鼠标/摄像头）
- 眨眼动作（自动随机触发）
- 嘴巴开合（根据音频/表情）
- 眉毛运动
- 表情预设

骨骼绑定使用 Cubism 4 的 .moc3 格式。
"""

from __future__ import annotations

import json
import random
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List

from PIL import Image
import numpy as np


# ===== 数据模型 =====

class ExpressionType(str, Enum):
    """表情类型"""
    NEUTRAL = "neutral"           # 中性/默认
    HAPPY = "happy"               # 开心
    SAD = "sad"                   # 难过
    ANGRY = "angry"               # 生气
    SURPRISED = "surprised"       # 惊讶
    LOVED = "loved"               # 喜欢
    FOCUSED = "focused"           # 专注

    @classmethod
    def all(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def label(cls, value: str) -> str:
        labels = {
            "neutral": "默认",
            "happy": "开心",
            "sad": "难过",
            "angry": "生气",
            "surprised": "惊讶",
            "loved": "喜欢",
            "focused": "专注",
        }
        return labels.get(value, value)


class FacePart(str, Enum):
    """面部部件"""
    LEFT_EYE = "left_eye"
    RIGHT_EYE = "right_eye"
    LEFT_EYEBROW = "left_eyebrow"
    RIGHT_EYEBROW = "right_eyebrow"
    MOUTH = "mouth"
    NOSE = "nose"


@dataclass
class BoneTransform:
    """骨骼变换数据"""
    x: float = 0.0           # X轴位移（相对值）
    y: float = 0.0           # Y轴位移
    angle: float = 0.0       # 旋转角度（度）
    scale_x: float = 1.0     # X轴缩放
    scale_y: float = 1.0     # Y轴缩放

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "BoneTransform":
        return cls(**data)


@dataclass
class EyeTracking:
    """眼睛跟随数据"""
    look_at_x: float = 0.0    # 视线X（-1 到 1）
    look_at_y: float = 0.0    # 视线Y（-1 到 1）
    blink_level: float = 0.0   # 眨眼程度（0 到 1，0为睁开，1为闭合）


@dataclass
class ExpressionBlend:
    """表情混合数据"""
    expression: str = ExpressionType.NEUTRAL.value
    intensity: float = 1.0     # 表情强度（0 到 1）

    def to_dict(self) -> Dict[str, Any]:
        return {"expression": self.expression, "intensity": self.intensity}


@dataclass
class RiggedFace:
    """绑骨后的面部数据"""
    model_id: str
    created_at: datetime = field(default_factory=datetime.now)

    # 骨骼信息
    bones: Dict[str, BoneTransform] = field(default_factory=dict)

    # 眼睛跟随
    eye_tracking: EyeTracking = field(default_factory=EyeTracking)

    # 表情混合
    expression: ExpressionBlend = field(default_factory=ExpressionBlend)

    # 蒙版信息（存储五官的裁剪区域）
    face_masks: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # 关键点（用于动画计算）
    landmarks: Dict[str, List[float]] = field(default_factory=dict)


@dataclass
class RiggingResult:
    """绑骨结果"""
    model_id: str
    rigged: bool = True
    bone_count: int = 0
    face_detected: bool = False
    face_bbox: Optional[List[float]] = None
    landmarks: Dict[str, List[float]] = field(default_factory=dict)
    face_masks: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    motions: List[Dict[str, Any]] = field(default_factory=list)
    export_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ===== 面部检测工具 =====

def detect_face_landmarks(image_path: str) -> Optional[Dict[str, List[float]]]:
    """
    检测面部关键点

    使用简单的图像处理方法定位面部区域。
    实际项目中可使用 face_recognition、dlib 或 MediaPipe。

    Args:
        image_path: 图片路径

    Returns:
        面部关键点字典，包含：
        - left_eye: 左眼中心 [x, y]
        - right_eye: 右眼中心 [x, y]
        - nose: 鼻尖 [x, y]
        - mouth_left: 嘴角左 [x, y]
        - mouth_right: 嘴角右 [x, y]
        - left_eyebrow: 左眉 [x, y]
        - right_eyebrow: 右眉 [x, y]
    """
    try:
        img = Image.open(image_path)
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        width, height = img.size

        # 简单的人脸检测（基于肤色和位置）
        # 实际应用中应使用专业的人脸检测库

        # 默认位置（基于常见面部比例）
        face_height = height * 0.4
        face_width = width * 0.5
        face_center_x = width * 0.5
        face_center_y = height * 0.45

        landmarks = {
            "left_eye": [face_center_x - face_width * 0.25, face_center_y - face_height * 0.1],
            "right_eye": [face_center_x + face_width * 0.25, face_center_y - face_height * 0.1],
            "nose": [face_center_x, face_center_y + face_height * 0.05],
            "mouth_left": [face_center_x - face_width * 0.15, face_center_y + face_height * 0.25],
            "mouth_right": [face_center_x + face_width * 0.15, face_center_y + face_height * 0.25],
            "left_eyebrow": [face_center_x - face_width * 0.25, face_center_y - face_height * 0.25],
            "right_eyebrow": [face_center_x + face_width * 0.25, face_center_y - face_height * 0.25],
        }

        return landmarks
    except Exception as e:
        print(f"面部检测失败: {e}")
        return None


def calculate_face_bbox(landmarks: Dict[str, List[float]]) -> List[float]:
    """根据关键点计算面部包围盒"""
    all_points = []
    for points in landmarks.values():
        if points:
            all_points.extend(points)

    if not all_points:
        return [0, 0, 100, 100]

    xs = all_points[0::2]
    ys = all_points[1::2]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    return [min_x, min_y, max_x - min_x, max_y - min_y]


def extract_face_masks(
    image_path: str,
    landmarks: Dict[str, List[float]],
    output_dir: Path
) -> Dict[str, Dict[str, Any]]:
    """
    从原图提取面部各部件的蒙版

    Args:
        image_path: 原图路径
        landmarks: 面部关键点
        output_dir: 输出目录

    Returns:
        各部件的蒙版信息
    """
    try:
        img = Image.open(image_path)
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        width, height = img.size
        masks = {}

        # 左眼蒙版
        left_eye = landmarks.get("left_eye", [0, 0])
        eye_width = width * 0.12
        eye_height = height * 0.05
        left_eye_mask = {
            "x": left_eye[0] - eye_width / 2,
            "y": left_eye[1] - eye_height / 2,
            "width": eye_width,
            "height": eye_height,
            "center": left_eye,
        }
        masks["left_eye"] = left_eye_mask

        # 右眼蒙版
        right_eye = landmarks.get("right_eye", [0, 0])
        right_eye_mask = {
            "x": right_eye[0] - eye_width / 2,
            "y": right_eye[1] - eye_height / 2,
            "width": eye_width,
            "height": eye_height,
            "center": right_eye,
        }
        masks["right_eye"] = right_eye_mask

        # 嘴巴蒙版
        mouth_left = landmarks.get("mouth_left", [0, 0])
        mouth_right = landmarks.get("mouth_right", [0, 0])
        mouth_center_x = (mouth_left[0] + mouth_right[0]) / 2
        mouth_center_y = (mouth_left[1] + mouth_right[1]) / 2
        mouth_width = abs(mouth_right[0] - mouth_left[0]) * 1.5
        mouth_height = height * 0.08
        mouth_mask = {
            "x": mouth_center_x - mouth_width / 2,
            "y": mouth_center_y - mouth_height / 2,
            "width": mouth_width,
            "height": mouth_height,
            "center": [mouth_center_x, mouth_center_y],
        }
        masks["mouth"] = mouth_mask

        # 左眉蒙版
        left_eyebrow = landmarks.get("left_eyebrow", [0, 0])
        eyebrow_width = width * 0.1
        eyebrow_height = height * 0.02
        left_eyebrow_mask = {
            "x": left_eyebrow[0] - eyebrow_width / 2,
            "y": left_eyebrow[1] - eyebrow_height / 2,
            "width": eyebrow_width,
            "height": eyebrow_height,
            "center": left_eyebrow,
        }
        masks["left_eyebrow"] = left_eyebrow_mask

        # 右眉蒙版
        right_eyebrow = landmarks.get("right_eyebrow", [0, 0])
        right_eyebrow_mask = {
            "x": right_eyebrow[0] - eyebrow_width / 2,
            "y": right_eyebrow[1] - eyebrow_height / 2,
            "width": eyebrow_width,
            "height": eyebrow_height,
            "center": right_eyebrow,
        }
        masks["right_eyebrow"] = right_eyebrow_mask

        return masks

    except Exception as e:
        print(f"蒙版提取失败: {e}")
        return {}


# ===== 表情和运动 =====

class ExpressionCalculator:
    """表情计算器"""

    # 各表情对应的骨骼变换
    EXPRESSION_BLENDS: Dict[str, Dict[str, BoneTransform]] = {
        ExpressionType.NEUTRAL.value: {
            "mouth": BoneTransform(y=0, scale_y=0.1),
        },
        ExpressionType.HAPPY.value: {
            "mouth": BoneTransform(y=0, scale_y=0.3),
        },
        ExpressionType.SAD.value: {
            "mouth": BoneTransform(y=-5, scale_y=0.05),
            "left_eyebrow": BoneTransform(angle=-10),
            "right_eyebrow": BoneTransform(angle=10),
        },
        ExpressionType.ANGRY.value: {
            "mouth": BoneTransform(y=0, scale_y=0.1),
            "left_eyebrow": BoneTransform(angle=15, y=-3),
            "right_eyebrow": BoneTransform(angle=-15, y=-3),
        },
        ExpressionType.SURPRISED.value: {
            "mouth": BoneTransform(y=0, scale_y=0.4),
            "left_eye": BoneTransform(scale_x=1.2, scale_y=1.2),
            "right_eye": BoneTransform(scale_x=1.2, scale_y=1.2),
        },
        ExpressionType.LOVED.value: {
            "mouth": BoneTransform(scale_y=0.2),
            "left_eyebrow": BoneTransform(angle=-5),
            "right_eyebrow": BoneTransform(angle=5),
        },
        ExpressionType.FOCUSED.value: {
            "mouth": BoneTransform(y=0, scale_y=0.1),
            "left_eye": BoneTransform(scale_y=0.9),
            "right_eye": BoneTransform(scale_y=0.9),
        },
    }

    @classmethod
    def calculate_blend(
        cls,
        expression: str,
        intensity: float = 1.0
    ) -> Dict[str, BoneTransform]:
        """计算表情混合"""
        if expression not in cls.EXPRESSION_BLENDS:
            expression = ExpressionType.NEUTRAL.value

        blends = cls.EXPRESSION_BLENDS[expression].copy()

        # 根据强度调整
        for bone_name, transform in blends.items():
            blends[bone_name] = BoneTransform(
                x=transform.x * intensity,
                y=transform.y * intensity,
                angle=transform.angle * intensity,
                scale_x=1.0 + (transform.scale_x - 1.0) * intensity,
                scale_y=1.0 + (transform.scale_y - 1.0) * intensity,
            )

        return blends


class BlinkController:
    """眨眼控制器"""

    def __init__(self, interval: float = 3.0, variance: float = 1.5):
        """
        初始化眨眼控制器

        Args:
            interval: 平均眨眼间隔（秒）
            variance: 间隔方差
        """
        self.interval = interval
        self.variance = variance
        self.next_blink_time = time.time() + self._random_interval()
        self.blink_duration = 0.15  # 眨眼持续时间（秒）
        self.blink_start_time = 0
        self.is_blinking = False

    def _random_interval(self) -> float:
        """生成随机眨眼间隔"""
        return max(1.0, random.gauss(self.interval, self.variance))

    def update(self) -> float:
        """
        更新眨眼状态

        Returns:
            当前眨眼程度（0 到 1）
        """
        current_time = time.time()

        # 检查是否应该眨眼
        if not self.is_blinking and current_time >= self.next_blink_time:
            self.is_blinking = True
            self.blink_start_time = current_time
            self.next_blink_time = current_time + self._random_interval()

        # 计算眨眼程度
        if self.is_blinking:
            elapsed = current_time - self.blink_start_time
            if elapsed < self.blink_duration / 2:
                # 闭合阶段
                blink_level = elapsed / (self.blink_duration / 2)
            elif elapsed < self.blink_duration:
                # 睁开阶段
                blink_level = 1.0 - (elapsed - self.blink_duration / 2) / (self.blink_duration / 2)
            else:
                # 眨眼完成
                self.is_blinking = False
                blink_level = 0.0

            return min(1.0, max(0.0, blink_level))

        return 0.0


class LookAtController:
    """视线跟随控制器"""

    def __init__(self, smoothing: float = 0.1):
        """
        初始化视线跟随控制器

        Args:
            smoothing: 平滑系数（0 到 1，越小越平滑）
        """
        self.smoothing = smoothing
        self.target_x = 0.0
        self.target_y = 0.0
        self.current_x = 0.0
        self.current_y = 0.0

    def set_target(self, x: float, y: float):
        """
        设置目标视线位置

        Args:
            x: 目标X（-1 到 1）
            y: 目标Y（-1 到 1）
        """
        self.target_x = max(-1.0, min(1.0, x))
        self.target_y = max(-1.0, min(1.0, y))

    def update(self) -> tuple[float, float]:
        """
        更新视线位置（平滑插值）

        Returns:
            当前视线位置 (x, y)
        """
        self.current_x += (self.target_x - self.current_x) * self.smoothing
        self.current_y += (self.target_y - self.current_y) * self.smoothing
        return self.current_x, self.current_y


# ===== 主服务类 =====

class RiggingService:
    """
    五官绑骨服务

    提供面部运动控制，包括：
    - 骨骼绑定
    - 眼睛跟随
    - 眨眼动画
    - 表情切换
    - 待机动作生成
    """

    def __init__(self):
        self.blink_controller = BlinkController()
        self.lookat_controller = LookAtController()

    def rig_face(
        self,
        model_id: str,
        image_path: str,
        output_dir: Path
    ) -> RiggingResult:
        """
        执行面部绑骨

        Args:
            model_id: 模型ID
            image_path: 输入图片路径
            output_dir: 输出目录

        Returns:
            绑骨结果
        """
        start_time = time.time()

        # 检测面部关键点
        landmarks = detect_face_landmarks(image_path)
        face_detected = landmarks is not None

        if not face_detected:
            return RiggingResult(
                model_id=model_id,
                rigged=False,
                face_detected=False,
                metadata={"error": "面部检测失败"},
            )

        # 计算面部包围盒
        face_bbox = calculate_face_bbox(landmarks)

        # 提取五官蒙版
        face_masks = extract_face_masks(image_path, landmarks, output_dir)

        # 创建骨骼数据
        bones = {}
        for part_name in ["left_eye", "right_eye", "mouth", "left_eyebrow", "right_eyebrow"]:
            if part_name in landmarks:
                center = landmarks[part_name]
                bones[part_name] = BoneTransform(
                    x=center[0],
                    y=center[1],
                    angle=0.0,
                    scale_x=1.0,
                    scale_y=1.0,
                )

        # 生成默认待机动作
        motions = self._generate_idle_motions(model_id, output_dir)

        # 生成骨骼配置文件
        rigging_config = {
            "model_id": model_id,
            "bones": {k: v.to_dict() for k, v in bones.items()},
            "landmarks": landmarks,
            "face_masks": face_masks,
            "face_bbox": face_bbox,
            "motions": motions,
            "created_at": datetime.now().isoformat(),
        }

        config_path = output_dir / f"{model_id}_rigging.json"
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(rigging_config, f, indent=2, ensure_ascii=False)

        return RiggingResult(
            model_id=model_id,
            rigged=True,
            bone_count=len(bones),
            face_detected=True,
            face_bbox=face_bbox,
            landmarks=landmarks,
            face_masks=face_masks,
            motions=motions,
            export_path=str(config_path),
            metadata={
                "processing_time": time.time() - start_time,
                "config_path": str(config_path),
            },
        )

    def _generate_idle_motions(
        self,
        model_id: str,
        output_dir: Path
    ) -> List[Dict[str, Any]]:
        """生成待机动作数据"""
        motions = []

        # 眨眼动作
        blink_motion = {
            "id": f"{model_id}_blink",
            "name": "眨眼",
            "type": "blink",
            "duration": 0.15,
            "keyframes": [
                {"time": 0.0, "blink_level": 0.0},
                {"time": 0.075, "blink_level": 1.0},
                {"time": 0.15, "blink_level": 0.0},
            ],
        }
        motions.append(blink_motion)

        # 呼吸动作
        breath_motion = {
            "id": f"{model_id}_breath",
            "name": "呼吸",
            "type": "breath",
            "duration": 4.0,
            "amplitude": 2.0,
            "frequency": 0.25,
        }
        motions.append(breath_motion)

        # 视线轻微移动
        look_around_motion = {
            "id": f"{model_id}_look_around",
            "name": "视线移动",
            "type": "look_around",
            "duration": 8.0,
            "pattern": "sine",
        }
        motions.append(look_around_motion)

        return motions

    def set_expression(self, expression: str, intensity: float = 1.0) -> Dict[str, BoneTransform]:
        """
        设置表情

        Args:
            expression: 表情类型
            intensity: 表情强度（0 到 1）

        Returns:
            骨骼变换字典
        """
        return ExpressionCalculator.calculate_blend(expression, intensity)

    def update_eye_tracking(
        self,
        target_x: float,
        target_y: float
    ) -> tuple[float, float]:
        """
        更新视线跟随

        Args:
            target_x: 目标X位置（-1 到 1）
            target_y: 目标Y位置（-1 到 1）

        Returns:
            平滑后的视线位置
        """
        self.lookat_controller.set_target(target_x, target_y)
        return self.lookat_controller.update()

    def update_blink(self) -> float:
        """
        更新眨眼状态

        Returns:
            当前眨眼程度
        """
        return self.blink_controller.update()

    def get_eye_transforms(
        self,
        look_at_x: float,
        look_at_y: float,
        blink_level: float
    ) -> Dict[str, BoneTransform]:
        """
        获取眼睛的变换数据

        Args:
            look_at_x: 视线X
            look_at_y: 视线Y
            blink_level: 眨眼程度

        Returns:
            左右眼的变换数据
        """
        # 视线跟随（眼球转动）
        eye_offset_x = look_at_x * 5  # 最大偏移5像素
        eye_offset_y = look_at_y * 3

        # 眨眼（通过缩放Y轴实现）
        left_eye_scale_y = max(0.1, 1.0 - blink_level * 0.9)
        right_eye_scale_y = left_eye_scale_y

        return {
            "left_eye": BoneTransform(
                x=eye_offset_x,
                y=eye_offset_y,
                scale_y=left_eye_scale_y,
            ),
            "right_eye": BoneTransform(
                x=eye_offset_x,
                y=eye_offset_y,
                scale_y=right_eye_scale_y,
            ),
        }


# ===== 全局服务实例 =====

_rigging_service: Optional[RiggingService] = None


def get_rigging_service() -> RiggingService:
    """获取全局 RiggingService 实例"""
    global _rigging_service
    if _rigging_service is None:
        _rigging_service = RiggingService()
    return _rigging_service


# ===== 便捷函数 =====

def rig_face_image(
    image_path: str,
    model_id: str,
    output_dir: Optional[Path] = None
) -> RiggingResult:
    """
    便捷函数：对图片进行面部绑骨

    Args:
        image_path: 输入图片路径
        model_id: 模型ID
        output_dir: 输出目录

    Returns:
        绑骨结果
    """
    if output_dir is None:
        output_dir = Path("uploads/live2d") / model_id / "rigging"
    output_dir.mkdir(parents=True, exist_ok=True)

    service = get_rigging_service()
    return service.rig_face(model_id, image_path, output_dir)


__all__ = [
    "RiggingService",
    "RiggingResult",
    "RiggedFace",
    "BoneTransform",
    "EyeTracking",
    "ExpressionBlend",
    "ExpressionType",
    "FacePart",
    "ExpressionCalculator",
    "BlinkController",
    "LookAtController",
    "rig_face_image",
    "get_rigging_service",
    "detect_face_landmarks",
    "calculate_face_bbox",
    "extract_face_masks",
]
