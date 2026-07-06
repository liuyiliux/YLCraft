"""Agent tools for managing file-backed skill packages safely."""

from __future__ import annotations

import json
from typing import Any

from app.db.database import AsyncSessionLocal, ensure_agent_tables
from app.services.agent.registry import register_tool
from app.services.agent.skill_drafts import AgentSkillDraftService, SkillDraftError
from app.services.agent.skill_loader import SkillPackageLoader


def _draft_to_dict(item) -> dict[str, Any]:
    try:
        metadata = json.loads(item.metadata_json or "{}")
    except json.JSONDecodeError:
        metadata = {}
    try:
        diagnostics = json.loads(item.diagnostics_json or "[]")
    except json.JSONDecodeError:
        diagnostics = []
    return {
        "id": item.id,
        "name": item.name,
        "title": item.title,
        "description": item.description,
        "skill_type": item.skill_type,
        "metadata": metadata,
        "source_type": item.source_type,
        "source_url": item.source_url,
        "status": item.status,
        "target_path": item.target_path,
        "checksum": item.checksum,
        "diagnostics": diagnostics,
        "created_at": item.created_at.isoformat() if item.created_at else "",
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else "",
    }


@register_tool(
    name="import_agent_skill_from_url",
    description=(
        "Import a remote SKILL.md URL as a pending Agent skill draft. "
        "This does not enable or execute the remote skill; a human must approve it in Settings > Agent 技能."
    ),
    category="agent_skill",
    examples=[
        "把这个 SKILL.md 地址导入到待审批 skill",
        "从 GitHub raw/blob 链接导入 Agent skill 草稿",
    ],
    input_schema_note="url must be an http(s) URL pointing to UTF-8 SKILL.md markdown. GitHub blob URLs are converted to raw URLs.",
    output_schema_note="Returns success, draft metadata, review reminder, and diagnostics when validation fails.",
    risk_level="write",
    output_type="agent_skill_draft",
    description_short="Import remote SKILL.md into pending review.",
)
async def import_agent_skill_from_url(url: str) -> dict[str, Any]:
    if not (url or "").strip():
        return {"success": False, "error": "url cannot be empty"}
    await ensure_agent_tables()
    async with AsyncSessionLocal() as session:
        service = AgentSkillDraftService(session)
        try:
            draft = await service.import_url(url)
            await session.commit()
        except SkillDraftError as exc:
            await session.rollback()
            return {"success": False, "error": str(exc), "diagnostics": exc.diagnostics}
        except Exception as exc:
            await session.rollback()
            return {"success": False, "error": str(exc), "diagnostics": [str(exc)]}
        return {
            "success": True,
            "draft": _draft_to_dict(draft),
            "next_step": "请到 设置 > Agent 技能 > Skill 草稿审批 中查看内容并批准后启用。",
        }


@register_tool(
    name="create_agent_skill_draft",
    description=(
        "Create a pending Agent skill draft from pasted SKILL.md markdown. "
        "The draft is not enabled until a human approves it."
    ),
    category="agent_skill",
    examples=["把这段 SKILL.md 保存为待审批 skill 草稿", "根据用户粘贴的 skill markdown 建草稿"],
    input_schema_note="content must be a complete SKILL.md with YAML frontmatter including name, description and skill_type.",
    output_schema_note="Returns success and draft metadata. It never approves or loads the skill automatically.",
    risk_level="write",
    output_type="agent_skill_draft",
    description_short="Create pending skill draft from markdown.",
)
async def create_agent_skill_draft(content: str, source_url: str = "") -> dict[str, Any]:
    if not (content or "").strip():
        return {"success": False, "error": "content cannot be empty"}
    await ensure_agent_tables()
    async with AsyncSessionLocal() as session:
        service = AgentSkillDraftService(session)
        try:
            draft = await service.create_manual_draft(
                content,
                source_type="manual",
                source_url=source_url or "",
            )
            await session.commit()
        except SkillDraftError as exc:
            await session.rollback()
            return {"success": False, "error": str(exc), "diagnostics": exc.diagnostics}
        except Exception as exc:
            await session.rollback()
            return {"success": False, "error": str(exc), "diagnostics": [str(exc)]}
        return {
            "success": True,
            "draft": _draft_to_dict(draft),
            "next_step": "请到 设置 > Agent 技能 > Skill 草稿审批 中查看内容并批准后启用。",
        }


@register_tool(
    name="list_agent_skill_drafts",
    description="List pending/approved/rejected Agent skill drafts for review.",
    category="agent_skill",
    examples=["列出待审批 skill 草稿", "查看已经导入的 Agent skill"],
    input_schema_note="status can be pending, approved, rejected, or all.",
    output_schema_note="Returns draft metadata without full markdown content.",
    risk_level="read",
    output_type="agent_skill_draft_list",
    description_short="List pending skill drafts.",
)
async def list_agent_skill_drafts(status: str = "pending") -> dict[str, Any]:
    await ensure_agent_tables()
    async with AsyncSessionLocal() as session:
        service = AgentSkillDraftService(session)
        drafts = await service.list_drafts(status=status or "pending")
        return {"success": True, "drafts": [_draft_to_dict(item) for item in drafts]}


@register_tool(
    name="list_agent_skill_packages",
    description="List loaded file-backed Agent skill packages and bundles.",
    category="agent_skill",
    examples=["列出当前可用 Agent skills", "看看有哪些 SKILL.md 包已经加载"],
    output_schema_note="Returns package index and bundle index from the file-backed skill loader.",
    risk_level="read",
    output_type="agent_skill_package_index",
    description_short="List loaded skill packages.",
)
async def list_agent_skill_packages() -> dict[str, Any]:
    loader = SkillPackageLoader()
    return {
        "success": True,
        "root": str(loader.default_builtin_root()),
        "packages": loader.package_index(),
        "bundles": loader.bundle_index(),
    }


@register_tool(
    name="inspect_agent_run_skill_candidate",
    description="Inspect whether a completed Agent run is suitable for creating a reusable SKILL.md draft.",
    category="agent_skill",
    examples=["分析这个 run 能不能沉淀成 skill", "看看刚才的工具链是否适合生成 skill 草稿"],
    input_schema_note="run_id is required.",
    output_schema_note="Returns eligibility, reasons, successful tool count, distinct tools and score.",
    risk_level="read",
    output_type="agent_skill_candidate_analysis",
    description_short="Analyze run as skill candidate.",
)
async def inspect_agent_run_skill_candidate(run_id: str) -> dict[str, Any]:
    if not (run_id or "").strip():
        return {"success": False, "error": "run_id cannot be empty"}
    await ensure_agent_tables()
    async with AsyncSessionLocal() as session:
        service = AgentSkillDraftService(session)
        try:
            analysis = await service.inspect_run_candidate(run_id)
        except SkillDraftError as exc:
            return {"success": False, "error": str(exc), "diagnostics": exc.diagnostics}
        return {"success": True, "analysis": analysis}


@register_tool(
    name="create_agent_skill_draft_from_run",
    description=(
        "Create a pending SKILL.md draft from a successful complex Agent run. "
        "The generated skill is not enabled until a human approves it."
    ),
    category="agent_skill",
    examples=["把这个 run 沉淀成 skill 草稿", "根据刚才成功的多工具流程生成 SKILL.md"],
    input_schema_note="run_id is required. Optional name/title override the generated package metadata.",
    output_schema_note="Returns pending draft metadata and review reminder.",
    risk_level="write",
    output_type="agent_skill_draft",
    description_short="Create skill draft from run evidence.",
)
async def create_agent_skill_draft_from_run(run_id: str, name: str = "", title: str = "") -> dict[str, Any]:
    if not (run_id or "").strip():
        return {"success": False, "error": "run_id cannot be empty"}
    await ensure_agent_tables()
    async with AsyncSessionLocal() as session:
        service = AgentSkillDraftService(session)
        try:
            draft = await service.create_draft_from_run(run_id, name=name or "", title=title or "")
            await session.commit()
        except SkillDraftError as exc:
            await session.rollback()
            return {"success": False, "error": str(exc), "diagnostics": exc.diagnostics}
        except Exception as exc:
            await session.rollback()
            return {"success": False, "error": str(exc), "diagnostics": [str(exc)]}
        return {
            "success": True,
            "draft": _draft_to_dict(draft),
            "next_step": "请到 设置 > Agent 技能 > Skill 草稿审批 中查看内容并批准后启用。",
        }
