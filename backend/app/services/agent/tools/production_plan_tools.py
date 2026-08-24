"""Runtime-bound tool for executing a selected creative production-plan slice."""

from __future__ import annotations

from typing import Any

from app.services.agent.registry import Tool, ToolRegistry


RUN_CREATIVE_PRODUCTION_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "project_id": {"type": "string", "description": "当前创作项目 ID。"},
        "node_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 6,
            "items": {"type": "string"},
            "description": "本次要推进的计划节点 ID；运行时会自动包含其尚在计划内的依赖节点。",
        },
        "include_dependencies": {
            "type": "boolean",
            "default": True,
            "description": "默认补齐上游依赖。仅在已确认上游产物可复用时设为 false，用于局部重跑。",
        },
    },
    "required": ["project_id", "node_ids"],
    "additionalProperties": False,
}


async def run_creative_production_plan(project_id: str, node_ids: list[str]) -> dict[str, Any]:
    raise RuntimeError("run_creative_production_plan 只能在创作导演运行上下文中执行")


ANALYZE_CREATIVE_PRODUCTION_PLAN_IMPACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "project_id": {"type": "string", "description": "当前创作项目 ID。"},
        "changed_node_ids": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string"},
            "description": "已修改、替换输入或需要重新生成的计划节点 ID。",
        },
    },
    "required": ["project_id", "changed_node_ids"],
    "additionalProperties": False,
}

UPDATE_CREATIVE_PRODUCTION_PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "project_id": {"type": "string", "description": "当前创作项目 ID。"},
        "node_id": {"type": "string", "description": "要局部修改的生产计划节点 ID。"},
        "changes": {
            "type": "object",
            "description": "仅允许修改可审计的节点字段。",
            "properties": {
                "label": {"type": "string"},
                "planning_summary": {"type": "object"},
                "provider": {"type": "string"},
                "model": {"type": "string"},
                "requires_confirmation": {"type": "boolean"},
                "rerun_scope": {"type": "string"},
            },
            "additionalProperties": False,
            "minProperties": 1,
        },
        "reason": {"type": "string", "minLength": 1, "description": "用户可见的修改原因。"},
    },
    "required": ["project_id", "node_id", "changes", "reason"],
    "additionalProperties": False,
}


async def analyze_creative_production_plan_impact(project_id: str, changed_node_ids: list[str]) -> dict[str, Any]:
    raise RuntimeError("analyze_creative_production_plan_impact 只能在创作导演运行上下文中执行")


async def update_creative_production_plan(
    project_id: str,
    node_id: str,
    changes: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    raise RuntimeError("update_creative_production_plan 只能在创作导演运行上下文中执行")


ToolRegistry.register(
    Tool(
        name="run_creative_production_plan",
        description=(
            "根据已保存的创作项目生产计划，选择至多六个节点并复用现有 TeamComposer 创建独立专家 Run。"
            "会自动带上所选节点依赖，所有结果汇合为导演 Run 的观察；它本身不绕过生成、下载或发布确认。"
        ),
        description_short="执行生产计划中的一组依赖节点，并将专家结果汇合给导演。",
        parameters=RUN_CREATIVE_PRODUCTION_PLAN_SCHEMA,
        handler=run_creative_production_plan,
        category="creative_project",
        examples=["推进本项目的故事节拍和视觉规划节点", "执行第三页分镜节点及其依赖"],
        input_schema_note="project_id 必须与当前导演上下文一致；node_ids 最多 6 个并自动包含依赖。",
        output_schema_note="返回 TeamComposer 的 joined_observation、delegations、linked_runs 和节点/Skill 选择信息。",
        risk_level="read",
        output_type="creative_production_plan_run",
    )
)

ToolRegistry.register(
    Tool(
        name="update_creative_production_plan",
        description=(
            "按用户明确要求局部修改已保存的创作生产计划，只允许更新节点标签、视觉规划摘要、供应商/模型、确认点和重跑范围；"
            "保存为新版本并返回受影响的下游节点，不会直接触发生成。"
        ),
        description_short="局部修改生产计划并计算下游影响。",
        parameters=UPDATE_CREATIVE_PRODUCTION_PLAN_SCHEMA,
        handler=update_creative_production_plan,
        category="creative_project",
        examples=["只改第三格构图", "保留角色脸型，只换成童话风"],
        input_schema_note="project_id 必须与当前导演上下文一致；实际生成仍需单独确认。",
        output_schema_note="返回新计划版本、修改节点、受影响下游节点和局部重跑提示。",
        risk_level="write",
        output_type="creative_production_plan_updated",
    )
)

ToolRegistry.register(
    Tool(
        name="analyze_creative_production_plan_impact",
        description="分析生产计划中某些节点变化的下游影响范围，为只重跑受影响节点提供可审计依据。",
        description_short="计算计划节点变更的下游重跑范围。",
        parameters=ANALYZE_CREATIVE_PRODUCTION_PLAN_IMPACT_SCHEMA,
        handler=analyze_creative_production_plan_impact,
        category="creative_project",
        examples=["第三格构图改了，哪些节点需要重跑", "角色参考图替换后分析影响范围"],
        input_schema_note="project_id 必须与当前导演上下文一致；changed_node_ids 是直接变更节点。",
        output_schema_note="返回按计划顺序排列的 affected_nodes、当前计划内容版本和局部重跑提示。",
        risk_level="read",
        output_type="creative_production_plan_impact",
    )
)


__all__ = [
    "ANALYZE_CREATIVE_PRODUCTION_PLAN_IMPACT_SCHEMA",
    "RUN_CREATIVE_PRODUCTION_PLAN_SCHEMA",
    "UPDATE_CREATIVE_PRODUCTION_PLAN_SCHEMA",
    "analyze_creative_production_plan_impact",
    "run_creative_production_plan",
    "update_creative_production_plan",
]
