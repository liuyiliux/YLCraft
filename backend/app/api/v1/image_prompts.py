"""Image prompt reference library API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db.database import SessionLocal
from app.services.image_prompt_reference import ImagePromptReferenceService

router = APIRouter()


class RefreshImagePromptSourcesRequest(BaseModel):
    source_id: str | None = None


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
        result = service.refresh_sources(source_id=req.source_id)
        return result


@router.get("/references", summary="Search image prompt references")
def search_image_prompt_references(
    keyword: Annotated[str, Query(description="Search title, prompt or category")] = "",
    tag: Annotated[str, Query(description="Filter by one tag")] = "",
    category: Annotated[str, Query(description="Filter by category")] = "",
    source_id: Annotated[str, Query(description="Filter by source id")] = "",
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


@router.post("/references/{reference_id}/save-as-asset", summary="Save image prompt reference as Asset Hub text asset")
def save_image_prompt_reference_as_asset(reference_id: str):
    with SessionLocal() as session:
        service = ImagePromptReferenceService(session)
        try:
            return service.save_reference_as_asset(reference_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
