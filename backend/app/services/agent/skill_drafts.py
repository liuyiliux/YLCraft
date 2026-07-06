"""Pending review flow for user-provided Agent skill packages."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models.agent import AgentRun, AgentRunStep, AgentSkill, AgentSkillDraft
from app.services.agent.skill_loader import SkillPackage, SkillPackageLoader
from app.services.agent.skill_templates import ensure_builtin_skills


class SkillDraftError(ValueError):
    def __init__(self, message: str, diagnostics: list[str] | None = None):
        super().__init__(message)
        self.diagnostics = diagnostics or [message]


class AgentSkillDraftService:
    MAX_SKILL_BYTES = 256 * 1024
    MAX_IMPORT_REDIRECTS = 5

    def __init__(self, session: AsyncSession, user_id: str = "default", loader: SkillPackageLoader | None = None):
        self.session = session
        self.user_id = user_id
        self.loader = loader or SkillPackageLoader()

    async def list_drafts(self, status: str = "pending") -> list[AgentSkillDraft]:
        query = select(AgentSkillDraft).where(AgentSkillDraft.user_id == self.user_id)
        if status and status != "all":
            query = query.where(AgentSkillDraft.status == status)
        query = query.order_by(AgentSkillDraft.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_draft(self, draft_id: int) -> AgentSkillDraft | None:
        result = await self.session.execute(
            select(AgentSkillDraft).where(
                AgentSkillDraft.id == draft_id,
                AgentSkillDraft.user_id == self.user_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_manual_draft(
        self,
        content: str,
        *,
        source_type: str = "manual",
        source_url: str = "",
        source_run_id: str = "",
        source_step_ids: list[int] | None = None,
    ) -> AgentSkillDraft:
        package = self._parse_or_raise(content, source_url or "SKILL.md")
        self._ensure_not_builtin_override(package)

        draft = AgentSkillDraft(
            user_id=self.user_id,
            name=package.name,
            title=package.title,
            description=package.description,
            skill_type=package.skill_type,
            content=content,
            metadata_json=json.dumps(self._metadata_for_package(package), ensure_ascii=False),
            source_type=source_type,
            source_url=source_url,
            source_run_id=source_run_id,
            source_step_ids_json=json.dumps(source_step_ids or [], ensure_ascii=False),
            status="pending",
            target_path=self._target_relative_path(package.name),
            checksum=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            diagnostics_json=json.dumps([], ensure_ascii=False),
        )
        self.session.add(draft)
        await self.session.flush()
        await self.session.refresh(draft)
        return draft

    async def import_url(self, url: str) -> AgentSkillDraft:
        candidate_urls = self._candidate_skill_urls(url)
        content: bytes | None = None
        fetched_url = candidate_urls[0]
        errors: list[str] = []
        for candidate_url in candidate_urls:
            try:
                content = await self._fetch_skill_markdown(candidate_url)
                fetched_url = candidate_url
                break
            except SkillDraftError as exc:
                errors.extend(exc.diagnostics)
            except httpx.HTTPError as exc:
                errors.append(f"{candidate_url}: {exc}")
        if content is None:
            raise SkillDraftError("Fetch skill URL failed", errors or ["No candidate URL could be fetched"])
        if len(content) > self.MAX_SKILL_BYTES:
            raise SkillDraftError(f"Skill markdown is too large: {len(content)} bytes")
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SkillDraftError("Skill markdown must be UTF-8 text") from exc
        return await self.create_manual_draft(text, source_type="url", source_url=fetched_url)

    async def _fetch_skill_markdown(self, url: str) -> bytes:
        current_url = url
        headers = {"Accept": "text/markdown,text/plain,*/*"}
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            for _ in range(self.MAX_IMPORT_REDIRECTS + 1):
                response = await client.get(current_url, headers=headers)
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise SkillDraftError("Skill URL redirect is missing Location header")
                    current_url = self._validate_url(urljoin(str(response.url), location))
                    continue
                response.raise_for_status()
                return response.content
        raise SkillDraftError("Skill URL has too many redirects")

    async def inspect_run_candidate(self, run_id: str) -> dict[str, Any]:
        run, steps = await self._load_run_with_steps(run_id)
        if run is None:
            raise SkillDraftError("Agent run not found")
        return self._analyze_run_candidate(run, steps)

    async def create_draft_from_run(self, run_id: str, name: str = "", title: str = "") -> AgentSkillDraft:
        run, steps = await self._load_run_with_steps(run_id)
        if run is None:
            raise SkillDraftError("Agent run not found")
        analysis = self._analyze_run_candidate(run, steps)
        if not analysis["eligible"]:
            raise SkillDraftError("Run is not a good skill candidate", analysis["reasons"])
        content = self._build_skill_markdown_from_run(run, steps, analysis, name=name, title=title)
        source_step_ids = [int(step.id) for step in steps if step.id is not None]
        return await self.create_manual_draft(
            content,
            source_type="agent_run",
            source_run_id=run.id,
            source_step_ids=source_step_ids,
        )

    async def approve(self, draft_id: int) -> AgentSkillDraft:
        draft = await self.get_draft(draft_id)
        if draft is None:
            raise SkillDraftError("Skill draft not found")
        if draft.status != "pending":
            raise SkillDraftError(f"Only pending drafts can be approved, current status={draft.status}")

        package = self._parse_or_raise(draft.content, draft.source_url or "SKILL.md")
        self._ensure_not_builtin_override(package)
        target = self._target_path(package.name)
        root = (self._skill_root() / "user").resolve()
        if not self._is_under(target, root):
            raise SkillDraftError("Resolved target path is outside user skill root")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(draft.content, encoding="utf-8", newline="\n")

        draft.status = "approved"
        draft.reviewed_at = datetime.utcnow()
        draft.updated_at = datetime.utcnow()
        draft.target_path = self._target_relative_path(package.name)
        draft.checksum = hashlib.sha256(draft.content.encode("utf-8")).hexdigest()
        draft.diagnostics_json = json.dumps([], ensure_ascii=False)
        await ensure_builtin_skills(self.session, self.user_id)
        await self._upsert_approved_skill(package)
        await self.session.flush()
        await self.session.refresh(draft)
        return draft

    async def reject(self, draft_id: int, reason: str = "") -> AgentSkillDraft:
        draft = await self.get_draft(draft_id)
        if draft is None:
            raise SkillDraftError("Skill draft not found")
        if draft.status != "pending":
            raise SkillDraftError(f"Only pending drafts can be rejected, current status={draft.status}")
        draft.status = "rejected"
        draft.reviewed_at = datetime.utcnow()
        draft.updated_at = datetime.utcnow()
        diagnostics = [reason.strip()] if reason.strip() else []
        draft.diagnostics_json = json.dumps(diagnostics, ensure_ascii=False)
        await self.session.flush()
        await self.session.refresh(draft)
        return draft

    async def _load_run_with_steps(self, run_id: str) -> tuple[AgentRun | None, list[AgentRunStep]]:
        run = await self.session.get(AgentRun, run_id)
        if run is None or run.user_id != self.user_id:
            return None, []
        result = await self.session.execute(
            select(AgentRunStep)
            .where(AgentRunStep.run_id == run_id)
            .order_by(AgentRunStep.order_index.asc(), AgentRunStep.id.asc())
        )
        return run, list(result.scalars().all())

    def _analyze_run_candidate(self, run: AgentRun, steps: list[AgentRunStep]) -> dict[str, Any]:
        tool_steps = [step for step in steps if step.step_type in {"tool_call", "confirm_tool_call"} and step.tool_name]
        successful_tools = [step for step in tool_steps if step.status == "completed" and not step.error]
        failed_tools = [step for step in tool_steps if step.status == "failed" or step.error]
        unique_tools = list(dict.fromkeys(step.tool_name for step in successful_tools if step.tool_name))
        verification_steps = [
            step for step in successful_tools
            if self._looks_like_verification_step(step)
        ]
        reasons: list[str] = []
        if run.status != "completed":
            reasons.append("run status is not completed")
        if len(successful_tools) < 3:
            reasons.append("fewer than 3 successful tool steps")
        if len(unique_tools) < 2:
            reasons.append("fewer than 2 distinct successful tools")
        if not str(run.objective or "").strip():
            reasons.append("missing run objective")
        eligible = not reasons
        return {
            "eligible": eligible,
            "reasons": reasons,
            "tool_step_count": len(tool_steps),
            "successful_tool_count": len(successful_tools),
            "failed_tool_count": len(failed_tools),
            "unique_tools": unique_tools,
            "verification_step_ids": [step.id for step in verification_steps if step.id is not None],
            "score": min(100, len(successful_tools) * 15 + len(unique_tools) * 10 + len(verification_steps) * 10),
        }

    @staticmethod
    def _looks_like_verification_step(step: AgentRunStep) -> bool:
        blob = " ".join(
            [
                step.tool_name or "",
                step.summary or "",
                step.output_json or "",
            ]
        ).lower()
        return any(token in blob for token in ("test", "verify", "preview", "inspect", "list_", "get_", "校验", "验证", "检查", "预览"))

    def _build_skill_markdown_from_run(
        self,
        run: AgentRun,
        steps: list[AgentRunStep],
        analysis: dict[str, Any],
        *,
        name: str = "",
        title: str = "",
    ) -> str:
        skill_name = self._safe_name(name or self._name_from_run(run, analysis))
        skill_title = (title or self._title_from_run(run)).strip()[:120]
        objective = str(run.objective or "").strip()
        context = self._json_loads(run.context_json, {})
        successful_tools = [
            step for step in steps
            if step.step_type in {"tool_call", "confirm_tool_call"} and step.status == "completed" and step.tool_name
        ]
        failed_tools = [
            step for step in steps
            if step.step_type in {"tool_call", "confirm_tool_call"} and (step.status == "failed" or step.error)
        ]
        keywords = self._keywords_from_text(objective)
        if not keywords:
            keywords = [skill_title]
        requires_tools = analysis.get("unique_tools") or []
        category = self._category_from_tools(requires_tools)
        trigger_block = "\n".join(f"    - {self._yaml_quote(item)}" for item in keywords[:8])
        tool_block = "\n".join(f"  - {self._yaml_quote(item)}" for item in requires_tools[:20])
        context_keys = [key for key, value in context.items() if value not in (None, "", [], {})]
        context_key_block = "\n".join(f"    - {self._yaml_quote(item)}" for item in context_keys[:10])
        step_lines = []
        for index, step in enumerate(successful_tools, start=1):
            args = self._json_loads(step.input_json, {})
            summary = (step.summary or step.tool_name or "").strip()
            arg_keys = sorted((args.get("arguments") or args or {}).keys()) if isinstance(args, dict) else []
            suffix = f" 参数: {', '.join(arg_keys[:8])}" if arg_keys else ""
            step_lines.append(f"{index}. 调用 `{step.tool_name}`。{summary}{suffix}")
        failure_lines = [
            f"- `{step.tool_name}`: {self._truncate(step.error or step.summary or 'failed', 180)}"
            for step in failed_tools[:8]
        ]
        verification_lines = [
            f"- `{step.tool_name}`: {self._truncate(step.summary or 'completed', 180)}"
            for step in successful_tools
            if step.id in set(analysis.get("verification_step_ids") or [])
        ]
        if not verification_lines:
            verification_lines = ["- 确认关键工具返回 `success=true` 或 run 状态为 completed。"]
        frontmatter = [
            "---",
            f"name: {self._yaml_quote(skill_name)}",
            f"title: {self._yaml_quote(skill_title)}",
            f"description: {self._yaml_quote('从成功 Agent run 自动沉淀的可复用工作流。')}",
            "skill_type: workflow",
            "version: 0.1.0",
            f"category: {self._yaml_quote(category)}",
            "tags:",
            "  - agent-run",
            "  - auto-draft",
            "triggers:",
            "  keywords:",
            trigger_block or "    - 自动沉淀",
        ]
        if context_key_block:
            frontmatter.extend(["  context_keys:", context_key_block])
        frontmatter.extend(
            [
                "requires_tools:",
                tool_block or "  []",
                "risk: write",
                "---",
                "",
            ]
        )
        body = [
            f"# {skill_title}",
            "",
            "## When To Use",
            "",
            f"- 用户目标接近：{objective or skill_title}",
            "- 需要复用一次已验证的多工具执行链路，而不是从零探索。",
            "",
            "## Workflow",
            "",
            *step_lines,
            "",
            "## Verification",
            "",
            *verification_lines,
            "",
            "## Failure Notes",
            "",
            *(failure_lines or ["- 本次 run 没有记录失败工具步骤。"]),
            "",
            "## Provenance",
            "",
            f"- source_run_id: `{run.id}`",
            f"- profile_id: `{run.profile_id}`",
            f"- successful_tool_count: {analysis.get('successful_tool_count', 0)}",
            f"- distinct_tools: {', '.join(requires_tools)}",
        ]
        return "\n".join(frontmatter + body).strip() + "\n"

    def _parse_or_raise(self, content: str, source_path: str) -> SkillPackage:
        if not content or not content.strip():
            raise SkillDraftError("Skill markdown is empty")
        raw = content.encode("utf-8")
        if len(raw) > self.MAX_SKILL_BYTES:
            raise SkillDraftError(f"Skill markdown is too large: {len(raw)} bytes")
        package, diagnostics = self.loader.validate_raw_package(content, source_path)
        if package is None:
            raise SkillDraftError("Invalid SKILL.md metadata", list(diagnostics))
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{1,99}", package.name):
            raise SkillDraftError("Skill name must use 2-100 ASCII letters, numbers, hyphen or underscore")
        return package

    @staticmethod
    def _json_loads(raw: str | None, default: Any) -> Any:
        try:
            return json.loads(raw or "")
        except Exception:
            return default

    @classmethod
    def _name_from_run(cls, run: AgentRun, analysis: dict[str, Any]) -> str:
        tools = analysis.get("unique_tools") or []
        base = "_".join(str(tool).replace("_tool", "") for tool in tools[:3]) or run.objective or run.id
        safe = cls._safe_name(base)
        suffix = str(run.id or "")[-8:].lower()
        if suffix and suffix not in safe:
            safe = f"{safe}_{suffix}"
        return safe[:100]

    @staticmethod
    def _title_from_run(run: AgentRun) -> str:
        objective = str(run.objective or "").strip()
        if objective:
            return objective[:80]
        return f"Agent Run {run.id} Workflow"

    @staticmethod
    def _keywords_from_text(text: str) -> list[str]:
        cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
        if not cleaned:
            return []
        keywords = [cleaned[:40]]
        tokens = re.findall(r"[\u4e00-\u9fff]{2,8}|[a-zA-Z][a-zA-Z0-9_-]{2,30}", cleaned)
        for token in tokens:
            if token not in keywords:
                keywords.append(token)
            if len(keywords) >= 8:
                break
        return keywords

    @staticmethod
    def _category_from_tools(tools: list[str]) -> str:
        joined = " ".join(tools)
        if "character" in joined or "portrait" in joined:
            return "creative"
        if "novel" in joined or "writer" in joined:
            return "novel"
        if "image" in joined or "video" in joined:
            return "generation"
        if "download" in joined or "wechat" in joined or "platform" in joined:
            return "collection"
        if "connector" in joined or "provider" in joined:
            return "ai-config"
        return "agent-run"

    @staticmethod
    def _yaml_quote(value: Any) -> str:
        text = str(value or "")
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    @staticmethod
    def _truncate(value: str, limit: int) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        return text[:limit] + ("..." if len(text) > limit else "")

    def _ensure_not_builtin_override(self, package: SkillPackage) -> None:
        existing = self.loader.get_package(package.name)
        if existing and existing.source_type != "user":
            raise SkillDraftError(f"Cannot override built-in skill package: {package.name}")

    @staticmethod
    def _metadata_for_package(package: SkillPackage) -> dict[str, Any]:
        return {
            "name": package.name,
            "title": package.title,
            "description": package.description,
            "skill_type": package.skill_type,
            "version": package.version,
            "category": package.category,
            "tags": list(package.tags),
            "triggers": {key: list(value) for key, value in package.triggers.items()},
            "requires_tools": list(package.requires_tools),
            "risk": package.risk,
        }

    def _target_path(self, name: str) -> Path:
        safe_name = self._safe_name(name)
        return (self._skill_root() / "user" / safe_name / SkillPackageLoader.SKILL_FILENAME).resolve()

    def _target_relative_path(self, name: str) -> str:
        target = self._target_path(name)
        return SkillPackageLoader._relative_source_path(target)

    def _skill_root(self) -> Path:
        return self.loader.roots[0] if self.loader.roots else self.loader.default_builtin_root()

    async def _upsert_approved_skill(self, package: SkillPackage) -> None:
        result = await self.session.execute(
            select(AgentSkill).where(
                AgentSkill.user_id == self.user_id,
                AgentSkill.name == package.name,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.description = package.description
            existing.skill_type = package.skill_type
            existing.content = package.content
            existing.is_builtin = False
            existing.updated_at = datetime.utcnow()
            return
        self.session.add(
            AgentSkill(
                user_id=self.user_id,
                name=package.name,
                description=package.description,
                skill_type=package.skill_type,
                content=package.content,
                is_builtin=False,
            )
        )

    @staticmethod
    def _safe_name(name: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-_").lower()
        if not safe:
            raise SkillDraftError("Skill name cannot resolve to an empty path")
        return safe[:100]

    @staticmethod
    def _is_under(path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            return False

    @staticmethod
    def _validate_url(url: str) -> str:
        normalized = str(url or "").strip()
        normalized = AgentSkillDraftService._normalize_skill_url(normalized)
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise SkillDraftError("Skill URL must be http(s)")
        host = (parsed.hostname or "").lower()
        if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
            raise SkillDraftError("Local skill URLs are not allowed")
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return normalized
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
            raise SkillDraftError("Private network skill URLs are not allowed")
        return normalized

    @staticmethod
    def _normalize_skill_url(url: str) -> str:
        parsed = urlparse(url)
        if parsed.netloc.lower() == "github.com" and "/blob/" in parsed.path:
            parts = parsed.path.strip("/").split("/")
            if len(parts) >= 5:
                owner, repo = parts[0], parts[1]
                branch = parts[3]
                rest = "/".join(parts[4:])
                return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{rest}"
        return url

    @classmethod
    def _candidate_skill_urls(cls, url: str) -> list[str]:
        normalized = str(url or "").strip()
        parsed = urlparse(normalized)
        candidates: list[str] = []
        if parsed.netloc.lower() == "github.com":
            parts = parsed.path.strip("/").split("/")
            if len(parts) >= 2:
                owner, repo = parts[0], parts[1]
                if "/blob/" in parsed.path:
                    candidates.append(cls._normalize_skill_url(normalized))
                elif len(parts) >= 4 and parts[2] == "tree":
                    branch = parts[3]
                    rest = "/".join(parts[4:])
                    base = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}"
                    candidates.append(f"{base}/{rest}/SKILL.md" if rest else f"{base}/SKILL.md")
                elif len(parts) == 2:
                    for branch in ("main", "master"):
                        base = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}"
                        candidates.extend(
                            [
                                f"{base}/SKILL.md",
                                f"{base}/skills/{repo}/SKILL.md",
                            ]
                        )
        candidates.append(cls._normalize_skill_url(normalized))
        seen: set[str] = set()
        validated: list[str] = []
        for candidate in candidates:
            try:
                safe_url = cls._validate_url(candidate)
            except SkillDraftError:
                continue
            if safe_url not in seen:
                seen.add(safe_url)
                validated.append(safe_url)
        if not validated:
            raise SkillDraftError("Skill URL must be http(s)")
        return validated
