"""
YLCraft — 剪映草稿 API

POST   /api/v1/jianying/parse       — 解析剪映草稿
POST   /api/v1/jianying/extract    — 提取草稿素材
POST   /api/v1/jianying/import     — 导入到资产中枢
POST   /api/v1/jianying/export     — 导出为剪映草稿
"""

from __future__ import annotations

import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import tempfile
import shutil

from app.db.database import get_async_session
from app.services.jianying.service import JianYingDraftParser

router = APIRouter()
logger = logging.getLogger("ylcraft.jianying")

# ---------------------------------------------------------------------------
# 依赖注入
# ---------------------------------------------------------------------------

async def get_jianying_service():
    """获取 JianYingDraftParser 实例"""
    async with get_async_session() as session:
        yield JianYingDraftParser(session)

# ---------------------------------------------------------------------------
# Pydantic Schema
# ---------------------------------------------------------------------------

class ParseDraftRequest(BaseModel):
    draft_path: str = Field(..., description="剪映草稿 ZIP 文件路径")

class ImportDraftRequest(BaseModel):
    draft_path: str = Field(..., description="剪映草稿 ZIP 文件路径")
    project_name: str = Field(..., description="项目名称")
    extract_materials: bool = Field(True, description="是否提取并导入素材")

class ExportDraftRequest(BaseModel):
    project_id: str = Field(..., description="资产中枢项目 ID")
    output_path: str = Field(..., description="输出 ZIP 文件路径")

class JianYingResponse(BaseModel):
    success: bool = True
    data: Dict[str, Any]

# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------

@router.post("/jianying/parse", response_model=JianYingResponse)
async def parse_jianying_draft(
    request: ParseDraftRequest,
    service: JianYingDraftParser = Depends(get_jianying_service),
):
    """
    解析剪映草稿 ZIP 包

    返回草稿信息、视频片段、音频片段、字幕、贴纸等。
    """
    result = await service.parse_draft(request.draft_path)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return {
        "success": True,
        "data": result,
    }


@router.post("/jianying/parse-upload", response_model=JianYingResponse)
async def parse_jianying_draft_upload(
    file: UploadFile = File(..., description="剪映草稿 ZIP 文件"),
    service: JianYingDraftParser = Depends(get_jianying_service),
):
    """
    上传并解析剪映草稿

    直接上传 ZIP 文件进行解析。
    """
    # 保存上传文件到临时目录
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        result = await service.parse_draft(tmp_path)

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        return {
            "success": True,
            "data": result,
        }
    finally:
        # 清理临时文件
        import os
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@router.post("/jianying/extract", response_model=JianYingResponse)
async def extract_jianying_materials(
    draft_path: str = Query(..., description="剪映草稿 ZIP 文件路径"),
    output_dir: Optional[str] = Query(None, description="输出目录"),
    service: JianYingDraftParser = Depends(get_jianying_service),
):
    """
    提取剪映草稿中的素材文件

    解压 ZIP 包，将视频、音频、图片分别保存到对应目录。
    """
    result = await service.extract_materials(draft_path, output_dir)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return {
        "success": True,
        "data": result,
    }


@router.post("/jianying/import", response_model=JianYingResponse)
async def import_jianying_draft(
    request: ImportDraftRequest,
    service: JianYingDraftParser = Depends(get_jianying_service),
):
    """
    将剪映草稿导入到资产中枢

    创建项目资产节点，并可选地提取导入所有素材。
    """
    result = await service.import_to_asset_hub(
        draft_zip_path=request.draft_path,
        project_name=request.project_name,
        extract_materials=request.extract_materials,
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return {
        "success": True,
        "data": result,
    }


@router.post("/jianying/import-upload", response_model=JianYingResponse)
async def import_jianying_draft_upload(
    file: UploadFile = File(..., description="剪映草稿 ZIP 文件"),
    project_name: str = Query(..., description="项目名称"),
    extract_materials: bool = Query(True, description="是否提取并导入素材"),
    service: JianYingDraftParser = Depends(get_jianying_service),
):
    """
    上传并导入剪映草稿到资产中枢
    """
    # 保存上传文件
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        result = await service.import_to_asset_hub(
            draft_zip_path=tmp_path,
            project_name=project_name,
            extract_materials=extract_materials,
        )

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        return {
            "success": True,
            "data": result,
        }
    finally:
        import os
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@router.post("/jianying/export", response_model=JianYingResponse)
async def export_jianying_draft(
    request: ExportDraftRequest,
    service: JianYingDraftParser = Depends(get_jianying_service),
):
    """
    将资产中枢项目导出为剪映草稿

    预留接口，尚未实现。
    """
    result = await service.export_draft(
        project_id=request.project_id,
        output_path=request.output_path,
    )

    if "error" in result:
        return {
            "success": True,
            "data": result,
        }

    return {
        "success": True,
        "data": result,
    }


@router.get("/jianying/supported-formats")
async def get_supported_draft_formats():
    """获取支持的剪映草稿格式"""
    return {
        "success": True,
        "data": {
            "formats": [".zip"],
            "note": "Only ZIP format exported by JianYing is supported",
        },
    }
