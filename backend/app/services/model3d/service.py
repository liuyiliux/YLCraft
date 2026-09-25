"""
YLCraft — 3D 模型服务

实现 3D 模型的元数据提取、格式转换、预览生成：
- 支持格式：glb, gltf, fbx, obj, usdz
- 元数据提取：顶点/面数/材质/骨骼
- TripoSR 图生 3D 集成
"""

from __future__ import annotations

import logging
import base64
import json
import mimetypes
import zipfile
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from uuid import uuid4
from sqlalchemy import String, cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.models.ai_connector import AIConnector
from app.db.models.asset_hub import AssetNode, AssetType

logger = logging.getLogger("ylcraft.model3d_service")


class Model3DService:
    """3D 模型服务"""

    # 支持的 3D 格式
    SUPPORTED_FORMATS = [".glb", ".gltf", ".fbx", ".obj", ".usdz", ".dae"]

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

        metadata.update(self._summarize_gltf(json_data))
        return metadata

    @staticmethod
    def _read_gltf_json(path: Path) -> Dict[str, Any]:
        """读 GLB 的 JSON chunk 或 .gltf 全文（只读，不启 Blender）。"""
        if path.suffix.lower() == ".gltf":
            return json.loads(path.read_text(encoding="utf-8"))
        import struct

        with path.open("rb") as handle:
            handle.read(12)  # magic + version + length
            while True:
                header = handle.read(8)
                if len(header) < 8:
                    return {}
                length, chunk_type = struct.unpack("<I4s", header)
                data = handle.read(length)
                if chunk_type == b"JSON":
                    return json.loads(data.decode("utf-8"))

    @classmethod
    def bone_names(cls, file_path: str) -> List[str]:
        """模型里的骨骼名（按顺序去重）。

        为什么单独做：判断一个模型"是不是已经统一到 Mixamo 命名"只需要读名字，
        为这点事启动一次 Blender（十几秒）太浪费。
        """
        path = Path(file_path)
        if not path.is_file():
            return []
        try:
            gltf = cls._read_gltf_json(path)
        except Exception as e:
            logger.warning(f"[Model3DService] Failed to read glTF JSON: {e}")
            return []
        nodes = gltf.get("nodes") or []
        names: List[str] = []
        seen: set = set()
        for skin in gltf.get("skins") or []:
            for joint in skin.get("joints") or []:
                if not isinstance(joint, int) or not (0 <= joint < len(nodes)):
                    continue
                name = str(nodes[joint].get("name") or "")
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)
        return names

    @staticmethod
    def is_mixamo_skeleton(file_path: str) -> bool:
        """骨骼命名是否已统一到 Mixamo 标准（决定是否还需要改名这一步）。

        Mixamo 是动作库的事实标准——只有两边的骨骼名对得上，动画才能跨模型复用。
        """
        names = Model3DService.bone_names(file_path)
        if not names:
            return False
        return all(name.startswith("mixamorig:") for name in names)

    @staticmethod
    def _summarize_gltf(json_data: dict) -> Dict[str, Any]:
        """统计网格/骨骼/动画。GLB 与 .gltf **共用同一套口径**。

        为什么抽出来（tasks #16 验收发现的真实缺陷）：
        1. 原来把 `len(skins)`（皮肤**套数**）当成骨骼数——vanguard.glb 有 2 套 skin、
           49 根骨骼，报告却写"2 根骨骼"。徽标靠布尔判断没露馅，但落库的数字是错的，
           一旦有人在界面上显示"骨骼 N 根"就会误导"这个绑定只有 2 根骨"。
           骨骼数应按骨架的 **joints** 数，多套 skin 可能共用骨骼，故取并集。
        2. 原来 .gltf 分支根本不提取 skins，导致 GLTF 模型永远打不上「已绑骨」标签。
        """
        accessors = json_data.get("accessors") or []
        meshes = json_data.get("meshes") or []

        total_vertices = 0
        total_faces = 0
        for mesh in meshes:
            for prim in mesh.get("primitives") or []:
                position = (prim.get("attributes") or {}).get("POSITION")
                if isinstance(position, int) and 0 <= position < len(accessors):
                    total_vertices += int(accessors[position].get("count") or 0)
                indices = prim.get("indices")
                if isinstance(indices, int) and 0 <= indices < len(accessors):
                    total_faces += int(accessors[indices].get("count") or 0) // 3

        joints: set = set()
        for skin in json_data.get("skins") or []:
            for joint in skin.get("joints") or []:
                if isinstance(joint, int):
                    joints.add(joint)

        animation_details: list[Dict[str, Any]] = []
        for index, animation in enumerate(json_data.get("animations") or []):
            channels = animation.get("channels") or []
            samplers = animation.get("samplers") or []
            start: Any = None
            end: Any = None
            for channel in channels:
                sampler_index = channel.get("sampler", 0)
                if not isinstance(sampler_index, int) or sampler_index >= len(samplers):
                    continue
                accessor_index = samplers[sampler_index].get("input")
                if not isinstance(accessor_index, int) or accessor_index >= len(accessors):
                    continue
                accessor = accessors[accessor_index]
                minimum = (accessor.get("min") or [None])[0]
                maximum = (accessor.get("max") or [None])[0]
                if minimum is not None:
                    start = minimum if start is None else min(start, minimum)
                if maximum is not None:
                    end = maximum if end is None else max(end, maximum)
            animation_details.append({
                "name": animation.get("name") or f"anim_{index}",
                "channels": len(channels),
                "start": start,
                "end": end,
            })

        summary: Dict[str, Any] = {
            "mesh_count": len(meshes),
            "vertices": total_vertices,
            "faces": total_faces,
            "skins": len(json_data.get("skins") or []),
            "bones": len(joints),
        }
        if json_data.get("materials"):
            summary["materials"] = len(json_data["materials"])
        if json_data.get("textures"):
            summary["textures"] = len(json_data["textures"])
        if animation_details:
            # `animations` 保持名称列表（既有调用方依赖它做布尔与展示）
            summary["animations"] = [item["name"] for item in animation_details]
            summary["animation_count"] = len(animation_details)
            summary["animation_details"] = animation_details
        return summary

    async def _extract_gltf_metadata(self, path: Path) -> Dict[str, Any]:
        """提取 GLTF 文件元数据（与 GLB 共用 `_summarize_gltf`）"""
        with open(path, "r") as f:
            json_data = json.load(f)

        metadata: Dict[str, Any] = {"format": "gltf"}
        metadata.update(self._summarize_gltf(json_data))
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

        用 Blender 无头渲染（`core/blender.py`）。

        Blender 不可用时返回 None 而不是抛错：预览是锦上添花，
        没有它模型照样能用，不该因此让入库或列表整个失败。
        """
        path = Path(file_path)

        if not path.exists():
            return None

        if output_path is None:
            output_path = str(path.parent / f"{path.stem}_preview.png")

        try:
            from app.core.blender import get_blender_service

            service = get_blender_service()
            if not await service.is_available():
                logger.info("[Model3DService] Preview skipped: Blender not available")
                return None
            await service.generate_preview(path, Path(output_path), resolution=resolution)
            return output_path
        except Exception as e:
            logger.error(f"[Model3DService] Failed to generate preview: {e}")
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
        转换 3D 模型格式（Blender 无头，见 `core/blender.py`）。

        这里**抛错**而不是返回 None：转换失败时调用方必须知道，
        否则会拿到一个"说转成了 FBX、实际还是 GLB"的文件。
        """
        source = Path(source_path)

        if not source.exists():
            raise ValueError(f"源文件不存在：{source_path}")

        if output_path is None:
            output_path = str(source.parent / f"{source.stem}.{target_format}")

        from app.core.blender import get_blender_service

        await get_blender_service().convert_format(source, Path(output_path))
        return output_path

    # -------------------------------------------------------------------------
    # Legacy image-to-3D route (now backed by AIConnector)
    # -------------------------------------------------------------------------

    async def _legacy_image_to_3d_connector(self) -> Optional[AIConnector]:
        """Find the explicitly marked TripoSR connector.

        The old route predates provider selection in the request, so it needs
        one deterministic target. The migration tool marks the imported
        connector with ``legacy_image_to_3d=true``; an arbitrary 3D connector
        is never used as a silent fallback.
        """
        if self.session is None:
            return None
        rows = (await self.session.execute(
            select(AIConnector).where(
                cast(AIConnector.provider_type, String) == "3d",
                AIConnector.is_active == True,
            ).order_by(AIConnector.priority, AIConnector.created_at)
        )).scalars().all()
        for row in rows:
            try:
                config = json.loads(row.response_config or "{}")
            except (TypeError, ValueError):
                config = {}
            if isinstance(config, dict) and config.get("legacy_image_to_3d"):
                return row
        return None

    @staticmethod
    def _connector_error_message(exc: Exception) -> str:
        diagnostics = getattr(exc, "diagnostics", {}) or {}
        return (
            diagnostics.get("response_excerpt")
            or diagnostics.get("exception_repr")
            or str(exc)
        )

    @staticmethod
    def _legacy_status(result: Dict[str, Any]) -> str:
        status = str(result.get("status") or "pending").lower()
        if status == "done":
            return "completed"
        if status == "error":
            return "failed"
        if status in {"processing", "running"}:
            return "processing"
        return "pending"

    @classmethod
    def _legacy_result(cls, result: Dict[str, Any], fallback_task_id: str = "") -> Dict[str, Any]:
        status = cls._legacy_status(result)
        return {
            "task_id": result.get("task_id") or fallback_task_id,
            "status": status,
            "progress": result.get("progress", 0),
            "result_url": result.get("url") if status == "completed" else None,
            "error": result.get("error") if status == "failed" else None,
        }

    async def _image_input(self, image_path: str) -> tuple[str, str]:
        """Return ``(data_uri, public_url)`` for the connector submit contract."""
        if image_path.startswith("data:"):
            return image_path, ""
        if image_path.startswith(("http://", "https://")):
            return "", image_path
        path = Path(image_path)
        if not path.is_file():
            raise ValueError(f"图片文件不存在：{image_path}")
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}", ""

    async def generate_3d_from_image(
        self,
        image_path: str,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Legacy TripoSR API facade backed by the configured connector.

        This keeps the existing HTTP endpoints and return keys stable while
        routing upload, submit, poll, and error mapping through
        ``Model3DConnectorBackend``. Business code no longer reads TRIPOSR
        environment variables or calls the provider directly.
        """
        from app.services.model3d.workspace import Model3DConnectorBackend

        connector = await self._legacy_image_to_3d_connector()
        if connector is None:
            return {
                "error": "未找到标记为 legacy_image_to_3d 的 TripoSR 连接器；"
                "请先运行迁移脚本或在 AI 连接器中创建/启用该连接器"
            }

        backend = Model3DConnectorBackend(connector)
        if task_id:
            try:
                result = await backend.poll(task_id)
            except Exception as exc:  # noqa: BLE001 - preserve readable error to legacy response
                return {"error": self._connector_error_message(exc)}
            return self._legacy_result(result, task_id)

        try:
            source_image, source_url = await self._image_input(image_path)
            result = await backend.submit(
                prompt="",
                source_image=source_image,
                source_url=source_url,
                model=connector.default_model,
            )
        except Exception as exc:  # noqa: BLE001 - preserve readable error to legacy response
            return {"error": self._connector_error_message(exc)}
        return self._legacy_result(result)

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
