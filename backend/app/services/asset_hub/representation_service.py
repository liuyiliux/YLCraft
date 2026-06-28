"""
YLCraft — 资产文件表示服务

AssetRepresentation 是资产版本的物理文件表示。
同一版本可以有多个 Representation（不同尺寸、格式、码率）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset_hub import AssetRepresentation, AssetVersion

logger = logging.getLogger("ylcraft.asset_hub.representation")


class AssetRepresentationService:
    """资产文件表示服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    async def create(
        self,
        asset_version_id: str,
        file_path: str,
        mime_type: str,
        file_size: int = 0,
        width: Optional[int] = None,
        height: Optional[int] = None,
        duration: Optional[float] = None,
        format: Optional[str] = None,
        extra: Optional[dict] = None,
    ) -> AssetRepresentation:
        """
        创建文件表示。

        Args:
            asset_version_id: 所属版本 ID
            file_path: 文件存储路径
            mime_type: MIME 类型（image/png、video/mp4...）
            file_size: 文件大小（字节）
            width: 宽度（图片/视频）
            height: 高度
            duration: 时长（秒，视频/音频）
            format: 格式名（png、mp4、wav）
            extra: 扩展元数据
        """
        # 验证版本存在
        version = await self.session.get(AssetVersion, asset_version_id)
        if not version:
            raise ValueError(f"AssetVersion {asset_version_id} 不存在")

        rep = AssetRepresentation(
            id=str(uuid4()),
            asset_version_id=asset_version_id,
            file_path=file_path,
            mime_type=mime_type,
            file_size=file_size,
            width=width,
            height=height,
            duration=duration,
            format=format or self._guess_format(file_path, mime_type),
            extra_json=extra or {},
        )
        self.session.add(rep)
        await self.session.flush()
        await self.session.refresh(rep)
        # asyncpg 把 PG UUID 字段返回为 UUID 对象，统一转 str 避免上游 SQLAlchemy
        # 在写 String 字段时收到 UUID 类型导致 ::VARCHAR 编码失败
        rep.id = str(rep.id)
        rep.asset_version_id = str(rep.asset_version_id)

        logger.info(
            f"[AssetRepresentationService] created | id={rep.id} | "
            f"version={asset_version_id} | path={file_path}"
        )
        return rep

    async def get(self, rep_id: str) -> Optional[AssetRepresentation]:
        """根据 ID 获取"""
        return await self.session.get(AssetRepresentation, rep_id)

    async def delete(self, rep_id: str) -> bool:
        """删除文件表示（不删物理文件，避免影响其他引用）"""
        rep = await self.session.get(AssetRepresentation, rep_id)
        if not rep:
            return False
        await self.session.delete(rep)
        await self.session.flush()
        return True

    # -------------------------------------------------------------------------
    # 查询
    # -------------------------------------------------------------------------

    async def list_by_version(
        self, version_id: str
    ) -> List[AssetRepresentation]:
        """获取版本下的所有文件表示"""
        result = await self.session.execute(
            select(AssetRepresentation)
            .where(AssetRepresentation.asset_version_id == version_id)
            .order_by(AssetRepresentation.file_size.desc())
        )
        return list(result.scalars().all())

    async def get_primary(
        self, version_id: str
    ) -> Optional[AssetRepresentation]:
        """获取主文件表示（文件最大的那个，通常是原图/原视频）"""
        reps = await self.list_by_version(version_id)
        return reps[0] if reps else None

    # -------------------------------------------------------------------------
    # 工具
    # -------------------------------------------------------------------------

    @staticmethod
    def _guess_format(file_path: str, mime_type: str) -> str:
        """从路径或 MIME 推断格式"""
        suffix = Path(file_path).suffix.lstrip(".")
        if suffix:
            return suffix.lower()
        # 从 MIME 推断
        if "/" in mime_type:
            return mime_type.split("/")[-1].lower()
        return mime_type.lower()

    @staticmethod
    def detect_mime_type(file_path: str) -> str:
        """根据扩展名推断 MIME 类型（轻量级，不读取文件头）"""
        suffix = Path(file_path).suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".mp4": "video/mp4",
            ".webm": "video/webm",
            ".mov": "video/quicktime",
            ".avi": "video/x-msvideo",
            ".mkv": "video/x-matroska",
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".flac": "audio/flac",
            ".aac": "audio/aac",
            ".ogg": "audio/ogg",
            ".glb": "model/gltf-binary",
            ".gltf": "model/gltf+json",
            ".fbx": "application/octet-stream",
            ".obj": "application/wavefront-obj",
            ".txt": "text/plain",
            ".json": "application/json",
            ".srt": "application/x-subrip",
            ".vtt": "text/vtt",
        }
        return mime_map.get(suffix, "application/octet-stream")
