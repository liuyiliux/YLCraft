"""
图片编辑器 API
"""

import io
import logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response

from app.services.image_editor import add_text_watermark, add_image_watermark

logger = logging.getLogger("image_editor_api")
router = APIRouter()

@router.post("/watermark/text")
async def add_text_watermark_api(
    file: UploadFile = File(...),
    text: str = Form(...),
    font_size: int = Form(24),
    color: str = Form("#ffffff"),
    opacity: float = Form(0.5),
    position: str = Form("bottom-right"),
    position_x: int = Form(50),
    position_y: int = Form(50),
):
    """
    添加文字水印
    
    支持 GIF 动画，会保留所有帧
    """
    try:
        # 读取图片数据
        image_data = await file.read()
        logger.info(f"接收到文件: {file.filename}, 大小: {len(image_data)} bytes")
        
        if len(image_data) == 0:
            raise HTTPException(status_code=400, detail="上传的文件为空")
        
        # 检测是否为 GIF
        is_gif = file.filename.lower().endswith('.gif')
        logger.info(f"是否为 GIF: {is_gif}")
        
        # 添加水印
        result = add_text_watermark(
            image_data=image_data,
            text=text,
            font_size=font_size,
            color=color,
            opacity=opacity,
            position=position,
            position_x=position_x,
            position_y=position_y,
            is_gif=is_gif
        )
        
        if not result or len(result) == 0:
            raise HTTPException(status_code=500, detail="水印处理结果为空")
        
        # 确定输出格式
        content_type = "image/gif" if is_gif else "image/png"
        filename = file.filename or "image"
        
        logger.info(f"处理完成, 输出大小: {len(result)} bytes")
        
        return Response(
            content=result,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加文字水印失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"水印处理失败: {str(e)}")

@router.post("/watermark/image")
async def add_image_watermark_api(
    file: UploadFile = File(...),
    watermark: UploadFile = File(...),
    scale: float = Form(15),
    opacity: float = Form(0.5),
    position: str = Form("bottom-right"),
    position_x: int = Form(50),
    position_y: int = Form(50),
):
    """
    添加图片水印
    
    支持 GIF 动画，会保留所有帧
    """
    try:
        # 读取图片数据
        image_data = await file.read()
        watermark_data = await watermark.read()
        
        logger.info(f"接收到文件: {file.filename}, 大小: {len(image_data)} bytes")
        
        if len(image_data) == 0:
            raise HTTPException(status_code=400, detail="上传的文件为空")
        if len(watermark_data) == 0:
            raise HTTPException(status_code=400, detail="上传的水印图片为空")
        
        # 检测是否为 GIF
        is_gif = file.filename.lower().endswith('.gif')
        logger.info(f"是否为 GIF: {is_gif}")
        
        # 添加水印
        result = add_image_watermark(
            image_data=image_data,
            watermark_data=watermark_data,
            scale=scale,
            opacity=opacity,
            position=position,
            position_x=position_x,
            position_y=position_y,
            is_gif=is_gif
        )
        
        if not result or len(result) == 0:
            raise HTTPException(status_code=500, detail="水印处理结果为空")
        
        # 确定输出格式
        content_type = "image/gif" if is_gif else "image/png"
        filename = file.filename or "image"
        
        logger.info(f"处理完成, 输出大小: {len(result)} bytes")
        
        return Response(
            content=result,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加图片水印失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"水印处理失败: {str(e)}")
