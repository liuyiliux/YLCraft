"""Asset Hub facade for new feature write paths.

This layer is the stable entry point for modules that need to create canonical
Asset Hub records while legacy `/api/v1/assets` compatibility is still present.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset_hub import AssetType
from app.services.asset_hub.node_service import AssetNodeService
from app.services.asset_hub.representation_service import AssetRepresentationService
from app.services.asset_hub.version_service import AssetVersionService


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
            thumbnail_url=str(path),
            metadata={
                "source": "image_generation",
                "provider": provider,
                "model": model,
                "source_url": source_url,
                "legacy_asset_id": legacy_asset_id,
                "prompt": prompt,
            },
            tags=tag_values,
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
            file_path=str(path),
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

        file_ref = local_path or portrait_url
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
        thumbnail_url = portrait_url or local_path or None

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
                "url": portrait_url,
                "local_path": local_path,
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

        node = await self.node_service.create(
            name=(title or path.stem or "Imported file")[:120],
            asset_type=node_type,
            thumbnail_url=thumbnail_url or None,
            metadata=meta,
            tags=[source, *(tags or [])],
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
            file_path=str(path),
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
                "thumbnail_url": thumbnail_url,
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
