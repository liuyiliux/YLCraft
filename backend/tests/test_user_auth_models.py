"""Focused contract tests for the authentication data-model migration slice."""

from app.db.models import User, UserSession
from app.db.models.asset_hub import AssetNode
from app.db.models.creative_project import CreativeProject
from app.db.models.task import Model3DGenerationTask, ProjectTaskRecord, VideoGenerationTask


def test_account_models_register_expected_tables_and_constraints():
    assert User.__tablename__ == "users"
    assert UserSession.__tablename__ == "user_sessions"
    assert User.__table__.c.username.unique is True
    assert User.__table__.c.email.nullable is True
    assert UserSession.__table__.c.token_hash.unique is True
    assert UserSession.__table__.c.user_id.foreign_keys


def test_account_model_timestamps_match_naive_postgres_columns():
    user = User(username="timestamp_user", password_hash="hash")
    session = UserSession(
        user_id=user.id,
        token_hash="a" * 64,
        expires_at=user.created_at,
    )
    assert user.created_at.tzinfo is None
    assert user.updated_at.tzinfo is None
    assert session.created_at.tzinfo is None
    assert session.updated_at.tzinfo is None


def test_ownership_fields_are_nullable_and_reference_users():
    for model in (
        CreativeProject,
        AssetNode,
        ProjectTaskRecord,
        VideoGenerationTask,
        Model3DGenerationTask,
    ):
        column = model.__table__.c.owner_user_id
        assert column.nullable is True
        assert {foreign_key.target_fullname for foreign_key in column.foreign_keys} == {"users.id"}
