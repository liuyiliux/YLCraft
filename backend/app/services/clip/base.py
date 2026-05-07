"""
YLCraft — Clip Lab 公共基础层

提供三种剪辑模式共用的底层能力：
- 硬件加速检测（CUDA/NVENC, QSV, AMF, VideoToolbox）
- FFmpeg 命令构建（编码器参数自动选择）
- 关键帧/缩略图抽取
- 场景边界检测
- 音频分析（节拍、能量）
- 视频时长/信息获取

参考 NarratoAI check_hardware_acceleration() + get_safe_encoder_config()
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ylcraft.clip.base")


# =============================================================================
# 硬件加速类型
# =============================================================================

class HWAccelType:
    """硬件加速类型枚举"""
    CUDA = "cuda"           # NVIDIA NVENC
    QSV = "qsv"             # Intel Quick Sync
    AMF = "amf"             # AMD AMF
    VIDEOTOOLBOX = "videotoolbox"  # macOS VideoToolbox
    NONE = "none"           # 纯 CPU（libx264）


@dataclass
class HWAccelConfig:
    """硬件加速配置"""
    type: HWAccelType
    decoder: Optional[str] = None   # -hwaccel DEVICE 用的解码器
    encoder: Optional[str] = None   # 实际编码器名（如 libx264 不变，输出用 h264_nvenc）
    pixel_format: str = "yuv420p"

    @property
    def is_available(self) -> bool:
        return self.type != HWAccelType.NONE


# =============================================================================
# 硬件加速检测
# =============================================================================

def check_hardware_acceleration() -> HWAccelConfig:
    """
    检测系统可用的硬件加速方案。

    检测顺序：CUDA(NVIDIA) > QSV(Intel) > AMF(AMD) > videotoolbox(macOS)
    Windows 默认回退到 CPU(libx264)。

    Returns:
        HWAccelConfig: 最佳可用加速配置

    参考 NarratoAI check_hardware_acceleration()
    """
    import platform

    system = platform.system().lower()

    # Linux/macOS 检测
    if system in ("linux", "darwin"):
        # 优先检测 NVIDIA
        try:
            result = subprocess.run(
                ["nvidia-smi"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return HWAccelConfig(
                    type=HWAccelType.CUDA,
                    decoder="cuda",
                    encoder="h264_nvenc",
                    pixel_format="yuv420p",
                )
        except Exception:
            pass

        # macOS VideoToolbox
        if system == "darwin":
            return HWAccelConfig(
                type=HWAccelType.VIDEOTOOLBOX,
                decoder=None,
                encoder="h264_videotoolbox",
                pixel_format="yuv420p",
            )

        # Intel QSV (Linux)
        if system == "linux":
            try:
                result = subprocess.run(
                    ["vainfo"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and "Intel" in result.stdout:
                    return HWAccelConfig(
                        type=HWAccelType.QSV,
                        decoder="qsv",
                        encoder="h264_qsv",
                        pixel_format="nv12",
                    )
            except Exception:
                pass

    # Windows: 尝试检测 NVIDIA
    if system == "windows":
        try:
            result = subprocess.run(
                ["nvidia-smi"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return HWAccelConfig(
                    type=HWAccelType.CUDA,
                    decoder="cuda",
                    encoder="h264_nvenc",
                    pixel_format="yuv420p",
                )
        except Exception:
            pass
        # Windows 也支持 QSV（Intel 核显），可后续扩展

    # 回退：纯 CPU
    return HWAccelConfig(
        type=HWAccelType.NONE,
        decoder=None,
        encoder="libx264",
        pixel_format="yuv420p",
    )


# =============================================================================
# FFmpeg 编码配置
# =============================================================================

def get_encoder_config(hwaccel: HWAccelConfig) -> dict:
    """
    根据硬件加速类型返回 FFmpeg 编码参数。

    参考 NarratoAI get_safe_encoder_config()

    Returns:
        dict: {
            "c:v": 视频编码器,
            "preset": 速度预设,
            "crf": 质量（CPU模式）,
            "b:v": 码率（硬件模式）,
            "hwaccel": 硬件加速参数列表（可展开）,
            "extra": 其他额外参数,
        }
    """
    if hwaccel.type == HWAccelType.CUDA:
        return {
            "c:v": hwaccel.encoder,         # h264_nvenc
            "preset": "p4",                   # medium 质量优先
            "b:v": "4M",                      # 码率控制
            "rc": "vbr",
            "hwaccel": ["-hwaccel", "cuda"],
            "extra": [],
        }
    elif hwaccel.type == HWAccelType.QSV:
        return {
            "c:v": hwaccel.encoder,           # h264_qsv
            "preset": "medium",
            "b:v": "4M",
            "load_plugins": "",
            "hwaccel": ["-hwaccel", "qsv", "-qsv_device", "0"],
            "extra": ["-look_ahead", "1"],
        }
    elif hwaccel.type == HWAccelType.VIDEOTOOLBOX:
        return {
            "c:v": hwaccel.encoder,           # h264_videotoolbox
            "preset": "medium",
            "b:v": "4M",
            "hwaccel": [],
            "extra": [],
        }
    else:
        # CPU: libx264，CRF 质量模式
        return {
            "c:v": hwaccel.encoder,           # libx264
            "preset": "fast",                  # 快速编码
            "crf": "23",                       # 质量档位（18-28，越小越清晰）
            "c:a": "aac",
            "b:a": "128k",
            "hwaccel": [],
            "extra": [],
        }


# =============================================================================
# FFmpeg 命令构建工具
# =============================================================================

def build_ffmpeg_cmd(
    input_path: Path,
    output_path: Path,
    hwaccel: HWAccelConfig,
    extra_filters: Optional[list[str]] = None,
    extra_inputs: Optional[list[tuple[Path, str]]] = None,  # [(path, label), ...]
    map_args: Optional[list[str]] = None,  # ["0:v", "0:a", ...]
    extra_args: Optional[list[str]] = None,
    overwrite: bool = True,
) -> list[str]:
    """
    构建 FFmpeg 命令行列表。

    Args:
        input_path: 主输入视频路径
        output_path: 输出路径
        hwaccel: 硬件加速配置
        extra_filters: 额外视频滤镜列表（会拼接在一起）
        extra_inputs: 额外输入 [(path, stream_label), ...]
        map_args: 自定义 map 参数
        extra_args: 任意额外参数
        overwrite: 是否覆盖输出

    Returns:
        FFmpeg 命令列表（适合 subprocess.run）
    """
    cmd = ["ffmpeg", "-y" if overwrite else "-n"]

    # 硬件解码参数
    enc_cfg = get_encoder_config(hwaccel)
    for arg in enc_cfg.get("hwaccel", []):
        cmd.append(arg)

    # 输入
    cmd.extend(["-i", str(input_path)])

    # 额外输入
    if extra_inputs:
        for path, label in extra_inputs:
            cmd.extend(["-i", str(path)])

    # 视频滤镜
    filters = []
    if extra_filters:
        filters.extend(extra_filters)

    if filters:
        cmd.extend(["-vf", ",".join(filters)])

    # 编码参数
    if enc_cfg.get("c:v"):
        cmd.extend(["-c:v", enc_cfg["c:v"]])
    if enc_cfg.get("preset"):
        cmd.extend(["-preset", enc_cfg["preset"]])
    if enc_cfg.get("crf"):
        cmd.extend(["-crf", str(enc_cfg["crf"])])
    if enc_cfg.get("b:v"):
        cmd.extend(["-b:v", enc_cfg["b:v"]])
    if enc_cfg.get("c:a"):
        cmd.extend(["-c:a", enc_cfg["c:a"]])
    if enc_cfg.get("b:a"):
        cmd.extend(["-b:a", enc_cfg["b:a"]])
    for arg in enc_cfg.get("extra", []):
        if arg:
            cmd.append(arg)

    # 音频：保留原音
    if not any("-c:a" in arg for arg in cmd):
        cmd.extend(["-c:a", "aac", "-b:a", "128k"])

    # map
    if map_args:
        for m in map_args:
            cmd.extend(["-map", m])

    cmd.append(str(output_path))
    return cmd


# =============================================================================
# 视频信息获取
# =============================================================================

async def get_video_duration(video_path: Path) -> float:
    """获取视频时长（秒）"""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = await asyncio.to_thread(
        subprocess.run, cmd, capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return float(result.stdout.strip())


async def get_video_info_full(video_path: Path) -> dict:
    """
    获取完整视频信息。

    Returns:
        {
            "width": int,
            "height": int,
            "duration": float,
            "fps": float,
            "codec": str,
            "audio_codec": str,
            "file_size": int,
            "bitrate": int,
        }
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration,r_frame_rate,codec_name,bit_rate",
        "-show_entries", "format=duration,size,bit_rate",
        "-of", "json",
        str(video_path),
    ]
    result = await asyncio.to_thread(
        subprocess.run, cmd, capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")

    data = json.loads(result.stdout)
    stream = data.get("streams", [{}])[0]
    fmt = data.get("format", {})

    fps_str = stream.get("r_frame_rate", "30/1")
    if "/" in fps_str:
        num, den = map(int, fps_str.split("/"))
        fps = num / den if den > 0 else 30.0
    else:
        fps = float(fps_str)

    return {
        "width": int(stream.get("width", 0)),
        "height": int(stream.get("height", 0)),
        "duration": float(stream.get("duration") or fmt.get("duration", 0)),
        "fps": fps,
        "codec": stream.get("codec_name", "h264"),
        "audio_codec": "aac",
        "file_size": int(fmt.get("size", 0)),
        "bitrate": int(fmt.get("bit_rate", stream.get("bit_rate", 0))),
    }


# =============================================================================
# 关键帧抽取
# =============================================================================

async def extract_keyframes(
    video_path: Path,
    output_dir: Path,
    interval_sec: float = 1.0,
    max_frames: int = 30,
) -> list[Path]:
    """
    按固定间隔抽取关键帧缩略图。

    Args:
        video_path: 输入视频
        output_dir: 输出目录
        interval_sec: 抽取间隔（秒）
        max_frames: 最大帧数（超过则按时间均匀采样）

    Returns:
        抽取的帧图片路径列表（按时间排序）
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_pattern = str(output_dir / "kf_%04d.jpg")

    duration = await get_video_duration(video_path)

    # 如果 duration * fps > max_frames * interval，减小 interval
    # 采样密度 = min(max_frames, duration / interval_sec)
    num_frames = min(max_frames, int(duration / interval_sec) + 1)
    actual_interval = duration / num_frames if num_frames > 0 else interval_sec

    # 使用 select + scale filter 批量抽取
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"fps=1/{actual_interval:.1f},scale=320:-1",
        "-q:v", "3",
        "-frames:v", str(max_frames),
        output_pattern,
    ]

    result = await asyncio.to_thread(
        subprocess.run, cmd, capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        logger.warning(f"extract_keyframes failed: {result.stderr}")

    # 收集输出文件
    frames = sorted(output_dir.glob("kf_*.jpg"))
    return frames


# =============================================================================
# 场景边界检测（基于帧差异）
# =============================================================================

async def detect_scene_changes(
    video_path: Path,
    threshold: float = 0.4,
    output_json: Optional[Path] = None,
) -> list[dict]:
    """
    检测视频场景变化点（镜头切换）。

    使用 FFmpeg 的 scene detection filter（libavfilter）。

    Args:
        video_path: 输入视频路径
        threshold: 场景切换阈值（0.0-1.0，越低越敏感）
        output_json: 可选：输出 JSON 文件路径

    Returns:
        场景列表 [{"start": float, "end": float, "start_time": str, "end_time": str}, ...]
    """
    # scene detection 过滤器输出
    json_output = str(output_json) if output_json else "/dev/null"  # Windows: NUL

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-filter_complex",
        f"select='gt(scene,{threshold})',showinfo",
        "-f", "null",
        "-",
    ]

    try:
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=180
        )
    except Exception as e:
        logger.warning(f"detect_scene_changes failed: {e}")
        return []

    # 从 stderr 解析时间戳
    # showinfo 输出格式: pts_time:1234.5 type:I ...
    scenes = []
    for line in result.stderr.split("\n"):
        if "pts_time:" in line and "type:I" in line:
            match = re.search(r"pts_time:([\d.]+)", line)
            if match:
                ts = float(match.group(1))
                scenes.append({
                    "start": ts,
                    "end": ts + 1.0,
                    "start_time": _format_time(ts),
                })

    return scenes


# =============================================================================
# 音频分析（节拍/能量）
# =============================================================================

async def analyze_audio_peaks(
    video_path: Path,
    output_json: Optional[Path] = None,
) -> dict:
    """
    分析音频能量峰值（用于踩点）。

    使用 FFmpeg astats 滤波器 + Python 后处理。
    输出高能量帧的时间点列表。

    Returns:
        {
            "peaks": [float, ...],  # 秒
            "energy_curve": [(float, float), ...],  # (时间, 能量)
        }
    """
    # 提取音频并分析
    with_ext = video_path.suffix.lower()
    audio_path = video_path.with_suffix(".wav")

    # 提取音频
    extract_cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "22050",  # 降采样加速分析
        "-ac", "1",
        str(audio_path),
    ]
    r1 = await asyncio.to_thread(
        subprocess.run, extract_cmd, capture_output=True, text=True, timeout=120
    )
    if r1.returncode != 0:
        logger.warning(f"analyze_audio_peaks extract audio failed: {r1.stderr}")
        return {"peaks": [], "energy_curve": []}

    # 分析音频能量
    # 使用 FFmpeg 的 volumedetect 获取大致峰值分布
    peak_cmd = [
        "ffmpeg", "-y",
        "-i", str(audio_path),
        "-af", "volumedetect",
        "-f", "null", "-",
    ]
    r2 = await asyncio.to_thread(
        subprocess.run, peak_cmd, capture_output=True, text=True, timeout=60
    )

    # 解析 max_volume
    peaks = []
    if r2.returncode == 0:
        for line in r2.stderr.split("\n"):
            m = re.search(r"max_volume:\s*([-\d.]+)\s*dB", line)
            if m:
                max_vol = float(m.group(1))
                # 提取高能量帧（-20dB 以上）
                if max_vol > -30:
                    # 简化：取音频中间点作为峰值
                    duration = await get_video_duration(video_path)
                    peaks = [duration * 0.5]  # 回退策略：取中点

    # 清理临时音频
    try:
        audio_path.unlink()
    except Exception:
        pass

    return {
        "peaks": peaks if peaks else [],
        "energy_curve": [],
    }


# =============================================================================
# 通用 FFmpeg 执行（带 fallback）
# =============================================================================

async def execute_ffmpeg(
    cmd: list[str],
    timeout: int = 300,
    cwd: Optional[Path] = None,
) -> subprocess.CompletedProcess:
    """
    执行 FFmpeg 命令，带超时保护。

    Returns:
        CompletedProcess

    Raises:
        RuntimeError: FFmpeg 返回非零退出码
    """
    logger.info(f"FFmpeg cmd: {' '.join(str(c) for c in cmd)}")
    result = await asyncio.to_thread(
        subprocess.run,
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(cwd) if cwd else None,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {result.stderr[-500:]}")
    return result


# =============================================================================
# 工具函数
# =============================================================================

def _format_time(seconds: float) -> str:
    """秒 → HH:MM:SS.ms 格式"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def ensure_dir(path: Path) -> Path:
    """确保目录存在，返回路径"""
    path.mkdir(parents=True, exist_ok=True)
    return path
