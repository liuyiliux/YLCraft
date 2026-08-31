"""
YLCraft — 平台事件日志 / 运行日志 API

GET  /api/v1/logs           — 事件日志列表（筛选/分页）
GET  /api/v1/logs/{id}      — 单条事件详情
GET  /api/v1/logs/runtime   — 运行日志（文件 tail，级别/关键词过滤）
POST /api/v1/logs/{id}/retry — 失败事件重发（按场景重放原请求）
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Depends, Query

from app.core.external_api_auth import optional_external_api_key
from app.db.models.external_api_key import ExternalApiKey
from pydantic import BaseModel

from app.services.platform_log import service as platform_log
from app.services.ai import get_ai_service
from app.services.ai.types import ImageGenerationRequest, VideoGenerationRequest
from app.db.models.creative_project import ProjectGenerationLog
from app.db.database import get_session
from app.services.creative_project.service import loads_json
import dataclasses

router = APIRouter()
logger = logging.getLogger("ylcraft.logs")

# 运行日志文件（与 main.py 配置保持一致）
_LOG_FILE = Path(__file__).parent.parent.parent.parent / "storage" / "logs" / "app.log"
_LOG_LEVELS = {"debug", "info", "warning", "error", "critical"}


class EventListResponse(BaseModel):
    success: bool = True
    items: list[dict[str, Any]] = []
    total: int = 0
    page: int = 1
    page_size: int = 50


class EventDetailResponse(BaseModel):
    success: bool = True
    item: dict[str, Any] | None = None


class RuntimeLogLine(BaseModel):
    timestamp: str = ""
    level: str = ""
    module: str = ""
    module_key: str = ""
    name: str = ""
    message: str = ""


class RuntimeLogResponse(BaseModel):
    success: bool = True
    lines: list[RuntimeLogLine] = []
    before: str = ""
    has_more: bool = False


class RetryResponse(BaseModel):
    success: bool = False
    event_id: str | None = None
    task_id: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# 事件日志查询
# ---------------------------------------------------------------------------


@router.get("", response_model=EventListResponse, summary="事件日志列表")
async def list_logs(
    scene: Optional[str] = None,
    level: Optional[str] = None,
    status: Optional[str] = None,
    task_type: Optional[str] = None,
    project_id: Optional[str] = None,
    ref_id: Optional[str] = None,
    q: Optional[str] = None,
    since: Optional[float] = None,
    until: Optional[float] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    external_key: Optional[ExternalApiKey] = Depends(optional_external_api_key),
):
    items, total = await platform_log.list_events(
        scene=scene,
        level=level,
        status=status,
        task_type=task_type,
        project_id=project_id,
        ref_id=ref_id,
        q=q,
        since=since,
        until=until,
        page=page,
        page_size=page_size,
    )
    return EventListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/runtime", response_model=RuntimeLogResponse, summary="运行日志（文件 tail）")
async def list_runtime_logs(
    level: Optional[str] = None,
    module: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(200, ge=1, le=2000),
    before: Optional[str] = None,
):
    if level and level.lower() not in _LOG_LEVELS:
        raise HTTPException(status_code=400, detail="无效的日志级别")
    if not _LOG_FILE.is_file():
        return RuntimeLogResponse(lines=[], has_more=False)

    lines = _read_runtime_lines(_LOG_FILE, limit=limit, before=before)
    filtered: list[RuntimeLogLine] = []
    for raw in lines:
        parsed = _parse_runtime_line(raw)
        if level and parsed.level.lower() != level.lower():
            continue
        if module and parsed.module_key.lower() != module.lower():
            continue
        if q and q.lower() not in parsed.message.lower() and q.lower() not in parsed.name.lower():
            continue
        filtered.append(parsed)

    # before 游标：用首条时间戳继续向前翻页
    next_before = filtered[0].timestamp if filtered else ""
    return RuntimeLogResponse(lines=filtered, before=next_before, has_more=len(filtered) >= limit)


@router.get("/{event_id}", response_model=EventDetailResponse, summary="事件日志详情")
async def get_log(event_id: str):
    item = await platform_log.get_event(event_id)
    if item is None:
        raise HTTPException(status_code=404, detail="事件不存在")
    return EventDetailResponse(item=item)


class GenerationLogResponse(BaseModel):
    success: bool = True
    generation_log: dict[str, Any] | None = None


@router.get("/{event_id}/generation", response_model=GenerationLogResponse, summary="事件的 LLM 完整生成日志")
async def get_log_generation(event_id: str):
    """按事件 id 找到关联的 ProjectGenerationLog，返回完整 prompt/raw_response/normalized。

    generation_log_id 记录在事件 retry_payload_json 中（由 creative writing
    任务在 record_event 时写入）。
    """
    item = await platform_log.get_event(event_id)
    if item is None:
        raise HTTPException(status_code=404, detail="事件不存在")

    retry_payload = item.get("retry_payload") or {}
    generation_log_id = retry_payload.get("generation_log_id")
    if not generation_log_id:
        return GenerationLogResponse(success=True, generation_log=None)

    try:
        with next(get_session()) as session:
            log = session.get(ProjectGenerationLog, generation_log_id)
            if log is None:
                return GenerationLogResponse(success=True, generation_log=None)
            # 复用 creative_projects 的序列化（含 prompt/raw_response/normalized + 乱码修复）
            from app.api.v1.creative_projects import serialize_generation_log

            return GenerationLogResponse(success=True, generation_log=serialize_generation_log(log))
    except Exception as exc:
        logger.warning("Could not load generation log for event %s: %s", event_id, exc)
        return GenerationLogResponse(success=True, generation_log=None)


# ---------------------------------------------------------------------------
# 失败重发
# ---------------------------------------------------------------------------


@router.post("/{event_id}/retry", response_model=RetryResponse, summary="失败事件重发")
async def retry_log(event_id: str):
    item = await platform_log.get_event(event_id)
    if item is None:
        raise HTTPException(status_code=404, detail="事件不存在")
    if item.get("status") != "failed":
        raise HTTPException(status_code=409, detail="只有失败的事件可以重发")
    payload = item.get("retry_payload") or {}
    if not payload:
        raise HTTPException(status_code=400, detail="该事件缺少可重放参数")

    scene = item.get("scene", "")
    manager = get_ai_service()
    if not manager.is_loaded():
        raise HTTPException(status_code=503, detail="AIService 未初始化")

    new_event_id: Optional[str] = None
    new_task_id: Optional[str] = None
    new_error: Optional[str] = None

    try:
        if scene == "image":
            image_payload = _filter_fields(payload, ImageGenerationRequest)
            result = await manager.generate_image(ImageGenerationRequest(**image_payload))
            new_task_id = result.task_id or None
            if result.success:
                new_event_id = await platform_log.record_event(
                    scene="image",
                    task_type="image_generation",
                    task_id=new_task_id,
                    level="info",
                    status="success",
                    provider=result.provider or "",
                    model=result.model or "",
                    message="图片生成重发成功",
                    duration_ms=result.latency_ms,
                    retry_of=event_id,
                )
            else:
                new_error = result.error
        elif scene == "video":
            video_payload = _filter_fields(payload, VideoGenerationRequest)
            result = await manager.generate_video(VideoGenerationRequest(**video_payload))
            new_task_id = result.task_id or None
            if result.success:
                new_event_id = await platform_log.record_event(
                    scene="video",
                    task_type="video_generation",
                    task_id=new_task_id,
                    level="info",
                    status="success",
                    provider=result.provider or "",
                    model=result.model or "",
                    message="视频生成重发成功",
                    duration_ms=result.latency_ms,
                    retry_of=event_id,
                )
            else:
                new_error = result.error
        elif scene == "llm":
            messages = payload.get("messages", [])
            model = payload.get("model")
            result = await manager.chat(messages, model=model)
            if result.success:
                new_event_id = await platform_log.record_event(
                    scene="llm",
                    task_type="llm_chat",
                    level="info",
                    status="success",
                    provider=result.provider or "",
                    model=result.model or model or "",
                    message="文本生成重发成功",
                    duration_ms=result.latency_ms,
                    retry_of=event_id,
                )
            else:
                new_error = result.error
        else:
            raise HTTPException(status_code=400, detail=f"不支持的场景重发: {scene}")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Retry of event %s failed: %s", event_id, exc)
        new_error = str(exc)

    if new_error:
        new_event_id = await platform_log.record_event(
            scene=scene,
            task_type=item.get("task_type", ""),
            level="error",
            status="failed",
            provider=item.get("provider", ""),
            model=item.get("model", ""),
            message="重发失败",
            error=new_error,
            retry_of=event_id,
        )

    if new_event_id:
        await platform_log.link_retried_by(event_id, new_event_id)
        return RetryResponse(success=new_error is None, event_id=new_event_id, task_id=new_task_id, error=new_error)
    return RetryResponse(success=False, error=new_error or "重发未产生结果")


# ---------------------------------------------------------------------------
# 运行日志读取 helper
# ---------------------------------------------------------------------------


def _read_runtime_lines(path: Path, *, limit: int, before: Optional[str]) -> list[str]:
    """读取文件末尾若干行；若给 before，则读到该时间戳之前的行。"""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return []

    lines = [ln for ln in text.splitlines() if ln.strip()]
    if before:
        lines = [ln for ln in lines if ln < before]
    return lines[-limit:]


def _filter_fields(payload: dict[str, Any], dataclass_type: Any) -> dict[str, Any]:
    """只保留 dataclass 接受的字段，避免 lineage 等额外字段导致 TypeError。"""
    valid = {f.name for f in dataclasses.fields(dataclass_type)}
    return {k: v for k, v in payload.items() if k in valid}


def _parse_runtime_line(raw: str) -> RuntimeLogLine:
    # 只把标准日志头中的 logger 识别为模块，避免 JSON/template 内的 ": " 被误判。
    line = RuntimeLogLine(message=raw, module="系统", module_key="system")
    match = re.match(r"^(\S+\s+\S+)\s+(DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+([A-Za-z_][\w.-]*)(?::\s?(.*))?$", raw)
    if match:
        line.timestamp = match.group(1).replace(",", ".")
        line.level = match.group(2)
        line.name = match.group(3)
        line.message = match.group(4) or ""
        line.module_key, line.module = _business_module(line.name, line.message)
    return line


def _business_module(name: str, message: str) -> tuple[str, str]:
    text = f"{name} {message}".lower()
    def has(*terms: str) -> bool:
        return any(term in text for term in terms)

    # 创作项目按生产阶段拆分，方便定位“哪一步”失败。
    if "正文" in message or "novel_body" in text or "refine-novel-body" in text:
        return "creative_project_body", "创作项目-正文"
    if "细纲" in message or "chapter-outline" in text or "chapter_plan" in text:
        return "creative_project_detail_outline", "创作项目-细纲"
    if "大纲" in message or "outline" in text:
        return "creative_project_outline", "创作项目-大纲"
    if "script" in text or "剧本" in message:
        return "creative_project_script", "创作项目-剧本"
    if has("storyboard", "分镜"):
        return "creative_project_storyboard", "创作项目-分镜"
    if "creative_projects" in name or "creative_project" in name:
        return "creative_project", "创作项目"

    # AI 生成与模型基础设施。
    if has("model3d", "3d", "图转3d"):
        return "ai_3d", "AI生3D"
    if has("video", "视频"):
        return "ai_video", "AI生视频"
    if has("image", "图片", "生图"):
        return "ai_image", "AI生图"
    if has("llm", "chat", "文本生成"):
        return "ai_text", "AI文本"
    if "ai.service" in name:
        return "ai_text", "AI文本"
    if has("tts", "语音合成"):
        return "ai_tts", "AI语音"
    if has("stt", "whisper", "语音识别"):
        return "ai_stt", "AI语音识别"
    if has("comfyui"):
        return "comfyui", "ComfyUI工作流"
    if has("connector", "registry", "provider"):
        return "model_config", "模型配置"

    # 资产、提示词与创作辅助。
    if has("asset_hub", "assets", "素材库", "资产"):
        return "asset_hub", "素材库-资产中枢"
    if has("lineage", "血缘"):
        return "asset_lineage", "素材库-资产血缘"
    if has("prompt_reference", "image_prompt", "prompt-library", "提示词"):
        return "prompt_library", "提示词库"
    if has("previs", "导演台", "预演"):
        return "previs", "3D预演"

    # 下载、采集、小说与平台能力。
    if has("download", "下载", "torrent"):
        return "download", "下载中心"
    if has("crawler", "采集", "search"):
        return "crawler", "素材采集"
    if has("bilibili", "b站"):
        return "bilibili", "哔哩哔哩"
    if has("fanqie", "番茄"):
        return "fanqie", "番茄创作"
    if has("wechat_mp", "公众号", "微信"):
        return "wechat", "微信内容"
    if has("up_analytics", "my_data", "creator_data", "创作者数据"):
        return "creator_data", "创作者数据中心"
    if has("novel", "book_source", "bookshelf", "reader", "ebook", "小说"):
        return "novel", "小说阅读与书源"

    # 生产工具与工作台。
    if has("live2d"):
        return "live2d", "Live2D工厂"
    if has("cutclaw", "narrato", "moe", "clip", "jianying", "剪辑"):
        return "clip", "AI剪辑"
    if has("subtitle", "字幕"):
        return "subtitle", "字幕工具"
    if has("bgm", "音乐"):
        return "bgm", "BGM音乐"
    if has("breaker", "爆款拆解"):
        return "breaker", "爆款拆解"
    if has("canvas", "画布"):
        return "canvas", "创作画布"
    if has("agent", "skill", "智能体"):
        return "agent", "Agent智能体"
    if has("export", "导出"):
        return "export", "导出中心"

    # 运行与账号管理。
    if has("account", "cookie", "登录"):
        return "account", "账号与登录"
    if has("task", "任务"):
        return "task", "任务中心"
    if has("platform_log", "logs", "运行日志"):
        return "logs", "日志中心"
    if has("settings", "设置"):
        return "settings", "系统设置"
    if name.startswith("httpx"):
        return "http", "外部接口"
    if name.startswith("ylcraft"):
        return "ylcraft", "系统服务"
    return name or "system", name or "系统"
