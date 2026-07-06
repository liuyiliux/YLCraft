"""Context assembly for the Agent runtime."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent import AgentRun
from app.services.agent.context_pack import build_creative_project_context_pack
from app.services.agent.runtime.skills import SkillRoute

logger = logging.getLogger("ylcraft.agent.runtime.context")


def safe_json_loads(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value) if value else fallback
    except (TypeError, json.JSONDecodeError):
        return fallback


def summarize_text(value: str, limit: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


class ContextAssembler:
    """Build the full per-turn context pack for AgentService."""

    def __init__(self, session: AsyncSession, creative_project_context_builder=build_creative_project_context_pack):
        self.session = session
        self.creative_project_context_builder = creative_project_context_builder

    def profile_context(self, profile: dict[str, Any]) -> dict[str, Any]:
        context: dict[str, Any] = {
            "agent_profile": {
                "id": profile.get("id"),
                "name": profile.get("name"),
                "role_type": profile.get("role_type"),
            }
        }
        default_project_id = str(profile.get("default_project_id") or "").strip()
        if default_project_id:
            context.setdefault("project_id", default_project_id)
            context.setdefault("creative_project_id", default_project_id)
            context["default_project_id"] = default_project_id
        default_workflow = str(profile.get("default_workflow") or "").strip()
        if default_workflow:
            context["default_workflow"] = default_workflow
        default_skill_ids = profile.get("default_skill_ids") or []
        if default_skill_ids:
            context["default_skill_ids"] = default_skill_ids
        return context

    def merge_context(
        self,
        session_context: dict[str, Any],
        profile: dict[str, Any],
        request_context: dict[str, Any],
    ) -> dict[str, Any]:
        effective_context = {
            **(session_context or {}),
            **(profile.get("default_context") or {}),
            **self.profile_context(profile),
            **(request_context or {}),
        }
        return self.augment_context(effective_context)

    def augment_context(self, context: dict[str, Any]) -> dict[str, Any]:
        project_id = str(context.get("project_id") or context.get("creative_project_id") or "").strip()
        if not project_id or context.get("creative_project_context"):
            return context
        try:
            chapter_number = context.get("chapter_number")
            pack = self.creative_project_context_builder(
                project_id,
                chapter_number=int(chapter_number) if chapter_number else None,
            )
            if pack:
                return {**context, "creative_project_context": pack}
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ContextAssembler] creative project context pack failed: %s", exc)
            return {**context, "creative_project_context_error": str(exc)}
        return context

    def build_project_context_summary(self, effective_context: dict[str, Any]) -> str:
        context_parts: list[str] = []
        creative_pack = effective_context.get("creative_project_context")
        if creative_pack and creative_pack.get("project"):
            project = creative_pack["project"]
            context_parts.append(
                f"当前创作项目：{project.get('title') or '未命名'} "
                f"({project.get('project_type') or 'unknown'})；"
                f"阶段：{project.get('current_stage') or '未标记'}；"
                f"共 {project.get('chapter_count') or 0} 章"
            )
            characters = creative_pack.get("characters") or []
            names = [item.get("name") for item in characters[:8] if item.get("name")]
            if names:
                context_parts.append(f"关联角色：{'、'.join(names)}")
            gaps = creative_pack.get("known_gaps") or []
            if gaps:
                context_parts.append(f"已知缺口：{'、'.join(gaps)}")
        if effective_context.get("continued_from_run_id"):
            context_parts.append("这是继续之前的智能体运行，请基于已完成的工作继续推进。")
        return "\n".join(context_parts)

    async def build_recent_run_context(self, session_id: str, current_run_id: str = "") -> list[dict[str, Any]]:
        if not session_id:
            return []
        try:
            result = await self.session.execute(
                select(AgentRun)
                .where(AgentRun.session_id == session_id, AgentRun.id != current_run_id)
                .order_by(AgentRun.created_at.desc())
                .limit(5)
            )
            runs = list(result.scalars().all())
        except SQLAlchemyError as exc:
            logger.warning("[ContextAssembler] recent run context skipped: %s", exc)
            return []
        items: list[dict[str, Any]] = []
        for run in runs:
            result_json = safe_json_loads(run.result_json or "{}", {})
            items.append(
                {
                    "run_id": run.id,
                    "status": run.status,
                    "objective": summarize_text(run.objective or "", limit=160),
                    "reply": summarize_text(str(result_json.get("reply") or ""), limit=240),
                    "tool_call_count": result_json.get("tool_call_count", 0),
                    "updated_at": run.updated_at.isoformat() if run.updated_at else "",
                }
            )
        return items

    def build_conversation_state(self, messages: list[dict[str, Any]], previous_state: Any = None) -> dict[str, Any]:
        prior = previous_state if isinstance(previous_state, dict) else {}
        user_messages = [
            str(message.get("content") or "").strip()
            for message in messages
            if message.get("role") == "user" and str(message.get("content") or "").strip()
        ]
        current = user_messages[-1] if user_messages else ""
        previous_slots = prior.get("slots") if isinstance(prior.get("slots"), dict) else {}
        platform = self.extract_platform(current) if current else None
        keyword = self.extract_search_keyword(current) if current else ""
        if platform and self.is_platform_refinement_without_keyword(current):
            keyword = ""
        if not keyword:
            keyword = str(previous_slots.get("keyword") or "").strip()
        if not keyword:
            for candidate in reversed(user_messages[:-1]):
                keyword = self.extract_search_keyword(candidate)
                if keyword:
                    break
        platform_value = str(previous_slots.get("platform") or "").strip()
        platform_label = str(previous_slots.get("platform_label") or "").strip()
        if platform:
            platform_value, platform_label = platform
        active_intent = str(prior.get("active_intent") or "").strip()
        if keyword or platform_value or re.search(r"(搜|搜索|找|查|检索|search)", current, flags=re.I):
            active_intent = "platform_search"
        slots: dict[str, Any] = {}
        if keyword:
            slots["keyword"] = keyword
        if platform_value:
            slots["platform"] = platform_value
            slots["platform_label"] = platform_label or platform_value
        missing_slots: list[str] = []
        if active_intent == "platform_search":
            if not slots.get("keyword"):
                missing_slots.append("keyword")
            if not slots.get("platform"):
                missing_slots.append("platform")
        pending_action = prior.get("pending_action") if isinstance(prior.get("pending_action"), dict) else {}
        if active_intent == "platform_search" and not missing_slots:
            pending_action = {
                "type": "tool_call_ready",
                "tool_name": "search_platform_sources",
                "arguments": {
                    "platform": slots["platform"],
                    "keyword": slots["keyword"],
                    "max_results": 20,
                },
            }
        elif missing_slots:
            pending_action = {"type": "await_user_slot", "missing_slots": missing_slots}
        return {
            "version": 1,
            "active_intent": active_intent,
            "intent_label": "平台内容搜索" if active_intent == "platform_search" else "",
            "slots": slots,
            "missing_slots": missing_slots,
            "pending_action": pending_action,
            "last_user_message": current,
            "updated_at": datetime.utcnow().isoformat(),
        }

    def build_followup_resolution(
        self,
        messages: list[dict[str, Any]],
        conversation_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        user_messages = [
            str(message.get("content") or "").strip()
            for message in messages
            if message.get("role") == "user" and str(message.get("content") or "").strip()
        ]
        if len(user_messages) < 2:
            return {}
        current = user_messages[-1]
        platform = self.extract_platform(current)
        if not platform:
            return {}
        slots = (conversation_state or {}).get("slots") if isinstance((conversation_state or {}).get("slots"), dict) else {}
        prior_keyword = str(slots.get("keyword") or "").strip()
        prior_message = ""
        if not prior_keyword:
            for candidate in reversed(user_messages[:-1]):
                keyword = self.extract_search_keyword(candidate)
                if keyword:
                    prior_keyword = keyword
                    prior_message = candidate
                    break
        if not prior_keyword:
            return {}
        if not self.is_platform_refinement_without_keyword(current):
            return {}
        platform_value, platform_label = platform
        return {
            "type": "platform_search_followup",
            "platform": platform_value,
            "platform_label": platform_label,
            "keyword": prior_keyword,
            "prior_message": prior_message,
            "current_message": current,
            "instruction": (
                f"上一轮用户的搜索目标是「{prior_keyword}」；本轮用户补充的平台/工具是「{platform_label}」。"
                f"请合并理解为：在 {platform_label} 搜索「{prior_keyword}」。不要再询问搜索关键词。"
            ),
        }

    def build_short_term_context_text(
        self,
        messages: list[dict[str, Any]],
        effective_context: dict[str, Any],
        conversation_state: dict[str, Any],
        recent_run_context: list[dict[str, Any]],
        routed_skills: list[SkillRoute] | None = None,
    ) -> str:
        recent_messages = [
            {
                "role": str(message.get("role") or "user"),
                "content": summarize_text(str(message.get("content") or ""), limit=320),
            }
            for message in messages[-10:]
            if message.get("role") in {"user", "assistant", "system"}
        ]
        context_keys = sorted(
            key for key, value in (effective_context or {}).items()
            if value not in (None, "", [], {})
        )
        compact_context = {
            key: effective_context[key]
            for key in context_keys
            if key in {
                "agent_profile",
                "default_workflow",
                "default_skill_ids",
                "routed_skill_ids",
                "activated_skill_ids",
                "activated_bundle_ids",
                "skill_bundle_instruction",
                "skill_activation_diagnostics",
                "project_id",
                "creative_project_id",
                "default_project_id",
                "conversation_state",
            }
        }
        payload = {
            "message_count": len(messages),
            "recent_messages": recent_messages,
            "session_context_keys": context_keys[:30],
            "session_context": compact_context,
            "conversation_state": conversation_state,
            "recent_runs": recent_run_context,
            "routed_skills": [
                {
                    "skill_id": item.skill_id,
                    "reason": item.reason,
                    "score": item.score,
                    "source": item.source,
                    "trigger_type": item.trigger_type,
                    "matches": list(item.matches),
                }
                for item in (routed_skills or [])
            ],
        }
        return (
            "以下是当前 thread 的完整短期上下文摘要，必须优先用于消解本轮省略、补充、确认、修正、继续等短句。\n"
            "如果用户本轮没有重复完整目标，请从 recent_messages、conversation_state、session_context、recent_runs 和 routed_skills 中继承。\n"
            f"{json.dumps(payload, ensure_ascii=False, default=str)}"
        )

    def extract_platform(self, text: str) -> tuple[str, str] | None:
        lowered = text.lower()
        aliases = [
            ("bili", "B站", ["b站", "b 站", "哔哩", "bilibili", "bili"]),
            ("xhs", "小红书", ["小红书", "xhs", "rednote"]),
            ("dy", "抖音", ["抖音", "douyin", "dy"]),
            ("ks", "快手", ["快手", "kuaishou", "ks"]),
            ("wb", "微博", ["微博", "weibo", "wb"]),
            ("zhihu", "知乎", ["知乎", "zhihu"]),
            ("wechat_mp", "公众号", ["公众号", "微信公号", "wechat"]),
        ]
        for value, label, terms in aliases:
            if any(term.lower() in lowered for term in terms):
                return value, label
        return None

    def is_platform_refinement_without_keyword(self, text: str) -> bool:
        compact = self.strip_platform_words(text)
        compact = re.sub(
            r"(有|用|走|调用|技能|工具|平台|搜索|搜|查|找|去|在|上|一下|可以|继续|就|吧|，|,|。|\s)+",
            "",
            compact,
            flags=re.I,
        )
        return len(compact) <= 2

    def strip_platform_words(self, text: str) -> str:
        result = text
        for term in [
            "B站", "b站", "b 站", "哔哩哔哩", "哔哩", "bilibili", "bili",
            "小红书", "xhs", "rednote", "抖音", "douyin", "dy", "快手", "kuaishou", "ks",
            "微博", "weibo", "wb", "知乎", "zhihu", "公众号", "微信公号", "wechat",
        ]:
            result = re.sub(re.escape(term), "", result, flags=re.I)
        return result

    def extract_search_keyword(self, text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""
        if not re.search(r"(搜|搜索|找|查|检索|search|视频|素材|解说)", raw, flags=re.I):
            return ""
        cleaned = self.strip_platform_words(raw)
        cleaned = re.sub(r"^(请|麻烦|帮我|帮忙|给我|我要|想要|去|在|从|用|到|帮)?\s*", "", cleaned)
        cleaned = re.sub(r"^(搜索|搜|找|查找|查|检索|search)\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"(帮我|帮忙|一下|看看|能不能|可以吗|吗|么|呢|吧)", "", cleaned)
        cleaned = cleaned.strip(" ：:，,。.!！?？\n\t")
        if not cleaned or len(cleaned) < 2:
            return ""
        return summarize_text(cleaned, limit=80)
