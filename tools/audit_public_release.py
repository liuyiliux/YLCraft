#!/usr/bin/env python3
"""Fail closed on common accidental-publication risks without printing secrets."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from collections.abc import Iterable


FORBIDDEN_TRACKED_PATHS = (
    re.compile(r"(^|/)\.env($|\.)", re.IGNORECASE),
    re.compile(r"^(backend/)?(storage|downloads|backups)/", re.IGNORECASE),
    re.compile(r"(^|/)(?:data|config|export|backup|local)/(?:cookies?|credentials?|secrets?)/", re.IGNORECASE),
    re.compile(r"(^|/).+\.(sqlite3?|db|dump|bak|p12|pfx|pem|jks|keystore)$", re.IGNORECASE),
    re.compile(r"(^|/).+\.(stdout|stderr)?\.log$", re.IGNORECASE),
)

ALLOWED_ENV_TEMPLATES = {".env.example", "backend/.env.example"}

# Patterns target credential-shaped values rather than ordinary configuration names.
CONTENT_RULES = {
    "api-key-like-token": r"(?<![A-Za-z0-9])(?:sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{30,}|gh[pousr]_[A-Za-z0-9_]{30,}|xox[baprs]-[A-Za-z0-9-]{20,})",
    "signed-object-url": r"X-Amz-(?:Security-Token|Signature)=",
    "cookie-session-value": r"(?:sessionid|sid_tt|passport_auth_status)=[A-Za-z0-9_%.-]{16,}",
    "platform-cookie-value": r"(?:_csrfToken|ywkey|ywopenid|SESSDATA|bili_jct)=[A-Za-z0-9_%.-]{16,}",
}

# Git's -G uses a POSIX-oriented regex engine and does not support lookbehind.
HISTORY_CONTENT_RULES = {
    "signed-object-url": r"X-Amz-Security-Token=|X-Amz-Signature=",
    "cookie-session-value": r"sessionid=[A-Za-z0-9_%.-]{16,}|sid_tt=[A-Za-z0-9_%.-]{16,}|passport_auth_status=[A-Za-z0-9_%.-]{16,}",
    "platform-cookie-value": r"_csrfToken=[A-Za-z0-9_%.-]{16,}|ywkey=[A-Za-z0-9_%.-]{16,}|ywopenid=[A-Za-z0-9_%.-]{16,}|SESSDATA=[A-Za-z0-9_%.-]{16,}|bili_jct=[A-Za-z0-9_%.-]{16,}",
}


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
        encoding="utf-8",
        errors="replace",
    )


def tracked_paths() -> list[str]:
    return [line for line in run_git("ls-files").stdout.splitlines() if line]


def forbidden_paths(paths: Iterable[str]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        if path in ALLOWED_ENV_TEMPLATES:
            continue
        if not Path(path).exists():
            continue
        if any(pattern.search(path) for pattern in FORBIDDEN_TRACKED_PATHS):
            findings.append(path)
    return findings


def current_content_findings() -> list[str]:
    findings: list[str] = []
    for name, pattern in CONTENT_RULES.items():
        compiled = re.compile(pattern)
        for path in tracked_paths():
            if path == "tools/audit_public_release.py":
                continue
            file_path = Path(path)
            if not file_path.is_file() or file_path.stat().st_size > 10_000_000:
                continue
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            # Public docs and tests may show conventional placeholders such as
            # sk-xxxx. Remove those before checking credential-shaped values.
            sanitized = re.sub(r"(?:sk-|Bearer\s+)[xX<][A-Za-z0-9_<>-]*", "", content)
            if compiled.search(sanitized):
                findings.append(f"{name}: {path}")
    return findings


def history_findings() -> list[str]:
    findings: list[str] = []
    for name, history_pattern in HISTORY_CONTENT_RULES.items():
        result = run_git("log", "--all", "--no-textconv", "--format=%H", "-G", history_pattern, check=False)
        if result.returncode not in (0, 1):
            raise RuntimeError(result.stderr.strip() or f"git log failed for {name}")
        for commit in sorted(set(filter(None, result.stdout.splitlines()))):
            findings.append(f"{name}: history commit {commit[:12]}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit tracked files before open-source publication.")
    parser.add_argument("--history", action="store_true", help="also inspect all reachable Git history")
    args = parser.parse_args()

    findings = [f"forbidden tracked path: {path}" for path in forbidden_paths(tracked_paths())]
    findings.extend(current_content_findings())
    if args.history:
        findings.extend(history_findings())

    if findings:
        print("Public release audit failed. Findings are paths/rules only:")
        for finding in findings:
            print(f"- {finding}")
        return 1

    print("Public release audit passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
