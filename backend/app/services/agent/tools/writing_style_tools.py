"""Agent tools for writing style profiles.

These mirror the human `/writing-styles` API exactly: the Agent calls the same
``WritingStyleService`` and goes through the same review gate.  Extraction only
produces a ``draft`` — activation and project binding are separate, explicit
write steps, so an Agent can never silently change how a project writes.
"""

from __future__ import annotations

from typing import Any

from app.db.database import SessionLocal
from app.services.agent.registry import register_tool
from app.services.creative_project.writing_style import (
    WritingStyleService,
    serialize_style_profile,
)


@register_tool(
    name="list_writing_style_profiles",
    description="列出写作风格档案（可按状态过滤），供选择要审核、激活或绑定的档案。",
    category="creative_project",
    examples=["列出我的写作风格档案", "看看有哪些已激活的风格"],
    input_schema_note="owner_id 默认 default；status 可选 draft/reviewed/active/archived。只读。",
    output_schema_note="返回 profiles；每项含 id/name/status/source_type/version/checksum。",
    risk_level="read",
    output_type="writing_style_profile_list",
)
def list_writing_style_profiles(owner_id: str = "default", status: str = "") -> dict[str, Any]:
    with SessionLocal() as session:
        items = WritingStyleService(session).list(owner_id=owner_id, status=status or None)
        return {
            "success": True,
            "total": len(items),
            "profiles": [serialize_style_profile(item) for item in items],
        }


@register_tool(
    name="get_writing_style_profile",
    description="读取单个写作风格档案详情：表达机制维度、溯源与校验和，用于人工或 Agent 审核。",
    category="creative_project",
    examples=["看看这个风格档案写了什么", "这个档案的来源样本是什么"],
    input_schema_note="profile_id 必填。只读。",
    output_schema_note="返回档案详情：dimensions/new_examples/anti_template_constraints/provenance/checksum/status。",
    risk_level="read",
    output_type="writing_style_profile_detail",
)
def get_writing_style_profile(profile_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WritingStyleService(session)
        item = service.get(profile_id)
        if not item:
            return {"success": False, "error": "风格档案不存在"}
        return {"success": True, "profile": serialize_style_profile(item)}


@register_tool(
    name="extract_writing_style_from_source",
    description=(
        "从来源快照提取写作风格草稿：本地测量聚合 + 有界抽象分析，只提炼“怎么写”的表达机制。"
        "产出恒为 draft，**不会自动激活、不会改任何项目**，必须再审核与激活。"
    ),
    category="creative_project",
    examples=["从《活着》提一份风格档案草稿", "按这本小说的写法生成风格草稿"],
    input_schema_note=(
        "snapshot_id 必填；name/owner_id/provider/model 可选；max_chars 为样本上限（默认 12000）。"
        "不落来源正文，只留样本 hash、测量指标与字符偏移；消耗一次文本配额。"
    ),
    output_schema_note="返回 draft 档案（含 dimensions 与 provenance）；需再调用 review 与 activate。",
    risk_level="write",
    output_type="writing_style_profile_detail",
)
async def extract_writing_style_from_source(
    snapshot_id: str,
    name: str = "",
    owner_id: str = "default",
    provider: str = "",
    model: str = "",
    max_chars: int = 12000,
) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WritingStyleService(session)
        try:
            item = await service.extract_draft_from_source(
                snapshot_id=snapshot_id,
                name=name,
                owner_id=owner_id,
                provider=provider or None,
                model=model or None,
                max_chars=max_chars,
            )
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        except RuntimeError as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "profile": serialize_style_profile(item)}


@register_tool(
    name="review_writing_style_profile",
    description="审核风格档案草稿（draft → reviewed）：确认其表达机制可用，仍不会生效。",
    category="creative_project",
    examples=["审核这份风格草稿", "确认这个风格档案没问题"],
    input_schema_note="profile_id 必填。只改状态，不绑定项目。",
    output_schema_note="返回审核后的档案（status=reviewed）。",
    risk_level="write",
    output_type="writing_style_profile_detail",
)
def review_writing_style_profile(profile_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WritingStyleService(session)
        try:
            item = service.review(profile_id)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "profile": serialize_style_profile(item)}


@register_tool(
    name="activate_writing_style_profile",
    description=(
        "激活已审核的风格档案（reviewed → active）。激活只意味着可被绑定，"
        "**绑定项目才会真正影响写作**，需再调用 bind_project_writing_style。"
    ),
    category="creative_project",
    examples=["激活这份风格档案", "让这个风格可用"],
    input_schema_note="profile_id 必填；未审核的草稿会被拒绝。",
    output_schema_note="返回激活后的档案（status=active）。",
    risk_level="write",
    output_type="writing_style_profile_detail",
)
def activate_writing_style_profile(profile_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WritingStyleService(session)
        try:
            item = service.activate(profile_id)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "profile": serialize_style_profile(item)}


@register_tool(
    name="bind_project_writing_style",
    description=(
        "把已激活的风格档案绑定到项目：仅作为 Context Pack T6 的表达机制注入，"
        "不会覆盖 T0-T5 正典、动态状态、章节契约或正文。"
    ),
    category="creative_project",
    examples=["给这个项目用上这个风格", "把风格绑到《活着》改编项目"],
    input_schema_note=(
        "project_id 与 profile_id 必填；intensity 为 subtle/balanced/strong（默认 balanced）；"
        "stage_scope 可限定生效阶段；priority 数字越大越优先。"
    ),
    output_schema_note="返回绑定关系；风格内容不会被复制进项目正典。",
    risk_level="write",
    output_type="writing_style_link",
)
def bind_project_writing_style(
    project_id: str,
    profile_id: str,
    intensity: str = "balanced",
    stage_scope: list[str] | None = None,
    priority: int = 100,
) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WritingStyleService(session)
        try:
            link = service.bind(
                project_id,
                profile_id,
                intensity=intensity,
                stage_scope=stage_scope or [],
                priority=priority,
            )
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {
            "success": True,
            "project_id": project_id,
            "profile_id": profile_id,
            "intensity": link.intensity,
            "stage_scope": link.stage_scope_json,
            "priority": link.priority,
        }


@register_tool(
    name="unbind_project_writing_style",
    description="解除项目与风格档案的绑定，项目回到无风格注入的写作状态。",
    category="creative_project",
    examples=["取消这个项目的风格", "别给这个项目套风格了"],
    input_schema_note="project_id 与 profile_id 必填。",
    output_schema_note="返回解绑结果。",
    risk_level="write",
    output_type="writing_style_unbind_result",
)
def unbind_project_writing_style(project_id: str, profile_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WritingStyleService(session)
        try:
            service.unbind(project_id, profile_id)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "project_id": project_id, "profile_id": profile_id}


@register_tool(
    name="export_writing_style_skill",
    description="把风格档案导出为 Markdown Skill 草稿（互操作格式，可版本管理与人工编辑）。",
    category="creative_project",
    examples=["把这份风格导出成 Markdown", "给我这个风格的 Skill 文件"],
    input_schema_note="profile_id 必填。只读，不改档案。",
    output_schema_note="返回 markdown 文本（含 frontmatter 元信息、表达机制维度、新造示例与约束）。",
    risk_level="read",
    output_type="writing_style_markdown",
)
def export_writing_style_skill(profile_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        try:
            markdown = WritingStyleService(session).export_skill_markdown(profile_id)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "profile_id": profile_id, "markdown": markdown}


@register_tool(
    name="import_writing_style_skill",
    description=(
        "从 Markdown Skill 草稿导入风格档案：解析后产出 draft，"
        "**同样要做来源材料检查**，不是免检通道。"
    ),
    category="creative_project",
    examples=["导入这份风格 Skill", "把这个 Markdown 变成风格档案"],
    input_schema_note="markdown 必填；name/owner_id 可选；source_terms 可传来源专名用于污染检查。",
    output_schema_note="返回导入的 draft 档案；需再审核与激活。",
    risk_level="write",
    output_type="writing_style_profile_detail",
)
def import_writing_style_skill(
    markdown: str,
    name: str = "",
    owner_id: str = "default",
    source_terms: list[str] | None = None,
) -> dict[str, Any]:
    with SessionLocal() as session:
        try:
            item = WritingStyleService(session).import_skill_markdown(
                markdown, name=name, owner_id=owner_id, source_terms=source_terms
            )
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "profile": serialize_style_profile(item)}


@register_tool(
    name="review_prose_style_deviation",
    description=(
        "审阅一段正文与项目已激活风格档案的偏差：给出实测指标与基线偏差、"
        "需人工核对的约束。**只报告，绝不改写正文或档案**。"
    ),
    category="creative_project",
    examples=["看看这段正文有没有跑偏风格", "检查这章是不是太不像设定的口吻"],
    input_schema_note="project_id 与 text 必填；stage 可限定生效阶段。不消耗配额。",
    output_schema_note="返回 reports；每项含 metrics（actual/expected/deviation_ratio/severity）与约束提醒。",
    risk_level="read",
    output_type="writing_style_deviation_report",
)
def review_prose_style_deviation(
    project_id: str, text: str, stage: str = ""
) -> dict[str, Any]:
    with SessionLocal() as session:
        return {
            "success": True,
            **WritingStyleService(session).review_prose_deviation(
                project_id, text, stage=stage
            ),
        }


@register_tool(
    name="archive_writing_style_profile",
    description="归档风格档案（archived）：不再参与激活与绑定，历史绑定保留。",
    category="creative_project",
    examples=["归档这份风格档案", "这个风格不用了"],
    input_schema_note="profile_id 必填。",
    output_schema_note="返回归档后的档案（status=archived）。",
    risk_level="write",
    output_type="writing_style_profile_detail",
)
def archive_writing_style_profile(profile_id: str) -> dict[str, Any]:
    with SessionLocal() as session:
        service = WritingStyleService(session)
        try:
            item = service.archive(profile_id)
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        return {"success": True, "profile": serialize_style_profile(item)}
