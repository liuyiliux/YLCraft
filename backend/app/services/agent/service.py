"""
YLCraft — Agent 核心服务（Agent Loop，参考 Hermes 思想）

核心流程：
1. 接收用户消息
2. 注入记忆上下文（L2 + L3）
3. 调用 LLM（传入 tools 列表）
4. LLM 返回 tool_calls → 执行工具
5. 将工具结果返回给 LLM
6. LLM 返回最终回复
7. 沉淀记忆（自动创建 Skill）
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contracts.types import LLMMessage, MediaType
from app.services.agent.registry import ToolRegistry, ToolCallResult
from app.services.agent.session.manager import SessionManager
from app.services.agent.memory.manager import MemoryManager
from app.services.llm.manager import get_manager

logger = logging.getLogger("ylcraft.agent.service")


# =============================================================================
# Agent 系统提示词
# =============================================================================

AGENT_SYSTEM_PROMPT = """你是一名专业的 YLCraft 视频创作助手。

你可以帮助用户完成以下任务：
- 素材搜索与管理（搜索、下载、标注视频/图片/音频素材）
- 视频剪辑（CutClaw Agent / NarratoAI Pipeline / MoE 多专家三种模式）
- 字幕提取与烧录（支持 SRT/ASS/VTT，自动生成多种样式）
- BGM 配乐（10+ 内置曲目，支持混音和淡入淡出）
- 爆款拆解（分析抖音/B站/快手链接，提取文案结构和分镜）

**重要原则：**
1. 每次只做一件事，完成后再做下一件
2. 优先使用工具完成任务，不要猜测
3. 工具调用失败时，向用户清晰说明错误原因
4. 越用越聪明：如果你发现某个复杂任务可以沉淀为可复用技能，告诉用户

你有以下工具可用：
"""


class AgentService:
    """
    Agent 核心服务。

    使用方式：
        agent = AgentService(session, user_id="default")
        result = await agent.chat(session_id, user_message)
    """

    def __init__(self, session: AsyncSession, user_id: str = "default"):
        self.session = session
        self.user_id = user_id
        self.session_mgr = AgentSessionManager(session)
        self.memory_mgr = AgentMemoryManager(session, user_id)
        self._llm_manager = None

    @property
    def llm_manager(self):
        """延迟获取 LLM Manager"""
        if self._llm_manager is None:
            self._llm_manager = get_manager()
        return self._llm_manager

    # -----------------------------------------------------------------
    # 核心对话接口
    # -----------------------------------------------------------------

    async def chat(
        self,
        session_id: str,
        user_message: str,
        context: Optional[dict] = None,
    ) -> dict:
        """
        处理一轮对话。

        返回：
        {
            "session_id": str,
            "reply": str,           # AI 最终回复
            "tool_calls": list,     # 本轮调用的工具列表
            "done": bool,          # 是否完成（未来支持多轮 tool call）
        }
        """
        # 1. 确保会话存在
        db_session = await self.session_mgr.get_session(session_id)
        if not db_session:
            db_session = await self.session_mgr.create_session(
                user_id=self.user_id, title=user_message[:50]
            )
            session_id = db_session.id

        # 2. 更新上下文（如果调用方传了）
        if context:
            await self.session_mgr.update_context(session_id, context)

        # 3. 追加用户消息
        await self.session_mgr.append_message(session_id, {
            "role": "user",
            "content": user_message,
        })

        # 4. 获取对话历史
        messages = await self.session_mgr.get_messages(session_id)

        # 5. 注入记忆上下文到 system prompt
        memory_context = await self.memory_mgr.build_memory_context()

        # 6. 调用 LLM（带 tools）
        llm_response = await self._call_llm_with_tools(messages, memory_context)

        # 7. 处理 tool calls（如果有）
        tool_call_results = []
        if llm_response.get("tool_calls"):
            for tool_call in llm_response["tool_calls"]:
                result = await self._execute_tool_call(tool_call, session_id)
                tool_call_results.append(result)
                # 将 tool result 追加到 messages，继续调用 LLM
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result.result if result.success else result.error, ensure_ascii=False),
                })

            # 再次调用 LLM，让它基于 tool results 生成最终回复
            llm_response = await self._call_llm_with_tools(messages, memory_context)

        # 8. 提取最终回复
        reply = llm_response.get("content", "")

        # 9. 追加 AI 回复到会话
        await self.session_mgr.append_message(session_id, {
            "role": "assistant",
            "content": reply,
        })

        # 10. 尝试从对话中沉淀记忆（Hermes 核心思想）
        await self._maybe_save_memory(user_message, reply)

        return {
            "session_id": session_id,
            "reply": reply,
            "tool_calls": [self._tool_result_to_dict(r) for r in tool_call_results],
            "done": True,
        }

    # -----------------------------------------------------------------
    # 私有方法：LLM 调用 + Tool 执行
    # -----------------------------------------------------------------

    async def _call_llm_with_tools(self, messages: list[dict], memory_context: str) -> dict:
        """
        调用 LLM，传入 tools 列表。

        接入 YLCraft 的 BackendManager（支持豆包等 LLM 后端）。
        """
        # 构造带记忆上下文的 messages
        system_messages = []
        if memory_context:
            system_messages.append(LLMMessage(
                role="system",
                content=f"【记忆上下文】\n{memory_context}\n\n请根据以上记忆上下文，结合用户的问题给出回答。如果记忆中有相关信息，优先使用。"
            ))

        # 构建完整的 messages
        llm_messages = system_messages + [
            LLMMessage(role=msg["role"], content=msg["content"])
            for msg in messages
        ]

        # 获取 tools spec
        tools = ToolRegistry.get_openai_tools_spec()

        # 调用 LLM
        try:
            result = await self.llm_manager.chat(
                messages=llm_messages,
                tools=tools if tools else None,
            )

            if result.success:
                # 检查是否返回了 tool_calls（通过 usage 字段传递的扩展信息）
                response_content = result.content

                # 尝试解析 tool_calls（如果有）
                tool_calls = self._parse_tool_calls(response_content)

                return {
                    "content": response_content,
                    "tool_calls": tool_calls,
                }
            else:
                logger.error(f"[AgentService] LLM call failed: {result.error}")
                return {
                    "content": f"抱歉，AI 服务暂时不可用：{result.error}",
                    "tool_calls": [],
                }

        except Exception as e:
            logger.error(f"[AgentService] LLM call error: {e}")
            return {
                "content": f"抱歉，发生了错误：{str(e)}",
                "tool_calls": [],
            }

    def _parse_tool_calls(self, content: str) -> list[dict]:
        """
        解析 LLM 返回的 tool_calls。

        豆包等模型的 tool_calls 格式可能不同，这里做兼容处理。
        简单实现：如果 content 是 JSON 且包含 tool_calls 字段，则解析。
        """
        tool_calls = []

        # 尝试解析为 JSON
        try:
            data = json.loads(content)
            if isinstance(data, dict) and "tool_calls" in data:
                tool_calls = data["tool_calls"]
            elif isinstance(data, dict) and data.get("type") == "tool_call":
                tool_calls = [data]
        except json.JSONDecodeError:
            pass

        return tool_calls

    async def _execute_tool_call(self, tool_call: dict, session_id: str) -> ToolCallResult:
        """执行单个 tool call"""
        # 处理不同的 tool_call 格式
        if isinstance(tool_call, dict):
            if "function" in tool_call:
                # OpenAI 格式
                tool_name = tool_call.get("function", {}).get("name", "")
                tool_args_str = tool_call.get("function", {}).get("arguments", "{}")
            else:
                # 简化格式
                tool_name = tool_call.get("name", "")
                tool_args_str = tool_call.get("arguments", "{}")
        else:
            tool_name = str(tool_call)
            tool_args_str = "{}"

        try:
            tool_args = json.loads(tool_args_str)
        except json.JSONDecodeError:
            tool_args = {}

        result = await ToolRegistry.execute_tool(tool_name, tool_args)

        # 记录 tool call 日志
        from app.db.models.agent import AgentToolCall
        log = AgentToolCall(
            session_id=session_id,
            tool_name=tool_name,
            tool_args=json.dumps(tool_args, ensure_ascii=False),
            result=str(result.result)[:500] if result.result else None,
            success=result.success,
            duration_ms=result.duration_ms,
        )
        self.session.add(log)

        return result

    def _tool_result_to_dict(self, result: ToolCallResult) -> dict:
        """将 ToolCallResult 转换为 dict"""
        return {
            "tool_name": result.tool_name,
            "success": result.success,
            "result": result.result,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }

    async def _maybe_save_memory(self, user_msg: str, reply: str) -> None:
        """
        从对话中自动沉淀记忆（Hermes 核心思想）。

        简单启发式：
        - 用户说"记住..." → 保存到 L2
        - 对话涉及偏好设置 → 保存到 L2
        - 复杂任务（>3 个 tool calls）→ 考虑沉淀为 L3 Skill
        """
        # 简单实现：检测"记住"关键词
        if "记住" in user_msg or "remember" in user_msg.lower():
            # 提取要记住的内容（简单实现）
            await self.memory_mgr.save_memory(
                key=f"user_note_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                value=user_msg,
                memory_type="preference",
                importance=7,
            )
