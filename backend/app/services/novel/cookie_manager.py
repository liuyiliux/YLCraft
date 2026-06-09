"""Cookie management for novel book sources."""

from __future__ import annotations

import re
import time
from datetime import datetime
from http.cookies import SimpleCookie
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from sqlalchemy.orm import Session
from sqlmodel import select

from app.db.models.book_source import BookSource
from app.db.models.book_source_cookie import BookSourceCookie


class BookSourceCookieManager:
    """CRUD and domain matching for book source cookies."""

    def __init__(self, db: Session):
        self.db = db

    def get_cookies_by_source(self, source_id: str) -> List[BookSourceCookie]:
        statement = (
            select(BookSourceCookie)
            .where(BookSourceCookie.book_source_id == source_id)
            .order_by(BookSourceCookie.domain, BookSourceCookie.created_at)
        )
        return list(self.db.exec(statement).all())

    def get_cookie(self, cookie_id: str, source_id: Optional[str] = None) -> Optional[BookSourceCookie]:
        cookie = self.db.get(BookSourceCookie, cookie_id)
        if not cookie:
            return None
        if source_id is not None and cookie.book_source_id != source_id:
            return None
        return cookie

    def get_cookie_for_url(self, url: str, source_id: str) -> Optional[str]:
        match = self.get_cookie_match(url, source_id)
        if not match:
            return None
        return match["cookie_header"]

    def get_cookie_match(self, url: str, source_id: str) -> Optional[Dict[str, Any]]:
        host = _normalize_host(urlparse(url).hostname or "")
        if not host:
            return None

        now = datetime.now()
        candidates = [
            cookie
            for cookie in self.get_cookies_by_source(source_id)
            if cookie.is_active and (cookie.expires_at is None or cookie.expires_at > now)
        ]

        best_cookie: Optional[BookSourceCookie] = None
        best_score = -1
        for cookie in candidates:
            score = _domain_match_score(host, cookie.domain)
            if score > best_score:
                cookie_header = cookie_content_to_header(cookie.cookie_content)
                if cookie_header:
                    best_cookie = cookie
                    best_score = score

        if best_cookie is None:
            return None

        return {
            "cookie_id": best_cookie.id,
            "domain": best_cookie.domain,
            "description": best_cookie.description,
            "cookie_header": cookie_content_to_header(best_cookie.cookie_content),
            "cookie_count": count_cookies(best_cookie.cookie_content),
        }

    def create_cookie(self, cookie_data: Dict[str, Any]) -> BookSourceCookie:
        source_id = cookie_data.get("book_source_id")
        if not source_id:
            raise ValueError("book_source_id is required")
        self._require_source(source_id)

        cookie = BookSourceCookie(
            book_source_id=source_id,
            domain=_normalize_cookie_domain(cookie_data.get("domain", "")),
            cookie_content=cookie_data.get("cookie_content", ""),
            description=cookie_data.get("description", "") or "",
            is_active=cookie_data.get("is_active", True),
            expires_at=cookie_data.get("expires_at"),
        )
        self.db.add(cookie)
        self.db.commit()
        self.db.refresh(cookie)
        return cookie

    def update_cookie(self, cookie_id: str, data: Dict[str, Any]) -> Optional[BookSourceCookie]:
        cookie = self.db.get(BookSourceCookie, cookie_id)
        if not cookie:
            return None

        allowed = {"domain", "cookie_content", "description", "is_active", "expires_at"}
        for key, value in data.items():
            if key not in allowed:
                continue
            if value is None and key != "expires_at":
                continue
            if key == "domain":
                value = _normalize_cookie_domain(value)
            setattr(cookie, key, value)

        cookie.updated_at = datetime.now()
        self.db.add(cookie)
        self.db.commit()
        self.db.refresh(cookie)
        return cookie

    def delete_cookie(self, cookie_id: str) -> bool:
        cookie = self.db.get(BookSourceCookie, cookie_id)
        if not cookie:
            return False
        self.db.delete(cookie)
        self.db.commit()
        return True

    def _require_source(self, source_id: str) -> None:
        source = self.db.get(BookSource, source_id)
        if not source:
            raise ValueError("book source does not exist")


CookieManager = BookSourceCookieManager


def cookie_content_to_header(cookie_content: str) -> str:
    """Convert Netscape or header-style cookie content to a Cookie header."""
    content = (cookie_content or "").strip()
    if not content:
        return ""

    if "\n" not in content and "\t" not in content and _looks_like_cookie_header(content):
        return _normalize_cookie_header(content)

    pairs: List[str] = []
    now_ts = int(time.time())
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_") :]
        elif line.startswith("#"):
            continue

        parts = line.split("\t")
        if len(parts) < 7:
            parts = re.split(r"\s+", line, maxsplit=6)

        if len(parts) >= 7:
            expires_raw = parts[4]
            name = parts[5].strip()
            value = parts[6].strip()
            if not name:
                continue
            try:
                expires = int(expires_raw)
            except ValueError:
                expires = 0
            if expires and expires < now_ts:
                continue
            pairs.append(f"{name}={value}")
            continue

        if _looks_like_cookie_header(line):
            pairs.extend(_split_cookie_header(line))

    return "; ".join(_dedupe_cookie_pairs(pairs))


def count_cookies(cookie_content: str) -> int:
    header = cookie_content_to_header(cookie_content)
    if not header:
        return 0
    return len(_split_cookie_header(header))


def _domain_match_score(host: str, cookie_domain: str) -> int:
    domain = _normalize_cookie_domain(cookie_domain)
    if domain in {"", "*", "default"}:
        return 1

    plain = domain.lstrip(".")
    if host == plain and not domain.startswith("."):
        return 1000 + len(plain)
    if host == plain:
        return 900 + len(plain)
    if domain.startswith(".") and host.endswith(domain):
        return 800 + len(plain)
    if host.endswith("." + plain):
        return 700 + len(plain)
    return -1


def _normalize_cookie_domain(domain: str) -> str:
    domain = (domain or "").strip().lower()
    if domain.startswith("http://") or domain.startswith("https://"):
        domain = urlparse(domain).hostname or domain
    return domain.rstrip("/")


def _normalize_host(host: str) -> str:
    return (host or "").strip().lower().rstrip(".")


def _looks_like_cookie_header(value: str) -> bool:
    return "=" in value and "\t" not in value


def _normalize_cookie_header(value: str) -> str:
    pairs = _split_cookie_header(value)
    return "; ".join(_dedupe_cookie_pairs(pairs))


def _split_cookie_header(value: str) -> List[str]:
    pairs = []
    for morsel in value.split(";"):
        morsel = morsel.strip()
        if morsel and "=" in morsel:
            pairs.append(morsel)
    return pairs


def _dedupe_cookie_pairs(pairs: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for pair in pairs:
        name = pair.split("=", 1)[0].strip()
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(pair)
    return result


def parse_cookie_header(value: str) -> Dict[str, str]:
    cookie = SimpleCookie()
    cookie.load(value or "")
    return {key: morsel.value for key, morsel in cookie.items()}
