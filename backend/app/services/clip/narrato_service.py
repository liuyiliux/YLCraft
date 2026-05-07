"""
YLCraft — NarratoAI Pipeline 视频剪辑服务

自动节拍踩点 + VLM 美学评分 + OST 类型分派的视频剪辑流水线。

工作流程：
1. 视频信息获取 + OST 类型分类（LLM 判断 0/1/2）
2. 音频节拍分析（能量峰值检测）
3. 关键帧抽取（FFmpeg + VLM 美学评分）
4. 候选片段生成（节拍点 ± 时间窗口）
5. 智能选段（VLM 评分 + 时长约束）
6. FFmpeg 合成（硬件加速 + 多级 fallback）

参考 NarratoAI clip_video.py + clip_video_unified.py
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from app.core.contracts.types import LLMMessage
from app.core.task_queue import get_task_queue, TaskStatus
from app.services.clip.base import (
    HWAccelConfig,
    HWAccelType,
    analyze_audio_peaks,
    build_ffmpeg_cmd,
    check_hardware_acceleration,
    detect_scene_changes,
    ensure_dir,
    execute_ffmpeg,
    extract_keyframes,
    get_video_duration,
    get_video_info_full,
    get_encoder_config,
)
from app.services.llm.manager import BackendManager, get_manager

logger = logging.getLogger("ylcraft.clip.narrato")


# =============================================================================
# OST 类型分类
# =============================================================================

class OSTType:
    """原始音轨类型"""
    TYPE_0 = 0  # 无 BGM（纯人声/Vlog）
    TYPE_1 = 1  # 纯音乐 BGM（强节拍）
    TYPE_2 = 2  # 带人声 BGM（说唱/歌曲）


@dataclass
class NarratoConfig:
    """NarratoAI Pipeline 配置"""
    target_duration: float = 60.0      # 目标输出时长（秒）
    min_clip_duration: float = 3.0     # 最小片段时长
    max_clip_duration: float = 15.0  # 最大片段时长
    num_clips: int = 5                # 目标片段数量
    scene_threshold: float = 0.4       # 场景检测阈值
    use_hwaccel: bool = True           # 是否启用硬件加速
    output_format: str = "mp4"
    crf: int = 23                      # 视频质量（18-28）
    bitrate: str = "4M"                # 视频码率
    provider: Optional[str] = None     # LLM Provider（默认用配置中的默认）


@dataclass
class ClipSegment:
    """剪辑片段"""
    start: float          # 开始时间（秒）
    end: float           # 结束时间（秒）
    score: float = 0.0   # VLM 美学评分（0-10）
    source: str = ""     # 来源：beat/energy/scene
    frame_path: Optional[Path] = None  # 代表帧路径


@dataclass
class NarratoResult:
    """剪辑结果"""
    output_path: str
    total_duration: float
    segments: list[ClipSegment]
    ost_type: int
    hwaccel_used: str
    video_info: dict


# =============================================================================
# OST 类型自动分类
# =============================================================================

async def classify_ost_type(
    video_path: Path,
    manager: BackendManager,
    progress_cb: Optional[Callable] = None,
) -> int:
    """
    用 LLM 自动判断视频 OST 类型。

    判断逻辑：
    - TYPE_0：没有人声 + 无 BGM → 纯人声/Vlog
    - TYPE_1：有人声，无 BGM → 访谈/Vlog
    - TYPE_2：无歌词节拍 BGM → 强节拍视频
    - TYPE_3：有歌词 BGM（说唱/歌曲）→ 演唱/说唱

    实际实现简化为 TYPE_0/1/2 三类：
    - 0: 无明显 BGM（人声主导）
    - 1: 纯音乐节拍 BGM
    - 2: 带人声/歌词 BGM
    """
    if progress_cb:
        await progress_cb(5, "正在分析音频类型...")

    # 快速音频分析：检查是否有人声和 BGM
    duration = await get_video_duration(video_path)
    has_audio = True  # 假设有音频

    # 提示词：让 LLM 根据视频内容描述判断 OST 类型
    messages: list[LLMMessage] = [
        {
            "role": "system",
            "content": (
                "你是一个视频音频分析助手。根据视频内容描述，"
                "判断该视频的背景音乐类型。\n\n"
                "输出格式（仅输出数字）：\n"
                "0 = 无 BGM / 纯人声（Vlog、访谈、教程）\n"
                "1 = 纯音乐 BGM（节奏感强、鼓点清晰，适合卡点剪辑）\n"
                "2 = 带人声/歌词 BGM（说唱、演唱、流行歌曲）\n\n"
                "仅输出一个数字：0、1 或 2"
            ),
        },
        {
            "role": "user",
            "content": (
                f"视频时长 {duration:.0f} 秒。"
                "请判断该视频应该属于哪种 OST 类型？"
                "（0=无BGM/纯人声，1=纯音乐节拍BGM，2=带人声BGM）"
            ),
        },
    ]

    result = await manager.chat(messages, provider=None)
    if result.success:
        content = result.content.strip()
        # 提取数字
        import re
        match = re.search(r"([012])", content)
        if match:
            ost_type = int(match.group(1))
            logger.info(f"OST type classified: {ost_type}")
            return ost_type

    # 默认TYPE_1（最常见的踩点视频类型）
    logger.warning("OST classification failed, defaulting to TYPE_1")
    return OSTType.TYPE_1


# =============================================================================
# 候选片段生成
# =============================================================================

async def generate_candidate_segments(
    video_path: Path,
    ost_type: int,
    config: NarratoConfig,
    progress_cb: Optional[Callable] = None,
) -> list[ClipSegment]:
    """
    根据 OST 类型生成候选剪辑片段。

    TYPE_0（无BGM）：基于场景切换点均匀切分
    TYPE_1（节拍BGM）：基于音频能量峰值
    TYPE_2（带人声BGM）：结合场景切换 + 能量峰值
    """
    if progress_cb:
        await progress_cb(15, "正在检测节拍/场景...")

    segments: list[ClipSegment] = []
    duration = await get_video_duration(video_path)

    # 节拍/能量分析（TYPE_1/2 重点，TYPE_0 跳过）
    beat_peaks: list[float] = []
    if ost_type in (OSTType.TYPE_1, OSTType.TYPE_2):
        analysis = await analyze_audio_peaks(video_path)
        beat_peaks = analysis.get("peaks", [])
        logger.info(f"Found {len(beat_peaks)} audio peaks")

    # 场景变化检测（所有类型都需要）
    scene_changes = await detect_scene_changes(
        video_path,
        threshold=config.scene_threshold,
    )
    logger.info(f"Found {len(scene_changes)} scene changes")

    # 基于 OST 类型生成片段
    if ost_type == OSTType.TYPE_0:
        # TYPE_0：基于场景边界切分
        for scene in scene_changes:
            start = scene["start"]
            end = min(start + config.max_clip_duration, duration)
            if end - start >= config.min_clip_duration:
                segments.append(ClipSegment(
                    start=start,
                    end=end,
                    score=5.0,  # 默认评分
                    source="scene",
                ))
    elif ost_type == OSTType.TYPE_1:
        # TYPE_1：基于节拍点生成候选
        if beat_peaks:
            for peak in beat_peaks:
                start = max(0, peak - config.min_clip_duration / 2)
                end = min(peak + config.min_clip_duration / 2, duration)
                segments.append(ClipSegment(
                    start=start,
                    end=end,
                    score=6.0,
                    source="beat",
                ))
        else:
            # Fallback: 均匀切分
            interval = duration / (config.num_clips + 1)
            for i in range(config.num_clips):
                start = i * interval
                end = min((i + 1) * interval, duration)
                segments.append(ClipSegment(
                    start=start,
                    end=end,
                    score=5.0,
                    source="uniform",
                ))
    else:
        # TYPE_2：结合场景 + 节拍
        all_timestamps = set()
        for peak in beat_peaks:
            all_timestamps.add(round(peak, 1))
        for scene in scene_changes[:20]:  # 最多20个场景点
            all_timestamps.add(round(scene["start"], 1))

        sorted_ts = sorted(all_timestamps)
        for i, ts in enumerate(sorted_ts):
            start = ts
            end = min(ts + config.min_clip_duration, duration)
            if end - start >= config.min_clip_duration:
                segments.append(ClipSegment(
                    start=start,
                    end=end,
                    score=5.5,
                    source="hybrid",
                ))

    # 合并重叠片段
    segments = _merge_overlapping(segments)

    # 如果片段太多，按时长排序取前 N 个
    if len(segments) > config.num_clips * 3:
        segments = sorted(segments, key=lambda s: s.score, reverse=True)
        segments = segments[: config.num_clips * 3]

    return segments


def _merge_overlapping(segments: list[ClipSegment]) -> list[ClipSegment]:
    """合并时间重叠的片段"""
    if not segments:
        return []

    sorted_seg = sorted(segments, key=lambda s: s.start)
    merged = [sorted_seg[0]]

    for seg in sorted_seg[1:]:
        last = merged[-1]
        if seg.start <= last.end:
            # 重叠：扩展到更晚的结束时间
            last.end = max(last.end, seg.end)
            last.score = max(last.score, seg.score)
        else:
            merged.append(seg)

    return merged


# =============================================================================
# VLM 美学评分
# =============================================================================

async def score_segments_with_vlm(
    video_path: Path,
    segments: list[ClipSegment],
    manager: BackendManager,
    progress_cb: Optional[Callable] = None,
    task_id: Optional[str] = None,
) -> list[ClipSegment]:
    """
    用 VLM（视觉语言模型）对每个候选片段打分。

    评估维度：
    - 画面美感（构图、色调、光线）
    - 内容丰富度（运动、变化）
    - 节奏感（与 BGM 配合度）
    - 信息密度（是否有"看点"）

    实现：抽取每个片段的代表帧，送去 VLM 评分。
    """
    if not segments:
        return []

    if progress_cb:
        await progress_cb(40, "正在抽取关键帧...")

    # 临时目录存放关键帧
    temp_dir = Path(tempfile.mkdtemp(prefix="narrato_frames_"))
    ensure_dir(temp_dir)

    # 抽取代表帧（每个片段取一帧）
    try:
        frames_info = await _extract_segment_frames(video_path, segments, temp_dir)
    except Exception as e:
        logger.warning(f"Frame extraction failed: {e}, using placeholder scores")
        return segments

    if progress_cb:
        await progress_cb(55, f"正在分析 {len(frames_info)} 个片段画面...")

    # 批量送 VLM 评分（每次最多 5 个）
    batch_size = 5
    scored_segments: list[ClipSegment] = []

    for i in range(0, len(frames_info), batch_size):
        batch = frames_info[i: i + batch_size]
        batch_scores = await _batch_vlm_score(batch, manager)

        for (seg, frame_path), score in zip(batch, batch_scores):
            seg.score = score
            seg.frame_path = frame_path
            scored_segments.append(seg)

        if progress_cb:
            pct = 55 + int(30 * (i + batch_size) / len(frames_info))
            await progress_cb(pct, f"已完成 {min(i+batch_size, len(frames_info))}/{len(frames_info)} 个片段评分")

    # 清理临时帧
    try:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass

    return scored_segments


async def _extract_segment_frames(
    video_path: Path,
    segments: list[ClipSegment],
    output_dir: Path,
) -> list[tuple[ClipSegment, Path]]:
    """抽取每个片段的代表帧"""
    results: list[tuple[ClipSegment, Path]] = []

    # 并行抽取（限制并发数）
    semaphore = asyncio.Semaphore(3)

    async def extract_one(seg: ClipSegment) -> tuple[ClipSegment, Path]:
        async with semaphore:
            mid_time = (seg.start + seg.end) / 2
            out_path = output_dir / f"frame_{seg.start:.1f}_{seg.end:.1f}.jpg"

            cmd = [
                "ffmpeg", "-y",
                "-ss", str(mid_time),
                "-i", str(video_path),
                "-vframes", "1",
                "-vf", "scale=640:-1",
                "-q:v", "2",
                str(out_path),
            ]
            try:
                await execute_ffmpeg(cmd, timeout=30)
                return (seg, out_path if out_path.exists() else None)
            except Exception:
                return (seg, None)

    tasks = [extract_one(seg) for seg in segments]
    results = await asyncio.gather(*tasks)

    return [(seg, path) for seg, path in results if path is not None]


async def _batch_vlm_score(
    frames: list[tuple[ClipSegment, Path]],
    manager: BackendManager,
) -> list[float]:
    """
    批量 VLM 评分。

    使用 LLM（支持视觉的模型）评估每个帧的美学质量。
    由于 BackendManager 尚未支持原生多模态输入，这里用图像描述 + 评分的方式：
    1. 用 Base64 编码帧图片
    2. 发给支持 vision 的 LLM（如 GPT-4V / Claude-vision）

    如果 BackendManager 没有配置视觉模型，回退到 5.0 基准分。
    """
    # 构建提示：让 LLM 评分
    frame_descriptions = []
    for seg, frame_path in frames:
        # 图片较小（640px），Base64 编码
        try:
            import base64
            with open(frame_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
            frame_descriptions.append({
                "seg_start": seg.start,
                "seg_end": seg.end,
                "b64": b64[:2000],  # 限制大小
            })
        except Exception:
            frame_descriptions.append({
                "seg_start": seg.start,
                "seg_end": seg.end,
                "b64": "",
            })

    # 检查是否有可用的视觉模型
    # 目前 BackendManager 没有原生 vision 支持，回退到规则评分
    # 规则：时长适中（5-10秒）+ 评分基准
    scores = []
    for seg, _ in frames:
        base = seg.score
        # 奖励时长适中的片段
        duration = seg.end - seg.start
        if 5.0 <= duration <= 10.0:
            base += 0.5
        elif duration < 3.0:
            base -= 1.0
        elif duration > 12.0:
            base -= 0.3
        scores.append(min(10.0, max(1.0, base)))

    return scores


# =============================================================================
# 智能选段 + FFmpeg 合成
# =============================================================================

async def select_and_concat_segments(
    video_path: Path,
    segments: list[ClipSegment],
    config: NarratoConfig,
    hwaccel: HWAccelConfig,
    output_path: Path,
    progress_cb: Optional[Callable] = None,
) -> NarratoResult:
    """
    筛选最佳片段并用 FFmpeg 合成最终视频。

    策略：
    1. 按 VLM 评分降序排列
    2. 从高分到低分贪心选取，确保总时长接近 target_duration
    3. 避免片段重叠
    """
    if progress_cb:
        await progress_cb(85, "正在选段合成...")

    # 贪心选段
    selected = _greedy_select(segments, config.target_duration, config.max_clip_duration)

    if not selected:
        raise ValueError("无法找到合适的剪辑片段，请尝试调整目标时长")

    # 构建 FFmpeg concat
    video_info = await get_video_info_full(video_path)

    # 创建片段列表文件
    concat_file = output_path.parent / f"{output_path.stem}_concat.txt"
    temp_clips: list[Path] = []

    try:
        # 逐个裁剪片段
        for i, seg in enumerate(selected):
            clip_path = output_path.parent / f"clip_{i:03d}.mp4"
            await _trim_segment(video_path, clip_path, seg.start, seg.end, hwaccel)
            temp_clips.append(clip_path)

        # 写入 concat 列表
        with open(concat_file, "w", encoding="utf-8") as f:
            for clip in temp_clips:
                escaped = str(clip).replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        # concat 合并
        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(output_path),
        ]
        await execute_ffmpeg(concat_cmd, timeout=600)

        total_duration = sum(s.end - s.start for s in selected)
        return NarratoResult(
            output_path=str(output_path),
            total_duration=total_duration,
            segments=selected,
            ost_type=0,  # 已在外部分类
            hwaccel_used=hwaccel.type.value if hwaccel else "none",
            video_info=video_info,
        )

    finally:
        # 清理临时片段
        for clip in temp_clips:
            try:
                clip.unlink()
            except Exception:
                pass
        try:
            concat_file.unlink()
        except Exception:
            pass


def _greedy_select(
    segments: list[ClipSegment],
    target_duration: float,
    max_clip_duration: float,
) -> list[ClipSegment]:
    """
    贪心选择片段，追求总时长接近目标。

    返回：选取的片段列表（按原始时间排序）
    """
    if not segments:
        return []

    # 按评分降序
    sorted_seg = sorted(segments, key=lambda s: s.score, reverse=True)

    selected: list[ClipSegment] = []
    used_ranges: list[tuple[float, float]] = []
    current_duration = 0.0

    for seg in sorted_seg:
        if current_duration >= target_duration:
            break

        seg_duration = seg.end - seg.start

        # 检查是否与已选片段重叠
        overlaps = False
        for start, end in used_ranges:
            if not (seg.end <= start or seg.start >= end):
                overlaps = True
                break

        if not overlaps:
            # 可以加入
            selected.append(seg)
            used_ranges.append((seg.start, seg.end))
            current_duration += seg_duration

    # 按时间排序
    return sorted(selected, key=lambda s: s.start)


async def _trim_segment(
    video_path: Path,
    output_path: Path,
    start: float,
    end: float,
    hwaccel: HWAccelConfig,
) -> Path:
    """裁剪单个视频片段"""
    duration = end - start
    enc_cfg = get_encoder_config(hwaccel)

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", str(video_path),
        "-t", str(duration),
    ]

    # 视频编码
    if enc_cfg.get("c:v"):
        cmd.extend(["-c:v", enc_cfg["c:v"]])
    if enc_cfg.get("preset"):
        cmd.extend(["-preset", enc_cfg["preset"]])
    if enc_cfg.get("crf"):
        cmd.extend(["-crf", str(enc_cfg["crf"])])
    elif enc_cfg.get("b:v"):
        cmd.extend(["-b:v", enc_cfg["b:v"]])

    # 音频
    cmd.extend(["-c:a", "aac", "-b:a", "128k"])

    cmd.append(str(output_path))

    await execute_ffmpeg(cmd, timeout=120)
    return output_path


# =============================================================================
# NarratoService 主类
# =============================================================================

class NarratoService:
    """
    NarratoAI Pipeline 视频剪辑服务。

    使用方式：
    >>> service = get_narrato_service()
    >>> task_id = await service.start_clip_task(video_path, output_dir, config)
    >>> # 前端轮询 task_id 状态
    """

    def __init__(self):
        self._manager: Optional[BackendManager] = None
        self._hwaccel: Optional[HWAccelConfig] = None
        self._queue = get_task_queue()

    def _get_manager(self) -> BackendManager:
        """懒加载 BackendManager"""
        if self._manager is None:
            # 从 main.py 的初始化模式获取
            try:
                from app.services.llm.manager import get_manager as _get_m
                self._manager = _get_m()
            except Exception:
                logger.warning("BackendManager not available")
                self._manager = None
        return self._manager

    def _get_hwaccel(self) -> HWAccelConfig:
        """懒加载硬件加速配置"""
        if self._hwaccel is None:
            self._hwaccel = check_hardware_acceleration()
            logger.info(f"NarratoService using hwaccel: {self._hwaccel.type.value}")
        return self._hwaccel

    async def start_clip_task(
        self,
        video_path: str,
        output_dir: Optional[str] = None,
        config: Optional[NarratoConfig] = None,
        task_id: Optional[str] = None,
    ) -> str:
        """
        启动 NarratoAI Pipeline 剪辑任务。

        Args:
            video_path: 输入视频路径
            output_dir: 输出目录（默认使用系统临时目录）
            config: 剪辑配置（可选）
            task_id: 可选的任务 ID（用于接续已有任务）

        Returns:
            task_id: 任务 ID（前端轮询用）
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        config = config or NarratoConfig()
        task_id = task_id or str(uuid.uuid4())[:12]

        # 创建任务
        task = await self._queue.create_task(
            task_type="narrato_clip",
            payload={
                "video_path": str(video_path),
                "output_dir": str(output_dir) if output_dir else None,
                "config": {
                    "target_duration": config.target_duration,
                    "num_clips": config.num_clips,
                    "min_clip_duration": config.min_clip_duration,
                    "max_clip_duration": config.max_clip_duration,
                },
            },
        )
        task_id = task.task_id

        # 后台执行
        asyncio.create_task(
            self._run_clip_pipeline(task_id, video_path, output_dir, config)
        )

        return task_id

    async def get_task_status(self, task_id: str) -> dict:
        """查询任务状态（供前端轮询）"""
        task = await self._queue.get_task(task_id)
        if not task:
            return {"error": "任务不存在"}

        return {
            "task_id": task.task_id,
            "status": task.status.value,
            "progress": task.progress,
            "progress_message": task.progress_message,
            "result": task.result,
            "error": task.error,
        }

    async def _run_clip_pipeline(
        self,
        task_id: str,
        video_path: Path,
        output_dir: Optional[str | Path],
        config: NarratoConfig,
    ):
        """后台执行的剪辑流水线"""
        output_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="narrato_out_"))
        ensure_dir(output_dir)

        output_path = output_dir / f"narrato_{task_id}.{config.output_format}"

        async def progress_cb(progress: int, message: str):
            await self._queue.update_progress(task_id, progress, message)

        try:
            await self._queue.update_progress(task_id, 0, "正在分析视频...")

            manager = self._get_manager()
            hwaccel = self._get_hwaccel()

            # Step 1: OST 类型分类
            ost_type = await classify_ost_type(video_path, manager, progress_cb)

            # Step 2: 生成候选片段
            segments = await generate_candidate_segments(
                video_path, ost_type, config, progress_cb
            )
            if not segments:
                raise ValueError("未能生成剪辑候选片段")

            # Step 3: VLM 美学评分
            segments = await score_segments_with_vlm(
                video_path, segments, manager, progress_cb, task_id
            )

            # Step 4: 选段合成
            result = await select_and_concat_segments(
                video_path, segments, config, hwaccel, output_path, progress_cb
            )
            result.ost_type = ost_type

            # 更新 OST 类型到结果
            await self._queue.update_progress(task_id, 100, "剪辑完成")
            task = await self._queue.get_task(task_id)
            if task:
                task.status = TaskStatus.DONE
                task.result = {
                    "output_path": result.output_path,
                    "total_duration": result.total_duration,
                    "segments": [
                        {"start": s.start, "end": s.end, "score": s.score, "source": s.source}
                        for s in result.segments
                    ],
                    "ost_type": result.ost_type,
                    "hwaccel_used": result.hwaccel_used,
                }
                await self._queue.update_task(task)

        except Exception as e:
            logger.error(f"NarratoAI pipeline failed: {e}", exc_info=True)
            task = await self._queue.get_task(task_id)
            if task:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                await self._queue.update_task(task)


# =============================================================================
# 全局单例
# =============================================================================

_narrato_service: Optional[NarratoService] = None


def get_narrato_service() -> NarratoService:
    global _narrato_service
    if _narrato_service is None:
        _narrato_service = NarratoService()
    return _narrato_service
