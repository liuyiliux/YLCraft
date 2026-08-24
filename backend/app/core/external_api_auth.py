"""外部 Agent API 鉴权：平台级外部 API Key 校验（可配置/可选）。"""
from __future__ import annotations

import hashlib
import os
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlmodel import select

from app.db.database import get_async_session_dependency
from app.db.models.external_api_key import ExternalApiKey

# 生产环境置 1 可对挂了校验依赖的路径强制要求 key（无 key 或未带 key 返回 401）。
_REQUIRE_KEY = os.getenv("YLCRAFT_EXTERNAL_API_REQUIRE_KEY", "") == "1"


def hash_external_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# 简单滑动窗口限流（每 key × 每 60s），进程内存，重启清空。生产可换 Redis。
_rate_windows: dict[str, deque[float]] = defaultdict(deque)


async def optional_external_api_key(
    request: Request,
    session=Depends(get_async_session_dependency),
) -> Optional[ExternalApiKey]:
    """若请求带 Authorization: Bearer <外部 key> 则校验并返回，否则返回 None（兼容浏览器/本地）。

    外部 Agent 契约接口可把本依赖挂在路径上；带 key 时校验哈希、活性、速率。
    生产环境可通过 `YLCRAFT_EXTERNAL_API_REQUIRE_KEY=1` 对消耗型路径强制校验。
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        if _REQUIRE_KEY:
            raise HTTPException(status_code=401, detail="需要外部 API Key（YLCRAFT_EXTERNAL_API_REQUIRE_KEY=1）")
        return None
    token = auth[7:]
    row = (await session.exec(
        select(ExternalApiKey).where(ExternalApiKey.key_hash == hash_external_key(token))
    )).first()
    if not row or not row.active:
        raise HTTPException(status_code=401, detail="无效或已停用的外部 API Key")

    now = time.time()
    win = _rate_windows[row.id]
    while win and now - win[0] > 60:
        win.popleft()
    if len(win) >= max(row.rate_limit_per_min, 1):
        raise HTTPException(status_code=429, detail="外部 API 请求速率超限")
    win.append(now)

    is_generate = row.scope == "generate"
    if is_generate and row.quota > 0 and row.quota_used >= row.quota:
        raise HTTPException(status_code=403, detail="外部 API Key 次数配额已耗尽")

    row.use_count += 1
    if is_generate and row.quota > 0:
        row.quota_used += 1
    row.last_used_at = datetime.utcnow()
    session.add(row)
    await session.commit()
    return row
