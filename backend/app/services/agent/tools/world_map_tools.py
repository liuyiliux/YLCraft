"""Agent tools for the structured world map workflow.

These mirror the human `/world-map` workbench exactly and share the same
service layer, so Agent and真人 never keep two copies of the rules:

- 正典是结构化 ``map_json``（区域/据点/路线/空间层），写入走 revision CAS；
- 成图与提示词润色是**派生**动作：成图只回写引用，不自动进底图、不叠标记；
- 提示词优化只改写文本，不落库、不生成图（消耗一次 LLM 文本配额）。

写作纪律：除 ``create/save/rollback`` 与两个 generate（成图 / 区域形状参数）外都是
read；写工具要求显式传入 expected_revision（区域形状生成内部读取当前版本做 CAS），
避免静默覆盖他人编辑。
"""

from __future__ import annotations

from typing import Any

from sqlmodel import select

from app.db.database import SessionLocal
from app.db.models.novel_source import WorldMapRevision
from app.services.agent.registry import register_tool
from app.services.creative_project.service import loads_json
from app.services.novel_source.world_map import (
    WorldMapService,
    build_map_export,
    build_map_visual_prompt,
    render_map_svg,
    serialize_map,
)
from app.services.novel_source.world_map_shape import (
    generate_region_shape_params,
    set_region_shape,
    shape_presets,
)
from app.services.novel_source.world_map_visual import (
    generate_map_visual,
    optimize_map_visual_prompt,
)

MAX_SVG_CHARS = 6000


def _map_summary(document: Any) -> dict[str, Any]:
    data = loads_json(document.map_json, {})
    return {
        "id": document.id,
        "title": document.title,
        "project_id": document.project_id,
        "snapshot_id": document.snapshot_id,
        "revision": document.revision,
        "regions": len(data.get("regions") or []),
        "nodes": len(data.get("nodes") or []),
        "routes": len(data.get("routes") or []),
        "layers": len(data.get("layers") or []),
        "visuals": len(data.get("visuals") or []),
    }


@register_tool(
    name="list_world_maps",
    description="列出世界地图文档（可按项目或来源快照过滤），返回标题、版本与各要素数量。",
    category="novel_source",
    examples=["这个项目有哪些世界地图", "列出我建过的地图"],
    input_schema_note="project_id 与 snapshot_id 可选，都不传则列全部；limit 最大 200。",
    output_schema_note="返回 total 与 maps（含 revision / regions / nodes / routes 计数）。",
    risk_level="read",
    output_type="world_map_list",
)
def list_world_maps(project_id: str = "", snapshot_id: str = "", limit: int = 50) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WorldMapService(session)
        maps = service.list_maps(
            project_id=project_id or None,
            snapshot_id=snapshot_id or None,
            limit=max(1, min(int(limit or 50), 200)),
        )
        return {"success": True, "total": len(maps), "maps": [_map_summary(item) for item in maps]}


@register_tool(
    name="get_world_map",
    description="读取单张世界地图的结构化内容（区域/据点/路线/空间层/派生成图引用）与版本号。",
    category="novel_source",
    examples=["打开这张世界地图看看内容", "这个地图有哪些据点和路线"],
    input_schema_note="必须提供 map_id；返回的 revision 是后续保存必填的 CAS 依据。",
    output_schema_note="返回 map（含 map_json 解析后的结构化数据）与 revision。",
    risk_level="read",
    output_type="world_map_detail",
)
def get_world_map(map_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WorldMapService(session)
        document = service.get_map(map_id)
        if not document:
            return {"success": False, "error": "地图文档不存在"}
        payload = serialize_map(document)
        payload["map_json"] = loads_json(document.map_json, {})
        return {"success": True, "map": payload, "revision": document.revision}


@register_tool(
    name="create_world_map",
    description="新建世界地图文档（可带初始 map_json，或从项目地点实体克隆）。",
    category="novel_source",
    examples=["给这个项目新建一张世界地图", "从项目地点实体生成初始地图"],
    input_schema_note="title 必填；project_id/snapshot_id 可选；clone_project_places=true 时从该项目地点实体克隆初始据点；map_json 为可选初始结构。",
    output_schema_note="返回新建地图摘要与 revision（初版为 1，并落 v1 历史快照）。",
    risk_level="write",
    output_type="world_map_detail",
)
def create_world_map(
    title: str,
    project_id: str = "",
    snapshot_id: str = "",
    map_json: dict[str, Any] | None = None,
    clone_project_places: bool = False,
    operator: str = "agent",
) -> dict[str, Any]:
    if clone_project_places and not project_id:
        return {"success": False, "error": "从地点克隆需要 project_id"}
    with SessionLocal() as session:
        service = WorldMapService(session)
        try:
            if clone_project_places:
                document = service.create_map_from_project_places(project_id)
                if title and title.strip():
                    document = service.update_map(
                        document.id,
                        map_json=loads_json(document.map_json, {}),
                        expected_revision=int(document.revision or 1),
                        title=title,
                        operator=operator,
                    )
            else:
                document = service.create_map(
                    title=title,
                    project_id=project_id or None,
                    snapshot_id=snapshot_id or None,
                    map_json=map_json,
                    operator=operator,
                )
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "map": _map_summary(document), "revision": document.revision}


@register_tool(
    name="save_world_map",
    description="按 revision 做 CAS 保存世界地图（版本不一致则拒绝，避免覆盖他人编辑），并落一条历史快照。",
    category="novel_source",
    examples=["把这版地图改好保存", "更新这张地图的区域和据点"],
    input_schema_note="map_id、map_json、expected_revision 必填；expected_revision 必须是读取时拿到的版本号；title 可选。",
    output_schema_note="返回新 revision；版本冲突时 success=false 并给出当前版本号。",
    risk_level="write",
    output_type="world_map_save_result",
)
def save_world_map(
    map_id: str,
    map_json: dict[str, Any],
    expected_revision: int,
    title: str = "",
    operator: str = "agent",
) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WorldMapService(session)
        try:
            document = service.update_map(
                map_id,
                map_json=map_json or {},
                expected_revision=int(expected_revision or 0),
                title=title or "",
                operator=operator,
            )
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "map": _map_summary(document), "revision": document.revision}


@register_tool(
    name="render_world_map_svg",
    description="把结构化地图确定性地渲染为 SVG（本地渲染，不调用模型、不消耗配额）。",
    category="novel_source",
    examples=["渲染这张地图的 SVG", "看看地图长什么样"],
    input_schema_note="必须提供 map_id；SVG 超长时会被截断并在 truncated 标记。",
    output_schema_note="返回 svg 文本与 truncated 标记。",
    risk_level="read",
    output_type="world_map_svg",
)
def render_world_map_svg(map_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WorldMapService(session)
        document = service.get_map(map_id)
        if not document:
            return {"success": False, "error": "地图文档不存在"}
        svg = render_map_svg(document)
        return {
            "success": True,
            "map_id": map_id,
            "svg": svg[:MAX_SVG_CHARS],
            "truncated": len(svg) > MAX_SVG_CHARS,
        }


@register_tool(
    name="export_world_map_points",
    description="导出地图的结构化点位 JSON（含 entity_id 与原文证据锚点），用于下游复用或校对。",
    category="novel_source",
    examples=["导出这张地图的点位数据", "把地图据点和证据给我"],
    input_schema_note="必须提供 map_id；返回的是结构化点位而非图片。",
    output_schema_note="返回 data（点位、区域、路线与实体/证据引用）。",
    risk_level="read",
    output_type="world_map_export",
)
def export_world_map_points(map_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WorldMapService(session)
        document = service.get_map(map_id)
        if not document:
            return {"success": False, "error": "地图文档不存在"}
        try:
            resolved = service.resolve_nodes_with_entities(map_id)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "data": build_map_export(document, resolved)}


@register_tool(
    name="resolve_world_map_entities",
    description="解析地图据点关联的地点实体与原文证据，识别游离标记（未关联实体的据点）。",
    category="novel_source",
    examples=["这张地图有哪些据点没关联实体", "看看据点的原文证据"],
    input_schema_note="必须提供 map_id；引用不复制，实体信息按需回查。",
    output_schema_note="返回已关联据点（含实体与证据）与游离标记列表。",
    risk_level="read",
    output_type="world_map_entity_resolution",
)
def resolve_world_map_entities(map_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WorldMapService(session)
        try:
            resolved = service.resolve_nodes_with_entities(map_id)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        # service 已把引用解析好：每项含 node / entity_id / entity / relations，
        # 游离标记（无 entity_id 或实体已不存在）由 orphan_node_ids 直接给出。
        items = resolved.get("nodes") or []
        orphan_ids = [str(item) for item in (resolved.get("orphan_node_ids") or []) if item]
        return {
            "success": True,
            "linked_count": max(0, len(items) - len(orphan_ids)),
            "orphan_node_ids": orphan_ids,
            "nodes": items,
        }


@register_tool(
    name="build_world_map_visual_prompt",
    description="从结构化地图确定性生成生图提示词（含坐标约定与据点方位），不消耗任何配额。",
    category="novel_source",
    examples=["生成这张地图的生图提示词", "看看地图成图会用什么 prompt"],
    input_schema_note="map_id 必填；style 可选（如 写实/水彩/水墨）；不落库、不生成图。",
    output_schema_note="返回 prompt 文本。",
    risk_level="read",
    output_type="world_map_prompt",
)
def build_world_map_visual_prompt_tool(map_id: str, style: str = "") -> dict[str, Any]:
    with SessionLocal() as session:
        service = WorldMapService(session)
        document = service.get_map(map_id)
        if not document:
            return {"success": False, "error": "地图文档不存在"}
        return {
            "success": True,
            "map_id": map_id,
            "prompt": build_map_visual_prompt(document, style=style),
        }


@register_tool(
    name="optimize_world_map_visual_prompt",
    description="用 LLM 润色地图生图提示词：保留全部地名、坐标约束与方位，只改写表达；不生成图、不落库。",
    category="novel_source",
    examples=["优化这张地图的生图提示词", "让提示词更贴近画面：强调北境雪原"],
    input_schema_note="map_id 必填；prompt 为空时从结构化数据生成；focus 为强调或修正项；provider/model 可选。消耗一次 LLM 文本配额。",
    output_schema_note="返回 prompt（原文）与 optimized_prompt（润色结果），需人工/下一步确认后才生图。",
    risk_level="read",
    output_type="world_map_prompt_optimization",
)
async def optimize_world_map_visual_prompt_tool(
    map_id: str,
    prompt: str = "",
    style: str = "",
    focus: str = "",
    provider: str = "",
    model: str = "",
) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WorldMapService(session)
        document = service.get_map(map_id)
        if not document:
            return {"success": False, "error": "地图文档不存在"}
        try:
            result = await optimize_map_visual_prompt(
                document,
                prompt=prompt,
                style=style,
                focus=focus,
                provider=provider,
                model=model,
            )
        except RuntimeError as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "map_id": map_id, **result}


@register_tool(
    name="generate_world_map_visual",
    description="用生图模型生成地图视觉成图：成图是派生资产，只回写引用，不改动结构化空间关系。",
    category="novel_source",
    examples=["给这张地图生成一张视觉成图", "按优化后的提示词出图"],
    input_schema_note="map_id 必填；prompt 为空时从结构化数据生成（可传上一步 optimized_prompt）；style/negative_prompt/size/n/provider/model 可选；参考图优先传 reference_asset_ids（素材库节点 ID，服务端解析为最新版本图片路径），reference_images（URL/base64）仅作兜底；save_to_asset_hub 默认 true。消耗生图配额，属于写操作。",
    output_schema_note="返回 url/local_path/node_id/provider/model 与实际使用的 prompt；成图不会自动铺为底图。",
    risk_level="write",
    output_type="world_map_visual",
)
async def generate_world_map_visual_tool(
    map_id: str,
    prompt: str = "",
    style: str = "",
    negative_prompt: str = "",
    size: str = "1024x1024",
    n: int = 1,
    provider: str = "",
    model: str = "",
    reference_asset_ids: list[str] | None = None,
    reference_images: list[str] | None = None,
    save_to_asset_hub: bool = True,
) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WorldMapService(session)
        document = service.get_map(map_id)
        if not document:
            return {"success": False, "error": "地图文档不存在"}
        try:
            generated = await generate_map_visual(
                session,
                document,
                prompt=prompt,
                style=style,
                negative_prompt=negative_prompt,
                size=size or "1024x1024",
                n=n or 1,
                provider=provider,
                model=model,
                reference_asset_ids=list(reference_asset_ids or []),
                reference_images=list(reference_images or []),
                save_to_asset_hub=save_to_asset_hub,
            )
        except RuntimeError as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "map_id": map_id, **generated}


@register_tool(
    name="list_region_shape_presets",
    description="列出区域形状的受控词表（自然意象/聚落形态/人工构筑/面积感/不规则度）与默认值，供选择 generate_region_shape 的参数。",
    category="novel_source",
    examples=["区域形状有哪些参数可选", "看看形状词表"],
    input_schema_note="无入参。",
    output_schema_note="返回 nature/settlement/structure/scale 词表、irregularity 范围与默认参数。",
    risk_level="read",
    output_type="region_shape_presets",
)
def list_region_shape_presets() -> dict[str, Any]:
    presets = shape_presets()
    return {"success": True, **presets}


@register_tool(
    name="generate_region_shape",
    description=(
        "为区域生成形状语义参数并写入地图：显式 params 直接校验，未给时由 LLM 从区域与"
        "成员据点描述推断（受控词表，越界回退并记录）。只写 mode/seed/params，"
        "不产生顶点——顶点由前端按 (成员据点, params, seed) 确定性展开（决策 D-1，"
        "本工具不实现几何）。手绘（manual）区域默认拒绝覆盖，需 overwrite=true。"
    ),
    category="novel_source",
    examples=["给徐家村生成区域形状", "把北岭画成山地形态的区域"],
    input_schema_note=(
        "map_id 与 region_id 必填；params 可选（缺省时调 LLM 推断，消耗一次文本配额）；"
        "seed 缺省按区域 id 稳定派生；overwrite=true 才能覆盖手绘区域（旧顶点可从版本历史找回）。"
    ),
    output_schema_note="返回 params/seed/fallbacks/source 与写入后的 revision；不含顶点。",
    risk_level="write",
    output_type="region_shape_generation",
)
async def generate_region_shape(
    map_id: str,
    region_id: str,
    params: dict[str, Any] | None = None,
    seed: int = 0,
    overwrite: bool = False,
    provider: str = "",
    model: str = "",
    operator: str = "agent",
) -> dict[str, Any]:
    with SessionLocal() as session:
        try:
            preview = await generate_region_shape_params(
                session,
                map_id,
                region_id,
                params=params,
                seed=seed or None,
                provider=provider,
                model=model,
            )
            document = set_region_shape(
                session,
                map_id,
                region_id,
                params=preview["params"],
                seed=preview["seed"],
                overwrite=overwrite,
                operator=operator or "agent",
            )
        except (ValueError, RuntimeError) as exc:
            return {"success": False, "error": str(exc)}
        return {
            "success": True,
            "map_id": map_id,
            "region_id": region_id,
            "params": preview["params"],
            "seed": preview["seed"],
            "fallbacks": preview["fallbacks"],
            "source": preview["source"],
            "revision": document.revision,
            "note": "顶点由前端展开显示；用户在画布显式保存时顶点才随 map_json 入库",
        }


@register_tool(
    name="list_world_map_revisions",
    description="列出世界地图的历史版本（append-only 快照，倒序），用于对比与回滚。",
    category="novel_source",
    examples=["这张地图有哪些历史版本", "看看地图 v2 改了什么"],
    input_schema_note="map_id 必填；revision 可选，传了则返回该版本完整 map_json。",
    output_schema_note="返回 revisions（版本号/标题/摘要/操作人）与可选的单版本内容。",
    risk_level="read",
    output_type="world_map_revision_list",
)
def list_world_map_revisions(
    map_id: str, revision: int = 0, limit: int = 50
) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WorldMapService(session)
        document = service.get_map(map_id)
        if not document:
            return {"success": False, "error": "地图文档不存在"}
        rows = service.list_revisions(map_id, limit=max(1, min(int(limit or 50), 500)))
        payload = [
            {
                "revision": row.revision,
                "title": row.title,
                "summary": row.summary,
                "operator": row.operator,
                "created_at": row.created_at.isoformat() if getattr(row, "created_at", None) else "",
            }
            for row in rows
        ]
        result: dict[str, Any] = {"success": True, "total": len(rows), "revisions": payload}
        if revision:
            row = session.exec(
                select(WorldMapRevision).where(
                    WorldMapRevision.map_id == map_id,
                    WorldMapRevision.revision == int(revision),
                )
            ).first()
            if not row:
                return {"success": False, "error": f"版本 v{revision} 不存在"}
            result["revision_detail"] = {
                "revision": row.revision,
                "title": row.title,
                "map_json": loads_json(row.map_json, {}),
            }
        return result


@register_tool(
    name="rollback_world_map",
    description="把世界地图回滚到某个历史版本：以旧快照为内容产生**新**版本，历史链不被改写。",
    category="novel_source",
    examples=["把地图回滚到 v2", "恢复上一版地图"],
    input_schema_note="map_id 与 revision 必填；expected_revision 为当前版本号（CAS），回滚同样会落一条历史快照。",
    output_schema_note="返回回滚后的新 revision 与地图摘要。",
    risk_level="write",
    output_type="world_map_rollback_result",
)
def rollback_world_map(
    map_id: str, revision: int, expected_revision: int, operator: str = "agent"
) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WorldMapService(session)
        current = service.get_map(map_id)
        if not current:
            return {"success": False, "error": "地图文档不存在"}
        # service.rollback 以当前版本做 CAS；这里先校验调用方持有的版本，避免覆盖他人编辑。
        if int(current.revision or 1) != int(expected_revision or 0):
            return {
                "success": False,
                "error": f"地图已被修改，当前版本为 {current.revision}，请刷新后重试",
            }
        try:
            document = service.rollback(
                map_id,
                int(revision),
                operator=operator or f"rollback:v{revision}",
            )
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {
            "success": True,
            "map": _map_summary(document),
            "revision": document.revision,
            "rolled_back_to": int(revision),
        }
