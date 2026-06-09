"""Schemas for book source cookies and YLCraft rule format."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class BookSourceCookieCreate(BaseModel):
    domain: str = Field(default="")
    cookie_content: str = Field(default="")
    description: str = Field(default="")
    is_active: bool = Field(default=True)
    expires_at: Optional[datetime] = None


class BookSourceCookieUpdate(BaseModel):
    domain: Optional[str] = None
    cookie_content: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    expires_at: Optional[datetime] = None


class BookSourceCookieRead(BaseModel):
    id: str
    book_source_id: str
    domain: str
    description: str = ""
    is_active: bool = True
    expires_at: Optional[datetime] = None
    cookie_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class FieldExtractConfig(BaseModel):
    selector: str = ""
    type: Literal["text", "attr", "html"] = "text"
    attr: Optional[str] = None
    trim: bool = True
    prefix: str = ""
    suffix: str = ""
    max_length: Optional[int] = None


class ItemRuleConfig(BaseModel):
    selector: str = ""
    limit: Optional[int] = None
    fields: Dict[str, FieldExtractConfig] = Field(default_factory=dict)


class RequestRuleConfig(BaseModel):
    url: str = ""
    method: Literal["GET", "POST"] = "GET"
    headers: Dict[str, str] = Field(default_factory=dict)
    params: Dict[str, Any] = Field(default_factory=dict)
    items: ItemRuleConfig = Field(default_factory=ItemRuleConfig)


class BookInfoRuleConfig(BaseModel):
    fields: Dict[str, FieldExtractConfig] = Field(default_factory=dict)


class TocRuleConfig(BaseModel):
    items: ItemRuleConfig = Field(default_factory=ItemRuleConfig)


class ContentRuleConfig(BaseModel):
    selector: str = ""
    remove: List[str] = Field(default_factory=list)
    text_only: bool = True
    join_with: str = "\n\n"


class YLCraftRule(BaseModel):
    version: str = "1.0"
    name: str = ""
    base_url: str = ""
    search: Optional[RequestRuleConfig] = None
    book_info: Optional[BookInfoRuleConfig] = None
    toc: Optional[TocRuleConfig] = None
    content: Optional[ContentRuleConfig] = None
    conversion_warnings: List[str] = Field(default_factory=list)
