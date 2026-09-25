"""Password, server-session, and caller-principal helpers.

Human browser sessions and external Agent keys are intentionally separate
credentials.  Callers that accept both use ``get_authenticated_principal`` so
they share one explicit "either credential" decision.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Request
from sqlmodel import select

from app.core.external_api_auth import get_external_api_key_optional
from app.db.database import get_async_session_dependency
from app.db.models.external_api_key import ExternalApiKey
from app.db.models.user import User, UserSession

logger = logging.getLogger("ylcraft.auth")

SESSION_COOKIE_NAME = "ylcraft_session"
SESSION_TTL_DAYS = int(os.getenv("YLCRAFT_SESSION_TTL_DAYS", "30"))
SESSION_COOKIE_SECURE = os.getenv("YLCRAFT_SESSION_COOKIE_SECURE", "") == "1"
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_LOGIN_FAILURE_LIMIT = int(os.getenv("YLCRAFT_LOGIN_FAILURE_LIMIT", "5"))
_LOGIN_FAILURE_WINDOW_SECONDS = int(os.getenv("YLCRAFT_LOGIN_FAILURE_WINDOW_SECONDS", "900"))
_login_failures: dict[str, deque[float]] = defaultdict(deque)


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """The authenticated caller, retaining its credential type for auditing."""

    user: User | None = None
    external_api_key: ExternalApiKey | None = None

    @property
    def kind(self) -> str:
        return "user" if self.user is not None else "external_api_key"

    @property
    def subject_id(self) -> str:
        if self.user is not None:
            return self.user.id
        assert self.external_api_key is not None
        return self.external_api_key.id


def validate_username(username: str) -> str:
    normalized = username.strip()
    if not _USERNAME_RE.fullmatch(normalized):
        raise ValueError("用户名必须为 3-64 位字母、数字、点、下划线或连字符")
    return normalized


def validate_password(password: str) -> None:
    if len(password) < 8:
        raise ValueError("密码至少需要 8 个字符")
    if len(password.encode("utf-8")) > 72:
        raise ValueError("密码 UTF-8 编码不能超过 72 字节")


def normalize_email(email: str | None) -> str | None:
    if email is None or not email.strip():
        return None
    normalized = email.strip().casefold()
    if len(normalized) > 320 or not _EMAIL_RE.fullmatch(normalized):
        raise ValueError("邮箱格式不正确")
    return normalized


def hash_password(password: str) -> str:
    validate_password(password)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def session_expiry(now: datetime | None = None) -> datetime:
    return (now or datetime.now(timezone.utc)) + timedelta(days=SESSION_TTL_DAYS)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


async def get_current_user_optional(
    request: Request,
    session=Depends(get_async_session_dependency),
) -> Optional[User]:
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    if not token:
        return None
    row = (await session.exec(
        select(UserSession).where(UserSession.token_hash == hash_session_token(token))
    )).first()
    if not row or row.is_revoked or _as_aware(row.expires_at) <= _utc_now():
        return None
    user = await session.get(User, row.user_id)
    return user if user and user.is_active else None


async def get_current_user(
    user: Optional[User] = Depends(get_current_user_optional),
) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="需要登录")
    return user


async def get_authenticated_principal_optional(
    request: Request,
    session=Depends(get_async_session_dependency),
) -> AuthenticatedPrincipal | None:
    """Accept a human session or an external Agent key using one DB session."""
    # A supplied Bearer credential remains strict: an invalid Agent key must
    # not be hidden by a valid browser session on the same request.
    external_key = await get_external_api_key_optional(request, session, require_key=False)
    if external_key is not None:
        return AuthenticatedPrincipal(external_api_key=external_key)
    user = await _get_current_user_from_request(request, session)
    return AuthenticatedPrincipal(user=user) if user is not None else None


async def get_authenticated_principal(
    principal: AuthenticatedPrincipal | None = Depends(get_authenticated_principal_optional),
) -> AuthenticatedPrincipal:
    if principal is None:
        raise HTTPException(status_code=401, detail="需要登录会话或有效的外部 API Key")
    return principal


async def _get_current_user_from_request(request: Request, session) -> User | None:
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    if not token:
        return None
    row = (await session.exec(
        select(UserSession).where(UserSession.token_hash == hash_session_token(token))
    )).first()
    if not row or row.is_revoked or _as_aware(row.expires_at) <= _utc_now():
        return None
    user = await session.get(User, row.user_id)
    return user if user and user.is_active else None


def login_rate_limit_key(username: str, ip_address: str) -> str:
    return f"{username.casefold()}:{ip_address}"


def login_is_rate_limited(username: str, ip_address: str, now: float | None = None) -> bool:
    current = time.time() if now is None else now
    failures = _login_failures[login_rate_limit_key(username, ip_address)]
    while failures and current - failures[0] >= _LOGIN_FAILURE_WINDOW_SECONDS:
        failures.popleft()
    return len(failures) >= _LOGIN_FAILURE_LIMIT


def login_rate_limit_retry_after(username: str, ip_address: str, now: float | None = None) -> int:
    current = time.time() if now is None else now
    failures = _login_failures[login_rate_limit_key(username, ip_address)]
    while failures and current - failures[0] >= _LOGIN_FAILURE_WINDOW_SECONDS:
        failures.popleft()
    if len(failures) < _LOGIN_FAILURE_LIMIT or not failures:
        return 0
    return max(1, int(_LOGIN_FAILURE_WINDOW_SECONDS - (current - failures[0]) + 0.999))


def record_login_failure(username: str, ip_address: str, now: float | None = None) -> None:
    current = time.time() if now is None else now
    _login_failures[login_rate_limit_key(username, ip_address)].append(current)
    logger.warning("Login failed for username=%s ip=%s", username, ip_address)


def clear_login_failures(username: str, ip_address: str) -> None:
    _login_failures.pop(login_rate_limit_key(username, ip_address), None)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
