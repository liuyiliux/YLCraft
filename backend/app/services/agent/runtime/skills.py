"""Skill routing for YLCraft agent runtime.

Skills are reusable work methods. Tools execute actions; skills tell the agent
when and how to combine tools for a domain workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.agent.skill_loader import SkillPackageLoader


@dataclass(frozen=True)
class SkillRoute:
    skill_id: str
    reason: str
    score: int = 1
    source: str = "fallback"
    trigger_type: str = ""
    matches: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillActivation:
    cleaned_message: str
    skill_ids: tuple[str, ...] = ()
    bundle_ids: tuple[str, ...] = ()
    bundle_instruction: str = ""
    diagnostics: tuple[str, ...] = ()


class SkillRouter:
    """Route task/context/tool signals to reusable AgentSkill templates."""

    # Business routing rules now live in backend/app/skills/**/SKILL.md.
    # Keep the shape for custom fallback injection in tests or future migrations.
    DOMAIN_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...]], ...] = ()
    TOOL_SKILL_HINTS: dict[str, tuple[str, ...]] = {
        "search_platform_sources": ("asset_search",),
        "search_platform_sources_enhanced": ("asset_search", "platform_source_search"),
        "parse_download_link": ("asset_search", "download_workflow"),
        "create_download_task": ("asset_search", "download_workflow"),
        "generate_image_asset": ("comic_image_prompt", "reference_match", "image_generation_workflow"),
        "generate_video_asset": ("video_generation_workflow",),
        "run_creative_writer_room": ("novel_completion", "prose_humanize", "prose_review"),
        "build_creative_project_context_pack": ("creative_project_advance", "gap_analysis"),
        "extract_subtitle": ("subtitle_workflow",),
        "burn_subtitle": ("subtitle_workflow",),
        "add_bgm_to_video": ("bgm_workflow",),
        "start_cutclaw_clip": ("clip_workflow",),
        "start_narrato_clip": ("clip_workflow",),
        "start_moe_clip": ("clip_workflow",),
        "generate_tts_audio": ("tts_workflow",),
        "create_ebook_from_folder": ("ebook_workflow",),
        "export_asset_dataset": ("export_quality_workflow",),
    }

    def __init__(self, loader: SkillPackageLoader | None = None):
        self.loader = loader or SkillPackageLoader()
        self.package_rules = self.loader.route_rules()
        self.package_skill_ids = {item[0] for item in self.package_rules}
        self.bundle_by_name = {item.name: item for item in self.loader.load_bundles()}
        package_skill_ids = {item[0] for item in self.package_rules}
        self.fallback_rules = [
            (*item, "fallback")
            for item in self.DOMAIN_RULES
            if item[0] not in package_skill_ids
        ]

    def parse_activation(self, message: str, max_items: int = 5) -> SkillActivation:
        """Parse leading `/skill` or `/bundle` tokens."""
        raw = str(message or "")
        stripped = raw.lstrip()
        if not stripped.startswith("/"):
            return SkillActivation(cleaned_message=raw)

        tokens = stripped.split()
        consumed = 0
        skill_ids: list[str] = []
        bundle_ids: list[str] = []
        bundle_instructions: list[str] = []
        diagnostics: list[str] = []
        known_skills = self.package_skill_ids | {item[0] for item in self.DOMAIN_RULES}

        for token in tokens[:max_items]:
            if not token.startswith("/"):
                break
            name = token[1:].strip()
            if not name:
                break
            if name in self.bundle_by_name:
                bundle = self.bundle_by_name[name]
                bundle_ids.append(name)
                skill_ids.extend(bundle.skills)
                if bundle.instruction:
                    bundle_instructions.append(f"[{bundle.name}] {bundle.instruction}")
                consumed += 1
                continue
            if name in known_skills:
                skill_ids.append(name)
                consumed += 1
                continue
            diagnostics.append(f"未知 Skill 或 Bundle：/{name}")
            break

        if consumed == 0:
            return SkillActivation(cleaned_message=raw, diagnostics=tuple(diagnostics))

        cleaned = " ".join(tokens[consumed:]).strip()
        return SkillActivation(
            cleaned_message=cleaned or raw,
            skill_ids=tuple(dict.fromkeys(skill_ids)),
            bundle_ids=tuple(dict.fromkeys(bundle_ids)),
            bundle_instruction="\n".join(bundle_instructions).strip(),
            diagnostics=tuple(diagnostics),
        )

    def route(
        self,
        message: str,
        context: dict[str, Any] | None = None,
        allowed_tools: list[str] | None = None,
        default_skill_ids: list[str] | None = None,
        activated_skill_ids: list[str] | None = None,
        max_skills: int = 8,
    ) -> list[SkillRoute]:
        text = (message or "").lower()
        context = context or {}
        allowed = set(allowed_tools or [])
        route_map: dict[str, SkillRoute] = {}

        def add(
            skill_id: str,
            reason: str,
            score: int = 1,
            source: str = "fallback",
            trigger_type: str = "",
            matches: tuple[str, ...] = (),
        ) -> None:
            current = route_map.get(skill_id)
            if not current or score > current.score:
                route_map[skill_id] = SkillRoute(
                    skill_id=skill_id,
                    reason=reason,
                    score=score,
                    source=source,
                    trigger_type=trigger_type,
                    matches=matches,
                )

        for skill_id in default_skill_ids or []:
            add(str(skill_id), "profile/default", 10, source="profile", trigger_type="profile")

        for skill_id in activated_skill_ids or []:
            add(str(skill_id), "slash/activated", 20, source="slash", trigger_type="slash", matches=(str(skill_id),))

        for skill_id, keywords, context_keys, tool_names, source_path in self.package_rules + self.fallback_rules:
            source = "package" if source_path != "fallback" else "fallback"
            keyword_hits = [item for item in keywords if item.lower() in text]
            context_hits = [key for key in context_keys if context.get(key)]
            tool_hits = [tool for tool in tool_names if "*" in allowed or tool in allowed]
            if keyword_hits:
                add(
                    skill_id,
                    f"message:{','.join(keyword_hits[:3])}",
                    6 + len(keyword_hits),
                    source=source,
                    trigger_type="keyword",
                    matches=tuple(keyword_hits[:5]),
                )
            elif context_hits and tool_hits:
                add(
                    skill_id,
                    f"context:{','.join(context_hits[:3])}",
                    4 + len(context_hits),
                    source=source,
                    trigger_type="context_tool",
                    matches=tuple(context_hits[:5] + tool_hits[:5]),
                )
            elif tool_hits and any(item in text for item in ("做", "生成", "搜索", "检查", "推进", "整理")):
                add(
                    skill_id,
                    f"tool:{','.join(tool_hits[:3])}",
                    2,
                    source=source,
                    trigger_type="tool",
                    matches=tuple(tool_hits[:5]),
                )

        for tool in allowed:
            for skill_id in self.TOOL_SKILL_HINTS.get(tool, ()):
                add(skill_id, f"allowed_tool:{tool}", 1, source="tool_hint", trigger_type="tool_hint", matches=(tool,))

        return sorted(route_map.values(), key=lambda item: (-item.score, item.skill_id))[:max_skills]
