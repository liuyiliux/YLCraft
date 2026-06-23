"""Shared local document reader API."""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services.reader import DocumentReaderService, ReaderError

router = APIRouter()


class ReaderChapter(BaseModel):
    id: str
    title: str
    content: str
    content_type: str = "html"
    order: int = 0


class ReaderFileResponse(BaseModel):
    success: bool
    title: str
    root_path: str = ""
    file_path: str
    file_name: str
    format: str
    file_size: int
    modified_at: float
    chapters: list[ReaderChapter]


class ReaderBatchRequest(BaseModel):
    file_paths: list[str]
    title: str = ""
    root_path: str = ""


class ReaderDeleteRequest(BaseModel):
    path: str
    root_path: str = ""
    recursive: bool = False


class ReaderDeleteResponse(BaseModel):
    success: bool
    path: str
    relative_path: str
    parent_relative_path: str
    is_dir: bool
    deleted_files: int = 0
    deleted_dirs: int = 0
    freed_size: int = 0
    message: str


class ReaderBrowseItem(BaseModel):
    name: str
    path: str
    relative_path: str
    is_dir: bool
    readable: bool
    format: str
    file_size: int = 0
    modified_at: float = 0


class ReaderBrowseResponse(BaseModel):
    success: bool
    root_path: str
    current_path: str
    current_relative_path: str = ""
    parent_relative_path: str = ""
    items: list[ReaderBrowseItem]
    supported_formats: list[str]


@router.get("/browse", response_model=ReaderBrowseResponse, summary="浏览下载目录中的可阅读文件")
async def browse_local_documents(
    directory: str = Query("", description="下载目录内的相对或绝对目录路径"),
    root_path: str = Query("", description="浏览根目录，默认使用设置中的下载路径"),
):
    service = DocumentReaderService(root=await _reader_root(root_path))
    try:
        return service.browse(directory)
    except ReaderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/file", response_model=ReaderFileResponse, summary="读取本地下载文档用于预览")
async def read_local_document(
    file_path: str = Query(..., description="下载目录内的本地文件路径"),
    root_path: str = Query("", description="读取根目录，默认使用设置中的下载路径"),
):
    service = DocumentReaderService(root=await _reader_root(root_path))
    try:
        return service.read(file_path)
    except ReaderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/files", response_model=ReaderFileResponse, summary="读取多个本地下载文档用于合集预览")
async def read_local_documents(req: ReaderBatchRequest):
    service = DocumentReaderService(root=await _reader_root(req.root_path))
    try:
        return service.read_many(req.file_paths, title=req.title)
    except ReaderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/delete", response_model=ReaderDeleteResponse, summary="删除下载目录内的本地文档或文件夹")
async def delete_local_document(req: ReaderDeleteRequest):
    service = DocumentReaderService(root=await _reader_root(req.root_path))
    try:
        return service.delete_item(req.path, recursive=req.recursive)
    except ReaderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/asset", summary="读取本地文档图片资源")
async def read_local_document_asset(
    file_path: str = Query(..., description="下载目录内的图片路径"),
    root_path: str = Query("", description="图片资源根目录，默认使用设置中的下载路径"),
):
    service = DocumentReaderService(root=await _reader_root(root_path))
    try:
        path = service.resolve_image_path(file_path)
    except ReaderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return FileResponse(path=path, media_type=media_type)


async def _reader_root(root_path: str = "") -> str | None:
    if root_path:
        return root_path
    try:
        from app.api.v1.settings import get_setting

        configured = await get_setting("video_download_path")
        if configured:
            return configured
    except Exception:
        pass
    return None
