"""工具参数 Schema 的类型还原：`from __future__ import annotations` 下的回归。

背景：本项目 30+ 个工具模块都带 `from __future__ import annotations`，于是
`inspect.signature(func).parameters[...].annotation` 是**字符串**而不是类型对象。
旧的 Schema 生成遇到字符串会走兜底分支，把 `list[dict[str, Any]]` 这类注解
一律写成 `{"type": "string"}`。

后果不是"缺个提示"——模型是照着 schema 生成参数的：它看到 `operations` 是 string，
就把操作数组**序列化成 JSON 字符串**传进来；字符串可迭代，下游 `for op in operations`
逐字符遍历，于是报出等于 JSON 文本长度的"未知操作类型：(空)"（实测 129/163/171 条）。
模型怎么改内容都没用，因为它错在遵循了错的 schema。

这组测试钉住两件事：
  1. 带字符串注解的工具，Schema 必须是 `array` / `integer` 等真实类型；
  2. 即便模型仍然传字符串，执行层也要还原成 list（双保险）。
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.services.agent.registry import Tool, ToolRegistry, register_tool


@pytest.fixture(autouse=True)
def _cleanup_probe_tools():
    """本文件注册的都是探针工具，退出时移除。

    不清理会污染 `test_agent_center` 的"所有已注册工具都要有 IO 规范"断言
    （探针工具没写 input_schema_note/output_type）。
    """
    yield
    for name in ("probe_array_schema", "probe_array_coerce", "probe_array_bad"):
        ToolRegistry._tools.pop(name, None)


def test_list_annotation_is_declared_as_array_not_string():
    """字符串注解（future annotations）不能让 list 参数退化成 string。"""

    @register_tool(name="probe_array_schema", description="probe", category="general")
    async def probe_array_schema(items: list[dict[str, Any]], count: int):
        return {"success": True}

    tool = ToolRegistry.get_tool("probe_array_schema")
    assert tool is not None
    properties = tool.parameters["properties"]
    assert properties["items"]["type"] == "array", properties["items"]
    assert properties["count"]["type"] == "integer", properties["count"]


def test_previs_operations_schema_is_array():
    """实际出问题的工具：`operations` 必须声明为 array，否则模型会传 JSON 字符串。"""
    import app.services.agent.tools.previs_tools  # noqa: F401  确保工具已注册

    tool = ToolRegistry.get_tool("previs_preview_operations")
    assert tool is not None
    properties = tool.parameters["properties"]
    assert properties["operations"]["type"] == "array", properties["operations"]
    assert properties["expected_revision"]["type"] == "integer", properties["expected_revision"]


def test_string_array_argument_is_parsed_not_iterated_per_character():
    """双保险：即便模型仍传 JSON 字符串，也必须还原成 list 而不是逐字符遍历。"""
    seen = {}

    def handler(operations: list):
        seen["operations"] = operations
        return {"success": True, "count": len(operations)}

    ToolRegistry.register(Tool(
        name="probe_array_coerce",
        description="probe",
        parameters={"type": "object", "properties": {"operations": {"type": "array", "items": {"type": "object"}}}, "required": ["operations"]},
        handler=handler,
    ))
    raw = '[{"type": "update_transform", "targetId": "node-table"}]'
    result = asyncio.run(ToolRegistry.execute_tool("probe_array_coerce", {"operations": raw}))
    assert result.success, result.error
    assert result.result["count"] == 1
    assert seen["operations"][0]["targetId"] == "node-table"


def test_unparsable_array_string_still_is_a_readable_list():
    """解析不出来时原样传入，不静默吞掉也不崩。"""

    def handler(operations):
        return {"success": True, "count": len(operations)}

    ToolRegistry.register(Tool(
        name="probe_array_bad",
        description="probe",
        parameters={"type": "object", "properties": {"operations": {"type": "array"}}, "required": ["operations"]},
        handler=handler,
    ))
    result = asyncio.run(ToolRegistry.execute_tool("probe_array_bad", {"operations": "not json"}))
    assert result.success
    assert result.result["count"] == len("not json")
