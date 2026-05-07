"""
YLCraft — Agent API 路由

POST /api/v1/agent/chat       — 对话（支持 SSE 流式）
GET  /api/v1/agent/sessions   — 会话列表
GET  /api/v1/agent/sessions/{id} — 获取会话详情
DELETE /api/v1/agent/sessions/{id} — 删除会话
GET  /api/v1/agent/tools      — 工具列表
GET  /api/v1/agent/memories   — 获取记忆
DELETE /api/v1/agent/memories/{key} — 删除记忆
GET  /api/v1/agent/skills     — 获取技能列表
POST /api/v1/agent/send       — 发送到 Agent（其他页面调用）
POST /api/v1/agent/stream     — SSE 流式对话（完整打字机效果）
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.db.database import get_session
from app.services.agent.service import AgentService
from app.services.agent.session.manager import SessionManager as AgentSessionManager
from app.services.agent.memory.manager import MemoryManager as AgentMemoryManager
from app.services.agent.registry import ToolRegistry

router = APIRouter(tags=["Agent"])
logger = logging.getLogger("ylcraft.api.agent")


# =============================================================================
# 请求/响应模型
# =============================================================================

class ChatRequest(BaseModel):
    message: str = Field(..., description="用户消息")
    session_id: Optional[str] = Field(None, description="会话 ID（空则创建新会话）")
    context: Optional[dict] = Field(default_factory=dict, description="额外上下文")
    stream: bool = Field(True, description="是否使用 SSE 流式响应")


class SendToAgentRequest(BaseModel):
    """其他页面「发送到 Agent」的请求"""
    source_page: str = Field(..., description="来源页面：assets / clip / subtitle / bgm / breaker")
    action: str = Field(..., description="操作：process / analyze / edit / generate")
    data: dict = Field(default_factory=dict, description="页面传递的上下文数据")


class CreateSkillRequest(BaseModel):
    name: str
    description: str
    content: str
    skill_type: str = "tool"


# =============================================================================
# 对话接口
# =============================================================================

@router.post("/chat", summary="Agent 对话")
async def chat(request: ChatRequest, db_session=Depends(get_session)):
    """
    Agent 对话接口。

    - stream=True：使用 SSE 流式返回（打字机效果）
    - stream=False：普通 JSON 返回
    """
    service = AgentService(db_session)

    if request.stream:
        return StreamingResponse(
            _chat_stream(service, request),
            media_type="text/event-stream",
        )
    else:
        result = await service.chat(
            session_id=request.session_id or "",
            user_message=request.message,
            context=request.context,
        )
        return result


async def _chat_stream(
    service: AgentService, request: ChatRequest
) -> AsyncGenerator[str, None]:
    """SSE 流式返回 Agent 回复（打字机效果）"""
    try:
        # 开始事件
        yield f"data: {json.dumps({'event': 'start'}, ensure_ascii=False)}\n\n"

        # 调用服务（目前不支持真正的 token by token，等 LLM streaming 后增强）
        result = await service.chat(
            session_id=request.session_id or "",
            user_message=request.message,
            context=request.context,
        )

        # 流式返回 reply（字符级打字机）
        reply = result.get("reply", "")
        for i in range(0, len(reply), 10):  # 每 10 个字符一个事件
            chunk = reply[i : i + 10]
            yield f"data: {json.dumps({'event': 'token', 'data': chunk}, ensure_ascii=False)}\n\n"

        # 发送 tool calls
        if result.get("tool_calls"):
            yield f"data: {json.dumps({'event': 'tool_calls', 'data': result['tool_calls']}, ensure_ascii=False)}\n\n"

        # 结束事件
        yield f"data: {json.dumps({'event': 'done', 'data': {'session_id': result['session_id']}}, ensure_ascii=False)}\n\n"

    except Exception as e:
        logger.error(f"[Agent API] Stream error: {e}")
        yield f"data: {json.dumps({'event': 'error', 'data': str(e)}, ensure_ascii=False)}\n\n"


# =============================================================================
# 会话管理
# =============================================================================

@router.get("/sessions", summary="会话列表")
async def list_sessions(user_id: str = "default", db_session=Depends(get_session)):
    mgr = AgentSessionManager(db_session)
    sessions = await mgr.list_sessions(user_id)
    return [
        {
            "id": s.id,
            "title": s.title,
            "created_at": s.created_at.isoformat(),
            "updated_at": s.updated_at.isoformat(),
        }
        for s in sessions
    ]


@router.get("/sessions/{session_id}", summary="会话详情")
async def get_session_detail(session_id: str, db_session=Depends(get_session)):
    mgr = AgentSessionManager(db_session)
    db_sess = await mgr.get_session(session_id)
    if not db_sess:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "id": db_sess.id,
        "title": db_sess.title,
        "messages": json.loads(db_sess.messages or "[]"),
        "context": json.loads(db_sess.context or "{}"),
        "created_at": db_sess.created_at.isoformat(),
        "updated_at": db_sess.updated_at.isoformat(),
    }


@router.delete("/sessions/{session_id}", summary="删除会话")
async def delete_session(session_id: str, db_session=Depends(get_session)):
    mgr = AgentSessionManager(db_session)
    success = await mgr.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True}


# =============================================================================
# 工具列表
# =============================================================================

@router.get("/tools", summary="可用工具列表")
async def list_tools(category: Optional[str] = None):
    """获取所有已注册的工具"""
    tools = ToolRegistry.list_tools(category)
    return [
        {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
            "category": t.category,
            "examples": t.examples,
        }
        for t in tools
    ]


# =============================================================================
# 记忆管理
# =============================================================================

@router.get("/memories", summary="获取记忆上下文")
async def get_memories(
    user_id: str = "default", db_session=Depends(get_session)
):
    mgr = AgentMemoryManager(db_session, user_id)
    memories = await mgr.get_all_memories()
    skills = await mgr.list_skills(min_usage=4)
    return {
        "memories": memories,
        "skills": [
            {
                "id": s.id,
                "name": s.name,
                "description": s.description,
                "usage_count": s.usage_count,
                "success_rate": (
                    s.success_count / s.usage_count
                    if s.usage_count > 0
                    else 0
                ),
            }
            for s in skills
        ],
    }


@router.delete("/memories/{key}", summary="删除记忆")
async def delete_memory(
    key: str, user_id: str = "default", db_session=Depends(get_session)
):
    mgr = AgentMemoryManager(db_session, user_id)
    success = await mgr.delete_memory(key)
    return {"success": success}


@router.post("/memories", summary="保存记忆")
async def save_memory(
    key: str,
    value: str,
    memory_type: str = "fact",
    importance: int = 5,
    user_id: str = "default",
    db_session=Depends(get_session),
):
    mgr = AgentMemoryManager(db_session, user_id)
    memory = await mgr.save_memory(key, value, memory_type, importance)
    return {"id": memory.id, "key": memory.key, "success": True}


# =============================================================================
# 技能管理
# =============================================================================

@router.get("/skills", summary="获取技能列表")
async def list_skills(
    skill_type: Optional[str] = None,
    user_id: str = "default",
    db_session=Depends(get_session),
):
    mgr = AgentMemoryManager(db_session, user_id)
    skills = await mgr.list_skills(skill_type)
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "skill_type": s.skill_type,
            "usage_count": s.usage_count,
            "success_count": s.success_count,
            "created_at": s.created_at.isoformat(),
        }
        for s in skills
    ]


@router.post("/skills", summary="创建技能")
async def create_skill(
    request: CreateSkillRequest,
    user_id: str = "default",
    db_session=Depends(get_session),
):
    mgr = AgentMemoryManager(db_session, user_id)
    skill = await mgr.create_skill(
        name=request.name,
        description=request.description,
        content=request.content,
        skill_type=request.skill_type,
    )
    return {"id": skill.id, "name": skill.name, "success": True}


# =============================================================================
# 发送到 Agent（其他页面调用）
# =============================================================================

@router.post("/send", summary="发送到 Agent（跨页面调用）")
async def send_to_agent(
    request: SendToAgentRequest, db_session=Depends(get_session)
):
    """
    其他页面「发送到 Agent」的统一入口。

    示例：
    - 素材库 → 分析多个素材：source_page="assets", action="analyze", data={"asset_ids": [1,2,3]}
    - 剪辑 → 智能剪辑：source_page="clip", action="auto_edit", data={"video_path": "..."}
    """
    # 构造发给 Agent 的消息
    action_desc = {
        "process": "处理",
        "analyze": "分析",
        "edit": "编辑",
        "generate": "生成",
    }.get(request.action, request.action)

    message = f"请帮我{action_desc}来自【{request.source_page}】的内容：{request.data}"

    service = AgentService(db_session)
    result = await service.chat(
        session_id="",  # 创建新会话
        user_message=message,
        context={
            "source_page": request.source_page,
            "action": request.action,
            **request.data,
        },
    )
    return result
