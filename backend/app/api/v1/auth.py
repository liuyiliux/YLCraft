"""Local-account registration and revocable browser-session endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlmodel import select

from app.core.user_auth import (
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_SECURE,
    SESSION_TTL_DAYS,
    clear_login_failures,
    client_ip,
    get_current_user,
    hash_password,
    hash_session_token,
    login_is_rate_limited,
    login_rate_limit_retry_after,
    new_session_token,
    normalize_email,
    record_login_failure,
    session_expiry,
    validate_password,
    validate_username,
    verify_password,
)
from app.db.database import get_async_session_dependency
from app.db.models.user import User, UserSession

router = APIRouter()


class RegisterRequest(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(min_length=8, max_length=72)
    display_name: str = Field(default="", max_length=120)
    email: str | None = Field(default=None, max_length=320)


class LoginRequest(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=72)


def _user_payload(user: User) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat(),
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="lax",
        secure=SESSION_COOKIE_SECURE,
        path="/",
    )


@router.post("/register", status_code=status.HTTP_201_CREATED, summary="注册本地用户")
async def register(body: RegisterRequest, session=Depends(get_async_session_dependency)):
    try:
        username = validate_username(body.username)
        validate_password(body.password)
        email = normalize_email(body.email)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    existing = (await session.exec(select(User).where(User.username == username))).first()
    if existing:
        raise HTTPException(status_code=409, detail="用户名已存在")
    if email and (await session.exec(select(User).where(User.email == email))).first():
        raise HTTPException(status_code=409, detail="邮箱已被使用")
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(body.password),
        display_name=body.display_name.strip(),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return {"success": True, "data": _user_payload(user)}


@router.post("/login", summary="登录并创建服务端会话")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session=Depends(get_async_session_dependency),
):
    username = body.username.strip()
    ip_address = client_ip(request)
    if login_is_rate_limited(username, ip_address):
        retry_after = login_rate_limit_retry_after(username, ip_address)
        raise HTTPException(status_code=429, detail=f"登录失败次数过多，请在约 {retry_after} 秒后再试", headers={"Retry-After": str(retry_after)})
    user = (await session.exec(select(User).where(User.username == username))).first()
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        record_login_failure(username, ip_address)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    clear_login_failures(username, ip_address)
    token = new_session_token()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    session.add(UserSession(token_hash=hash_session_token(token), user_id=user.id, expires_at=session_expiry(now)))
    user.last_login_at = now
    session.add(user)
    await session.commit()
    _set_session_cookie(response, token)
    return {"success": True, "data": _user_payload(user)}


@router.post("/logout", summary="撤销当前服务端会话")
async def logout(request: Request, response: Response, session=Depends(get_async_session_dependency)):
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    if token:
        row = (await session.exec(
            select(UserSession).where(UserSession.token_hash == hash_session_token(token))
        )).first()
        if row and not row.is_revoked:
            row.is_revoked = True
            session.add(row)
            await session.commit()
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"success": True}


@router.get("/me", summary="获取当前登录用户")
async def current_user(user: User = Depends(get_current_user)):
    return {"success": True, "data": _user_payload(user)}
