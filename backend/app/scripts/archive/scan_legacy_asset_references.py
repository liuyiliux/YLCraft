"""Scan runtime code for old asset table/model references before final deletion.

Usage:
    python -m app.scripts.archive.scan_legacy_asset_references
    python -m app.scripts.archive.scan_legacy_asset_references --fail-on-found

This command is read-only. It helps decide whether old `assets` tables and
legacy AssetService can be safely removed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parents[3]
APP_DIR = ROOT / "app"

EXCLUDED_PARTS = {
    "__pycache__",
}

EXCLUDED_PREFIXES = (
    Path("app/scripts/archive"),
    Path("app/scripts/migrate_legacy_assets_to_hub.py"),
    Path("app/scripts/audit_legacy_assets_archive.py"),
)

PATTERNS = {
    "legacy_model_import": re.compile(r"from\s+app\.db\.models\.asset\s+import\s+.*\bAsset\b"),
    "legacy_service_import": re.compile(r"from\s+app\.services\.asset(?:\.service)?\s+import\s+AssetService"),
    "raw_assets_sql": re.compile(r"\b(FROM|JOIN|UPDATE|INSERT\s+INTO|ALTER\s+TABLE|DROP\s+TABLE)\s+assets\b", re.IGNORECASE),
    "asset_service_symbol": re.compile(r"\bAssetService\b"),
}


def _is_excluded(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return True
    return any(relative == prefix or prefix in relative.parents for prefix in EXCLUDED_PREFIXES)


def _scan_file(path: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    text = path.read_text(encoding="utf-8", errors="ignore")
    for line_number, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in PATTERNS.items():
            if pattern.search(line):
                findings.append(
                    {
                        "kind": kind,
                        "file": str(path.relative_to(ROOT)).replace("\\", "/"),
                        "line": line_number,
                        "text": line.strip()[:220],
                    }
                )
    return findings


def scan() -> dict[str, object]:
    findings: list[dict[str, object]] = []
    for path in APP_DIR.rglob("*.py"):
        if _is_excluded(path):
            continue
        findings.extend(_scan_file(path))

    by_file: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for item in findings:
        by_file[str(item["file"])] = by_file.get(str(item["file"]), 0) + 1
        by_kind[str(item["kind"])] = by_kind.get(str(item["kind"]), 0) + 1

    return {
        "success": True,
        "safe_to_drop": len(findings) == 0,
        "finding_count": len(findings),
        "by_kind": by_kind,
        "by_file": by_file,
        "findings": findings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan for legacy asset runtime references.")
    parser.add_argument("--fail-on-found", action="store_true", help="Exit 1 when references are found.")
    args = parser.parse_args()

    result = scan()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.fail_on_found and not result["safe_to_drop"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
