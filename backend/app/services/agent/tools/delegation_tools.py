"""Internal Supervisor tools.

The public registry owns the model-facing schema. Execution is injected by
AgentService because delegation needs the current user, parent run and DB
session; calling this module-level handler directly would lose that scope.
"""

from __future__ import annotations

from typing import Any

from app.services.agent.registry import Tool, ToolRegistry


DELEGATE_AGENT_TASKS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "minItems": 1,
            "maxItems": 6,
            "description": "可并行或按依赖执行的子任务。没有依赖的任务会并行运行。",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "task_key": {
                        "type": "string",
                        "description": "本次委派内唯一且稳定的任务键，例如 research 或 review。",
                    },
                    "profile_id": {
                        "type": "string",
                        "description": "负责执行的 Agent Profile ID。",
                    },
                    "objective": {
                        "type": "string",
                        "description": "边界清晰、可独立验收的子任务目标。",
                    },
                    "context": {
                        "type": "object",
                        "description": "只传子任务额外需要的结构化上下文。项目上下文会由运行时投影。",
                    },
                    "depends_on": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "必须先完成的同批 task_key；留空表示可并行。",
                    },
                },
                "required": ["task_key", "profile_id", "objective"],
            },
        },
        "join_strategy": {
            "type": "string",
            "enum": ["all", "best_effort"],
            "default": "all",
            "description": "all 要求全部成功；best_effort 允许部分结果进入父 Agent。",
        },
    },
    "required": ["tasks"],
    "additionalProperties": False,
}


async def delegate_agent_tasks(
    tasks: list[dict[str, Any]],
    join_strategy: str = "all",
) -> dict[str, Any]:
    raise RuntimeError("delegate_agent_tasks 只能在 Agent Supervisor 运行上下文中执行")


ToolRegistry.register(
    Tool(
        name="delegate_agent_tasks",
        description=(
            "把复杂目标拆成多个专业子 Agent 任务。独立任务会并行执行，有 depends_on 的任务按拓扑顺序执行；"
            "所有子结果汇合后会作为观察返回，你必须继续推理并给用户最终答复。"
        ),
        description_short="并行或按依赖委派专业子 Agent，并汇合结果后继续父任务。",
        parameters=DELEGATE_AGENT_TASKS_SCHEMA,
        handler=delegate_agent_tasks,
        category="agent_runtime",
        examples=[
            "让小说作者续写，同时让质量审校检查上一章，再汇总决定修改方案",
            "让角色设计师和分镜导演并行检查项目缺口",
        ],
        input_schema_note="tasks 最多 6 个；task_key 唯一；depends_on 只能引用本次任务键。",
        output_schema_note="返回 joined_observation、delegations、linked_runs、summary；父 Agent 会继续观察该结果。",
        risk_level="read",
        output_type="agent_delegation_join",
    )
)


__all__ = ["DELEGATE_AGENT_TASKS_SCHEMA", "delegate_agent_tasks"]
