"""
YLCraft — 平台登录态体检的公共工具

B站有 `/api/v1/bilibili/login-health`，抖音/小红书原先**没有**——
用户存完 Cookie 完全不知道还能不能用。实测就发生过
"小红书 Cookie 保存成功但搜索一直失败"，因为存进去的其实是游客态值。

这里放两个平台共用的取值/格式化逻辑，避免各写一份。
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def get_raw_cookie(conn_id: str) -> str:
    """按连接 ID 取原始 Cookie（Netscape 或 header 格式，原样返回）。"""
    from app.db.database import SessionLocal
    from app.db.models.platform_connection import PlatformConnection

    session = SessionLocal()
    try:
        row = session.get(PlatformConnection, conn_id)
        return (row.cookie_content or "") if row else ""
    finally:
        session.close()


def cookie_names(raw: str) -> list[str]:
    """列出 Cookie 名（**不返回任何值**）。兼容 Netscape 与 `k=v; k2=v2`。"""
    names: list[str] = []
    if not raw:
        return names
    if "\t" in raw:
        for line in raw.splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) >= 6:
                names.append(parts[5])
    else:
        for part in raw.split(";"):
            if "=" in part:
                names.append(part.strip().split("=", 1)[0])
    return names


def netscape_to_header(raw: str, domain_key: str) -> str:
    """Netscape → `k=v; k2=v2`，只保留包含 domain_key 的域。"""
    if "\t" not in raw:
        return raw
    pairs: list[str] = []
    for line in raw.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 7 and domain_key in parts[0]:
            pairs.append(f"{parts[5]}={parts[6]}")
    return "; ".join(pairs)


def health_item(
    key: str,
    label: str,
    ok: bool,
    message: str,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """体检结果条目（与 B站 login-health 同构，前端可复用同一渲染）。"""
    return {
        "key": key,
        "label": label,
        "ok": bool(ok),
        "message": message,
        "data": data or {},
    }
