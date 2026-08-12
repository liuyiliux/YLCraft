"""
YLCraft — 工具注册表

实现动态工具注册、发现、Schema 生成。
参考 OpenClaw 和 Hermes Agent 的工具机制。
"""

from __future__ import annotations

import logging
import time
import inspect
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger("ylcraft.agent.registry")


@dataclass
class Tool:
    """工具定义（Hermes-inspired: 支持渐进式披露）"""
    name: str                           # 工具唯一标识
    description: str                    # 工具描述（供 LLM 理解何时调用）
    parameters: dict                    # JSON Schema 参数定义
    handler: Callable                   # 工具执行函数
    category: str = "general"           # 分类：asset/clip/subtitle/bgm/...
    examples: list[str] = field(default_factory=list)  # 使用示例
    requires_progress: bool = False     # 是否需要进度回调
    input_schema_note: str = ""
    output_schema_note: str = ""
    risk_level: str = "read"
    output_type: str = "generic"
    cost_hint: str = ""
    description_short: str = ""         # Hermes: 1-line summary for progressive disclosure


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
    def list_tools(cls, category: str | None = None) -> list[Tool]:
        """List registered tools, optionally filtered by category."""
        if category:
            return cls.get_tools_by_category(category)
        return cls.get_all_tools()

    @classmethod
    def get_tool_schemas(cls) -> list[dict]:
        """生成 LLM 可见的工具 Schema（OpenAI function calling 格式）"""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": cls._tool_description(tool),
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
    def get_openai_tools_spec(
        cls,
        allowed_tools: list[str] | None = None,
        summary_mode: bool = False,
        excluded_tools: set[str] | None = None,
    ) -> list[dict]:
        """Return OpenAI-compatible tool specs with an optional allowlist.

        Hermes-inspired progressive disclosure: when summary_mode=True,
        use description_short if available instead of full description.
        This reduces token overhead when many tools are available.
        """
        allow_all = not allowed_tools or "*" in allowed_tools
        allowed = set(allowed_tools or [])
        excluded = excluded_tools or set()
        tools = (
            [tool for name, tool in cls._tools.items() if name not in excluded]
            if allow_all
            else [tool for name, tool in cls._tools.items() if name in allowed and name not in excluded]
        )
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": (
                        tool.description_short
                        if (summary_mode and tool.description_short)
                        else cls._tool_description(tool)
                    ),
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    @classmethod
    def _tool_description(cls, tool: Tool) -> str:
        parts = [tool.description]
        if tool.input_schema_note:
            parts.append(f"输入规范：{tool.input_schema_note}")
        if tool.output_schema_note:
            parts.append(f"输出规范：{tool.output_schema_note}")
        parts.append(f"风险等级：{tool.risk_level}；输出类型：{tool.output_type}")
        if tool.cost_hint:
            parts.append(f"成本提示：{tool.cost_hint}")
        return "\n".join(part for part in parts if part)

    @classmethod
    def _validate_arguments(cls, tool: Tool, arguments: dict | None) -> str | None:
        args = arguments or {}
        if not isinstance(args, dict):
            return f"工具参数必须是 JSON 对象，当前收到 {type(args).__name__}"

        schema = tool.parameters or {}
        required = [item for item in schema.get("required", []) if item]
        missing = [item for item in required if item not in args or args.get(item) in (None, "")]
        if missing:
            hint = f"；输入规范：{tool.input_schema_note}" if tool.input_schema_note else ""
            return f"缺少必填参数：{', '.join(missing)}{hint}"

        properties = schema.get("properties") or {}
        signature = inspect.signature(tool.handler)
        accepts_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values())
        if properties and not accepts_kwargs:
            unexpected = [key for key in args if key not in properties]
            if unexpected:
                return f"存在未定义参数：{', '.join(unexpected)}；可用参数：{', '.join(properties.keys()) or '无'}"

        try:
            signature.bind(**args)
        except TypeError as exc:
            return f"工具参数无法匹配函数签名：{exc}"
        return None

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

        validation_error = cls._validate_arguments(tool, arguments)
        if validation_error:
            return ToolCallResult(
                tool_name=name,
                success=False,
                error=validation_error,
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
    input_schema_note: str = "",
    output_schema_note: str = "",
    risk_level: str = "read",
    output_type: str = "generic",
    cost_hint: str = "",
    description_short: str = "",
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
            param_info = _annotation_to_json_schema(param_type, param_name)

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
            input_schema_note=input_schema_note,
            output_schema_note=output_schema_note,
            risk_level=risk_level,
            output_type=output_type,
            cost_hint=cost_hint,
            description_short=description_short,
        )
        ToolRegistry.register(tool)
        return func
    return decorator


def _unwrap_optional(annotation):
    """Unwrap Optional[T] -> T, Union[T, None] -> T."""
    import types

    origin = getattr(annotation, "__origin__", None)
    if origin is types.UnionType:
        # Python 3.10+ union: str | None, bool | None
        args = getattr(annotation, "__args__", ())
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return annotation


def _annotation_to_json_schema(annotation, param_name: str = "param") -> dict:
    """Convert a Python type annotation to JSON Schema properties dict."""
    if annotation == inspect.Parameter.empty:
        return {"type": "string", "description": f"{param_name} parameter"}

    # Unwrap Optional / Union[None, T]
    from typing import get_origin as _get_origin
    origin = _get_origin(annotation)

    if origin is not None:
        args = getattr(annotation, "__args__", ())

        if origin == list or origin is list:
            schema: dict = {"type": "array", "description": f"{param_name} parameter"}
            if args:
                elem_type = _annotation_to_json_schema(_unwrap_optional(args[0]), f"{param_name} element")
                schema["items"] = {"type": elem_type.get("type", "string")}
            else:
                schema["items"] = {"type": "string"}
            return schema

        if origin == dict or origin is dict:
            return {"type": "object", "description": f"{param_name} (free-form JSON object)"}

    # Handle Python 3.10+ union types (e.g., bool | None, str | None)
    import types
    if getattr(annotation, "__origin__", None) is types.UnionType:
        args = getattr(annotation, "__args__", ())
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _annotation_to_json_schema(non_none[0], param_name)

    # Simple types
    if annotation == str:
        return {"type": "string", "description": f"{param_name} parameter"}
    elif annotation == int:
        return {"type": "integer", "description": f"{param_name} parameter"}
    elif annotation == float:
        return {"type": "number", "description": f"{param_name} parameter"}
    elif annotation == bool:
        return {"type": "boolean", "description": f"{param_name} parameter"}

    return {"type": "string", "description": f"{param_name} parameter"}
