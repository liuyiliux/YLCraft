"""Tool execution runtime for AgentService."""

from __future__ import annotations

import json
import uuid
from typing import Any, Awaitable, Callable

from app.services.agent.registry import ToolCallResult, ToolRegistry


CONFIRMATION_RISK_LEVELS = {"write", "delete", "costly"}
AUTO_CONFIRMED_WRITE_TOOLS = {
    "upsert_provider_metadata",
    "create_ai_connector",
    "update_ai_connector",
}

ToolLogCallback = Callable[[str, dict[str, Any], ToolCallResult], Awaitable[None]]


class ToolExecutor:
    """Authorize, repair, confirm, and execute agent tool calls."""

    def tool_name_and_args(self, tool_call: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if "function" in tool_call:
            function = tool_call.get("function") or {}
            name = str(function.get("name") or "")
            raw_args = function.get("arguments") or "{}"
        else:
            name = str(tool_call.get("name") or "")
            raw_args = tool_call.get("arguments") or "{}"
        if isinstance(raw_args, dict):
            return name, dict(raw_args)
        try:
            args = json.loads(str(raw_args))
        except json.JSONDecodeError:
            args = {}
        return name, args

    def tool_call_id(self, tool_call: dict[str, Any]) -> str:
        return str(tool_call.get("id") or tool_call.get("name") or tool_call.get("function", {}).get("name") or "tool")

    def tool_call_to_dict(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        name, args = self.tool_name_and_args(tool_call)
        return {"id": self.tool_call_id(tool_call), "name": name, "arguments": args}

    def is_pending_confirmation(self, result: ToolCallResult) -> bool:
        return isinstance(result.result, dict) and bool(result.result.get("pending_confirmation"))

    def repair_tool_call_with_followup(
        self,
        tool_call: dict[str, Any],
        followup_resolution: dict[str, Any] | None,
    ) -> dict[str, Any]:
        resolution = followup_resolution or {}
        if resolution.get("type") != "platform_search_followup":
            return tool_call
        tool_name, args = self.tool_name_and_args(tool_call)
        if tool_name not in {"search_platform_sources", "search_platform_sources_enhanced"}:
            return tool_call
        repaired = dict(args)
        repaired.setdefault("platform", resolution.get("platform") or "")
        repaired.setdefault("keyword", resolution.get("keyword") or "")
        if repaired == args:
            return tool_call
        next_call = dict(tool_call)
        if "function" in next_call:
            function = dict(next_call.get("function") or {})
            function["arguments"] = json.dumps(repaired, ensure_ascii=False)
            next_call["function"] = function
        else:
            next_call["arguments"] = json.dumps(repaired, ensure_ascii=False)
        return next_call

    def tool_call_from_followup_resolution(
        self,
        followup_resolution: dict[str, Any] | None,
        profile: dict[str, Any],
    ) -> dict[str, Any] | None:
        resolution = followup_resolution or {}
        if resolution.get("type") != "platform_search_followup":
            return None
        tool_name = "search_platform_sources"
        allowed_tools = profile.get("allowed_tools") or []
        if allowed_tools and "*" not in allowed_tools and tool_name not in allowed_tools:
            return None
        if not ToolRegistry.get_tool(tool_name):
            return None
        args = {
            "platform": resolution.get("platform") or "",
            "keyword": resolution.get("keyword") or "",
            "max_results": 20,
        }
        if not args["platform"] or not args["keyword"]:
            return None
        return {
            "id": f"followup_{uuid.uuid4().hex[:8]}",
            "name": tool_name,
            "arguments": json.dumps(args, ensure_ascii=False),
        }

    async def execute_tool_call(
        self,
        tool_call: dict[str, Any],
        profile: dict[str, Any],
        log_callback: ToolLogCallback | None = None,
    ) -> ToolCallResult:
        tool_name, tool_args = self.tool_name_and_args(tool_call)
        allowed_tools = profile.get("allowed_tools") or []
        if allowed_tools and "*" not in allowed_tools and tool_name not in allowed_tools:
            result = ToolCallResult(
                tool_name=tool_name,
                success=False,
                error=f"当前智能体无权调用工具：{tool_name}",
            )
            if log_callback:
                await log_callback(tool_name, tool_args, result)
            return result

        tool = ToolRegistry.get_tool(tool_name)
        risk_level = tool.risk_level if tool else "read"
        confirmed = bool(tool_args.pop("__confirmed", False) or tool_args.pop("confirmed", False))
        requires_confirmation = risk_level in CONFIRMATION_RISK_LEVELS and tool_name not in AUTO_CONFIRMED_WRITE_TOOLS
        if requires_confirmation and not confirmed:
            result = ToolCallResult(
                tool_name=tool_name,
                success=False,
                result={
                    "pending_confirmation": True,
                    "risk_level": risk_level,
                    "tool_name": tool_name,
                    "arguments": tool_args,
                    "message": f"工具 {tool_name} 风险等级为 {risk_level}，需要用户确认后执行。",
                },
                error="工具需要用户确认后执行",
            )
            if log_callback:
                await log_callback(tool_name, tool_args, result)
            return result

        result = await ToolRegistry.execute_tool(tool_name, tool_args)
        if isinstance(result.result, dict):
            result.result.setdefault("arguments", dict(tool_args))
        if result.success and isinstance(result.result, dict) and result.result.get("success") is False:
            result.success = False
            result.error = str(result.result.get("error") or result.result.get("message") or "tool returned success=false")
        if log_callback:
            await log_callback(tool_name, tool_args, result)
        return result
