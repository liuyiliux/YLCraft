"""File-backed Agent Skill package loader.

YLCraft's project tools define what an agent can do. Skill packages define how
the agent should combine those tools for recurring workflows.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("ylcraft.agent.skills")


@dataclass(frozen=True)
class SkillPackage:
    name: str
    description: str
    skill_type: str
    content: str
    title: str = ""
    version: str = "1.0.0"
    category: str = "general"
    tags: tuple[str, ...] = ()
    triggers: dict[str, tuple[str, ...]] = field(default_factory=dict)
    requires_tools: tuple[str, ...] = ()
    risk: str = "read"
    source_type: str = "builtin"
    source_path: str = ""
    checksum: str = ""
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillBundle:
    name: str
    description: str
    skills: tuple[str, ...]
    instruction: str = ""
    source_path: str = ""
    diagnostics: tuple[str, ...] = ()


class SkillPackageLoader:
    """Load `SKILL.md` packages from configured roots."""

    SKILL_FILENAME = "SKILL.md"
    BUNDLE_GLOB = "bundles/*.yaml"

    def __init__(self, roots: list[Path] | None = None):
        self.roots = roots or [self.default_builtin_root()]

    @staticmethod
    def default_builtin_root() -> Path:
        return Path(__file__).resolve().parents[2] / "skills"

    def load_packages(self) -> list[SkillPackage]:
        packages: list[SkillPackage] = []
        for root in self.roots:
            if not root.exists():
                continue
            for path in sorted(root.rglob(self.SKILL_FILENAME)):
                package = self.load_package(path)
                if package is not None:
                    packages.append(package)
        return packages

    def load_package(self, path: Path) -> SkillPackage | None:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("[SkillPackageLoader] failed reading %s: %s", path, exc)
            return None

        return self.parse_raw_package(raw, source_path=path)

    def parse_raw_package(self, raw: str, source_path: Path | str) -> SkillPackage | None:
        path = Path(source_path)
        metadata, body = self._split_frontmatter(raw)
        diagnostics = self._validate_metadata(path, metadata)
        if diagnostics:
            for message in diagnostics:
                logger.warning("[SkillPackageLoader] %s", message)
            return None

        triggers = metadata.get("triggers") or {}
        normalized_triggers = {
            "keywords": self._as_str_tuple(triggers.get("keywords")),
            "context_keys": self._as_str_tuple(triggers.get("context_keys")),
            "tools": self._as_str_tuple(triggers.get("tools")),
        }
        checksum = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return SkillPackage(
            name=str(metadata["name"]).strip(),
            title=str(metadata.get("title") or metadata["name"]).strip(),
            description=str(metadata["description"]).strip(),
            skill_type=str(metadata["skill_type"]).strip(),
            content=body.strip(),
            version=str(metadata.get("version") or "1.0.0").strip(),
            category=str(metadata.get("category") or "general").strip(),
            tags=self._as_str_tuple(metadata.get("tags")),
            triggers=normalized_triggers,
            requires_tools=self._as_str_tuple(metadata.get("requires_tools")),
            risk=str(metadata.get("risk") or "read").strip(),
            source_type=self._source_type_for_path(path),
            source_path=self._relative_source_path(path),
            checksum=checksum,
        )

    def validate_raw_package(self, raw: str, source_path: Path | str = "SKILL.md") -> tuple[SkillPackage | None, tuple[str, ...]]:
        path = Path(source_path)
        try:
            metadata, _body = self._split_frontmatter(raw)
        except Exception as exc:
            return None, (f"{path} frontmatter parse failed: {exc}",)
        diagnostics = self._validate_metadata(path, metadata)
        if diagnostics:
            return None, diagnostics
        package = self.parse_raw_package(raw, path)
        if package is None:
            return None, (f"{path} could not be parsed as a skill package",)
        return package, ()

    def package_index(self) -> list[dict[str, Any]]:
        return [
            {
                "name": item.name,
                "title": item.title,
                "description": item.description,
                "skill_type": item.skill_type,
                "version": item.version,
                "category": item.category,
                "tags": list(item.tags),
                "triggers": {key: list(value) for key, value in item.triggers.items()},
                "requires_tools": list(item.requires_tools),
                "risk": item.risk,
                "source_type": item.source_type,
                "source_path": item.source_path,
                "checksum": item.checksum,
            }
            for item in self.load_packages()
        ]

    def get_package(self, name: str) -> SkillPackage | None:
        normalized = str(name or "").strip()
        if not normalized:
            return None
        for item in self.load_packages():
            if item.name == normalized:
                return item
        return None

    def package_files(self, name: str) -> list[dict[str, Any]]:
        package_dir = self._package_dir_for_name(name)
        if package_dir is None:
            return []

        files: list[dict[str, Any]] = []
        for path in sorted(package_dir.rglob("*")):
            if not path.is_file() or not self._is_allowed_package_file(package_dir, path):
                continue
            rel_path = path.relative_to(package_dir).as_posix()
            try:
                stat = path.stat()
            except OSError:
                continue
            files.append(
                {
                    "path": rel_path,
                    "size": stat.st_size,
                    "kind": self._package_file_kind(rel_path),
                }
            )
        return files

    def read_package_file(self, name: str, relative_path: str) -> dict[str, Any] | None:
        package_dir = self._package_dir_for_name(name)
        if package_dir is None:
            return None

        requested = str(relative_path or "").strip().replace("\\", "/")
        if not requested:
            requested = self.SKILL_FILENAME
        path = (package_dir / requested).resolve()
        if not self._is_allowed_package_file(package_dir, path) or not path.is_file():
            return None
        try:
            content = path.read_text(encoding="utf-8")
            stat = path.stat()
        except OSError:
            return None
        rel_path = path.relative_to(package_dir).as_posix()
        return {
            "path": rel_path,
            "kind": self._package_file_kind(rel_path),
            "size": stat.st_size,
            "content": content,
        }

    def load_bundles(self) -> list[SkillBundle]:
        bundles: list[SkillBundle] = []
        for root in self.roots:
            if not root.exists():
                continue
            bundle_paths = [*root.glob(self.BUNDLE_GLOB), *root.glob("user/bundles/*.yaml")]
            for path in sorted(bundle_paths):
                bundle = self.load_bundle(path)
                if bundle is not None:
                    bundles.append(bundle)
        return bundles

    def load_bundle(self, path: Path) -> SkillBundle | None:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("[SkillPackageLoader] failed reading bundle %s: %s", path, exc)
            return None
        loaded = yaml.safe_load(raw) or {}
        if not isinstance(loaded, dict):
            logger.warning("[SkillPackageLoader] %s bundle must be a YAML object", path)
            return None
        missing = [field for field in ("name", "description", "skills") if not loaded.get(field)]
        if missing:
            logger.warning("[SkillPackageLoader] %s missing bundle fields: %s", path, ", ".join(missing))
            return None
        skills = self._as_str_tuple(loaded.get("skills"))
        if not skills:
            logger.warning("[SkillPackageLoader] %s bundle has no valid skills", path)
            return None
        return SkillBundle(
            name=str(loaded["name"]).strip(),
            description=str(loaded["description"]).strip(),
            skills=skills,
            instruction=str(loaded.get("instruction") or "").strip(),
            source_path=self._relative_source_path(path),
        )

    def bundle_index(self) -> list[dict[str, Any]]:
        return [
            {
                "name": item.name,
                "description": item.description,
                "skills": list(item.skills),
                "instruction": item.instruction,
                "source_path": item.source_path,
            }
            for item in self.load_bundles()
        ]

    def route_rules(self) -> list[tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...], str]]:
        rules: list[tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...], str]] = []
        for item in self.load_packages():
            rules.append(
                (
                    item.name,
                    item.triggers.get("keywords", ()),
                    item.triggers.get("context_keys", ()),
                    item.triggers.get("tools", ()),
                    item.source_path,
                )
            )
        return rules

    def _package_dir_for_name(self, name: str) -> Path | None:
        package = self.get_package(name)
        if package is None:
            return None
        for root in self.roots:
            if not root.exists():
                continue
            for path in root.rglob(self.SKILL_FILENAME):
                loaded = self.load_package(path)
                if loaded and loaded.name == package.name:
                    return path.parent.resolve()
        return None

    @classmethod
    def _split_frontmatter(cls, raw: str) -> tuple[dict[str, Any], str]:
        text = raw.lstrip("\ufeff")
        if not text.startswith("---"):
            return {}, raw
        lines = text.splitlines()
        end_index = None
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                end_index = index
                break
        if end_index is None:
            return {}, raw
        yaml_text = "\n".join(lines[1:end_index])
        body = "\n".join(lines[end_index + 1 :])
        loaded = yaml.safe_load(yaml_text) or {}
        return loaded if isinstance(loaded, dict) else {}, body

    @staticmethod
    def _validate_metadata(path: Path, metadata: dict[str, Any]) -> tuple[str, ...]:
        missing = [field for field in ("name", "description", "skill_type") if not str(metadata.get(field) or "").strip()]
        if missing:
            return (f"{path} missing required metadata: {', '.join(missing)}",)
        return ()

    @staticmethod
    def _as_str_tuple(value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return (value.strip(),) if value.strip() else ()
        if isinstance(value, (list, tuple, set)):
            return tuple(str(item).strip() for item in value if str(item or "").strip())
        return ()

    @classmethod
    def _relative_source_path(cls, path: Path) -> str:
        try:
            return str(path.relative_to(Path(__file__).resolve().parents[3])).replace("\\", "/")
        except ValueError:
            return str(path).replace("\\", "/")

    @classmethod
    def _is_allowed_package_file(cls, package_dir: Path, path: Path) -> bool:
        try:
            rel_path = path.resolve().relative_to(package_dir.resolve()).as_posix()
        except ValueError:
            return False
        if rel_path == cls.SKILL_FILENAME:
            return True
        return rel_path.startswith("references/") or rel_path.startswith("templates/")

    @staticmethod
    def _package_file_kind(relative_path: str) -> str:
        if relative_path == SkillPackageLoader.SKILL_FILENAME:
            return "skill"
        if relative_path.startswith("references/"):
            return "reference"
        if relative_path.startswith("templates/"):
            return "template"
        return "file"

    @staticmethod
    def _source_type_for_path(path: Path) -> str:
        normalized = str(path).replace("\\", "/")
        return "user" if "/skills/user/" in normalized or normalized.startswith("skills/user/") else "builtin"
