"""YLCraft — 爆款拆解服务（增强版）

核心流程：
1. 解析视频链接（内置 VideoParser）→ 元数据 + 视频URL
2. 下载视频 → 提取音频 → 语音转录
3. 提取关键帧 → 角色分析 + 场景识别
4. LLM 分析文案结构 → 生成仿写提示词
5. 返回结构化报告（含角色库、分镜表、提示词）
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import httpx

from app.core.contracts.types import LLMMessage, MediaType, StrEnum
from app.services.llm.manager import get_manager
from app.services.video import parser as video_parser
from app.services.xhs_parser import get_xhs_parser, XhsNote
import re


class AnalysisStatus(StrEnum):
    PENDING = "pending"
    PARSING = "parsing"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    ANALYZING = "analyzing"
    DONE = "done"
    FAILED = "failed"


@dataclass
class CharacterExtract:
    """从视频中提取的角色"""
    name: str
    role: str = "supporting"  # protagonist / antagonist / supporting / extra
    appearance: str = ""
    first_appearance_shot: int = 0
    total_shots: int = 0
    traits: list[str] = field(default_factory=list)


@dataclass
class ShotExtract:
    """从视频中提取的分镜"""
    order: int
    timestamp_sec: float = 0.0
    description: str = ""
    shot_type: str = "MS"  # ECU/CU/MCU/MS/MLS/LS/ELS
    characters: list[str] = field(default_factory=list)
    dialogue: str = ""
    emotion: str = ""
    key_frame_url: str = ""


@dataclass
class BreakdownResult:
    """拆解结果"""
    # 基本信息
    title: str = ""
    author: str = ""
    platform: str = ""
    video_url: str = ""
    cover_url: str = ""
    duration_estimate: str = ""

    # 文案分析
    hook_analysis: str = ""
    structure: dict = field(default_factory=dict)
    emotion_curve: list[str] = field(default_factory=list)
    key_elements: dict = field(default_factory=dict)
    style_tags: list[str] = field(default_factory=list)
    viral_factors: list[str] = field(default_factory=list)

    # 角色与分镜
    characters: list[CharacterExtract] = field(default_factory=list)
    shots: list[ShotExtract] = field(default_factory=list)

    # 仿写提示词
    rewrite_prompts: dict = field(default_factory=dict)

    # 原始内容
    transcript: str = ""


@dataclass
class BreakTask:
    """拆解任务"""
    task_id: str
    url: str
    status: AnalysisStatus = AnalysisStatus.PENDING
    result: BreakdownResult | None = None
    error: str | None = None
    created_at: float = 0.0
    progress: int = 0
    progress_message: str = ""


# =============================================================================
# Redis 任务队列（替换内存存储）
# =============================================================================

from app.core.task_queue import get_task_queue, TaskStatus


async def create_task(url: str) -> BreakTask:
    """创建拆解任务（使用 Redis）"""
    queue = get_task_queue()

    # 创建统一任务
    task = await queue.create_task(
        task_type="breaker",
        payload={"url": url},
        max_retries=2,
    )

    # 转换为 BreakTask 格式（保持 API 兼容）
    return BreakTask(
        task_id=task.task_id,
        url=url,
        status=AnalysisStatus(task.status.value),
        created_at=task.created_at,
        progress=0,
    )


async def get_task(task_id: str) -> BreakTask | None:
    """获取任务（从 Redis）"""
    queue = get_task_queue()
    task = await queue.get_task(task_id)

    if not task:
        return None

    # 转换为 BreakTask 格式
    result = None
    if task.result:
        report_data = task.result.get("report", {})
        result = BreakdownResult(
            title=task.result.get("title", ""),
            author=task.result.get("author", ""),
            platform=task.result.get("platform", ""),
            video_url=task.result.get("video_url", ""),
            cover_url=task.result.get("cover_url", ""),
            duration_estimate=task.result.get("duration_estimate", ""),
            hook_analysis=report_data.get("hook", "") or task.result.get("hook_analysis", ""),
            structure=task.result.get("structure", {}),
            emotion_curve=task.result.get("emotion_curve", []) or report_data.get("emotion_curve", []),
            key_elements=task.result.get("key_elements", {}),
            style_tags=task.result.get("style_tags", []),
            viral_factors=task.result.get("viral_factors", []),
            characters=[CharacterExtract(**c) for c in task.result.get("characters", [])],
            shots=[ShotExtract(**s) for s in task.result.get("shots", [])],
            rewrite_prompts=task.result.get("rewrite_prompts", {}),
            transcript=task.result.get("transcript", ""),
        )

    return BreakTask(
        task_id=task.task_id,
        url=task.payload.get("url", ""),
        status=AnalysisStatus(task.status.value),
        result=result,
        error=task.error,
        created_at=task.created_at,
        progress=task.progress,
    )


# =============================================================================
# 视频解析与转录
# =============================================================================

async def parse_video_url(url: str) -> dict:
    """
    解析视频链接，返回元数据 + 无水印视频地址。
    使用内置 VideoParser（支持抖音/快手/B站/小红书/微博，yt-dlp 兜底）。

    返回: {
        "video_url": "...",
        "cover_url": "...",
        "title": "...",
        "author": {"name": "...", "uid": "...", "avatar": "..."},
        "platform": "douyin",
        "duration": 30,
        "content_type": "video",
        "images": [],
        "parse_method": "douyin_api_v1",
    }
    """
    info = await video_parser.parse(url)
    return video_parser.to_breaker_format(info)


async def download_video(original_url: str, output_path: str, video_url: str = "") -> bool:
    """
    下载视频文件。
    优先 yt-dlp（处理各平台防盗链），兜底 httpx 直链下载。
    """
    info = video_parser.VideoInfo(
        original_url=original_url,
        platform=video_parser._detect_platform(original_url),
        video_url=video_url,
    )
    return await video_parser.download(info, output_path)


async def extract_audio(video_path: str, audio_path: str) -> bool:
    """从视频中提取音频（使用 ffmpeg）"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-i", video_path,
            "-vn", "-acodec", "libmp3lame", "-q:a", "2",
            audio_path, "-y",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        return proc.returncode == 0
    except Exception:
        return False


async def transcribe_audio(audio_path: str, api_key: str | None = None) -> str:
    """
    使用 SiliconFlow ASR API 转录音频。
    如果没有 API Key，返回空字符串。
    """
    api_key = api_key or os.environ.get("SILICONFLOW_API_KEY")
    if not api_key:
        return ""

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            with open(audio_path, "rb") as f:
                files = {"file": ("audio.mp3", f, "audio/mpeg")}
                headers = {"Authorization": f"Bearer {api_key}"}
                response = await client.post(
                    "https://api.siliconflow.cn/v1/audio/transcriptions",
                    files=files,
                    data={"model": "FunAudioLLM/SenseVoiceSmall"},
                    headers=headers,
                )

            if response.status_code == 200:
                result = response.json()
                return result.get("text", "")
    except Exception:
        pass

    return ""


async def extract_key_frames(
    video_path: str,
    output_dir: str,
    num_frames: int = 5,
) -> list[str]:
    """
    从视频中均匀提取关键帧。
    返回: 关键帧图片路径列表
    """
    os.makedirs(output_dir, exist_ok=True)

    # 先获取视频时长
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        duration = float(stdout.decode().strip())
    except Exception:
        duration = 10.0

    # 均匀提取帧
    frame_paths = []
    interval = duration / (num_frames + 1)

    for i in range(num_frames):
        timestamp = interval * (i + 1)
        frame_path = os.path.join(output_dir, f"frame_{i+1:02d}.jpg")

        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-ss", str(timestamp),
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "2",
                frame_path, "-y",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            if os.path.exists(frame_path):
                frame_paths.append(frame_path)
        except Exception:
            continue

    return frame_paths


# =============================================================================
# LLM 分析
# =============================================================================

BREAKDOWN_PROMPT = """你是一位短视频内容分析专家。请分析以下视频内容，输出结构化报告。

## 分析任务

### 1. 钩子分析（Hook Analysis）
分析开头 3-5 秒如何吸引注意力，具体手法是什么？

### 2. 文案结构（Structure）
分析总时长、段落数、节奏变化点

### 3. 情绪曲线（Emotion Curve）
标注开头、中段、结尾的情绪状态

### 4. 核心要素（Key Elements）
识别核心冲突、高潮点、结尾处理方式

### 5. 风格标签（Style Tags）
内容类型、目标人群、表现手法

### 6. 爆款因子（Viral Factors）
分析哪些元素可能引发共鸣/争议/好奇

### 7. 角色识别（Character Extraction）
识别视频中的主要角色，描述其外貌特征

### 8. 分镜拆解（Shot Breakdown）
将视频拆解为 5-8 个分镜，每个分镜包含：描述、景别、情绪、角色

## 输入信息

**标题**: {title}
**平台**: {platform}
**作者**: {author}
**字幕/转录**:
{transcript}

## 输出格式

请严格输出以下 JSON schema（不要添加注释）：

```json
{{
  "hook_analysis": "钩子分析（50字以内）",
  "structure": {{
    "duration_estimate": "预估时长（如：45秒）",
    "segments": ["开头段落描述", "中段段落描述", "结尾段落描述"],
    "pacing": "节奏描述"
  }},
  "emotion_curve": ["开头情绪", "中段情绪", "结尾情绪"],
  "key_elements": {{
    "conflict": "核心冲突",
    "climax": "高潮点",
    "ending": "结尾处理"
  }},
  "style_tags": ["标签1", "标签2", "标签3"],
  "viral_factors": ["因子1", "因子2"],
  "characters": [
    {{
      "name": "角色名（如：女生A、男生B）",
      "role": "protagonist/supporting",
      "appearance": "外貌描述（用于生成角色立绘）",
      "traits": ["性格特征1", "性格特征2"]
    }}
  ],
  "shots": [
    {{
      "order": 1,
      "description": "分镜描述",
      "shot_type": "MS",
      "characters": ["角色名"],
      "dialogue": "对白（如有）",
      "emotion": "情绪"
    }}
  ],
  "rewrite_prompts": {{
    "character_prompt": "角色设定提示词（用于生成相似角色）",
    "scene_prompt": "场景提示词",
    "script_template": "脚本模板（保留结构替换内容）"
  }}
}}
"""

# 小红书图文分析 Prompt
XHS_ANALYSIS_PROMPT = """你是一位小红书内容分析专家，擅长拆解图文笔记的爆款逻辑。

## 分析任务
分析以下小红书图文笔记，识别其爆款结构。

### 1. 钩子分析（Hook）
分析标题和第一句话如何吸引点击，具体用了什么手法？

### 2. 文案结构（Structure）
正文分为几个部分？每部分的核心是什么？

### 3. 情绪曲线（Emotion Curve）
从头到尾情绪如何变化？哪些点触发共鸣/好奇/感动？

### 4. 核心要素（Key Elements）
识别：核心冲突/共鸣点/记忆点/行动号召

### 5. 风格标签（Style Tags）
内容类型、目标人群、表现手法、平台调性

### 6. 爆款因子（Viral Factors）
分析哪些元素让它有传播潜力

### 7. 角色识别（Character Extraction）
识别笔记中涉及的人物，描述外貌和性格特征

### 8. 仿写提示词（Rewrite Prompts）
生成可直接用于生成相似内容的提示词

## 输入信息

**标题**: {title}
**作者**: {author}
**正文内容**: 
{content}
**图片数量**: {images_count} 张

## 输出格式

请严格输出以下 JSON schema（不要添加注释，不要加 ```json 标记）：

{{
  "hook_analysis": "钩子分析（50字以内）",
  "structure": {{
    "segments": ["段落1描述", "段落2描述", "段落3描述"],
    "pacing": "节奏描述",
    "word_count_estimate": "预估正文字数"
  }},
  "emotion_curve": ["开头情绪", "中段情绪", "结尾情绪"],
  "key_elements": {{
    "conflict": "核心冲突或主题",
    "resonance": "共鸣点",
    "memorable": "记忆点",
    "call_to_action": "行动号召"
  }},
  "style_tags": ["标签1", "标签2", "标签3", "标签4"],
  "viral_factors": ["因子1", "因子2"],
  "characters": [
    {{
      "name": "人物称谓（如：博主、闺蜜、男友）",
      "role": "protagonist/supporting",
      "appearance": "外貌描述（用于生成角色立绘）",
      "traits": ["性格特征1", "性格特征2"]
    }}
  ],
  "rewrite_prompts": {{
    "character_prompt": "角色设定提示词",
    "content_prompt": "内容风格提示词（用于生成相似风格的图文内容）",
    "visual_prompt": "视觉风格提示词（用于生成封面图）"
  }}
}}
"""


async def analyze_xhs_content(
    title: str,
    description: str,
    images_count: int,
    author: str = "",
    provider: str | None = None,
) -> dict:
    """使用 LLM 分析小红书图文内容"""
    manager = get_manager()
    if not manager.is_loaded() or not manager.get_default(MediaType.LLM):
        return {}

    prompt = XHS_ANALYSIS_PROMPT.format(
        title=title,
        author=author,
        content=description[:3000] if description else "（无正文）",
        images_count=images_count,
    )

    result = await manager.chat(
        [LLMMessage(role="user", content=prompt)],
        provider=provider,
    )

    if not result.success:
        return {}

    content = result.content.strip()
    # 提取 JSON
    if "{" in content and "}" in content:
        start = content.find("{")
        end = content.rfind("}") + 1
        json_str = content[start:end]
    else:
        json_str = content

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return {}


async def analyze_with_llm(
    title: str,
    platform: str,
    author: str,
    transcript: str,
    provider: str | None = None,
) -> dict:
    """使用 LLM 分析视频内容"""
    manager = get_manager()
    if not manager.is_loaded() or not manager.get_default(MediaType.LLM):
        return {}

    prompt = BREAKDOWN_PROMPT.format(
        title=title,
        platform=platform,
        author=author,
        transcript=transcript[:4000] if transcript else "（无字幕）",
    )

    result = await manager.chat(
        [LLMMessage(role="user", content=prompt)],
        provider=provider,
    )

    if not result.success:
        return {}

    # 解析 JSON
    content = result.content.strip()

    # 提取 JSON 块
    if "```" in content:
        start = content.find("```")
        end = content.find("```", start + 3)
        if end > start:
            json_str = content[start + 3:end].strip()
            if json_str.startswith("json"):
                json_str = json_str[4:].strip()
        else:
            json_str = content[start + 3:].strip()
    else:
        json_str = content

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return {}


# =============================================================================
# 主流程
# =============================================================================

async def run_analysis(break_task: BreakTask) -> None:
    """执行完整拆解流程（兼容 Redis 任务队列）"""
    queue = get_task_queue()

    # 获取统一任务对象用于进度更新
    unified_task = await queue.get_task(break_task.task_id)

    async def update_progress(progress: int, message: str = ""):
        """更新进度到 Redis"""
        break_task.progress = progress
        if message:
            break_task.progress_message = message
        if unified_task:
            unified_task.progress = progress
            unified_task.progress_message = message
            await queue.update_progress(break_task.task_id, progress, message)

    break_task.status = AnalysisStatus.PARSING
    await update_progress(5, "检测链接类型...")

    # -------------------------------------------------------------------------
    # 分支1：小红书图文笔记 → XHS 解析流程
    # -------------------------------------------------------------------------
    XHS_PATTERN = re.compile(
        r"xiaohongshu\.com/(explore|discovery/item)|xhs\.cn/t"
    )

    if XHS_PATTERN.search(break_task.url):
        await update_progress(10, "解析小红书笔记...")

        try:
            xhs_parser = get_xhs_parser()
            xhs_note = xhs_parser.parse(break_task.url)

            if xhs_note and (xhs_note.title or xhs_note.description or xhs_note.images):
                await update_progress(30, "小红书笔记解析完成，开始 LLM 分析...")

                # 构建图文分析用的 transcript（description 作为主要内容）
                text_content = f"""标题：{xhs_note.title}\n\n正文：{xhs_note.description}\n\n图片数量：{len(xhs_note.images)}张"""

                manager = get_manager()
                llm_available = manager.is_loaded() and bool(manager.get_default(MediaType.LLM))

                if llm_available:
                    break_task.status = AnalysisStatus.ANALYZING
                    await update_progress(50, "LLM 分析图文内容...")

                    analysis = await analyze_xhs_content(
                        title=xhs_note.title,
                        description=xhs_note.description,
                        images_count=len(xhs_note.images),
                        author=xhs_note.author,
                    )

                    await update_progress(80, "构建拆解结果...")

                    characters = [
                        CharacterExtract(
                            name=c.get("name", f"角色{i+1}"),
                            role=c.get("role", "supporting"),
                            appearance=c.get("appearance", ""),
                            traits=c.get("traits", []),
                        )
                        for i, c in enumerate(analysis.get("characters", []))
                    ]

                    break_task.result = BreakdownResult(
                        title=xhs_note.title,
                        author=xhs_note.author,
                        platform="xiaohongshu",
                        cover_url=xhs_note.cover_url,
                        hook_analysis=analysis.get("hook_analysis", ""),
                        structure=analysis.get("structure", {}),
                        emotion_curve=analysis.get("emotion_curve", []),
                        key_elements=analysis.get("key_elements", {}),
                        style_tags=analysis.get("style_tags", []),
                        viral_factors=analysis.get("viral_factors", []),
                        characters=characters,
                        shots=[],
                        rewrite_prompts=analysis.get("rewrite_prompts", {}),
                        transcript=text_content,
                    )
                else:
                    await update_progress(80, "构建拆解结果...")
                    break_task.result = BreakdownResult(
                        title=xhs_note.title,
                        author=xhs_note.author,
                        platform="xiaohongshu",
                        cover_url=xhs_note.cover_url,
                        hook_analysis="No LLM configured - XHS note parsed (LLM analysis skipped)",
                        style_tags=["图文笔记", "小红书"],
                        viral_factors=[f"获赞 {xhs_note.likes}"],
                        transcript=text_content,
                    )

                break_task.status = AnalysisStatus.DONE
                await update_progress(100, "完成")

                if unified_task:
                    unified_task.result = result_to_dict(break_task.result)
                    unified_task.status = TaskStatus.DONE
                    await queue.update_task(unified_task)
                return

        except Exception as e:
            logger.warning(f"[Breaker] XHS 解析失败，回退到视频解析流程: {e}")

    # -------------------------------------------------------------------------
    # 分支2：视频链接 → 原有视频分析流程
    # -------------------------------------------------------------------------
    await update_progress(10, "解析视频链接...")

    try:
        # Step 1: 解析视频链接
        video_info = await parse_video_url(break_task.url)
        await update_progress(20, "获取视频信息完成")

        video_url = video_info.get("video_url", "")
        cover_url = video_info.get("cover_url", "")
        title = video_info.get("title", "未知标题")
        author_obj = video_info.get("author", {})
        author = author_obj.get("name", "未知作者") if isinstance(author_obj, dict) else str(author_obj)
        platform = video_info.get("platform", "unknown")

        break_task.status = AnalysisStatus.DOWNLOADING
        await update_progress(30, "下载视频...")

        # Step 2: 下载视频（如果可以）
        transcript = ""
        key_frames = []
        download_success = False

        if video_url and video_url.startswith("http"):
            with tempfile.TemporaryDirectory() as tmpdir:
                video_path = os.path.join(tmpdir, "video.mp4")
                audio_path = os.path.join(tmpdir, "audio.mp3")
                frames_dir = os.path.join(tmpdir, "frames")

                download_success = await download_video(break_task.url, video_path, video_url)
                await update_progress(40, "视频下载完成" if download_success else "视频下载失败，使用在线地址")

                if download_success:
                    break_task.status = AnalysisStatus.TRANSCRIBING
                    await update_progress(50, "提取音频并转录...")

                    has_audio = await extract_audio(video_path, audio_path)
                    if has_audio:
                        transcript = await transcribe_audio(audio_path)

                    await update_progress(60, "转录完成")

                    key_frame_paths = await extract_key_frames(
                        video_path, frames_dir, num_frames=5
                    )
                    key_frames = key_frame_paths

        if not download_success:
            video_url = break_task.url

        # Step 3: LLM 分析
        manager = get_manager()
        llm_available = manager.is_loaded() and bool(manager.get_default(MediaType.LLM))

        if llm_available:
            break_task.status = AnalysisStatus.ANALYZING
            await update_progress(70, "LLM 分析中...")

            analysis = await analyze_with_llm(
                title=title,
                platform=platform,
                author=author,
                transcript=transcript,
            )

            await update_progress(90, "构建结果...")

            characters = [
                CharacterExtract(
                    name=c.get("name", f"角色{i+1}"),
                    role=c.get("role", "supporting"),
                    appearance=c.get("appearance", ""),
                    traits=c.get("traits", []),
                )
                for i, c in enumerate(analysis.get("characters", []))
            ]

            shots = [
                ShotExtract(
                    order=s.get("order", i + 1),
                    description=s.get("description", ""),
                    shot_type=s.get("shot_type", "MS"),
                    characters=s.get("characters", []),
                    dialogue=s.get("dialogue", ""),
                    emotion=s.get("emotion", ""),
                )
                for i, s in enumerate(analysis.get("shots", []))
            ]

            break_task.result = BreakdownResult(
                title=title,
                author=author,
                platform=platform,
                video_url=video_url,
                cover_url=cover_url,
                duration_estimate=analysis.get("structure", {}).get("duration_estimate", ""),
                hook_analysis=analysis.get("hook_analysis", ""),
                structure=analysis.get("structure", {}),
                emotion_curve=analysis.get("emotion_curve", []),
                key_elements=analysis.get("key_elements", {}),
                style_tags=analysis.get("style_tags", []),
                viral_factors=analysis.get("viral_factors", []),
                characters=characters,
                shots=shots,
                rewrite_prompts=analysis.get("rewrite_prompts", {}),
                transcript=transcript,
            )
        else:
            await update_progress(90, "构建结果...")
            break_task.result = BreakdownResult(
                title=title,
                author=author,
                platform=platform,
                video_url=video_url,
                cover_url=cover_url,
                duration_estimate="",
                hook_analysis="No LLM configured - video info only (LLM analysis skipped)",
                structure={},
                emotion_curve=[],
                key_elements={},
                style_tags=[],
                viral_factors=[],
                characters=[],
                shots=[],
                rewrite_prompts={},
                transcript=transcript,
            )

        break_task.status = AnalysisStatus.DONE
        await update_progress(100, "完成")

        # 同步结果到 Redis
        if unified_task:
            unified_task.result = result_to_dict(break_task.result)
            unified_task.status = TaskStatus.DONE
            await queue.update_task(unified_task)

    except Exception as e:
        break_task.status = AnalysisStatus.FAILED
        break_task.error = str(e)
        await update_progress(0, f"失败: {str(e)}")

        if unified_task:
            unified_task.error = str(e)
            unified_task.status = TaskStatus.FAILED
            await queue.update_task(unified_task)


# =============================================================================
# 辅助函数
# =============================================================================

def result_to_dict(result: BreakdownResult) -> dict:
    """将结果转换为字典（用于 API 响应 + task_queue 存储）"""
    # 转换 structure dict 为可读字符串
    structure_str = ""
    if result.structure:
        segments = result.structure.get("segments", [])
        pacing = result.structure.get("pacing", "")
        duration_est = result.structure.get("duration_estimate", "")
        structure_str = f"Duration: {duration_est}; Pacing: {pacing}; Segments: {' / '.join(segments)}" if segments or pacing else str(result.structure)

    # 转换 key_elements dict 为 elements 列表
    elements_list: list[str] = []
    if result.key_elements:
        ke = result.key_elements
        for key in ["conflict", "climax", "ending"]:
            val = ke.get(key, "")
            if val:
                elements_list.append(f"{key}: {val}")
    elements_list.extend(result.viral_factors)
    elements_list.extend(result.style_tags)

    return {
        # 前端 BreakerResult 格式（嵌套）
        "report": {
            "hook": result.hook_analysis or "Not analyzed",
            "structure": structure_str,
            "emotion_curve": " / ".join(result.emotion_curve) if result.emotion_curve else "Not analyzed",
            "elements": elements_list,
        },
        "script": [
            {
                "shot": s.order,
                "description": s.description,
                "duration": 0,
                "dialogue": s.dialogue,
            }
            for s in result.shots
        ],
        "prompts": _build_prompts(result),
        "video_url": result.video_url or None,
        # get_task 读取的平铺字段（兼容旧格式）
        "title": result.title,
        "author": result.author,
        "platform": result.platform,
        "cover_url": result.cover_url,
        "duration_estimate": result.duration_estimate,
        "hook_analysis": result.hook_analysis,
        "structure": result.structure or {},
        "emotion_curve": result.emotion_curve or [],
        "key_elements": result.key_elements or {},
        "style_tags": result.style_tags or [],
        "viral_factors": result.viral_factors or [],
        "characters": [asdict(c) for c in result.characters],
        "shots": [asdict(s) for s in result.shots],
        "rewrite_prompts": result.rewrite_prompts or {},
        "transcript": result.transcript,
    }


def _build_prompts(result: BreakdownResult) -> list[dict]:
    """从 result 构建仿写提示词（兼容前端格式）"""
    prompts = []
    rp = result.rewrite_prompts or {}

    character_prompt = rp.get("character_prompt", "")
    scene_prompt = rp.get("scene_prompt", "")
    script_template = rp.get("script_template", "")

    if not character_prompt and result.characters:
        names = [c.name for c in result.characters if c.name]
        character_prompt = f"角色设定：{'，'.join(names)}；外貌：{result.characters[0].appearance}" if result.characters else ""

    if character_prompt:
        prompts.append({"type": "character", "prompt": character_prompt})
    if scene_prompt:
        prompts.append({"type": "scene", "prompt": scene_prompt})
    if script_template:
        prompts.append({"type": "script", "prompt": script_template})

    return prompts
