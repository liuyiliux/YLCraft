"""Agent 侧的 3D 预演台受限操作工具（design §5.3 / #18）。

拆成两个工具，对应 design 的两步流程：

    previs_preview_operations  →  只读：校验 + 差异预览，不改任何东西
    previs_apply_operations    →  写入：再校验一次 → CAS 落库（需人工确认）

为什么预览与落库必须分开：design 要求"Agent 生成的操作先在预演台显示差异预览，
用户确认后才落库"。合成一个工具就等于让 Agent 自己决定"要不要落库"，确认环节会被跳过。

为什么落库前要**再校验一次**：预览通过不代表落库时仍然通过——两次之间场景可能已变。
校验是廉价的，而一次错误的覆盖会把人工调整冲掉。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import update

from app.db.database import SessionLocal
from app.db.models.previs import PrevisSceneDocument
from app.services.agent.registry import register_tool
from app.services.previs.operations import (
    PREVIS_OPERATION_TYPES,
    apply_operations,
    diff_operations,
    validate_operations,
)

logger = logging.getLogger("ylcraft.agent.tools.previs")

#: 落库后的操作历史上限，与前端 types.ts 的 MAX_SCENE_OPERATIONS 一致
MAX_SCENE_OPERATIONS = 200

_OPERATION_CONTRACT = (
    "operations 是对象数组，每项形如 "
    "{type, targetId?, payload, expectedRevision}；type 只能是 "
    + "/".join(PREVIS_OPERATION_TYPES)
)


def _load_scene(session, scene_id: str) -> PrevisSceneDocument | None:
    return session.get(PrevisSceneDocument, scene_id)


def _scene_dict(row: PrevisSceneDocument) -> dict[str, Any]:
    return dict(row.scene_json or {})


@register_tool(
    name="previs_preview_operations",
    description="校验一批 3D 预演台操作并给出差异预览（只读，不改任何东西）。用于在落库前把 Agent 提出的镜头改动呈现给人工确认。",
    category="creative_project",
    examples=[
        "预览把主演挪到画面左侧的改动",
        "看看给第 3 格加上推镜头关键帧会改哪些值",
        "校验这批预演操作有没有踩到锁定的对象",
    ],
    input_schema_note=(
        "scene_id 为预演场景 ID（见 build_creative_project_context_pack 的 previs.scenes[].scene_id）；"
        f"{_OPERATION_CONTRACT}。"
    ),
    output_schema_note=(
        "返回 current_revision、accepted_count、rejected（含逐条原因）与 diff（逐条改前/改后）。"
        "整批因 revision 过期被拒时 rejected 会覆盖所有条目。"
    ),
    risk_level="read",
    # 遵循 creative_project 分类的既有约定：output_type 以 creative_ 开头
    output_type="creative_previs_preview",
)
async def previs_preview_operations(
    scene_id: str,
    operations: list[dict[str, Any]],
    expected_revision: int,
) -> dict[str, Any]:
    """只读校验 + 差异预览，供预演台渲染"确认"对话框。"""
    with SessionLocal() as session:
        row = _load_scene(session, scene_id)
        if row is None:
            return {"success": False, "error": f"预演场景不存在：{scene_id}"}
        scene = _scene_dict(row)
        current_revision = int(row.revision or 1)

    accepted, rejected = validate_operations(
        scene, operations, expected_revision=expected_revision, current_revision=current_revision
    )
    return {
        "success": True,
        "scene_id": scene_id,
        "current_revision": current_revision,
        "expected_revision": int(expected_revision),
        "valid": not rejected,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "rejected": rejected,
        "diff": diff_operations(scene, accepted),
    }


@register_tool(
    name="previs_apply_operations",
    description=(
        "把人工已确认的 3D 预演台操作落库（带 revision 校验，写入需人工确认）。"
        "落库前会重新校验一次：预览通过不代表落库时仍然通过。"
    ),
    category="creative_project",
    examples=["确认执行刚才预览的那批机位改动", "把预览通过的关键帧改动落库"],
    input_schema_note=(
        "scene_id 为预演场景 ID。"
        f"{_OPERATION_CONTRACT}。"
        "expected_revision 必须等于场景当前 revision，否则整批拒绝——这是防止过期 Agent 覆盖人工编辑的关键。"
    ),
    output_schema_note=(
        "返回新的 revision、已应用条数与被拒条目（含原因）。"
        "返回值刻意保持精简：工具调用会被自动记录进 AgentToolCall，而它的 result 有 2000 字符上限，"
        "完整细节写进了随场景持久化的操作历史（可由预演台的「操作历史」查看）。"
    ),
    risk_level="write",
    output_type="creative_previs_result",
    cost_hint="会修改预演场景并递增 revision，执行前需要人工确认。",
)
async def previs_apply_operations(
    scene_id: str,
    operations: list[dict[str, Any]],
    expected_revision: int,
) -> dict[str, Any]:
    """校验 → 应用 → CAS 落库，并把摘要写进随场景持久化的操作历史。"""
    with SessionLocal() as session:
        row = _load_scene(session, scene_id)
        if row is None:
            return {"success": False, "error": f"预演场景不存在：{scene_id}"}
        scene = _scene_dict(row)
        current_revision = int(row.revision or 1)

        # 落库前重新校验：预览与落库之间场景可能已被人工改动
        accepted, rejected = validate_operations(
            scene, operations, expected_revision=expected_revision, current_revision=current_revision
        )
        if rejected:
            return {
                "success": False,
                "scene_id": scene_id,
                "current_revision": current_revision,
                "expected_revision": int(expected_revision),
                "applied_count": 0,
                "rejected": rejected,
                "message": "这批操作未通过校验，场景未做任何改动",
            }
        if not accepted:
            return {"success": True, "scene_id": scene_id, "applied_count": 0, "revision": current_revision,
                    "message": "没有可执行的操作"}

        next_scene, applied = apply_operations(scene, accepted)

        # 操作历史：随场景一起持久化（design 要求可撤销性不能只存在浏览器里）
        stamp = datetime.utcnow().isoformat()
        history = list(next_scene.get("operations") or [])
        for item in applied:
            history.append({
                "id": f"op_{uuid.uuid4().hex[:12]}",
                "at": stamp,
                "type": str(item.get("type") or ""),
                "targetId": str(item.get("target_id") or ""),
                "summary": str(item.get("summary") or ""),
            })
        next_scene["operations"] = history[-MAX_SCENE_OPERATIONS:]

        session.exec(
            update(PrevisSceneDocument)
            .where(PrevisSceneDocument.id == scene_id)
            .values(scene_json=next_scene, revision=current_revision + 1, updated_at=datetime.utcnow())
        )
        session.commit()

    return {
        "success": True,
        "scene_id": scene_id,
        "previous_revision": current_revision,
        "revision": current_revision + 1,
        "applied_count": len(applied),
        "applied": [
            {"type": str(item.get("type") or ""), "target_id": str(item.get("target_id") or ""),
             "summary": str(item.get("summary") or "")}
            for item in applied
        ],
        "trace": {
            "kind": "previs_operations",
            "scene_id": scene_id,
            "applied_count": len(applied),
            # 完整细节在场景的操作历史里；这里只放 ID 便于回溯
            "note": "完整记录见场景的 operations（预演台「操作历史」）",
        },
    }
