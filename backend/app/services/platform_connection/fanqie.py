"""
番茄小说作家后台 — 凭证提取辅助（对齐 B站 bilibili.py）

设计约束（Phase 2，安全只读）：
  - 测试连接时用来「探活 + 尽力提取作家标识」，绝不改动任何线上数据。
  - 用一个**已验证的只读接口** `get_my_books`（book_list/v0/ GET）探活：
    code==0 → cookie 存活；返回登录页 / code 判为登录失效 → cookie 失效。
  - 作家昵称/头像等需 Phase 3 抓包「作家资料」接口后补全；当前仅从
    cookie 中尽力解析 writer_id（通常不在 cookie 中，退而用 sessionid 诊断）。

与 bilibili.py 保持一致：本函数为**同步**实现（内部用 httpx 同步客户端），
由 `PlatformConnectionService._test_cookie` 在同步流程中直接调用，避免异步事件
循环冲突。
"""
from __future__ import annotations

import logging

import httpx

from app.services.platforms.fanqie.apis import (
    BASE_URL,
    BOOK_LIST,
    DEFAULT_AID,
    DEFAULT_APP_NAME,
)
from app.services.platforms.fanqie.utils import (
    classify_fanqie_error,
    extract_writer_id_from_cookie,
    normalize_cookie,
    CookieExpiredError,
)

logger = logging.getLogger("ylcraft.platform_connection.fanqie")

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)


def extract_account_info_from_cookie(cookie_str: str) -> dict:
    """
    验证番茄 cookie 有效性并尽力提取作家标识。

    Returns:
        {"account_id", "account_name", "account_avatar", "account_url"}
        cookie 失效或解析失败时返回全 None 字典。
    """
    info = {
        "account_id": None,
        "account_name": None,
        "account_avatar": None,
        "account_url": None,
    }
    if not cookie_str:
        return info

    cookie = normalize_cookie(cookie_str)
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
        "origin": "https://fanqienovel.com",
        "referer": "https://fanqienovel.com/main/writer/",
        "user-agent": _USER_AGENT,
        "Cookie": cookie,
    }
    params = {
        "aid": DEFAULT_AID,
        "app_name": DEFAULT_APP_NAME,
        "page": "1",
        "size": "20",
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{BASE_URL}{BOOK_LIST}", params=params, headers=headers)

        # 非 200 或返回 HTML（登录页重定向）→ cookie 失效
        if resp.status_code != 200:
            return info
        try:
            payload = resp.json()
        except ValueError:
            return info

        code = payload.get("code", -1)
        if code != 0:
            err = classify_fanqie_error(code, payload.get("message") or "")
            if isinstance(err, CookieExpiredError):
                logger.warning("[Fanqie] Cookie expired during extract (code=%s)", code)
                return info
            # 其他非登录错误不直接判定失效，但保守不提取账号
            logger.warning("[Fanqie] book_list returned code=%s, treating as no-extract", code)
            return info

        # code == 0 → cookie 存活，尽力解析作家标识
        writer_id = extract_writer_id_from_cookie(cookie_str)
        if writer_id:
            info["account_id"] = writer_id
            info["account_name"] = writer_id
            info["account_url"] = f"https://fanqienovel.com/main/writer/{writer_id}"
            logger.info("[Fanqie] Extracted account: %s", writer_id)
        else:
            logger.info("[Fanqie] Cookie valid but no writer_id in cookie (Phase 3 will add profile endpoint)")

    except Exception as e:  # noqa: BLE001
        logger.warning("[Fanqie] Failed to extract account info: %s", e)
        return info

    return info


__all__ = ["extract_account_info_from_cookie"]
