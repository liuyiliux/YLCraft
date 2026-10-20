"""Asset Hub facade for new feature write paths.

This layer is the stable entry point for modules that need to create canonical
Asset Hub records while legacy `/api/v1/assets` compatibility is still present.
"""

from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset_hub import AssetType
from app.services.asset_file_resolver import (
    resolve_asset_file,
    to_asset_download_url,
    to_storage_path,
)
from app.services.asset_hub.node_service import AssetNodeService
from app.services.asset_hub import source_taxonomy
from app.services.asset_hub.representation_service import AssetRepresentationService
from app.services.asset_hub.version_service import AssetVersionService

logger = logging.getLogger("ylcraft.asset_hub")


@dataclass
class AssetHubCreateResult:
    node_id: str
    version_id: str
    representation_id: str
    version_number: int | None = None


class AssetHubFacade:
    """Canonical Asset Hub write adapter used during legacy asset migration."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.node_service = AssetNodeService(session)
        self.version_service = AssetVersionService(session)
        self.rep_service = AssetRepresentationService(session)

    async def create_derived_version(
        self,
        *,
        source_node_id: str,
        file_path: str,
        prompt: str = "",
        provider: str = "",
        model: str = "",
        lineage: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> AssetHubCreateResult:
        """把一张派生图登记成**源资产的新版本**（v2、v3…），而不是另起一个资产。

        为什么需要：`create_generated_image` 每次都先 `node_service.create` 建一个**新节点**、
        再在它上面挂 v1。于是"同一张图的后处理版本"在素材库里表现为一堆互不相干的资产，
        每个都从 v1 开始——版本机制（version_number / parent_version_id / link_versions）
        本身是完整的，但**没有任何一条路会去建 v2**。

        贴字正是这个场景：原图与贴字图是**同一张图的两个版本**，不该拆成两个资产。
        """
        node = await self.node_service.get(source_node_id)
        if node is None:
            raise ValueError("源资产不存在：%s" % source_node_id)

        path = Path(file_path)
        width, height = _image_dimensions(path)
        file_size = path.stat().st_size if path.exists() else 0
        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        params = {
            key: value
            for key, value in {
                "provider": provider,
                "model": model,
                "size": "%dx%d" % (width, height),
            }.items()
            if value
        }
        lineage_data = {"source": "derived_version", **(lineage or {})}
        lineage_data = {key: value for key, value in lineage_data.items() if value not in (None, "")}

        # 接到最新版本后面，形成 v1 → v2 → v3 的链。
        latest = await self.version_service.get_latest_version(source_node_id)
        version = await self.version_service.create(
            asset_node_id=source_node_id,
            prompt_used=prompt,
            model_used=model,
            params=params,
            lineage=lineage_data,
            parent_version_id=str(latest.id) if latest else None,
        )
        rep = await self.rep_service.create(
            asset_version_id=str(version.id),
            file_path=to_storage_path(path),
            mime_type=mime_type,
            file_size=file_size,
            width=width,
            height=height,
            format=path.suffix.lstrip(".").lower() or None,
        )
        # 节点封面指向最新版本。不更新的话素材库列表里仍显示旧图——用户会以为
        # "贴了字却没生效"（封面与版本不一致是最容易被误判成 bug 的一种状态）。
        await self.node_service.update(source_node_id, thumbnail_url=to_asset_download_url(path))
        return AssetHubCreateResult(
            node_id=source_node_id,
            version_id=str(version.id),
            representation_id=str(rep.id),
            version_number=version.version_number,
        )

    async def create_generated_image(
        self,
        *,
        file_path: str,
        prompt: str,
        provider: str,
        model: str,
        source_url: str = "",
        negative_prompt: str = "",
        size: str = "",
        seed: int | None = None,
        generation_params: dict[str, Any] | None = None,
        lineage: dict[str, Any] | None = None,
        legacy_asset_id: str = "",
        tags: list[str] | None = None,
        owner_user_id: str | None = None,
    ) -> AssetHubCreateResult:
        path = Path(file_path)
        width, height = _image_dimensions(path)
        file_size = path.stat().st_size if path.exists() else 0
        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        params = {
            "provider": provider,
            "model": model,
            "negative_prompt": negative_prompt,
            "size": size,
            "seed": seed,
            **(generation_params or {}),
        }
        params = {key: value for key, value in params.items() if value not in (None, "")}
        lineage_data = {
            "source": "image_generation",
            "source_url": source_url,
            "legacy_asset_id": legacy_asset_id,
            **(lineage or {}),
        }
        lineage_data = {key: value for key, value in lineage_data.items() if value not in (None, "")}
        tag_values = ["ai-generated", provider, model, *(tags or [])]
        tag_values = [str(tag) for tag in tag_values if tag]

        node = await self.node_service.create(
            name=(prompt or path.stem or "Generated image")[:120],
            asset_type=AssetType.IMAGE,
            thumbnail_url=to_asset_download_url(path),
            metadata={
                "source": "image_generation",
                "provider": provider,
                "model": model,
                "source_url": source_url,
                "legacy_asset_id": legacy_asset_id,
                "prompt": prompt,
            },
            tags=tag_values,
            owner_user_id=owner_user_id,
        )
        version = await self.version_service.create(
            asset_node_id=str(node.id),
            prompt_used=prompt,
            model_used=model,
            params=params,
            lineage=lineage_data,
        )
        rep = await self.rep_service.create(
            asset_version_id=str(version.id),
            file_path=to_storage_path(path),
            mime_type=mime_type,
            file_size=file_size,
            width=width,
            height=height,
            format=path.suffix.lstrip(".").lower() or None,
            extra={
                "source_url": source_url,
                "legacy_asset_id": legacy_asset_id,
                "original_file_size": file_size,
            },
        )
        return AssetHubCreateResult(
            node_id=str(node.id),
            version_id=str(version.id),
            representation_id=str(rep.id),
            version_number=version.version_number,
        )

    async def create_motion_gif(
        self,
        *,
        name: str,
        primary_file_path: str,
        representations: list[dict[str, Any]],
        prompt: str = "",
        provider: str = "",
        model: str = "",
        slice_config: dict[str, Any] | None = None,
        lineage: dict[str, Any] | None = None,
        source_node_id: str = "",
        tags: list[str] | None = None,
        owner_user_id: str | None = None,
    ) -> AssetHubCreateResult:
        """Create (or append a version to) a motion-GIF asset node.

        **一个动图 = 一个 AssetNode**：列表里只占一行，详情里展开多版本与多格式。

        多格图（frame sheet）作为**同一个版本下的一个 representation**（``format="framesheet"``）
        而不是独立节点 —— 它既是「改切帧重出」的依据，也应能被其它功能按 format 取用
        （用户要的「多方位数据」）。

        ``slice_config`` 存切帧配置（帧顺序、删了哪些格、循环方式、尺寸等）。
        **必须存**：没有它就无法复现「上次那个切法」，「改切帧出新版本」也就无从谈起。

        Args:
            name: 资产名（列表显示）。
            primary_file_path: 主表示（成品 GIF）的本地路径。
            representations: 全部表示，含 ``{format, mime_type, file_path, file_size}``。
            source_node_id: 已存在的节点 id —— 传了就追加新版本，不建新节点。

        Returns:
            AssetHubCreateResult（含 version_number，前端可显示"v1/v2"）。
        """
        primary = Path(primary_file_path)
        if not primary.exists():
            # 主表示不存在就没有可入库的东西——直接报错，别建出一个空节点。
            # 调用方传的多半是相对项目根的路径，先经解析器还原再判存在性。
            resolved = resolve_asset_file(primary_file_path)
            if resolved is None or not resolved.exists():
                raise FileNotFoundError(f"动图主表示文件不存在：{primary_file_path}")
            primary = resolved
        width, height = _image_dimensions(primary)
        file_size = primary.stat().st_size
        mime_type = mimetypes.guess_type(primary.name)[0] or "image/gif"
        config = {k: v for k, v in (slice_config or {}).items() if v is not None}

        node_id = str(source_node_id or "")
        if not node_id:
            # ⚠️ 入库前自检：值必须在 `source_taxonomy` 里登记过。
            # 这不是形式主义 —— 一个未登记的 source 不会报任何错，只会让资产
            # **从素材库筛选里消失**（显示"未知"、被「AI生成」排除）。
            # 动图就是这么踩的："存入素材库显示成功，再查素材库怎么看不到"。
            source_taxonomy.assert_known_source("image_generation", where="create_motion_gif")
            # 过滤空串：provider/model 可能为空，写进标签表会产生一个**无名标签**，
            # 在素材库筛选里既没意义又占位。
            node_tags = [
                str(t) for t in ("ai-generated", "motion-gif", provider, model, *(tags or [])) if t
            ]
            node = await self.node_service.create(
                name=(name or primary.stem or "动图")[:120],
                asset_type=AssetType.IMAGE,
                thumbnail_url=to_asset_download_url(primary),
                metadata={
                    # ⚠️ **必须是 `image_generation`，不能自创 `motion_gif`**。
                    # 素材库的「来源」筛选按这个值分组（前端 SOURCE_TYPE_OPTIONS），
                    # 自创的值不在选项里 —— 卡片会显示成"未知来源"，
                    # 而且一点「AI生成」筛选就被排除掉。
                    # 用户实测："点存入素材库显示成功，再查素材库怎么看不到" ——
                    # 资产**确实存进去了**，只是在正常筛选下看不见。
                    # 区分"这是动图"交给 tags（已有 `motion-gif`）和
                    # `slice_config`，不该另立一个 source 值。
                    "source": "image_generation",
                    # 卡片缩略图/预览靠它解析（其它 AI 图片也有这个字段）
                    "source_url": to_asset_download_url(primary),
                    "provider": provider,
                    "model": model,
                    "prompt": prompt,
                    "slice_config": config,
                },
                tags=node_tags,
                owner_user_id=owner_user_id,
            )
            node_id = str(node.id)

        version = await self.version_service.create(
            asset_node_id=node_id,
            prompt_used=prompt,
            model_used=model,
            params={
                "provider": provider,
                "model": model,
                "slice_config": config,
            },
            lineage={
                # lineage 里保留 `motion_gif`：它是**溯源信息**（这条版本是怎么来的），
                # 素材库的"来源"筛选读的是 node metadata 的 `source`（已改为
                # `image_generation`）。两者职责不同，不要一起改。
                "source": "motion_gif",
                "source_version_id": source_node_id,
                **(lineage or {}),
            },
        )

        first_rep = None
        for item in representations:
            # representation 里存的是**相对项目根**的路径（多机共享数据库、文件各自本地），
            # 而本进程 CWD 通常是 backend/。直接 Path(x).exists() 会全部判为不存在，
            # 结果是"合成成功但一个表示都没入库"。必须经解析器还原。
            rep_path = resolve_asset_file(str(item.get("file_path") or ""))
            if rep_path is None or not rep_path.exists():
                # 产物缺失不能静默跳过——列表里少了格式却看不出来，比直接失败更难查
                logger.warning(
                    "[AssetHub] motion gif representation missing on disk: %s (format=%s)",
                    item.get("file_path"),
                    item.get("format"),
                )
                continue
            is_primary = str(item.get("format")) == "gif"
            rep = await self.rep_service.create(
                asset_version_id=str(version.id),
                file_path=to_storage_path(rep_path),
                mime_type=str(item.get("mime_type") or ""),
                file_size=int(item.get("file_size") or rep_path.stat().st_size),
                width=width if is_primary else None,
                height=height if is_primary else None,
                format=str(item.get("format") or ""),
                extra={"role": "primary" if is_primary else "companion"},
            )
            if first_rep is None or is_primary:
                first_rep = rep

        if first_rep is None:
            raise ValueError("动图没有任何可入库的产物表示")

        # 节点封面指向最新版本的主表示，否则列表里显示的还是旧图
        await self.node_service.update(node_id, thumbnail_url=to_asset_download_url(primary))
        return AssetHubCreateResult(
            node_id=node_id,
            version_id=str(version.id),
            representation_id=str(first_rep.id),
            version_number=version.version_number,
        )

    async def create_or_update_character_portrait(
        self,
        *,
        character: Any,
        portrait_url: str,
        local_path: str = "",
        prompt: str = "",
        provider: str = "",
        model: str = "",
        negative_prompt: str = "",
        size: str = "",
        seed: int | None = None,
        generation_params: dict[str, Any] | None = None,
        lineage: dict[str, Any] | None = None,
        legacy_asset_id: str = "",
        source: str = "character_portrait",
        upgraded_from: str = "",
        tags: list[str] | None = None,
    ) -> AssetHubCreateResult:
        """Create a character portrait node or append a new portrait version."""

        file_ref = to_storage_path(local_path) if local_path else _normalize_file_reference(portrait_url)
        mime_type, file_size, width, height, fmt = _image_file_metadata(
            local_path=local_path,
            url=portrait_url,
        )
        character_id = str(getattr(character, "id", "") or "")
        character_name = str(getattr(character, "name", "") or "")
        node_metadata = {
            "source": source,
            "character_id": character_id,
            "character_name": character_name,
            "legacy_asset_id": legacy_asset_id,
            "upgraded_from": upgraded_from,
        }
        node_metadata = {
            key: value for key, value in node_metadata.items() if value not in (None, "")
        }

        portrait_node_id = getattr(character, "portrait_node_id", None)
        node = await self.node_service.get(str(portrait_node_id)) if portrait_node_id else None
        thumbnail_url = (
            _normalize_asset_url(portrait_url)
            if portrait_url
            else (to_asset_download_url(local_path) if local_path else None)
        )

        if node is None:
            node = await self.node_service.create(
                name=f"{character_name or '角色'}-立绘",
                asset_type=AssetType.CHARACTER,
                thumbnail_url=thumbnail_url,
                metadata=node_metadata,
                tags=["character_portrait", *(tags or [])],
            )
        else:
            await self.node_service.update(
                node_id=str(node.id),
                thumbnail_url=thumbnail_url,
                metadata=node_metadata,
            )

        params = {
            "provider": provider,
            "model": model,
            "seed": seed,
            "size": size,
            "negative_prompt": negative_prompt,
            **(generation_params or {}),
        }
        params = {key: value for key, value in params.items() if value not in (None, "")}
        lineage_data = {
            "source": source,
            "character_id": character_id,
            "character_name": character_name,
            "legacy_asset_id": legacy_asset_id,
            **(lineage or {}),
        }
        lineage_data = {
            key: value for key, value in lineage_data.items() if value not in (None, "")
        }

        version = await self.version_service.create(
            asset_node_id=str(node.id),
            prompt_used=prompt,
            model_used=model,
            params=params,
            lineage=lineage_data,
        )
        rep = await self.rep_service.create(
            asset_version_id=str(version.id),
            file_path=file_ref,
            mime_type=mime_type,
            file_size=file_size,
            width=width,
            height=height,
            format=fmt,
            extra={
                "url": _normalize_asset_url(portrait_url),
                "local_path": to_storage_path(local_path) if local_path else "",
                "legacy_asset_id": legacy_asset_id,
                "source": source,
                "upgraded_from": upgraded_from,
                "preset": params.get("preset"),
                "is_main": params.get("set_as_main"),
            },
        )

        return AssetHubCreateResult(
            node_id=str(node.id),
            version_id=str(version.id),
            representation_id=str(rep.id),
            version_number=version.version_number,
        )

    async def create_imported_file(
        self,
        *,
        file_path: str,
        title: str,
        asset_type: AssetType | str,
        source: str,
        source_url: str = "",
        thumbnail_url: str = "",
        metadata: dict[str, Any] | None = None,
        lineage: dict[str, Any] | None = None,
        legacy_asset_id: str = "",
        tags: list[str] | None = None,
        owner_user_id: str | None = None,
    ) -> AssetHubCreateResult:
        """Create Asset Hub records for a downloaded or imported local file."""

        path = Path(file_path)
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        file_size = path.stat().st_size if path.exists() else 0
        node_type = AssetType(asset_type) if isinstance(asset_type, str) else asset_type
        meta = {
            "source": source,
            "source_url": source_url,
            "legacy_asset_id": legacy_asset_id,
            **(metadata or {}),
        }
        meta = {key: value for key, value in meta.items() if value not in (None, "")}
        lineage_data = {
            "source": source,
            "source_url": source_url,
            "legacy_asset_id": legacy_asset_id,
            **(lineage or {}),
        }
        lineage_data = {
            key: value for key, value in lineage_data.items() if value not in (None, "")
        }

        normalized_thumbnail_url = thumbnail_url
        if normalized_thumbnail_url and not normalized_thumbnail_url.startswith(("/api/", "http://", "https://", "data:")):
            normalized_thumbnail_url = to_asset_download_url(normalized_thumbnail_url)

        node = await self.node_service.create(
            name=(title or path.stem or "Imported file")[:120],
            asset_type=node_type,
            thumbnail_url=normalized_thumbnail_url or None,
            metadata=meta,
            tags=[source, *(tags or [])],
            owner_user_id=owner_user_id,
        )
        version = await self.version_service.create(
            asset_node_id=str(node.id),
            prompt_used=str((metadata or {}).get("prompt") or ""),
            model_used=str((metadata or {}).get("model") or ""),
            params=meta,
            lineage=lineage_data,
        )
        rep = await self.rep_service.create(
            asset_version_id=str(version.id),
            file_path=to_storage_path(path),
            mime_type=mime_type,
            file_size=file_size,
            width=_optional_int(meta.get("width")),
            height=_optional_int(meta.get("height")),
            duration=_optional_float(meta.get("duration")),
            format=path.suffix.lstrip(".").lower() or None,
            extra={
                "source": source,
                "source_url": source_url,
                "legacy_asset_id": legacy_asset_id,
                "thumbnail_url": normalized_thumbnail_url or "",
            },
        )

        return AssetHubCreateResult(
            node_id=str(node.id),
            version_id=str(version.id),
            representation_id=str(rep.id),
            version_number=version.version_number,
        )


def _image_dimensions(path: Path) -> tuple[int | None, int | None]:
    if not path.exists():
        return None, None
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size
    except Exception:
        return None, None


def _normalize_file_reference(value: str) -> str:
    if not value or value.startswith(("/api/", "http://", "https://", "data:")):
        return value
    return to_storage_path(value)


def _normalize_asset_url(value: str) -> str:
    if not value or value.startswith(("/api/", "http://", "https://", "data:")):
        return value
    return to_asset_download_url(value)


def _image_file_metadata(
    *,
    local_path: str,
    url: str,
) -> tuple[str, int, int | None, int | None, str | None]:
    path = Path(local_path) if local_path else None
    width, height = _image_dimensions(path) if path else (None, None)
    file_size = path.stat().st_size if path and path.exists() else 0
    fmt = path.suffix.lstrip(".").lower() if path and path.suffix else None

    parsed_url = urlparse(url) if url else None
    if not fmt and parsed_url:
        suffix = Path(parsed_url.path).suffix.lstrip(".").lower()
        fmt = suffix or None
    if not fmt and parsed_url:
        query = parse_qs(parsed_url.query)
        fmt = (query.get("wx_fmt") or query.get("format") or [""])[0].lower() or None

    mime_type = "image/png"
    if fmt:
        mime_type = mimetypes.types_map.get(f".{fmt}", mime_type)
        if fmt in {"jpg", "jpeg"}:
            mime_type = "image/jpeg"
        elif fmt == "webp":
            mime_type = "image/webp"

    return mime_type, file_size, width, height, fmt


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except Exception:
        return None


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except Exception:
        return None
