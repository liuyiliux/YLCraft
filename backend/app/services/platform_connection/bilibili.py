"""Bilibili account helpers for platform connections."""

from __future__ import annotations

import logging

import httpx

from app.services.cookies.manager import CookieManager

logger = logging.getLogger("ylcraft.platform_connection.bilibili")


def extract_account_info_from_cookie(cookie_str: str) -> dict:
    """Extract Bilibili account profile fields from a cookie string."""
    info = {
        "account_id": None,
        "account_name": None,
        "account_avatar": None,
        "account_url": None,
    }

    try:
        mgr = CookieManager()
        raw_cookie = mgr.extract_raw(cookie_str)

        with httpx.Client(timeout=30) as client:
            headers = {
                "Cookie": raw_cookie or cookie_str,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.bilibili.com/",
            }
            resp = client.get("https://api.bilibili.com/x/web-interface/nav", headers=headers)

            if resp.status_code == 200:
                result = resp.json()
                if result.get("code") == 0:
                    data = result.get("data", {})
                    if data.get("isLogin"):
                        info["account_id"] = str(data.get("mid", ""))
                        info["account_name"] = data.get("uname", "")
                        info["account_avatar"] = data.get("face", "")
                        info["account_url"] = f"https://space.bilibili.com/{info['account_id']}"
                        logger.info("[Bilibili] Extracted account: %s", info["account_name"])

    except Exception as e:
        logger.warning("[Bilibili] Failed to extract account info: %s", e)

    return info


__all__ = ["extract_account_info_from_cookie"]
