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
from app.services.previs.draft_service import compose_previs_draft
from app.services.previs.motion_service import list_motions, motion_carriers, motion_to_dict
from app.services.previs.operations import (
    HUMAN_PROXY_HEIGHT,
    HUMAN_PROXY_POSES,
    LIGHT_KINDS,
    NODE_KINDS,
    PREVIS_OPERATION_TYPES,
    PRIMITIVE_KINDS,
    apply_operations,
    diff_operations,
    validate_operations,
)

logger = logging.getLogger("ylcraft.agent.tools.previs")

#: 落库后的操作历史上限，与前端 types.ts 的 MAX_SCENE_OPERATIONS 一致
MAX_SCENE_OPERATIONS = 200

#: 工具说明里的操作契约 = AI 唯一的文档来源，因此**每种 type 的 payload 形状都要写清楚**。
#: 只列 type 名是不够的：AI 只能靠猜 payload，而猜错的表现是被拒或落库成坏数据。
_OPERATION_CONTRACT = (
    "operations 是对象数组，每项形如 {type, targetId?, payload, expectedRevision}。"
    "type 只能是 " + "/".join(PREVIS_OPERATION_TYPES) + "；各 type 的 payload："
    "add_node={node:{kind,name,transform,metadata?,assetId?}}，kind 只能是 " + "/".join(NODE_KINDS) + "，"
    "人形占位的 metadata 可带 height(0.5–2.5 米)/pose(" + "/".join(HUMAN_PROXY_POSES) + ")"
    "/poseJoints(通道→角度)/animationClip('motion:<动作标识>')；"
    "update_transform={position|rotation|scale}；set_camera={position|target|fov}；"
    "add_keyframe={property,frame,value}；remove_keyframe={property,frame}；"
    "set_human_proxy={height?|pose?|poseJoints?}（只作用于人形占位节点，改身高/姿势用这个，"
    "不要直接写 metadata）；assign_motion={motion:'motion:<动作标识>'}（用空串清除动作，"
    "只作用于人形占位节点）"
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
        # 动作清单与场景在同一次会话里读：校验要拿它判断"动作是否存在、载体是否匹配人形占位"
        carriers = motion_carriers(session)

    accepted, rejected = validate_operations(
        scene,
        operations,
        expected_revision=expected_revision,
        current_revision=current_revision,
        motion_carriers=carriers,
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
        carriers = motion_carriers(session)

        # 落库前重新校验：预览与落库之间场景可能已被人工改动
        accepted, rejected = validate_operations(
            scene,
            operations,
            expected_revision=expected_revision,
            current_revision=current_revision,
            motion_carriers=carriers,
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


#: 载体说明：**哪种对象吃哪种动作**。写进工具输出是为了省一轮往返——
#: 拿 `params` 动作去驱动非人形对象会在落库校验时被拒，但那已经是白跑一趟。
_CARRIER_GUIDE = {
    "params": "人形参数型：驱动程序化人形占位（human_proxy），通道是 23 个关节角度（含躯干 / 头颈 / 重心）",
    "transform": (
        "通用变换型：位置 / 旋转 / 缩放曲线。**本期前端没有求值路径，实际用不了**"
        "（见 tasks 7.3 的记录）——要给非人形对象做运动，请用手打关键帧（`add_keyframe`）。"
        "**不要**把一个变换型动作指派给对象：那会得到一个「看着设了、画面不动」的节点"
    ),
    "bone": "骨骼型：留给带动画骨骼的模型（本期未启用，库里通常为空）",
}


@register_tool(
    name="list_previs_motions",
    description=(
        "列出 3D 预演台可用的动作资产（只读）：标识、中文名、分类、标签、载体、兼容规格、时长、帧数、"
        "是否循环、来源与许可。**给角色或对象指定动作前先查标识**——凭印象编出来的标识会在落库校验时被拒。"
    ),
    category="creative_project",
    examples=[
        "预演台里有哪些人形动作可以用",
        "找找有没有鞠躬或点头类的动作",
        "列出通用变换型动作（给非人形对象用的）",
    ],
    input_schema_note=(
        "carrier 可选：params（人形参数型，供 human_proxy）/ transform（通用变换型，供非人形对象）；"
        "category 与 tag 为可选筛选。都不传则返回全部启用中的动作。"
    ),
    output_schema_note=(
        "返回 motions[]（slug 标识、name 中文名、carrier、skeleton、duration_seconds、frame_count、"
        "loopable、channels、origin / license / license_status）与 total，另带 carrier_guide。"
        "**没有匹配时返回空数组**，不要据此编造标识。"
    ),
    risk_level="read",
    output_type="creative_previs_motions",
)
async def list_previs_motions(
    carrier: str = "",
    category: str = "",
    tag: str = "",
) -> dict[str, Any]:
    """只读动作清单，与预演台的动作选择器同源（`motion_service.list_motions`）。"""
    with SessionLocal() as session:
        rows = list_motions(
            session,
            carrier=carrier or None,
            category=category or None,
            tag=tag or None,
        )
        motions = [motion_to_dict(row) for row in rows]
    return {
        "success": True,
        "motions": motions,
        "total": len(motions),
        "carrier_guide": _CARRIER_GUIDE,
        "empty_hint": "" if motions else (
            "没有匹配的动作：放宽筛选条件，或先补齐动作资产"
            "（python -m app.scripts.seed_previs_motions）"
        ),
    }


@register_tool(
    name="get_previs_composition_options",
    description=(
        "列出 3D 预演台**能摆什么**（只读）：节点种类、可摆姿势、身高范围、尺寸锚点、素材库里可用的模型。"
        "提摆放方案前先看它，避免提出预演台不支持的对象种类，或一个尺寸上不可能的东西。"
    ),
    category="creative_project",
    examples=[
        "预演台里能摆哪些类型的对象",
        "摆两个人形占位能选什么姿势",
        "素材库里有哪些模型可以放进预演场景",
    ],
    input_schema_note="limit 控制素材库模型最多返回几条（默认 20，上限 50）。",
    output_schema_note=(
        "返回 node_kinds（节点种类与用途）、primitive_kinds / light_kinds、human_proxy（姿势清单、"
        "身高范围与\"姿势是静态的\"说明）、size_anchors_m（预演参照尺寸）、library_models"
        "（素材库里扩展名可加载的模型：asset_id / name / model_url）。"
        "**素材库没有匹配时 library_models 为空数组**，不要编 asset_id。"
        "尺寸口径：素材库模型以**自带包围盒**为准，不要手写尺寸。"
    ),
    risk_level="read",
    output_type="creative_previs_options",
)
async def get_previs_composition_options(limit: int = 20) -> dict[str, Any]:
    """只读的可摆对象与素材清单，支撑\"先查后摆\"。"""
    from app.services.agent.tools.asset_tools import search_assets
    from app.services.previs.draft import SIZE_ANCHORS
    from app.services.previs.draft_service import PROP_MODEL_EXTS

    size = max(1, min(int(limit or 20), 50))
    models: list[dict[str, Any]] = []
    try:
        result = await search_assets(query="", limit=size)
        for asset in result.get("assets") or []:
            path = str(asset.get("file_path") or "")
            if path.lower().endswith(PROP_MODEL_EXTS):
                models.append({
                    "asset_id": str(asset.get("id") or ""),
                    "name": str(asset.get("title") or ""),
                    "model_url": path,
                })
    except Exception as exc:  # noqa: BLE001 —— 素材库不可用不该让"能摆什么"整体失败
        logger.warning("预演可摆对象：素材库检索失败：%s", exc)

    return {
        "success": True,
        "node_kinds": [
            {"kind": "human_proxy", "label": "人形占位",
             "note": "通用胶囊人，驱动参数型动作；表示人物一律用它，不要用造型化模型"},
            {"kind": "asset_model", "label": "素材库模型",
             "note": "需要 assetId；模型以自带包围盒为准，不要写尺寸"},
            {"kind": "primitive", "label": "几何体", "note": "/".join(PRIMITIVE_KINDS)},
            {"kind": "panorama", "label": "全景背景", "note": "当前只支持纯色（贴图未接入）"},
            {"kind": "light", "label": "灯光", "note": "/".join(LIGHT_KINDS)},
        ],
        "primitive_kinds": list(PRIMITIVE_KINDS),
        "light_kinds": list(LIGHT_KINDS),
        "human_proxy": {
            "poses": list(HUMAN_PROXY_POSES),
            "height_range_m": list(HUMAN_PROXY_HEIGHT),
            "note": "姿势是静态的；要\"会动\"请用 list_previs_motions 里的 params 动作（assign_motion）",
        },
        "size_anchors_m": SIZE_ANCHORS,
        "library_models": models,
        "library_models_note": (
            "只列素材库里扩展名为模型格式（glb/gltf/fbx/obj）的资产；"
            "素材库检索不可用时为空数组——此时不要假设某个模型存在"
        ),
    }


@register_tool(
    name="generate_previs_draft",
    description=(
        "按分镜格生成 3D 预演初稿（只读，返回草案**不落库**）：人物数量与站位、机位与镜头、场景时长、道具。"
        "产出是一批受限操作 + 默认值清单 + 未翻译提示，人工确认后才由 previs_apply_operations 落库。"
    ),
    category="creative_project",
    examples=[
        "按第 3 格分镜生成一版 3D 预演初稿",
        "这一格的调度和景别翻成预演场景会是什么样",
    ],
    input_schema_note=(
        "scene_id 为预演场景 ID（见 build_creative_project_context_pack 的 previs.scenes[].scene_id）。"
        "场景必须已绑定项目分镜格，否则无法生成初稿（会返回可读原因）。"
    ),
    output_schema_note=(
        "返回 operations（可直接交给 previs_preview_operations 预览）、defaults（哪些字段取了默认值及原因）、"
        "warnings（哪些分镜字段本版未翻译）、summary（景别 / 机位 / 时长 / 人物姿势摘要）与 scene_revision。"
        "**刻意不返回完整场景对象**：那是给预演台幽灵预览用的（HTTP 接口返回），"
        "而工具结果有长度上限，塞进来只会把有用信息挤掉。"
    ),
    risk_level="read",
    output_type="creative_previs_draft",
)
async def generate_previs_draft(scene_id: str) -> dict[str, Any]:
    """分镜格 → 初稿操作集（只读）。与 HTTP 接口共用 `compose_previs_draft` 同一条管线。"""
    result = await compose_previs_draft(scene_id)
    if not result.get("ok"):
        return {"success": False, "error": str(result.get("error") or "生成初稿失败")}
    operations = result.get("operations") or []
    return {
        "success": True,
        "read_only": True,
        "scene_id": scene_id,
        "panel_number": result.get("panel_number"),
        "scene_revision": result.get("scene_revision"),
        "operations": operations,
        "operation_count": len(operations),
        "defaults": result.get("defaults") or [],
        "warnings": result.get("warnings") or [],
        "rejected": result.get("rejected") or [],
        "summary": result.get("summary") or {},
    }
