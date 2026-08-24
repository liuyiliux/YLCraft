"""Creative-project tools exposed to the Agent Center."""

from __future__ import annotations

from typing import Any

from sqlmodel import select

from app.db.database import SessionLocal
from app.db.models.creative_project import ProjectAssetLink, ProjectContent, ProjectGenerationLog
from app.services.agent.context_pack import build_creative_project_context_pack
from app.services.agent.registry import register_tool
from app.services.creative_project.service import CreativeProjectService, loads_json


def _content_summary(content: ProjectContent) -> dict[str, Any]:
    data = loads_json(content.data_json)
    return {
        "id": content.id,
        "project_id": content.project_id,
        "content_type": content.content_type,
        "chapter_number": content.chapter_number,
        "episode_number": content.episode_number,
        "title": content.title,
        "version": content.version,
        "is_locked": content.is_locked,
        "source_content_id": content.source_content_id,
        "created_at": content.created_at.isoformat() if content.created_at else None,
        "updated_at": content.updated_at.isoformat() if content.updated_at else None,
        "summary": data.get("summary") or data.get("title") or (content.text_content or "")[:240],
    }


def _content_detail(content: ProjectContent) -> dict[str, Any]:
    payload = _content_summary(content)
    payload.update(
        {
            "data": loads_json(content.data_json),
            "text_content": content.text_content or "",
            "text_length": len(content.text_content or ""),
        }
    )
    return payload


def _asset_link_detail(link: ProjectAssetLink) -> dict[str, Any]:
    return {
        "id": link.id,
        "project_id": link.project_id,
        "asset_id": link.asset_id,
        "content_id": link.content_id,
        "role": link.role,
        "relation": link.relation,
        "metadata": loads_json(link.metadata_json),
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


def _truncate_text(value: str | None, limit: int = 800) -> str:
    text = value or ""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... (truncated, len={len(text)})"


def _generation_log_summary(log: ProjectGenerationLog) -> dict[str, Any]:
    return {
        "id": log.id,
        "project_id": log.project_id,
        "content_id": log.content_id,
        "scene": log.scene,
        "ref_id": log.ref_id,
        "stage": log.stage,
        "provider": log.provider,
        "model": log.model,
        "status": log.status,
        "validation_error": log.validation_error,
        "prompt_preview": _truncate_text(log.prompt, 360),
        "raw_response_preview": _truncate_text(log.raw_response, 360),
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def _generation_log_detail(log: ProjectGenerationLog, *, include_large_fields: bool = True) -> dict[str, Any]:
    detail = _generation_log_summary(log)
    detail.update(
        {
            "request": loads_json(log.request_json),
            "normalized": loads_json(log.normalized_json),
            "prompt": log.prompt if include_large_fields else _truncate_text(log.prompt),
            "raw_response": log.raw_response if include_large_fields else _truncate_text(log.raw_response),
        }
    )
    return detail


@register_tool(
    name="list_creative_projects",
    description="列出创作项目，可按状态或项目类型过滤。",
    category="creative_project",
    examples=["列出最近的创作项目", "有哪些短剧项目"],
    input_schema_note="status/project_type 可留空；limit 建议 5-20，最大 50。",
    output_schema_note="返回 success、total、projects；projects 包含 id/title/project_type/status/current_stage/chapter_count/updated_at。",
    risk_level="read",
    output_type="creative_project_list",
)
async def list_creative_projects(status: str = "", project_type: str = "", limit: int = 20):
    with SessionLocal() as session:
        service = CreativeProjectService(session)
        projects, total = service.list_projects(
            limit=max(1, min(int(limit or 20), 50)),
            status=status or None,
            project_type=project_type or None,
        )
        return {
            "success": True,
            "total": total,
            "projects": [
                {
                    "id": project.id,
                    "title": project.title,
                    "project_type": project.project_type,
                    "status": project.status,
                    "current_stage": project.current_stage,
                    "chapter_count": (loads_json(project.chapter_plan_json).get("chapter_count") or 0),
                    "updated_at": project.updated_at.isoformat() if project.updated_at else None,
                }
                for project in projects
            ],
        }


@register_tool(
    name="inspect_creative_project",
    description="读取创作项目概览、内容数量、最近日志和项目圣经/世界资产摘要。",
    category="creative_project",
    examples=["检查这个项目现在做到哪了", "看看项目有哪些正文和分镜"],
    input_schema_note="必须提供 project_id。",
    output_schema_note="返回 project、content_counts、asset_link_count、bible_cards、recent_logs。",
    risk_level="read",
    output_type="creative_project_inspection",
)
async def inspect_creative_project(project_id: str):
    with SessionLocal() as session:
        service = CreativeProjectService(session)
        project = service.get_project(project_id)
        if not project:
            return {"success": False, "message": "项目不存在"}
        contents = service.list_contents(project_id)
        assets = service.list_asset_links(project_id)
        logs, _ = service.list_generation_logs(project_id, limit=8)
        counts: dict[str, int] = {}
        for content in contents:
            counts[content.content_type] = counts.get(content.content_type, 0) + 1
        bible_cards = [
            _content_summary(content)
            for content in contents
            if content.content_type in {"project_bible", "world_asset"}
        ][:20]
        return {
            "success": True,
            "project": {
                "id": project.id,
                "title": project.title,
                "project_type": project.project_type,
                "status": project.status,
                "current_stage": project.current_stage,
                "outline_title": loads_json(project.outline_json).get("title") or "",
                "chapter_count": loads_json(project.chapter_plan_json).get("chapter_count") or 0,
            },
            "content_counts": counts,
            "asset_link_count": len(assets),
            "bible_cards": bible_cards,
            "recent_logs": [
                {
                    "id": log.id,
                    "stage": log.stage,
                    "status": log.status,
                    "provider": log.provider,
                    "model": log.model,
                    "validation_error": log.validation_error,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
                for log in logs
            ],
        }


@register_tool(
    name="build_creative_project_context_pack",
    description="为智能体构建紧凑的创作项目上下文包，包含项目概览、章节状态、角色摘要、参考素材、最近日志和缺口。",
    category="creative_project",
    examples=["为当前创作项目构建上下文包", "读取第 2 章相关的项目上下文"],
    input_schema_note="必须提供 project_id；chapter_number 可选，传 0 表示全项目。",
    output_schema_note="返回 context_pack，包含 project、chapter_status、latest_contents、characters、reference_assets、known_gaps。",
    risk_level="read",
    output_type="creative_project_context_pack",
)
async def build_creative_project_context_pack_tool(project_id: str, chapter_number: int = 0):
    pack = build_creative_project_context_pack(
        project_id,
        chapter_number=int(chapter_number) if chapter_number else None,
    )
    return {"success": bool(pack), "context_pack": pack}


@register_tool(
    name="list_creative_project_contents",
    description="列出某个创作项目的阶段内容摘要，例如 chapter_outline、novel_body、script、storyboard、project_bible、world_asset。",
    category="creative_project",
    examples=["列出这个项目第 2 章的正文和分镜", "查看项目所有脚本版本"],
    input_schema_note="必须提供 project_id；content_type/chapter_number 可选；limit 建议 10-30，最大 80。",
    output_schema_note="返回 contents；每项包含 id/content_type/chapter_number/title/version/is_locked/summary。",
    risk_level="read",
    output_type="creative_project_content_list",
)
async def list_creative_project_contents(project_id: str, content_type: str = "", chapter_number: int = 0, limit: int = 30):
    with SessionLocal() as session:
        query = select(ProjectContent).where(ProjectContent.project_id == project_id)
        if content_type:
            query = query.where(ProjectContent.content_type == content_type)
        if chapter_number:
            query = query.where(ProjectContent.chapter_number == int(chapter_number))
        query = query.order_by(ProjectContent.created_at.desc()).limit(max(1, min(int(limit or 30), 80)))
        contents = session.exec(query).all()
        return {"success": True, "contents": [_content_summary(content) for content in contents]}


@register_tool(
    name="get_creative_project_content",
    description="读取单条项目内容的完整结构化数据和正文文本，供续写、改写、分镜拆解或质检使用。",
    category="creative_project",
    examples=["读取这个正文版本的完整内容", "打开第 3 章分镜内容给我检查"],
    input_schema_note="必须提供 content_id；project_id 可选，用于防止误读其他项目内容。",
    output_schema_note="返回 content；包含 data、text_content、text_length、版本、章节号、锁定状态和来源内容 ID。",
    risk_level="read",
    output_type="creative_project_content_detail",
)
async def get_creative_project_content(content_id: str, project_id: str = ""):
    with SessionLocal() as session:
        content = session.get(ProjectContent, content_id)
        if not content or (project_id and content.project_id != project_id):
            return {"success": False, "message": "项目内容不存在"}
        return {"success": True, "content": _content_detail(content)}


@register_tool(
    name="get_creative_production_plan",
    description="读取创作项目当前的可编辑生产计划；可选返回版本历史，以便导演检查节点依赖、确认状态、素材和画布引用。",
    category="creative_project",
    examples=["读取这个项目的导演计划", "查看生产计划的历史版本"],
    input_schema_note="必须提供 project_id；include_history=true 时返回全部历史版本。",
    output_schema_note="返回 plan 或 plans；计划节点包含阶段、专业角色、依赖、内容/素材/画布引用、可审计规划摘要和确认点。",
    risk_level="read",
    output_type="creative_production_plan",
)
async def get_creative_production_plan(project_id: str, include_history: bool = False):
    with SessionLocal() as session:
        service = CreativeProjectService(session)
        result = service.get_production_plan(project_id, include_history=include_history)
        if include_history:
            return {"success": True, "plans": [_content_detail(item) for item in result]}
        return {"success": True, "plan": _content_detail(result) if result else None}


@register_tool(
    name="save_creative_production_plan",
    description="将导演提出或用户修改后的结构化生产计划保存为新版本。计划只记录可见的执行摘要，不会暴露隐藏推理；保存本身不启动图片、视频或发布等消耗型动作。",
    category="creative_project",
    examples=["保存恐怖漫画的生产计划", "基于上一版计划只调整第三页构图节点"],
    input_schema_note="必须提供 project_id 和 plan_json（有效 JSON 对象）；base_plan_id 可选，用于明确计划来源版本。",
    output_schema_note="返回新 plan 版本；会校验节点依赖、项目内容、Asset Hub 素材和项目画布的归属。",
    risk_level="write",
    output_type="creative_production_plan_saved",
)
async def save_creative_production_plan(
    project_id: str,
    plan_json: str,
    base_plan_id: str = "",
):
    plan = loads_json(plan_json, fallback=None)
    if not isinstance(plan, dict):
        raise ValueError("plan_json 必须是有效 JSON 对象")
    with SessionLocal() as session:
        service = CreativeProjectService(session)
        content = service.save_production_plan(
            project_id=project_id,
            plan=plan,
            base_plan_id=base_plan_id or None,
        )
        return {"success": True, "plan": _content_detail(content)}


@register_tool(
    name="update_creative_project_content",
    description="写回一条项目内容的标题、正文文本、结构化 JSON 或锁定状态，用于保存智能体改写后的产物。",
    category="creative_project",
    examples=["把润色后的第 3 章正文保存回项目", "更新这个分镜内容并锁定"],
    input_schema_note="必须提供 project_id 和 content_id；title/text_content/data_json/is_locked 均可选，data_json 必须是 JSON 字符串。",
    output_schema_note="返回 content；包含更新后的摘要、完整 text_content 长度、版本号和更新时间。",
    risk_level="write",
    output_type="creative_project_content_updated",
)
async def update_creative_project_content(
    project_id: str,
    content_id: str,
    title: str = "",
    text_content: str = "",
    data_json: str = "",
    is_locked: bool | None = None,
):
    data = None
    if data_json:
        loaded = loads_json(data_json, fallback=None)
        if loaded is None:
            raise ValueError("data_json 必须是有效 JSON 字符串")
        data = loaded
    with SessionLocal() as session:
        service = CreativeProjectService(session)
        content = service.update_content(
            project_id=project_id,
            content_id=content_id,
            title=title if title else None,
            data=data,
            text_content=text_content if text_content else None,
            is_locked=is_locked,
        )
        return {"success": True, "content": _content_detail(content)}


@register_tool(
    name="list_creative_project_asset_links",
    description="列出创作项目已关联的素材/参考卡，可按内容 ID 或角色类型过滤。",
    category="creative_project",
    examples=["列出这个项目的角色参考图", "查看第 3 章分镜绑定了哪些参考素材"],
    input_schema_note="必须提供 project_id；content_id/role 可选。role 常用 character/background/style/world/reference/output。",
    output_schema_note="返回 asset_links；每项包含 id/project_id/asset_id/content_id/role/relation/metadata/created_at。",
    risk_level="read",
    output_type="creative_project_asset_link_list",
)
async def list_creative_project_asset_links(project_id: str, content_id: str = "", role: str = ""):
    with SessionLocal() as session:
        service = CreativeProjectService(session)
        links = service.list_asset_links(project_id)
        if content_id:
            links = [link for link in links if link.content_id == content_id]
        if role:
            links = [link for link in links if link.role == role]
        return {
            "success": True,
            "asset_links": [_asset_link_detail(link) for link in links],
            "total": len(links),
        }


@register_tool(
    name="link_creative_project_asset",
    description="把素材库资产挂到创作项目或某条项目内容上，作为角色、背景、风格、世界观或输出产物参考。",
    category="creative_project",
    examples=["把这张角色立绘挂到项目参考卡集合", "把生成的分镜图关联到当前 storyboard 内容"],
    input_schema_note="必须提供 project_id 和 asset_id；content_id 可选；role 默认 reference；relation 默认 references；metadata_json 可选且必须是 JSON 字符串。",
    output_schema_note="返回 asset_link；后续脚本、分镜、生图提示词可使用该 asset_id 作为 reference_asset_ids。",
    risk_level="write",
    output_type="creative_project_asset_link_created",
)
async def link_creative_project_asset(
    project_id: str,
    asset_id: str,
    content_id: str = "",
    role: str = "reference",
    relation: str = "references",
    metadata_json: str = "",
):
    metadata = loads_json(metadata_json, fallback={}) if metadata_json else {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata_json 必须是 JSON 对象字符串")
    with SessionLocal() as session:
        service = CreativeProjectService(session)
        link = service.link_asset(
            project_id=project_id,
            asset_id=asset_id,
            content_id=content_id or None,
            role=role or "reference",
            relation=relation or "references",
            metadata=metadata,
        )
        return {"success": True, "asset_link": _asset_link_detail(link)}


@register_tool(
    name="match_creative_project_reference_assets",
    description="为脚本、分镜或漫画页内容匹配项目参考卡，并把 reference_asset_ids/reference_notes 写回内容 JSON。",
    category="creative_project",
    examples=["给这个分镜内容匹配角色和背景参考图", "根据项目参考卡给脚本场景补 reference_asset_ids"],
    input_schema_note="必须提供 project_id 和 content_id；content_type 需为 script/storyboard/comic_pages；provider/model 可选。",
    output_schema_note="返回 content；content.data 中每个 scene/panel/page 会尽量补充 reference_asset_ids 和 reference_notes。",
    risk_level="costly",
    output_type="creative_project_reference_match_result",
    cost_hint="可能调用文本模型分析参考卡并写回项目内容；执行前应确认。",
)
async def match_creative_project_reference_assets(
    project_id: str,
    content_id: str,
    provider: str = "",
    model: str = "",
):
    with SessionLocal() as session:
        service = CreativeProjectService(session)
        content = await service.match_reference_assets(
            project_id,
            content_id=content_id,
            provider=provider or None,
            model=model or None,
        )
        return {"success": True, "content": _content_detail(content)}


@register_tool(
    name="list_creative_project_generation_logs",
    description="查询创作项目或跨项目的 AI 生成日志摘要，用于排查提示词、模型返回、校验失败和生成状态。",
    category="creative_project",
    examples=["查看这个项目最近失败的生成日志", "列出某个角色立绘的生成日志"],
    input_schema_note="project_id 可为空表示跨项目；stage/status/scene/ref_id 可选；limit 建议 10-50，最大 200；offset 可分页。",
    output_schema_note="返回 logs、total、limit、offset；logs 只含 prompt/raw_response 预览，完整内容请用 get_creative_project_generation_log。",
    risk_level="read",
    output_type="creative_project_generation_log_list",
)
async def list_creative_project_generation_logs(
    project_id: str = "",
    stage: str = "",
    status: str = "",
    scene: str = "",
    ref_id: str = "",
    limit: int = 30,
    offset: int = 0,
):
    with SessionLocal() as session:
        service = CreativeProjectService(session)
        logs, total = service.list_generation_logs(
            project_id=project_id or None,
            stage=stage or None,
            status=status or None,
            scene=scene or None,
            ref_id=ref_id or None,
            limit=max(1, min(int(limit or 30), 200)),
            offset=max(0, int(offset or 0)),
        )
        return {
            "success": True,
            "logs": [_generation_log_summary(log) for log in logs],
            "total": total,
            "limit": max(1, min(int(limit or 30), 200)),
            "offset": max(0, int(offset or 0)),
        }


@register_tool(
    name="get_creative_project_generation_log",
    description="读取单条 AI 生成日志详情，包括完整 prompt、request、raw_response、normalized 和 validation_error。",
    category="creative_project",
    examples=["打开这条失败日志看原始响应", "读取这个生成日志的完整 prompt"],
    input_schema_note="必须提供 log_id；include_large_fields=false 时会截断 prompt/raw_response。",
    output_schema_note="返回 log；包含 prompt、request、raw_response、normalized、validation_error、provider/model/stage/status。",
    risk_level="read",
    output_type="creative_project_generation_log_detail",
)
async def get_creative_project_generation_log(log_id: str, include_large_fields: bool = True):
    with SessionLocal() as session:
        log = session.get(ProjectGenerationLog, log_id)
        if not log:
            return {"success": False, "message": "生成日志不存在"}
        return {"success": True, "log": _generation_log_detail(log, include_large_fields=include_large_fields)}


@register_tool(
    name="sync_creative_project_bible",
    description="从当前故事大纲同步项目圣经和世界资产卡，供后续章节细纲、分镜和智能体使用。",
    category="creative_project",
    input_schema_note="必须提供 project_id；overwrite=false 时只补缺失卡片。",
    output_schema_note="返回 created_count 和 cards；会写入 project_contents。",
    risk_level="write",
    output_type="creative_project_bible_cards",
)
async def sync_creative_project_bible(project_id: str, overwrite: bool = False):
    with SessionLocal() as session:
        service = CreativeProjectService(session)
        cards = service.sync_project_bible(project_id, overwrite=overwrite)
        return {
            "success": True,
            "created_count": len(cards),
            "cards": [_content_summary(card) for card in cards],
        }


@register_tool(
    name="run_creative_project_pipeline",
    description="运行创作项目生产流水线，可生成细纲、正文、脚本、分镜、参考卡匹配或漫画页。默认跳过已有内容。",
    category="creative_project",
    input_schema_note="必须提供 project_id；stages 可包含 chapter_outline/novel_body/script/storyboard/reference_asset_match/comic_pages；chapters 可选。",
    output_schema_note="返回 result，包含各阶段执行、跳过和失败信息；会写入项目内容和生成日志。",
    risk_level="costly",
    output_type="creative_project_pipeline_result",
    cost_hint="会按阶段调用文本模型并写入项目内容/日志；章节越多消耗越高，执行前需要确认。",
)
async def run_creative_project_pipeline(
    project_id: str,
    stages: list[str] | None = None,
    chapters: list[int] | None = None,
    provider: str = "",
    model: str = "",
    skip_existing: bool = True,
    continue_on_error: bool = True,
):
    with SessionLocal() as session:
        service = CreativeProjectService(session)
        result = await service.run_pipeline(
            project_id,
            stages=stages or [],
            chapters=chapters or [],
            provider=provider or None,
            model=model or None,
            skip_existing=skip_existing,
            continue_on_error=continue_on_error,
        )
        return {"success": True, "result": result}


@register_tool(
    name="run_creative_writer_room",
    description="运行小说写作室分阶段候选链，例如 scene_beats、character_rehearsal、prose_draft、prose_humanized、prose_review。",
    category="creative_project",
    input_schema_note="必须提供 project_id 和 chapter_number；steps 可为空表示默认流程。",
    output_schema_note="返回 result，包含写作室各步骤产物；会写入 project_contents 和日志。",
    risk_level="costly",
    output_type="creative_writer_room_result",
    cost_hint="会运行小说写作室多步骤模型调用并写入候选产物，执行前需要确认。",
)
async def run_creative_writer_room(
    project_id: str,
    chapter_number: int,
    steps: list[str] | None = None,
    provider: str = "",
    model: str = "",
    rehearsal_mode: str = "team",
    continue_on_error: bool = True,
):
    with SessionLocal() as session:
        service = CreativeProjectService(session)
        result = await service.run_writer_room(
            project_id,
            chapter_number=chapter_number,
            steps=steps or [],
            provider=provider or None,
            model=model or None,
            rehearsal_mode=rehearsal_mode,
            continue_on_error=continue_on_error,
        )
        return {"success": True, "result": result}
