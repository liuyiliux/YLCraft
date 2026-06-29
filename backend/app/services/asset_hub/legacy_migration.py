"""Backfill legacy Asset rows into the Asset Hub three-layer model."""

from __future__ import annotations

import json
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select, text
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.asset import Asset
from app.db.models.asset_hub import AssetNode, AssetType
from app.services.asset_hub.node_service import AssetNodeService
from app.services.asset_hub.representation_service import AssetRepresentationService
from app.services.asset_hub.version_service import AssetVersionService


class LegacyAssetHubMigration:
    """Idempotently migrate rows from the old assets table into asset_hub."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.node_service = AssetNodeService(session)
        self.version_service = AssetVersionService(session)
        self.rep_service = AssetRepresentationService(session)

    async def migrate(
        self,
        *,
        limit: Optional[int] = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        query = select(Asset).where(Asset.status != "DELETED").order_by(Asset.created_at.desc())
        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        assets = list(result.scalars().all())

        migrated = 0
        skipped = 0
        failed = 0
        dry_run_count = 0
        errors: list[dict[str, str]] = []

        for asset in assets:
            asset_id = asset.id
            try:
                existing = await self.find_existing_node(asset)
                if existing:
                    if not dry_run:
                        await self.sync_existing(asset, existing)
                        await self.session.commit()
                    skipped += 1
                    continue

                if dry_run:
                    dry_run_count += 1
                    continue

                await self.migrate_one(asset)
                await self.session.commit()
                migrated += 1
            except Exception as exc:
                await self.session.rollback()
                failed += 1
                errors.append({"asset_id": asset_id, "error": str(exc)})

        return {
            "success": failed == 0,
            "dry_run": dry_run,
            "total_scanned": len(assets),
            "would_migrate": dry_run_count,
            "migrated": migrated,
            "skipped": skipped,
            "failed": failed,
            "errors": errors[:20],
        }

    async def migrate_one(self, asset: Asset) -> AssetNode:
        metadata = _json_dict(asset.metadata_json)
        tags = _json_list(asset.tags)
        now = datetime.now().isoformat()
        asset_type = _map_asset_type(asset.type)
        material_path = _primary_material_path(asset)
        mime_type = asset.mime_type or mimetypes.guess_type(material_path)[0] or "application/octet-stream"
        thumbnail_url = asset.cover_url or material_path

        node = await self.node_service.create(
            name=asset.title or Path(material_path).name or asset.id,
            asset_type=asset_type,
            thumbnail_url=thumbnail_url,
            metadata={
                "source": "legacy_assets",
                "legacy_asset_id": asset.id,
                "legacy_type": asset.type,
                "platform": asset.platform,
                "source_type": asset.source_type,
                "source_url": asset.source_url,
                "cover_url": asset.cover_url,
                "author": asset.author,
                "status": asset.status,
                "metadata": metadata,
                "migrated_at": now,
            },
            tags=tags,
        )
        node.created_at = asset.created_at or node.created_at
        node.updated_at = asset.updated_at or node.updated_at
        self.session.add(node)

        version = await self.version_service.create(
            asset_node_id=str(node.id),
            prompt_used=metadata.get("prompt") or asset.title,
            model_used=metadata.get("model") or "",
            params={
                "legacy_asset_id": asset.id,
                "platform": asset.platform,
                "source_type": asset.source_type,
                "source_url": asset.source_url,
                "size": metadata.get("size") or _size_string(asset.width, asset.height),
                "negative_prompt": metadata.get("negative_prompt", ""),
                "metadata": metadata,
            },
            lineage={
                "source": "legacy_assets",
                "legacy_asset_id": asset.id,
            },
        )
        version.created_at = asset.created_at or version.created_at
        self.session.add(version)

        original_file_size = asset.file_size or _safe_file_size(asset.file_path)
        await self.rep_service.create(
            asset_version_id=str(version.id),
            file_path=material_path,
            mime_type=mime_type,
            file_size=_int32_file_size(original_file_size),
            width=asset.width or None,
            height=asset.height or None,
            duration=float(asset.duration or 0),
            format=_format_from_path(material_path, mime_type),
            extra={
                "legacy_asset_id": asset.id,
                "source_url": asset.source_url,
                "cover_url": asset.cover_url,
                "file_path": asset.file_path,
                "original_file_size": original_file_size,
                "file_size_truncated": original_file_size > _MAX_INT32,
            },
        )

        metadata["asset_hub_node_id"] = str(node.id)
        metadata["asset_hub_migrated_at"] = now
        asset.metadata_json = json.dumps(metadata, ensure_ascii=False)
        asset.updated_at = datetime.now()
        self.session.add(asset)
        return node

    async def sync_existing(self, asset: Asset, node: AssetNode) -> None:
        metadata = _json_dict(asset.metadata_json)
        node_meta = _json_dict(node.metadata_json)
        node_meta.setdefault("source", "legacy_assets")
        node_meta.setdefault("legacy_asset_id", asset.id)
        node_meta.setdefault("legacy_type", asset.type)
        node_meta.setdefault("source_url", asset.source_url)
        node_meta.setdefault("cover_url", asset.cover_url)
        node_meta.setdefault("metadata", metadata)
        node.metadata_json = node_meta
        node.created_at = asset.created_at or node.created_at
        node.updated_at = asset.updated_at or node.updated_at
        self.session.add(node)

        version = await self.version_service.get_latest_version(str(node.id))
        if version and asset.created_at:
            version.created_at = asset.created_at
            self.session.add(version)

        metadata["asset_hub_node_id"] = str(node.id)
        metadata.setdefault("asset_hub_migrated_at", datetime.now().isoformat())
        asset.metadata_json = json.dumps(metadata, ensure_ascii=False)
        self.session.add(asset)

    async def find_existing_node(self, asset: Asset) -> Optional[AssetNode]:
        metadata = _json_dict(asset.metadata_json)
        node_id = metadata.get("asset_hub_node_id")
        if node_id:
            node = await self.session.get(AssetNode, node_id)
            if node:
                return node

        # PostgreSQL JSONB fast path. If a non-PG test DB is used, fall back to scanning.
        try:
            result = await self.session.execute(
                text(
                    """
                    SELECT id FROM asset_nodes
                    WHERE metadata_json ->> 'legacy_asset_id' = :legacy_asset_id
                    LIMIT 1
                    """
                ),
                {"legacy_asset_id": asset.id},
            )
            row = result.first()
            if row:
                return await self.session.get(AssetNode, str(row[0]))
        except Exception:
            pass

        for asset_type in AssetType:
            nodes, _ = await self.node_service.list_nodes(asset_type=asset_type, page=1, page_size=1000)
            for node in nodes:
                node_meta = node.metadata_json if isinstance(node.metadata_json, dict) else {}
                if node_meta.get("legacy_asset_id") == asset.id:
                    return node
        return None


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return [str(item) for item in parsed if item] if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _map_asset_type(value: str) -> AssetType:
    normalized = (value or "").lower()
    if normalized == "image":
        return AssetType.IMAGE
    if normalized == "video":
        return AssetType.VIDEO
    if normalized == "audio":
        return AssetType.AUDIO
    if normalized in {"document", "text", "novel", "article"}:
        return AssetType.TEXT
    if normalized in {"3d_model", "model"}:
        return AssetType.THREE_D_MODEL
    return AssetType.TEXT


def _primary_material_path(asset: Asset) -> str:
    return asset.file_path or asset.source_url or asset.cover_url or asset.id


def _safe_file_size(path: str) -> int:
    if not path:
        return 0
    try:
        candidate = Path(path)
        return candidate.stat().st_size if candidate.exists() else 0
    except Exception:
        return 0


_MAX_INT32 = 2_147_483_647


def _int32_file_size(value: int) -> int:
    if value < 0:
        return 0
    return min(value, _MAX_INT32)


def _size_string(width: int, height: int) -> str:
    return f"{width}x{height}" if width and height else ""


def _format_from_path(path: str, mime_type: str) -> str:
    suffix = Path(path).suffix.lstrip(".")
    if suffix:
        return suffix.lower()
    if "/" in mime_type:
        return mime_type.split("/", 1)[1]
    return mime_type or "bin"
