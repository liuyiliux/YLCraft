"""显性（视觉可见）水印去除 —— 面向图片与视频素材。

与 `service.py`（隐形 Unicode / 文件元数据清理）、`deep_watermark.py`（只读合成水印检测）互补：
本模块处理的是**画面上肉眼可见的水印**（角落 logo、半透明文字、台标等），目的是在短剧等
成片场景里去除影响观感的水印，不修改源文件、不覆盖原资产，总是生成带 `derived_from` 血缘的派生副本。

实现基于系统 ffmpeg 滤镜（无 GPU / 无 OpenCV / 纯 CPU，确定且可复现）：

- `delogo`：用 logo 区域周围像素插值填充。适合静态、不透明、边界清晰的角落 logo / 文字水印。
  注意 delogo 会插值填充整个方框区域，若水印横跨大面积文字，插值可能产生轻微模糊。
- `blur`：对目标区域做高斯模糊（图片用 PIL `GaussianBlur`；视频退化为 delogo 插值）。适合半透明、
  大面积、动态水印，保留画面内容但让水印不再可读。
- `crop`：从画面边缘直接裁掉水印所在的行/列。适合水印固定在画面边缘、裁掉不影响主体的场景。

区域指定两种方式：
- 预设角落：`corner` ∈ {top_left, top_right, bottom_left, bottom_right, top, bottom, center}，可选 `inset` 边距
- 自定义框：`x, y, w, h`（像素）

能力边界（同 `deep_watermark.py`）：本模块只做“视觉水印”的去除，**绝不宣称**能移除像素/波形
隐写水印（合成水印检测见 `deep_watermark.py`），也不清理文件元数据（见 `service.py`）。
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".avif"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}

# 预设角落 → 相对画面比例（x/y 起点、宽高比），inset 为与边缘的边距。
_CORNERS: dict[str, dict[str, Any]] = {
    "top_left": {"x_ratio": 0.0, "y_ratio": 0.0, "w_ratio": 0.25, "h_ratio": 0.12},
    "top_right": {"x_ratio": 0.75, "y_ratio": 0.0, "w_ratio": 0.25, "h_ratio": 0.12},
    "bottom_left": {"x_ratio": 0.0, "y_ratio": 0.88, "w_ratio": 0.25, "h_ratio": 0.12},
    "bottom_right": {"x_ratio": 0.75, "y_ratio": 0.88, "w_ratio": 0.25, "h_ratio": 0.12},
    "top": {"x_ratio": 0.25, "y_ratio": 0.0, "w_ratio": 0.5, "h_ratio": 0.1},
    "bottom": {"x_ratio": 0.25, "y_ratio": 0.9, "w_ratio": 0.5, "h_ratio": 0.1},
    "center": {"x_ratio": 0.375, "y_ratio": 0.4, "w_ratio": 0.25, "h_ratio": 0.15},
}


@dataclass
class WatermarkRegion:
    """水印区域（像素坐标，已在画面内）。"""

    x: int
    y: int
    w: int
    h: int

    def clamp(self, width: int, height: int) -> "WatermarkRegion":
        x = max(0, min(self.x, width - 1))
        y = max(0, min(self.y, height - 1))
        w = max(4, min(self.w, width - x))
        h = max(4, min(self.h, height - y))
        return WatermarkRegion(x=x, y=y, w=w, h=h)

    def asdict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


@dataclass
class VisualWatermarkResult:
    """一次显性水印去除的结果。"""

    supported: bool
    media_kind: str  # image / video / unsupported
    method: str
    region: dict[str, int]
    output_path: str
    notes: list[str]


def _probe_dimensions(path: Path) -> tuple[int, int]:
    """用 ffprobe 读取宽高（图片和视频通用）。"""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0:s=x",
        str(path),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
        if out:
            w, h = out.split("x")
            return int(w), int(h)
    except Exception:  # noqa: BLE001
        pass
    return 640, 360


def _resolve_region(
    region: dict[str, Any] | None, width: int, height: int
) -> WatermarkRegion:
    """把请求里的区域解析为像素坐标并 clamp 到画面内。

    delogo 滤镜需要 logo 区域四周都有邻域用于插值，因此区域必须离画面边缘
    至少一个像素（这里统一在 clamp 后强制收缩 2px 保险边距）。
    """
    region = region or {}
    if region.get("x") is not None and region.get("y") is not None:
        r = WatermarkRegion(
            x=int(region["x"]), y=int(region["y"]),
            w=int(region.get("w") or 120), h=int(region.get("h") or 60),
        ).clamp(width, height)
    else:
        corner = region.get("corner") or "top_right"
        spec = _CORNERS.get(corner, _CORNERS["top_right"])
        inset = int(region.get("inset") or 0)
        x = int(spec["x_ratio"] * width) + inset
        y = int(spec["y_ratio"] * height) + inset
        w = int(spec["w_ratio"] * width)
        h = int(spec["h_ratio"] * height)
        r = WatermarkRegion(x=x, y=y, w=w, h=h).clamp(width, height)
    # 为 delogo 保留边缘邻域：区域四周至少留 4px。
    edge = 4
    x = max(edge, r.x)
    y = max(edge, r.y)
    w = max(4, min(r.w, width - x - edge))
    h = max(4, min(r.h, height - y - edge))
    return WatermarkRegion(x=x, y=y, w=w, h=h).clamp(width, height)


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _build_vf(method: str, r: WatermarkRegion) -> str:
    """按方法构建 ffmpeg 视频滤镜串（视频专用）。"""
    method = method or "delogo"
    if method == "delogo":
        return f"delogo=x={r.x}:y={r.y}:w={r.w}:h={r.h}"
    if method == "crop":
        # 裁掉水印所在矩形覆盖的整条边（取较宽/较高方向），保证矩形裁切合法。
        if r.h >= r.w:
            return f"crop=in_w:in_h-{r.h}:0:in_h-{r.h}"  # 裁底部整行
        return f"crop=in_w-{r.w}:in_h:{r.w}:0"  # 裁右侧整列
    raise ValueError(f"未知去水印方法: {method}")


def remove_visual_watermark(
    source_path: str | Path,
    *,
    region: dict[str, Any] | None = None,
    method: str = "delogo",
) -> VisualWatermarkResult:
    """对图片/视频去除显性可见水印，返回派生文件路径。源文件不被修改。

    返回结果里的 `output_path` 是刚生成的临时派生文件，由调用方负责落到正式存储并入库。
    """
    source = Path(source_path)
    suffix = source.suffix.lower()
    guessed = __import__("mimetypes").guess_type(source.name)[0] or ""
    method = (method or "delogo").lower()

    if method not in {"delogo", "blur", "crop"}:
        return VisualWatermarkResult(
            supported=False, media_kind="unsupported", method=method,
            region={}, output_path="", notes=[f"未知去水印方法: {method}"],
        )

    if suffix in IMAGE_SUFFIXES or guessed.startswith("image/"):
        media_kind = "image"
    elif suffix in VIDEO_SUFFIXES or guessed.startswith("video/"):
        media_kind = "video"
    else:
        return VisualWatermarkResult(
            supported=False, media_kind="unsupported", method=method,
            region={}, output_path="", notes=["当前格式暂不支持显性水印去除"],
        )

    if not _ffmpeg_available():
        return VisualWatermarkResult(
            supported=False, media_kind=media_kind, method=method,
            region={}, output_path="", notes=["系统缺少 ffmpeg/ffprobe，无法去除显性水印"],
        )

    width, height = _probe_dimensions(source)
    r = _resolve_region(region, width, height)
    out_path = source.with_name(f"{source.stem}-nowm{source.suffix}")

    # 图片的 blur 方法用 PIL 对目标区域做高斯模糊（比 ffmpeg 滤镜组合更稳定）；
    # 视频的 blur 方法退化为 delogo（区域插值，同样消除可读水印）。
    if media_kind == "image" and method == "blur":
        ok, err = _image_blur(source, r, out_path)
        if not ok:
            return VisualWatermarkResult(
                supported=True, media_kind=media_kind, method=method,
                region=r.asdict(), output_path="", notes=[f"去水印处理失败: {err}"],
            )
        notes = [
            f"用 PIL 高斯模糊去除 image 显性水印，区域 {r.asdict()}，源文件未被修改。",
            "本能力只处理肉眼可见的视觉水印；像素/波形隐写水印（合成水印）见 deep-watermark 只读检测。",
        ]
        return VisualWatermarkResult(
            supported=True, media_kind=media_kind, method=method,
            region=r.asdict(), output_path=str(out_path), notes=notes,
        )

    video_method = "delogo" if (media_kind == "video" and method == "blur") else method
    vf = _build_vf(video_method, r)

    try:
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(source),
            "-vf", vf,
        ]
        if media_kind == "image":
            # 图片也按视频滤镜处理（ffmpeg 把单帧当视频），输出到对应格式
            cmd += ["-frames:v", "1"]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"] if media_kind == "video" else ["-q:v", "2"]
        cmd += [str(out_path)]
        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=600)
    except Exception as exc:  # noqa: BLE001
        return VisualWatermarkResult(
            supported=True, media_kind=media_kind, method=method,
            region=r.asdict(), output_path="", notes=[f"去水印处理失败: {exc}"],
        )

    notes = [
        f"用 ffmpeg {video_method} 滤镜去除 {media_kind} 显性水印，区域 {r.asdict()}，源文件未被修改。",
        "本能力只处理肉眼可见的视觉水印；像素/波形隐写水印（合成水印）见 deep-watermark 只读检测。",
    ]
    return VisualWatermarkResult(
        supported=True,
        media_kind=media_kind,
        method=method,
        region=r.asdict(),
        output_path=str(out_path),
        notes=notes,
    )


def _image_blur(source: Path, r: WatermarkRegion, out_path: Path) -> tuple[bool, str]:
    """用 PIL 对图片目标区域做高斯模糊，保留其余画面。"""
    try:
        from PIL import Image, ImageFilter

        with Image.open(source) as img:
            img = img.convert("RGB")
            box = (r.x, r.y, r.x + r.w, r.y + r.h)
            region = img.crop(box).filter(ImageFilter.GaussianBlur(radius=12))
            img.paste(region, box)
            img.save(out_path, quality=92)
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def remove_visual_watermark_dict(
    source_path: str | Path,
    *,
    region: dict[str, Any] | None = None,
    method: str = "delogo",
) -> dict[str, Any]:
    return asdict(
        remove_visual_watermark(source_path, region=region, method=method)
    )
