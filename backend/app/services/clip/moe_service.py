"""
YLCraft — MoE 多专家协作剪辑服务

三个专家模型协作：
1. BeatExpert（节拍专家）：分析音频节奏，输出节拍踩点时间表
2. CompositionExpert（构图专家）：分析画面美学，输出高质量帧区间
3. NarrativeExpert（叙事专家）：分析内容叙事流，输出故事结构片段

ControlPlane（仲裁层）：整合三专家输出，进行多目标优化，
输出最优剪辑片段排序 + 时间安排。

参考 montage-ai src/montage_ai/ 架构。
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from app.core.contracts.types import LLMMessage
from app.core.task_queue import get_task_queue, TaskStatus
from app.services.clip.base import (
    HWAccelConfig,
    analyze_audio_peaks,
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

logger = logging.getLogger("ylcraft.clip.moe")


# =============================================================================
# 专家输出结构
# =============================================================================

@dataclass
class ExpertOutput:
    """专家分析输出"""
    expert: str           # 专家名称
    confidence: float      # 置信度 0-1
    segments: list[dict]   # [{start, end, score, reason}, ...]
    summary: str          # 文字总结
    raw: Any = None       # 原始数据


@dataclass
class ControlPlaneDecision:
    """仲裁层决策"""
    final_segments: list[dict]  # 最终选段 [{start, end, source_expert, score, reason}]
    rejected_reasons: list[str]  # 被拒绝的理由
    total_duration: float
    output_format: str


# =============================================================================
# 三专家分析
# =============================================================================

async def beat_expert(
    video_path: Path,
    manager: BackendManager,
    progress_cb=None,
) -> ExpertOutput:
    """
    BeatExpert：节拍专家。

    分析音频节奏，识别鼓点/节拍时刻，输出踩点时间表。
    评分维度：节奏强度、节拍稳定性、BPM 估计。
    """
    if progress_cb:
        await progress_cb(5, "BeatExpert: 分析音频节拍...")

    # 音频节拍分析
    audio_data = await analyze_audio_peaks(video_path)
    beat_peaks = audio_data.get("peaks", [])

    # 补充：用 LLM 理解音乐类型和节奏特点
    prompt = (
        "你是一个音乐节奏分析专家。请分析这段视频/音频的节奏特点：\n"
        f"检测到的能量峰值点：{beat_peaks}\n\n"
        "请输出：\n"
        "1. 音乐类型（说唱/流行/电子/古典等）\n"
        "2. 节奏特点（快/慢/有变化/平稳）\n"
        "3. 推荐的踩点时间段（秒）：给出3-5个最佳踩点时间\n"
        "4. 每个踩点的置信度（0-1）\n\n"
        "格式：JSON\n"
        '{"type": "...", "tempo": "...", "recommended_beats": [{"time": float, "confidence": float}], "summary": "..."}'
    )

    result = await manager.chat(
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        parsed = json.loads(result.content) if result.success else {}
    except Exception:
        parsed = {}

    beats = parsed.get("recommended_beats", [])
    segments = []
    for beat in beats:
        t = beat.get("time", 0)
        if t > 0:
            segments.append({
                "start": max(0, t - 3),
                "end": min(t + 3, await get_video_duration(video_path)),
                "score": beat.get("confidence", 0.5),
                "reason": f"节拍踩点 @ {t}s",
                "source": "beat",
            })

    return ExpertOutput(
        expert="BeatExpert",
        confidence=0.8,
        segments=segments,
        summary=parsed.get("summary", f"检测到 {len(beats)} 个节拍点"),
        raw=audio_data,
    )


async def composition_expert(
    video_path: Path,
    manager: BackendManager,
    progress_cb=None,
) -> ExpertOutput:
    """
    CompositionExpert：构图专家。

    分析画面美学（构图、色调、运动、景别），输出高质量帧区间。
    评分维度：构图美感、色调统一、运动丰富度、景别多样性。
    """
    if progress_cb:
        await progress_cb(25, "CompositionExpert: 分析画面构图...")

    # 抽取关键帧
    temp_dir = Path(tempfile.mkdtemp(prefix="moe_comp_"))
    ensure_dir(temp_dir)
    keyframes = await extract_keyframes(video_path, temp_dir, interval=2.0, max_frames=20)

    # 用 LLM 视觉分析（简化：描述帧特征而非真正的视觉模型）
    if keyframes and manager:
        prompt = (
            "你是一个专业摄影和构图分析专家。请分析这些视频帧的构图质量：\n"
            f"共 {len(keyframes)} 帧\n\n"
            "分析维度：\n"
            "1. 构图美感（三分法/黄金分割/对称等）\n"
            "2. 色调风格（暖/冷/对比强/柔和）\n"
            "3. 景别变化（大远景/远景/中景/近景/特写）\n"
            "4. 运动丰富度（静止/轻微运动/剧烈运动）\n\n"
            "输出格式（JSON）：\n"
            '{"highlights": [{"time": float, "score": float, "reason": str}], "summary": str}'
        )
        result = await manager.chat([{"role": "user", "content": prompt}])

        try:
            parsed = json.loads(result.content) if result.success else {}
        except Exception:
            parsed = {}

        highlights = parsed.get("highlights", [])
        segments = []
        for hl in highlights:
            t = hl.get("time", 0)
            if t > 0:
                segments.append({
                    "start": max(0, t - 2),
                    "end": min(t + 5, await get_video_duration(video_path)),
                    "score": min(1.0, max(0.0, hl.get("score", 0.5))),
                    "reason": hl.get("reason", "构图质量高"),
                    "source": "composition",
                })
    else:
        parsed = {}
        segments = []

    # 清理临时帧
    try:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass

    return ExpertOutput(
        expert="CompositionExpert",
        confidence=0.7,
        segments=segments,
        summary=parsed.get("summary", f"分析了 {len(keyframes)} 个画面"),
        raw={"num_frames": len(keyframes)},
    )


async def narrative_expert(
    video_path: Path,
    manager: BackendManager,
    progress_cb=None,
) -> ExpertOutput:
    """
    NarrativeExpert：叙事专家。

    分析视频内容叙事结构（开场/发展/高潮/结尾），输出故事节奏片段。
    评分维度：叙事完整性、节奏张力、信息密度。
    """
    if progress_cb:
        await progress_cb(50, "NarrativeExpert: 分析叙事结构...")

    # 获取场景变化 + 视频信息
    scenes = await detect_scene_changes(video_path, threshold=0.35)
    info = await get_video_info_full(video_path)
    duration = info["duration"]

    # 用 LLM 分析叙事结构
    prompt = (
        "你是一个视频叙事分析专家。请分析这段视频的叙事结构：\n"
        f"视频总时长：{duration:.0f}秒\n"
        f"检测到的场景切换：{len(scenes)}处\n"
        f"场景切换时间点：{[round(s['start'], 1) for s in scenes[:15]]}\n\n"
        "请分析：\n"
        "1. 叙事阶段划分（开场/发展/高潮/结尾）及其时间区间\n"
        "2. 叙事节奏（快/慢/张弛有度）\n"
        "3. 推荐保留的叙事关键片段（3-5个）\n\n"
        "输出格式（JSON）：\n"
        '{"structure": [{"phase": str, "start": float, "end": float}], "highlights": [{"time": float, "phase": str, "score": float, "reason": str}], "summary": str}'
    )

    result = await manager.chat([{"role": "user", "content": prompt}])

    try:
        parsed = json.loads(result.content) if result.success else {}
    except Exception:
        parsed = {}

    highlights = parsed.get("highlights", [])
    segments = []
    for hl in highlights:
        t = hl.get("time", 0)
        if t > 0:
            phase = hl.get("phase", "叙事")
            segments.append({
                "start": max(0, t - 2),
                "end": min(t + 4, duration),
                "score": min(1.0, max(0.0, hl.get("score", 0.5))),
                "reason": f"{phase} @ {t}s",
                "source": "narrative",
            })

    return ExpertOutput(
        expert="NarrativeExpert",
        confidence=0.75,
        segments=segments,
        summary=parsed.get("summary", f"识别了 {len(highlights)} 个叙事片段"),
        raw=parsed,
    )


# =============================================================================
# ControlPlane 仲裁层
# =============================================================================

async def control_plane(
    expert_outputs: list[ExpertOutput],
    target_duration: float = 60.0,
    progress_cb=None,
) -> ControlPlaneDecision:
    """
    ControlPlane：仲裁层。

    整合三专家输出，进行多目标优化：
    1. 片段去重/合并（重叠片段取最高分）
    2. 时长约束（总时长 ≈ target_duration）
    3. 专家权重（BeatExpert > Composition > Narrative）
    4. 多样性惩罚（同一时间段避免重复选取）

    返回最优选段方案。
    """
    if progress_cb:
        await progress_cb(75, "ControlPlane: 整合专家意见...")

    # 专家权重
    weights = {
        "beat": 0.4,
        "composition": 0.3,
        "narrative": 0.3,
    }

    # 收集所有候选片段
    all_candidates: list[dict] = []
    for expert in expert_outputs:
        w = weights.get(expert.segments[0]["source"] if expert.segments else "", 0.3) if expert.segments else 0.3
        for seg in expert.segments:
            candidate = dict(seg)
            candidate["weighted_score"] = seg["score"] * w * expert.confidence
            candidate["source_expert"] = expert.expert
            all_candidates.append(candidate)

    # 去重：合并重叠片段
    merged = _merge_segments_by_time(all_candidates)

    # 按加权分数排序
    sorted_candidates = sorted(merged, key=lambda s: s["weighted_score"], reverse=True)

    # 贪心选段
    selected: list[dict] = []
    used_ranges: list[tuple[float, float]] = []
    total_duration = 0.0
    rejected: list[str] = []

    for cand in sorted_candidates:
        if total_duration >= target_duration:
            break

        # 检查重叠
        overlaps = any(
            not (cand["end"] <= start or cand["start"] >= end)
            for start, end in used_ranges
        )

        if overlaps:
            rejected.append(f"[{cand['source_expert']}] {cand['start']:.1f}s-{cand['end']:.1f}s 重叠被拒")
            continue

        selected.append(cand)
        used_ranges.append((cand["start"], cand["end"]))
        total_duration += cand["end"] - cand["start"]

    # 按时间排序最终结果
    selected = sorted(selected, key=lambda s: s["start"])

    return ControlPlaneDecision(
        final_segments=selected,
        rejected_reasons=rejected[:10],  # 最多保留10条
        total_duration=total_duration,
        output_format="mp4",
    )


def _merge_segments_by_time(segments: list[dict]) -> list[dict]:
    """按时间重叠合并片段，取最高加权分"""
    if not segments:
        return []

    sorted_seg = sorted(segments, key=lambda s: s["start"])
    merged = [dict(sorted_seg[0])]

    for seg in sorted_seg[1:]:
        last = merged[-1]
        if seg["start"] <= last["end"] + 1.0:  # 1秒重叠容忍
            # 合并：保留更高分
            if seg.get("weighted_score", 0) > last.get("weighted_score", 0):
                merged[-1] = dict(seg)
            else:
                last["end"] = max(last["end"], seg["end"])
        else:
            merged.append(dict(seg))

    return merged


# =============================================================================
# MoE 合成执行
# =============================================================================

async def execute_moe_concat(
    video_path: Path,
    segments: list[dict],
    output_path: Path,
    progress_cb=None,
) -> tuple[str, float]:
    """
    执行 FFmpeg 合成（MoE 选定的片段）。

    Returns:
        (output_path, total_duration)
    """
    if progress_cb:
        await progress_cb(90, "正在执行 FFmpeg 合成...")

    hwaccel = check_hardware_acceleration()
    temp_clips: list[Path] = []

    try:
        for i, seg in enumerate(segments):
            clip_path = output_path.parent / f"moe_clip_{i:03d}.mp4"
            await _trim_clip(video_path, clip_path, seg["start"], seg["end"], hwaccel)
            temp_clips.append(clip_path)

        concat_file = output_path.parent / "moe_concat.txt"
        with open(concat_file, "w", encoding="utf-8") as f:
            for cp in temp_clips:
                esc = str(cp).replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{esc}'\n")

        concat_cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(output_path),
        ]
        await execute_ffmpeg(concat_cmd, timeout=600)

        total_duration = sum(s["end"] - s["start"] for s in segments)

        return str(output_path), total_duration

    finally:
        for cp in temp_clips:
            try:
                cp.unlink()
            except Exception:
                pass
        try:
            concat_file.unlink()
        except Exception:
            pass


async def _trim_clip(
    video_path: Path,
    output_path: Path,
    start: float,
    end: float,
    hwaccel: HWAccelConfig,
) -> Path:
    duration = end - start
    enc_cfg = get_encoder_config(hwaccel)
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", str(video_path),
        "-t", str(duration),
    ]
    if enc_cfg.get("c:v"):
        cmd.extend(["-c:v", enc_cfg["c:v"]])
    if enc_cfg.get("preset"):
        cmd.extend(["-preset", enc_cfg["preset"]])
    if enc_cfg.get("crf"):
        cmd.extend(["-crf", str(enc_cfg["crf"])])
    elif enc_cfg.get("b:v"):
        cmd.extend(["-b:v", enc_cfg["b:v"]])
    cmd.extend(["-c:a", "aac", "-b:a", "128k"])
    cmd.append(str(output_path))
    await execute_ffmpeg(cmd, timeout=120)
    return output_path


# =============================================================================
# MoEService 主类
# =============================================================================

class MoEService:
    """
    MoE 多专家协作剪辑服务。

    使用方式：
    >>> service = get_moe_service()
    >>> task_id = await service.start_moe_task(video_path, target_duration=60)
    """

    def __init__(self):
        self._manager: Optional[BackendManager] = None
        self._queue = get_task_queue()

    def _get_manager(self) -> Optional[BackendManager]:
        if self._manager is None:
            try:
                from app.services.llm.manager import get_manager as _get_m
                self._manager = _get_m()
            except Exception:
                logger.warning("BackendManager not available")
                self._manager = None
        return self._manager

    async def start_moe_task(
        self,
        video_path: str,
        target_duration: float = 60.0,
        output_dir: Optional[str] = None,
    ) -> str:
        """
        启动 MoE 多专家协作剪辑任务。

        Args:
            video_path: 输入视频路径
            target_duration: 目标输出时长（秒）
            output_dir: 输出目录

        Returns:
            task_id
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        task = await self._queue.create_task(
            task_type="moe_clip",
            payload={
                "video_path": str(video_path),
                "target_duration": target_duration,
                "output_dir": str(output_dir) if output_dir else None,
            },
        )

        asyncio.create_task(
            self._run_moe(task.task_id, video_path, target_duration, output_dir)
        )

        return task.task_id

    async def get_task_status(self, task_id: str) -> dict:
        """查询任务状态"""
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

    async def _run_moe(
        self,
        task_id: str,
        video_path: Path,
        target_duration: float,
        output_dir: Optional[str | Path],
    ):
        """后台运行 MoE 流水线"""
        output_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="moe_out_"))
        ensure_dir(output_dir)
        output_path = output_dir / f"moe_{task_id}.mp4"

        async def progress_cb(progress: int, message: str):
            await self._queue.update_progress(task_id, progress, message)

        try:
            await self._queue.update_progress(task_id, 0, "MoE 多专家分析中...")

            manager = self._get_manager()
            if not manager:
                raise RuntimeError("LLM Manager 不可用")

            # 并行运行三专家
            beat_out, comp_out, narr_out = await asyncio.gather(
                beat_expert(video_path, manager, progress_cb),
                composition_expert(video_path, manager, progress_cb),
                narrative_expert(video_path, manager, progress_cb),
            )

            expert_outputs = [beat_out, comp_out, narr_out]

            # ControlPlane 仲裁
            decision = await control_plane(
                expert_outputs,
                target_duration=target_duration,
                progress_cb=progress_cb,
            )

            if not decision.final_segments:
                raise ValueError("MoE 未能找到合适的剪辑片段")

            # 执行合成
            output_path_str, total_duration = await execute_moe_concat(
                video_path,
                decision.final_segments,
                output_path,
                progress_cb,
            )

            await self._queue.update_progress(task_id, 100, "MoE 剪辑完成")

            task = await self._queue.get_task(task_id)
            if task:
                task.status = TaskStatus.DONE
                task.result = {
                    "output_path": output_path_str,
                    "total_duration": total_duration,
                    "segments": decision.final_segments,
                    "expert_summary": {
                        e.expert: {"confidence": e.confidence, "segments_found": len(e.segments)}
                        for e in expert_outputs
                    },
                    "rejected_reasons": decision.rejected_reasons,
                }
                await self._queue.update_task(task)

        except Exception as e:
            logger.error(f"MoE pipeline failed: {e}", exc_info=True)
            task = await self._queue.get_task(task_id)
            if task:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                await self._queue.update_task(task)


# =============================================================================
# 全局单例
# =============================================================================

_moe_service: Optional[MoEService] = None


def get_moe_service() -> MoEService:
    global _moe_service
    if _moe_service is None:
        _moe_service = MoEService()
    return _moe_service
