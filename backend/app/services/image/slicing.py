"""通用图片切片（frame sheet slicing）服务。

**为什么是公共组件**：项目里至少有两处需要"把一张多格图切成 N 格"——

- 角色立绘九宫格切片（现有实现焊死在 `api/v1/characters.py` 内）
- 动图切帧（多格图 → 逐帧）

两者要的是同一件事：**按 rows×cols 把一张图切成若干格，并按用户指定的顺序
与取舍重排**。各写一份必然漂移，所以抽到这里。**本模块只做像素级切分与
顺序/取舍的纯计算，不认识 Asset Hub、不落库、不认识业务**——落库与业务
语义由调用方决定，这样立绘与动图都能用它而不互相牵制。

纯函数、无 IO，便于完整单测。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from PIL import Image, ImageFilter

# 背景掩膜阈值：影棚背景常是**渐变**的，低阈值会把整片背景判成主体，
# 于是 bbox 退化成整格、裁切失效。实测 40 会踩这个坑（2x4 的 256x512 格
# 被整块保留），70 才稳定切出主体。
BG_MASK_THRESHOLD = 70

#: 单格短边的最小像素。太小的格在缩放后必然发糊，宁可明确拒绝。
MIN_CELL_SIDE = 16

#: 两条相邻分割线被强行分开时的最小归一化间隔。
#: 只在**真的重合**时使用；正常值（含均匀值）一律原样保留。
EDGE_EPS = 1e-6


@dataclass(frozen=True)
class SliceRef:
    """一格的来源标识。

    `source` 区分三种来源，**顺序信息只认这个字段，不认数组下标**：

    - ``{"kind": "origin", "index": 3}``  —— 原多格图的第 3 格
    - ``{"kind": "upload", "index": 1}``  —— 用户上传补的第 1 张
    - ``{"kind": "region", "box": (l,t,r,b)}`` —— 自由裁切区域

    为什么不用下标：用户删掉第 3 格再补一张上传图之后，"第 5 格是原图第几格"
    才是用户要核对的信息（`P3=原4`），下标会随操作漂移。
    """

    source: dict[str, Any]

    @property
    def kind(self) -> str:
        return str(self.source.get("kind") or "origin")

    @property
    def origin_index(self) -> int | None:
        """原多格图的格号（1 起）；上传或自由裁切返回 None。"""
        if self.kind != "origin":
            return None
        value = self.source.get("index")
        return int(value) if value is not None else None

    def label(self) -> str:
        if self.kind == "upload":
            return f"上传{int(self.source.get('index') or 0)}号"
        if self.kind == "region":
            return "自选区域"
        return f"原{self.origin_index}"


def origin_refs(count: int) -> list[SliceRef]:
    """把一整张多格图按 1..count 变成默认切片序列。"""
    return [SliceRef({"kind": "origin", "index": i}) for i in range(1, count + 1)]


# ---------------------------------------------------------------------------
# 每格微调
# ---------------------------------------------------------------------------

#: 微调项的允许范围与中性值。前端滑块与后端校验共用这一份定义。
ADJUST_RANGES: dict[str, tuple[float, float]] = {
    "brightness": (0.4, 1.6),  # 1.0 = 不变
    "contrast": (0.4, 1.6),
    "saturation": (0.0, 2.0),  # 0 = 纯灰
    "hue": (-0.5, 0.5),  # ±180°
    "rotate": (-15.0, 15.0),  # ±15°，再大就会露画布缺角
}


@dataclass(frozen=True)
class FrameAdjust:
    """一帧的**像素级微调**（不调模型）。

    为什么需要：模型每格的亮度/色调常有轻微差异，拼成动图会表现为
    "一闪一闪"。这类问题**不该花钱重画**，滑一下亮度就解决。

    只做纯像素变换，**零模型调用、零质量损失**（除缩放/旋转的重采样）。
    想要"真的改画面内容"（重画、扩图）得走图片编辑器，那不是微调。

    越界的值一律**夹回合法范围**而不是报错：前端滑块可能因为切了排布
    而带上旧值，宁可夹住也不要整个合成失败。
    """

    brightness: float = 1.0
    contrast: float = 1.0
    saturation: float = 1.0
    hue: float = 0.0
    rotate: float = 0.0

    @classmethod
    def from_source(cls, source: dict[str, Any] | None) -> FrameAdjust | None:
        """从 ``SliceRef.source['adjust']`` 解析；没有或全是中性值返回 None。"""
        if not source:
            return None
        raw = source.get("adjust")
        if not isinstance(raw, dict):
            return None
        kwargs: dict[str, float] = {}
        for key, (lo, hi) in ADJUST_RANGES.items():
            try:
                value = float(raw.get(key))
            except (TypeError, ValueError):
                continue
            kwargs[key] = min(hi, max(lo, value))
        inst = cls(**kwargs)
        return None if inst.is_neutral else inst

    @property
    def is_neutral(self) -> bool:
        return (
            abs(self.brightness - 1.0) < 1e-6
            and abs(self.contrast - 1.0) < 1e-6
            and abs(self.saturation - 1.0) < 1e-6
            and abs(self.hue) < 1e-6
            and abs(self.rotate) < 1e-6
        )

    def apply(self, image: Image.Image) -> Image.Image:
        """把微调作用到一帧。RGB 模式走 PIL 增强，rotate 用同色补边。"""
        if self.is_neutral:
            return image
        out = image.convert("RGB")
        if abs(self.rotate) > 1e-6:
            # 旋转会露画布缺角，用**边缘像素**补，不留黑角（与对齐同一教训）
            out = out.rotate(
                self.rotate,
                resample=Image.BICUBIC,
                expand=False,
                fillcolor=out.getpixel((out.width // 2, 0)),
            )
        from PIL import ImageEnhance

        if abs(self.brightness - 1.0) > 1e-6:
            out = ImageEnhance.Brightness(out).enhance(self.brightness)
        if abs(self.contrast - 1.0) > 1e-6:
            out = ImageEnhance.Contrast(out).enhance(self.contrast)
        if abs(self.saturation - 1.0) > 1e-6:
            out = ImageEnhance.Color(out).enhance(self.saturation)
        if abs(self.hue) > 1e-6:
            # 色相没有 ImageEnhance，自行走 HSV；PIL 的 H 是 0..255
            hsv = out.convert("HSV")
            h, s, v = hsv.split()
            shift = int(round(self.hue * 255)) % 256
            h = h.point(lambda p: (p + shift) % 256)
            out = Image.merge("HSV", (h, s, v)).convert("RGB")
        return out


def slice_grid(
    sheet: Image.Image,
    rows: int,
    cols: int,
) -> list[Image.Image]:
    """按 rows×cols 均匀切分（行优先，与人眼阅读顺序一致）。

    切出来的格尺寸可能不是方形（2×4 时单格是 256×512），这是几何事实，
    不在这里裁成方形——**是否统一取景由调用方决定**（动图用
    :func:`content_bbox` 做一次全局裁切，保证 16 格取景一致）。

    要支持用户拖分割线改比例，走 :class:`SheetGrid`。
    """
    return SheetGrid.uniform(rows, cols).slice(sheet)


@dataclass(frozen=True)
class SheetGrid:
    """**可拖分割线**的规整网格。

    为什么不是"自由框"：用户要的是"九宫格但能自己调"，自由框虽然更灵活，
    但要处理任意重叠、任意大小的框，交互立刻变得难懂。这里保留规整的
    rows×cols 结构，只让**分割线位置可调** —— 拖一条线，相邻两格同时变形，
    符合直觉且不会出现"格子重叠/空洞"。

    边界用**归一化坐标**（0..1）存储，不用像素：换一张分辨率不同的多格图时，
    同样的拖法能直接复用，不会开出 256px 宽的框落在 1024px 的图上。

    坐标约定：`xs` 长度 ``cols+1``，`ys` 长度 ``rows+1``，两端固定 0/1，
    中间严格递增（允许重合 → 那一格宽度为 0，会被拒绝）。
    """

    rows: int
    cols: int
    xs: tuple[float, ...] = ()
    ys: tuple[float, ...] = ()

    @classmethod
    def uniform(cls, rows: int, cols: int) -> SheetGrid:
        if rows <= 0 or cols <= 0:
            raise ValueError("rows/cols 必须为正整数")
        return cls(
            rows=rows,
            cols=cols,
            xs=tuple(i / cols for i in range(cols + 1)),
            ys=tuple(i / rows for i in range(rows + 1)),
        )

    @classmethod
    def from_edges(
        cls,
        rows: int,
        cols: int,
        xs: Sequence[float] | None = None,
        ys: Sequence[float] | None = None,
    ) -> SheetGrid:
        """从用户拖出来的边界构造，自动**补齐/夹紧/去重**。

        故意做得很宽容：前端可能传来少一个端点、越界、非递增的值。
        这里一律修正而不是抛错 —— 拖分割线过程中的中间态很常见，
        让整个合成因为"边界没对齐"失败没有意义。
        """
        if rows <= 0 or cols <= 0:
            raise ValueError("rows/cols 必须为正整数")
        return cls(
            rows=rows,
            cols=cols,
            xs=_normalize_edges(xs, cols),
            ys=_normalize_edges(ys, rows),
        )

    def cell_boxes(self, width: int, height: int) -> list[tuple[int, int, int, int]]:
        """按归一化边界算出每格的像素框（行优先）。"""
        out: list[tuple[int, int, int, int]] = []
        for r in range(self.rows):
            top = round(self.ys[r] * height)
            bottom = round(self.ys[r + 1] * height)
            for c in range(self.cols):
                left = round(self.xs[c] * width)
                right = round(self.xs[c + 1] * width)
                out.append((left, top, right, bottom))
        return out

    def slice(self, sheet: Image.Image) -> list[Image.Image]:
        """按当前边界切出所有格。"""
        if self.rows <= 0 or self.cols <= 0:
            raise ValueError("rows/cols 必须为正整数")
        width, height = sheet.size
        boxes = self.cell_boxes(width, height)
        thin = [b for b in boxes if min(b[2] - b[0], b[3] - b[1]) < MIN_CELL_SIDE]
        if thin:
            bad = thin[0]
            raise ValueError(
                f"单格尺寸过小：{bad[2] - bad[0]}x{bad[3] - bad[1]} 像素"
                f"（{self.rows}x{self.cols} 切 {width}x{height}，最小 {MIN_CELL_SIDE}）。"
                f"格数过多、源图太小，或分割线被拖到一起了。"
            )
        return [sheet.crop(box) for box in boxes]

    def is_uniform(self) -> bool:
        base = SheetGrid.uniform(self.rows, self.cols)
        return self.xs == base.xs and self.ys == base.ys


def _normalize_edges(edges: Sequence[float] | None, count: int) -> tuple[float, ...]:
    """把拖出来的分割线整理成 ``count+1`` 个**严格递增**的归一化边界。

    **输入可以是「含两端点」或「只含内部线」两种写法**，都会被接受：

    - ``count+1`` 个（前端 ``uniformEdges`` 与回传都走这种，含 0 和 1）→ 去掉两端
    - ``count-1`` 个（只给内部线）→ 直接用

    早期只按"只含内部线"读，结果前端把 ``[0, 0.25, 0.5, 0.75, 1]`` 发过来时，
    开头的 ``0`` 被当成第一条内部线 —— **第一格宽度直接塌成 0**，
    整单报"单格尺寸过小 0x0"。

    其余宽容处理：少给、越界、非递增都不报错 ——
    - 少给 → 缺失的内部线用均匀值补
    - 给多 → 只取前 ``count-1`` 个内部线（两端由 0/1 固定）
    - 越界 → 夹到 (0, 1)
    - 非递增 → 与前一个值取较大者再夹，最后与 1 合并保证最后一格非空
    """
    uniform = [i / count for i in range(count + 1)]
    out = [0.0]
    given = [float(v) for v in (edges or [])] if edges else []
    # 含两端点 → 去掉首尾，只留内部线
    if len(given) >= count + 1:
        given = given[1:count]
    for i in range(1, count):
        raw = given[i - 1] if len(given) >= i else uniform[i]
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = uniform[i]
        if value != value:  # NaN
            value = uniform[i]
        value = min(1.0, max(0.0, value))
        # 严格递增：重合的两条线会让格子宽 0，min/max 夹不出来。
        # ⚠️ **只在真的撞上（或更小）时才推开**：均匀值 `[0, 0.5, 1]` 被逐项
        # `max(v, prev+eps)` 推一遍会变成 `[0, 1e-6, 1]` —— 第一格直接塌成 0 高。
        # 前端每次拖完都会把边界原样回传，均匀的那份也走这条路，
        # 所以这里必须原样保留。
        if value <= out[-1]:
            value = out[-1] + EDGE_EPS
        if value > 1.0:
            # 撞到右边界：最后一个内部线必须给末格留出宽度
            value = max(out[-1] + EDGE_EPS, 1.0 - EDGE_EPS * (count - i))
        out.append(value)
    out.append(1.0)
    return tuple(out)


def background_mask(image: Image.Image, threshold: int = BG_MASK_THRESHOLD) -> Image.Image:
    """以四角颜色中位数为背景色，估主体掩膜。"""
    import numpy as np

    arr = _to_array(image.convert("RGB"))
    bg = np.median(_corner_pixels(arr), axis=0)
    diff = np.abs(arr - bg).sum(axis=2)
    mask = Image.fromarray(((diff > threshold) * 255).astype("uint8"), "L")
    # 去零星噪点：几个杂点就能把 bbox 撑满
    return mask.filter(ImageFilter.MedianFilter(size=5))


def content_bbox(image: Image.Image, threshold: int = BG_MASK_THRESHOLD) -> tuple[int, int, int, int] | None:
    """单帧内主体包围盒（不含背景）。全平背景时返回 None。"""
    return background_mask(image, threshold).getbbox()


def union_bbox(
    images: Sequence[Image.Image],
    pad: int = 6,
    threshold: int = BG_MASK_THRESHOLD,
) -> tuple[int, int, int, int] | None:
    """多帧主体的**并集**包围盒，并裁剪回各自图范围内。

    对动图很关键：每格单独裁会得到不同尺寸，合成后尺寸跳变；按并集统一裁
    才能保证所有帧同尺寸、同取景。

    `pad` 向外扩一点留边。**必须夹回图内**——否则负坐标会让相邻格被卷进来
    （实测裁到 -132 就把左边那格吃了一半）。
    """
    boxes = [b for b in (content_bbox(img, threshold) for img in images) if b]
    if not boxes:
        return None
    width, height = images[0].size
    x0 = max(0, min(b[0] for b in boxes) - pad)
    y0 = max(0, min(b[1] for b in boxes) - pad)
    x1 = min(width, max(b[2] for b in boxes) + pad)
    y1 = min(height, max(b[3] for b in boxes) + pad)
    if x1 - x0 < MIN_CELL_SIDE or y1 - y0 < MIN_CELL_SIDE:
        return None
    return (x0, y0, x1, y1)


def apply_global_crop(
    images: Sequence[Image.Image],
    pad: int = 6,
    enabled: bool = False,
) -> list[Image.Image]:
    """对所有帧套用同一个并集裁切框，保证尺寸与取景一致。

    ⚠️ **默认关闭裁切**（`enabled=False`）。这不是偷懒，是实测踩出来的：

    多格图**每一格本身就已经取好景了**（生成提示词里写了"主体居中"）。
    而"并集包围盒"是**所有帧主体的最小公共框** —— 它会切掉每格画面里
    主体之外的留白。实测蓝狗图：单格 256×512，并集框只有 **234×212**，
    裁完**把狗腰斩了**，主体占满整帧、顶到边，还被补出白边。

    所以：
    - `enabled=False`（默认）：只保证**同尺寸**（格与格之间已由 `slice_grid`
      保证一致），不裁内容 —— 保住每格原有的取景。
    - `enabled=True`：需要去掉格与格之间的空白边时才开（比如模型在每格里
      又画了一圈边距）。**开着会让画面更紧**，不是"更清晰"。
    """
    if not enabled:
        return [img.copy() for img in images]
    box = union_bbox(images, pad=pad)
    if box is None:
        return [img.copy() for img in images]
    return [img.crop(box) for img in images]


def align_frames_by_content(
    images: Sequence[Image.Image],
    threshold: int = BG_MASK_THRESHOLD,
) -> list[Image.Image]:
    """把每帧的**主体内容居中**到同一画布。

    为什么需要：`apply_global_crop` 用的是所有帧的**并集**包围盒 —— 裁切框统一、
    尺寸也就一致了，但**主体在每格里的位置仍然不一样**。图像模型生成多格图时
    不保证主体在每格中居中，于是拼成动画后主体会上下/左右跳动，观感像"整张图在抖"。

    这里按每帧自己的内容 bbox 把主体**平移**到画布中心。**只平移、不缩放**：
    缩放会引入插值糊化，而位置抖动靠平移就能解决。

    代价是背景被横向补边（原本露出的背景换成边缘像素的横向拉伸）。对影棚纯色背景
    几乎无感，对复杂背景可见 —— 所以做成**可关的开关**，让用户按素材选。
    """
    if not images:
        return []
    # ⚠️ **各帧尺寸不同时，不做对齐**。
    #
    # 对齐的前提是"所有帧共用一块画布"：它把每帧主体平移到画布中心，必然要求
    # 输出尺寸统一。而**拖过分割线之后各格尺寸本来就不同**（实测同一张图能切出
    # 378px 与 134px 并存的列）—— 强行统一只能把窄的那格**补边撑回最宽**，
    # 于是"用户刚拖窄的那一列"在结果里**看不出来**（正是用户反馈的
    # "我拖动以后点确认，下面没有变化，应该最后两个被切一半了"）。
    #
    # 说明：这种情况下"对齐"本身也没有意义 —— 每格宽高比都不同，
    # 谈"主体居中"没有统一参照。保住用户拖出来的真实几何更重要。
    sizes = {img.size for img in images}
    if len(sizes) > 1:
        return [img.copy() for img in images]
    width, height = images[0].size
    out: list[Image.Image] = []
    for img in images:
        box = content_bbox(img, threshold)
        if not box:
            out.append(img.copy())
            continue
        x0, y0, x1, y1 = box
        dx = ((x0 + x1) / 2) - (width / 2)
        dy = ((y0 + y1) / 2) - (height / 2)
        # 容差 1.0：bbox 右/下边界是**开区间**，一个正好居中的偶数尺寸主体
        # 会算出 0.5px 的"偏移"。卡在 0.5 会让本该跳过的帧白白重采样一次。
        if abs(dx) < 1.0 and abs(dy) < 1.0:
            out.append(img.copy())
            continue
        # `Image.AFFINE` 的矩阵是 **输出 → 输入**：输出点 (x,y) 取输入点
        # (a·x + b·y + c, d·x + e·y + f)。要让主体在输出里朝 -dx 移动，
        # 就得在输入坐标里朝 +dx 取样，即 c = dx。
        #
        # ⚠️ `fillcolor` 必须给：挪出画布的那部分默认填**纯黑**，
        # 实测对齐后边框有 38~50% 变成黑边（对齐前是 0%）——GIF 里就是一圈黑框。
        # 用边缘像素横向拉伸来补（影棚纯色背景下几乎无感），复杂背景下可见。
        edge = img.getpixel((width // 2, 0)) or img.getpixel((0, height // 2)) or (0, 0, 0)
        out.append(
            img.transform(
                (width, height),
                Image.AFFINE,
                (1, 0, dx, 0, 1, dy),
                resample=Image.BILINEAR,
                fillcolor=edge,
            )
        )
    return out


def resolve_frames(
    sheet: Image.Image,
    rows: int,
    cols: int,
    order: Sequence[SliceRef],
    uploads: dict[int, Image.Image] | None = None,
    grid: SheetGrid | None = None,
) -> list[Image.Image]:
    """按 ``order`` 取到实际像素帧，并逐帧应用微调。

    这是切片的**唯一权威入口**：``slice_grid`` 只负责几何切分，"用户把第 3 格
    删了、补了一张自己的图、调了亮度、拖了分割线" 这类语义全在这里收口，
    避免多处各自解释同一份 order。

    Args:
        sheet: 多格图原图。
        rows / cols: 多格图排布。
        order: 期望的帧序列，元素说明"这一帧取自哪里"。
        uploads: 上传图，按 ``SliceRef.source["index"]`` 索引。
        grid: 用户拖过分割线的网格；None = 均匀切分。

    Raises:
        ValueError: ``order`` 引用了不存在的原图格号。
    """
    grid_obj = grid if grid is not None and not grid.is_uniform() else None
    cache: dict[int, Image.Image] | None = None
    out: list[Image.Image] = []
    for ref in order:
        adjust = FrameAdjust.from_source(ref.source)
        if ref.kind == "upload":
            index = int(ref.source.get("index") or 0)
            image = (uploads or {}).get(index)
            if image is None:
                raise ValueError(f"上传图 #{index} 不存在")
            out.append(_apply_adjust(image.convert("RGB"), adjust))
            continue
        if ref.kind == "region":
            box = ref.source.get("box")
            if not box or len(tuple(box)) != 4:
                raise ValueError("自选区域必须提供 (left, top, right, bottom)")
            out.append(
                _apply_adjust(sheet.crop(tuple(int(v) for v in box)).convert("RGB"), adjust)
            )
            continue
        origin = ref.origin_index
        if origin is None:
            raise ValueError(f"无法识别的切片来源：{ref.source}")
        if cache is None:
            cells = (
                grid_obj.slice(sheet)
                if grid_obj is not None
                else slice_grid(sheet, rows, cols)
            )
            cache = {i + 1: img for i, img in enumerate(cells)}
        if origin not in cache:
            raise ValueError(f"原图只有 {len(cache)} 格，order 引用了第 {origin} 格")
        out.append(_apply_adjust(cache[origin], adjust))
    return out


def _apply_adjust(image: Image.Image, adjust: FrameAdjust | None) -> Image.Image:
    return image if adjust is None else adjust.apply(image)


def describe_order(order: Sequence[SliceRef]) -> list[str]:
    """把 order 渲染成 ``["原1", "原4", "上传1号"]``，供 UI 与日志核对。"""
    return [ref.label() for ref in order]


def drop_missing_origin(order: Sequence[SliceRef], total_cells: int) -> list[SliceRef]:
    """剔除引用了不存在格号的项（用户换排布后旧的 order 会失效）。"""
    return [
        ref
        for ref in order
        if ref.kind != "origin" or (ref.origin_index or 0) <= total_cells
    ]


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _to_array(image: Image.Image):
    import numpy as np

    return np.asarray(image, dtype=np.int16)


def _corner_pixels(arr, size: int = 6):
    """取四角各 ``size`` 像素，用来估计背景色。"""
    import numpy as np

    return np.concatenate(
        [
            arr[:size, :size].reshape(-1, 3),
            arr[:size, -size:].reshape(-1, 3),
            arr[-size:, :size].reshape(-1, 3),
            arr[-size:, -size:].reshape(-1, 3),
        ]
    )
