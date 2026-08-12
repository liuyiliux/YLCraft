"""LLM planning runtime for AgentService."""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

from app.services.agent.context_compressor import ContextCompressor, token_budget_check
from app.services.agent.registry import ToolRegistry
from app.services.ai.types import LLMMessage

logger = logging.getLogger("ylcraft.agent.runtime.planner")


ProviderChainBuilder = Callable[[dict[str, Any]], Awaitable[list[tuple[str | None, str | None]]]]


class Planner:
    """Build prompts, call LLM providers, and parse tool call plans."""

    def __init__(
        self,
        *,
        llm_manager_getter: Callable[[], Any],
        provider_chain_builder: ProviderChainBuilder,
        compressor: ContextCompressor | None = None,
    ):
        self._llm_manager_getter = llm_manager_getter
        self._provider_chain_builder = provider_chain_builder
        self._compressor = compressor or ContextCompressor()

    async def plan(
        self,
        *,
        messages: list[dict[str, Any]],
        memory_context: str,
        profile: dict[str, Any],
        agent_system_prompt: str,
        context_summary: str = "",
        short_term_context: str = "",
        followup_resolution: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        allowed_tools = profile.get("_effective_allowed_tools", profile.get("allowed_tools") or [])
        excluded_tools = {"delegate_agent_tasks"} if not profile.get("can_delegate") else set()
        tool_index_context = profile.get("_tool_index_context") or self._build_tool_index_context(
            allowed_tools,
            excluded_tools=excluded_tools,
        )
        system_parts = [
            agent_system_prompt,
            f"当前智能体：{profile.get('name') or '默认智能体'}",
            profile.get("system_prompt") or "",
        ]
        if context_summary:
            system_parts.append(f"项目上下文：\n{context_summary}")
        if short_term_context:
            system_parts.append(f"短期对话上下文：\n{short_term_context}")
        if memory_context:
            system_parts.append(f"记忆上下文：\n{memory_context}")
        if tool_index_context:
            system_parts.append(f"可用工具索引：\n{tool_index_context}")
        if followup_resolution and followup_resolution.get("instruction"):
            system_parts.append(
                "多轮续问解析：\n"
                f"{followup_resolution['instruction']}\n"
                "如果本轮用户只是补充平台、工具、账号、范围、排序或确认条件，必须继承上一轮未完成目标；"
                "不要把短句当成全新任务，也不要重复询问已经在历史里出现的关键词。"
            )
        if allowed_tools and "*" not in allowed_tools:
            system_parts.append("当前智能体允许调用的工具：" + "、".join(allowed_tools))

        system_text = "\n\n".join(part for part in system_parts if part)
        over_budget, est_tokens = token_budget_check(messages, system_parts)
        if over_budget:
            logger.info("[Planner] token budget exceeded (est=%d), compressing", est_tokens)
            messages = await self._compressor.ensure_fits(
                messages=messages,
                system_prompt=system_text,
                memory_context=memory_context,
                profile=profile,
            )

        llm_messages = [
            LLMMessage(role="system", content=system_text),
            *[
                LLMMessage(role=str(message.get("role") or "user"), content=str(message.get("content") or ""))
                for message in messages
                if message.get("role") in {"user", "assistant", "system"}
            ],
        ]
        tools = ToolRegistry.get_openai_tools_spec(
            allowed_tools=allowed_tools,
            excluded_tools=excluded_tools,
        )
        providers_to_try = await self._provider_chain_builder(profile)
        last_error = None
        result = None
        for idx, (provider_name, model_name) in enumerate(providers_to_try):
            try:
                if idx > 0:
                    logger.warning("[Planner] provider failover: trying %s/%s", provider_name, model_name)
                result = await self._llm_manager_getter().chat(
                    messages=llm_messages,
                    backend_name=provider_name,
                    model=model_name,
                    tools=tools if tools else None,
                )
                if result.success:
                    break
                last_error = result.error or f"{provider_name} returned unsuccessful"
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                logger.warning("[Planner] LLM provider %s failed: %s", provider_name, exc)
        else:
            logger.exception("[Planner] all LLM providers failed, last error: %s", last_error)
            return {"content": f"Agent 调用模型失败（已尝试 {len(providers_to_try)} 个供应商）：{last_error}", "tool_calls": []}

        if not result or not result.success:
            return {"content": f"Agent 调用模型失败：{getattr(result, 'error', last_error)}", "tool_calls": []}
        tool_calls = result.tool_calls or self.parse_tool_calls(result.content or "")
        return {
            "content": result.content or "",
            "tool_calls": tool_calls,
            "native_tool_calls": bool(result.tool_calls),
        }

    def parse_tool_calls(self, content: str) -> list[dict[str, Any]]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return []
        if isinstance(data, dict) and isinstance(data.get("tool_calls"), list):
            return data["tool_calls"]
        if isinstance(data, dict) and (data.get("type") == "tool_call" or data.get("name")):
            return [data]
        return []

    def _build_tool_index_context(
        self,
        allowed_tools: list[str] | None,
        *,
        excluded_tools: set[str] | None = None,
    ) -> str:
        allow_all = not allowed_tools or "*" in allowed_tools
        allowed = set(allowed_tools or [])
        excluded = excluded_tools or set()
        tools = [
            tool
            for tool in ToolRegistry.get_all_tools()
            if tool.name not in excluded and (allow_all or tool.name in allowed)
        ]
        if not tools:
            return ""
        grouped: dict[str, list[str]] = {}
        for tool in sorted(tools, key=lambda item: (item.category, item.name)):
            summary = tool.description_short or tool.description.splitlines()[0]
            grouped.setdefault(tool.category or "general", []).append(f"{tool.name}：{summary}")
        lines = [
            "下面是当前可调用工具的简表。需要执行时优先返回 tool_calls JSON 或使用原生 function calling；不要声称没有这些能力。",
        ]
        tool_count = 0
        max_tools = 90
        for category, items in grouped.items():
            if tool_count >= max_tools:
                break
            lines.append(f"- {category}")
            for item in items:
                if tool_count >= max_tools:
                    break
                lines.append(f"  - {item}")
                tool_count += 1
        if len(tools) > tool_count:
            lines.append(f"- ...另有 {len(tools) - tool_count} 个低频工具已省略，可在工具 schema 中查看。")
        return "\n".join(lines)
