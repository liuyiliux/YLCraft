"""自动找出整页漫画里模型留下的「空白占位框」。

**为什么需要**：提示词里写「留出对白气泡的空白位置」时，生图模型经常会**字面地画一个
纯白矩形/椭圆**。贴字前先把它检测出来，就不用靠人眼一个个估坐标了——手工估框很容易
放偏，字就会跑到气泡外面去。

**算法**（移植自 `manga-page-comic` skill 的 `find_blank_boxes.py`，逻辑保持等价）：

1. 转灰度并缩放到固定宽度（`SCAN_W`）——检测只需要大致几何，缩放能把开销压到很低，
   而且顺带抹掉网点与描边这类高频噪声；
2. 二值化：灰度 ≥ `WHITE_MIN` 视为「纯白」。阈值取 244 而不是 255，是为了容忍 JPEG
   压缩与重绘带来的轻微偏色；
3. 对白像素做**连通域（BFS 泛洪）**，取每个连通域的外接框；
4. 按四个条件过滤，只留下「像气泡的矩形」：
   - `fill = 连通域像素数 / 外接框面积` ≥ `min_fill`：真正的矩形/椭圆接近 1；
     描边或纹理构成的碎白区域远低于此；
   - 外接框面积占整页比例在 `[min_area, max_area]`：太小是噪点，太大是整块留白；
   - 长宽比在 `[0.35, 3.2]`：排除细长条（页边、分隔线）；
   - **贴页边的（同时触到 ≥2 条边）一律排除**——那是页边留白，不是占位框；这条最容易
     误判，因为页边留白同样是一大块纯白。
5. 按**从上到下、从左到右**排序，与人阅读漫画的顺序一致——这样自动生成的框能直接和
   该页的分格对白按顺序对应上。

坐标一律是 **0~1 相对值** `[x0, y0, x1, y1]`，与分辨率无关，可直接喂给贴字。
"""

from __future__ import annotations

import logging
from collections import deque
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)

#: 检测用缩放宽度。越小越快、越大越准；384 在 1024~2048 宽的页面上足够定位气泡。
#:
#: 因为扫描宽度固定，下面几个以像素为单位的参数（滤波核、短边下限）也就与原始分辨率
#: 无关——同一条阈值能同时适配 1024 宽和 3840 宽的页。
SCAN_W = 384
#: 「白色」阈值的取值方式：按**页面自身**的亮度分布定，而不是全库一个固定值。
#:
#: 曾经用固定 240，结果是**暗调页全数漏检**：那几页整体压暗，气泡不是纯白而是浅灰
#: （肉眼一眼能看出是空白气泡，程序却一个都检不出来）。实测 15 页里漏 4 页。
#: 再换一个固定值只是重复同一个错误——下一批可能有更暗或更亮的页。
#:
#: 取法：先算页面灰度的 95 分位（近似"这页最亮的那些像素"），再往下退 `WHITE_MARGIN`，
#: 最后夹在 `[WHITE_FLOOR, WHITE_CEIL]` 内。夹取是必须的——分位数本身会被极端值带偏
#: （页面上只有一小块高光时它照样很高），夹取把阈值锁在一个仍然严格的区间里。
#:
#: 实测（15 张真实页 + 1 张无气泡页）：固定 240 → 22 框 / 4 页空；本方案 → **30 框 /
#: 0 页空 / 0 误检**，且 30 框正好是每页 2 个，与该批"每页 2 格各留一个气泡"吻合。
WHITE_PERCENTILE = 95.0
WHITE_MARGIN = 30
WHITE_FLOOR = 200
WHITE_CEIL = 245
#: 二值化前的中值滤波核。
#:
#: **没有它，带颗粒的页面会全数漏检**。实测：提示词里带 `film grain` 的那页，气泡肉眼
#: 看是纯白，但颗粒让灰度在 230~255 之间抖，白像素被碎成一片片——最大的连通域只有
#: 3x387px，远低于面积下限，**两个气泡一个都检不出来**（同一套参数在没有颗粒的页上
#: 能全中，所以问题一直藏着）。中值滤波先抹掉这种抖，气泡内部才重新连成整块。
#:
#: 取 5 而不是 3：3 的核在同样这页上仍会漏（配合 244 阈值时），5 才稳定。这不会误伤
#: 小气泡——`DEFAULT_MIN_SIDE_R` 已要求短边 ≥ 27px（0.07 × 384），5px 的中值抹不掉它。
SCAN_DENOISE_KERNEL = 5
#: 白像素占外接框比例的下限。
#:
#: **刻意低于原脚本的 0.86**：原值是按「矩形气泡」调的，而我们的模型画的是**带尾巴的
#: 椭圆**——椭圆内接于自身外接框，其 fill 上限就是 π/4 ≈ 0.785，永远够不到 0.86。
#: 实测：某张 5 个气泡的叶子上，原参数只检出 1 个（5 个的 fill 分别是 0.84/0.87/0.80/
#: 0.83/0.86，四个卡在 0.86 以下被全数漏掉）。降到 0.72 后 5 个全中。
DEFAULT_MIN_FILL = 0.72
#: 外接框面积占整页比例的下限 / 上限。
DEFAULT_MIN_AREA_R = 0.0009
DEFAULT_MAX_AREA_R = 0.075
#: 外接框**短边**占页宽比例的下限。
#:
#: 这是为压低 fill 阈值必须付的代价：阈值放宽后，画面里成片的白色（白墙、窗框、
#: 天空）也会被连通域捞出来。实测在一张**没有气泡**的教室插图上有 2 个误检，短边
#: 仅占页宽 3.9% / 4.9%；而真实气泡的短边占 9.6%~16%。取 7% 落在这条缝里，
#: 两侧都留了余量。要更保守可调高，要抓小气泡可调低。
DEFAULT_MIN_SIDE_R = 0.07


def _white_threshold(pixels, scan_w: int, scan_h: int) -> int:
    """按页面自身的亮度分布算出「白色」阈值（见 WHITE_PERCENTILE 的说明）。"""
    hist = [0] * 256
    for y in range(scan_h):
        for x in range(scan_w):
            hist[pixels[x, y]] += 1

    total = scan_w * scan_h
    target = total * WHITE_PERCENTILE / 100.0
    accumulated = 0
    percentile = 255
    for value in range(256):
        accumulated += hist[value]
        if accumulated >= target:
            percentile = value
            break
    return max(WHITE_FLOOR, min(WHITE_CEIL, percentile - WHITE_MARGIN))


def detect_blank_boxes(
    image_path: str | Path,
    *,
    min_fill: float = DEFAULT_MIN_FILL,
    min_area_r: float = DEFAULT_MIN_AREA_R,
    max_area_r: float = DEFAULT_MAX_AREA_R,
    min_side_r: float = DEFAULT_MIN_SIDE_R,
) -> list[dict[str, Any]]:
    """找出一张漫画页里的空白占位框。

    检测是**第一遍粗筛**，不是判决：结果会交给贴字编辑器让用户增删，所以宁可召回
    稍宽一点，也不要因为过严而让人重新手估坐标。

    Args:
        image_path: 页图路径。相对路径按**当前工作目录**解析——调用方应先把它变成
            绝对路径（仓库统一用 `asset_file_resolver.resolve_storage_path`，
            因为资产里存的是相对**项目根**的路径，而进程 CWD 通常是 `backend/`）。
        min_fill: 白像素占外接框比例的下限。
        min_area_r: 外接框面积占整页比例的下限。
        max_area_r: 外接框面积占整页比例的上限。
        min_side_r: 外接框短边占页宽比例的下限。

    Returns:
        list[dict]: 每项含 `box`（0~1 的 `[x0, y0, x1, y1]`）、`px_w` / `px_h`（原图像素
        尺寸，供人工核对）、`fill`（矩形度）。按从上到下、从左到右排序。
    """
    path = Path(image_path)
    with Image.open(path) as raw:
        gray = raw.convert("L")
        width, height = gray.size
        scan_w = min(SCAN_W, max(1, width))
        scan_h = max(1, int(height * scan_w / width))
        small = gray.resize((scan_w, scan_h), Image.BOX)
        # 先中值滤波再二值化——否则颗粒会把气泡内部的白色打碎（见 SCAN_DENOISE_KERNEL）。
        small = small.filter(ImageFilter.MedianFilter(SCAN_DENOISE_KERNEL))
        pixels = small.load()

        white_min = _white_threshold(pixels, scan_w, scan_h)
        white = bytearray(scan_w * scan_h)
        for y in range(scan_h):
            row = y * scan_w
            for x in range(scan_w):
                white[row + x] = 1 if pixels[x, y] >= white_min else 0

        seen = bytearray(scan_w * scan_h)
        boxes: list[dict[str, Any]] = []
        for y0 in range(scan_h):
            for x0 in range(scan_w):
                start = y0 * scan_w + x0
                if not white[start] or seen[start]:
                    continue
                queue = deque([(x0, y0)])
                seen[start] = 1
                min_x = max_x = x0
                min_y = max_y = y0
                count = 0
                while queue:
                    x, y = queue.popleft()
                    count += 1
                    if x < min_x:
                        min_x = x
                    if x > max_x:
                        max_x = x
                    if y < min_y:
                        min_y = y
                    if y > max_y:
                        max_y = y
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < scan_w and 0 <= ny < scan_h:
                            idx = ny * scan_w + nx
                            if white[idx] and not seen[idx]:
                                seen[idx] = 1
                                queue.append((nx, ny))

                box_w = max_x - min_x + 1
                box_h = max_y - min_y + 1
                fill = count / float(box_w * box_h)
                area_r = (box_w * box_h) / float(scan_w * scan_h)
                aspect = box_w / float(box_h)
                # 同时贴到两条及以上的边 → 是页边留白，不是占位框。
                touches = sum([min_x == 0, min_y == 0, max_x == scan_w - 1, max_y == scan_h - 1])

                if fill < min_fill or not (min_area_r <= area_r <= max_area_r):
                    continue
                if not (0.35 <= aspect <= 3.2):
                    continue
                if touches >= 2:
                    continue
                # 短边太短的多半是白墙、窗框、天空反光，不是气泡（见 DEFAULT_MIN_SIDE_R）。
                if min(box_w / scan_w, box_h / scan_h) < min_side_r:
                    continue

                boxes.append({
                    "box": [
                        round(min_x / scan_w, 4),
                        round(min_y / scan_h, 4),
                        round((max_x + 1) / scan_w, 4),
                        round((max_y + 1) / scan_h, 4),
                    ],
                    "px_w": int(round(box_w / scan_w * width)),
                    "px_h": int(round(box_h / scan_h * height)),
                    "fill": round(fill, 3),
                })

    # 阅读顺序：先上后下、同高度先左后右。取整到两位是为了让同一"行"的框不至于因
    # 一两个像素的高度差而被判成不同行。
    boxes.sort(key=lambda item: (round(item["box"][1], 2), item["box"][0]))
    logger.info("[blank_boxes] %s -> 检出 %d 个占位框", path.name, len(boxes))
    return boxes
