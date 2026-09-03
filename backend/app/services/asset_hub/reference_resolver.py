"""把素材库引用解析为生图可用的本地图片路径。

生图链路（AI 图片、角色立绘、世界地图成图）都遵循同一条规则：
调用方传**素材库 ID**（稳定引用），由这里解析出节点最新版本的图片表示路径；
调用方也可以直接传 URL/base64 兜底，两者按去重顺序合并。

放在 services 层是为了让 api 层与 Agent 工具共用，避免每接入一个生图入口
就复制一遍解析逻辑。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import select

from app.db.models.asset_hub import AssetNode
from app.services.asset_hub.representation_service import AssetRepresentationService
from app.services.asset_hub.version_service import AssetVersionService

logger = logging.getLogger("ylcraft.asset_hub.reference_resolver")

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
DEFAULT_MAX_REFS = 12


def looks_like_image_path(path_value: str) -> bool:
    return Path(path_value or "").suffix.lower() in IMAGE_SUFFIXES


def _is_image_representation(rep: Any) -> bool:
    mime_type = str(getattr(rep, "mime_type", "") or "").lower()
    return mime_type.startswith("image/") or looks_like_image_path(
        getattr(rep, "file_path", "") or ""
    )


async def _primary_image_path_for_asset(session: Any, asset_id: str) -> str | None:
    node = await session.get(AssetNode, asset_id)
    if not node:
        return None
    node_meta = node.metadata_json if isinstance(node.metadata_json, dict) else {}
    if node_meta.get("deleted_at") or str(node_meta.get("status", "")).upper() == "DELETED":
        return None

    version = await AssetVersionService(session).get_latest_version(str(node.id))
    if not version:
        return None

    reps = await AssetRepresentationService(session).list_by_version(str(version.id))
    for rep in reps:
        if _is_image_representation(rep) and rep.file_path:
            return str(rep.file_path)
    return None


def reference_images_from_collection(collection: list[dict] | None) -> list[str]:
    """从参考图卡片集合里取出可用的图片地址（url / data_url / local_path 等）。"""
    refs: list[str] = []
    for item in collection or []:
        if not isinstance(item, dict):
            continue
        value = (
            item.get("url")
            or item.get("image_url")
            or item.get("src")
            or item.get("data_url")
            or item.get("local_path")
            or item.get("path")
        )
        if value:
            refs.append(str(value))
    return refs


async def reference_images_from_asset_ids(
    asset_ids: list[str] | None, *, max_refs: int = DEFAULT_MAX_REFS
) -> list[str]:
    """Resolve Asset Hub IDs into local image paths for image-to-image backends.

    参考卡可能是集合/角色根节点，可用图片挂在子节点上，因此找不到主图时
    会向下取一层子节点的图片。
    """
    ids = [str(item or "").strip() for item in (asset_ids or []) if str(item or "").strip()]
    if not ids:
        return []

    from app.db.database import get_async_session

    refs: list[str] = []
    async with get_async_session() as session:
        for asset_id in ids:
            if len(refs) >= max_refs:
                break

            primary_path = await _primary_image_path_for_asset(session, asset_id)
            if primary_path:
                refs.append(primary_path)
                continue

            try:
                result = await session.execute(
                    select(AssetNode)
                    .where(AssetNode.parent_id == asset_id)
                    .order_by(AssetNode.created_at.asc())
                    .limit(max_refs)
                )
                children = list(result.scalars().all())
            except Exception as exc:
                logger.warning(
                    "[asset_hub] failed to resolve reference asset children for %s: %s",
                    asset_id,
                    exc,
                )
                children = []

            for child in children:
                if len(refs) >= max_refs:
                    break
                child_path = await _primary_image_path_for_asset(session, str(child.id))
                if child_path:
                    refs.append(child_path)
    return refs


async def merge_reference_images(
    *,
    reference_images: Iterable[str] | None = None,
    reference_asset_ids: Iterable[str] | None = None,
    reference_image_collection: list[dict] | None = None,
) -> list[str]:
    """按「显式 URL/base64 → 集合卡片 → 素材库 ID」的顺序合并去重。

    素材库 ID 是稳定引用，解析不到图片时静默跳过（不阻塞生图）。
    """
    asset_refs = await reference_images_from_asset_ids(list(reference_asset_ids or []))
    refs: list[str] = []
    seen: set[str] = set()
    for value in [
        *(reference_images or []),
        *reference_images_from_collection(reference_image_collection),
        *asset_refs,
    ]:
        item = str(value or "").strip()
        if item and item not in seen:
            seen.add(item)
            refs.append(item)
    return refs
