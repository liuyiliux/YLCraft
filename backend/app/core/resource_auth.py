"""Ownership checks shared by user-scoped API routes.

External API keys are authenticated callers but do not yet have a User mapping.
They can therefore pass an authentication gate, while only human sessions can
write a concrete ``owner_user_id`` or be compared against one.
"""

from __future__ import annotations

from fastapi import HTTPException

from app.core.user_auth import AuthenticatedPrincipal


def principal_owner_user_id(principal: AuthenticatedPrincipal | object) -> str | None:
    """Return a human owner, including safe direct internal function calls.

    Some Agent tools call route functions as internal services rather than via
    FastAPI dependency injection. Their existing tool authorization remains the
    gate; until keys gain an owner mapping their output is deliberately legacy
    (NULL) instead of failing with an attribute error.
    """
    user = getattr(principal, "user", None)
    return str(user.id) if user is not None else None


def require_owned_or_legacy(
    *, owner_user_id: str | None, principal: AuthenticatedPrincipal
) -> None:
    """Allow legacy NULL data and prevent one logged-in user reading another's data.

    An external key is intentionally permitted until a separate change gives it
    an explicit owner subject. It has already passed the API-key scope/quota
    checks at the authentication boundary.
    """
    if owner_user_id is None or principal.external_api_key is not None:
        return
    if principal.user is not None and owner_user_id == principal.user.id:
        return
    raise HTTPException(status_code=403, detail="无权访问其他用户的资源")
