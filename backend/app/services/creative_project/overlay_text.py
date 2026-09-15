"""漫画页后期贴字（对白气泡 / 旁白框 / 拟声字）。

**为什么必须有这一层**：生图模型无法可靠地写出中文，硬让它写就会出乱码与错别字。
正确做法是生图时**把气泡留空**（提示词里明写"气泡内绝对不要写任何文字"），
再由本模块精确贴字。整页多格漫画的提示词模板已经这么要求了。

引擎来源与改动说明：移植自 workbuddy 的 `manga-page-comic` skill（`scripts/overlay_text.py`），
它的绘制逻辑是实测调好的，**原样保留**（超采样、贝塞尔尾巴、自动换行缩字号、逐字加字距的
拟声字、patch 克隆纹理）。这里只做三件事：① 提供可被服务端调用的函数入口（原脚本是 CLI）；
② 字体发现改成跨平台且优先用仓库可用的字体；③ 增加结构化校验结果，便于接口回传 warnings。

坐标约定：`box = [x0, y0, x1, y1]`，全部是 0~1 的**相对比例**，与图片分辨率无关。
`font_size` 的单位是「图片高度 1024 时的像素」，脚本按实际高度等比缩放。
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

#: 超采样倍数，让椭圆描边和斜体字不锯齿。
SS = 3
#: `font_size` 的参考高度。
BASE_H = 1024.0
#: 成图上低于这个像素高度的字号就算"塞得下"也不可用（中文在这个尺寸已经糊成一团）。
#: 用于把"字号被压到不可读"和"文字被裁切"一起报出来——两者都让成图出错，
#: 但前者不报的话使用者只会觉得"字怎么这么小"，看不出是框给小了。
MIN_USABLE_FONT_PX = 9.0

#: 字体候选。Windows 优先（本项目主环境），其余作兜底；
#: 都找不到时由调用方显式指定 `font`——不静默用默认字体画出不成形的中文。
FALLBACK_FONTS = (
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
)

#: 允许的元素类型。`text` 与 `patch` 是「模型已画好气泡」场景下最常用的两个：
#: `text` 往模型画的空泡里写字；`patch` 把模型多画的泡用旁边纹理盖掉。
ITEM_TYPES = ("bubble", "narration", "sfx", "text", "patch")


def pick_font(path: str | None) -> str:
    for candidate in ([path] if path else []) + list(FALLBACK_FONTS):
        if candidate and os.path.exists(candidate):
            return candidate
    raise ValueError("找不到可用中文字体，请显式指定 font 路径")


def load_font(path: str | None, size: float) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(pick_font(path), int(size))
    except Exception:  # noqa: BLE001 - 字体损坏/不可读时退回候选
        return ImageFont.truetype(pick_font(None), int(size))


def wrap_cjk(text: str, font: ImageFont.FreeTypeFont, max_w: float, draw: ImageDraw.ImageDraw) -> list[str]:
    """按字符宽度换行；支持 ``\\n`` 强制换行。

    中文没有词边界，所以按**字符**折行；这对中英混排也够用（英文单词会被拆开，
    但贴字场景里极少出现长英文）。
    """
    lines: list[str] = []
    for para in text.split("\n"):
        if not para:
            lines.append("")
            continue
        cur = ""
        for ch in para:
            trial = cur + ch
            if draw.textlength(trial, font=font) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)
    return lines


def fit_text(
    text: str, font_path: str | None, max_w: float, max_h: float, start_size: float, draw: ImageDraw.ImageDraw
) -> tuple[ImageFont.FreeTypeFont, list[str], float, bool]:
    """不断缩字号，直到行数与宽度都塞进 ``max_w x max_h``。

    返回 `(font, lines, line_height, fits)`。**`fits=False` 表示缩到最小仍塞不下**——
    此时会照常绘制但文字会被裁掉（原脚本在这里是静默的）。实测踩过：框给得太小，
    "那是什么？" 被裁成 "那是什"，成图看上去只是"少了个字"，很难察觉是尺寸问题。
    所以把这件事显式报出来，交给调用方出 warning。
    """
    size = start_size
    while size >= 6:
        font = load_font(font_path, size)
        lines = wrap_cjk(text, font, max_w, draw)
        lh = size * 1.35
        total_h = lh * len(lines)
        widest = max((draw.textlength(line, font=font) for line in lines), default=0)
        if total_h <= max_h and widest <= max_w:
            return font, lines, lh, True
        size -= max(1, int(size * 0.05))
    font = load_font(font_path, 6)
    return font, wrap_cjk(text, font, max_w, draw), 6 * 1.35, False


def draw_para(
    draw: ImageDraw.ImageDraw, lines: list[str], font: ImageFont.FreeTypeFont, lh: float,
    cx: float, cy: float, max_w: float, fill: tuple, align: str,
) -> None:
    """以 (cx, cy) 为中心画多行文本。"""
    total_h = lh * len(lines)
    y = cy - total_h / 2
    for line in lines:
        w = draw.textlength(line, font=font)
        if align == "left":
            x = cx - max_w / 2
        elif align == "right":
            x = cx + max_w / 2 - w
        else:
            x = cx - w / 2
        draw.text((x, y), line, font=font, fill=fill)
        y += lh


def draw_vertical(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
                  x: float, y: float, fill: tuple, lh: float) -> None:
    """竖排（传统中式旁白框用）。"""
    yy = y
    for ch in text:
        if ch == "\n":
            continue
        w = font.getbbox(ch)[2] - font.getbbox(ch)[0]
        draw.text((x - w / 2, yy), ch, font=font, fill=fill)
        yy += lh


def qbez(p0: tuple, p1: tuple, p2: tuple, n: int = 14) -> list[tuple]:
    """二次贝塞尔采样，用来画有弧度的尾巴侧边。"""
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append((u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                    u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]))
    return pts


def tail_polygon(cx: float, cy: float, bw: float, bh: float, tx: float, ty: float,
                 shape: str, width_ratio: float = 0.34, curve: float = 0.10,
                 grow: float = 0.0) -> list[tuple]:
    """生成气泡尾巴的顶点：细长锥形 + 两侧轻微外弧，指向 (tx, ty)。

    比朴素三角形好的两点，都是实测结论：
    - 宽度按**短边**算（按长边算的话横长气泡会长出又宽又扁的三角）；
    - 侧边用贝塞尔外弧，尖端不再像尖刺。

    返回的顶点同时用于描边层与填充层，因此尾巴与气泡之间不会留接缝。
    ``grow > 0`` 把整条尾巴等比外扩（用于描边层）——**不要**用 PIL 的
    ``polygon(outline=, width=)``，它在尖角处会把尖端切平，尾巴会变成钝头。
    """
    vx, vy = tx - cx, ty - cy
    dist = math.hypot(vx, vy) or 1.0
    vx, vy = vx / dist, vy / dist
    rx, ry = bw / 2.0, bh / 2.0

    # 从气泡中心沿指向射出时与气泡边界的交点
    if shape == "ellipse":
        denom = math.sqrt((vx / rx) ** 2 + (vy / ry) ** 2) or 1e-6
        k = 1.0 / denom
    else:
        k = min(rx / abs(vx) if abs(vx) > 1e-6 else 1e9,
                ry / abs(vy) if abs(vy) > 1e-6 else 1e9)
    k = max(0.0, min(k, dist * 0.88))          # 尾巴长度不越过 tip
    bx, by = cx + vx * k, cy + vy * k
    px, py = -vy, vx                            # 垂直单位向量

    half = min(bw, bh) * width_ratio / 2.0
    half = min(half, dist * 0.5)                # 基部不比尾巴长
    p_l = (bx + px * (half + grow), by + py * (half + grow))
    p_r = (bx - px * (half + grow), by - py * (half + grow))
    bx -= vx * grow * 0.6                       # 基部略回收，外扩更均匀
    by -= vy * grow * 0.6

    tip = (tx + vx * grow, ty + vy * grow)
    bow = curve * dist
    c_l = ((p_l[0] + tip[0]) / 2 + px * bow, (p_l[1] + tip[1]) / 2 + py * bow)
    c_r = ((p_r[0] + tip[0]) / 2 - px * bow, (p_r[1] + tip[1]) / 2 - py * bow)
    left = qbez(p_l, c_l, tip)
    right = qbez(p_r, c_r, tip)[::-1]
    return left + right


def rotated_paste(base_overlay: Image.Image, item_layer: Image.Image, box_px: tuple,
                  angle: float, ss: int) -> None:
    """把内容层旋转后贴回（用于斜着的拟声字 / 歪气泡）。"""
    if not angle:
        base_overlay.alpha_composite(item_layer)
        return
    bb = item_layer.getbbox()
    if not bb:
        return
    pad = int(20 * ss)
    crop = item_layer.crop((max(0, bb[0] - pad), max(0, bb[1] - pad),
                            min(item_layer.width, bb[2] + pad),
                            min(item_layer.height, bb[3] + pad)))
    rot = crop.rotate(angle, expand=True, resample=Image.BICUBIC)
    x = int((box_px[0] + box_px[2]) / 2 - rot.width / 2)
    y = int((box_px[1] + box_px[3]) / 2 - rot.height / 2)
    base_overlay.alpha_composite(rot, (max(0, x), max(0, y)))


def render_item(item: dict[str, Any], overlay: Image.Image, draw: ImageDraw.ImageDraw,
                W: int, H: int, ss: int, font_path: str | None,
                base: Image.Image | None = None,
                warnings: list[str] | None = None) -> None:
    def _note_overflow(font: ImageFont.FreeTypeFont, fits: bool) -> None:
        """文字放不下的两种情况都要报——它们都会让成图出错，但表现完全不同。

        ① `fits=False`：缩到最小仍塞不下，文字**被裁切**（成图看上去只是"少了个字"）；
        ② `fits=True` 但字号已被压到**不可读**：`fit_text` 会一路缩到 6px，技术上"塞得下"，
           实际印出来看不清。实测：一个 18px 见方的框把 15 个字缩成 3 行 6px 字，
           校验通过、肉眼看不出写了什么。只判 ① 会漏掉这一整类问题。
        """
        if warnings is None:
            return
        final_px = font.size / ss          # font.size 在超采样空间里，换算回成图像素
        if fits and final_px >= MIN_USABLE_FONT_PX:
            return
        reason = "被裁切" if not fits else "字号被压到 %.0fpx，已不可读" % final_px
        warnings.append(
            "文字%s（box 太小或字太多）：box=%s text=%r"
            % (reason, item.get("box"), str(item.get("text"))[:20])
        )

    t = item.get("type", "bubble")
    if "box" not in item:
        raise ValueError("item 缺少 box")
    x0, y0, x1, y1 = [v * (W if i % 2 == 0 else H) * ss
                      for i, v in enumerate(item["box"])]
    box_w, box_h = x1 - x0, y1 - y0
    scale = (H / BASE_H)
    fs = item.get("font_size") or max(14, box_h / ss * 0.30 / scale)
    start = max(8, fs * scale * ss)
    text = item.get("text", "")
    fill = tuple(item.get("color", [17, 17, 17]))
    pad = item.get("pad", 0.10)
    align = item.get("align", "center")
    layer = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)

    if t == "bubble":
        shape = item.get("shape", "ellipse")
        stroke = max(2, int(2.4 * scale * ss))
        # 文字安全区：椭圆按内接矩形收 0.70，方形按 pad 收
        if shape == "ellipse":
            tw, th = box_w * 0.70, box_h * 0.68
            radius = None
        else:
            tw, th = box_w * (1 - pad * 2), box_h * (1 - pad * 2)
            radius = int(min(box_w, box_h) * 0.18)
        font, lines, lh, fits = fit_text(text, font_path, tw, th, start, ld)
        _note_overflow(font, fits)

        black, white = (10, 10, 10, 255), (255, 255, 255, 255)
        tail = item.get("tail")
        tw_ratio = item.get("tail_width", 0.34)
        curve = item.get("tail_curve", 0.10)
        cx_c, cy_c = (x0 + x1) / 2, (y0 + y1) / 2

        def _tail(grow: float) -> list[tuple]:
            return tail_polygon(cx_c, cy_c, box_w, box_h,
                                tail[0] * W * ss, tail[1] * H * ss, shape,
                                tw_ratio, curve, grow)

        # ① 先画黑色轮廓层（几何外扩 stroke）；② 再画白色内层盖回去
        #    —— 尾巴与气泡是「一个连通轮廓」，底边不会留黑线，尖端也不会被切平。
        if tail:
            ld.polygon(_tail(stroke), fill=black)
        if shape == "ellipse":
            ld.ellipse([x0 - stroke, y0 - stroke, x1 + stroke, y1 + stroke], fill=black)
        else:
            ld.rounded_rectangle([x0 - stroke, y0 - stroke, x1 + stroke, y1 + stroke],
                                 radius=radius + stroke, fill=black)

        if tail:
            ld.polygon(_tail(0), fill=white)
        if shape == "ellipse":
            ld.ellipse([x0, y0, x1, y1], fill=white)
        else:
            ld.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=white)

        draw_para(ld, lines, font, lh, (x0 + x1) / 2, (y0 + y1) / 2, tw, fill, align)

    elif t == "narration":
        vertical = item.get("vertical", False)
        bg = tuple(item.get("bg", [255, 255, 255, 255]))
        bw = max(2, int(2.2 * scale * ss))
        if vertical:
            ld.rectangle([x0, y0, x1, y1], fill=bg, outline=(10, 10, 10, 255), width=bw)
            lh = max(8, (box_w) * 0.78)
            font = load_font(font_path, lh * 0.86)
            cols = text.split("\n")
            col_gap = box_w * 1.15
            cx = x1 - box_w * 0.6
            for col in cols:
                draw_vertical(ld, col, font, cx, y0 + box_h * 0.08, fill, lh)
                cx -= col_gap
        else:
            ld.rectangle([x0, y0, x1, y1], fill=bg, outline=(10, 10, 10, 255), width=bw)
            tw, th = box_w * (1 - pad * 2), box_h * (1 - pad * 2)
            font, lines, lh, fits = fit_text(text, font_path, tw, th, start, ld)
            _note_overflow(font, fits)
            draw_para(ld, lines, font, lh, (x0 + x1) / 2, (y0 + y1) / 2, tw, fill, align)

    elif t == "sfx":
        # 拟声字：逐字绘制并加字距，避免粗描边把相邻字糊成一团
        font, lines, lh, fits = fit_text(text, font_path, box_w, box_h, start, ld)
        _note_overflow(font, fits)
        ow = item.get("outline", 3.5) * scale * ss * 0.5
        oc = tuple(item.get("outline_color", [255, 255, 255]))
        spacing = item.get("spacing", 0.12)

        def layout(f: ImageFont.FreeTypeFont, line: str) -> tuple[list[float], float, float]:
            ws = [ld.textlength(ch, font=f) for ch in line]
            gap = f.size * spacing if len(line) > 1 else 0
            return ws, gap, sum(ws) + gap * (len(line) - 1)

        # 加了字距后可能超宽 → 缩字号重排
        for _ in range(40):
            total_w = max((layout(font, line)[2] for line in lines), default=0)
            if total_w <= box_w or font.size <= 8:
                break
            font = load_font(font_path, font.size * 0.96)
            lines = wrap_cjk(text, font, box_w, ld)
        lh = max(lh, font.size * 1.35)

        total_h = lh * len(lines)
        y = (y0 + y1) / 2 - total_h / 2
        for line in lines:
            ws, gap, line_w = layout(font, line)
            x = (x0 + x1) / 2 - line_w / 2
            for ch, w in zip(line, ws):
                ld.text((x, y), ch, font=font, fill=fill,
                        stroke_width=int(ow), stroke_fill=oc)
                x += w + gap
            y += lh

    elif t == "text":
        # 只写字、不画框：用于**模型已经把气泡/旁白框画好**的页面，直接写进去。
        # 这是整页多格漫画最主要的用法——提示词已让模型留空气泡。
        tw, th = box_w * (1 - pad * 2), box_h * (1 - pad * 2)
        font, lines, lh, fits = fit_text(text, font_path, tw, th, start, ld)
        _note_overflow(font, fits)
        draw_para(ld, lines, font, lh, (x0 + x1) / 2, (y0 + y1) / 2, tw, fill, align)

    elif t == "patch":
        # 把模型多画的空白框用旁边的画面纹理补掉（原地克隆，交界处羽化）。
        # 注意：patch 要从**原图 base** 取纹理，不能从透明 overlay 层取。
        bw, bh = int(box_w), int(box_h)
        if bw < 2 or bh < 2:
            return
        src_dir = item.get("source", "left")
        for cand in ([src_dir] + [d for d in ("left", "right", "up", "down") if d != src_dir]):
            ox, oy = {"left": (-bw, 0), "right": (bw, 0),
                      "up": (0, -bh), "down": (0, bh)}[cand]
            sx, sy = int(x0 + ox), int(y0 + oy)
            if sx < 0 or sy < 0 or sx + bw > overlay.width or sy + bh > overlay.height:
                continue
            if base is None:
                continue
            patch = base.crop((max(0, int(sx / ss)), max(0, int(sy / ss)),
                               min(base.width, int((sx + bw) / ss) + 1),
                               min(base.height, int((sy + bh) / ss) + 1)))
            patch = patch.resize((bw, bh), Image.LANCZOS).convert("RGBA")
            if item.get("mirror", True):
                patch = patch.transpose(Image.FLIP_LEFT_RIGHT)
            mask = Image.new("L", (bw, bh), 255)
            ImageDraw.Draw(mask).rectangle([0, 0, bw - 1, bh - 1], outline=0, width=4)
            mask = mask.filter(ImageFilter.GaussianBlur(3))
            overlay.paste(patch, (int(x0), int(y0)), mask)
            return
        raise ValueError("patch 找不到可用来源: %s" % (item.get("box"),))

    else:
        raise ValueError("未知 type: " + t)

    rotated_paste(overlay, layer, (x0, y0, x1, y1), item.get("rotate", 0), ss)


def validate_items(items: list[dict[str, Any]]) -> list[str]:
    """校验框位：越界、顶点顺序、以及气泡互相重叠。

    重叠是最常见的翻车点（气泡压住人物眼睛），所以单独查——`patch` 是覆盖操作，跳过。
    """
    warns: list[str] = []
    boxes: list[tuple[int, list[float]]] = []
    for i, it in enumerate(items):
        b = it.get("box")
        if not b or len(b) != 4:
            warns.append("items[%d] box 格式错误" % i)
            continue
        if not all(0 <= v <= 1 for v in b):
            warns.append("items[%d] box 超出 0~1：%s" % (i, b))
        if b[0] >= b[2] or b[1] >= b[3]:
            warns.append("items[%d] box 顶点顺序错误（需 x0<x1, y0<y1）：%s" % (i, b))
        if it.get("type") == "patch":
            continue
        boxes.append((i, b))
    for a in range(len(boxes)):
        for c in range(a + 1, len(boxes)):
            _, b1 = boxes[a]
            _, b2 = boxes[c]
            ox = max(0, min(b1[2], b2[2]) - max(b1[0], b2[0]))
            oy = max(0, min(b1[3], b2[3]) - max(b1[1], b2[1]))
            if ox > 0 and oy > 0:
                area = ox * oy
                smaller = min((b1[2] - b1[0]) * (b1[3] - b1[1]), (b2[2] - b2[0]) * (b2[3] - b2[1]))
                if smaller and area / smaller > 0.15:
                    warns.append("items[%d] 与 items[%d] 重叠 %.0f%%" % (boxes[a][0], boxes[c][0], area / smaller * 100))
    return warns


def overlay_spec(spec: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    """对一张图执行贴字。

    `spec`：`{"image": <输入路径>, "output": <输出路径>, "font"?: str, "items": [...]}`。
    返回 `{"warnings": [...], "output": <输出路径|None>, "size": [w, h]}`。
    `dry_run=True` 只校验不出图（用于"先看框位"）。
    """
    image_path = spec.get("image")
    if not image_path:
        raise ValueError("spec 缺少 image")
    items = spec.get("items") or []
    if not isinstance(items, list):
        raise ValueError("spec.items 必须是数组")

    warnings = validate_items(items)
    base = Image.open(image_path).convert("RGBA")
    W, H = base.size
    if dry_run:
        return {"warnings": warnings, "output": None, "size": [W, H]}

    out_path = spec.get("output") or str(Path(image_path).with_name(Path(image_path).stem + "_text.png"))
    font_path = spec.get("font")

    # 超采样：先在放大图上画，再缩回原尺寸，消除椭圆描边与斜体的锯齿。
    big = base.resize((W * SS, H * SS), Image.LANCZOS)
    overlay = Image.new("RGBA", big.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for item in items:
        # 绘制期的告警（目前是"文字塞不下被裁切"）也收集进来，和框位校验一起回传。
        render_item(item, overlay, draw, W, H, SS, font_path, base=big, warnings=warnings)
    big.alpha_composite(overlay)
    result = big.resize((W, H), Image.LANCZOS)
    result.convert("RGB").save(out_path)
    return {"warnings": warnings, "output": out_path, "size": [W, H]}


def _main() -> int:  # pragma: no cover - 仅供命令行手工调试
    import argparse
    import json

    ap = argparse.ArgumentParser(description="漫画页贴字")
    ap.add_argument("spec", help="JSON 配置文件")
    ap.add_argument("--dry-run", action="store_true", help="只校验框位，不出图")
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    result = overlay_spec(spec, dry_run=args.dry_run)
    for w in result["warnings"]:
        print("  [warn] %s" % w)
    print("  输出: %s" % result["output"])
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main())
