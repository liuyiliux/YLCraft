"""Agent tools for platform and creative-project prompt templates."""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlmodel import select

from app.db.database import SessionLocal
from app.db.models.platform_template import PlatformTemplate
from app.services.agent.registry import register_tool


_VARIABLE_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def _template_summary(template: PlatformTemplate) -> dict[str, Any]:
    return {
        "id": str(template.id),
        "platform": template.platform,
        "name": template.name,
        "template_scope": template.template_scope,
        "template_stage": template.template_stage,
        "description": template.description or "",
        "variables": template.variables or {},
        "default_size": template.default_size,
        "is_active": template.is_active,
        "sort_order": template.sort_order,
        "system_template_length": len(template.system_template or ""),
        "outline_template_length": len(template.outline_template or ""),
        "image_template_length": len(template.image_template or ""),
        "video_template_length": len(template.video_template or ""),
    }


def _template_detail(template: PlatformTemplate) -> dict[str, Any]:
    payload = _template_summary(template)
    payload.update(
        {
            "system_template": template.system_template or "",
            "outline_template": template.outline_template or "",
            "image_template": template.image_template or "",
            "video_template": template.video_template or "",
            "page_structure": template.page_structure or {},
        }
    )
    return payload


def _resolve_template(session, template_id: str = "", platform: str = "") -> PlatformTemplate | None:
    if template_id:
        try:
            return session.get(PlatformTemplate, uuid.UUID(template_id))
        except ValueError:
            return None
    if platform:
        return session.exec(select(PlatformTemplate).where(PlatformTemplate.platform == platform)).first()
    return None


def _replace_known_variables(template: str, variables: dict[str, Any]) -> tuple[str, list[str]]:
    used: list[str] = []

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in variables:
            return match.group(0)
        used.append(key)
        value = variables[key]
        if isinstance(value, (dict, list)):
            import json

            return json.dumps(value, ensure_ascii=False, indent=2)
        return str(value)

    return _VARIABLE_PATTERN.sub(replace, template or ""), sorted(set(used))


def _detect_variables(*templates: str) -> list[str]:
    names: set[str] = set()
    for template in templates:
        names.update(_VARIABLE_PATTERN.findall(template or ""))
    return sorted(names)


@register_tool(
    name="list_prompt_templates",
    description="列出平台图文和创作项目 Prompt 模板，供智能体选择大纲、正文、脚本、分镜、生图等阶段使用。",
    category="prompt_template",
    examples=["列出创作项目的分镜模板", "看看有哪些小说正文模板", "列出所有平台图文模板"],
    input_schema_note="template_scope 默认 creative_project；可传 image_platform/creative_project/all；template_stage 可传 outline/chapter_plan/novel_body/script/storyboard/platform；include_inactive 默认 false；limit 最大 100。",
    output_schema_note="返回 success、total、templates；templates 为摘要，不包含完整长 Prompt，只包含长度、变量、阶段和启用状态。",
    risk_level="read",
    output_type="prompt_template_list",
)
async def list_prompt_templates(
    template_scope: str = "creative_project",
    template_stage: str = "",
    include_inactive: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    with SessionLocal() as session:
        stmt = select(PlatformTemplate)
        if not include_inactive:
            stmt = stmt.where(PlatformTemplate.is_active == True)
        if template_scope and template_scope not in {"all", "*"}:
            stmt = stmt.where(PlatformTemplate.template_scope == template_scope)
        if template_stage and template_stage not in {"all", "*"}:
            stmt = stmt.where(PlatformTemplate.template_stage == template_stage)
        stmt = stmt.order_by(PlatformTemplate.template_scope, PlatformTemplate.sort_order).limit(max(1, min(int(limit or 50), 100)))
        templates = session.exec(stmt).all()
        return {"success": True, "total": len(templates), "templates": [_template_summary(item) for item in templates]}


@register_tool(
    name="get_prompt_template",
    description="读取单个 Prompt 模板的完整 system_template、主要模板、图片模板、视频模板、变量说明和页面结构。",
    category="prompt_template",
    examples=["读取分镜模板完整内容", "查看 writer_room_humanize 模板", "看这个模板的 system prompt"],
    input_schema_note="template_id 和 platform 二选一；platform 是唯一模板标识，例如 creative_storyboard、writer_room_humanize、xiaohongshu。",
    output_schema_note="返回 success、template；template 包含完整模板文本、variables、page_structure、template_scope 和 template_stage。",
    risk_level="read",
    output_type="prompt_template_detail",
)
async def get_prompt_template(template_id: str = "", platform: str = "") -> dict[str, Any]:
    with SessionLocal() as session:
        template = _resolve_template(session, template_id=template_id, platform=platform)
        if not template:
            return {"success": False, "message": "Prompt 模板不存在", "template_id": template_id, "platform": platform}
        return {"success": True, "template": _template_detail(template)}


@register_tool(
    name="preview_prompt_template_render",
    description="用示例变量预览 Prompt 模板渲染结果，不调用大模型、不写入数据库，适合检查智能体准备发送给模型的 system/user/image prompt。",
    category="prompt_template",
    examples=["用当前章节变量预览正文模板", "检查分镜模板会不会把角色参考图写进去", "预览小红书生图模板"],
    input_schema_note="template_id 和 platform 二选一；variables 为要替换的变量对象；template_field 可选 system_template/outline_template/image_template/video_template/all，默认 all。",
    output_schema_note="返回 rendered 字典、detected_variables、used_variables、missing_variables；只替换已知 {变量名}，不会误处理 JSON 示例里的大括号。",
    risk_level="read",
    output_type="prompt_template_preview",
)
async def preview_prompt_template_render(
    template_id: str = "",
    platform: str = "",
    variables: dict[str, Any] | None = None,
    template_field: str = "all",
) -> dict[str, Any]:
    with SessionLocal() as session:
        template = _resolve_template(session, template_id=template_id, platform=platform)
        if not template:
            return {"success": False, "message": "Prompt 模板不存在", "template_id": template_id, "platform": platform}

        fields = ["system_template", "outline_template", "image_template", "video_template"]
        if template_field and template_field != "all":
            if template_field not in fields:
                return {"success": False, "message": f"不支持的 template_field: {template_field}", "supported_fields": fields + ["all"]}
            fields = [template_field]

        values = variables or {}
        rendered: dict[str, str] = {}
        used: set[str] = set()
        detected = _detect_variables(*(getattr(template, field) or "" for field in fields))
        for field in fields:
            text, field_used = _replace_known_variables(getattr(template, field) or "", values)
            rendered[field] = text
            used.update(field_used)
        return {
            "success": True,
            "template": _template_summary(template),
            "rendered": rendered,
            "detected_variables": detected,
            "used_variables": sorted(used),
            "missing_variables": [name for name in detected if name not in values],
        }


@register_tool(
    name="update_prompt_template",
    description="更新平台或创作项目 Prompt 模板，供用户确认后修正文案、变量说明、system prompt、阶段说明和启用状态。",
    category="prompt_template",
    examples=["把分镜模板改成必须输出参考素材 ID", "更新正文模板的人味润色要求", "临时停用某个旧模板"],
    input_schema_note="必须提供 template_id 或 platform；其余字段可选。可更新 name/description/system_template/outline_template/image_template/video_template/variables/page_structure/default_size/is_active/sort_order。",
    output_schema_note="返回 success、template、changed_fields；template 为更新后的完整模板详情。",
    risk_level="write",
    output_type="prompt_template_updated",
)
async def update_prompt_template(
    template_id: str = "",
    platform: str = "",
    name: str | None = None,
    description: str | None = None,
    system_template: str | None = None,
    outline_template: str | None = None,
    image_template: str | None = None,
    video_template: str | None = None,
    variables: dict[str, Any] | None = None,
    page_structure: dict[str, Any] | None = None,
    default_size: str | None = None,
    is_active: bool | None = None,
    sort_order: int | None = None,
) -> dict[str, Any]:
    with SessionLocal() as session:
        template = _resolve_template(session, template_id=template_id, platform=platform)
        if not template:
            return {"success": False, "message": "Prompt 模板不存在", "template_id": template_id, "platform": platform}

        changed: list[str] = []
        updates = {
            "name": name,
            "description": description,
            "system_template": system_template,
            "outline_template": outline_template,
            "image_template": image_template,
            "video_template": video_template,
            "variables": variables,
            "page_structure": page_structure,
            "default_size": default_size,
            "is_active": is_active,
            "sort_order": sort_order,
        }
        for field, value in updates.items():
            if value is None:
                continue
            setattr(template, field, value)
            changed.append(field)
        if not changed:
            return {"success": False, "message": "没有提供需要更新的字段"}

        session.add(template)
        session.commit()
        session.refresh(template)
        return {"success": True, "changed_fields": changed, "template": _template_detail(template)}
