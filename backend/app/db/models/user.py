"""用户账号与服务端会话数据模型。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """本地账号的可认证主体。

    密码只保留由后续认证服务写入的哈希值，模型和日志均不承载明文密码。
    """

    __tablename__ = "users"

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
        max_length=64,
    )
    username: str = Field(index=True, unique=True, max_length=64)
    email: Optional[str] = Field(default=None, index=True, max_length=320)
    password_hash: str = Field(max_length=255)
    display_name: str = Field(default="", max_length=120)
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column_kwargs={"server_default": "now()"},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column_kwargs={
            "server_default": "now()",
            "onupdate": lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        },
    )
    last_login_at: Optional[datetime] = Field(default=None)


class UserSession(SQLModel, table=True):
    """可即时撤销的服务端登录会话。"""

    __tablename__ = "user_sessions"

    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        primary_key=True,
        max_length=64,
    )
    token_hash: str = Field(index=True, unique=True, max_length=128)
    user_id: str = Field(
        foreign_key="users.id",
        index=True,
        max_length=64,
    )
    expires_at: datetime = Field(index=True)
    is_revoked: bool = Field(default=False, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column_kwargs={"server_default": "now()"},
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        sa_column_kwargs={
            "server_default": "now()",
            "onupdate": lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        },
    )
