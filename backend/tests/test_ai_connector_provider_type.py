from app.services.ai_connector.service import normalize_provider_type
from app.db.models.ai_connector import AIConnector, normalize_ai_connector_provider_type


def test_normalize_legacy_3d_provider_type():
    assert normalize_provider_type("model3d") == "3d"


def test_normalize_current_3d_provider_type():
    assert normalize_provider_type("3d") == "3d"


def test_normalize_all_legacy_3d_aliases_to_the_single_canonical_value():
    assert {
        normalize_provider_type(value)
        for value in ("model3d", "model_3d", "image_to_3d", "image-to-3d", "3d")
    } == {"3d"}


def test_orm_normalizes_legacy_3d_provider_type_before_insert():
    connector = AIConnector(
        id="legacy-3d-type-test",
        provider="generic",
        name="Legacy 3D connector",
        provider_type="model3d",
    )

    normalize_ai_connector_provider_type(None, None, connector)

    assert connector.provider_type == "3d"


def test_orm_uses_canonical_3d_value_instead_of_python_enum_member_name():
    connector = AIConnector(
        id="canonical-3d-type-test",
        provider="generic",
        name="Canonical 3D connector",
        provider_type="3d",
    )

    assert connector.provider_type == "3d"
