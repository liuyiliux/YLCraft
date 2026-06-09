"""Book source cookie model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel


class BookSourceCookie(SQLModel, table=True):
    """Cookie credentials scoped to a book source and domain."""

    __tablename__ = "book_source_cookies"

    id: str = Field(
        primary_key=True,
        default_factory=lambda: uuid.uuid4().hex,
    )
    book_source_id: str = Field(foreign_key="book_sources.id", index=True)
    domain: str = Field(max_length=255, index=True)
    cookie_content: str = Field(default="", sa_column=Column(Text, nullable=False))
    description: str = Field(default="", max_length=255)
    is_active: bool = Field(default=True, index=True)
    expires_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
