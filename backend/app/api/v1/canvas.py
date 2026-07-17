"""Free-form creative canvas API."""

from __future__ import annotations

from datetime import datetime
import base64
import binascii
from pathlib import Path
from typing import Annotated, Any, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from app.db.database import SessionLocal
from app.db.models.canvas import CanvasDocument as CanvasDocumentModel
from app.db.models.asset_hub import (
    AssetNode,
    AssetRepresentation,
    AssetRelation,
    AssetType,
    AssetVersion,
    RelationType,
)

router = APIRouter()


class CanvasDocumentRequest(BaseModel):
    document: dict[str, Any] = Field(default_factory=dict)


class CanvasImageAssetSaveRequest(BaseModel):
    """Explicitly persist a browser-produced canvas image into Asset Hub."""

    image_data_url: str = Field(..., min_length=32, description="Processed image data URL")
    title: str = Field(default="Canvas processed image", max_length=120)
    canvas_document_id: str = Field(default="", max_length=128)
    canvas_node_id: str = Field(default="", max_length=128)
    source_node_id: str = Field(default="", max_length=128)
    source_asset_id: str = Field(default="", max_length=128)
    operation: str = Field(default="", max_length=64)
    width: int | None = Field(default=None, ge=1, le=16384)
    height: int | None = Field(default=None, ge=1, le=16384)
    format: str = Field(default="png", max_length=12)
    parameters: dict[str, Any] = Field(default_factory=dict)


_CANVAS_IMAGE_MIME_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}
_MAX_CANVAS_IMAGE_BYTES = 40 * 1024 * 1024


def _decode_canvas_image_data_url(value: str) -> tuple[str, str, bytes]:
    header, separator, encoded = str(value or "").partition(",")
    if not separator or not header.startswith("data:") or ";base64" not in header:
        raise HTTPException(status_code=422, detail="image_data_url must be a base64 image data URL")
    mime_type = header[5:].split(";", 1)[0].strip().lower()
    extension = _CANVAS_IMAGE_MIME_TYPES.get(mime_type)
    if not extension:
        raise HTTPException(status_code=422, detail="Only PNG, JPEG, and WebP canvas image outputs can be saved")
    try:
        binary = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(status_code=422, detail="image_data_url contains invalid base64 data") from None
    if not binary:
        raise HTTPException(status_code=422, detail="image_data_url cannot be empty")
    if len(binary) > _MAX_CANVAS_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Canvas image is too large to save")
    return mime_type, extension, binary


def _canvas_image_storage_root() -> Path:
    root = Path(__file__).resolve().parents[2] / "storage" / "canvas" / "processed_images"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _persist_canvas_image_asset(req: CanvasImageAssetSaveRequest) -> dict[str, Any]:
    mime_type, extension, binary = _decode_canvas_image_data_url(req.image_data_url)
    stored_path = _canvas_image_storage_root() / f"{uuid4()}.{extension}"
    stored_path.write_bytes(binary)

    try:
        with SessionLocal() as session:
            asset_node = AssetNode(
                id=str(uuid4()),
                name=(req.title or "Canvas processed image")[:120],
                asset_type=AssetType.IMAGE,
                thumbnail_url=str(stored_path),
                metadata_json={
                    "source": "canvas_image_transform",
                    "canvas_document_id": req.canvas_document_id,
                    "canvas_node_id": req.canvas_node_id,
                    "source_node_id": req.source_node_id,
                    "source_asset_id": req.source_asset_id,
                    "operation": req.operation,
                    "parameters": req.parameters,
                },
                tags_json=["canvas", "processed-image", *( [req.operation] if req.operation else [] )],
            )
            session.add(asset_node)
            session.flush()
            asset_version = AssetVersion(
                id=str(uuid4()),
                asset_node_id=str(asset_node.id),
                version_number=1,
                params_json={
                    "operation": req.operation,
                    "format": req.format,
                    "width": req.width,
                    "height": req.height,
                    **req.parameters,
                },
                lineage_json={
                    "source": "canvas_image_transform",
                    "canvas_document_id": req.canvas_document_id,
                    "canvas_node_id": req.canvas_node_id,
                    "source_node_id": req.source_node_id,
                    "source_asset_id": req.source_asset_id,
                },
            )
            session.add(asset_version)
            session.flush()
            representation = AssetRepresentation(
                id=str(uuid4()),
                asset_version_id=str(asset_version.id),
                file_path=str(stored_path),
                mime_type=mime_type,
                file_size=len(binary),
                width=req.width,
                height=req.height,
                format=extension,
                extra_json={
                    "source": "canvas_image_transform",
                    "canvas_document_id": req.canvas_document_id,
                    "canvas_node_id": req.canvas_node_id,
                    "operation": req.operation,
                },
            )
            session.add(representation)
            relation_created = False
            if req.source_asset_id and session.get(AssetNode, req.source_asset_id):
                session.add(AssetRelation(
                    id=str(uuid4()),
                    source_id=req.source_asset_id,
                    target_id=str(asset_node.id),
                    relation_type=RelationType.DERIVED_FROM,
                    context_json={
                        "source": "canvas_image_transform",
                        "canvas_document_id": req.canvas_document_id,
                        "canvas_node_id": req.canvas_node_id,
                        "source_node_id": req.source_node_id,
                        "operation": req.operation,
                    },
                ))
                relation_created = True
            session.commit()
            return {
                "success": True,
                "data": {
                    "asset_id": str(asset_node.id),
                    "asset_version_id": str(asset_version.id),
                    "representation_id": str(representation.id),
                    "file_path": str(stored_path),
                    "asset_url": f"/api/v1/assets/{asset_node.id}/download",
                    "relation_created": relation_created,
                },
            }
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise


def _utc_now() -> datetime:
    return datetime.utcnow()


def _doc_id(value: Any = None) -> str:
    raw = str(value or "").strip()
    return raw or str(uuid4())


def _project_id_from_document(document: dict[str, Any]) -> str | None:
    value = document.get("projectId") or document.get("project_id")
    text = str(value or "").strip()
    return text or None


def _normalize_connections(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    required_fields = ("id", "fromNodeId", "toNodeId", "fromPortId", "toPortId")
    for index, raw_connection in enumerate(value):
        if not isinstance(raw_connection, dict):
            raise HTTPException(status_code=422, detail=f"connections[{index}] must be an object")
        connection = dict(raw_connection)
        missing = [field for field in required_fields if not str(connection.get(field) or "").strip()]
        if missing:
            raise HTTPException(
                status_code=422,
                detail=f"connections[{index}] requires runtime ports and ids: {', '.join(missing)}",
            )
        normalized.append(connection)
    return normalized

def _normalize_document(document: dict[str, Any], *, document_id: str | None = None) -> dict[str, Any]:
    now = _utc_now().isoformat()
    doc = dict(document or {})
    doc["id"] = _doc_id(document_id or doc.get("id"))
    doc["title"] = str(doc.get("title") or "Creative canvas")
    doc["description"] = str(doc.get("description") or "")
    doc["viewport"] = doc.get("viewport") if isinstance(doc.get("viewport"), dict) else {"x": 120, "y": 80, "k": 1}
    doc["nodes"] = doc.get("nodes") if isinstance(doc.get("nodes"), list) else []
    doc["connections"] = _normalize_connections(doc.get("connections"))
    doc["createdAt"] = str(doc.get("createdAt") or doc.get("created_at") or now)
    doc["updatedAt"] = now
    project_id = _project_id_from_document(doc)
    if project_id:
        doc["projectId"] = project_id
    else:
        doc.pop("projectId", None)
    doc.pop("project_id", None)
    return doc


def _row_to_document(row: CanvasDocumentModel) -> dict[str, Any]:
    document = dict(row.document_json or {})
    document["id"] = str(row.id)
    document["title"] = row.title
    document["description"] = row.description or document.get("description") or ""
    if row.project_id:
        document["projectId"] = str(row.project_id)
    document["createdAt"] = document.get("createdAt") or row.created_at.isoformat()
    document["updatedAt"] = row.updated_at.isoformat()
    return document


@router.get("/documents", summary="List canvas documents")
def list_canvas_documents(
    project_id: Annotated[Optional[str], Query(description="Filter by project ID")] = None,
):
    with SessionLocal() as session:
        query = select(CanvasDocumentModel).order_by(CanvasDocumentModel.updated_at.desc())
        if project_id:
            query = query.where(CanvasDocumentModel.project_id == project_id)
        rows = session.exec(query).all()
        return {
            "success": True,
            "data": [_row_to_document(row) for row in rows],
            "total": len(rows),
        }


@router.post("/documents", summary="Create canvas document")
def create_canvas_document(req: CanvasDocumentRequest):
    document = _normalize_document(req.document)
    project_id = _project_id_from_document(document)
    now = _utc_now()
    row = CanvasDocumentModel(
        id=document["id"],
        title=document["title"],
        description=document.get("description") or "",
        project_id=project_id,
        document_json=document,
        created_at=now,
        updated_at=now,
    )
    with SessionLocal() as session:
        existing = session.get(CanvasDocumentModel, row.id)
        if existing:
            raise HTTPException(status_code=409, detail="Canvas document already exists")
        session.add(row)
        session.commit()
        session.refresh(row)
        return {"success": True, "data": _row_to_document(row)}


@router.get("/documents/{document_id}", summary="Get canvas document")
def get_canvas_document(document_id: str):
    with SessionLocal() as session:
        row = session.get(CanvasDocumentModel, document_id)
        if not row:
            raise HTTPException(status_code=404, detail="Canvas document not found")
        return {"success": True, "data": _row_to_document(row)}


@router.put("/documents/{document_id}", summary="Save canvas document")
def save_canvas_document(document_id: str, req: CanvasDocumentRequest):
    """Last-write-wins save for overlapping debounced canvas autosaves."""
    document = _normalize_document(req.document, document_id=document_id)
    project_id = _project_id_from_document(document)
    now = _utc_now()
    values = {
        "title": document["title"],
        "description": document.get("description") or "",
        "project_id": project_id,
        "document_json": document,
        "updated_at": now,
    }
    with SessionLocal() as session:
        try:
            updated = session.exec(
                update(CanvasDocumentModel)
                .where(CanvasDocumentModel.id == document_id)
                .values(**values)
            ).rowcount
            if not updated:
                session.add(CanvasDocumentModel(
                    id=document_id,
                    created_at=now,
                    **values,
                ))
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            raise HTTPException(status_code=503, detail="Canvas document sync failed; local draft is preserved") from exc

        row = session.get(CanvasDocumentModel, document_id)
        if not row:
            raise HTTPException(status_code=500, detail="Canvas document save did not persist")
        return {"success": True, "data": _row_to_document(row)}
@router.delete("/documents/{document_id}", summary="Delete canvas document")
def delete_canvas_document(document_id: str):
    with SessionLocal() as session:
        row = session.get(CanvasDocumentModel, document_id)
        if not row:
            raise HTTPException(status_code=404, detail="Canvas document not found")
        session.delete(row)
        session.commit()
        return {"success": True, "deleted_id": document_id}

@router.post("/assets/image", summary="Save processed canvas image to Asset Hub")
def save_canvas_image_asset(req: CanvasImageAssetSaveRequest):
    """Store an explicit canvas image result and its transform provenance in Asset Hub."""
    return _persist_canvas_image_asset(req)
