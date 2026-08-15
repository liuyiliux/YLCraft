"""Agent Center API."""

from __future__ import annotations

import json
import logging
import difflib
import re
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.database import ensure_agent_tables, get_async_session_dependency
from app.core.task_queue import get_task_queue, task_event_to_dict
from app.db.models.agent import AgentContextSnapshot, AgentDelegation, AgentMemorySnapshot, AgentMessage, AgentRun, AgentRunStep, AgentThread, AgentToolCall
from app.db.models.creative_project import ProjectGenerationLog
from app.services.agent import tools as _agent_tools  # noqa: F401 - register tools
from app.services.agent.memory.manager import MemoryManager as AgentMemoryManager
from app.services.agent.profile import AgentProfileManager, profile_to_dict
from app.services.agent.registry import ToolRegistry
from app.services.agent.runtime import SkillRouter
from app.services.agent.service import CONFIRMATION_RISK_LEVELS, AgentService
from app.services.agent.session.manager import SessionManager as AgentSessionManager
from app.services.agent.skill_drafts import AgentSkillDraftService, SkillDraftError
from app.services.agent.skill_loader import SkillPackageLoader
from app.services.agent.thread_manager import ThreadManager

router = APIRouter(tags=["Agent"])
logger = logging.getLogger("ylcraft.api.agent")


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    session_id: Optional[str] = None
    context: dict = Field(default_factory=dict)
    stream: bool = True
    profile_id: Optional[str] = None
    force_new_thread: bool = False


class SendToAgentRequest(BaseModel):
    source_page: str
    action: str
    data: dict = Field(default_factory=dict)
    profile_id: Optional[str] = None


class CreateSkillRequest(BaseModel):
    name: str
    description: str
    content: str
    skill_type: str = "tool"


class SkillRoutePreviewRequest(BaseModel):
    message: str = ""
    context: dict = Field(default_factory=dict)
    allowed_tools: list[str] = Field(default_factory=list)
    default_skill_ids: list[str] = Field(default_factory=list)
    max_skills: int = Field(default=8, ge=1, le=20)
    target_skill_id: str = ""


class SkillDraftCreateRequest(BaseModel):
    content: str
    source_type: str = "manual"
    source_url: str = ""
    source_run_id: str = ""
    source_step_ids: list[int] = Field(default_factory=list)


class SkillDraftImportUrlRequest(BaseModel):
    url: str


class SkillDraftRejectRequest(BaseModel):
    reason: str = ""


class SkillDraftFromRunRequest(BaseModel):
    name: str = ""
    title: str = ""


class SkillBundleCreateRequest(BaseModel):
    name: str
    description: str = ""
    skills: list[str] = Field(default_factory=list)
    instruction: str = ""


class AgentProfileRequest(BaseModel):
    name: str = ""
    description: str = ""
    avatar: str = "🤖"
    role_type: str = "assistant"
    system_prompt: str = ""
    allowed_tools: list[str] = Field(default_factory=list)
    default_context: dict = Field(default_factory=dict)
    default_project_id: str = ""
    default_workflow: str = ""
    default_skill_ids: list[str] = Field(default_factory=list)
    provider: str = ""
    model: str = ""
    max_steps: int = Field(default=8, ge=1, le=20, description="迭代预算（轮），不是步数上限，是单轮计划/工具/观察循环的保护阈值")
    can_delegate: bool = False
    is_default: bool = False


class ContinueRunRequest(BaseModel):
    message: str = ""
    context: dict = Field(default_factory=dict)


class RetryRunRequest(BaseModel):
    step_id: Optional[int] = None


class DelegateRunRequest(BaseModel):
    profile_id: str
    message: str = ""
    context: dict = Field(default_factory=dict)
    resume_parent: bool = False


class ToolTestRequest(BaseModel):
    tool_name: str
    arguments: dict = Field(default_factory=dict)
    profile_id: str = ""
    confirmed: bool = False


class SaveMemoryCandidatesRequest(BaseModel):
    indices: list[int] = Field(default_factory=list)


class SaveMemoryRequest(BaseModel):
    value: str = ""
    memory_type: str = "fact"
    importance: int = Field(default=5, ge=1, le=10)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


@router.post("/chat", summary="Agent 对话")
async def chat(request: ChatRequest, db_session=Depends(get_async_session_dependency)):
    await ensure_agent_tables()
    service = AgentService(db_session)
    if request.stream:
        return StreamingResponse(_chat_stream(service, request), media_type="text/event-stream")
    context = dict(request.context or {})
    return await service.chat(
        session_id=request.thread_id or request.session_id or "",
        user_message=request.message,
        context=context,
        profile_id=request.profile_id,
        force_new_thread=request.force_new_thread,
    )


async def _chat_stream(service: AgentService, request: ChatRequest) -> AsyncGenerator[str, None]:
    try:
        yield f"data: {json.dumps({'event': 'start'}, ensure_ascii=False)}\n\n"
        context = dict(request.context or {})
        result = await service.chat(
            session_id=request.thread_id or request.session_id or "",
            user_message=request.message,
            context=context,
            profile_id=request.profile_id,
            force_new_thread=request.force_new_thread,
        )
        reply = result.get("reply", "")
        for index in range(0, len(reply), 10):
            yield f"data: {json.dumps({'event': 'token', 'data': reply[index:index + 10]}, ensure_ascii=False)}\n\n"
        if result.get("tool_calls"):
            yield f"data: {json.dumps({'event': 'tool_calls', 'data': result['tool_calls']}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'event': 'done', 'data': {'thread_id': result.get('thread_id') or result['session_id'], 'session_id': result['session_id'], 'run_id': result.get('run_id'), 'profile': result.get('profile')}}, ensure_ascii=False)}\n\n"
    except SQLAlchemyError as exc:
        # 数据库层面错误：事务可能已 aborted，显式 rollback 清脏，避免后续请求复用连接时连锁失败
        logger.exception("[Agent API] stream DB error")
        try:
            await service.session.rollback()
        except Exception:  # noqa: BLE001
            pass
        yield f"data: {json.dumps({'event': 'error', 'data': f'数据库错误：{exc.__class__.__name__}'}, ensure_ascii=False)}\n\n"
    except Exception as exc:
        logger.exception("[Agent API] stream failed")
        yield f"data: {json.dumps({'event': 'error', 'data': str(exc)}, ensure_ascii=False)}\n\n"


@router.get("/profiles", summary="智能体配置列表")
async def list_profiles(user_id: str = "default", db_session=Depends(get_async_session_dependency)):
    await ensure_agent_tables()
    manager = AgentProfileManager(db_session, user_id)
    profiles = await manager.list_profiles()
    await db_session.commit()
    return [profile_to_dict(profile) for profile in profiles]


@router.post("/profiles", summary="创建智能体配置")
async def create_profile(
    request: AgentProfileRequest,
    user_id: str = "default",
    db_session=Depends(get_async_session_dependency),
):
    await ensure_agent_tables()
    manager = AgentProfileManager(db_session, user_id)
    profile = await manager.create_profile(request.model_dump())
    await db_session.commit()
    return profile_to_dict(profile)


@router.put("/profiles/{profile_id}", summary="更新智能体配置")
async def update_profile(
    profile_id: str,
    request: AgentProfileRequest,
    user_id: str = "default",
    db_session=Depends(get_async_session_dependency),
):
    await ensure_agent_tables()
    manager = AgentProfileManager(db_session, user_id)
    profile = await manager.update_profile(profile_id, request.model_dump(exclude_unset=True))
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    await db_session.commit()
    return profile_to_dict(profile)


@router.get("/sessions", summary="对话列表")
async def list_sessions(user_id: str = "default", db_session=Depends(get_async_session_dependency)):
    manager = AgentSessionManager(db_session)
    sessions = await manager.list_sessions(user_id)
    return [
        {
            "id": item.id,
            "thread_id": item.id,
            "session_id": item.id,
            "title": item.title,
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
        }
        for item in sessions
    ]


@router.get("/threads", summary="Agent Thread 列表")
async def list_threads(user_id: str = "default", db_session=Depends(get_async_session_dependency)):
    await ensure_agent_tables()
    manager = ThreadManager(db_session)
    threads = await manager.list_threads(user_id)
    await db_session.commit()
    return [
        {
            "id": item.id,
            "thread_id": item.id,
            "session_id": item.id,
            "title": item.title,
            "status": item.status,
            "active_profile_id": item.active_profile_id,
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
        }
        for item in threads
    ]


def _safe_json_loads(raw: str | None, default):
    try:
        return json.loads(raw or "")
    except Exception:
        return default


def _step_to_dict(step: AgentRunStep) -> dict:
    output = _safe_json_loads(step.output_json, {})
    return {
        "id": step.id,
        "run_id": step.run_id,
        "session_id": step.session_id,
        "profile_id": step.profile_id,
        "step_type": step.step_type,
        "status": step.status,
        "order_index": step.order_index,
        "tool_name": step.tool_name,
        "summary": step.summary,
        "input": _safe_json_loads(step.input_json, {}),
        "output": output,
        "raw_json": output,
        "linked_objects": _safe_json_loads(step.linked_objects_json, []),
        "error": step.error,
        "duration_ms": step.duration_ms,
        "created_at": step.created_at.isoformat(),
    }


def _run_to_dict(run: AgentRun, include_steps: bool = False, steps: list[AgentRunStep] | None = None) -> dict:
    data = {
        "id": run.id,
        "user_id": run.user_id,
        "thread_id": run.session_id,
        "session_id": run.session_id,
        "profile_id": run.profile_id,
        "parent_run_id": run.parent_run_id,
        "root_run_id": run.root_run_id or run.id,
        "run_kind": run.run_kind,
        "delegation_depth": run.delegation_depth,
        "status": run.status,
        "objective": run.objective,
        "context": _safe_json_loads(run.context_json, {}),
        "result": _safe_json_loads(run.result_json, {}),
        "error": run.error,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }
    if include_steps:
        data["steps"] = [_step_to_dict(item) for item in (steps or [])]
    return data


def _delegation_to_dict(item: AgentDelegation) -> dict:
    return {
        "id": item.id,
        "user_id": item.user_id,
        "root_run_id": item.root_run_id,
        "parent_run_id": item.parent_run_id,
        "child_run_id": item.child_run_id,
        "parent_step_id": item.parent_step_id,
        "task_key": item.task_key,
        "target_profile_id": item.target_profile_id,
        "objective": item.objective,
        "context": _safe_json_loads(item.context_json, {}),
        "depends_on": _safe_json_loads(item.depends_on_json, []),
        "execution_mode": item.execution_mode,
        "status": item.status,
        "result": _safe_json_loads(item.result_json, {}),
        "error": item.error,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "finished_at": item.finished_at.isoformat() if item.finished_at else None,
    }


async def _sync_parent_delegation_state(
    db_session,
    child_run: AgentRun,
    *,
    child_status: str,
    child_result: dict | None = None,
    child_error: str = "",
) -> None:
    """Propagate a child confirmation/cancellation into its durable parent join."""
    records_result = await db_session.execute(
        select(AgentDelegation).where(AgentDelegation.child_run_id == child_run.id)
    )
    records = list(records_result.scalars().all())
    if not records:
        return

    normalized_status = {
        "completed": "completed",
        "failed": "failed",
        "cancelled": "cancelled",
        "waiting_confirmation": "waiting_confirmation",
    }.get(child_status, child_status or "failed")
    now = datetime.utcnow()
    for record in records:
        record.status = normalized_status
        record.result_json = json.dumps(child_result or {}, ensure_ascii=False, default=str)
        record.error = child_error
        record.updated_at = now
        if normalized_status not in {"pending", "running", "waiting_confirmation"}:
            record.finished_at = now
        if not record.parent_step_id:
            continue

        siblings_result = await db_session.execute(
            select(AgentDelegation)
            .where(AgentDelegation.parent_step_id == record.parent_step_id)
            .order_by(AgentDelegation.created_at.asc(), AgentDelegation.task_key.asc())
        )
        siblings = list(siblings_result.scalars().all())
        statuses = [item.status for item in siblings]
        completed = statuses.count("completed")
        failed = statuses.count("failed")
        skipped = statuses.count("skipped")
        waiting = sum(status in {"pending", "running", "waiting_confirmation"} for status in statuses)
        cancelled = statuses.count("cancelled")

        step = await db_session.get(AgentRunStep, record.parent_step_id)
        if not step:
            continue
        previous_output = _safe_json_loads(step.output_json, {})
        join_strategy = str(previous_output.get("join_strategy") or "all")
        if waiting:
            join_status = "waiting_confirmation"
        elif completed == len(siblings):
            join_status = "completed"
        elif completed and join_strategy == "best_effort":
            join_status = "partial"
        elif cancelled == len(siblings):
            join_status = "cancelled"
        else:
            join_status = "failed"
        summary = {
            "total": len(siblings),
            "completed": completed,
            "failed": failed,
            "skipped": skipped,
            "waiting_confirmation": waiting,
            "cancelled": cancelled,
        }
        previous_output.update(
            {
                "status": join_status,
                "summary": summary,
                "resume_required": join_status != "waiting_confirmation",
                "delegations": [_delegation_to_dict(item) for item in siblings],
            }
        )
        step.status = join_status
        step.summary = f"子任务完成 {completed}/{len(siblings)}"
        step.output_json = json.dumps(previous_output, ensure_ascii=False, default=str)
        step.error = "一个或多个子任务失败" if join_status == "failed" else ""

        parent = await db_session.get(AgentRun, record.parent_run_id)
        if parent:
            parent.status = "waiting_confirmation" if waiting else join_status
            parent.error = step.error
            parent.updated_at = now


def _generation_log_to_dict(log: ProjectGenerationLog) -> dict:
    return {
        "id": log.id,
        "project_id": log.project_id,
        "content_id": log.content_id,
        "scene": log.scene,
        "ref_id": log.ref_id,
        "stage": log.stage,
        "provider": log.provider,
        "model": log.model,
        "status": log.status,
        "validation_error": log.validation_error,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def _agent_tool_call_to_dict(log: AgentToolCall) -> dict:
    return {
        "id": log.id,
        "session_id": log.session_id,
        "tool_name": log.tool_name,
        "tool_args": _safe_json_loads(log.tool_args, {}),
        "result": _safe_json_loads(log.result, log.result),
        "success": log.success,
        "duration_ms": log.duration_ms,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def _task_to_dict(task) -> dict:
    status = task.status.value if hasattr(task.status, "value") else str(task.status)
    return {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "payload": task.payload,
        "status": status,
        "progress": task.progress,
        "progress_message": task.progress_message,
        "result": task.result,
        "error": task.error,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
        "events": [task_event_to_dict(event) for event in task.events],
    }


async def _collect_run_linked_logs(db_session, run: AgentRun, steps: list[AgentRunStep]) -> dict:
    context = _safe_json_loads(run.context_json, {})
    project_ids: set[str] = set()
    content_ids: set[str] = set()
    task_ids: set[str] = set()

    for key in ("project_id", "creative_project_id", "default_project_id"):
        value = context.get(key)
        if value:
            project_ids.add(str(value))

    for step in steps:
        for item in _safe_json_loads(step.linked_objects_json, []):
            if not isinstance(item, dict):
                continue
            kind = str(item.get("type") or "")
            identifier = item.get("id")
            if not identifier:
                continue
            if kind == "project":
                project_ids.add(str(identifier))
            elif kind == "project_content":
                content_ids.add(str(identifier))
            elif kind == "task":
                task_ids.add(str(identifier))

    tool_query = select(AgentToolCall).where(AgentToolCall.session_id == run.session_id)
    if run.started_at:
        tool_query = tool_query.where(AgentToolCall.created_at >= run.started_at)
    if run.finished_at:
        tool_query = tool_query.where(AgentToolCall.created_at <= run.finished_at)
    tool_logs = (
        await db_session.execute(tool_query.order_by(AgentToolCall.created_at.desc()).limit(80))
    ).scalars().all()

    generation_logs = []
    if project_ids or content_ids:
        from sqlalchemy import or_

        filters = []
        if project_ids:
            filters.append(ProjectGenerationLog.project_id.in_(project_ids))
        if content_ids:
            filters.append(ProjectGenerationLog.content_id.in_(content_ids))
        generation_logs = (
            await db_session.execute(
                select(ProjectGenerationLog)
                .where(or_(*filters))
                .order_by(ProjectGenerationLog.created_at.desc())
                .limit(80)
            )
        ).scalars().all()

    queue = get_task_queue()
    tasks = []
    for task_id in sorted(task_ids):
        task = await queue.get_task(task_id)
        if task:
            tasks.append(_task_to_dict(task))

    return {
        "run_id": run.id,
        "linked_object_counts": {
            "projects": len(project_ids),
            "project_contents": len(content_ids),
            "tasks": len(task_ids),
        },
        "project_ids": sorted(project_ids),
        "content_ids": sorted(content_ids),
        "task_ids": sorted(task_ids),
        "tool_calls": [_agent_tool_call_to_dict(log) for log in tool_logs],
        "generation_logs": [_generation_log_to_dict(log) for log in generation_logs],
        "tasks": tasks,
    }


def _markdown_json_block(value) -> str:
    return "```json\n" + json.dumps(value or {}, ensure_ascii=False, indent=2, default=str) + "\n```"


def _compact_tool_result_text(result: object, limit: int = 900) -> str:
    if result is None:
        return "工具没有返回内容。"
    if isinstance(result, str):
        text = result
    else:
        text = json.dumps(result, ensure_ascii=False, default=str)
    compact = " ".join(text.split())
    return compact[:limit] + ("..." if len(compact) > limit else "")


def _run_to_markdown(run: AgentRun, steps: list[AgentRunStep], thread: AgentThread | None = None, messages: list[AgentMessage] | None = None) -> str:
    run_data = _run_to_dict(run)
    lines = [
        f"# Agent Run {run.id}",
        "",
        f"- 状态：{run.status}",
        f"- 智能体：{run.profile_id or '-'}",
        f"- 工作线程：{run.session_id or '-'}",
        f"- 父 Run：{run.parent_run_id or '-'}",
        f"- 创建时间：{run.created_at.isoformat()}",
        f"- 完成时间：{run.finished_at.isoformat() if run.finished_at else '-'}",
        "",
        "## 目标",
        "",
        run.objective or "未记录目标",
        "",
        "## 上下文",
        "",
        _markdown_json_block(run_data.get("context")),
    ]

    # Thread context section
    if thread:
        lines.extend([
            "",
            "## 工作线程信息",
            "",
            f"- 线程 ID：{thread.id}",
            f"- 标题：{thread.title or '-'}",
            f"- 状态：{thread.status}",
            f"- 协作智能体：{thread.active_profile_id or '-'}",
            f"- 创建时间：{thread.created_at.isoformat()}",
            f"- 更新时间：{thread.updated_at.isoformat()}",
        ])
        if thread.archived_at:
            lines.append(f"- 归档时间：{thread.archived_at.isoformat()}")
        thread_metadata = _safe_json_loads(thread.metadata_json, {})
        if thread_metadata:
            lines.extend(["", "线程元数据：", "", _markdown_json_block(thread_metadata)])

    lines.extend([
        "",
        "## 结果",
        "",
        _markdown_json_block(run_data.get("result")),
    ])
    if run.error:
        lines.extend(["", "## Run 错误", "", run.error])

    # Messages section - show conversation context from this run
    if messages:
        lines.extend(["", "## 对话消息"])
        for msg in messages:
            role_label = {"user": "用户", "assistant": "助手", "system": "系统", "tool": "工具"}.get(msg.role, msg.role)
            lines.extend([
                "",
                f"### [{role_label}] {msg.id}",
                "",
                f"- 时间：{msg.created_at.isoformat()}",
            ])
            if msg.tool_call_id:
                lines.append(f"- 工具调用 ID：{msg.tool_call_id}")
            lines.extend(["", msg.content or "(空内容)"])
            msg_json = _safe_json_loads(msg.content_json, {})
            if msg_json:
                lines.extend(["", "<details><summary>结构化内容</summary>", "", _markdown_json_block(msg_json), "", "</details>"])

    lines.extend(["", "## 步骤"])
    for step in steps:
        step_data = _step_to_dict(step)
        title = f"{step.order_index + 1}. {step.step_type}"
        if step.tool_name:
            title += f" / {step.tool_name}"
        lines.extend(
            [
                "",
                f"### {title}",
                "",
                f"- 状态：{step.status}",
                f"- 耗时：{step.duration_ms or 0}ms",
                f"- 时间：{step.created_at.isoformat()}",
                "",
                step.summary or "无摘要",
            ]
        )
        if step.error:
            lines.extend(["", f"错误：{step.error}"])
        if step_data.get("linked_objects"):
            lines.extend(["", "关联对象："])
            for item in step_data["linked_objects"]:
                lines.append(f"- {item.get('type')}: {item.get('title') or item.get('id')} ({item.get('id')})")
        lines.extend(["", "<details><summary>输入 / 输出</summary>", "", _markdown_json_block({"input": step_data.get("input"), "output": step_data.get("output")}), "", "</details>"])
    lines.append("")
    return "\n".join(lines)


async def _next_step_index(db_session, run_id: str) -> int:
    result = await db_session.execute(
        select(AgentRunStep)
        .where(AgentRunStep.run_id == run_id)
        .order_by(AgentRunStep.order_index.desc(), AgentRunStep.id.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    return (last.order_index + 1) if last else 0


async def _append_control_step(
    db_session,
    run: AgentRun,
    step_type: str,
    status: str,
    summary: str,
    input_data: dict | None = None,
    output_data: dict | None = None,
    error: str = "",
) -> AgentRunStep:
    step = AgentRunStep(
        run_id=run.id,
        session_id=run.session_id,
        profile_id=run.profile_id,
        step_type=step_type,
        status=status,
        order_index=await _next_step_index(db_session, run.id),
        summary=summary,
        input_json=json.dumps(input_data or {}, ensure_ascii=False, default=str),
        output_json=json.dumps(output_data or {}, ensure_ascii=False, default=str),
        error=error,
    )
    db_session.add(step)
    await db_session.flush()
    return step


@router.get("/runs", summary="Agent 运行记录")
async def list_runs(
    thread_id: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: str = "default",
    limit: int = 30,
    db_session=Depends(get_async_session_dependency),
):
    await ensure_agent_tables()
    query = select(AgentRun).where(AgentRun.user_id == user_id)
    effective_thread_id = thread_id or session_id
    if effective_thread_id:
        query = query.where(AgentRun.session_id == effective_thread_id)
    query = query.order_by(AgentRun.created_at.desc()).limit(max(1, min(limit, 100)))
    result = await db_session.execute(query)
    return [_run_to_dict(item) for item in result.scalars().all()]


@router.get("/runs/{run_id}", summary="Agent 运行详情")
async def get_run_detail(run_id: str, db_session=Depends(get_async_session_dependency)):
    await ensure_agent_tables()
    run = await db_session.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    steps_result = await db_session.execute(
        select(AgentRunStep)
        .where(AgentRunStep.run_id == run_id)
        .order_by(AgentRunStep.order_index.asc(), AgentRunStep.id.asc())
    )
    return _run_to_dict(run, include_steps=True, steps=steps_result.scalars().all())


@router.get("/runs/{run_id}/delegations", summary="获取 Agent Run 的子任务委派记录")
async def get_run_delegations(run_id: str, db_session=Depends(get_async_session_dependency)):
    await ensure_agent_tables()
    run = await db_session.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    result = await db_session.execute(
        select(AgentDelegation)
        .where(AgentDelegation.parent_run_id == run_id)
        .order_by(AgentDelegation.created_at.asc(), AgentDelegation.task_key.asc())
    )
    items = list(result.scalars().all())
    return {
        "run_id": run_id,
        "root_run_id": run.root_run_id or run.id,
        "total": len(items),
        "delegations": [_delegation_to_dict(item) for item in items],
    }


@router.get("/runs/{run_id}/tree", summary="获取 Agent Run 执行树")
async def get_run_tree(run_id: str, db_session=Depends(get_async_session_dependency)):
    await ensure_agent_tables()
    selected = await db_session.get(AgentRun, run_id)
    if not selected:
        raise HTTPException(status_code=404, detail="Run not found")
    root_run_id = selected.root_run_id or selected.id
    runs_result = await db_session.execute(
        select(AgentRun)
        .where(AgentRun.user_id == selected.user_id, AgentRun.root_run_id == root_run_id)
        .order_by(AgentRun.created_at.asc())
    )
    runs = list(runs_result.scalars().all())
    if selected.id == root_run_id and not any(item.id == selected.id for item in runs):
        runs.insert(0, selected)
    delegations_result = await db_session.execute(
        select(AgentDelegation)
        .where(
            AgentDelegation.user_id == selected.user_id,
            AgentDelegation.root_run_id == root_run_id,
        )
        .order_by(AgentDelegation.created_at.asc(), AgentDelegation.task_key.asc())
    )
    delegations = list(delegations_result.scalars().all())
    from app.services.agent.runtime.delegation import DelegationLimits

    limits = DelegationLimits()

    nodes = {item.id: {**_run_to_dict(item), "children": []} for item in runs}
    roots: list[dict] = []
    for item in runs:
        node = nodes[item.id]
        if item.parent_run_id and item.parent_run_id in nodes:
            nodes[item.parent_run_id]["children"].append(node)
        else:
            roots.append(node)
    return {
        "selected_run_id": run_id,
        "root_run_id": root_run_id,
        "root": nodes.get(root_run_id) or (roots[0] if roots else None),
        "runs": [_run_to_dict(item) for item in runs],
        "delegations": [_delegation_to_dict(item) for item in delegations],
        "limits": {
            "max_depth": limits.max_depth,
            "max_children_per_call": limits.max_children_per_call,
            "max_concurrency": limits.max_concurrency,
            "max_children_per_root": limits.max_children_per_root,
            "child_timeout_seconds": limits.child_timeout_seconds,
        },
    }


@router.get("/runs/{run_id}/skill-candidate", summary="分析 Run 是否适合沉淀为 Skill")
async def inspect_run_skill_candidate(run_id: str, user_id: str = "default", db_session=Depends(get_async_session_dependency)):
    await ensure_agent_tables()
    service = AgentSkillDraftService(db_session, user_id=user_id)
    try:
        analysis = await service.inspect_run_candidate(run_id)
    except SkillDraftError as exc:
        _raise_skill_draft_error(exc)
    return {"success": True, "analysis": analysis}


@router.post("/runs/{run_id}/skill-draft", summary="从 Run 生成待审批 Skill 草稿")
async def create_skill_draft_from_run(
    run_id: str,
    request: SkillDraftFromRunRequest,
    user_id: str = "default",
    db_session=Depends(get_async_session_dependency),
):
    await ensure_agent_tables()
    service = AgentSkillDraftService(db_session, user_id=user_id)
    try:
        draft = await service.create_draft_from_run(run_id, name=request.name, title=request.title)
    except SkillDraftError as exc:
        _raise_skill_draft_error(exc)
    return {"success": True, "draft": _skill_draft_to_dict(draft)}


@router.get("/runs/{run_id}/linked-logs", summary="Agent Run 关联日志")
async def get_run_linked_logs(run_id: str, db_session=Depends(get_async_session_dependency)):
    await ensure_agent_tables()
    run = await db_session.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    steps_result = await db_session.execute(
        select(AgentRunStep)
        .where(AgentRunStep.run_id == run_id)
        .order_by(AgentRunStep.order_index.asc(), AgentRunStep.id.asc())
    )
    return await _collect_run_linked_logs(db_session, run, steps_result.scalars().all())


@router.get("/runs/{run_id}/memory-snapshot", summary="获取 Agent Run 记忆快照")
async def get_run_memory_snapshot(run_id: str, db_session=Depends(get_async_session_dependency)):
    await ensure_agent_tables()
    run = await db_session.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    result = await db_session.execute(
        select(AgentMemorySnapshot)
        .where(AgentMemorySnapshot.run_id == run_id)
        .order_by(AgentMemorySnapshot.created_at.desc(), AgentMemorySnapshot.id.desc())
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()
    if not snapshot:
        return {"success": True, "snapshot": None}
    return {
        "success": True,
        "snapshot": {
            "id": snapshot.id,
            "run_id": snapshot.run_id,
            "session_id": snapshot.session_id,
            "profile_id": snapshot.profile_id,
            "memory_context": snapshot.memory_context,
            "context_summary": snapshot.context_summary,
            "tool_index_text": snapshot.tool_index_text,
            "snapshot": _safe_json_loads(snapshot.snapshot_json, {}),
            "created_at": snapshot.created_at.isoformat(),
        },
    }


@router.get("/runs/{run_id}/export.md", summary="导出 Agent Run Markdown")
async def export_run_markdown(run_id: str, db_session=Depends(get_async_session_dependency)):
    await ensure_agent_tables()
    run = await db_session.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    thread_id = run.session_id or ""
    thread = await db_session.get(AgentThread, thread_id) if thread_id else None
    messages_result = await db_session.execute(
        select(AgentMessage)
        .where(AgentMessage.run_id == run_id)
        .order_by(AgentMessage.created_at.asc(), AgentMessage.id.asc())
    )
    steps_result = await db_session.execute(
        select(AgentRunStep)
        .where(AgentRunStep.run_id == run_id)
        .order_by(AgentRunStep.order_index.asc(), AgentRunStep.id.asc())
    )
    markdown = _run_to_markdown(run, steps_result.scalars().all(), thread=thread, messages=messages_result.scalars().all())
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="agent-run-{run_id}.md"'},
    )


@router.post("/runs/{run_id}/cancel", summary="取消 Agent 运行")
async def cancel_run(run_id: str, db_session=Depends(get_async_session_dependency)):
    await ensure_agent_tables()
    run = await db_session.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status in {"completed", "failed", "cancelled"}:
        return {"success": True, "run": _run_to_dict(run), "message": "Run already finished"}

    run.status = "cancelled"
    run.error = "用户取消运行"
    run.finished_at = datetime.utcnow()
    run.updated_at = datetime.utcnow()
    await _append_control_step(
        db_session,
        run,
        step_type="cancel",
        status="cancelled",
        summary="用户取消运行",
    )
    await _sync_parent_delegation_state(
        db_session,
        run,
        child_status="cancelled",
        child_result={"status": "cancelled"},
        child_error=run.error,
    )
    await db_session.commit()
    return {"success": True, "run": _run_to_dict(run)}


@router.post("/runs/{run_id}/context-snapshot", summary="重建 Run 上下文快照")
async def reconstruct_context_snapshot(run_id: str, db_session=Depends(get_async_session_dependency)):
    """根据 run_id 重建当时的模型上下文快照，用于回放和调试。"""
    await ensure_agent_tables()
    run = await db_session.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    thread_mgr = ThreadManager(db_session)
    thread_id = run.session_id  # session_id == thread_id
    thread = await thread_mgr.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    # 收集该 run 之前的消息（含当前 run 的 intake）
    all_messages = await thread_mgr.get_messages(thread_id)
    run_messages = [m for m in all_messages if m.get("run_id") == run_id or m.get("metadata", {}).get("phase") == "intake"]
    pre_messages = [m for m in all_messages if m.get("created_at", "") <= (run.created_at.isoformat() if run.created_at else "")]
    recent_msgs = pre_messages[-20:] if len(pre_messages) > 20 else pre_messages

    # 收集 steps
    step_query = select(AgentRunStep).where(AgentRunStep.run_id == run_id).order_by(AgentRunStep.order_index)
    step_result = await db_session.execute(step_query)
    steps = list(step_result.scalars().all())

    context_meta = _safe_json_loads(thread.metadata_json, {})
    effective_context = context_meta.get("effective_context") if isinstance(context_meta, dict) else {}

    payload = {
        "thread_id": thread_id,
        "run_id": run_id,
        "run_status": run.status,
        "objective": run.objective or "",
        "profile_id": run.profile_id or "",
        "message_count": len(recent_msgs),
        "step_count": len(steps),
        "recent_messages": [
            {
                "role": str(m.get("role") or ""),
                "content": str(m.get("content") or "")[:320],
                "run_id": str(m.get("run_id") or ""),
                "created_at": str(m.get("created_at") or ""),
            }
            for m in recent_msgs[-10:]
            if isinstance(m, dict) and m.get("role") in {"user", "assistant", "system"}
        ],
        "steps_summary": [
            {
                "step_type": s.step_type or "",
                "status": s.status or "",
                "summary": s.summary or "",
                "tool_name": s.tool_name or "",
                "duration_ms": s.duration_ms or 0,
                "error": (s.error or "")[:200],
            }
            for s in steps
        ],
        "effective_context_keys": sorted(
            k for k, v in effective_context.items()
            if v not in (None, "", [], {})
        ) if isinstance(effective_context, dict) else [],
        "conversation_state": effective_context.get("conversation_state") if isinstance(effective_context, dict) else {},
        "reconstructed_at": datetime.utcnow().isoformat(),
    }

    summary_text = run.objective or ""
    if steps:
        summary_text += f"（{len(steps)} 步骤）"

    snapshot = await thread_mgr.create_context_snapshot(
        thread_id=thread_id,
        run_id=run_id,
        kind="reconstructed",
        context=payload,
        summary=summary_text[:500],
        token_estimate=max(1, len(json.dumps(payload, ensure_ascii=False, default=str)) // 4),
    )
    await db_session.commit()

    return {
        "success": True,
        "snapshot_id": snapshot.id,
        "kind": snapshot.kind,
        "summary": snapshot.summary,
        "context": payload,
        "created_at": snapshot.created_at.isoformat() if snapshot.created_at else "",
    }


@router.get("/runs/{run_id}/context-snapshot", summary="获取 Run 上下文快照")
async def get_context_snapshot(run_id: str, db_session=Depends(get_async_session_dependency)):
    """获取指定 run 的上下文快照列表。"""
    await ensure_agent_tables()
    run = await db_session.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    result = await db_session.execute(
        select(AgentContextSnapshot)
        .where(AgentContextSnapshot.run_id == run_id)
        .order_by(AgentContextSnapshot.created_at.desc())
        .limit(5)
    )
    snapshots = list(result.scalars().all())
    return {
        "snapshots": [
            {
                "id": s.id,
                "kind": s.kind,
                "summary": s.summary,
                "token_estimate": s.token_estimate,
                "context": _safe_json_loads(s.context_json, {}),
                "created_at": s.created_at.isoformat() if s.created_at else "",
            }
            for s in snapshots
        ]
    }


@router.post("/runs/{run_id}/continue", summary="继续 Agent 运行")
async def continue_run(
    run_id: str,
    request: ContinueRunRequest,
    db_session=Depends(get_async_session_dependency),
):
    await ensure_agent_tables()
    run = await db_session.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    context = {
        **_safe_json_loads(run.context_json, {}),
        **(request.context or {}),
        "continued_from_run_id": run.id,
    }
    message = request.message or f"继续执行上一次智能体运行：{run.objective}"
    service = AgentService(db_session, user_id=run.user_id)
    return await service.chat(
        session_id=run.session_id,
        user_message=message,
        context=context,
        profile_id=run.profile_id or None,
    )


@router.post("/runs/{run_id}/retry", summary="重试 Agent 失败步骤")
async def retry_run_step(
    run_id: str,
    request: RetryRunRequest,
    db_session=Depends(get_async_session_dependency),
):
    await ensure_agent_tables()
    run = await db_session.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    query = select(AgentRunStep).where(AgentRunStep.run_id == run_id, AgentRunStep.status == "failed")
    if request.step_id:
        query = query.where(AgentRunStep.id == request.step_id)
    query = query.order_by(AgentRunStep.order_index.desc(), AgentRunStep.id.desc()).limit(1)
    result = await db_session.execute(query)
    failed_step = result.scalar_one_or_none()
    if not failed_step:
        raise HTTPException(status_code=404, detail="No failed step found")
    if failed_step.step_type != "tool_call":
        raise HTTPException(status_code=400, detail="Only failed tool_call steps can be retried now")

    step_input = _safe_json_loads(failed_step.input_json, {})
    tool_name = failed_step.tool_name or step_input.get("name") or ""
    tool_args = step_input.get("arguments") or {}
    if not tool_name:
        raise HTTPException(status_code=400, detail="Failed step does not contain a tool name")

    tool_result = await ToolRegistry.execute_tool(tool_name, tool_args)
    retry_step = await _append_control_step(
        db_session,
        run,
        step_type="retry_tool_call",
        status="completed" if tool_result.success else "failed",
        summary=f"重试工具 {tool_name} {'成功' if tool_result.success else '失败'}",
        input_data={"retry_step_id": failed_step.id, "name": tool_name, "arguments": tool_args},
        output_data=tool_result.result if tool_result.success else {"error": tool_result.error},
        error=tool_result.error or "",
    )
    retry_step.tool_name = tool_name
    retry_step.duration_ms = tool_result.duration_ms
    run.status = "completed" if tool_result.success else "failed"
    run.error = "" if tool_result.success else (tool_result.error or "")
    run.updated_at = datetime.utcnow()
    if tool_result.success:
        run.result_json = json.dumps(
            {"retried_step_id": failed_step.id, "retry_step_id": retry_step.id, "tool_name": tool_name},
            ensure_ascii=False,
            default=str,
        )

    # 双写工具观察消息到 agent_messages
    thread_mgr = ThreadManager(db_session)
    observation_content = json.dumps(
        tool_result.result if tool_result.success else {"error": tool_result.error},
        ensure_ascii=False, default=str,
    )
    await thread_mgr.append_message(
        run.session_id,  # session_id == thread_id
        {
            "role": "user",
            "content": (
                f"[工具结果 - 重试]\n"
                f"工具: {tool_name}\n"
                f"状态: {'成功' if tool_result.success else '失败'}\n"
                f"返回: {observation_content}"
            ),
        },
        run_id=run_id,
        metadata={"phase": "tool_retry", "tool_name": tool_name, "success": tool_result.success},
    )
    await db_session.commit()
    return {
        "success": tool_result.success,
        "run": _run_to_dict(run),
        "step": _step_to_dict(retry_step),
        "error": tool_result.error,
    }


@router.post("/runs/{run_id}/steps/{step_id}/confirm", summary="确认并执行 pending 工具步骤")
async def confirm_pending_step(
    run_id: str,
    step_id: int,
    db_session=Depends(get_async_session_dependency),
):
    await ensure_agent_tables()
    run = await db_session.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    step = await db_session.get(AgentRunStep, step_id)
    if not step or step.run_id != run_id:
        raise HTTPException(status_code=404, detail="Step not found")
    if step.status != "pending" or step.step_type != "tool_call":
        raise HTTPException(status_code=400, detail="Only pending tool_call steps can be confirmed")

    step_input = _safe_json_loads(step.input_json, {})
    tool_name = step.tool_name or step_input.get("name") or ""
    tool_args = step_input.get("arguments") or {}
    if not tool_name:
        raise HTTPException(status_code=400, detail="Pending step does not contain a tool name")

    confirmed_args = {**tool_args, "__confirmed": True}
    execute_args = {key: value for key, value in confirmed_args.items() if key not in {"__confirmed", "confirmed"}}
    tool_result = await ToolRegistry.execute_tool(tool_name, execute_args)
    if tool_result.success and isinstance(tool_result.result, dict) and tool_result.result.get("success") is False:
        tool_result.success = False
        tool_result.error = str(tool_result.result.get("error") or tool_result.result.get("message") or "tool returned success=false")
    confirmed_step = await _append_control_step(
        db_session,
        run,
        step_type="confirm_tool_call",
        status="completed" if tool_result.success else "failed",
        summary=f"确认执行工具 {tool_name} {'成功' if tool_result.success else '失败'}",
        input_data={"pending_step_id": step.id, "name": tool_name, "arguments": confirmed_args},
        output_data=tool_result.result if tool_result.success else {"error": tool_result.error},
        error=tool_result.error or "",
    )
    confirmed_step.tool_name = tool_name
    confirmed_step.duration_ms = tool_result.duration_ms
    step.status = "completed" if tool_result.success else "failed"
    step.error = "" if tool_result.success else (tool_result.error or "")
    run.status = "completed" if tool_result.success else "failed"
    run.error = "" if tool_result.success else (tool_result.error or "")
    run.updated_at = datetime.utcnow()
    await _sync_parent_delegation_state(
        db_session,
        run,
        child_status=run.status,
        child_result={
            "tool_name": tool_name,
            "tool_result": tool_result.result,
            "confirmed_step_id": confirmed_step.id,
        },
        child_error=run.error,
    )
    assistant_message = (
        f"已确认并执行工具 `{tool_name}`。\n\n"
        f"状态：{'成功' if tool_result.success else '失败'}\n\n"
        f"结果摘要：{_compact_tool_result_text(tool_result.result if tool_result.success else {'error': tool_result.error})}"
    )
    # 双写进 agent_messages 表（thread 为事实来源）
    thread_mgr = ThreadManager(db_session)
    await thread_mgr.append_message(
        run.session_id,  # session_id == thread_id
        {"role": "user", "content": f"确认执行上一条待确认工具：{tool_name}"},
        run_id=run_id,
        metadata={"phase": "confirm_user"},
    )
    await thread_mgr.append_message(
        run.session_id,
        {"role": "assistant", "content": assistant_message},
        run_id=run_id,
        metadata={"phase": "confirm_assistant", "tool_name": tool_name, "success": tool_result.success},
    )
    # Update conversation state via ThreadManager (M2.3: SessionManager → ThreadManager facade)
    thread = await thread_mgr.get_thread(run.session_id)
    if thread:
        context = _safe_json_loads(thread.metadata_json, {}).get("legacy_context") or {}
        conversation_state = context.get("conversation_state") if isinstance(context, dict) else None
        if isinstance(conversation_state, dict):
            conversation_state["pending_action"] = {}
            conversation_state["last_tool_result"] = {
                "tool_name": tool_name,
                "success": bool(tool_result.success),
                "summary": _compact_tool_result_text(tool_result.result if tool_result.success else {"error": tool_result.error}),
                "updated_at": datetime.utcnow().isoformat(),
            }
            conversation_state["updated_at"] = datetime.utcnow().isoformat()
            context["conversation_state"] = conversation_state
            await thread_mgr.update_context(run.session_id, context)
    await db_session.commit()
    return {
        "success": tool_result.success,
        "run": _run_to_dict(run),
        "pending_step": _step_to_dict(step),
        "step": _step_to_dict(confirmed_step),
        "message": assistant_message,
        "error": tool_result.error,
    }


@router.post("/runs/{run_id}/delegate", summary="委派 Agent 子任务")
async def delegate_run(
    run_id: str,
    request: DelegateRunRequest,
    db_session=Depends(get_async_session_dependency),
):
    await ensure_agent_tables()
    parent_run = await db_session.get(AgentRun, run_id)
    if not parent_run:
        raise HTTPException(status_code=404, detail="Run not found")
    if not request.profile_id:
        raise HTTPException(status_code=400, detail="profile_id is required")

    from app.db.database import AsyncSessionLocal
    from app.services.agent.runtime.delegation import SubagentExecutor, SubagentOrchestrator

    executor = SubagentExecutor(AsyncSessionLocal)
    orchestrator = SubagentOrchestrator(db_session, executor)
    result = await orchestrator.delegate(
        parent_run,
        [
            {
                "task_key": "manual-delegation",
                "profile_id": request.profile_id,
                "objective": request.message or f"继续处理父任务：{parent_run.objective}",
                "context": request.context or {},
            }
        ],
    )
    parent_resume = None
    if request.resume_parent and result.get("status") in {"completed", "partial"}:
        service = AgentService(db_session, user_id=parent_run.user_id)
        parent_resume = await service.resume_from_delegation_observation(parent_run, result)
        await db_session.commit()
    child_run = await db_session.get(AgentRun, result.get("child_run_id")) if result.get("child_run_id") else None
    return {
        **result,
        "parent_run": _run_to_dict(parent_run),
        "child_run": _run_to_dict(child_run) if child_run else None,
        "parent_resume": parent_resume,
    }


@router.get("/sessions/{session_id}", summary="会话详情")
async def get_session_detail(session_id: str, db_session=Depends(get_async_session_dependency)):
    manager = AgentSessionManager(db_session)
    db_sess = await manager.get_session(session_id)
    if not db_sess:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "id": db_sess.id,
        "thread_id": db_sess.id,
        "session_id": db_sess.id,
        "title": db_sess.title,
        "messages": json.loads(db_sess.messages or "[]"),
        "context": json.loads(db_sess.context or "{}"),
        "created_at": db_sess.created_at.isoformat(),
        "updated_at": db_sess.updated_at.isoformat(),
    }


@router.get("/threads/{thread_id}", summary="Agent Thread 详情")
async def get_thread_detail(thread_id: str, db_session=Depends(get_async_session_dependency)):
    await ensure_agent_tables()
    manager = ThreadManager(db_session)
    thread = await manager.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    messages = await manager.get_messages(thread_id)
    await db_session.commit()
    return {
        "id": thread.id,
        "thread_id": thread.id,
        "session_id": thread.id,
        "title": thread.title,
        "status": thread.status,
        "active_profile_id": thread.active_profile_id,
        "messages": messages,
        "context": _safe_json_loads(thread.metadata_json, {}),
        "created_at": thread.created_at.isoformat(),
        "updated_at": thread.updated_at.isoformat(),
    }


@router.delete("/sessions/{session_id}", summary="删除对话")
async def delete_session(session_id: str, db_session=Depends(get_async_session_dependency)):
    manager = AgentSessionManager(db_session)
    success = await manager.delete_session(session_id)
    await db_session.commit()
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True}


@router.delete("/threads/{thread_id}", summary="删除 Agent Thread")
async def delete_thread(thread_id: str, db_session=Depends(get_async_session_dependency)):
    await ensure_agent_tables()
    manager = ThreadManager(db_session)
    success = await manager.archive_thread(thread_id)
    await db_session.commit()
    if not success:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"success": True}


@router.get("/tools", summary="可用工具列表")
async def list_tools(category: Optional[str] = None):
    tools = ToolRegistry.list_tools(category)
    return [
        {
            "name": item.name,
            "description": item.description,
            "parameters": item.parameters,
            "category": item.category,
            "examples": item.examples,
            "requires_progress": item.requires_progress,
            "input_schema_note": item.input_schema_note,
            "output_schema_note": item.output_schema_note,
            "risk_level": item.risk_level,
            "output_type": item.output_type,
            "cost_hint": item.cost_hint,
        }
        for item in tools
    ]


@router.post("/tools/test", summary="测试 Agent 工具调用")
async def run_tool_test(
    request: ToolTestRequest,
    user_id: str = "default",
    db_session=Depends(get_async_session_dependency),
):
    await ensure_agent_tables()
    tool = ToolRegistry.get_tool(request.tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    allowed_tools: list[str] = ["*"]
    profile_data = None
    if request.profile_id:
        manager = AgentProfileManager(db_session, user_id)
        profile = await manager.get_profile(request.profile_id)
        profile_data = profile_to_dict(profile)
        allowed_tools = profile_data.get("allowed_tools") or []
        if allowed_tools and "*" not in allowed_tools and request.tool_name not in allowed_tools:
            return {
                "success": False,
                "pending_confirmation": False,
                "authorized": False,
                "tool_name": request.tool_name,
                "risk_level": tool.risk_level,
                "error": f"当前智能体无权调用工具：{request.tool_name}",
                "profile": profile_data,
            }

    if tool.risk_level in CONFIRMATION_RISK_LEVELS and not request.confirmed:
        return {
            "success": False,
            "pending_confirmation": True,
            "authorized": True,
            "tool_name": request.tool_name,
            "risk_level": tool.risk_level,
            "arguments": request.arguments or {},
            "message": f"工具 {request.tool_name} 风险等级为 {tool.risk_level}，测试执行前需要确认。",
            "profile": profile_data,
        }

    arguments = {**(request.arguments or {}), "__confirmed": True}
    execute_args = {key: value for key, value in arguments.items() if key not in {"__confirmed", "confirmed"}}
    result = await ToolRegistry.execute_tool(request.tool_name, execute_args)
    if result.success and isinstance(result.result, dict) and result.result.get("success") is False:
        result.success = False
        result.error = str(result.result.get("error") or result.result.get("message") or "tool returned success=false")
    return {
        "success": result.success,
        "pending_confirmation": False,
        "authorized": True,
        "tool_name": request.tool_name,
        "risk_level": tool.risk_level,
        "result": result.result,
        "error": result.error,
        "duration_ms": result.duration_ms,
        "profile": profile_data,
    }


@router.get("/memories", summary="获取记忆")
async def get_memories(user_id: str = "default", db_session=Depends(get_async_session_dependency)):
    manager = AgentMemoryManager(db_session, user_id)
    memories = await manager.get_all_memories()
    skills = await manager.list_skills()
    return {
        "memories": memories,
        "skills": [
            {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "skill_type": item.skill_type,
                "content": item.content,
                "version": item.version,
                "is_builtin": item.is_builtin,
                "usage_count": item.usage_count,
                "success_count": item.success_count,
                "success_rate": item.success_count / item.usage_count if item.usage_count else 0,
                "created_at": item.created_at.isoformat(),
            }
            for item in skills
        ],
    }


@router.get("/memories/view", summary="获取 Hermes 风格记忆视图")
async def get_memory_view(user_id: str = "default", db_session=Depends(get_async_session_dependency)):
    await ensure_agent_tables()
    manager = AgentMemoryManager(db_session, user_id)
    view = await manager.build_readable_memory_view()
    return {"success": True, **view}


@router.post("/memories", summary="保存记忆")
async def save_memory(
    key: str,
    request: SaveMemoryRequest | None = None,
    value: str = "",
    memory_type: str = "fact",
    importance: int = 5,
    user_id: str = "default",
    db_session=Depends(get_async_session_dependency),
):
    payload = request or SaveMemoryRequest(value=value, memory_type=memory_type, importance=importance)
    if not key.strip():
        raise HTTPException(status_code=400, detail="key is required")
    if not payload.value.strip():
        raise HTTPException(status_code=400, detail="value is required")
    manager = AgentMemoryManager(db_session, user_id)
    memory = await manager.save_memory(
        key=key.strip(),
        value=payload.value.strip(),
        memory_type=payload.memory_type or "fact",
        importance=max(1, min(int(payload.importance or 5), 10)),
        confidence=max(0.0, min(float(payload.confidence if payload.confidence is not None else 1.0), 1.0)),
    )
    await db_session.commit()
    return {"id": memory.id, "key": memory.key, "success": True}


@router.delete("/memories/{key}", summary="删除记忆")
async def delete_memory(key: str, user_id: str = "default", db_session=Depends(get_async_session_dependency)):
    manager = AgentMemoryManager(db_session, user_id)
    success = await manager.delete_memory(key)
    await db_session.commit()
    return {"success": success}


@router.post("/runs/{run_id}/steps/{step_id}/memory-candidates/save", summary="保存待确认记忆")
async def save_memory_candidates(
    run_id: str,
    step_id: int,
    request: SaveMemoryCandidatesRequest,
    user_id: str = "default",
    db_session=Depends(get_async_session_dependency),
):
    await ensure_agent_tables()
    run = await db_session.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    step = await db_session.get(AgentRunStep, step_id)
    if not step or step.run_id != run_id or step.step_type != "memory_extract":
        raise HTTPException(status_code=404, detail="Memory candidate step not found")

    payload = _safe_json_loads(step.output_json, {})
    candidates = payload.get("candidates") or []
    selected_indices = set(request.indices or range(len(candidates)))
    manager = AgentMemoryManager(db_session, user_id or run.user_id)
    saved = []
    for index, item in enumerate(candidates):
        if index not in selected_indices or not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        value = str(item.get("value") or "").strip()
        if not key or not value:
            continue
        memory = await manager.save_memory(
            key=key[:100],
            value=value,
            memory_type=str(item.get("memory_type") or item.get("type") or "fact"),
            importance=max(1, min(int(item.get("importance") or 5), 10)),
            confidence=max(0.0, min(float(item.get("confidence") or 1.0), 1.0)),
            source="user_confirmed",
            session_id=run.session_id,
            thread_id=run.session_id,  # session_id == thread_id
            run_id=run_id,
            message_ids=[str(item["message_id"])] if item.get("message_id") else None,
        )
        saved.append({"id": memory.id, "key": memory.key})

    # Dual-write memory confirmation to agent_messages for provenance
    try:
        thread_mgr = ThreadManager(db_session)
        await thread_mgr.append_message(
            run.session_id,
            {
                "role": "user",
                "content": f"[记忆确认] 已保存 {len(saved)} 条记忆: {', '.join(item['key'] for item in saved)}",
            },
            run_id=run_id,
            metadata={"phase": "memory_confirmation", "saved_count": len(saved), "saved_ids": [item["id"] for item in saved]},
        )
    except Exception:
        pass  # Non-critical: don't fail the save if dual-write fails

    step.status = "completed"
    step.summary = f"已保存 {len(saved)} 条记忆"
    step.output_json = json.dumps({**payload, "saved": saved}, ensure_ascii=False, default=str)
    run.updated_at = datetime.utcnow()
    await db_session.commit()
    return {"success": True, "saved": saved, "step": _step_to_dict(step)}


@router.post("/runs/{run_id}/steps/{step_id}/memory-candidates/discard", summary="丢弃待确认记忆")
async def discard_memory_candidates(run_id: str, step_id: int, db_session=Depends(get_async_session_dependency)):
    await ensure_agent_tables()
    run = await db_session.get(AgentRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    step = await db_session.get(AgentRunStep, step_id)
    if not step or step.run_id != run_id or step.step_type != "memory_extract":
        raise HTTPException(status_code=404, detail="Memory candidate step not found")
    step.status = "dismissed"
    step.summary = "用户已丢弃待确认记忆"
    run.updated_at = datetime.utcnow()
    # Dual-write discard to agent_messages
    try:
        thread_mgr = ThreadManager(db_session)
        await thread_mgr.append_message(
            run.session_id,
            {"role": "user", "content": "[记忆确认] 已丢弃待确认记忆"},
            run_id=run_id,
            metadata={"phase": "memory_discard"},
        )
    except Exception:
        pass
    await db_session.commit()
    return {"success": True, "step": _step_to_dict(step)}


@router.get("/skills", summary="技能列表")
async def list_skills(skill_type: Optional[str] = None, user_id: str = "default", db_session=Depends(get_async_session_dependency)):
    manager = AgentMemoryManager(db_session, user_id)
    skills = await manager.list_skills(skill_type)
    return [
        {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "skill_type": item.skill_type,
            "content": item.content,
            "version": item.version,
            "is_builtin": item.is_builtin,
            "usage_count": item.usage_count,
            "success_count": item.success_count,
            "success_rate": item.success_count / item.usage_count if item.usage_count else 0,
            "created_at": item.created_at.isoformat(),
        }
        for item in skills
    ]


@router.get("/skills/package-index", summary="文件化 Skill 包索引")
async def list_skill_package_index():
    loader = SkillPackageLoader()
    return {
        "root": str(loader.default_builtin_root()),
        "packages": loader.package_index(),
        "bundles": loader.bundle_index(),
    }


@router.get("/skills/packages/{skill_name}/files", summary="Skill 包文件列表")
async def list_skill_package_files(skill_name: str):
    loader = SkillPackageLoader()
    package = loader.get_package(skill_name)
    if package is None:
        raise HTTPException(status_code=404, detail="Skill package not found")
    return {
        "name": package.name,
        "title": package.title,
        "source_path": package.source_path,
        "files": loader.package_files(skill_name),
    }


@router.get("/skills/packages/{skill_name}/files/content", summary="读取 Skill 包文件")
async def read_skill_package_file(skill_name: str, path: str = "SKILL.md"):
    loader = SkillPackageLoader()
    package = loader.get_package(skill_name)
    if package is None:
        raise HTTPException(status_code=404, detail="Skill package not found")
    item = loader.read_package_file(skill_name, path)
    if item is None:
        raise HTTPException(status_code=404, detail="Skill package file not found")
    return {
        "name": package.name,
        "title": package.title,
        "source_path": package.source_path,
        "file": item,
    }


@router.post("/skills/bundles", summary="创建用户 Skill Bundle")
async def create_skill_bundle(request: SkillBundleCreateRequest):
    return _write_user_skill_bundle(request)


@router.put("/skills/bundles/{bundle_name}", summary="更新用户 Skill Bundle")
async def update_skill_bundle(bundle_name: str, request: SkillBundleCreateRequest):
    if str(request.name or "").strip() and str(request.name or "").strip().lower() != str(bundle_name or "").strip().lower():
        raise HTTPException(status_code=400, detail="Bundle name in path and body must match")
    request.name = bundle_name
    return _write_user_skill_bundle(request)


@router.delete("/skills/bundles/{bundle_name}", summary="删除用户 Skill Bundle")
async def delete_skill_bundle(bundle_name: str):
    name = str(bundle_name or "").strip().lower()
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{1,79}", name):
        raise HTTPException(status_code=400, detail="Bundle name must use 2-80 ASCII letters, numbers, hyphen or underscore")
    root = SkillPackageLoader.default_builtin_root().resolve()
    bundle_dir = (root / "user" / "bundles").resolve()
    target = (bundle_dir / f"{name}.yaml").resolve()
    try:
        target.relative_to(bundle_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Resolved bundle path is outside user bundle root")
    if not target.exists():
        raise HTTPException(status_code=404, detail="User bundle not found")
    target.unlink()
    return {"success": True, "name": name}


def _write_user_skill_bundle(request: SkillBundleCreateRequest):
    name = str(request.name or "").strip().lower()
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{1,79}", name):
        raise HTTPException(status_code=400, detail="Bundle name must use 2-80 ASCII letters, numbers, hyphen or underscore")
    skills = [str(item or "").strip() for item in request.skills if str(item or "").strip()]
    if not skills:
        raise HTTPException(status_code=400, detail="Bundle must include at least one skill")
    known_skills = {item["name"] for item in SkillPackageLoader().package_index()}
    missing = [item for item in skills if item not in known_skills]
    if missing:
        raise HTTPException(status_code=400, detail={"message": "Bundle references unknown skills", "missing": missing})

    root = SkillPackageLoader.default_builtin_root().resolve()
    bundle_dir = (root / "user" / "bundles").resolve()
    bundle_dir.mkdir(parents=True, exist_ok=True)
    target = (bundle_dir / f"{name}.yaml").resolve()
    try:
        target.relative_to(bundle_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Resolved bundle path is outside user bundle root")

    description = str(request.description or "").strip() or f"用户自定义 Bundle：{name}"
    instruction = str(request.instruction or "").strip()
    yaml_lines = [
        f"name: {json.dumps(name, ensure_ascii=False)}",
        f"description: {json.dumps(description, ensure_ascii=False)}",
        "skills:",
        *[f"  - {json.dumps(skill, ensure_ascii=False)}" for skill in skills],
    ]
    if instruction:
        yaml_lines.extend(["instruction: |", *[f"  {line}" for line in instruction.splitlines()]])
    target.write_text("\n".join(yaml_lines).strip() + "\n", encoding="utf-8", newline="\n")
    bundle = next((item for item in SkillPackageLoader().bundle_index() if item["name"] == name), None)
    return {"success": True, "bundle": bundle}


def _skill_draft_to_dict(item) -> dict:
    try:
        metadata = json.loads(item.metadata_json or "{}")
    except json.JSONDecodeError:
        metadata = {}
    try:
        diagnostics = json.loads(item.diagnostics_json or "[]")
    except json.JSONDecodeError:
        diagnostics = []
    review = _skill_draft_review(item)
    return {
        "id": item.id,
        "user_id": item.user_id,
        "name": item.name,
        "title": item.title,
        "description": item.description,
        "skill_type": item.skill_type,
        "content": item.content,
        "metadata": metadata,
        "source_type": item.source_type,
        "source_url": item.source_url,
        "source_run_id": item.source_run_id,
        "status": item.status,
        "target_path": item.target_path,
        "checksum": item.checksum,
        "diagnostics": diagnostics,
        "review": review,
        "created_at": item.created_at.isoformat() if item.created_at else "",
        "updated_at": item.updated_at.isoformat() if item.updated_at else "",
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else "",
    }


def _skill_draft_review(item) -> dict:
    target_path = str(getattr(item, "target_path", "") or "")
    review = {
        "mode": "create",
        "existing_path": "",
        "existing_checksum": "",
        "diff": "",
    }
    if not target_path:
        return review
    try:
        root = SkillPackageLoader.default_builtin_root().resolve()
        target = (Path(__file__).resolve().parents[3] / target_path).resolve()
        target.relative_to(root)
    except Exception:
        return review
    if not target.exists() or not target.is_file():
        return review
    try:
        existing = target.read_text(encoding="utf-8")
    except OSError:
        return review
    existing_package, _diagnostics = SkillPackageLoader().validate_raw_package(existing, target)
    review["mode"] = "update"
    review["existing_path"] = target_path
    review["existing_checksum"] = existing_package.checksum if existing_package else ""
    review["diff"] = "\n".join(
        difflib.unified_diff(
            existing.splitlines(),
            str(getattr(item, "content", "") or "").splitlines(),
            fromfile=f"current/{getattr(item, 'name', 'skill')}",
            tofile=f"draft/{getattr(item, 'name', 'skill')}",
            lineterm="",
            n=3,
        )
    )
    return review


def _raise_skill_draft_error(exc: SkillDraftError) -> None:
    raise HTTPException(
        status_code=400,
        detail={
            "message": str(exc),
            "diagnostics": exc.diagnostics,
        },
    )


@router.get("/skills/drafts", summary="Skill 待审批草稿列表")
async def list_skill_drafts(
    status: str = "pending",
    user_id: str = "default",
    db_session=Depends(get_async_session_dependency),
):
    await ensure_agent_tables()
    service = AgentSkillDraftService(db_session, user_id=user_id)
    drafts = await service.list_drafts(status=status)
    return {"drafts": [_skill_draft_to_dict(item) for item in drafts]}


@router.post("/skills/drafts", summary="创建 Skill 草稿")
async def create_skill_draft(
    request: SkillDraftCreateRequest,
    user_id: str = "default",
    db_session=Depends(get_async_session_dependency),
):
    await ensure_agent_tables()
    service = AgentSkillDraftService(db_session, user_id=user_id)
    try:
        draft = await service.create_manual_draft(
            request.content,
            source_type=request.source_type,
            source_url=request.source_url,
            source_run_id=request.source_run_id,
            source_step_ids=request.source_step_ids,
        )
    except SkillDraftError as exc:
        _raise_skill_draft_error(exc)
    return {"draft": _skill_draft_to_dict(draft)}


@router.post("/skills/drafts/import-url", summary="从 URL 导入 Skill 草稿")
async def import_skill_draft_url(
    request: SkillDraftImportUrlRequest,
    user_id: str = "default",
    db_session=Depends(get_async_session_dependency),
):
    await ensure_agent_tables()
    service = AgentSkillDraftService(db_session, user_id=user_id)
    try:
        draft = await service.import_url(request.url)
    except SkillDraftError as exc:
        _raise_skill_draft_error(exc)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=400,
            detail={"message": f"Fetch skill URL failed: {exc}", "diagnostics": [str(exc)]},
        )
    return {"draft": _skill_draft_to_dict(draft)}


@router.get("/skills/drafts/{draft_id}", summary="读取 Skill 草稿")
async def get_skill_draft(
    draft_id: int,
    user_id: str = "default",
    db_session=Depends(get_async_session_dependency),
):
    await ensure_agent_tables()
    service = AgentSkillDraftService(db_session, user_id=user_id)
    draft = await service.get_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Skill draft not found")
    return {"draft": _skill_draft_to_dict(draft)}


@router.post("/skills/drafts/{draft_id}/approve", summary="批准并启用 Skill 草稿")
async def approve_skill_draft(
    draft_id: int,
    user_id: str = "default",
    db_session=Depends(get_async_session_dependency),
):
    await ensure_agent_tables()
    service = AgentSkillDraftService(db_session, user_id=user_id)
    try:
        draft = await service.approve(draft_id)
    except SkillDraftError as exc:
        _raise_skill_draft_error(exc)
    return {"draft": _skill_draft_to_dict(draft)}


@router.post("/skills/drafts/{draft_id}/reject", summary="拒绝 Skill 草稿")
async def reject_skill_draft(
    draft_id: int,
    request: SkillDraftRejectRequest,
    user_id: str = "default",
    db_session=Depends(get_async_session_dependency),
):
    await ensure_agent_tables()
    service = AgentSkillDraftService(db_session, user_id=user_id)
    try:
        draft = await service.reject(draft_id, request.reason)
    except SkillDraftError as exc:
        _raise_skill_draft_error(exc)
    return {"draft": _skill_draft_to_dict(draft)}


@router.post("/skills/route-preview", summary="Skill 路由预览")
async def preview_skill_route(request: SkillRoutePreviewRequest):
    router_instance = SkillRouter()
    activation = router_instance.parse_activation(request.message)
    routes = router_instance.route(
        message=activation.cleaned_message or request.message,
        context=request.context,
        allowed_tools=request.allowed_tools,
        default_skill_ids=request.default_skill_ids,
        activated_skill_ids=list(activation.skill_ids),
        max_skills=request.max_skills,
    )
    return {
        "activation": {
            "cleaned_message": activation.cleaned_message,
            "skill_ids": list(activation.skill_ids),
            "bundle_ids": list(activation.bundle_ids),
            "bundle_instruction": activation.bundle_instruction,
            "diagnostics": list(activation.diagnostics),
        },
        "routes": [
            {
                "skill_id": item.skill_id,
                "reason": item.reason,
                "score": item.score,
                "source": item.source,
                "trigger_type": item.trigger_type,
                "matches": list(item.matches),
            }
            for item in routes
        ],
        "diagnostic": router_instance.diagnose_target(
            target_skill_id=request.target_skill_id,
            message=activation.cleaned_message or request.message,
            context=request.context,
            allowed_tools=request.allowed_tools,
            routes=routes,
        ) if request.target_skill_id else {},
    }


@router.post("/skills", summary="创建技能")
async def create_skill(request: CreateSkillRequest, user_id: str = "default", db_session=Depends(get_async_session_dependency)):
    manager = AgentMemoryManager(db_session, user_id)
    skill = await manager.create_skill(
        name=request.name,
        description=request.description,
        content=request.content,
        skill_type=request.skill_type,
    )
    await db_session.commit()
    return {"id": skill.id, "name": skill.name, "success": True}


@router.post("/send", summary="发送到 Agent")
async def send_to_agent(request: SendToAgentRequest, db_session=Depends(get_async_session_dependency)):
    action_desc = {
        "process": "处理",
        "analyze": "分析",
        "edit": "编辑",
        "generate": "生成",
    }.get(request.action, request.action)
    message = f"请帮我{action_desc}来自【{request.source_page}】的内容：{request.data}"
    service = AgentService(db_session)
    return await service.chat(
        session_id="",
        user_message=message,
        context={"source_page": request.source_page, "action": request.action, **request.data},
        profile_id=request.profile_id,
    )


# ---------------------------------------------------------------------------
# Multi-Agent Scene Simulation (Phase 5)
# ---------------------------------------------------------------------------


class SceneSimulationRequest(BaseModel):
    """Request to run a multi-agent scene simulation pipeline."""

    project_id: Optional[str] = Field(default=None, description="创作项目 ID")
    scene_context: str = Field(default="", description="场景/章节上下文描述")
    characters_of_interest: list[str] = Field(default_factory=list, description="参与本场景的角色名称列表")
    iteration_budget_per_agent: int = Field(default=8, ge=4, le=20, description="每个智能体的迭代预算")
    store_as_candidate: bool = Field(default=True, description="是否将输出存为候选版本")


@router.post("/multi-agent/scene-simulation", summary="多智能体场景推演")
async def run_scene_simulation(
    request: SceneSimulationRequest,
    db_session=Depends(get_async_session_dependency),
):
    """运行多智能体场景推演流水线。

    流水线：天意总导演 → 角色演员(每角色) → 编辑润色师 → 创作导演(合成)。

    每个智能体独立运行，前序输出作为后续上下文。
    所有输出存为候选版本，不覆盖已确认内容。
    """
    from app.services.agent.multi_agent_coordinator import (
        MultiAgentCoordinator,
        SimulationConfig,
    )

    service = AgentService(db_session)
    coordinator = MultiAgentCoordinator(service)

    config = SimulationConfig(
        project_id=request.project_id,
        scene_context=request.scene_context,
        characters_of_interest=request.characters_of_interest,
        iteration_budget_per_agent=request.iteration_budget_per_agent,
        store_as_candidate=request.store_as_candidate,
    )

    result = await coordinator.run_team("scene-sim", config)
    return result
