"""Image prompt reference library API."""

from __future__ import annotations

import mimetypes
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.db.database import SessionLocal
from app.services.image_prompt_reference import ImagePromptReferenceService, image_prompt_media_root

router = APIRouter()


class RefreshImagePromptSourcesRequest(BaseModel):
    source_id: str | None = None
    force_remote: bool = False


class CreateUserImagePromptReferenceRequest(BaseModel):
    prompt: str
    title: str = ""
    negative_prompt: str = ""
    provider: str = ""
    model: str = ""
    asset_id: str = ""
    generation_mode: str = "text_to_image"
    size: str = ""
    seed: int | None = None
    tags: list[str] = []


@router.get("/sources", summary="List image prompt reference sources")
def list_image_prompt_sources(include_disabled: bool = False):
    with SessionLocal() as session:
        service = ImagePromptReferenceService(session)
        sources = service.list_sources(include_disabled=include_disabled)
        return {
            "success": True,
            "data": [service.source_to_dict(source) for source in sources],
            "total": len(sources),
        }


@router.post("/sources/refresh", summary="Refresh image prompt reference sources")
def refresh_image_prompt_sources(req: RefreshImagePromptSourcesRequest):
    with SessionLocal() as session:
        service = ImagePromptReferenceService(session)
        result = service.refresh_sources(source_id=req.source_id, force_remote=req.force_remote)
        return result


@router.get("/media/{source_id}/{item_id}/{filename}", summary="Read cached image prompt reference media")
def read_image_prompt_reference_media(source_id: str, item_id: str, filename: str):
    root = image_prompt_media_root().resolve()
    candidate = (root / source_id / item_id / filename).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="media path is outside prompt cache") from exc
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="cached prompt media not found")
    media_type = mimetypes.guess_type(str(candidate))[0] or "application/octet-stream"
    return FileResponse(path=str(candidate), media_type=media_type)


@router.get("/references", summary="Search image prompt references")
def search_image_prompt_references(
    keyword: Annotated[str, Query(description="Search title, prompt or category")] = "",
    tag: Annotated[str, Query(description="Filter by one tag")] = "",
    category: Annotated[str, Query(description="Filter by category")] = "",
    source_id: Annotated[str, Query(description="Filter by source id")] = "",
    model_group: Annotated[str, Query(description="Filter by normalized model group: ChatGPT, NanoBanana2, NanoBananaPro")] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    with SessionLocal() as session:
        service = ImagePromptReferenceService(session)
        return service.search_references(
            keyword=keyword,
            tag=tag,
            category=category,
            source_id=source_id,
            model_group=model_group,
            page=page,
            page_size=page_size,
        )


@router.get("/references/{reference_id}", summary="Get image prompt reference detail")
def get_image_prompt_reference(reference_id: str):
    with SessionLocal() as session:
        service = ImagePromptReferenceService(session)
        reference = service.get_reference(reference_id)
        if not reference:
            raise HTTPException(status_code=404, detail="image prompt reference not found")
        return {"success": True, "data": service.reference_to_dict(reference)}


@router.post("/references", summary="Save a generated image prompt into the user prompt library")
def create_user_image_prompt_reference(req: CreateUserImagePromptReferenceRequest):
    with SessionLocal() as session:
        service = ImagePromptReferenceService(session)
        try:
            reference, created, sample_added = service.create_user_reference(**req.model_dump())
            return {"success": True, "created": created, "sample_added": sample_added, "data": service.reference_to_dict(reference)}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/references/{reference_id}/save-as-asset", summary="Save cached prompt reference image into Asset Hub")
def save_image_prompt_reference_as_asset(reference_id: str):
    with SessionLocal() as session:
        service = ImagePromptReferenceService(session)
        try:
            return service.save_reference_as_asset(reference_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
