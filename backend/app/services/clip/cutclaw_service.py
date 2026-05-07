"""
YLCraft — CutClaw Agent 服务

基于 LLM Agent 的自然语言视频剪辑工具。

CutClaw 的核心是 LLM 工具调用循环：
1. LLM 分析视频内容 + 用户指令
2. LLM 选择合适的工具（trim/review/scene_detect 等）
3. 工具执行，返回结果给 LLM
4. LLM 判断是否完成或继续调用工具
5. 输出最终剪辑方案 + 执行 FFmpeg

工具集：
- analyze_video：分析视频内容、人物、场景
- get_video_info：获取视频基本信息
- detect_scenes：检测场景切换点
- analyze_audio_peaks：分析音频节拍
- trim_segment：裁剪指定时间段
- review_segments：审视已选片段，给出优化建议
- commit：提交最终剪辑方案

参考 CutClaw src/core.py + src/func_call_schema.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.core.contracts.types import LLMMessage
from app.core.task_queue import get_task_queue, TaskStatus
from app.services.clip.base import (
    HWAccelConfig,
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

logger = logging.getLogger("ylcraft.clip.cutclaw")


# =============================================================================
# 工具定义（Tool Schemas）
# =============================================================================

@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    content: str  # LLM 可见的文本描述
    data: Any = None  # 额外数据（不放入 prompt）


# 工具 Schema（用于 LLM 函数调用）
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_video_info",
            "description": "获取视频基本信息（分辨率、时长、帧率、编码等）。先调用此工具了解视频基本参数。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "detect_scenes",
            "description": "检测视频场景切换点（镜头切换位置）。返回场景边界时间戳列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "threshold": {
                        "type": "number",
                        "description": "场景检测敏感度，0.0-1.0，默认0.4。值越高越敏感（检测越多切换）。",
                        "default": 0.4,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_keyframes",
            "description": "抽取视频关键帧缩略图，返回帧图片路径列表。每隔 N 秒取一帧，最多返回30帧。",
            "parameters": {
                "type": "object",
                "properties": {
                    "interval": {
                        "type": "number",
                        "description": "抽取间隔（秒），默认1.0",
                        "default": 1.0,
                    },
                    "max_frames": {
                        "type": "number",
                        "description": "最大帧数，默认30",
                        "default": 30,
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_content",
            "description": "用 LLM 分析关键帧图片，理解视频内容（人物、场景、动作、文字等）。需要先 extract_keyframes。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "select_clips",
            "description": "根据分析结果，选定要剪辑的片段时间范围。这是最终决策点。",
            "parameters": {
                "type": "object",
                "properties": {
                    "clips": {
                        "type": "array",
                        "description": "选定的片段列表，每项为 {start: float, end: float, reason: str}",
                        "items": {
                            "type": "object",
                            "properties": {
                                "start": {"type": "number", "description": "开始时间（秒）"},
                                "end": {"type": "number", "description": "结束时间（秒）"},
                                "reason": {"type": "string", "description": "选择理由"},
                            },
                            "required": ["start", "end"],
                        },
                    },
                },
                "required": ["clips"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "commit",
            "description": "提交最终剪辑方案，执行 FFmpeg 合成视频。必须在 select_clips 之后调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "clips": {
                        "type": "array",
                        "description": "最终剪辑片段（由 select_clips 返回）",
                        "items": {
                            "type": "object",
                            "properties": {
                                "start": {"type": "number"},
                                "end": {"type": "number"},
                            },
                        },
                    },
                    "instruction": {
                        "type": "string",
                        "description": "用户原始剪辑指令",
                    },
                },
                "required": ["clips", "instruction"],
            },
        },
    },
]


# =============================================================================
# CutClaw Agent
# =============================================================================

@dataclass
class CutClawConfig:
    """CutClaw Agent 配置"""
    max_turns: int = 10          # LLM 最大思考轮次
    auto_cut: bool = True        # 是否自动执行 commit
    output_format: str = "mp4"
    provider: Optional[str] = None
    model: Optional[str] = None


class CutClawAgent:
    """
    CutClaw LLM Agent：自然语言驱动的视频剪辑。

    工作方式：
    - 维护对话历史（messages）
    - 每次 LLM 回复可能包含工具调用
    - 执行工具，返回结果给 LLM
    - 循环直到 LLM 调用 commit 或达到 max_turns
    """

    def __init__(
        self,
        video_path: Path,
        instruction: str,
        config: Optional[CutClawConfig] = None,
        manager: Optional[BackendManager] = None,
    ):
        self.video_path = video_path
        self.instruction = instruction
        self.config = config or CutClawConfig()
        self.manager = manager
        self._hwaccel: Optional[HWAccelConfig] = None

        # Agent 状态
        self.messages: list[LLMMessage] = []
        self.turn_count = 0
        self.selected_clips: list[dict] = []
        self.keyframes: list[Path] = []
        self.video_info: dict = {}
        self.scenes: list[dict] = []
        self.content_analysis: str = ""
        self.output_path: Optional[Path] = None

        # 初始化系统提示
        self._init_system_prompt()

    def _init_system_prompt(self):
        """初始化系统提示词"""
        system_prompt = (
            "你是一个专业的视频剪辑助手，名为 CutClaw。\n\n"
            "你的职责是根据用户的自然语言指令，"
            "从一段原始视频中智能选取最佳片段并完成剪辑。\n\n"
            "你有以下工具可用：\n"
            "- get_video_info: 获取视频基本信息\n"
            "- detect_scenes(threshold): 检测镜头切换点\n"
            "- extract_keyframes(interval, max_frames): 抽取关键帧\n"
            "- analyze_content: 基于关键帧理解视频内容\n"
            "- select_clips(clips): 选定剪辑片段\n"
            "- commit(clips, instruction): 执行最终剪辑\n\n"
            "剪辑流程：\n"
            "1. 先 get_video_info 了解视频\n"
            "2. detect_scenes 找到镜头切换\n"
            "3. extract_keyframes + analyze_content 理解内容\n"
            "4. select_clips 选定片段（需给出时间范围+理由）\n"
            "5. commit 提交执行\n\n"
            "重要规则：\n"
            "- 必须先了解视频才能选段\n"
            "- 选段要贴合用户指令（如「保留高潮」「剪掉广告」）\n"
            "- commit 后返回最终文件路径\n"
            "- 每轮最多调用1个工具，谨慎选择\n"
            "- 如果已有足够信息，应立即 select_clips + commit"
        )
        self.messages = [{"role": "system", "content": system_prompt}]

    def _get_hwaccel(self) -> HWAccelConfig:
        if self._hwaccel is None:
            self._hwaccel = check_hardware_acceleration()
        return self._hwaccel

    # -------------------------------------------------------------------------
    # 工具注册表
    # -------------------------------------------------------------------------

    def _get_tool_map(self) -> dict[str, callable]:
        return {
            "get_video_info": self._tool_get_video_info,
            "detect_scenes": self._tool_detect_scenes,
            "extract_keyframes": self._tool_extract_keyframes,
            "analyze_content": self._tool_analyze_content,
            "select_clips": self._tool_select_clips,
            "commit": self._tool_commit,
        }

    async def _execute_tool(self, name: str, args: dict) -> ToolResult:
        """执行指定工具"""
        tools = self._get_tool_map()
        if name not in tools:
            return ToolResult(success=False, content=f"未知工具: {name}")

        try:
            result = await tools[name](args)
            return result
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}", exc_info=True)
            return ToolResult(success=False, content=f"工具执行失败: {e}")

    # -------------------------------------------------------------------------
    # 工具实现
    # -------------------------------------------------------------------------

    async def _tool_get_video_info(self, args: dict) -> ToolResult:
        self.video_info = await get_video_info_full(self.video_path)
        content = (
            f"视频信息：\n"
            f"- 分辨率：{self.video_info['width']}x{self.video_info['height']}\n"
            f"- 时长：{self.video_info['duration']:.1f}秒\n"
            f"- 帧率：{self.video_info['fps']:.1f}fps\n"
            f"- 编码：{self.video_info['codec']}\n"
            f"- 文件大小：{self.video_info['file_size'] / 1024 / 1024:.1f}MB"
        )
        return ToolResult(success=True, content=content, data=self.video_info)

    async def _tool_detect_scenes(self, args: dict) -> ToolResult:
        threshold = args.get("threshold", 0.4)
        self.scenes = await detect_scene_changes(self.video_path, threshold)
        if not self.scenes:
            content = "未检测到明显场景切换。"
        else:
            scene_times = ", ".join(f"{s['start']:.1f}s" for s in self.scenes[:10])
            content = f"检测到 {len(self.scenes)} 个场景切换，主要时间点：{scene_times}"
        return ToolResult(success=True, content=content, data=self.scenes)

    async def _tool_extract_keyframes(self, args: dict) -> ToolResult:
        interval = args.get("interval", 1.0)
        max_frames = args.get("max_frames", 30)
        temp_dir = Path(tempfile.mkdtemp(prefix="cutclaw_kf_"))
        self.keyframes = await extract_keyframes(
            self.video_path, temp_dir, interval, max_frames
        )
        content = f"已抽取 {len(self.keyframes)} 个关键帧。"
        return ToolResult(success=True, content=content, data=self.keyframes)

    async def _tool_analyze_content(self, args: dict) -> ToolResult:
        if not self.keyframes:
            return ToolResult(success=False, content="请先调用 extract_keyframes")

        # 用 LLM 分析关键帧内容
        if not self.manager:
            self.content_analysis = (
                f"视频共 {len(self.keyframes)} 帧。"
                f"用户指令：{self.instruction}"
            )
        else:
            # 构建 vision prompt
            frames_desc = "\n".join(
                f"[帧{i+1}] {kf.name}" for i, kf in enumerate(self.keyframes[:10])
            )
            prompt = (
                f"你是一个视频内容分析助手。请分析以下视频关键帧，"
                f"描述视频的主要内容、人物、场景变化和节奏特点。\n\n"
                f"关键帧文件：\n{frames_desc}\n\n"
                f"用户剪辑指令：{self.instruction}\n\n"
                f"请用中文详细描述。"
            )
            messages = [{"role": "user", "content": prompt}]
            result = await self.manager.chat(messages)
            self.content_analysis = result.content if result.success else "分析失败"

        content = f"内容分析：{self.content_analysis[:200]}..."
        return ToolResult(success=True, content=content, data=self.content_analysis)

    async def _tool_select_clips(self, args: dict) -> ToolResult:
        clips = args.get("clips", [])
        if not clips:
            return ToolResult(success=False, content="必须指定至少一个剪辑片段")

        self.selected_clips = clips
        duration = await get_video_duration(self.video_path)

        # 验证片段合理性
        valid_clips = []
        for clip in clips:
            start = max(0, float(clip["start"]))
            end = min(duration, float(clip["end"]))
            if end - start >= 1.0:  # 最少1秒
                valid_clips.append({"start": start, "end": end, "reason": clip.get("reason", "")})

        self.selected_clips = valid_clips
        total = sum(c["end"] - c["start"] for c in valid_clips)
        content = (
            f"已选定 {len(valid_clips)} 个片段，总时长 {total:.1f}秒：\n"
            + "\n".join(f"  [{c['start']:.1f}s - {c['end']:.1f}s] {c.get('reason', '')}"
                        for c in valid_clips)
        )
        return ToolResult(success=True, content=content, data=valid_clips)

    async def _tool_commit(self, args: dict) -> ToolResult:
        clips = args.get("clips", self.selected_clips)
        instruction = args.get("instruction", self.instruction)

        if not clips:
            return ToolResult(success=False, content="没有可剪辑的片段")

        output_dir = Path(tempfile.mkdtemp(prefix="cutclaw_out_"))
        output_path = output_dir / f"cutclaw_{uuid.uuid4().hex[:8]}.{self.config.output_format}"

        # 执行 FFmpeg 裁剪 + concat
        hwaccel = self._get_hwaccel()
        temp_clips: list[Path] = []

        try:
            # 逐个裁剪
            for i, clip in enumerate(clips):
                clip_path = output_path.parent / f"clip_{i:03d}.mp4"
                await self._trim_clip(self.video_path, clip_path, clip["start"], clip["end"], hwaccel)
                temp_clips.append(clip_path)

            # Concat
            concat_list = output_path.parent / "concat.txt"
            with open(concat_list, "w", encoding="utf-8") as f:
                for cp in temp_clips:
                    esc = str(cp).replace("\\", "/").replace("'", "'\\''")
                    f.write(f"file '{esc}'\n")

            concat_cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c", "copy",
                str(output_path),
            ]
            await execute_ffmpeg(concat_cmd, timeout=600)

            self.output_path = output_path
            total = sum(c["end"] - c["start"] for c in clips)
            content = (
                f"✅ 剪辑完成！\n"
                f"输出文件：{output_path}\n"
                f"总时长：{total:.1f}秒\n"
                f"片段数：{len(clips)}\n"
                f"使用硬件加速：{hwaccel.type.value}"
            )
            return ToolResult(success=True, content=content, data=str(output_path))

        finally:
            # 清理临时片段
            for cp in temp_clips:
                try:
                    cp.unlink()
                except Exception:
                    pass
            try:
                concat_list.unlink()
            except Exception:
                pass

    async def _trim_clip(
        self,
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

    # -------------------------------------------------------------------------
    # Agent 循环
    # -------------------------------------------------------------------------

    async def run(self, progress_cb=None) -> ToolResult:
        """
        运行 CutClaw Agent 主循环。

        Returns:
            ToolResult: 最终结果（commit 后的输出路径）
        """
        # 添加用户指令
        self.messages.append({
            "role": "user",
            "content": f"请帮我剪辑视频：{self.instruction}\n\n视频路径：{self.video_path}",
        })

        for self.turn_count in range(self.config.max_turns):
            if progress_cb:
                await progress_cb(
                    int(90 * self.turn_count / self.config.max_turns),
                    f"AI 思考中（第{self.turn_count + 1}轮）...",
                )

            # 调用 LLM
            manager = self.manager or self._get_manager()
            if not manager:
                return ToolResult(
                    success=False,
                    content="LLM Manager 不可用，无法执行 CutClaw Agent",
                )

            result = await manager.chat(
                messages=self.messages,
                provider=self.config.provider,
                tools=TOOL_SCHEMAS,
            )

            if not result.success:
                return ToolResult(success=False, content=f"LLM 调用失败: {result.error}")

            assistant_msg = {"role": "assistant", "content": result.content}

            # 检查是否包含工具调用
            if hasattr(result, "tool_calls") and result.tool_calls:
                for tc in result.tool_calls:
                    tool_name = tc.get("function", {}).get("name", "")
                    tool_args = json.loads(tc.get("function", {}).get("arguments", "{}"))
                    tool_args = tool_args if isinstance(tool_args, dict) else {}

                    assistant_msg["tool_calls"] = [tc]

                    # 添加 LLM 决策到历史
                    self.messages.append(assistant_msg)

                    # 执行工具
                    if progress_cb:
                        await progress_cb(
                            int(80 * self.turn_count / self.config.max_turns),
                            f"执行工具：{tool_name}...",
                        )

                    tool_result = await self._execute_tool(tool_name, tool_args)

                    # 添加工具结果到历史
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc.get("id", "unknown"),
                        "content": tool_result.content,
                    })

                    # 如果是 commit，结束
                    if tool_name == "commit":
                        return tool_result

            else:
                # LLM 没有调用工具（可能是结束或追问）
                self.messages.append(assistant_msg)
                if "commit" in result.content.lower() or self.turn_count >= self.config.max_turns - 2:
                    # 最后一轮：尝试自动 commit
                    if self.selected_clips:
                        return await self._tool_commit({
                            "clips": self.selected_clips,
                            "instruction": self.instruction,
                        })
                    return ToolResult(
                        success=False,
                        content="Agent 未能完成剪辑，已达最大轮次",
                    )

        return ToolResult(success=False, content="达到最大思考轮次，未能完成剪辑")


# =============================================================================
# CutClawService
# =============================================================================

class CutClawService:
    """
    CutClaw Agent 服务层（管理任务生命周期）。

    使用方式：
    >>> service = get_cutclaw_service()
    >>> task_id = await service.start_agent_task(video_path, instruction)
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

    async def start_agent_task(
        self,
        video_path: str,
        instruction: Optional[str] = None,
        config: Optional[CutClawConfig] = None,
        auto_cut: bool = True,
    ) -> str:
        """
        启动 CutClaw Agent 任务。

        Args:
            video_path: 输入视频路径
            instruction: 自然语言剪辑指令
            config: Agent 配置
            auto_cut: 是否自动执行

        Returns:
            task_id
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        config = config or CutClawConfig(auto_cut=auto_cut)
        if not instruction:
            instruction = "请帮我剪辑出最精彩的片段，适合短视频分享"

        task = await self._queue.create_task(
            task_type="cutclaw_agent",
            payload={
                "video_path": str(video_path),
                "instruction": instruction,
                "auto_cut": auto_cut,
            },
        )

        asyncio.create_task(
            self._run_agent(task.task_id, video_path, instruction, config)
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

    async def _run_agent(
        self,
        task_id: str,
        video_path: Path,
        instruction: str,
        config: CutClawConfig,
    ):
        """后台运行 Agent"""
        async def progress_cb(progress: int, message: str):
            await self._queue.update_progress(task_id, progress, message)

        try:
            await self._queue.update_progress(task_id, 0, "正在初始化 CutClaw Agent...")

            agent = CutClawAgent(
                video_path=video_path,
                instruction=instruction,
                config=config,
                manager=self._get_manager(),
            )

            result = await agent.run(progress_cb)

            task = await self._queue.get_task(task_id)
            if task:
                task.status = TaskStatus.DONE if result.success else TaskStatus.FAILED
                task.progress = 100
                task.progress_message = result.content[:100]
                task.result = {
                    "success": result.success,
                    "message": result.content,
                    "output_path": result.data,
                    "selected_clips": agent.selected_clips,
                }
                if not result.success:
                    task.error = result.content
                await self._queue.update_task(task)

        except Exception as e:
            logger.error(f"CutClaw Agent failed: {e}", exc_info=True)
            task = await self._queue.get_task(task_id)
            if task:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                await self._queue.update_task(task)


# =============================================================================
# 全局单例
# =============================================================================

_cutclaw_service: Optional[CutClawService] = None


def get_cutclaw_service() -> CutClawService:
    global _cutclaw_service
    if _cutclaw_service is None:
        _cutclaw_service = CutClawService()
    return _cutclaw_service
