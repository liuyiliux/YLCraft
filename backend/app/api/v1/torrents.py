"""Torrent download API."""

from __future__ import annotations

import json
import importlib.util
import mimetypes
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from app.db.database import get_async_session
from app.db.models.torrent import TorrentDownload
from app.services.torrent.config import get_torrent_config
from app.services.torrent.service import TorrentService

router = APIRouter()


class MagnetRequest(BaseModel):
    magnet: str = Field(..., min_length=12)
    start_paused: bool = True


class SelectFilesRequest(BaseModel):
    file_indexes: list[int]
    start: bool = True


class SuccessResponse(BaseModel):
    success: bool = True
    data: Any


async def get_torrent_service():
    async with get_async_session() as session:
        try:
            service = TorrentService(session)
        except Exception as exc:
            raise _http_error(exc)
        try:
            yield service
        finally:
            await service.close()


def _json_list(value: str) -> list:
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _record_to_dict(record: TorrentDownload) -> dict:
    return {
        "id": record.id,
        "engine": record.engine,
        "torrent_hash": record.torrent_hash,
        "name": record.name,
        "source": record.source,
        "source_uri": record.source_uri,
        "save_path": record.save_path,
        "status": record.status,
        "progress": record.progress,
        "download_speed": record.download_speed,
        "upload_speed": record.upload_speed,
        "downloaded_bytes": record.downloaded_bytes,
        "total_size": record.total_size,
        "selected_files": _json_list(record.selected_files_json),
        "asset_ids": _json_list(record.asset_ids_json),
        "error_message": record.error_message,
        "created_at": record.created_at.strftime("%Y-%m-%d %H:%M:%S") if record.created_at else None,
        "updated_at": record.updated_at.strftime("%Y-%m-%d %H:%M:%S") if record.updated_at else None,
    }


def _file_to_dict(item) -> dict:
    return {
        "index": item.index,
        "name": item.name,
        "size": item.size,
        "progress": item.progress,
        "priority": item.priority,
        "is_video": item.is_video,
    }


def _http_error(exc: Exception) -> HTTPException:
    message = str(exc) or exc.__class__.__name__
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=message)
    lowered = message.lower()
    if "login" in lowered or "connect" in lowered or "requires installing" in lowered:
        return HTTPException(status_code=503, detail=f"Torrent engine unavailable: {message}")
    if "unsupported torrent engine" in lowered:
        return HTTPException(status_code=400, detail=message)
    return HTTPException(status_code=500, detail=message)


@router.get("/engine", response_model=SuccessResponse, summary="Get torrent engine status")
async def get_engine_status():
    config = get_torrent_config()
    libtorrent_available = importlib.util.find_spec("libtorrent") is not None
    return SuccessResponse(data={
        "engine": config.engine,
        "download_dir": str(config.download_dir),
        "metadata_cache_dir": str(config.download_dir / "_metadata_cache"),
        "max_active": config.max_active,
        "listen_interfaces": config.listen_interfaces,
        "metadata_cache_providers": len(config.metadata_cache_urls),
        "requires_external_app": config.engine == "qbittorrent",
        "libtorrent_available": libtorrent_available,
        "hint": (
            "qBittorrent Web UI is required"
            if config.engine == "qbittorrent"
            else (
                "Project embedded libtorrent engine is available"
                if libtorrent_available
                else "libtorrent Python package is required"
            )
        ),
    })


@router.get("", response_model=SuccessResponse, summary="List torrent downloads")
async def list_torrents(service: TorrentService = Depends(get_torrent_service)):
    try:
        records = await service.list_records()
        return SuccessResponse(data=[_record_to_dict(r) for r in records])
    except Exception as exc:
        raise _http_error(exc)


@router.post("/magnet", response_model=SuccessResponse, summary="Add magnet link")
async def add_magnet(req: MagnetRequest, service: TorrentService = Depends(get_torrent_service)):
    try:
        record = await service.add_magnet(req.magnet.strip(), start_paused=req.start_paused)
        return SuccessResponse(data=_record_to_dict(record))
    except Exception as exc:
        raise _http_error(exc)


@router.post("/upload", response_model=SuccessResponse, summary="Upload torrent file")
async def upload_torrent(
    file: UploadFile = File(...),
    start_paused: bool = Query(True),
    service: TorrentService = Depends(get_torrent_service),
):
    config = get_torrent_config()
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".torrent"):
        raise HTTPException(status_code=400, detail="Only .torrent files are supported")

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".torrent") as tmp:
            tmp_path = Path(tmp.name)
            total = 0
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if config.max_upload_bytes and total > config.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="Torrent file is too large")
                tmp.write(chunk)
        record = await service.add_torrent_file(tmp_path, filename, start_paused=start_paused)
        return SuccessResponse(data=_record_to_dict(record))
    except HTTPException:
        raise
    except Exception as exc:
        raise _http_error(exc)
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


@router.get("/{download_id}", response_model=SuccessResponse, summary="Get torrent task")
async def get_torrent(download_id: str, service: TorrentService = Depends(get_torrent_service)):
    record = await service.get_record(download_id)
    if not record:
        raise HTTPException(status_code=404, detail="Torrent task not found")
    return SuccessResponse(data=_record_to_dict(record))


@router.get("/{download_id}/files", response_model=SuccessResponse, summary="List torrent files")
async def list_files(download_id: str, service: TorrentService = Depends(get_torrent_service)):
    record = await service.get_record(download_id)
    if not record:
        raise HTTPException(status_code=404, detail="Torrent task not found")
    try:
        files = await service.list_files(record)
        return SuccessResponse(data=[_file_to_dict(item) for item in files])
    except Exception as exc:
        raise _http_error(exc)


@router.post("/{download_id}/select-files", response_model=SuccessResponse, summary="Select files")
async def select_files(download_id: str, req: SelectFilesRequest, service: TorrentService = Depends(get_torrent_service)):
    record = await service.get_record(download_id)
    if not record:
        raise HTTPException(status_code=404, detail="Torrent task not found")
    try:
        record = await service.select_files(record, req.file_indexes, start=req.start)
        return SuccessResponse(data=_record_to_dict(record))
    except Exception as exc:
        raise _http_error(exc)


@router.post("/{download_id}/pause", response_model=SuccessResponse, summary="Pause torrent task")
async def pause_torrent(download_id: str, service: TorrentService = Depends(get_torrent_service)):
    record = await service.get_record(download_id)
    if not record:
        raise HTTPException(status_code=404, detail="Torrent task not found")
    try:
        return SuccessResponse(data=_record_to_dict(await service.pause(record)))
    except Exception as exc:
        raise _http_error(exc)


@router.post("/{download_id}/resume", response_model=SuccessResponse, summary="Resume torrent task")
async def resume_torrent(download_id: str, service: TorrentService = Depends(get_torrent_service)):
    record = await service.get_record(download_id)
    if not record:
        raise HTTPException(status_code=404, detail="Torrent task not found")
    try:
        return SuccessResponse(data=_record_to_dict(await service.resume(record)))
    except Exception as exc:
        raise _http_error(exc)


@router.post("/{download_id}/refresh-metadata", response_model=SuccessResponse, summary="Retry torrent metadata discovery")
async def refresh_torrent_metadata(download_id: str, service: TorrentService = Depends(get_torrent_service)):
    record = await service.get_record(download_id)
    if not record:
        raise HTTPException(status_code=404, detail="Torrent task not found")
    try:
        return SuccessResponse(data=_record_to_dict(await service.refresh_metadata(record)))
    except Exception as exc:
        raise _http_error(exc)


@router.delete("/{download_id}", response_model=SuccessResponse, summary="Delete torrent task")
async def delete_torrent(
    download_id: str,
    delete_files: bool = Query(False),
    service: TorrentService = Depends(get_torrent_service),
):
    record = await service.get_record(download_id)
    if not record:
        raise HTTPException(status_code=404, detail="Torrent task not found")
    try:
        await service.delete(record, delete_files=delete_files)
        return SuccessResponse(data={"deleted": True})
    except Exception as exc:
        raise _http_error(exc)


@router.post("/{download_id}/import-assets", response_model=SuccessResponse, summary="Import completed files")
async def import_assets(download_id: str, service: TorrentService = Depends(get_torrent_service)):
    record = await service.get_record(download_id)
    if not record:
        raise HTTPException(status_code=404, detail="Torrent task not found")
    try:
        assets = await service.import_assets(record)
        return SuccessResponse(data=[{"id": asset.id, "title": asset.title} for asset in assets])
    except Exception as exc:
        raise _http_error(exc)


@router.get("/{download_id}/files/{file_index}/stream", summary="Stream torrent video file")
async def stream_file(
    download_id: str,
    file_index: int,
    request: Request,
    service: TorrentService = Depends(get_torrent_service),
):
    record = await service.get_record(download_id)
    if not record:
        raise HTTPException(status_code=404, detail="Torrent task not found")
    try:
        item, path = await service.get_file_for_stream(record, file_index)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise _http_error(exc)

    media_type = mimetypes.guess_type(item.name)[0] or "video/mp4"
    return _range_file_response(request, path, media_type)


def _range_file_response(request: Request, file_path: Path, media_type: str) -> Response:
    file_size = file_path.stat().st_size
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(
            path=file_path,
            media_type=media_type,
            headers={"Accept-Ranges": "bytes"},
        )

    try:
        units, value = range_header.split("=", 1)
        if units.strip().lower() != "bytes":
            raise ValueError("unsupported range unit")
        start_s, end_s = value.split("-", 1)
        if start_s:
            start = int(start_s)
            end = int(end_s) if end_s else file_size - 1
        else:
            suffix_length = int(end_s)
            if suffix_length <= 0:
                raise ValueError("invalid suffix range")
            start = max(file_size - suffix_length, 0)
            end = file_size - 1
        end = min(end, file_size - 1)
        if start < 0 or end < start or start >= file_size:
            raise ValueError("invalid range")
    except Exception:
        return Response(
            status_code=416,
            headers={
                "Content-Range": f"bytes */{file_size}",
                "Accept-Ranges": "bytes",
            },
        )

    chunk_size = end - start + 1

    async def iter_file():
        with file_path.open("rb") as f:
            f.seek(start)
            remaining = chunk_size
            while remaining > 0:
                chunk = f.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        iter_file(),
        status_code=206,
        media_type=media_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
        },
    )
