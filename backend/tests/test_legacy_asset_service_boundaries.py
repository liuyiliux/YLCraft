from pathlib import Path


DIRECT_IMPORT_PATTERNS = (
    "from app.services.asset.service import AssetService",
    "from app.services.asset import AssetService",
)

ALLOWED_DIRECT_IMPORTS: set[Path] = set()


def test_direct_asset_service_imports_stay_in_legacy_allowlist():
    """New feature writes should use AssetHubFacade instead of old AssetService."""

    app_dir = Path(__file__).resolve().parents[1] / "app"
    offenders: list[str] = []

    for path in app_dir.rglob("*.py"):
        relative = path.relative_to(app_dir.parent)
        text = path.read_text(encoding="utf-8")
        if any(pattern in text for pattern in DIRECT_IMPORT_PATTERNS):
            if relative not in ALLOWED_DIRECT_IMPORTS:
                offenders.append(relative.as_posix())

    assert offenders == []
