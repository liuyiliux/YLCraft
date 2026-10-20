"""动图合成服务：多格图 → GIF / WebP / MP4。

**原理**：动图不是"生成一段视频"，而是**一次性画好多格连续画面**，再按节奏
把它们连起来播放。逐帧生成会漂移，一次画完则前后一致。

本模块负责**纯合成**：切片（交给公共组件 `services/image/slicing.py`）→
统一裁切 → 循环补缝 → 帧时长 → 量化 → 导出 GIF/WebP/MP4。**不调用任何
图像模型**，因此重复执行不花钱，这是"改切帧不用重画"的实现基础。

实测结论（gpt-image-2，见 docs/devlog 里的验证记录）：

- **8 格（2×4）比 16 格（4×4）明显更稳**：16 格会出现"每行重开一次"的
  来回摆动，且最大相邻差可达 9.3；8 格换行跳变比降到 1.05，转动幅度反而更大。
- **WebP 通常只有 GIF 的 1/10 ~ 1/24 体积**且满分辨率，高质量/透明素材应主推 WebP。
- **GIF 只有 1-bit 透明**，半透明残影会被压成实心色块，透明素材必须用 WebP。
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Sequence

from PIL import Image

from app.services.image import slicing

logger = logging.getLogger("ylcraft.motion_gif")

LoopMode = Literal["pingpong", "cycle", "none"]

#: GIF/WebP 的循环次数：0 = 无限循环。
GIF_LOOP_FOREVER = 0

#: 单帧最短停留（毫秒）。低于 ~20ms 多数播放器会跳帧。
MIN_FRAME_MS = 20

#: 多格图原图在产物目录里的文件名。它是**附属数据**：成品要能"改切帧重出"
#: 就必须留着原图，而它本身也是可被其它功能取用的素材。
FRAMESHEET_NAME = "framesheet.png"


@dataclass(frozen=True)
class MotionGifOptions:
    """合成参数。

    这些**全部是合成参数，不影响模型画什么**，因此都放在生成之后让用户调，
    改任何一个都不需要重新调用模型。

    Args:
        rows / cols: 多格图排布。
        order: 帧序列（来源标识），见 :class:`~app.services.image.slicing.SliceRef`。
        loop: ``pingpong`` 正放完倒放（环绕类接缝最自然）、``cycle`` 首尾相接
            （表情/动作类需要最后一格回到第一格）、``none`` 正放一次。
        size: 输出长边像素。
        frame_ms: 基础帧时长。
        timing: ``ramp`` 前慢后快（让观众看清起始画面，环绕类默认）、
            ``even`` 按每格变化量分配、``none`` 等距。
        max_kb: GIF 体积上限；超了就沿阶梯降尺寸/色数。0 = 不限制。
        colors: GIF 调色板色数上限。
        resample: ``nearest`` 用于像素风（平滑滤镜会毁掉像素网格）。
        dither: Floyd-Steinberg 抖动，像素风/平色应关闭（会撒噪点）。
        transparent: 是否走透明通道（透明素材必须配 WebP）。
    """

    rows: int
    cols: int
    order: tuple[slicing.SliceRef, ...]
    loop: LoopMode = "pingpong"
    size: int = 480
    frame_ms: int = 70
    timing: Literal["ramp", "even", "none"] = "ramp"
    max_kb: int = 3000
    colors: int = 255
    resample: Literal["lanczos", "nearest"] = "lanczos"
    dither: bool = True
    transparent: bool = False
    fps: int = 25
    #: 把每帧主体**平移居中**。关掉则保留各帧原始位置（背景不补边，
    #: 但主体可能上下跳动）。默认开 ——「主体不动」比「背景轻微变形」更符合预期。
    align_subject: bool = True
    #: 是否按"并集包围盒"裁掉每格主体之外的留白。**默认关** ——
    #: 多格图每格本身已取好景，裁内容会把主体切坏（实测把蓝狗腰斩）。
    trim: bool = False
    #: 用户拖过分割线的网格。None = 均匀切分。见 :class:`~app.services.image.slicing.SheetGrid`。
    grid: slicing.SheetGrid | None = None


@dataclass
class MotionGifResult:
    """合成产物。``paths`` 为空表示 MP4 跳过（ffmpeg 不可用）。"""

    frames: int
    cell_size: tuple[int, int]
    output_size: tuple[int, int]
    frame_durations: list[int] = field(default_factory=list)
    gif_path: Path | None = None
    gif_kb: float = 0.0
    gif_colors: int = 0
    webp_path: Path | None = None
    webp_kb: float = 0.0
    mp4_path: Path | None = None
    mp4_kb: float = 0.0
    mp4_skipped_reason: str = ""
    #: 每帧的小图 URL（前端切帧面板直接显示真实像素）。
    frame_paths: list[str] = field(default_factory=list)
    #: 产物版本指纹（由 GIF 文件的 size+mtime 算出）。
    #:
    #: 为什么需要：合成产物**原地覆写同一个 `animation.gif`**，URL 一个字不变，
    #: 浏览器就会一直显示旧图 —— 用户改了循环方式重新合成，预览却毫无变化
    #: （实测反馈："我修改循环或者改了帧重新合成，预览这里没变"）。
    #: 前端拿它拼成 `?v=<revision>` 强制刷新。
    revision: str = ""

    def to_payload(self) -> dict[str, Any]:
        """给 API / 前端用的可序列化摘要。"""
        return {
            "frames": self.frames,
            "cell_size": list(self.cell_size),
            "output_size": list(self.output_size),
            "frame_durations": self.frame_durations,
            "gif_path": str(self.gif_path) if self.gif_path else None,
            "gif_kb": round(self.gif_kb, 1),
            "gif_colors": self.gif_colors,
            "webp_path": str(self.webp_path) if self.webp_path else None,
            "webp_kb": round(self.webp_kb, 1),
            "mp4_path": str(self.mp4_path) if self.mp4_path else None,
            "mp4_kb": round(self.mp4_kb, 1),
            "mp4_skipped_reason": self.mp4_skipped_reason,
            "frame_paths": list(self.frame_paths),
            "revision": self.revision,
        }


def output_revision(*paths: Path | None) -> str:
    """按产物文件的**内容**算一个版本指纹。

    用它拼 `?v=<revision>` 让浏览器刷新被覆写的产物。

    ⚠️ **必须按内容算，不能按 mtime**：实测"同参数重复合成"用 mtime 会得到
    不同指纹（文件每次都被重写），于是每次重新合成都白白让缓存失效 ——
    同一张图来回看几次就反复重下几 MB 的 GIF。

    按内容则：内容真变了指纹才变；内容相同（同参数重合成）指纹稳定，缓存继续有效。
    这也与 `assets.download` 的 ETag 思路一致。
    """
    digest = hashlib.sha1()
    for p in paths:
        if p is None:
            continue
        try:
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    digest.update(chunk)
        except OSError:
            continue
    return digest.hexdigest()[:12]


async def compose_motion_gif(
    sheet: Image.Image,
    uploads: dict[int, Image.Image] | None,
    options: MotionGifOptions,
    output_dir: Path,
    *,
    write_webp: bool = True,
    write_mp4: bool = False,
) -> MotionGifResult:
    """把多格图合成为动图。

    Args:
        sheet: 多格图原图（模型产出）。
        uploads: 用户上传补位的图片，按 upload index 索引。
        options: 合成参数。
        output_dir: 产物目录（不存在会自动创建）。
        write_webp / write_mp4: 是否导出对应格式。透明素材应 ``write_mp4=False``
            ——MP4 没有 alpha，导出时会被压到白底，透明信息本就不存在。

    Raises:
        ValueError: order 为空、引用了不存在的格号，或单格尺寸过小。
    """
    if not options.order:
        raise ValueError("切帧顺序为空：至少要有一帧才能合成")

    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. 按 order 取帧（切片语义的唯一入口）
    frames = slicing.resolve_frames(
        sheet, options.rows, options.cols, options.order, uploads, grid=options.grid
    )

    # 2. 统一取景。**默认不裁**：多格图每格本身已取好景，而"并集包围盒"会切掉
    #    主体之外的留白 —— 实测蓝狗图单格 256×512、并集框只有 234×212，裁完把狗腰斩、
    #    主体顶满画布还补出白边。不裁时 `slice_grid` 已保证各帧同尺寸，合成不会跳变。
    if options.trim:
        frames = slicing.apply_global_crop(frames, enabled=True)
    # 2.5 主体居中对齐：模型不保证主体在每格中居中，不对齐的话主体会在画面里
    #     上下跳动（用户实测："gif 主体上下位置有不同"）。只平移不缩放。
    if options.align_subject:
        frames = slicing.align_frames_by_content(frames)
    # 拖过分割线后各格可能不同尺寸；`cell_size` 报**众数**（与 `_resize_all`
    # 选的画布一致），别拿第一帧去代表全部。
    _counts: dict[tuple[int, int], int] = {}
    for f in frames:
        _counts[f.size] = _counts.get(f.size, 0) + 1
    cell_size = max(_counts, key=lambda s: (_counts[s], s[0] * s[1]))

    # 3. 循环补缝
    out_frames = _build_loop(frames, options.loop)

    # 4. 帧时长（基于缩放后的帧算变化量）
    scaled = _resize_all(out_frames, options.size, options.resample)
    durations = _frame_durations(scaled, options)

    # 多格图随产物一起留着：没有它就无法"改切帧"重出而不重新生成
    save_frame_sheet(sheet, output_dir)

    result = MotionGifResult(
        frames=len(scaled),
        cell_size=cell_size,
        output_size=scaled[0].size,
        frame_durations=durations,
    )

    # 6. GIF：单一共享调色板，超预算沿阶梯降档。
    # 传入**未缩放**的原始帧，由体积阶梯自己决定每档尺寸——
    # 直接传 scaled 会让阶梯无法降尺寸（scaled 已经是定好的成品尺寸）。
    gif_path = output_dir / "animation.gif"
    final_bytes, used_colors, used_size = _write_gif_within_budget(
        out_frames, durations, gif_path, options
    )
    result.gif_path = gif_path
    result.gif_kb = final_bytes / 1024
    result.gif_colors = used_colors
    # 体积阶梯可能降过档，最终 GIF 尺寸以实际写出的为准
    result.output_size = Image.open(gif_path).size

    if write_webp:
        webp_path = output_dir / "animation.webp"
        _export_webp(scaled, webp_path, durations, options)
        result.webp_path = webp_path
        result.webp_kb = webp_path.stat().st_size / 1024

    if write_mp4:
        mp4_path = output_dir / "animation.mp4"
        reason = await _export_mp4(scaled, mp4_path, options.fps)
        if reason:
            result.mp4_skipped_reason = reason
        else:
            result.mp4_path = mp4_path
            result.mp4_kb = mp4_path.stat().st_size / 1024

    # 产物版本指纹：**必须在所有文件写完之后**算，否则拿到的还是旧指纹。
    # 前端用它拼 `?v=<revision>`，避免浏览器继续用被覆写的旧图。
    result.revision = output_revision(result.gif_path, result.webp_path, result.mp4_path)

    logger.info(
        "[motion-gif] composed frames=%s size=%s gif=%.0fKB webp=%.0fKB rev=%s",
        result.frames,
        result.output_size,
        result.gif_kb,
        result.webp_kb,
        result.revision,
    )
    return result


def save_frame_sheet(sheet: Image.Image, output_dir: Path) -> Path:
    """保存多格图本身。

    它是动图产物的**附属数据**：成品要能"改切帧重出"就必须留着原图，
    而多格图本身也是有价值的素材（可被其它功能按 format 取用）。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "framesheet.png"
    sheet.convert("RGB").save(path, format="PNG")
    return path


# ---------------------------------------------------------------------------
# 内部实现
# ---------------------------------------------------------------------------


def _build_loop(frames: list[Image.Image], loop: LoopMode) -> list[Image.Image]:
    """按循环方式拼帧序列。

    ``pingpong``：16 帧只覆盖单程角度，正放完镜像回退才无缝（16 -> 30）。
    不能用自动模式——旋转会被判为"姿态变化"，而半程补缝只在纯平移时生效。
    """
    if loop == "pingpong":
        return frames + frames[-2:0:-1]
    return list(frames)


def _resize_all(
    frames: Sequence[Image.Image], long_edge: int, resample: str
) -> list[Image.Image]:
    """把所有帧缩放成**同一尺寸**（GIF 格式要求各帧等大）。

    ⚠️ 拖过分割线之后各格尺寸本来就不同（实测 378px 与 134px 并存），
    所以这里不能假设"所有帧同尺寸"。

    画布按**出现次数最多的那个尺寸**（众数）决定，而不是第一帧：
    - 用第一帧：若第一格恰好是被拖窄的那列，整条 GIF 都会按窄画布做，其余帧被压扁；
    - 用众数：多数格维持原样，只有少数被拖过的格被缩放进画布（可能留边）。

    缩放而非补边，是因为**动图里各帧不一致的留边会非常显眼**（一圈色块在跳）；
    缩放至少让画面连续。极端的宽高比差异会让窄帧内容变小，但那是用户
    自己拖出来的取景，应当如实反映。
    """
    if long_edge <= 0:
        raise ValueError("size 必须为正整数")
    filter_mode = Image.NEAREST if resample == "nearest" else Image.LANCZOS

    # 众数尺寸（并列时取面积最大的那个，避免选中被拖窄的极端值）
    counts: dict[tuple[int, int], int] = {}
    for f in frames:
        counts[f.size] = counts.get(f.size, 0) + 1
    base_w, base_h = max(counts, key=lambda s: (counts[s], s[0] * s[1]))

    scale = long_edge / max(base_w, base_h)
    size = (max(1, round(base_w * scale)), max(1, round(base_h * scale)))
    # 尺寸一致的帧直接返回（不重采样，避免无谓的糊化）
    return [f if f.size == size else f.resize(size, filter_mode) for f in frames]


def _frame_durations(frames: Sequence[Image.Image], options: MotionGifOptions) -> list[int]:
    """每帧停留毫秒。"""
    if options.timing == "even":
        durations = _even_durations(frames, options.frame_ms)
    elif options.timing == "ramp":
        durations = _ramp_durations(len(frames), options.frame_ms)
    else:
        durations = [max(MIN_FRAME_MS, options.frame_ms)] * len(frames)
    return [max(MIN_FRAME_MS, int(d)) for d in durations]


def _ramp_durations(count: int, base_ms: int) -> list[int]:
    """前慢后快：开头停留久、逐渐加速，让观众看清起始画面。"""
    import numpy as np

    hi, lo, curve = 2.6, 0.7, 1.8
    t = np.linspace(0.0, 1.0, count)
    mult = hi + (lo - hi) * (t ** (1.0 / curve))
    return [base_ms * float(m) for m in mult]


def _even_durations(frames: Sequence[Image.Image], base_ms: int) -> list[float]:
    """按每格实际变化量分配时间，追求恒定观感速度。"""
    import numpy as np

    if len(frames) < 2:
        return [float(base_ms)] * len(frames)
    arrs = [np.asarray(f.convert("L"), dtype=np.float32) for f in frames]
    deltas = [float(np.abs(arrs[i] - arrs[i + 1]).mean()) for i in range(len(arrs) - 1)]
    deltas.append(deltas[-1] if deltas else 0.0)
    total = sum(deltas)
    if total <= 0:
        return [float(base_ms)] * len(frames)
    return [base_ms * d / (total / len(deltas)) for d in deltas]


def _quantize(
    frames: Sequence[Image.Image], colors: int, options: MotionGifOptions
) -> list[Image.Image]:
    import numpy as np

    method = Image.MEDIANCUT if options.dither else Image.Quantize.MEDIANCUT
    out: list[Image.Image] = []
    for frame in frames:
        rgba = frame.convert("RGBA")
        if options.transparent:
            # GIF 只有 1-bit 透明：用 alpha<=128 二值化。
            # 半透明柔边会被切硬——这是 GIF 格式的硬限制，所以透明素材必须同时给 WebP。
            quantized = Image.new("RGB", rgba.size, (255, 255, 255)).quantize(
                colors=colors, method=method
            )
            alpha = np.asarray(rgba.split()[-1])
            quantized.paste(colors, mask=Image.fromarray(
                (alpha <= 128).astype("uint8") * 255, "L"))
            out.append(quantized)
        else:
            out.append(rgba.convert("RGB").quantize(colors=colors, method=method))
    return out


def _write_gif_within_budget(
    frames: Sequence[Image.Image],
    durations: Sequence[int],
    path: Path,
    options: MotionGifOptions,
) -> tuple[int, int, int]:
    """写 GIF，必要时沿阶梯降尺寸/色数以满足体积上限。

    阶梯顺序：先降尺寸再降色数。**最低不要跌破约 460px/96 色**——那个档位
    明显发糊，宁可让调用方放宽预算，也不要交付糊的档位。

    每档都从**同一批原始帧**重新缩放，而不是拿上一档的量化结果继续降——
    那样是二次有损，越降越糊。
    """
    ladder: list[tuple[int, int]] = [(options.size, options.colors)]
    if options.max_kb:
        for factor in (0.85, 0.72, 0.6, 0.5):
            for color_count in (192, 128, 96, 64):
                ladder.append((round(options.size * factor), color_count))

    final_bytes = 0
    used_colors = options.colors
    used_size = options.size
    for size, colors in ladder:
        scaled = _resize_all(frames, size, options.resample)
        quantized = _quantize(scaled, colors, options)
        first, *rest = quantized
        first.save(
            path,
            save_all=True,
            append_images=rest,
            duration=list(durations),
            loop=GIF_LOOP_FOREVER,
            optimize=True,
            disposal=2,
        )
        final_bytes = path.stat().st_size
        used_colors = colors
        used_size = size
        if not options.max_kb or final_bytes <= options.max_kb * 1024:
            break
    return final_bytes, used_colors, used_size


def _export_webp(
    frames: Sequence[Image.Image],
    path: Path,
    durations: Sequence[int],
    options: MotionGifOptions,
) -> None:
    """WebP：支持真 alpha、同分辨率下体积远小于 GIF，质量/透明素材首选。

    注意耗时：512px×16 帧透明 WebP 实测可超过 3 分钟，调用方需放进后台任务，
    否则前台超时会把输出管道 SIGTERM 掉且日志全丢。
    """
    first, *rest = frames
    first.save(
        path,
        save_all=True,
        append_images=rest,
        duration=list(durations),
        loop=GIF_LOOP_FOREVER,
        quality=82,
        method=4,
    )


async def _export_mp4(frames: Sequence[Image.Image], path: Path, fps: int) -> str:
    """导出 MP4（广告投放用）。返回空串表示成功，非空为跳过原因。

    MP4 没有 alpha，透明素材导出时会丢透明信息，调用方应对这类素材传
    ``write_mp4=False``——这不是"导出失败"，而是本就不该产出这个格式。
    """
    from app.core.ffmpeg import get_ffmpeg_service

    service = get_ffmpeg_service()
    # 帧序列目录必须与 `images_to_video` 的 pattern 对齐，这里用默认 frame_%04d.jpg
    frames_dir = path.parent / "_mp4_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    try:
        width, height = frames[0].size
        for index, frame in enumerate(frames, 1):
            cropped = frame.convert("RGB")
            if cropped.size != (width, height):
                cropped = cropped.resize((width, height), Image.LANCZOS)
            cropped.save(frames_dir / f"frame_{index:04d}.jpg", format="JPEG", quality=92)
        # 奇数边长由 images_to_video 的 -vf scale=trunc(iw/2)*2 处理，这里不必再夹
        await service.images_to_video(
            frames_dir=frames_dir,
            output_path=path,
            fps=max(1, fps),
        )
    except Exception as exc:  # noqa: BLE001 - MP4 是可选产物，不该让 GIF 整单失败
        logger.warning("[motion-gif] MP4 导出失败: %s", exc)
        return f"MP4 导出异常：{exc}"
    finally:
        for leftover in frames_dir.glob("*.jpg"):
            leftover.unlink(missing_ok=True)
        try:
            frames_dir.rmdir()
        except OSError:
            pass
    return ""
