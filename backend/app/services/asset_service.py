"""
YLCraft — 资产服务

提供资产入库、查询、更新等核心操作。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from app.db.database import get_session
from app.db.models.asset import Asset, AssetType, AssetStatus

logger = logging.getLogger("ylcraft.asset_service")


class AssetService:
    """资产服务类"""

    @staticmethod
    def create_asset(
        asset_type: AssetType,
        title: str,
        file_path: str,
        source_url: str = "",
        platform: str = "ylcraft",
        author: str = "AI Generated",
        description: str = "",
        file_size: int = 0,
        duration: int = 0,
        width: int = 0,
        height: int = 0,
        mime_type: str = "",
        thumbnail_path: str = "",
        tags: list[str] | None = None,
        metadata: dict | None = None,
        session: Session | None = None,
    ) -> Asset:
        """
        创建新资产记录。

        Args:
            asset_type: 资产类型（IMAGE/VIDEO/AUDIO/DOCUMENT）
            title: 资产标题
            file_path: 本地文件路径
            source_url: 来源 URL
            platform: 来源平台
            author: 作者
            description: 描述
            file_size: 文件大小（字节）
            duration: 时长（秒）
            width: 宽度
            height: 高度
            mime_type: MIME 类型
            thumbnail_path: 缩略图路径
            tags: 标签列表
            metadata: 元数据字典
            session: 数据库会话（可选）

        Returns:
            Asset: 创建的资产对象
        """
        if session is None:
            session = next(get_session())

        asset = Asset(
            asset_type=asset_type,
            title=title or f"{asset_type.value}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            description=description,
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            duration=duration,
            width=width,
            height=height,
            source_url=source_url,
            platform=platform,
            author=author,
            thumbnail_path=thumbnail_path,
            status=AssetStatus.READY,
            tags=json.dumps(tags or [], ensure_ascii=False),
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
            downloaded_at=datetime.now(),
        )

        session.add(asset)
        session.commit()
        session.refresh(asset)

        logger.info(f"Created asset: {asset.id} ({asset_type.value}) - {title}")
        return asset

    @staticmethod
    def create_from_image_generation(
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
        session: Session | None = None,
    ) -> Asset:
        """
        从图像生成结果创建资产。

        Args:
            image_path: 图片本地路径
            prompt: 生成提示词
            provider: 生成提供商
            model: 生成模型
            seed: 随机种子
            url: 远程 URL（可选）
            negative_prompt: 反向提示词
            size: 图片尺寸（如 "1024x1024"）
            steps: 采样步数
            cfg_scale: CFG 引导系数
            sampler: 采样器名称
            lora: LoRA 模型
            controlnet: ControlNet 模型
            source_image: 图生图源图片路径
            reference_images: 参考图片路径列表
            session: 数据库会话

        Returns:
            Asset: 创建的资产对象
        """
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

        return AssetService.create_asset(
            asset_type=AssetType.IMAGE,
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
            thumbnail_path=str(path),  # 图片本身就是缩略图
            tags=gen_tags,
            metadata=metadata,
            session=session,
        )

    @staticmethod
    def create_from_video_generation(
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
        session: Session | None = None,
    ) -> Asset:
        """
        从视频生成结果创建资产。

        Args:
            video_path: 视频本地路径
            prompt: 生成提示词
            provider: 生成提供商
            model: 生成模型
            duration: 视频时长（秒）
            seed: 随机种子
            url: 远程 URL（可选）
            negative_prompt: 反向提示词
            resolution: 分辨率
            aspect_ratio: 画幅比例
            generate_audio: 是否生成音频
            start_image: 图生视频首帧图片路径
            reference_images: 参考图片路径列表
            session: 数据库会话

        Returns:
            Asset: 创建的资产对象
        """
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

        return AssetService.create_asset(
            asset_type=AssetType.VIDEO,
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
            tags=gen_tags,
            metadata=metadata,
            session=session,
        )

    @staticmethod
    def get_asset(asset_id: str, session: Session | None = None) -> Optional[Asset]:
        """获取资产详情"""
        if session is None:
            session = next(get_session())
        return session.get(Asset, asset_id)

    @staticmethod
    def list_assets(
        asset_type: Optional[AssetType] = None,
        platform: Optional[str] = None,
        status: Optional[AssetStatus] = None,
        search: str = "",
        tags: list[str] | None = None,
        page: int = 1,
        page_size: int = 20,
        session: Session | None = None,
    ) -> tuple[list[Asset], int]:
        """
        查询资产列表。

        Returns:
            tuple[list[Asset], int]: (资产列表, 总数)
        """
        if session is None:
            session = next(get_session())

        query = select(Asset)

        if asset_type:
            query = query.where(Asset.asset_type == asset_type)
        if platform:
            query = query.where(Asset.platform == platform)
        if status:
            query = query.where(Asset.status == status)
        if search:
            query = query.where(Asset.title.contains(search))

        # 暂时忽略标签过滤（需要 JSON 查询）

        # 统计总数
        count_query = query
        total = len(session.exec(count_query).all())

        # 分页
        query = query.order_by(Asset.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        assets = session.exec(query).all()
        return list(assets), total
