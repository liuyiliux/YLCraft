"""
YLCraft — Live2D VTS 导出服务

将绑骨后的 Live2D 模型导出为 VTube Studio 可识别的格式。
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List


class VTSFileType(str, Enum):
    """VTS 文件类型"""
    MODEL3_JSON = "model3.json"
    SETTINGS_JSON = "settings.json"
    METADATA_JSON = "metadata.json"


@dataclass
class VTSModelSettings:
    """VTS 模型设置"""
    version: int = 3  # Cubism 4
    name: str = "Live2D Model"
    id: str = "live2d-model"
    model: str = "model.moc3"
    textures: List[str] = field(default_factory=list)
    physics: str = "physics.json"
    pose: str = "pose.json"
    expressions: List[Dict[str, Any]] = field(default_factory=list)
    layout: Dict[str, float] = field(default_factory=lambda: {
        "width": 1.0,
        "height": 1.0,
        "x": 0.0,
        "y": 0.0,
    })
    hit_areas: List[Dict[str, Any]] = field(default_factory=list)
    motion_groups: Dict[str, List[str]] = field(default_factory=dict)
    user_data: str = "userData.json"


@dataclass
class VTSExpression:
    """VTS 表情"""
    name: str
    file: str
    fade_in: float = 1.0
    fade_out: float = 1.0


@dataclass
class VTSMotion:
    """VTS 动作"""
    name: str
    file: str
    fade_in: float = 1.0
    fade_out: float = 1.0
    loop: bool = True


class VTSExporter:
    """
    VTS 格式导出器

    生成 VTube Studio 可识别的模型文件：
    - model.json: 模型主配置
    - settings.json: VTS 特定设置
    - textures/: 纹理图片
    - motions/: 动作文件
    - expressions/: 表情文件
    """

    def __init__(self, model_id: str):
        self.model_id = model_id
        self.model_name = f"model_{model_id[:8]}"

    def generate_model_config(
        self,
        rigging_data: Dict[str, Any],
        motion_groups: Optional[Dict[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """
        生成 model.json 配置

        Args:
            rigging_data: 绑骨数据
            motion_groups: 动作组

        Returns:
            model.json 内容
        """
        return {
            "Version": 3,
            "FileReferences": {
                "Moc": "model.moc3",
                "Textures": [
                    "textures/texture_00.png",
                ],
                "Physics": "physics.json",
                "Pose": "pose.json",
                "Expressions": [
                    {"Name": exp["name"], "File": exp["file"]}
                    for exp in rigging_data.get("expressions", [])
                ],
                "Motions": motion_groups or {
                    "Idle": ["motions/idle.motion3.json"],
                    "TapBody": ["motions/tap_body.motion3.json"],
                },
            },
            "Groups": [
                {
                    "Target": "Parameter",
                    "Name": "LipSync",
                    "Ids": ["ParamMouthOpenY"],
                },
                {
                    "Target": "Parameter",
                    "Name": "EyeBlink",
                    "Ids": ["ParamEyeLOpen", "ParamEyeROpen"],
                },
            ],
            "Layout": {
                "Width": rigging_data.get("layout_width", 1.0),
                "Height": rigging_data.get("layout_height", 1.0),
                "X": 0.0,
                "Y": 0.0,
                "CenterX": 0.0,
                "CenterY": 0.0,
            },
            "HitAreas": [
                {"Name": "Head", "Id": "HitArea"},
                {"Name": "Body", "Id": "HitArea2"},
            ],
            "Name": self.model_name,
            "Id": f"live2d-{self.model_id}",
        }

    def generate_settings(self, model_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成 settings.json (VTS 特定设置)

        Args:
            model_config: model.json 配置

        Returns:
            settings.json 内容
        """
        return {
            "model_id": f"live2d-{self.model_id}",
            "model_name": model_config.get("Name", self.model_name),
            "vendor": "YLCraft",
            "model_version": "1.0.0",
            "is_builtin": False,
            "model_load_at_once": False,
            "model_path": "",
            " Physics": {
                "mx": 0.0,
                "my": 0.0,
                "vx": 0.0,
                "vy": 0.0,
                "primary_velocity": 0.0,
            },
            "expressions": [
                {
                    "name": exp["Name"],
                    "file": exp["File"],
                    "fade_in": 1.0,
                    "fade_out": 1.0,
                }
                for exp in model_config.get("FileReferences", {}).get("Expressions", [])
            ],
            "motion_groups": {
                group_name: [
                    {"file": motion_file, "fade_in": 1.0, "fade_out": 1.0, "priority": 0}
                    for motion_file in motion_files
                ]
                for group_name, motion_files in model_config.get("FileReferences", {}).get("Motions", {}).items()
            },
            "auto_motion_expression_priority": 75,
            "auto_motion_body_priority": 75,
            "auto_motion_leading_priority": 75,
            "artmesh_optimization": {
                "exclude_hidden_artmeshes": False,
                "exclude_desktop_artmeshes_from_mobile": False,
                "exclude_mobile_artmeshes_from_desktop": False,
            },
        }

    def generate_physics(self) -> Dict[str, Any]:
        """生成 physics.json (物理模拟配置)"""
        return {
            "Version": 3,
            "PhysicsSettings": [
                {
                    "Id": "PhysicsSetting",
                    "Input": [
                        {
                            "SourceId": "ParamAngleX",
                            "Type": "X",
                            "Weight": 0.5,
                        },
                    ],
                    "Output": [
                        {
                            "DestinationId": "ParamAngleX",
                            "Type": "Angle",
                            "Value": 30.0,
                            "Weight": 1.0,
                        },
                    ],
                    "Vertices": [
                        {"X": 0.0, "Y": 0.0},
                        {"X": 0.0, "Y": 1.0},
                    ],
                    "Normalization": {
                        "Position": {
                            "X": {"Min": -10.0, "Max": 10.0},
                            "Y": {"Min": -10.0, "Max": 10.0},
                        },
                    },
                },
            ],
        }

    def generate_pose(self) -> Dict[str, Any]:
        """生成 pose.json (姿态配置)"""
        return {
            "Version": 3,
            "PoseInfo": {
                "Name": "Pose",
                "Groups": [
                    {
                        "Id": "Group",
                        "Link": [
                            {"Id": "ParamBody"},
                        ],
                    },
                ],
            },
            "FadeInTime": 1.0,
            "FadeOutTime": 1.0,
        }

    def generate_idle_motion(self) -> Dict[str, Any]:
        """
        生成待机动作

        Returns:
            motion3.json 内容
        """
        return {
            "Version": 3,
            "Meta": {
                "Duration": 4000,
                "Fps": 30,
                "Loop": True,
                "AreBeziersRestricted": True,
                "CurveCount": 3,
                "TotalSegmentCount": 4,
                "TotalPointCount": 6,
            },
            "Curves": [
                {
                    "Target": "Parameter",
                    "Id": "ParamAngleX",
                    "Segments": [0, 0, 0, 0, 2, 0, 0, 4000, 0],
                },
                {
                    "Target": "Parameter",
                    "Id": "ParamEyeLOpen",
                    "Segments": [0, 1, 0, 0, 1, 0, 0, 4000, 1],
                },
                {
                    "Target": "Parameter",
                    "Id": "ParamEyeROpen",
                    "Segments": [0, 1, 0, 0, 1, 0, 0, 4000, 1],
                },
            ],
        }

    def export(
        self,
        rigging_data: Dict[str, Any],
        output_dir: Path,
        include_motions: bool = True,
    ) -> Dict[str, Any]:
        """
        导出模型

        Args:
            rigging_data: 绑骨数据
            output_dir: 输出目录
            include_motions: 是否包含动作文件

        Returns:
            导出结果
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # 生成配置文件
        model_config = self.generate_model_config(rigging_data)
        settings = self.generate_settings(model_config)
        physics = self.generate_physics()
        pose = self.generate_pose()

        # 写入配置文件
        with open(output_dir / "model.json", "w", encoding="utf-8") as f:
            json.dump(model_config, f, indent=2, ensure_ascii=False)

        with open(output_dir / "settings.json", "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)

        with open(output_dir / "physics.json", "w", encoding="utf-8") as f:
            json.dump(physics, f, indent=2, ensure_ascii=False)

        with open(output_dir / "pose.json", "w", encoding="utf-8") as f:
            json.dump(pose, f, indent=2, ensure_ascii=False)

        # 创建纹理目录
        textures_dir = output_dir / "textures"
        textures_dir.mkdir(exist_ok=True)

        # 创建动作目录
        motions_dir = output_dir / "motions"
        motions_dir.mkdir(exist_ok=True)

        if include_motions:
            # 生成待机动作
            idle_motion = self.generate_idle_motion()
            with open(motions_dir / "idle.motion3.json", "w", encoding="utf-8") as f:
                json.dump(idle_motion, f, indent=2, ensure_ascii=False)

        # 创建 ZIP 包
        zip_path = output_dir / f"{self.model_name}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in output_dir.glob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.name)

            for file_path in textures_dir.glob("*"):
                if file_path.is_file():
                    zf.write(file_path, f"textures/{file_path.name}")

            for file_path in motions_dir.glob("*"):
                if file_path.is_file():
                    zf.write(file_path, f"motions/{file_path.name}")

        return {
            "success": True,
            "model_id": self.model_id,
            "model_name": self.model_name,
            "output_dir": str(output_dir),
            "zip_path": str(zip_path),
            "files": {
                "model_config": str(output_dir / "model.json"),
                "settings": str(output_dir / "settings.json"),
                "physics": str(output_dir / "physics.json"),
                "pose": str(output_dir / "pose.json"),
            },
            "metadata": {
                "exported_at": datetime.now().isoformat(),
                "version": "1.0.0",
                "vendor": "YLCraft",
            },
        }


def export_to_vts(
    model_id: str,
    rigging_data: Dict[str, Any],
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    便捷函数：导出模型为 VTS 格式

    Args:
        model_id: 模型ID
        rigging_data: 绑骨数据
        output_dir: 输出目录

    Returns:
        导出结果
    """
    if output_dir is None:
        output_dir = Path("uploads/live2d") / model_id / "export"

    exporter = VTSExporter(model_id)
    return exporter.export(rigging_data, output_dir)


__all__ = [
    "VTSExporter",
    "VTSModelSettings",
    "VTSExpression",
    "VTSMotion",
    "export_to_vts",
]
