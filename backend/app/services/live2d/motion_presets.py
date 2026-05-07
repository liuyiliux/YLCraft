"""
YLCraft — 动作预设库

提供常见的 Live2D 动作预设模板。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional


class MotionCategory(str, Enum):
    """动作分类"""
    IDLE = "idle"           # 待机
    GREETING = "greeting"   # 打招呼
    EXPRESSION = "expression"  # 表情动作
    BODY = "body"           # 身体动作
    INTERACTION = "interaction"  # 互动动作


@dataclass
class MotionPreset:
    """动作预设"""
    id: str
    name: str
    name_cn: str
    category: MotionCategory
    description: str
    duration: float  # 持续时间（秒）
    loop: bool = True
    parameters: Dict[str, List[float]] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)


# 预设动作库
MOTION_PRESETS: List[MotionPreset] = [
    # 待机动作
    MotionPreset(
        id="idle_breath",
        name="Idle Breath",
        name_cn="呼吸待机",
        category=MotionCategory.IDLE,
        description="轻微的呼吸动画，让模型看起来更有生气",
        duration=4.0,
        loop=True,
        parameters={
            "ParamAngleY": [0, 0.5, 0, -0.5, 0],
            "ParamAngleX": [0, 0.3, 0, -0.3, 0],
        },
        tags=["待机", "呼吸", "基础"],
    ),
    MotionPreset(
        id="idle_look_around",
        name="Idle Look Around",
        name_cn="视线移动待机",
        category=MotionCategory.IDLE,
        description="视线轻微左右移动，观察周围环境",
        duration=8.0,
        loop=True,
        parameters={
            "ParamAngleX": [0, 5, 0, -5, 0],
        },
        tags=["待机", "视线", "自然"],
    ),
    MotionPreset(
        id="idle_blink",
        name="Idle with Blink",
        name_cn="眨眼待机",
        category=MotionCategory.IDLE,
        description="带有随机眨眼的待机动作",
        duration=6.0,
        loop=True,
        parameters={
            "ParamEyeLOpen": [1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1],
        },
        tags=["待机", "眨眼", "自然"],
    ),

    # 打招呼
    MotionPreset(
        id="greeting_wave",
        name="Wave",
        name_cn="挥手打招呼",
        category=MotionCategory.GREETING,
        description="挥手打招呼的动作",
        duration=2.0,
        loop=False,
        parameters={
            "ParamArmLA": [0, 30, 0],
            "ParamArmRA": [0, -20, 0],
        },
        tags=["招呼", "挥手", "互动"],
    ),
    MotionPreset(
        id="greeting_bow",
        name="Bow",
        name_cn="鞠躬",
        category=MotionCategory.GREETING,
        description="微微鞠躬表示问候",
        duration=2.5,
        loop=False,
        parameters={
            "ParamAngleX": [0, 15, 0],
            "ParamAngleZ": [0, -5, 0],
        },
        tags=["招呼", "鞠躬", "礼貌"],
    ),
    MotionPreset(
        id="greeting_nod",
        name="Nod",
        name_cn="点头",
        category=MotionCategory.GREETING,
        description="轻轻点头表示认同",
        duration=1.5,
        loop=False,
        parameters={
            "ParamAngleX": [0, 5, 0, -3, 0, 3, 0],
        },
        tags=["招呼", "点头", "认同"],
    ),

    # 表情动作
    MotionPreset(
        id="expression_smile",
        name="Smile",
        name_cn="微笑",
        category=MotionCategory.EXPRESSION,
        description="自然微笑的表情",
        duration=1.0,
        loop=False,
        parameters={
            "ParamMouthForm": [0, 0.5, 0],
            "ParamEyeForm": [0, 0.3, 0],
        },
        tags=["表情", "微笑", "开心"],
    ),
    MotionPreset(
        id="expression_surprised",
        name="Surprised",
        name_cn="惊讶",
        category=MotionCategory.EXPRESSION,
        description="惊讶的表情",
        duration=1.5,
        loop=False,
        parameters={
            "ParamMouthForm": [0, 0.8, 0],
            "ParamEyeForm": [0, -0.3, 0],
        },
        tags=["表情", "惊讶", "震惊"],
    ),
    MotionPreset(
        id="expression_angry",
        name="Angry",
        name_cn="生气",
        category=MotionCategory.EXPRESSION,
        description="生气的表情",
        duration=1.0,
        loop=False,
        parameters={
            "ParamBrowL": [0, 0.5, 0],
            "ParamBrowR": [0, 0.5, 0],
            "ParamMouthForm": [0, -0.3, 0],
        },
        tags=["表情", "生气", "愤怒"],
    ),

    # 身体动作
    MotionPreset(
        id="body_jump",
        name="Jump",
        name_cn="跳跃",
        category=MotionCategory.BODY,
        description="轻轻跳一下",
        duration=1.0,
        loop=False,
        parameters={
            "ParamBody": [0, 0.1, 0, -0.05, 0],
        },
        tags=["身体", "跳跃", "活泼"],
    ),
    MotionPreset(
        id="body_turn",
        name="Turn Around",
        name_cn="转身",
        category=MotionCategory.BODY,
        description="转身动作",
        duration=3.0,
        loop=False,
        parameters={
            "ParamAngleZ": [0, 30, 0, -30, 0],
        },
        tags=["身体", "转身", "动作"],
    ),
    MotionPreset(
        id="body_shake",
        name="Shake Head",
        name_cn="摇头",
        category=MotionCategory.BODY,
        description="摇头表示否定",
        duration=2.0,
        loop=False,
        parameters={
            "ParamAngleX": [0, -10, 0, 10, 0, -8, 0, 8, 0],
        },
        tags=["身体", "摇头", "否定"],
    ),

    # 互动动作
    MotionPreset(
        id="interaction_thumbs_up",
        name="Thumbs Up",
        name_cn="点赞",
        category=MotionCategory.INTERACTION,
        description="竖起大拇指点赞",
        duration=2.0,
        loop=False,
        parameters={
            "ParamArmRA": [0, -45, 0],
            "ParamHandRA": [0, 1, 0],
        },
        tags=["互动", "点赞", "鼓励"],
    ),
    MotionPreset(
        id="interaction_clap",
        name="Clap",
        name_cn="鼓掌",
        category=MotionCategory.INTERACTION,
        description="拍手鼓掌",
        duration=2.0,
        loop=False,
        parameters={
            "ParamArmLA": [0, 45, 0, 30, 0],
            "ParamArmRA": [0, -45, 0, -30, 0],
        },
        tags=["互动", "鼓掌", "庆祝"],
    ),
    MotionPreset(
        id="interaction_think",
        name="Thinking",
        name_cn="思考",
        category=MotionCategory.INTERACTION,
        description="思考的手势",
        duration=3.0,
        loop=True,
        parameters={
            "ParamArmLA": [0, 20, 0, 15, 0],
            "ParamAngleX": [0, -3, 0, 3, 0],
        },
        tags=["互动", "思考", "学习"],
    ),
]


def get_motion_preset(preset_id: str) -> Optional[MotionPreset]:
    """
    获取指定 ID 的动作预设

    Args:
        preset_id: 预设 ID

    Returns:
        动作预设，如果没有找到返回 None
    """
    for preset in MOTION_PRESETS:
        if preset.id == preset_id:
            return preset
    return None


def get_motion_presets_by_category(category: MotionCategory) -> List[MotionPreset]:
    """
    获取指定分类的所有动作预设

    Args:
        category: 动作分类

    Returns:
        动作预设列表
    """
    return [p for p in MOTION_PRESETS if p.category == category]


def generate_motion_json(preset: MotionPreset) -> Dict[str, Any]:
    """
    将动作预设转换为 Live2D motion3.json 格式

    Args:
        preset: 动作预设

    Returns:
        motion3.json 内容
    """
    curves = []
    total_segments = 0

    for param_id, keyframes in preset.parameters.items():
        # keyframes 格式: [time1, value1, time2, value2, ...]
        segments = []
        time = 0
        for i, value in enumerate(keyframes):
            if i % 2 == 0:
                time = value
            else:
                segments.extend([time, value])
                total_segments += 1

        curves.append({
            "Target": "Parameter",
            "Id": param_id,
            "Segments": segments,
        })

    return {
        "Version": 3,
        "Meta": {
            "Duration": preset.duration * 1000,
            "Fps": 30,
            "Loop": preset.loop,
            "AreBeziersRestricted": True,
            "CurveCount": len(curves),
            "TotalSegmentCount": total_segments,
            "TotalPointCount": total_segments * 2,
        },
        "Curves": curves,
    }


def get_all_presets() -> List[Dict[str, Any]]:
    """
    获取所有动作预设

    Returns:
        动作预设列表（转换为字典格式）
    """
    return [
        {
            "id": p.id,
            "name": p.name,
            "name_cn": p.name_cn,
            "category": p.category.value,
            "category_label": MotionCategory.label(p.category) if hasattr(MotionCategory, 'label') else p.category.value,
            "description": p.description,
            "duration": p.duration,
            "loop": p.loop,
            "tags": p.tags,
        }
        for p in MOTION_PRESETS
    ]


# 添加 category 标签方法
MotionCategory.label = lambda self: {
    MotionCategory.IDLE: "待机",
    MotionCategory.GREETING: "打招呼",
    MotionCategory.EXPRESSION: "表情动作",
    MotionCategory.BODY: "身体动作",
    MotionCategory.INTERACTION: "互动动作",
}[self]


__all__ = [
    "MotionCategory",
    "MotionPreset",
    "MOTION_PRESETS",
    "get_motion_preset",
    "get_motion_presets_by_category",
    "generate_motion_json",
    "get_all_presets",
]
