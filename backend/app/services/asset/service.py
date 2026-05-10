"""
YLCraft — AssetService CRUD 实现

支持素材资产的完整 CRUD、标签管理、软删除。
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset import Asset, AssetTag

logger = logging.getLogger("ylcraft.asset_service")


class AssetService:
    """素材资产 CRUD 服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # -------------------------------------------------------------------------
    # 资产 CRUD
    # -------------------------------------------------------------------------

    async def list_assets(
        self,
        asset_type: str | None = None,
        platform: str | None = None,
        source_type: str | None = None,
        status: str | None = None,
        search: str | None = None,
        tags: list[str] | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Asset], int]:
        """
        多条件分页查询资产。
        返回 (资产列表, 总数)
        """
        conditions = []
        if asset_type:
            conditions.append(Asset.type == asset_type)
        if platform:
            conditions.append(Asset.platform == platform)
        if source_type:
            conditions.append(Asset.source_type == source_type)
        if status:
            conditions.append(Asset.status == status)
        if search:
            conditions.append(Asset.title.contains(search))

        query = select(Asset)
        if conditions:
            for cond in conditions:
                query = query.where(cond)

        # 标签过滤（JSON 数组包含）
        if tags:
            for tag in tags:
                conditions.append(Asset.tags.contains(tag))

        # 总数
        count_query = select(func.count(Asset.id))
        if conditions:
            for cond in conditions:
                count_query = count_query.where(cond)
        total = (await self.session.execute(count_query)).scalar_one()

        # 排序
        sort_column = getattr(Asset, sort_by, Asset.created_at)
        if sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # 分页
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)

        result = await self.session.execute(query)
        assets = result.scalars().all()
        return list(assets), total

    async def get_by_id(self, asset_id: str) -> Asset | None:
        """根据 ID 获取资产"""
        result = await self.session.execute(
            select(Asset).where(Asset.id == asset_id)
        )
        return result.scalar_one_or_none()

    async def get_by_url(self, url: str) -> Asset | None:
        """根据 source_url 查找资产（用于去重）"""
        result = await self.session.execute(
            select(Asset).where(Asset.source_url == url)
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> Asset:
        """创建资产记录"""
        asset = Asset(**kwargs)
        self.session.add(asset)
        await self.session.flush()
        await self.session.refresh(asset)
        return asset

    async def create_from_parse(
        self,
        source_url: str,
        title: str,
        platform: str,
        author: str = "",
        cover_url: str = "",
        duration: int = 0,
        metadata: dict | None = None,
        asset_type: str = "VIDEO",
    ) -> Asset:
        """
        从解析结果创建资产记录（status=PARSED）。

        用于 parse 接口：解析完成后先创建资产占位，
        下载完成后再更新为 READY。
        """
        # 检查是否已存在（URL 去重）
        existing = await self.get_by_url(source_url)
        if existing:
            # 已存在则更新元信息
            existing.title = title
            existing.author = author
            if cover_url:
                existing.cover_url = cover_url
            if duration:
                existing.duration = duration
            if metadata:
                # 合并 metadata（保留旧值，只更新新值）
                try:
                    existing_meta = json.loads(existing.metadata_json)
                    existing_meta.update(metadata)
                    existing.metadata_json = json.dumps(existing_meta, ensure_ascii=False)
                except:
                    existing.metadata_json = json.dumps(metadata, ensure_ascii=False)
            existing.updated_at = datetime.now()
            await self.session.flush()
            await self.session.refresh(existing)
            return existing

        # 新建记录
        asset = Asset(
            type=asset_type.upper() if asset_type else "VIDEO",
            title=title,
            source_url=source_url,
            platform=platform,
            author=author,
            cover_url=cover_url,
            duration=duration,
            status="PARSED",
            source_type="parse",  # 视频解析来源
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
            tags="[]",
        )
        self.session.add(asset)
        await self.session.flush()
        await self.session.refresh(asset)
        logger.info(f"[AssetService] created asset | id={asset.id} | title={title}")
        return asset

    async def create_from_ai(
        self,
        title: str,
        file_path: str,
        file_size: int,
        mime_type: str,
        asset_type: str = "image",
        ai_model: str = "",
        ai_prompt: str = "",
        ai_negative_prompt: str = "",
        ai_params: dict | None = None,
        thumbnail_path: str = "",
        width: int = 0,
        height: int = 0,
        duration: int = 0,
    ) -> Asset:
        """
        从 AI 生成结果创建资产记录（status=READY）。

        用于 AI 生图/生视频接口：生成完成后直接创建 READY 状态的资产。
        """
        # 构建 metadata（类型特定字段存入 JSON）
        metadata = {
            "source_type": "ai_generated",
            "ai_model": ai_model,
            "ai_prompt": ai_prompt,
            "ai_negative_prompt": ai_negative_prompt,
        }
        if ai_params:
            metadata["ai_params"] = ai_params

        asset = Asset(
            type=asset_type,
            title=title,
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            width=width,
            height=height,
            duration=duration,
            cover_url=thumbnail_path or "",
            source_type="ai_generated",  # 主表字段也要设置
            status="ready",
            metadata_json=json.dumps(metadata, ensure_ascii=False),
            tags="[]",
        )
        self.session.add(asset)
        await self.session.flush()
        await self.session.refresh(asset)
        logger.info(f"[AssetService] created AI asset | id={asset.id} | model={ai_model}")
        return asset

    async def create_from_image_generation(
        self,
        image_path: str,
        prompt: str,
        provider: str,
        model: str,
        seed: int | None = None,
        url: str = "",
        negative_prompt: str = "",
        size: str = "1024x1024",
        steps: int | None = None,
        cfg_scale: float | None = None,
        sampler: str = "",
        lora: str = "",
        controlnet: str = "",
        source_image: str = "",
        reference_images: list[str] | None = None,
    ) -> Asset:
        """
        从图像生成结果创建资产。
        """
        from pathlib import Path
        path = Path(image_path)
        file_size = path.stat().st_size if path.exists() else 0

        # 尝试读取图片尺寸
        width, height = 0, 0
        mime_type = "image/png"
        if path.suffix.lower() in [".jpg", ".jpeg"]:
            mime_type = "image/jpeg"
        elif path.suffix.lower() == ".webp":
            mime_type = "image/webp"
        elif path.suffix.lower() == ".gif":
            mime_type = "image/gif"

        # 尝试用 PIL 获取尺寸
        try:
            from PIL import Image
            with Image.open(path) as img:
                width, height = img.size
        except Exception:
            pass

        # 构建生成模式标签
        gen_tags = ["ai-generated", provider, model]
        if source_image or reference_images:
            gen_tags.append("image-to-image")

        # 构建完整元数据
        metadata: dict = {
            "provider": provider,
            "model": model,
            "seed": seed,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "size": size,
        }
        if steps is not None:
            metadata["steps"] = steps
        if cfg_scale is not None:
            metadata["cfg_scale"] = cfg_scale
        if sampler:
            metadata["sampler"] = sampler
        if lora:
            metadata["lora"] = lora
        if controlnet:
            metadata["controlnet"] = controlnet
        if source_image:
            metadata["source_image"] = source_image
        if reference_images:
            metadata["reference_images"] = reference_images

        asset = Asset(
            type="image",
            title=prompt[:100] if prompt else "AI Generated Image",
            file_path=str(path),
            source_url=url or f"ylcraft://image/{path.name}",
            platform=provider,
            author=f"AI ({model})",
            description=prompt,
            file_size=file_size,
            width=width,
            height=height,
            mime_type=mime_type,
            cover_url=str(path),
            source_type="ai_generated",
            status="ready",
            tags=json.dumps(gen_tags, ensure_ascii=False),
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )
        self.session.add(asset)
        await self.session.flush()
        await self.session.refresh(asset)
        logger.info(f"[AssetService] created image asset | id={asset.id} | model={model}")
        return asset

    async def create_from_video_generation(
        self,
        video_path: str,
        prompt: str,
        provider: str,
        model: str,
        duration: int,
        seed: int | None = None,
        url: str = "",
        negative_prompt: str = "",
        resolution: str = "720p",
        aspect_ratio: str = "9:16",
        generate_audio: bool = True,
        start_image: str = "",
        reference_images: list[str] | None = None,
    ) -> Asset:
        """
        从视频生成结果创建资产。
        """
        from pathlib import Path
        path = Path(video_path)
        file_size = path.stat().st_size if path.exists() else 0

        # 尝试用 ffprobe 获取视频信息
        width, height = 0, 0
        mime_type = "video/mp4"
        try:
            import subprocess
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=width,height",
                    "-of", "csv=p=0",
                    str(path)
                ],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(",")
                if len(parts) == 2:
                    width, height = int(parts[0]), int(parts[1])
        except Exception:
            pass

        # 构建生成模式标签
        gen_tags = ["ai-generated", provider, model]
        if start_image or reference_images:
            gen_tags.append("image-to-video")

        # 构建完整元数据
        metadata: dict = {
            "provider": provider,
            "model": model,
            "seed": seed,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "duration": duration,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "generate_audio": generate_audio,
        }
        if start_image:
            metadata["start_image"] = start_image
        if reference_images:
            metadata["reference_images"] = reference_images

        asset = Asset(
            type="video",
            title=prompt[:100] if prompt else "AI Generated Video",
            file_path=str(path),
            source_url=url or f"ylcraft://video/{path.name}",
            platform=provider,
            author=f"AI ({model})",
            description=prompt,
            file_size=file_size,
            duration=duration,
            width=width,
            height=height,
            mime_type=mime_type,
            source_type="ai_generated",
            status="ready",
            tags=json.dumps(gen_tags, ensure_ascii=False),
            metadata_json=json.dumps(metadata, ensure_ascii=False),
        )
        self.session.add(asset)
        await self.session.flush()
        await self.session.refresh(asset)
        logger.info(f"[AssetService] created video asset | id={asset.id} | model={model}")
        return asset

    async def mark_ready(self, asset: Asset, file_path: str, file_size: int, mime_type: str) -> Asset:
        """将 parsed 状态的资产标记为 ready（下载完成后调用）"""
        asset.file_path = file_path
        asset.file_size = file_size
        asset.mime_type = mime_type
        asset.status = "READY"
        asset.updated_at = datetime.now()
        await self.session.flush()
        await self.session.refresh(asset)
        logger.info(f"[AssetService] marked ready | id={asset.id} | path={file_path[:60]}")
        return asset

    async def update_tags(self, asset: Asset, tag_names: list[str]) -> Asset:
        """更新资产的标签列表"""
        asset.tags = json.dumps(tag_names, ensure_ascii=False)
        asset.updated_at = datetime.now()
        await self.session.flush()
        await self.session.refresh(asset)
        # 更新标签计数
        for tag_name in tag_names:
            await self._inc_tag_count(tag_name)
        return asset

    async def delete(self, asset_id: str, hard: bool = False) -> bool:
        """
        删除资产。
        - hard=False：软删除（保留记录）
        - hard=True：同时删除物理文件和数据库记录
        """
        asset = await self.get_by_id(asset_id)
        if not asset:
            return False

        if hard:
            # 删除物理文件
            if asset.file_path and os.path.exists(asset.file_path):
                try:
                    os.remove(asset.file_path)
                    logger.info(f"Deleted file: {asset.file_path}")
                except OSError as e:
                    logger.warning(f"Failed to delete file {asset.file_path}: {e}")
            # 删除缩略图（从 metadata_json 中读取路径）
            try:
                if asset.metadata_json:
                    meta = json.loads(asset.metadata_json)
                    thumbnail_path = meta.get("thumbnail_path", "")
                    if thumbnail_path and os.path.exists(thumbnail_path):
                        os.remove(thumbnail_path)
            except Exception:
                pass

        await self.session.delete(asset)
        await self.session.flush()
        return True

    # -------------------------------------------------------------------------
    # 标签管理
    # -------------------------------------------------------------------------

    async def list_tags(self) -> list[AssetTag]:
        """列出所有标签"""
        result = await self.session.execute(
            select(AssetTag).order_by(AssetTag.asset_count.desc())
        )
        return list(result.scalars().all())

    async def get_or_create_tag(self, name: str, color: str = "#1890ff") -> AssetTag:
        """根据名称查找标签，不存在则创建"""
        result = await self.session.execute(
            select(AssetTag).where(AssetTag.name == name)
        )
        tag = result.scalar_one_or_none()
        if tag:
            return tag
        tag = AssetTag(name=name, color=color)
        self.session.add(tag)
        await self.session.flush()
        await self.session.refresh(tag)
        return tag

    async def _inc_tag_count(self, tag_name: str) -> None:
        """增加标签计数"""
        result = await self.session.execute(
            select(AssetTag).where(AssetTag.name == tag_name)
        )
        tag = result.scalar_one_or_none()
        if tag:
            tag.asset_count = (tag.asset_count or 0) + 1
            await self.session.flush()
