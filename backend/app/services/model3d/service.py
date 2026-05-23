"""
YLCraft — 3D 模型服务

实现 3D 模型的元数据提取、格式转换、预览生成：
- 支持格式：glb, gltf, fbx, obj, usdz
- 元数据提取：顶点/面数/材质/骨骼
- TripoSR 图生 3D 集成
"""

from __future__ import annotations

import logging
import os
import json
import zipfile
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from uuid import uuid4
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset_hub import AssetNode, AssetType

logger = logging.getLogger("ylcraft.model3d_service")


class Model3DService:
    """3D 模型服务"""

    # 支持的 3D 格式
    SUPPORTED_FORMATS = [".glb", ".gltf", ".fbx", ".obj", ".usdz", ".dae"]

    # TripoSR API 配置
    TRIPOSR_API_BASE = "https://api.tripo3d.ai/api/v1"
    TRIPOSR_API_KEY = os.getenv("TRIPOSR_API_KEY", "")

    def __init__(self, session: AsyncSession):
        self.session = session

    # -------------------------------------------------------------------------
    # 格式检测和验证
    # -------------------------------------------------------------------------

    def is_supported_format(self, file_path: str) -> bool:
        """检查是否是支持的 3D 格式"""
        ext = Path(file_path).suffix.lower()
        return ext in self.SUPPORTED_FORMATS

    def get_format_info(self, file_path: str) -> Dict[str, Any]:
        """获取 3D 模型格式信息"""
        path = Path(file_path)

        if not path.exists():
            return {"error": "File not found"}

        ext = path.suffix.lower()

        format_info = {
            "extension": ext,
            "filename": path.name,
            "size": path.stat().st_size,
            "mime_type": self._get_mime_type(ext),
        }

        return format_info

    def _get_mime_type(self, ext: str) -> str:
        """获取 MIME 类型"""
        mime_types = {
            ".glb": "model/gltf-binary",
            ".gltf": "model/gltf+json",
            ".fbx": "application/octet-stream",
            ".obj": "model/obj",
            ".usdz": "model/vnd.usdz+zip",
            ".dae": "model/vnd.collada+xml",
        }
        return mime_types.get(ext, "application/octet-stream")

    # -------------------------------------------------------------------------
    # 元数据提取
    # -------------------------------------------------------------------------

    async def extract_metadata(self, file_path: str) -> Dict[str, Any]:
        """
        提取 3D 模型元数据

        返回格式：
        {
            "vertices": 12345,
            "faces": 10000,
            "materials": 3,
            "textures": ["diffuse.png", "normal.png"],
            "animations": ["idle", "walk"],
            "bones": 25,
            "blend_shapes": ["smile", "blink"],
            "bounding_box": {"width": 1.0, "height": 2.0, "depth": 0.5}
        }
        """
        path = Path(file_path)

        if not path.exists():
            return {"error": "File not found"}

        ext = path.suffix.lower()

        try:
            if ext == ".glb":
                return await self._extract_glb_metadata(path)
            elif ext == ".gltf":
                return await self._extract_gltf_metadata(path)
            elif ext == ".obj":
                return await self._extract_obj_metadata(path)
            else:
                # 其他格式，返回基本信息
                return {
                    "extension": ext,
                    "size": path.stat().st_size,
                    "note": "Detailed extraction not supported for this format",
                }
        except Exception as e:
            logger.error(f"[Model3DService] Failed to extract metadata: {e}")
            return {"error": str(e)}

    async def _extract_glb_metadata(self, path: Path) -> Dict[str, Any]:
        """提取 GLB 文件元数据"""
        import struct

        with open(path, "rb") as f:
            # 读取 GLB 头部
            magic = f.read(4)
            if magic != b"glTF":
                return {"error": "Invalid GLB file"}

            version = struct.unpack("<I", f.read(4))[0]
            length = struct.unpack("<I", f.read(4))[0]

            # 读取 JSON chunk
            chunk_length = struct.unpack("<I", f.read(4))[0]
            chunk_type = struct.unpack("<I", f.read(4))[0]

            json_data = json.loads(f.read(chunk_length))

        # 提取基本信息
        metadata = {
            "format": "glb",
            "version": version,
        }

        # 资产信息
        if "asset" in json_data:
            asset = json_data["asset"]
            metadata["generator"] = asset.get("generator", "")
            metadata["version"] = asset.get("version", "")

        # 场景信息
        if "scene" in json_data:
            metadata["scene"] = json_data["scene"]

        # 节点统计
        if "nodes" in json_data:
            metadata["node_count"] = len(json_data["nodes"])

        # 网格统计
        if "meshes" in json_data:
            total_vertices = 0
            total_faces = 0
            for mesh in json_data["meshes"]:
                for prim in mesh.get("primitives", []):
                    if "attributes" in prim and "POSITION" in prim["attributes"]:
                        accessor = json_data["accessors"][prim["attributes"]["POSITION"]]
                        total_vertices += accessor.get("count", 0)
                    if "indices" in prim:
                        accessor = json_data["accessors"][prim["indices"]]
                        total_faces += accessor.get("count", 0) // 3

            metadata["mesh_count"] = len(json_data["meshes"])
            metadata["vertices"] = total_vertices
            metadata["faces"] = total_faces

        # 材质数量
        if "materials" in json_data:
            metadata["materials"] = len(json_data["materials"])

        # 纹理数量
        if "textures" in json_data:
            metadata["textures"] = len(json_data["textures"])

        # 动画数量
        if "animations" in json_data:
            metadata["animations"] = [anim.get("name", f"anim_{i}") for i, anim in enumerate(json_data["animations"])]

        # 皮肤（骨骼）数量
        if "skins" in json_data:
            metadata["bones"] = len(json_data["skins"])

        return metadata

    async def _extract_gltf_metadata(self, path: Path) -> Dict[str, Any]:
        """提取 GLTF 文件元数据"""
        with open(path, "r") as f:
            json_data = json.load(f)

        metadata = {
            "format": "gltf",
        }

        # 复用 GLB 逻辑
        if "meshes" in json_data:
            total_vertices = 0
            total_faces = 0
            for mesh in json_data["meshes"]:
                for prim in mesh.get("primitives", []):
                    if "attributes" in prim and "POSITION" in prim["attributes"]:
                        accessor = json_data["accessors"][prim["attributes"]["POSITION"]]
                        total_vertices += accessor.get("count", 0)
                    if "indices" in prim:
                        accessor = json_data["accessors"][prim["indices"]]
                        total_faces += accessor.get("count", 0) // 3

            metadata["vertices"] = total_vertices
            metadata["faces"] = total_faces

        if "materials" in json_data:
            metadata["materials"] = len(json_data["materials"])

        if "animations" in json_data:
            metadata["animations"] = len(json_data["animations"])

        return metadata

    async def _extract_obj_metadata(self, path: Path) -> Dict[str, Any]:
        """提取 OBJ 文件元数据（简单实现）"""
        vertices = 0
        faces = 0
        materials = set()

        with open(path, "r") as f:
            for line in f:
                if line.startswith("v "):
                    vertices += 1
                elif line.startswith("f "):
                    faces += 1
                elif line.startswith("usemtl "):
                    materials.add(line.split()[1].strip())

        return {
            "format": "obj",
            "vertices": vertices,
            "faces": faces,
            "materials": len(materials),
        }

    # -------------------------------------------------------------------------
    # 预览生成
    # -------------------------------------------------------------------------

    async def generate_preview(
        self,
        file_path: str,
        output_path: Optional[str] = None,
        resolution: int = 512,
    ) -> Optional[str]:
        """
        生成 3D 模型预览图（预留接口）

        实际实现需要集成 Blender 或 three.js 进行服务端渲染
        """
        path = Path(file_path)

        if not path.exists():
            return None

        if output_path is None:
            output_path = str(path.parent / f"{path.stem}_preview.png")

        # TODO: 集成服务端渲染
        # 方案1: 使用 Blender 命令行渲染
        # 方案2: 使用 headless three.js
        logger.info(f"[Model3DService] Preview generation not implemented: {file_path}")

        return None

    # -------------------------------------------------------------------------
    # 格式转换
    # -------------------------------------------------------------------------

    async def convert_format(
        self,
        source_path: str,
        target_format: str,
        output_path: Optional[str] = None,
    ) -> Optional[str]:
        """
        转换 3D 模型格式（预留接口）

        需要 Blender 或 pyransport 进行格式转换
        """
        source = Path(source_path)

        if not source.exists():
            return None

        if output_path is None:
            output_path = str(source.parent / f"{source.stem}.{target_format}")

        # TODO: 集成 Blender Python SDK
        # bpy.ops.import_scene.gltf(filepath=source_path)
        # bpy.ops.export_scene.gltf(filepath=output_path)

        logger.info(f"[Model3DService] Format conversion not implemented: {source_path} -> {target_format}")

        return None

    # -------------------------------------------------------------------------
    # TripoSR 图生 3D
    # -------------------------------------------------------------------------

    async def generate_3d_from_image(
        self,
        image_path: str,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        使用 TripoSR 从图片生成 3D 模型

        Args:
            image_path: 图片路径或 URL
            task_id: 已有任务 ID（用于查询进度）

        Returns:
            {"task_id": "...", "status": "pending"|"processing"|"completed", "result_url": "..."}
        """
        if not self.TRIPOSR_API_KEY:
            return {"error": "TripoSR API key not configured"}

        # 如果没有 task_id，创建新任务
        if not task_id:
            return await self._create_triposr_task(image_path)

        # 查询任务状态
        return await self._get_triposr_task_status(task_id)

    async def _create_triposr_task(self, image_path: str) -> Dict[str, Any]:
        """创建 TripoSR 任务"""
        headers = {
            "Authorization": f"Bearer {self.TRIPOSR_API_KEY}",
        }

        # 处理图片（可以是 URL 或上传）
        if image_path.startswith("http"):
            # 在线图片
            payload = {"image_url": image_path}
        else:
            # 本地图片，需要上传
            try:
                with open(image_path, "rb") as f:
                    files = {"file": f}
                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            f"{self.TRIPOSR_API_BASE}/upload",
                            headers=headers,
                            files=files,
                            timeout=60,
                        )
                        response.raise_for_status()
                        upload_result = response.json()
                        image_url = upload_result.get("url", "")
            except Exception as e:
                logger.error(f"[Model3DService] Failed to upload image: {e}")
                return {"error": f"Upload failed: {e}"}

            payload = {"image_url": image_url}

        # 创建生成任务
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.TRIPOSR_API_BASE}/task",
                    headers=headers,
                    json=payload,
                    timeout=30,
                )
                response.raise_for_status()
                result = response.json()
                return {
                    "task_id": result.get("task_id"),
                    "status": "pending",
                }
        except httpx.HTTPError as e:
            logger.error(f"[Model3DService] TripoSR API error: {e}")
            return {"error": str(e)}

    async def _get_triposr_task_status(self, task_id: str) -> Dict[str, Any]:
        """查询 TripoSR 任务状态"""
        headers = {
            "Authorization": f"Bearer {self.TRIPOSR_API_KEY}",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.TRIPOSR_API_BASE}/task/{task_id}",
                    headers=headers,
                    timeout=30,
                )
                response.raise_for_status()
                result = response.json()

                return {
                    "task_id": task_id,
                    "status": result.get("status"),  # pending, processing, completed, failed
                    "progress": result.get("progress", 0),
                    "result_url": result.get("result", {}).get("model_url") if result.get("status") == "completed" else None,
                    "error": result.get("error") if result.get("status") == "failed" else None,
                }
        except httpx.HTTPError as e:
            logger.error(f"[Model3DService] TripoSR API error: {e}")
            return {"error": str(e)}

    # -------------------------------------------------------------------------
    # 资产关联
    # -------------------------------------------------------------------------

    async def create_3d_asset(
        self,
        file_path: str,
        name: str,
        metadata: Optional[Dict[str, Any]] = None,
        parent_id: Optional[str] = None,
    ) -> Optional[AssetNode]:
        """创建 3D 模型资产"""
        path = Path(file_path)

        if not path.exists():
            return None

        # 提取元数据（如果未提供）
        if metadata is None:
            metadata = await self.extract_metadata(str(path))

        asset = AssetNode(
            id=str(uuid4()),
            name=name,
            asset_type=AssetType.THREE_D_MODEL,
            parent_id=parent_id,
            metadata_json=metadata,
        )

        self.session.add(asset)
        await self.session.commit()
        await self.session.refresh(asset)

        logger.info(f"[Model3DService] Created 3D asset: {name}")
        return asset
