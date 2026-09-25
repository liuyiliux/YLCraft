"""End-to-end contract tests for local account sessions."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1 import auth
from app.core import user_auth
from app.core.resource_auth import principal_owner_user_id, require_owned_or_legacy
from app.core.external_api_auth import hash_external_key
from app.db.models.external_api_key import ExternalApiKey
from app.db.database import get_async_session_dependency
from app.db.models.user import User, UserSession


@pytest.fixture
def auth_client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}")
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: User.metadata.create_all(
                    sync_connection, tables=[User.__table__, UserSession.__table__]
                )
            )

    import asyncio

    asyncio.run(setup())
    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")

    async def session_override():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_async_session_dependency] = session_override
    with TestClient(app) as client:
        yield client, factory
    asyncio.run(engine.dispose())


def test_password_hash_never_round_trips_plaintext():
    password_hash = user_auth.hash_password("correct horse battery staple")
    assert password_hash != "correct horse battery staple"
    assert user_auth.verify_password("correct horse battery staple", password_hash)
    assert not user_auth.verify_password("wrong password", password_hash)


def test_owner_policy_allows_legacy_and_rejects_another_human_user():
    first = User(id="first", username="first_user", password_hash="hash")
    second = User(id="second", username="second_user", password_hash="hash")
    first_principal = user_auth.AuthenticatedPrincipal(user=first)

    assert principal_owner_user_id(first_principal) == "first"
    require_owned_or_legacy(owner_user_id=None, principal=first_principal)
    require_owned_or_legacy(owner_user_id="first", principal=first_principal)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        require_owned_or_legacy(
            owner_user_id=first.id,
            principal=user_auth.AuthenticatedPrincipal(user=second),
        )
    assert exc.value.status_code == 403


def test_register_login_logout_revokes_server_session(auth_client):
    client, factory = auth_client
    created = client.post("/auth/register", json={
        "username": "local_user", "password": "correct horse battery staple", "display_name": "Local User",
    })
    assert created.status_code == 201
    assert "password_hash" not in created.text

    login = client.post("/auth/login", json={
        "username": "local_user", "password": "correct horse battery staple",
    })
    assert login.status_code == 200
    assert user_auth.SESSION_COOKIE_NAME in login.headers["set-cookie"]
    assert client.get("/auth/me").status_code == 200

    logout = client.post("/auth/logout")
    assert logout.status_code == 200
    assert client.get("/auth/me").status_code == 401

    import asyncio

    async def session_is_revoked():
        async with factory() as session:
            rows = (await session.exec(select(UserSession))).all()
            return rows[0].is_revoked

    assert asyncio.run(session_is_revoked()) is True


def test_expired_session_is_not_a_current_user(auth_client):
    client, factory = auth_client
    password_hash = user_auth.hash_password("correct horse battery staple")
    token = user_auth.new_session_token()

    import asyncio

    async def seed_expired_session():
        async with factory() as session:
            user = User(username="expired_user", password_hash=password_hash)
            session.add(user)
            await session.flush()
            session.add(UserSession(
                user_id=user.id,
                token_hash=user_auth.hash_session_token(token),
                expires_at=user_auth.session_expiry() - timedelta(days=user_auth.SESSION_TTL_DAYS + 1),
            ))
            await session.commit()

    asyncio.run(seed_expired_session())
    client.cookies.set(user_auth.SESSION_COOKIE_NAME, token)
    assert client.get("/auth/me").status_code == 401


def test_login_failure_limit_is_keyed_by_username_and_ip(monkeypatch):
    user_auth._login_failures.clear()
    monkeypatch.setattr(user_auth, "_LOGIN_FAILURE_LIMIT", 2)
    username = "limited_user"
    ip_address = "127.0.0.1"
    user_auth.record_login_failure(username, ip_address, now=100)
    user_auth.record_login_failure(username, ip_address, now=101)
    assert user_auth.login_is_rate_limited(username, ip_address, now=102)
    assert not user_auth.login_is_rate_limited(username, "127.0.0.2", now=102)
    assert user_auth.login_rate_limit_retry_after(username, ip_address, now=102) == 898


@pytest.mark.asyncio
async def test_either_credential_dependency_accepts_human_or_agent_and_rejects_invalid_bearer(monkeypatch):
    user = User(username="session_user", password_hash="hash")
    key = ExternalApiKey(name="agent", key_hash=hash_external_key("ylk_valid"), key_prefix="ylk_val")

    class RequestWithCookies:
        cookies = {user_auth.SESSION_COOKIE_NAME: "session-token"}
        headers = {}

    async def session_user(_request, _session):
        return user

    async def no_external_key(_request, _session, *, require_key):
        return None

    monkeypatch.setattr(user_auth, "_get_current_user_from_request", session_user)
    monkeypatch.setattr(user_auth, "get_external_api_key_optional", no_external_key)
    principal = await user_auth.get_authenticated_principal_optional(RequestWithCookies(), object())
    assert principal and principal.kind == "user"

    async def external_key(_request, _session, *, require_key):
        return key

    monkeypatch.setattr(user_auth, "get_external_api_key_optional", external_key)
    principal = await user_auth.get_authenticated_principal_optional(RequestWithCookies(), object())
    assert principal and principal.kind == "external_api_key"

    async def invalid_key(_request, _session, *, require_key):
        raise HTTPException(status_code=401, detail="invalid")

    from fastapi import HTTPException

    monkeypatch.setattr(user_auth, "get_external_api_key_optional", invalid_key)
    with pytest.raises(HTTPException, match="invalid"):
        await user_auth.get_authenticated_principal_optional(RequestWithCookies(), object())
