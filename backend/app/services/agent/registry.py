"""
YLCraft — 工具注册表

实现动态工具注册、发现、Schema 生成。
参考 OpenClaw 和 Hermes Agent 的工具机制。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger("ylcraft.agent.registry")


@dataclass
class Tool:
    """工具定义"""
    name: str                           # 工具唯一标识
    description: str                    # 工具描述（供 LLM 理解何时调用）
    parameters: dict                    # JSON Schema 参数定义
    handler: Callable                   # 工具执行函数
    category: str = "general"           # 分类：asset/clip/subtitle/bgm/...
    examples: list[str] = field(default_factory=list)  # 使用示例
    requires_progress: bool = False     # 是否需要进度回调


@dataclass
class ToolCallResult:
    """工具执行结果"""

    tool_name: str
    success: bool
    result: object = None
    error: str | None = None
    duration_ms: int = 0


class ToolRegistry:
    """工具注册表（单例模式）"""

    _tools: dict[str, Tool] = {}
    _categories: dict[str, list[str]] = {}

    @classmethod
    def register(cls, tool: Tool):
        """注册一个工具"""
        if tool.name in cls._tools:
            logger.warning(f"[ToolRegistry] Tool '{tool.name}' already registered, overwriting")
        cls._tools[tool.name] = tool
        cls._categories.setdefault(tool.category, []).append(tool.name)
        logger.info(f"[ToolRegistry] Registered: {tool.name} ({tool.category})")

    @classmethod
    def get_tool(cls, name: str) -> Optional[Tool]:
        """根据名称获取工具"""
        return cls._tools.get(name)

    @classmethod
    def get_tools_by_category(cls, category: str) -> list[Tool]:
        """根据分类获取工具列表"""
        names = cls._categories.get(category, [])
        return [cls._tools[n] for n in names]

    @classmethod
    def get_all_tools(cls) -> list[Tool]:
        """获取所有工具"""
        return list(cls._tools.values())

    @classmethod
    def get_tool_schemas(cls) -> list[dict]:
        """生成 LLM 可见的工具 Schema（OpenAI function calling 格式）"""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
            }
            for tool in cls._tools.values()
        ]

    @classmethod
    def get_categories(cls) -> dict[str, list[str]]:
        """获取所有分类及其工具"""
        return cls._categories.copy()

    @classmethod
    async def execute_tool(cls, name: str, arguments: dict | None = None) -> ToolCallResult:
        """执行已注册工具并返回统一结果"""
        started = time.perf_counter()
        tool = cls.get_tool(name)
        if not tool:
            return ToolCallResult(
                tool_name=name,
                success=False,
                error=f"工具不存在: {name}",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

        try:
            result = tool.handler(**(arguments or {}))
            if hasattr(result, "__await__"):
                result = await result
            return ToolCallResult(
                tool_name=name,
                success=True,
                result=result,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:
            logger.exception("[ToolRegistry] tool execution failed: %s", name)
            return ToolCallResult(
                tool_name=name,
                success=False,
                error=str(exc),
                duration_ms=int((time.perf_counter() - started) * 1000),
            )


def register_tool(
    name: str,
    description: str,
    category: str = "general",
    examples: list[str] = None,
    requires_progress: bool = False,
):
    """
    工具注册装饰器

    使用示例：
    ```python
    @register_tool(
        name="search_assets",
        description="搜索素材库中的视频、图片、音频等资产",
        category="asset",
        examples=["搜索搞笑猫咪视频", "找找有没有美食素材"],
    )
    async def search_assets(query: str, asset_type: str = None, limit: int = 10):
        ...
    ```
    """
    def decorator(func):
        import inspect

        # 自动推断参数 Schema
        sig = inspect.signature(func)
        parameters = {
            "type": "object",
            "properties": {},
            "required": [],
        }

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            param_type = param.annotation
            param_info = {
                "type": "string",  # 默认类型
                "description": f"{param_name} parameter",
            }

            # 尝试从类型注解推断 JSON Schema 类型
            if param_type != inspect.Parameter.empty:
                if param_type == str:
                    param_info["type"] = "string"
                elif param_type == int:
                    param_info["type"] = "integer"
                elif param_type == float:
                    param_info["type"] = "number"
                elif param_type == bool:
                    param_info["type"] = "boolean"
                elif hasattr(param_type, "__origin__") and param_type.__origin__ == list:
                    param_info["type"] = "array"

            # 检查是否有默认值
            if param.default != inspect.Parameter.empty:
                param_info["default"] = param.default
            else:
                parameters["required"].append(param_name)

            parameters["properties"][param_name] = param_info

        tool = Tool(
            name=name,
            description=description,
            parameters=parameters,
            handler=func,
            category=category,
            examples=examples or [],
            requires_progress=requires_progress,
        )
        ToolRegistry.register(tool)
        return func
    return decorator
