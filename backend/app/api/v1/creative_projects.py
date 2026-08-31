"""Creative project workflow API."""

from __future__ import annotations

import io
import json
import re
import time
import zipfile
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.db.database import get_session
from app.db.models.creative_project import (
    CreativeProject,
    ProjectAssetLink,
    ProjectContent,
    ProjectGenerationLog,
    ProjectNarrativeRun,
    ProjectStateEntry,
    NarrativeRunStatus,
)
from app.services.creative_project.service import (
    CreativeProjectService,
    loads_json,
    normalize_chapter_plan,
    repair_utf8_mojibake,
)
from app.services.creative_project.profiles import CONTENT_PRODUCTION_PROFILES
from app.services.creative_project.schemas import ProductionPlanSchema
from app.services.creative_project.narrative_runtime import ChapterAftermathPipeline, NarrativeReviewService
from app.core.task_queue import TaskStatus, get_task_queue
from app.services.platform_log import service as platform_log

router = APIRouter()


def _truncate_for_summary(value: str | None, limit: int = 1000) -> str:
    if not value:
        return ""
    if len(value) <= limit:
        return value
    return value[:limit] + f"... (truncated, total {len(value)} chars)"


def _build_llm_event_extra(generation_log_id: str | None) -> dict[str, Any]:
    """从 ProjectGenerationLog 读出 prompt/raw_response/normalized 等，
    写进 platform_event 的 request/response/retry_payload_json，让用户在
    事件详情里能看到完整 LLM 请求与返回。

    返回字段会赋给 record_event 的 request（与 payload 合并）、response、
    以及 retry_payload_json（除 retry 字段外附加 generation_log_id）。
    """
    if not generation_log_id:
        return {}
    try:
        with next(get_session()) as session:
            log = session.get(ProjectGenerationLog, generation_log_id)
            if not log:
                return {}
            req_json = loads_json(log.request_json) if log.request_json else {}
            prompt_text = log.prompt or ""
            raw = log.raw_response or ""
            normalized = loads_json(log.normalized_json) if log.normalized_json else {}
            return {
                "request_extra": {
                    "messages": req_json.get("messages") if isinstance(req_json, dict) else None,
                    "params": req_json.get("params") if isinstance(req_json, dict) else None,
                    "template_id": req_json.get("template_id") if isinstance(req_json, dict) else None,
                    "prompt": prompt_text,
                    "raw_response_preview": _truncate_for_summary(raw, 1500),
                    "normalized_keys": list(normalized.keys()) if isinstance(normalized, dict) else None,
                },
                "response": {
                    "raw_response": raw,
                    "raw_response_preview": _truncate_for_summary(raw, 1500),
                    "normalized": normalized,
                    "validation_error": log.validation_error,
                },
                "generation_log_id": generation_log_id,
            }
    except Exception as e:  # noqa: BLE001
        return {"generation_lookup_error": str(e)}


async def _run_creative_task(task_type: str, payload: dict[str, Any], operation):
    """Record synchronous creative generation in the shared task center."""
    queue = get_task_queue()
    task = await queue.create_task(task_type, payload)
    await queue.update_progress(task.task_id, 5, f"开始{payload.get('stage_label') or '创作请求'}")
    try:
        result = await operation()
        tracked = await queue.get_task(task.task_id)
        if tracked:
            tracked.status = TaskStatus.DONE
            tracked.progress = 100
            tracked.progress_message = f"{payload.get('stage_label') or '创作请求'}完成"
            if isinstance(result, dict):
                tracked.result = result
            elif hasattr(result, "model_dump"):
                tracked.result = result.model_dump()
            elif hasattr(result, "dict"):
                tracked.result = result.dict()
            else:
                tracked.result = {"value": str(result)}
            tracked.completed_at = time.time()
            await queue.update_task(tracked)
        # 把 service 留下的 __generation_log_id__ 提出来，并查出 LLM 详细
        log_id = None
        if isinstance(result, dict):
            log_id = result.pop("__generation_log_id__", None)
        extra = _build_llm_event_extra(log_id)
        event_request = dict(payload)
        if extra.get("request_extra"):
            event_request["llm_detail"] = extra["request_extra"]
        event_response: dict[str, Any] = {"result_type": type(result).__name__}
        if extra.get("response"):
            event_response = {**event_response, **extra["response"]}
        retry_payload = {**(payload.get("retry_payload") or {})}
        if extra.get("generation_log_id"):
            retry_payload["generation_log_id"] = extra["generation_log_id"]
        await platform_log.record_event(
            scene="writing",
            task_type=task_type,
            task_id=task.task_id,
            level="info",
            status="success",
            provider=str(payload.get("provider") or ""),
            model=str(payload.get("model") or ""),
            message=f"{payload.get('stage_label') or '创作请求'}完成",
            request=event_request,
            response=event_response,
            project_id=str(payload.get("project_id") or "") or None,
            retry_payload=retry_payload,
        )
        return result
    except Exception as exc:
        tracked = await queue.get_task(task.task_id)
        if tracked:
            tracked.status = TaskStatus.FAILED
            tracked.progress_message = f"{payload.get('stage_label') or '创作请求'}失败"
            tracked.error = str(exc)
            tracked.completed_at = time.time()
            await queue.update_task(tracked)
        # 失败时也尝试把 service 的 _last_generation_log 关联进来，便于排查
        retry_payload = {**(payload.get("retry_payload") or {})}
        try:
            from app.services.creative_project.service import CreativeProjectService  # noqa
            # 找最近一次成功的 generation log（同一 project + stage 上一条）
            project_id = str(payload.get("project_id") or "")
            stage = str(payload.get("stage") or "")
            if project_id and stage:
                with next(get_session()) as session:
                    log = session.exec(
                        select(ProjectGenerationLog)
                        .where(ProjectGenerationLog.project_id == project_id)
                        .where(ProjectGenerationLog.stage == stage)
                        .order_by(ProjectGenerationLog.created_at.desc())
                    ).first()
                    if log:
                        retry_payload["generation_log_id"] = log.id
        except Exception:  # noqa: BLE001
            pass
        await platform_log.record_event(
            scene="writing",
            task_type=task_type,
            task_id=task.task_id,
            level="error",
            status="failed",
            provider=str(payload.get("provider") or ""),
            model=str(payload.get("model") or ""),
            message=f"{payload.get('stage_label') or '创作请求'}失败",
            error=str(exc),
            request=payload,
            project_id=str(payload.get("project_id") or "") or None,
            retry_payload=retry_payload,
        )
        raise


class CreativeProjectCreateRequest(BaseModel):
    title: str = ""
    idea: str = ""
    project_type: str = "short_drama"
    production_profile: str | None = None
    source_type: str = "original_idea"
    source_ref: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    character_id: str | None = Field(default=None, description="可选：创建后立即绑定的角色 ID，并写入初始项目大纲")


class CreativeProjectUpdateRequest(BaseModel):
    title: str | None = None
    project_type: str | None = None
    source_type: str | None = None
    status: str | None = None
    current_stage: str | None = None
    source_ref: dict[str, Any] | None = None
    outline: dict[str, Any] | None = None
    chapter_plan: dict[str, Any] | None = None
    settings: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    canvas: dict[str, Any] | None = None


class FillDemoDataRequest(BaseModel):
    overwrite: bool = Field(default=False, description="是否覆盖项目已有阶段内容")


class SyncProjectBibleRequest(BaseModel):
    overwrite: bool = Field(default=False, description="是否从当前大纲重新创建圣经/世界资产版本")


class GenerateOutlineRequest(BaseModel):
    idea: str = ""
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None


class ExtractCharactersRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    max_characters: int = Field(default=30, ge=1, le=30)
    apply: bool = Field(default=False, description="是否将预览结果写入角色库和项目大纲")
    cards: list[dict[str, Any]] | None = Field(
        default=None,
        description="确认写入时可传回预览返回的 characters，避免重新调用模型",
    )


class GenerateChapterPlanRequest(BaseModel):
    chapter_count: int = Field(default=12, ge=1, le=200)
    append_existing: bool = Field(default=False, description="保留当前章节规划，只补齐到目标章节数")
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None


class GenerateScriptRequest(BaseModel):
    chapter_number: int = Field(default=1, ge=1)
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None


class GenerateChapterOutlineRequest(BaseModel):
    chapter_number: int = Field(default=1, ge=1)
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None


class GenerateNovelBodyRequest(BaseModel):
    chapter_number: int = Field(default=1, ge=1)
    content_id: str | None = None
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None


class RefineNovelBodyRequest(BaseModel):
    content_id: str
    instruction: str
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None


class SplitComicPagesRequest(BaseModel):
    chapter_number: int = Field(default=1, ge=1)
    content_id: str | None = None
    page_count: int = Field(default=10, ge=1, le=80)
    visual_style: str | None = None
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None


class GenerateStoryboardRequest(BaseModel):
    content_id: str
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None


class MatchReferenceAssetsRequest(BaseModel):
    content_id: str
    provider: str | None = None
    model: str | None = None


class CreateFromNovelRequest(BaseModel):
    asset_id: str
    chapter_ids: list[str] = Field(default_factory=list)
    chapter_indices: list[int] = Field(default_factory=list)
    title: str = ""
    project_type: str = "short_drama"
    production_profile: str | None = None


class ProjectAssetLinkRequest(BaseModel):
    asset_id: str
    content_id: str | None = None
    role: str = "reference"
    relation: str = "references"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectContentUpdateRequest(BaseModel):
    title: str | None = None
    data: dict[str, Any] | None = None
    text_content: str | None = None
    is_locked: bool | None = None


class ContentPackageSaveRequest(BaseModel):
    """Save a versioned lightweight package owned by one project."""

    package: dict[str, Any]
    source_content_id: str | None = None


class ContentPackagePlanRequest(BaseModel):
    topic: str = ""
    brief: str = ""
    item_count: int = Field(default=12, ge=1, le=80)
    prompt_only: bool = False
    provider: str | None = None
    model: str | None = None


class ProductionPlanSaveRequest(BaseModel):
    """Append an editable production-plan revision for the current project."""

    plan: ProductionPlanSchema
    base_plan_id: str | None = None


class NarrativeAftermathRequest(BaseModel):
    """Explicit replay trigger; it never promotes or edits prose."""

    pipeline_version: str = Field(default="v1", min_length=1, max_length=32)


class NarrativeRebuildRequest(BaseModel):
    chapter_numbers: list[int] = Field(default_factory=list)


class NarrativeBatchRunRequest(BaseModel):
    chapter_numbers: list[int] = Field(default_factory=list)
    max_cost_amount: float | None = Field(default=None, ge=0)
    max_token_usage: int | None = Field(default=None, ge=0)


class NarrativeAutopilotRequest(BaseModel):
    enabled: bool = False
    chapter_numbers: list[int] = Field(default_factory=list)
    max_chapters_per_run: int = Field(default=3, ge=1, le=20)
    max_consecutive_failures: int = Field(default=2, ge=1, le=5)


class ForeshadowingDecisionRequest(BaseModel):
    note: str = Field(default="", max_length=2000)
    current_chapter: int | None = Field(default=None, ge=1)


class RegenerateChapterOutlineScenesRequest(BaseModel):
    content_id: str
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None


class CanvasSaveRequest(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    viewport: dict[str, Any] = Field(default_factory=dict)


class RunPipelineRequest(BaseModel):
    stages: list[str] = Field(default_factory=list)
    chapters: list[int] = Field(default_factory=list)
    chapter_count: int | None = Field(default=None, ge=1, le=200)
    page_count: int = Field(default=10, ge=1, le=80)
    visual_style: str | None = None
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None
    skip_existing: bool = True
    continue_on_error: bool = False
    match_source_type: str = "storyboard"


class WriterRoomStepRequest(BaseModel):
    chapter_number: int = Field(default=1, ge=1)
    content_id: str | None = None
    instruction: str | None = None
    selected_text: str | None = None
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None
    rehearsal_mode: str = Field(default="team", description="fast | team（角色演绎团队模式）")


class WriterRoomRunRequest(BaseModel):
    chapter_number: int = Field(default=1, ge=1)
    steps: list[str] = Field(default_factory=list)
    content_id: str | None = None
    instruction: str | None = None
    selected_text: str | None = None
    provider: str | None = None
    model: str | None = None
    template_id: str | None = None
    rehearsal_mode: str = Field(default="team", description="fast | team（角色演绎团队模式）")
    continue_on_error: bool = True


class WriterRoomPromoteRequest(BaseModel):
    content_id: str


def service(session: Session = Depends(get_session)) -> CreativeProjectService:
    return CreativeProjectService(session)


def _serialize_narrative_run(run: ProjectNarrativeRun) -> dict[str, Any]:
    input_data = loads_json(run.input_json, {})
    budget = input_data.get("budget", {}) if isinstance(input_data, dict) else {}
    return {
        "id": run.id,
        "project_id": run.project_id,
        "mode": run.mode,
        "status": run.status,
        "pipeline_version": run.pipeline_version,
        "target_chapters": loads_json(run.target_chapters_json, []),
        "input": input_data,
        "trace": loads_json(run.trace_json, []),
        "context_snapshot_ids": loads_json(run.context_snapshot_ids_json, []),
        "current_cursor": run.current_cursor,
        "retry_count": run.retry_count,
        "token_usage": run.token_usage,
        "cost_amount": run.cost_amount,
        "budget": budget,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def _execute_narrative_batch_background(project_id: str, run_id: str) -> None:
    """Use an isolated session: request sessions cannot outlive the response."""
    from app.db.database import SessionLocal

    with SessionLocal() as session:
        try:
            ChapterAftermathPipeline(session).resume_batch_run(project_id, run_id)
        except Exception:
            # The durable run record is the source of truth. A later explicit
            # resume can retry a pending run after provider/database recovery.
            session.rollback()


@router.get("/{project_id}/narrative/runs", summary="列出项目叙事运行记录")
def list_narrative_runs(
    project_id: str,
    limit: int = Query(default=30, ge=1, le=100),
    svc: CreativeProjectService = Depends(service),
):
    if svc.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="创作项目不存在")
    rows = svc.session.exec(
        select(ProjectNarrativeRun)
        .where(ProjectNarrativeRun.project_id == project_id)
        .order_by(ProjectNarrativeRun.created_at.desc())
        .limit(limit)
    ).all()
    return {"success": True, "data": [_serialize_narrative_run(item) for item in rows]}


@router.post("/{project_id}/narrative/runs", summary="创建后台叙事批次运行")
def create_narrative_batch_run(
    project_id: str,
    req: NarrativeBatchRunRequest,
    background_tasks: BackgroundTasks,
    svc: CreativeProjectService = Depends(service),
):
    try:
        run = ChapterAftermathPipeline(svc.session).create_batch_run(
            project_id,
            chapter_numbers=req.chapter_numbers,
            input_data={
                "budget": {
                    "max_cost_amount": req.max_cost_amount,
                    "max_token_usage": req.max_token_usage,
                    "metering": "narrative_aftermath_deterministic_zero_cost",
                },
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(_execute_narrative_batch_background, project_id, run.id)
    return {"success": True, "data": _serialize_narrative_run(run)}


@router.put("/{project_id}/narrative/autopilot", summary="配置并启动受控叙事自动推进")
def configure_narrative_autopilot(
    project_id: str,
    req: NarrativeAutopilotRequest,
    background_tasks: BackgroundTasks,
    svc: CreativeProjectService = Depends(service),
):
    project = svc.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="创作项目不存在")
    settings = loads_json(project.settings_json)
    policy = {
        "enabled": req.enabled,
        "max_chapters_per_run": req.max_chapters_per_run,
        "max_consecutive_failures": req.max_consecutive_failures,
        "scope": "approved_prose_aftermath_only",
    }
    settings["narrative_autopilot"] = policy
    svc.update_project(project_id, {"settings": settings})
    if not req.enabled:
        return {"success": True, "data": {"policy": policy, "run": None}}
    requested = req.chapter_numbers[:req.max_chapters_per_run]
    run = ChapterAftermathPipeline(svc.session).create_batch_run(
        project_id,
        chapter_numbers=requested,
        mode="guarded_autopilot",
        input_data={"autopilot_policy": policy},
    )
    background_tasks.add_task(_execute_narrative_batch_background, project_id, run.id)
    return {"success": True, "data": {"policy": policy, "run": _serialize_narrative_run(run)}}


@router.post("/{project_id}/narrative/runs/{run_id}/{action}", summary="控制叙事批次运行")
def control_narrative_run(
    project_id: str,
    run_id: str,
    action: str,
    background_tasks: BackgroundTasks,
    svc: CreativeProjectService = Depends(service),
):
    run = svc.session.get(ProjectNarrativeRun, run_id)
    if run is None or run.project_id != project_id:
        raise HTTPException(status_code=404, detail="叙事运行不存在")
    if run.mode not in {"batch", "guarded_autopilot"}:
        raise HTTPException(status_code=400, detail="只有批次叙事运行可以控制")
    normalized = action.strip().lower()
    terminal = {NarrativeRunStatus.SUCCESS.value, NarrativeRunStatus.PARTIAL.value, NarrativeRunStatus.FAILED.value, NarrativeRunStatus.CANCELLED.value}
    if normalized == "pause":
        if run.status != NarrativeRunStatus.RUNNING.value:
            raise HTTPException(status_code=409, detail="只有运行中的批次可以暂停")
        run.status = NarrativeRunStatus.PAUSED.value
    elif normalized == "resume":
        if run.status != NarrativeRunStatus.PAUSED.value:
            raise HTTPException(status_code=409, detail="只有已暂停的批次可以恢复")
        run.status = NarrativeRunStatus.PENDING.value
        background_tasks.add_task(_execute_narrative_batch_background, project_id, run.id)
    elif normalized == "retry":
        if run.status not in {NarrativeRunStatus.PARTIAL.value, NarrativeRunStatus.FAILED.value}:
            raise HTTPException(status_code=409, detail="只有部分完成或失败的批次可以重试")
        targets = [int(item) for item in loads_json(run.target_chapters_json, []) if int(item) > 0]
        trace = loads_json(run.trace_json, [])
        failed_chapters = {
            int(item.get("chapter_number"))
            for item in trace
            if isinstance(item, dict) and item.get("status") == "failed" and item.get("chapter_number") is not None
        }
        first_failed_index = next((index for index, chapter in enumerate(targets) if chapter in failed_chapters), None)
        if first_failed_index is None:
            raise HTTPException(status_code=409, detail="运行记录中没有可重试的失败章节")
        run.current_cursor = first_failed_index
        run.retry_count += 1
        run.status = NarrativeRunStatus.PENDING.value
        run.error_message = ""
        run.finished_at = None
        background_tasks.add_task(_execute_narrative_batch_background, project_id, run.id)
    elif normalized == "cancel":
        if run.status in terminal:
            raise HTTPException(status_code=409, detail="终态批次不能取消")
        run.status = NarrativeRunStatus.CANCELLED.value
        run.finished_at = datetime.now()
    else:
        raise HTTPException(status_code=400, detail="操作仅支持 pause、resume、retry 或 cancel")
    run.updated_at = datetime.now()
    svc.session.add(run)
    svc.session.commit()
    svc.session.refresh(run)
    return {"success": True, "data": _serialize_narrative_run(run)}


@router.get("", summary="列出创作项目")
def list_projects(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str | None = None,
    project_type: str | None = None,
    svc: CreativeProjectService = Depends(service),
):
    projects, total = svc.list_projects(
        limit=limit,
        offset=offset,
        status=status,
        project_type=project_type,
    )
    return {
        "success": True,
        "data": [serialize_project(p) for p in projects],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("", summary="创建创作项目")
def create_project(
    req: CreativeProjectCreateRequest,
    svc: CreativeProjectService = Depends(service),
):
    project = svc.create_project(
        title=req.title,
        idea=req.idea,
        project_type=req.project_type,
        source_type=req.source_type,
        source_ref=req.source_ref,
        settings=req.settings,
        metadata=req.metadata,
        production_profile=req.production_profile,
        character_id=req.character_id,
    )
    return {"success": True, "data": serialize_project(project)}


@router.get("/profiles", summary="列出内容生产方案")
def list_production_profiles():
    """Return the declarative profile catalog used by project creation UIs."""

    return {
        "success": True,
        "data": [
            {
                "id": profile_id,
                **profile,
            }
            for profile_id, profile in CONTENT_PRODUCTION_PROFILES.items()
        ],
    }


@router.post("/from-novel", summary="从小说章节创建创作项目")
def create_from_novel(
    req: CreateFromNovelRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        project = svc.create_from_novel(
            asset_id=req.asset_id,
            chapter_ids=req.chapter_ids,
            chapter_indices=req.chapter_indices,
            title=req.title,
            project_type=req.project_type,
            production_profile=req.production_profile,
        )
        return {"success": True, "data": serialize_project(project)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/extract-characters", summary="两趟提取项目/小说角色")
async def extract_project_characters(
    project_id: str,
    req: ExtractCharactersRequest,
    svc: CreativeProjectService = Depends(service),
):
    """Scan source text, merge aliases, then build YLCraft character cards.

    ``apply=false`` is the human review path. Agent callers can set
    ``apply=true`` after inspecting the returned cards and merge candidates.
    """
    try:
        data = await svc.extract_character_cards(
            project_id,
            provider=req.provider,
            model=req.model,
            max_characters=req.max_characters,
            apply=req.apply,
            cards=req.cards,
        )
        return {"success": True, "data": data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{project_id}", summary="获取创作项目详情")
def get_project(
    project_id: str,
    svc: CreativeProjectService = Depends(service),
):
    project = svc.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="创作项目不存在")
    return {"success": True, "data": serialize_project(project)}


@router.get("/{project_id}/production-plan", summary="读取创作导演生产计划")
def get_production_plan(
    project_id: str,
    include_history: bool = False,
    svc: CreativeProjectService = Depends(service),
):
    try:
        result = svc.get_production_plan(project_id, include_history=include_history)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    if include_history:
        return {"success": True, "data": [serialize_content(item) for item in result]}
    return {"success": True, "data": serialize_content(result) if result else None}


@router.put("/{project_id}/production-plan", summary="保存创作导演生产计划新版本")
def save_production_plan(
    project_id: str,
    req: ProductionPlanSaveRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        content = svc.save_production_plan(
            project_id=project_id,
            plan=req.plan,
            base_plan_id=req.base_plan_id,
        )
        return {"success": True, "data": serialize_content(content)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{project_id}/narrative/health", summary="检查小说叙事数据健康状态")
def get_narrative_health(
    project_id: str,
    svc: CreativeProjectService = Depends(service),
):
    try:
        return {"success": True, "data": svc.narrative_health(project_id).model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{project_id}/narrative/context-preview", summary="预览下一章叙事上下文包")
def preview_narrative_context(
    project_id: str,
    chapter_number: int = Query(default=1, ge=1),
    svc: CreativeProjectService = Depends(service),
):
    try:
        return {
            "success": True,
            "data": svc.preview_narrative_context(project_id, chapter_number=chapter_number),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{project_id}/state", summary="查看项目动态状态当前值")
def get_project_state(
    project_id: str,
    svc: CreativeProjectService = Depends(service),
):
    """返回折叠后的当前动态状态：{scope: {key: value}}。"""
    from app.services.creative_project.state_ledger import StateLedger

    state = StateLedger.compute_state(svc.session, project_id)
    return {"success": True, "data": state}


@router.get("/{project_id}/state/timeline", summary="查看项目动态状态按章变化轨迹")
def get_project_state_timeline(
    project_id: str,
    svc: CreativeProjectService = Depends(service),
):
    """返回按章有序的状态变更台账（章节即时间顺序）。"""
    entries = svc.session.exec(
        select(ProjectStateEntry)
        .where(ProjectStateEntry.project_id == project_id)
        .order_by(ProjectStateEntry.chapter_number.asc(), ProjectStateEntry.created_at.asc())
    ).all()
    timeline = [
        {
            "id": e.id,
            "scope": e.scope,
            "key": e.key,
            "op": e.op,
            "value": loads_json(e.value_json),
            "chapter_number": e.chapter_number,
            "source_content_id": e.source_content_id,
            "source_version": e.source_version,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]
    return {"success": True, "data": timeline}


@router.get("/{project_id}/writing-preflight", summary="检查写作阶段前置条件")
def get_writing_preflight(
    project_id: str,
    chapter_number: int = Query(default=1, ge=1),
    stage: str = Query(default="novel_body"),
    content_id: str | None = Query(default=None),
    svc: CreativeProjectService = Depends(service),
):
    try:
        return {"success": True, "data": svc.writing_preflight(
            project_id, chapter_number=chapter_number, stage=stage, content_id=content_id,
        )}
    except ValueError as e:
        status_code = 404 if "not found" in str(e).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(e)) from e


@router.post("/{project_id}/contents/{content_id}/aftermath", summary="从正式正文建立叙事后处理状态")
def run_narrative_aftermath(
    project_id: str,
    content_id: str,
    req: NarrativeAftermathRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        # The pipeline owns its derived tables but shares the request session;
        # approved prose remains untouched if an enrichment stage is partial.
        pipeline = ChapterAftermathPipeline(svc.session)
        if req.pipeline_version != pipeline.pipeline_version:
            raise ValueError(f"不支持的叙事后处理版本：{req.pipeline_version}")
        result = pipeline.run(project_id, content_id)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/narrative/rebuild", summary="按正式章节顺序重建叙事状态")
def rebuild_narrative_state(
    project_id: str,
    req: NarrativeRebuildRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        return {
            "success": True,
            "data": ChapterAftermathPipeline(svc.session).rebuild(
                project_id,
                chapter_numbers=req.chapter_numbers,
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{project_id}/foreshadowing", summary="列出项目伏笔台账")
def list_foreshadowing(
    project_id: str,
    status: list[str] = Query(default=[]),
    chapter_number: int | None = Query(default=None, ge=1),
    svc: CreativeProjectService = Depends(service),
):
    try:
        return {
            "success": True,
            "data": NarrativeReviewService(svc.session).list_foreshadowing(
                project_id, statuses=status, chapter_number=chapter_number
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/foreshadowing/{item_id}/{action}", summary="确认、推进、解决或忽略伏笔")
def decide_foreshadowing(
    project_id: str,
    item_id: str,
    action: str,
    req: ForeshadowingDecisionRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        return {
            "success": True,
            "data": NarrativeReviewService(svc.session).decide_foreshadowing(
                project_id,
                item_id,
                action=action,
                note=req.note,
                current_chapter=req.current_chapter,
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{project_id}/narrative-graph", summary="查询项目叙事关系图谱")
def get_narrative_graph(
    project_id: str,
    node_type: list[str] = Query(default=[]),
    chapter_number: int | None = Query(default=None, ge=1),
    include_pending: bool = Query(default=False),
    svc: CreativeProjectService = Depends(service),
):
    try:
        return {
            "success": True,
            "data": NarrativeReviewService(svc.session).narrative_graph(
                project_id,
                node_types=node_type,
                chapter_number=chapter_number,
                include_pending=include_pending,
            ),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _export_content_markdown(content: dict[str, Any]) -> str:
    title = content.get("title") or content.get("content_type") or "项目内容"
    body = str(content.get("text_content") or "").strip()
    lines = [f"# {title}", ""]
    if body:
        lines.append(body)
        lines.append("")
    data = content.get("data") or {}
    if data:
        lines.extend(["## 结构化数据", "", "```json", json.dumps(data, ensure_ascii=False, indent=2), "```"])
    return "\n".join(lines).rstrip() + "\n"


def _export_content_filename(content: dict[str, Any], index: int) -> str:
    content_type = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(content.get("content_type") or "content"))
    chapter = content.get("chapter_number") or content.get("episode_number")
    chapter_label = f"chapter-{int(chapter):03d}-" if isinstance(chapter, int) else ""
    version = content.get("version") or 1
    return f"contents/{index:03d}-{chapter_label}{content_type}-v{version}.md"


@router.get("/{project_id}/export", summary="导出创作项目 ZIP")
def export_project_zip(
    project_id: str,
    svc: CreativeProjectService = Depends(service),
):
    try:
        export = svc.build_project_export(project_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("project.json", json.dumps(export["project"], ensure_ascii=False, indent=2))
        archive.writestr("contents/index.json", json.dumps(export["contents"], ensure_ascii=False, indent=2))
        archive.writestr("assets/manifest.json", json.dumps(export["asset_manifest"], ensure_ascii=False, indent=2))
        archive.writestr(
            "README.md",
            "# YLCraft 创作项目导出\n\n"
            "本包包含项目快照、所有项目内容版本的 Markdown/JSON 与关联素材血缘清单。"
            "素材文件本体仍由 Asset Hub 管理，使用 assets/manifest.json 中的 asset_id 追溯。\n",
        )
        for index, content in enumerate(export["contents"], start=1):
            archive.writestr(_export_content_filename(content, index), _export_content_markdown(content))
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="ylcraft-project-export.zip"'},
    )


@router.patch("/{project_id}", summary="更新创作项目")
def update_project(
    project_id: str,
    req: CreativeProjectUpdateRequest,
    svc: CreativeProjectService = Depends(service),
):
    data = req.model_dump(exclude_unset=True)
    try:
        project = svc.update_project(project_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not project:
        raise HTTPException(status_code=404, detail="创作项目不存在")
    return {"success": True, "data": serialize_project(project)}


@router.delete("/{project_id}", summary="删除创作项目")
def delete_project(
    project_id: str,
    svc: CreativeProjectService = Depends(service),
):
    try:
        stats = svc.delete_project(project_id)
        return {"success": True, "data": stats}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{project_id}/fill-demo-data", summary="为创作项目补充示例大纲、正文、脚本和分镜")
def fill_demo_data(
    project_id: str,
    req: FillDemoDataRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        result = svc.fill_demo_data(project_id, overwrite=req.overwrite)
        return {
            "success": True,
            "data": result["changed"],
            "project": serialize_project(result["project"]),
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{project_id}/sync-project-bible", summary="从故事大纲同步项目圣经和世界资产")
def sync_project_bible(
    project_id: str,
    req: SyncProjectBibleRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        contents = svc.sync_project_bible(project_id, overwrite=req.overwrite)
        return {"success": True, "data": [serialize_content(content) for content in contents]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/contents/{content_id}/extract-continuity", summary="从正文提取连续性候选卡")
def extract_continuity_candidates(
    project_id: str,
    content_id: str,
    svc: CreativeProjectService = Depends(service),
):
    try:
        candidates = svc.extract_continuity_candidates(project_id, content_id)
        return {"success": True, "data": [serialize_content(item) for item in candidates]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/generate-outline", summary="生成故事大纲")
async def generate_outline(
    project_id: str,
    req: GenerateOutlineRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = await _run_creative_task(
            "creative_writing",
            {"project_id": project_id, "stage": "outline", "stage_label": "生成故事大纲"},
            lambda: svc.generate_outline(project_id, idea=req.idea, provider=req.provider, model=req.model, template_id=req.template_id),
        )
        project = svc.get_project(project_id)
        return {"success": True, "data": data, "project": serialize_project(project) if project else None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/generate-chapter-plan", summary="生成章节规划")
async def generate_chapter_plan(
    project_id: str,
    req: GenerateChapterPlanRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = await _run_creative_task(
            "creative_writing",
            {"project_id": project_id, "stage": "chapter_plan", "stage_label": "生成章节规划", "chapter_count": req.chapter_count},
            lambda: svc.generate_chapter_plan(project_id, chapter_count=req.chapter_count, append_existing=req.append_existing, provider=req.provider, model=req.model, template_id=req.template_id),
        )
        project = svc.get_project(project_id)
        return {"success": True, "data": data, "project": serialize_project(project) if project else None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/run-pipeline", summary="Run creative project production pipeline")
async def run_pipeline(
    project_id: str,
    req: RunPipelineRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = await svc.run_pipeline(
            project_id,
            stages=req.stages,
            chapters=req.chapters,
            chapter_count=req.chapter_count,
            page_count=req.page_count,
            visual_style=req.visual_style,
            provider=req.provider,
            model=req.model,
            template_id=req.template_id,
            skip_existing=req.skip_existing,
            continue_on_error=req.continue_on_error,
            match_source_type=req.match_source_type,
        )
        project = svc.get_project(project_id)
        return {"success": True, "data": data, "project": serialize_project(project) if project else None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/generate-script", summary="生成短剧脚本")
async def generate_script(
    project_id: str,
    req: GenerateScriptRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = await _run_creative_task(
            "creative_writing",
            {"project_id": project_id, "stage": "script", "stage_label": "生成短剧脚本", "chapter_number": req.chapter_number},
            lambda: svc.generate_script(project_id, chapter_number=req.chapter_number, provider=req.provider, model=req.model, template_id=req.template_id),
        )
        return {"success": True, "data": data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/generate-chapter-outline", summary="生成单话细纲")
async def generate_chapter_outline(
    project_id: str,
    req: GenerateChapterOutlineRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = await _run_creative_task(
            "creative_writing",
            {"project_id": project_id, "stage": "chapter_outline", "stage_label": "生成单话细纲", "chapter_number": req.chapter_number},
            lambda: svc.generate_chapter_outline(project_id, chapter_number=req.chapter_number, provider=req.provider, model=req.model, template_id=req.template_id),
        )
        project = svc.get_project(project_id)
        return {"success": True, "data": data, "project": serialize_project(project) if project else None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/generate-novel-body", summary="生成章节正文")
async def generate_novel_body(
    project_id: str,
    req: GenerateNovelBodyRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = await _run_creative_task(
            "creative_writing",
            {"project_id": project_id, "stage": "novel_body", "stage_label": "生成正文", "chapter_number": req.chapter_number, "content_id": req.content_id or ""},
            lambda: svc.generate_novel_body(project_id, chapter_number=req.chapter_number, content_id=req.content_id, provider=req.provider, model=req.model, template_id=req.template_id),
        )
        project = svc.get_project(project_id)
        return {"success": True, "data": data, "project": serialize_project(project) if project else None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/refine-novel-body", summary="按中文要求微调章节正文")
async def refine_novel_body(
    project_id: str,
    req: RefineNovelBodyRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        content = await _run_creative_task(
            "creative_writing",
            {"project_id": project_id, "stage": "novel_body_refine", "stage_label": "正文润色", "content_id": req.content_id},
            lambda: svc.refine_novel_body(project_id=project_id, content_id=req.content_id, instruction=req.instruction, provider=req.provider, model=req.model, template_id=req.template_id),
        )
        return {"success": True, "data": serialize_content(content)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/writer-room/step/{step}", summary="Run one novel writer-room step")
async def run_writer_room_step(
    project_id: str,
    step: str,
    req: WriterRoomStepRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        content = await _run_creative_task(
            "creative_writing",
            {"project_id": project_id, "stage": f"writer_room:{step}", "stage_label": f"Writer Room · {step}", "chapter_number": req.chapter_number, "content_id": req.content_id or ""},
            lambda: svc.run_writer_room_step(project_id, step=step, chapter_number=req.chapter_number, content_id=req.content_id, instruction=req.instruction, selected_text=req.selected_text, provider=req.provider, model=req.model, template_id=req.template_id, rehearsal_mode=req.rehearsal_mode),
        )
        return {"success": True, "data": serialize_content(content)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/writer-room/run", summary="Run selected novel writer-room steps")
async def run_writer_room(
    project_id: str,
    req: WriterRoomRunRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = await _run_creative_task(
            "creative_writing",
            {"project_id": project_id, "stage": "writer_room_run", "stage_label": "Writer Room 批量运行", "chapter_number": req.chapter_number, "steps": req.steps},
            lambda: svc.run_writer_room(project_id, steps=req.steps, chapter_number=req.chapter_number, content_id=req.content_id, instruction=req.instruction, selected_text=req.selected_text, provider=req.provider, model=req.model, template_id=req.template_id, rehearsal_mode=req.rehearsal_mode, continue_on_error=req.continue_on_error),
        )
        generated_ids = [
            str(item.get("content_id"))
            for item in data.get("results", [])
            if item.get("status") == "success" and item.get("content_id")
        ]
        session = getattr(svc, "session", None)
        data["results_contents"] = [
            serialize_content(content)
            for content_id in generated_ids
            if session is not None
            and (content := session.get(ProjectContent, content_id)) is not None
        ]
        return {"success": True, "data": data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/writer-room/promote", summary="Promote writer-room prose to latest novel body")
def promote_writer_room_content(
    project_id: str,
    req: WriterRoomPromoteRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        content = svc.promote_writer_room_content(project_id, content_id=req.content_id)
        project = svc.get_project(project_id)
        return {
            "success": True,
            "data": serialize_content(content),
            "project": serialize_project(project) if project else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/split-comic-pages", summary="拆分漫画页")
async def split_comic_pages(
    project_id: str,
    req: SplitComicPagesRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = await svc.split_comic_pages(
            project_id,
            chapter_number=req.chapter_number,
            content_id=req.content_id,
            page_count=req.page_count,
            visual_style=req.visual_style,
            provider=req.provider,
            model=req.model,
            template_id=req.template_id,
        )
        project = svc.get_project(project_id)
        return {"success": True, "data": data, "project": serialize_project(project) if project else None}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/generate-storyboard", summary="生成分镜草稿")
async def generate_storyboard(
    project_id: str,
    req: GenerateStoryboardRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = await svc.generate_storyboard(
            project_id,
            content_id=req.content_id,
            provider=req.provider,
            model=req.model,
            template_id=req.template_id,
        )
        return {"success": True, "data": data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/match-reference-assets", summary="AI 匹配脚本/分镜参考卡")
async def match_reference_assets(
    project_id: str,
    req: MatchReferenceAssetsRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        content = await svc.match_reference_assets(
            project_id,
            content_id=req.content_id,
            provider=req.provider,
            model=req.model,
        )
        return {"success": True, "data": serialize_content(content)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{project_id}/contents", summary="列出项目阶段内容")
def list_contents(
    project_id: str,
    content_type: str | None = None,
    content_types: str | None = Query(
        default=None,
        description="Comma-separated content types. Applies only when content_type is omitted.",
    ),
    chapter_number: int | None = Query(default=None, ge=1),
    include_history: bool = False,
    summary: bool = Query(
        default=False,
        description="Return only identity/version metadata without text_content or data.",
    ),
    svc: CreativeProjectService = Depends(service),
):
    if not svc.get_project(project_id):
        raise HTTPException(status_code=404, detail="创作项目不存在")
    contents = svc.list_contents(
        project_id,
        content_type=content_type,
        content_types=[item.strip() for item in (content_types or "").split(",") if item.strip()] or None,
        chapter_number=chapter_number,
        latest_only=not include_history,
        summary_only=summary,
    )
    serializer = serialize_content_summary if summary else serialize_content
    return {"success": True, "data": [serializer(c) for c in contents]}


@router.patch("/{project_id}/contents/{content_id}", summary="保存项目阶段内容")
def update_content(
    project_id: str,
    content_id: str,
    req: ProjectContentUpdateRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        content = svc.update_content(
            project_id=project_id,
            content_id=content_id,
            title=req.title,
            data=req.data,
            text_content=req.text_content,
            is_locked=req.is_locked,
        )
        return {"success": True, "data": serialize_content(content)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.put("/{project_id}/content-package", summary="保存项目内容包版本")
def save_content_package(
    project_id: str,
    req: ContentPackageSaveRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        content = svc.save_content_package(
            project_id=project_id,
            package=req.package,
            source_content_id=req.source_content_id,
        )
        return {"success": True, "data": serialize_content(content)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/content-package/plan", summary="一次生成项目内容包")
async def plan_content_package(
    project_id: str,
    req: ContentPackagePlanRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        content = await _run_creative_task(
            "creative_writing",
            {
                "project_id": project_id,
                "stage": "content_package",
                "stage_label": "生成内容包",
                "provider": req.provider or "",
                "model": req.model or "",
                "item_count": req.item_count,
                "prompt_only": req.prompt_only,
            },
            lambda: svc.generate_content_package(
                project_id, topic=req.topic, brief=req.brief, item_count=req.item_count,
                prompt_only=req.prompt_only, provider=req.provider, model=req.model,
            ),
        )
        return {"success": True, "data": serialize_content(content)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/regenerate-chapter-outline-scenes", summary="只重生成单话细纲场景")
async def regenerate_chapter_outline_scenes(
    project_id: str,
    req: RegenerateChapterOutlineScenesRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        content = await svc.regenerate_chapter_outline_scenes(
            project_id=project_id,
            content_id=req.content_id,
            provider=req.provider,
            model=req.model,
            template_id=req.template_id,
        )
        return {"success": True, "data": serialize_content(content)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{project_id}/assets", summary="列出项目素材关联")
def list_project_assets(
    project_id: str,
    svc: CreativeProjectService = Depends(service),
):
    if not svc.get_project(project_id):
        raise HTTPException(status_code=404, detail="创作项目不存在")
    links = svc.list_asset_links(project_id)
    return {"success": True, "data": [serialize_asset_link(link) for link in links]}


@router.get("/{project_id}/generation-logs", summary="列出项目生成日志")
def list_generation_logs(
    project_id: str,
    stage: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    svc: CreativeProjectService = Depends(service),
):
    try:
        logs, total = svc.list_generation_logs(
            project_id,
            stage=stage,
            status=status,
            limit=limit,
            offset=offset,
        )
        return {
            "success": True,
            "data": [serialize_generation_log(log) for log in logs],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/logs/generation", summary="跨项目查询生成日志")
def list_generation_logs_global(
    scene: str | None = None,
    ref_id: str | None = None,
    stage: str | None = None,
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    svc: CreativeProjectService = Depends(service),
):
    """
    跨项目查询生成日志，支持按 scene / ref_id 过滤。

    典型用法：
    - GET /api/v1/creative-projects/logs/generation?scene=character_portrait
    - GET /api/v1/creative-projects/logs/generation?scene=character_portrait&ref_id={character_id}
    """
    logs, total = svc.list_generation_logs(
        project_id=None,
        scene=scene,
        ref_id=ref_id,
        stage=stage,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {
        "success": True,
        "data": [serialize_generation_log(log) for log in logs],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/{project_id}/assets", summary="关联项目素材")
def link_project_asset(
    project_id: str,
    req: ProjectAssetLinkRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        link = svc.link_asset(
            project_id=project_id,
            asset_id=req.asset_id,
            content_id=req.content_id,
            role=req.role,
            relation=req.relation,
            metadata=req.metadata,
        )
        return {"success": True, "data": serialize_asset_link(link)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/contents/{content_id}/save-as-asset", summary="保存项目文本为素材")
def save_project_content_as_asset(
    project_id: str,
    content_id: str,
    svc: CreativeProjectService = Depends(service),
):
    try:
        return svc.save_content_as_text_asset(project_id, content_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/{project_id}/sync-characters", summary="同步大纲角色到角色库")
def sync_project_characters(
    project_id: str,
    svc: CreativeProjectService = Depends(service),
):
    try:
        characters = svc.sync_outline_characters(project_id)
        project = svc.get_project(project_id)
        return {
            "success": True,
            "data": [serialize_character(item) for item in characters],
            "project": serialize_project(project) if project else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{project_id}/canvas", summary="获取项目画布状态")
def get_canvas(
    project_id: str,
    svc: CreativeProjectService = Depends(service),
):
    try:
        return {"success": True, "data": svc.get_canvas(project_id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.put("/{project_id}/canvas", summary="保存项目画布状态")
def save_canvas(
    project_id: str,
    req: CanvasSaveRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = svc.save_canvas(project_id, req.model_dump())
        return {"success": True, "data": data}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


def serialize_project(project: CreativeProject | None) -> dict[str, Any] | None:
    if project is None:
        return None
    settings = loads_json(project.settings_json)
    profile_id = settings.get("production_profile")
    profile = CONTENT_PRODUCTION_PROFILES.get(profile_id) if profile_id else None
    return {
        "id": project.id,
        "title": repair_utf8_mojibake(project.title),
        "project_type": project.project_type,
        "source_type": project.source_type,
        "source_ref": loads_json(project.source_ref_json),
        "status": project.status,
        "current_stage": project.current_stage,
        "outline": loads_json(project.outline_json),
        "chapter_plan": normalize_chapter_plan(loads_json(project.chapter_plan_json)),
        "settings": settings,
        "production_profile": profile,
        "metadata": loads_json(project.metadata_json),
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


def serialize_content(content: ProjectContent) -> dict[str, Any]:
    return {
        "id": content.id,
        "project_id": content.project_id,
        "content_type": content.content_type,
        "chapter_number": content.chapter_number,
        "episode_number": content.episode_number,
        "title": repair_utf8_mojibake(content.title),
        "data": loads_json(content.data_json),
        "text_content": repair_utf8_mojibake(content.text_content),
        "source_content_id": content.source_content_id,
        "version": content.version,
        "is_locked": content.is_locked,
        "created_at": content.created_at.isoformat() if content.created_at else None,
        "updated_at": content.updated_at.isoformat() if content.updated_at else None,
    }


def serialize_content_summary(content: ProjectContent) -> dict[str, Any]:
    """Lightweight projection for chapter rails and stage counters.

    ``data`` and ``text_content`` are omitted on purpose: this serializer is
    paired with a ``load_only`` query so the large payload columns are never
    transferred from the database.
    """
    return {
        "id": content.id,
        "project_id": content.project_id,
        "content_type": content.content_type,
        "chapter_number": content.chapter_number,
        "episode_number": content.episode_number,
        "version": content.version,
        "is_locked": content.is_locked,
        "created_at": content.created_at.isoformat() if content.created_at else None,
        "updated_at": content.updated_at.isoformat() if content.updated_at else None,
    }


def serialize_asset_link(link: ProjectAssetLink) -> dict[str, Any]:
    return {
        "id": link.id,
        "project_id": link.project_id,
        "asset_id": link.asset_id,
        "content_id": link.content_id,
        "role": repair_utf8_mojibake(link.role),
        "relation": repair_utf8_mojibake(link.relation),
        "metadata": loads_json(link.metadata_json),
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


def serialize_generation_log(log: ProjectGenerationLog) -> dict[str, Any]:
    request = loads_json(log.request_json)
    normalized = loads_json(log.normalized_json)
    return {
        "id": log.id,
        "project_id": log.project_id,
        "content_id": log.content_id,
        "scene": log.scene,
        "ref_id": log.ref_id,
        "stage": repair_utf8_mojibake(log.stage),
        "provider": repair_utf8_mojibake(log.provider),
        "model": repair_utf8_mojibake(log.model),
        "status": log.status,
        "prompt": repair_utf8_mojibake(log.prompt),
        "request": request,
        "prompt_template": request.get("prompt_template") if isinstance(request, dict) else None,
        "raw_response": repair_utf8_mojibake(log.raw_response),
        "normalized": normalized,
        "validation_error": repair_utf8_mojibake(log.validation_error),
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def serialize_character(character: Any) -> dict[str, Any]:
    return {
        "id": character.id,
        "name": repair_utf8_mojibake(character.name),
        "role": repair_utf8_mojibake(character.role),
        "appearance": repair_utf8_mojibake(character.appearance),
        "personality": repair_utf8_mojibake(character.personality),
        "costume_hint": repair_utf8_mojibake(character.costume_hint),
        "signature_items": loads_json(getattr(character, "signature_items", "[]"), []),
        "expressions": loads_json(getattr(character, "expressions", "[]"), []),
        "poses": loads_json(getattr(character, "poses", "[]"), []),
        "visual_consistency": repair_utf8_mojibake(getattr(character, "visual_consistency", "") or ""),
        "background": repair_utf8_mojibake(character.background),
        "age_range": repair_utf8_mojibake(character.age_range),
        "portrait_url": getattr(character, "portrait_url", "") or "",
        "portrait_asset_id": character.portrait_asset_id,
        "portrait_node_id": getattr(character, "portrait_node_id", None),
        "reference_asset_ids": loads_json(character.reference_asset_ids, []),
        "created_at": character.created_at.isoformat() if character.created_at else None,
        "updated_at": character.updated_at.isoformat() if character.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Continuity fact workflow (creative-project-continuity-facts)
# ---------------------------------------------------------------------------


class ContinuityExtractRequest(BaseModel):
    source_kind: str = "prose_review"
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class ContinuityDecisionRequest(BaseModel):
    note: str = ""
    merged_fact_id: str | None = None


class ContinuityCheckRequest(BaseModel):
    candidate_id: str | None = None


class ContinuityRewriteRequest(BaseModel):
    paragraph_index: int = Field(..., ge=0)
    instruction: str = Field(..., min_length=1)
    provider: str | None = None
    model: str | None = None


@router.get(
    "/{project_id}/continuity-candidates",
    summary="列出连续性候选事实",
)
def list_continuity_candidates(
    project_id: str,
    status: str | None = Query(default=None),
    source_content_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    svc: CreativeProjectService = Depends(service),
):
    try:
        items = svc.list_continuity_candidates(
            project_id,
            status=status,
            source_content_id=source_content_id,
            limit=limit,
        )
        return {
            "success": True,
            "data": [serialize_continuity_candidate(item) for item in items],
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post(
    "/{project_id}/contents/{content_id}/continuity-candidates/extract",
    summary="从正文提取/入库结构化连续性候选",
)
def extract_continuity_candidates(
    project_id: str,
    content_id: str,
    req: ContinuityExtractRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        items = svc.extract_continuity_candidates_v2(
            project_id,
            content_id,
            source_kind=req.source_kind,
            candidates_in=req.candidates,
        )
        return {
            "success": True,
            "data": [serialize_continuity_candidate(item) for item in items],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/{project_id}/continuity-candidates/{candidate_id}/accept",
    summary="确认候选事实，写入 locked project_bible / world_asset",
)
def accept_continuity_candidate(
    project_id: str,
    candidate_id: str,
    req: ContinuityDecisionRequest | None = None,
    svc: CreativeProjectService = Depends(service),
):
    note = (req.note if req else "") or ""
    try:
        item = svc.accept_continuity_candidate(
            project_id, candidate_id, note=note
        )
        return {"success": True, "data": serialize_continuity_candidate(item)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/{project_id}/continuity-candidates/{candidate_id}/ignore",
    summary="忽略候选事实",
)
def ignore_continuity_candidate(
    project_id: str,
    candidate_id: str,
    req: ContinuityDecisionRequest | None = None,
    svc: CreativeProjectService = Depends(service),
):
    note = (req.note if req else "") or ""
    try:
        item = svc.ignore_continuity_candidate(
            project_id, candidate_id, note=note
        )
        return {"success": True, "data": serialize_continuity_candidate(item)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/{project_id}/continuity-candidates/{candidate_id}/merge",
    summary="合并候选事实到已有 project_bible / world_asset",
)
def merge_continuity_candidate(
    project_id: str,
    candidate_id: str,
    req: ContinuityDecisionRequest,
    svc: CreativeProjectService = Depends(service),
):
    if not req.merged_fact_id:
        raise HTTPException(status_code=400, detail="merged_fact_id 不能为空")
    try:
        item = svc.merge_continuity_candidate(
            project_id,
            candidate_id,
            merged_fact_id=req.merged_fact_id,
            note=req.note,
        )
        return {"success": True, "data": serialize_continuity_candidate(item)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get(
    "/{project_id}/continuity-candidates/context-summary",
    summary="连续性事实上下文摘要（不进模型硬约束）",
)
def continuity_context_summary(
    project_id: str,
    generation_log_id: str | None = Query(default=None),
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = svc.build_continuity_context_summary(
            project_id, generation_log_id=generation_log_id
        )
        return {"success": True, "data": data}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post(
    "/{project_id}/chapters/{chapter_number}/check-continuity",
    summary="跨章连续性检查（对比已锁定事实）",
)
def check_continuity(
    project_id: str,
    chapter_number: int,
    req: ContinuityCheckRequest | None = None,
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = svc.check_continuity(
            project_id,
            chapter_number,
            candidate_id=(req.candidate_id if req else None),
        )
        return {"success": True, "data": data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post(
    "/{project_id}/contents/{content_id}/rewrite-paragraph",
    summary="段落级非破坏性重写（生成候选版本）",
)
async def rewrite_paragraph(
    project_id: str,
    content_id: str,
    req: ContinuityRewriteRequest,
    svc: CreativeProjectService = Depends(service),
):
    try:
        data = await svc.rewrite_paragraph(
            project_id,
            content_id,
            paragraph_index=req.paragraph_index,
            instruction=req.instruction,
            provider=req.provider,
            model=req.model,
        )
        return {"success": True, "data": data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def serialize_continuity_candidate(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "project_id": item.project_id,
        "source_content_id": item.source_content_id,
        "source_generation_log_id": item.source_generation_log_id,
        "source_kind": item.source_kind,
        "source_fingerprint": item.source_fingerprint,
        "entity_type": item.entity_type,
        "entity_name": item.entity_name,
        "claim": item.claim,
        "evidence_excerpt": item.evidence_excerpt,
        "evidence_anchor": loads_json(item.evidence_anchor_json or "{}"),
        "severity": item.severity,
        "suggested_action": item.suggested_action,
        "target_fact_type": item.target_fact_type,
        "status": item.status,
        "resolved_fact_id": item.resolved_fact_id,
        "resolution_note": item.resolution_note,
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }
