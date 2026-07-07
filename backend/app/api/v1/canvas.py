"""Free-form creative canvas API."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import select

from app.db.database import SessionLocal
from app.db.models.canvas import CanvasDocument as CanvasDocumentModel

router = APIRouter()


class CanvasDocumentRequest(BaseModel):
    document: dict[str, Any] = Field(default_factory=dict)


def _utc_now() -> datetime:
    return datetime.utcnow()


def _doc_id(value: Any = None) -> str:
    raw = str(value or "").strip()
    return raw or str(uuid4())


def _project_id_from_document(document: dict[str, Any]) -> str | None:
    value = document.get("projectId") or document.get("project_id")
    text = str(value or "").strip()
    return text or None


def _normalize_document(document: dict[str, Any], *, document_id: str | None = None) -> dict[str, Any]:
    now = _utc_now().isoformat()
    doc = dict(document or {})
    doc["id"] = _doc_id(document_id or doc.get("id"))
    doc["title"] = str(doc.get("title") or "创作画布")
    doc["description"] = str(doc.get("description") or "")
    doc["viewport"] = doc.get("viewport") if isinstance(doc.get("viewport"), dict) else {"x": 120, "y": 80, "k": 1}
    doc["nodes"] = doc.get("nodes") if isinstance(doc.get("nodes"), list) else []
    doc["connections"] = doc.get("connections") if isinstance(doc.get("connections"), list) else []
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


@router.get("/documents", summary="列出创作画布文档")
def list_canvas_documents(
    project_id: Annotated[Optional[str], Query(description="按项目 ID 过滤")] = None,
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


@router.post("/documents", summary="创建创作画布文档")
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
            raise HTTPException(status_code=409, detail="画布文档已存在")
        session.add(row)
        session.commit()
        session.refresh(row)
        return {"success": True, "data": _row_to_document(row)}


@router.get("/documents/{document_id}", summary="获取创作画布文档")
def get_canvas_document(document_id: str):
    with SessionLocal() as session:
        row = session.get(CanvasDocumentModel, document_id)
        if not row:
            raise HTTPException(status_code=404, detail="画布文档不存在")
        return {"success": True, "data": _row_to_document(row)}


@router.put("/documents/{document_id}", summary="保存创作画布文档")
def save_canvas_document(document_id: str, req: CanvasDocumentRequest):
    document = _normalize_document(req.document, document_id=document_id)
    project_id = _project_id_from_document(document)
    with SessionLocal() as session:
        row = session.get(CanvasDocumentModel, document_id)
        now = _utc_now()
        if not row:
            row = CanvasDocumentModel(
                id=document_id,
                title=document["title"],
                description=document.get("description") or "",
                project_id=project_id,
                document_json=document,
                created_at=now,
                updated_at=now,
            )
        else:
            row.title = document["title"]
            row.description = document.get("description") or ""
            row.project_id = project_id
            row.document_json = document
            row.updated_at = now
        session.add(row)
        session.commit()
        session.refresh(row)
        return {"success": True, "data": _row_to_document(row)}


@router.delete("/documents/{document_id}", summary="删除创作画布文档")
def delete_canvas_document(document_id: str):
    with SessionLocal() as session:
        row = session.get(CanvasDocumentModel, document_id)
        if not row:
            raise HTTPException(status_code=404, detail="画布文档不存在")
        session.delete(row)
        session.commit()
        return {"success": True, "deleted_id": document_id}
