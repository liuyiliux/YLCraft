"""分镜格 → 预演初稿的**共用管线**：HTTP 接口与 Agent 工具走同一条路。

为什么必须共用：`POST /api/v1/previs/scenes/{id}/draft` 与工具 `generate_previs_draft`
要做完全相同的事（读场景与绑定分镜 → 匹配道具 → 翻译 → 校验 → 应用出 `proposed_scene`）。
两处各写一遍，迟早出现"接口生成的草案"与"AI 拿到的草案"不一样——而它们本该是同一件事，
且差异只会在用户按了确认之后才暴露。

**它是只读的**：只做 SELECT，不写任何表（包括不产生素材库资产）。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.db.database import SessionLocal
from app.db.models.creative_project import ProjectContent
from app.db.models.previs import PrevisSceneDocument
from app.services.previs.draft import build_previs_draft, load_storyboard_panel
from app.services.previs.motion_service import motion_carriers
from app.services.previs.operations import apply_operations, validate_operations

logger = logging.getLogger("ylcraft.previs.draft_service")

#: 道具匹配只接受这几种可加载的模型文件：素材库里同名图片/视频不少，
#: 不按扩展名把一道关，初稿会写出一个"加载失败"的模型节点。
PROP_MODEL_EXTS = (".glb", ".gltf", ".fbx", ".obj")


def normalize_scene_dict(scene: Any) -> dict[str, Any]:
    """补齐场景字典的必备字段（`fps` / `durationFrames` / `nodes` / `cameras` / `keyframes` …）。

    **接口层与工具层必须用同一份口径**：`proposed_scene` 会被前端直接拿去落库，
    少一个 `keyframes` 键就会在下一次求值时炸在渲染层。接口层在此之上还有一层
    \"不是对象就 422\"的入参校验（那是 API 的职责，不属于这里）。
    """
    normalized = dict(scene) if isinstance(scene, dict) else {}
    normalized.setdefault("fps", 24)
    normalized.setdefault("durationFrames", 0)
    normalized.setdefault("activeCameraId", "")
    normalized.setdefault("nodes", [])
    normalized.setdefault("cameras", [])
    normalized.setdefault("keyframes", [])
    normalized.setdefault("settings", {})
    return normalized


async def lookup_prop_assets(props: list[str]) -> dict[str, dict[str, Any]]:
    """道具名 → 素材库里的模型资产（**只读**，不产生任何资产）。

    复用 `search_assets` 工具而不是另写一套查询：素材检索的口径（状态过滤、关键词命中）
    只有一份，这里再写一遍迟早会和它漂移。查询失败**降级成\"没找到\"**而不是抛错——
    道具匹配不到只是少摆一个道具，不该让整个初稿生成失败。
    """
    from app.api.v1.assets import _hub_file_url
    from app.services.agent.tools.asset_tools import search_assets

    found: dict[str, dict[str, Any]] = {}
    for prop in props:
        if not prop or prop in found:
            continue
        try:
            result = await search_assets(query=prop, limit=5)
        except Exception as exc:  # noqa: BLE001
            logger.warning("初稿道具匹配失败（prop=%s）：%s", prop, exc)
            continue
        for asset in result.get("assets") or []:
            path = str(asset.get("file_path") or "")
            if path.lower().endswith(PROP_MODEL_EXTS):
                found[prop] = {
                    "asset_id": str(asset.get("id") or ""),
                    "name": str(asset.get("title") or prop),
                    "model_url": _hub_file_url(path),
                }
                break
    return found


async def compose_previs_draft(scene_id: str, *, fps: Optional[int] = None) -> dict[str, Any]:
    """按场景绑定的分镜格生成初稿。

    返回两种形状之一：
    - 失败：`{"ok": False, "status": 404|400, "error": "<可读原因>"}`
      （`status` 供 HTTP 层直接映射；工具层只取 `error`）
    - 成功：`{"ok": True, "scene_id", "panel_number", "scene_revision", "operations",
      "defaults", "warnings", "summary", "rejected", "proposed_scene"}`

    **只读**：全程不写库；草案要不要落库由调用方决定（接口返回给预演台做幽灵预览，
    工具返回给 Agent 作为提案）。
    """
    with SessionLocal() as session:
        row = session.get(PrevisSceneDocument, scene_id)
        if row is None:
            return {"ok": False, "status": 404, "error": f"预演场景不存在：{scene_id}"}
        scene = normalize_scene_dict(row.scene_json)
        current_revision = int(row.revision or 1)
        content_id = str(row.storyboard_content_id or "")
        panel_number = int(row.panel_number or 0)
        if not content_id or panel_number <= 0:
            return {
                "ok": False,
                "status": 400,
                "error": "该场景未绑定项目分镜面板，无法从分镜生成初稿；请从分镜卡片进入预演台，或手动搭建场景",
            }
        content = session.get(ProjectContent, content_id)
        panel = load_storyboard_panel(content, panel_number)
        if panel is None:
            return {
                "ok": False,
                "status": 404,
                "error": f"分镜内容 {content_id} 里找不到第 {panel_number} 格",
            }
        # 动作清单必须一起读：初稿会把分镜的 `action` 翻成 `assign_motion`（"挥手""点头"…），
        # 而自检时要判断"这个动作是否存在、载体是否匹配"。**不传就等于把这些操作全部拒掉**
        # ——草案看起来生成了，实际少了动作（这类"自检把正确的东西判错"最难发现）。
        carriers = motion_carriers(session)

    props = [str(item).strip() for item in (panel.get("props") or []) if str(item).strip()]
    prop_assets = await lookup_prop_assets(props) if props else {}
    draft = build_previs_draft(scene, panel, prop_assets=prop_assets, fps=fps)

    # 顺手把草案跑一遍校验并应用，返回 `proposed_scene`：
    # 前端的幽灵预览要渲染"落库后会变成什么样"，而它**不该再实现一遍应用逻辑**——两份实现必然漂移。
    # 校验顺带变成一次自检：草案若有落不了库的操作，会出现在 rejected 里（而不是等到用户点确认才炸）。
    accepted, rejected = validate_operations(
        scene,
        draft["operations"],
        expected_revision=current_revision,
        current_revision=current_revision,
        motion_carriers=carriers,
    )
    proposed_scene = scene
    warnings = list(draft["warnings"])
    if rejected:
        warnings.append(
            f"有 {len(rejected)} 条草案操作未通过校验，已从草案中剔除："
            + "；".join(str(item.get("reason") or "") for item in rejected[:3])
        )
    elif accepted:
        proposed_scene, _ = apply_operations(scene, accepted)

    return {
        "ok": True,
        "scene_id": scene_id,
        "panel_number": panel_number,
        # 生成草案时服务端场景的版本：与本地不一致时前端必须拦住确认（本地有未保存改动，
        # 或场景已被他人改动），否则"看着草案点确认"会把别人的改动覆盖掉
        "scene_revision": current_revision,
        "proposed_scene": proposed_scene,
        "rejected": rejected,
        **draft,
    }
