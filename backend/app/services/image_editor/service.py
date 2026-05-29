"""
图片处理服务 - 支持 GIF 动画
"""

import io
import logging
import os
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont
import re

logger = logging.getLogger("image_editor")

def get_font(size: int) -> ImageFont.FreeTypeFont:
    """获取字体，优先使用系统字体"""
    font_paths = [
        # Windows
        "msyh.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        # Linux
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        # macOS
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial.ttf",
        # Docker/Linux 容器常见路径
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
    ]
    
    # 扫描系统字体目录
    font_dirs = [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        "/System/Library/Fonts",
        "/Library/Fonts",
    ]
    for font_dir in font_dirs:
        if os.path.exists(font_dir):
            for root, dirs, files in os.walk(font_dir):
                for f in files:
                    if f.endswith(('.ttf', '.ttc', '.otf')):
                        font_paths.append(os.path.join(root, f))
    
    for font_path in font_paths:
        try:
            font = ImageFont.truetype(font_path, size)
            logger.info(f"成功加载字体: {font_path}")
            return font
        except Exception as e:
            continue
    
    logger.warning(f"未找到任何字体，使用默认字体")
    return ImageFont.load_default()

def parse_rgba_color(color: str, opacity: float = 1.0) -> Tuple[int, int, int, int]:
    """解析颜色字符串，返回 RGBA 元组"""
    # 处理 rgba(r, g, b, a) 格式
    rgba_match = re.match(r'rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)', color)
    if rgba_match:
        r, g, b = int(rgba_match.group(1)), int(rgba_match.group(2)), int(rgba_match.group(3))
        a = float(rgba_match.group(4)) * 255 if rgba_match.group(4) else 255
        return (r, g, b, int(a * opacity))
    
    # 处理十六进制格式
    if color.startswith('#'):
        hex_color = color[1:]
        if len(hex_color) == 6:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            return (r, g, b, int(255 * opacity))
        elif len(hex_color) == 8:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            a = int(hex_color[6:8], 16)
            return (r, g, b, int(a * opacity))
    
    return (255, 255, 255, int(255 * opacity))

def add_text_watermark(
    image_data: bytes,
    text: str,
    font_size: int = 24,
    color: str = "#ffffff",
    opacity: float = 0.5,
    position: str = "bottom-right",
    position_x: int = 50,
    position_y: int = 50,
    is_gif: bool = False
) -> bytes:
    """
    添加文字水印
    
    Args:
        image_data: 图片二进制数据
        text: 水印文字
        font_size: 字体大小
        color: 颜色（支持 rgba, hex）
        opacity: 透明度 0-1
        position: 位置 (center, bottom-right, tile, custom)
        position_x: 自定义位置 X (百分比)
        position_y: 自定义位置 Y (百分比)
        is_gif: 是否为 GIF
    
    Returns:
        处理后的图片二进制数据
    """
    try:
        if is_gif:
            return _add_text_watermark_gif(image_data, text, font_size, color, opacity, position, position_x, position_y)
        else:
            return _add_text_watermark_static(image_data, text, font_size, color, opacity, position, position_x, position_y)
    except Exception as e:
        logger.error(f"添加文字水印失败: {e}")
        raise

def _add_text_watermark_static(
    image_data: bytes,
    text: str,
    font_size: int,
    color: str,
    opacity: float,
    position: str,
    position_x: int,
    position_y: int
) -> bytes:
    """为静态图片添加水印"""
    img = Image.open(io.BytesIO(image_data))
    
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    overlay = Image.new('RGBA', img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    
    font = get_font(font_size)
    rgba_color = parse_rgba_color(color, opacity)
    
    # 计算文字尺寸
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # 根据位置计算坐标
    if position == 'center':
        x = (img.width - text_width) // 2
        y = (img.height - text_height) // 2
    elif position == 'bottom-right':
        x = img.width - text_width - 20
        y = img.height - text_height - 20
    elif position == 'tile':
        # 平铺水印
        step_x = text_width + 60
        step_y = text_height + 30
        for row in range(int(text_height + 30), img.height, int(step_y)):
            for col in range(int(text_width + 60), img.width, int(step_x)):
                draw.text((col, row), text, font=font, fill=rgba_color)
        # 直接返回平铺结果
        result = Image.alpha_composite(img, overlay)
        if result.mode == 'RGBA':
            result = result.convert('RGB')
        output = io.BytesIO()
        result.save(output, format='PNG')
        return output.getvalue()
    else:  # custom
        x = int(position_x / 100 * img.width)
        y = int(position_y / 100 * img.height)
    
    draw.text((x, y), text, font=font, fill=rgba_color)
    
    # 合并图层
    result = Image.alpha_composite(img, overlay)
    if result.mode == 'RGBA':
        result = result.convert('RGB')
    
    output = io.BytesIO()
    result.save(output, format='PNG')
    return output.getvalue()

def _add_text_watermark_gif(
    image_data: bytes,
    text: str,
    font_size: int,
    color: str,
    opacity: float,
    position: str,
    position_x: int,
    position_y: int
) -> bytes:
    """为 GIF 动画添加水印（保留所有帧）"""
    logger.info(f"开始处理 GIF: 文字水印")
    
    try:
        img = Image.open(io.BytesIO(image_data))
        logger.info(f"GIF 信息: 尺寸={img.size}, 模式={img.mode}")
    except Exception as e:
        logger.error(f"无法打开 GIF 图片: {e}")
        raise ValueError(f"无法打开 GIF 图片: {e}")
    
    # 获取 GIF 所有帧
    frames = []
    durations = []
    disposes = []
    
    try:
        frame_count = 0
        current = Image.new('RGBA', img.size, (0, 0, 0, 0))
        
        while True:
            frame_count += 1
            
            # 获取当前帧
            try:
                # 获取帧的透明信息
                dispose = img.disposal_method if hasattr(img, 'disposal_method') else 0
                disposes.append(dispose)
                
                # 获取帧延迟
                duration = img.info.get('duration', 100)
                if duration < 20:  # 防止帧延迟过小
                    duration = 100
                durations.append(duration)
                
                # 转换帧为 RGBA
                frame = img.convert('RGBA')
                
                # 叠加到当前画布（处理 disposal）
                if dispose == 2:  # Restore to background
                    current = Image.new('RGBA', img.size, (0, 0, 0, 0))
                elif dispose == 1 and frames:  # Keep previous frame
                    pass  # 保持上一帧
                
                # 使用 alpha 混合
                current = Image.alpha_composite(current, frame)
                
                # 保存处理后的帧
                frames.append(current.copy())
                
                # 跳到下一帧
                img.seek(img.tell() + 1)
            except EOFError:
                break
                
        logger.info(f"共提取 {frame_count} 帧")
    except Exception as e:
        logger.error(f"提取 GIF 帧失败: {e}", exc_info=True)
        raise ValueError(f"提取 GIF 帧失败: {e}")
    
    if not frames:
        raise ValueError("GIF 文件不包含任何帧")
    
    # 为每一帧添加水印
    processed_frames = []
    font = get_font(font_size)
    rgba_color = parse_rgba_color(color, opacity)
    
    try:
        for i, frame in enumerate(frames):
            overlay = Image.new('RGBA', frame.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(overlay)
            
            # 计算文字尺寸
            try:
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
            except:
                text_width = len(text) * font_size * 0.6
                text_height = font_size
            
            # 根据位置计算坐标
            if position == 'center':
                x = (frame.width - text_width) // 2
                y = (frame.height - text_height) // 2
            elif position == 'bottom-right':
                x = frame.width - text_width - 20
                y = frame.height - text_height - 20
            elif position == 'tile':
                step_x = text_width + 60
                step_y = text_height + 30
                for row in range(int(text_height + 30), frame.height, int(step_y)):
                    for col in range(int(text_width + 60), frame.width, int(step_x)):
                        draw.text((col, row), text, font=font, fill=rgba_color)
                processed = Image.alpha_composite(frame, overlay)
                # 转回 P 模式（GIF 需要调色板）
                processed = processed.convert('P', palette=Image.QuantizeAlgorithm.FASTOCTREE)
                processed_frames.append(processed)
                continue
            else:  # custom
                x = int(position_x / 100 * frame.width)
                y = int(position_y / 100 * frame.height)
            
            if position != 'tile':
                draw.text((x, y), text, font=font, fill=rgba_color)
            
            # 合并图层
            processed = Image.alpha_composite(frame, overlay)
            # 转回 P 模式（GIF 需要调色板）
            processed = processed.convert('P', palette=Image.QuantizeAlgorithm.FASTOCTREE)
            processed_frames.append(processed)
            
            if i % 10 == 0:
                logger.info(f"已处理 {i+1}/{len(frames)} 帧")
    except Exception as e:
        logger.error(f"处理 GIF 帧失败: {e}", exc_info=True)
        raise ValueError(f"处理 GIF 帧失败: {e}")
    
    # 保存为 GIF
    output = io.BytesIO()
    try:
        # 第一帧需要包含所有后续帧需要的调色板信息
        processed_frames[0].save(
            output,
            format='GIF',
            save_all=True,
            append_images=processed_frames[1:],
            duration=durations,
            loop=0,
            optimize=False
        )
        result_size = len(output.getvalue())
        logger.info(f"GIF 保存成功, 大小: {result_size} bytes")
        
        if result_size < 100:
            raise ValueError("生成的 GIF 文件过小，可能是处理失败")
            
    except Exception as e:
        logger.error(f"保存 GIF 失败: {e}", exc_info=True)
        raise ValueError(f"保存 GIF 失败: {e}")
    
    return output.getvalue()

def add_image_watermark(
    image_data: bytes,
    watermark_data: bytes,
    scale: float = 15,
    opacity: float = 0.5,
    position: str = "bottom-right",
    position_x: int = 50,
    position_y: int = 50,
    is_gif: bool = False
) -> bytes:
    """
    添加图片水印
    
    Args:
        image_data: 原图二进制数据
        watermark_data: 水印图片二进制数据
        scale: 缩放比例（相对于原图尺寸的百分比）
        opacity: 透明度 0-1
        position: 位置
        position_x: 自定义位置 X (百分比)
        position_y: 自定义位置 Y (百分比)
        is_gif: 是否为 GIF
    """
    try:
        if is_gif:
            return _add_image_watermark_gif(image_data, watermark_data, scale, opacity, position, position_x, position_y)
        else:
            return _add_image_watermark_static(image_data, watermark_data, scale, opacity, position, position_x, position_y)
    except Exception as e:
        logger.error(f"添加图片水印失败: {e}")
        raise

def _add_image_watermark_static(
    image_data: bytes,
    watermark_data: bytes,
    scale: float,
    opacity: float,
    position: str,
    position_x: int,
    position_y: int
) -> bytes:
    """为静态图片添加图片水印"""
    img = Image.open(io.BytesIO(image_data))
    wm_img = Image.open(io.BytesIO(watermark_data))
    
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    if wm_img.mode != 'RGBA':
        wm_img = wm_img.convert('RGBA')
    
    # 计算水印尺寸
    max_dim = max(img.width, img.height)
    wm_width = int(max_dim * scale / 100)
    wm_height = int(wm_width * wm_img.height / wm_img.width)
    wm_img = wm_img.resize((wm_width, wm_height), Image.Resampling.LANCZOS)
    
    # 应用透明度
    alpha = wm_img.split()[3]
    alpha = alpha.point(lambda p: int(p * opacity))
    wm_img.putalpha(alpha)
    
    overlay = Image.new('RGBA', img.size, (255, 255, 255, 0))
    
    # 根据位置计算坐标
    if position == 'center':
        x = (img.width - wm_width) // 2
        y = (img.height - wm_height) // 2
    elif position == 'bottom-right':
        x = img.width - wm_width - 20
        y = img.height - wm_height - 20
    elif position == 'tile':
        step_x = wm_width + 30
        step_y = wm_height + 30
        for row in range(10, img.height, step_y):
            for col in range(10, img.width, step_x):
                overlay.paste(wm_img, (col, row), wm_img)
        result = Image.alpha_composite(img, overlay)
        if result.mode == 'RGBA':
            result = result.convert('RGB')
        output = io.BytesIO()
        result.save(output, format='PNG')
        return output.getvalue()
    else:  # custom
        x = int(position_x / 100 * img.width) - wm_width // 2
        y = int(position_y / 100 * img.height) - wm_height // 2
    
    overlay.paste(wm_img, (x, y), wm_img)
    result = Image.alpha_composite(img, overlay)
    if result.mode == 'RGBA':
        result = result.convert('RGB')
    
    output = io.BytesIO()
    result.save(output, format='PNG')
    return output.getvalue()

def _add_image_watermark_gif(
    image_data: bytes,
    watermark_data: bytes,
    scale: float,
    opacity: float,
    position: str,
    position_x: int,
    position_y: int
) -> bytes:
    """为 GIF 动画添加图片水印"""
    img = Image.open(io.BytesIO(image_data))
    wm_img = Image.open(io.BytesIO(watermark_data))
    
    if wm_img.mode != 'RGBA':
        wm_img = wm_img.convert('RGBA')
    
    # 获取 GIF 所有帧
    frames = []
    durations = []
    
    try:
        while True:
            frame = img.copy()
            if frame.mode != 'RGBA':
                frame = frame.convert('RGBA')
            frames.append(frame)
            durations.append(img.info.get('duration', 100))
            img.seek(img.tell() + 1)
    except EOFError:
        pass
    
    # 计算水印尺寸（基于第一帧）
    max_dim = max(frames[0].width, frames[0].height)
    wm_width = int(max_dim * scale / 100)
    wm_height = int(wm_width * wm_img.height / wm_img.width)
    wm_resized = wm_img.resize((wm_width, wm_height), Image.Resampling.LANCZOS)
    
    # 应用透明度
    alpha = wm_resized.split()[3]
    alpha = alpha.point(lambda p: int(p * opacity))
    wm_resized.putalpha(alpha)
    
    # 为每一帧添加水印
    processed_frames = []
    
    for frame in frames:
        overlay = Image.new('RGBA', frame.size, (255, 255, 255, 0))
        
        if position == 'center':
            x = (frame.width - wm_width) // 2
            y = (frame.height - wm_height) // 2
        elif position == 'bottom-right':
            x = frame.width - wm_width - 20
            y = frame.height - wm_height - 20
        elif position == 'tile':
            step_x = wm_width + 30
            step_y = wm_height + 30
            for row in range(10, frame.height, step_y):
                for col in range(10, frame.width, step_x):
                    overlay.paste(wm_resized, (col, row), wm_resized)
        else:  # custom
            x = int(position_x / 100 * frame.width) - wm_width // 2
            y = int(position_y / 100 * frame.height) - wm_height // 2
        
        if position != 'tile':
            overlay.paste(wm_resized, (x, y), wm_resized)
        
        processed = Image.alpha_composite(frame, overlay)
        processed_frames.append(processed)
    
    # 保存为 GIF
    output = io.BytesIO()
    processed_frames[0].save(
        output,
        format='GIF',
        save_all=True,
        append_images=processed_frames[1:],
        duration=durations,
        loop=0,
        optimize=False
    )
    return output.getvalue()
