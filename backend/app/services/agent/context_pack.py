"""Context pack builders for Agent Center runs."""

from __future__ import annotations

from typing import Any

from sqlmodel import select

from app.db.database import SessionLocal
from app.db.models.character import Character, CharacterStoryLink
from app.db.models.creative_project import ProjectContent, ProjectGenerationLog
from app.db.models.previs import PrevisSceneDocument
from app.services.creative_project.profiles import CONTENT_PRODUCTION_PROFILES
from app.services.creative_project.service import CreativeProjectService, loads_json


IMPORTANT_CONTENT_TYPES = [
    "chapter_outline",
    "novel_body",
    "script",
    "storyboard",
    "comic_pages",
    "reference_asset_match",
    "project_bible",
    "world_asset",
]


def _content_brief(content: ProjectContent) -> dict[str, Any]:
    data = loads_json(content.data_json)
    text = content.text_content or ""
    return {
        "id": content.id,
        "content_type": content.content_type,
        "chapter_number": content.chapter_number,
        "title": content.title,
        "version": content.version,
        "is_locked": content.is_locked,
        "summary": data.get("summary") or data.get("title") or text[:180],
        "updated_at": content.updated_at.isoformat() if content.updated_at else None,
    }


def _production_plan_brief(content: ProjectContent | None) -> dict[str, Any] | None:
    """Return the business-visible director plan state for an Agent context.

    A production plan is deliberately not a scratchpad for hidden model
    reasoning.  The context therefore carries only the user-editable plan
    fields and bounded node summaries needed to decide the next safe action.
    """
    if content is None:
        return None

    data = loads_json(content.data_json)
    nodes = list(data.get("nodes") or [])
    confirmation_nodes = []
    for node in nodes:
        if not isinstance(node, dict) or not node.get("requires_confirmation"):
            continue
        confirmation_nodes.append(
            {
                "id": str(node.get("id") or ""),
                "label": str(node.get("label") or ""),
                "stage": str(node.get("stage") or ""),
                "status": str(node.get("status") or "planned"),
            }
        )

    return {
        "content_id": content.id,
        "version": content.version,
        "source_plan_id": data.get("source_plan_id") or content.source_content_id or "",
        "title": content.title,
        "goal": (data.get("goal") or content.text_content or "")[:400],
        "production_profile": data.get("production_profile") or "",
        "status": data.get("status") or "draft",
        "confirmation_status": data.get("confirmation_status") or "pending",
        "canvas_document_id": data.get("canvas_document_id") or "",
        "asset_ids": list(data.get("asset_ids") or [])[:24],
        "node_count": len(nodes),
        "confirmation_nodes": confirmation_nodes[:24],
        "nodes": [
            {
                "id": str(node.get("id") or ""),
                "stage": str(node.get("stage") or ""),
                "label": str(node.get("label") or ""),
                "specialist_role": str(node.get("specialist_role") or ""),
                "status": str(node.get("status") or "planned"),
                "depends_on": list(node.get("depends_on") or []),
                "input_content_ids": list(node.get("input_content_ids") or []),
                "input_asset_ids": list(node.get("input_asset_ids") or []),
                "output_content_ids": list(node.get("output_content_ids") or []),
                "output_asset_ids": list(node.get("output_asset_ids") or []),
                "provider": str(node.get("provider") or ""),
                "model": str(node.get("model") or ""),
                "requires_confirmation": bool(node.get("requires_confirmation", True)),
                "rerun_scope": str(node.get("rerun_scope") or "node"),
                "planning_summary": node.get("planning_summary") if isinstance(node.get("planning_summary"), dict) else {},
            }
            for node in nodes[:48]
            if isinstance(node, dict)
        ],
        "updated_at": content.updated_at.isoformat() if content.updated_at else None,
    }


def _chapter_status(contents: list[ProjectContent]) -> list[dict[str, Any]]:
    by_chapter: dict[int, dict[str, Any]] = {}
    for item in contents:
        if not item.chapter_number:
            continue
        chapter = by_chapter.setdefault(
            int(item.chapter_number),
            {
                "chapter_number": int(item.chapter_number),
                "content_types": [],
                "latest_titles": {},
            },
        )
        if item.content_type not in chapter["content_types"]:
            chapter["content_types"].append(item.content_type)
        chapter["latest_titles"].setdefault(item.content_type, item.title)
    return [by_chapter[key] for key in sorted(by_chapter)]


def _character_briefs(project_id: str, limit: int = 12) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        links = session.exec(
            select(CharacterStoryLink)
            .where(CharacterStoryLink.story_id == project_id)
            .order_by(CharacterStoryLink.updated_at.desc())
            .limit(limit)
        ).all()
        if not links:
            return []
        ids = [item.character_id for item in links if item.character_id]
        characters = session.exec(select(Character).where(Character.id.in_(ids))).all() if ids else []
        by_id = {item.id: item for item in characters}
        briefs = []
        for link in links:
            character = by_id.get(link.character_id)
            if not character:
                continue
            briefs.append(
                {
                    "character_id": character.id,
                    "name": character.name,
                    "role": link.usage_role or character.role,
                    "identity": link.local_identity,
                    "faction": link.local_faction,
                    "appearance": character.appearance[:220],
                    "costume": link.local_costume or character.costume_hint,
                    "portrait_node_id": character.portrait_node_id,
                    "portrait_url": character.portrait_url,
                }
            )
        return briefs


#: 覆盖度明细的截断上限。**计数始终是精确值**——截断只影响明细，且会被显式标记；
#: 否则 Agent 会把「只看到前 24 个」误当成「总共只有 24 个」，据此给出错的排产建议。
PREVIS_UNCOVERED_LIMIT = 24
PREVIS_SCENE_LIMIT = 12
#: 每个场景摘要里的人形对象明细上限（同样显式标记截断，避免"只看到前 12 个"被读成"只有 12 个"）。
PREVIS_HUMAN_PROXY_LIMIT = 12


def _node_metadata(node: dict[str, Any]) -> dict[str, Any]:
    metadata = node.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _previs_scene_brief(row: PrevisSceneDocument) -> dict[str, Any]:
    """单个预演场景的只读摘要，带稳定 ID 与锁定状态。"""
    scene = dict(row.scene_json or {})
    nodes = [item for item in (scene.get("nodes") or []) if isinstance(item, dict)]
    cameras = [item for item in (scene.get("cameras") or []) if isinstance(item, dict)]
    # 人形对象的**当前状态**（姿势 / 动作 / 身高）必须给出来：只给 id 与锁定状态的话，
    # Agent 只能猜"这个人现在是什么样"，于是会提出"把坐姿改成坐姿"这类无效改动。
    human_proxies = [
        {
            "node_id": str(item.get("id") or ""),
            "name": str(item.get("name") or ""),
            "height": _node_metadata(item).get("height"),
            "pose": str(_node_metadata(item).get("pose") or "stand"),
            # 动作存的是引用（`motion:<标识>` 或模型自带的 clip 名），空串表示无动作
            "motion": str(_node_metadata(item).get("animationClip") or ""),
            "custom_pose": bool(_node_metadata(item).get("poseJoints")),
        }
        for item in nodes
        if str(item.get("kind") or "") == "human_proxy"
    ]
    return {
        # scene_id / 节点与机位 id 都是创建后稳定的，是 Agent 唯一可用的操作目标
        "scene_id": str(row.id),
        "storyboard_content_id": row.storyboard_content_id or "",
        "panel_number": row.panel_number,
        "title": row.title,
        "revision": int(row.revision or 1),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "node_count": len(nodes),
        "camera_count": len(cameras),
        "keyframe_count": len(scene.get("keyframes") or []),
        "active_camera_id": str(scene.get("activeCameraId") or ""),
        # 锁定状态是「哪些东西不能被自动改」的结构化答案，必须带 ID；
        # 只给数量等于让 Agent 再问一次，而它没有"再问"的能力。
        "locked_nodes": [
            {"node_id": str(item.get("id") or ""), "name": str(item.get("name") or "")}
            for item in nodes
            if item.get("locked")
        ],
        "locked_cameras": [
            {"camera_id": str(item.get("id") or ""), "name": str(item.get("name") or "")}
            for item in cameras
            if item.get("locked")
        ],
        "human_proxies": human_proxies[:PREVIS_HUMAN_PROXY_LIMIT],
        "human_proxies_truncated": len(human_proxies) > PREVIS_HUMAN_PROXY_LIMIT,
    }


def _storyboard_panels(contents: list[ProjectContent]) -> list[tuple[str, int]]:
    """项目里全部分镜面板的 `(storyboard_content_id, panel_number)` 列表。

    覆盖度计算的基准。分镜可以按章有多份（各自一个 `storyboard` 内容），
    面板号只在各自的分镜内唯一，所以键必须带上 content_id。
    """
    panels: list[tuple[str, int]] = []
    for content in contents:
        if content.content_type != "storyboard":
            continue
        data = loads_json(content.data_json)
        for panel in data.get("panels") or []:
            if not isinstance(panel, dict):
                continue
            try:
                number = int(panel.get("panel_number") or 0)
            except Exception:
                continue
            if number > 0:
                panels.append((content.id, number))
    return panels


def _previs_brief(project_id: str, contents: list[ProjectContent]) -> dict[str, Any]:
    """预演场景的只读摘要，面向**覆盖度**问题而不是只罗列节点。

    为什么强调覆盖度：只列「有哪些场景」回答不了「还有哪些镜头没预演」，
    而后者才是导演在排产前真正要问的——前者是清单，后者才是决策依据。
    """
    panels = _storyboard_panels(contents)
    try:
        with SessionLocal() as session:
            rows = session.exec(
                select(PrevisSceneDocument)
                .where(PrevisSceneDocument.project_id == project_id)
                .order_by(PrevisSceneDocument.updated_at.desc())
            ).all()
    except Exception as exc:  # noqa: BLE001
        # 预演表不可用不该让整份上下文崩掉——导演还需要项目的其它部分才能工作。
        # 但必须**显式报错**：若悄悄当成"没有预演场景"，Agent 会把覆盖度读成 0
        # 并据此给出完全错误的排产建议。
        return {
            "read_only": True,
            "scope": "project",
            "error": f"预演场景读取失败：{exc}",
            "storyboard_panels_total": len(panels),
            # 置 None 而非 0：调用方据此区分"确实没有"与"没读出来"
            "panels_without_scene": None,
        }

    panel_keys = set(panels)
    bound_keys = {
        (row.storyboard_content_id, int(row.panel_number))
        for row in rows
        if row.storyboard_content_id and row.panel_number
    }
    uncovered = sorted(panel_keys - bound_keys)
    scene_briefs = [_previs_scene_brief(row) for row in rows]

    return {
        "read_only": True,
        "note": "只读摘要；对预演场景的写入须经受限操作与人工确认。",
        # 覆盖度按**整个项目**统计（不随 chapter_number 收窄），并显式声明范围，
        # 否则调用方会把「某一章的缺口」误读成「全项目的缺口」。
        "scope": "project",
        "storyboard_content_count": len({content_id for content_id, _ in panels}),
        "storyboard_panels_total": len(panels),
        "scene_count": len(rows),
        "panels_with_scene": len(panel_keys & bound_keys),
        "panels_without_scene": len(uncovered),
        "uncovered_panels": [
            {"storyboard_content_id": content_id, "panel_number": number}
            for content_id, number in uncovered[:PREVIS_UNCOVERED_LIMIT]
        ],
        "uncovered_panels_truncated": len(uncovered) > PREVIS_UNCOVERED_LIMIT,
        # 两种不一致都报出来：场景没绑定面板、场景指向已不存在的面板
        "scenes_without_panel": len(rows) - len(
            [row for row in rows if row.storyboard_content_id and row.panel_number]
        ),
        "scenes_referencing_missing_panel": len(bound_keys - panel_keys),
        "scenes": scene_briefs[:PREVIS_SCENE_LIMIT],
        "scenes_truncated": len(scene_briefs) > PREVIS_SCENE_LIMIT,
    }


def build_creative_project_context_pack(
    project_id: str,
    *,
    chapter_number: int | None = None,
    content_limit: int = 24,
) -> dict[str, Any]:
    """Build a compact read-only project context for agent reasoning."""
    if not project_id:
        return {}

    with SessionLocal() as session:
        service = CreativeProjectService(session)
        project = service.get_project(project_id)
        if not project:
            return {
                "project_id": project_id,
                "found": False,
                "warning": "creative project not found",
            }

        outline = loads_json(project.outline_json)
        chapter_plan = loads_json(project.chapter_plan_json)
        settings = loads_json(project.settings_json)
        profile_id = str(settings.get("production_profile") or "")
        profile = CONTENT_PRODUCTION_PROFILES.get(profile_id) or {}
        contents = service.list_contents(project_id)
        production_plan = service.get_production_plan(project_id)
        assets = service.list_asset_links(project_id)
        logs, _ = service.list_generation_logs(project_id, limit=8)

        latest_by_type: dict[str, dict[str, Any]] = {}
        filtered_contents = []
        for content in contents:
            if chapter_number and content.chapter_number and int(content.chapter_number) != int(chapter_number):
                continue
            if content.content_type in IMPORTANT_CONTENT_TYPES:
                filtered_contents.append(content)
            latest_by_type.setdefault(content.content_type, _content_brief(content))

        bible_cards = [
            _content_brief(content)
            for content in contents
            if content.content_type in {"project_bible", "world_asset"}
        ][:12]

        # 算一次复用：覆盖度既要作为独立块给 Agent，也要并进 known_gaps，
        # 分两次调就是两次 DB 查询。
        previs = _previs_brief(project_id, contents)

        return {
            "project": {
                "id": project.id,
                "title": project.title,
                "project_type": project.project_type,
                "status": project.status,
                "current_stage": project.current_stage,
                "production_profile": {
                    "id": profile_id,
                    "label": profile.get("label") or "",
                    # 两个生产族的**编排单位**不同：内容包以条目（页/卡/镜头）为单位，
                    # 叙事族以章节与正文为单位，因此各有自己的阶段词表。只暴露阶段名而
                    # 隐藏族别，会让「为什么该按这些阶段走」无法自查；导演在提议计划前
                    # 需要能分辨自己属于哪一族。
                    "production_family": profile.get("production_family") or "",
                    "package_type": profile.get("package_type") or None,
                    "planning_unit": profile.get("planning_unit") or "",
                    "recommended_stages": list(profile.get("recommended_stages") or []),
                    "optional_stages": list(profile.get("optional_stages") or []),
                },
                "outline_title": outline.get("title") or "",
                "logline": outline.get("logline") or "",
                "chapter_count": chapter_plan.get("chapter_count") or len(chapter_plan.get("chapters") or []),
            },
            "chapter_number": chapter_number,
            "production_plan": _production_plan_brief(production_plan),
            "chapter_status": _chapter_status(contents),
            "latest_contents": list(latest_by_type.values())[:content_limit],
            "focused_contents": [_content_brief(item) for item in filtered_contents[:content_limit]],
            "characters": _character_briefs(project_id),
            "reference_assets": [
                {
                    "asset_id": link.asset_id,
                    "content_id": link.content_id,
                    "role": link.role,
                    "relation": link.relation,
                    "metadata": loads_json(link.metadata_json),
                }
                for link in assets[:18]
            ],
            "bible_cards": bible_cards,
            "previs": previs,
            "recent_logs": [
                {
                    "stage": log.stage,
                    "status": log.status,
                    "provider": log.provider,
                    "model": log.model,
                    "validation_error": log.validation_error,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
                for log in logs
            ],
            "known_gaps": _known_gaps(chapter_plan, contents, assets, previs),
        }


def _known_gaps(
    chapter_plan: dict[str, Any],
    contents: list[ProjectContent],
    assets: list[Any],
    previs: dict[str, Any] | None = None,
) -> list[str]:
    gaps: list[str] = []
    if not chapter_plan.get("chapters"):
        gaps.append("缺少章节规划")
    content_types = {item.content_type for item in contents}
    for content_type, label in [
        ("project_bible", "项目圣经"),
        ("chapter_outline", "章节细纲"),
        ("novel_body", "正文"),
        ("script", "脚本"),
        ("storyboard", "分镜"),
    ]:
        if content_type not in content_types:
            gaps.append(f"缺少{label}")
    # 预演的覆盖度缺口放进这里，而不是只留在 previs 块里——known_gaps 是既有机制，
    # 导演按它决定"下一步做什么"，覆盖度属于同一类判断。
    if previs and previs.get("panels_without_scene"):
        gaps.append(f"{previs['panels_without_scene']} 个分镜面板还没有预演场景")
    if not assets:
        gaps.append("缺少项目参考素材")
    return gaps[:8]
