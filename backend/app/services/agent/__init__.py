"""
YLCraft — Agent 模块统一导出
"""

# 触发所有 @register_tool 装饰器（关键！）
from app.services.agent.tools.asset_tools import *
from app.services.agent.tools.clip_tools import *
from app.services.agent.tools.subtitle_tools import *
from app.services.agent.tools.bgm_tools import *
from app.services.agent.tools.breaker_tools import *

from app.services.agent.registry import ToolRegistry, register_tool, Tool, ToolCallResult
from app.services.agent.service import AgentService, AGENT_SYSTEM_PROMPT
from app.services.agent.session.manager import SessionManager
from app.services.agent.memory.manager import MemoryManager

__all__ = [
    "ToolRegistry",
    "register_tool",
    "Tool",
    "ToolCallResult",
    "AgentService",
    "AGENT_SYSTEM_PROMPT",
    "AgentSessionManager",
    "AgentMemoryManager",
]
