"""
YLCraft — 平台登录态体检的公共工具

B站有 `/api/v1/bilibili/login-health`，抖音/小红书原先**没有**——
用户存完 Cookie 完全不知道还能不能用。实测就发生过
"小红书 Cookie 保存成功但搜索一直失败"，因为存进去的其实是游客态值。

这里放两个平台共用的取值/格式化逻辑，避免各写一份。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("ylcraft.platforms.login_health")


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


def resolve_connection(conn_id: str, platform: str = "") -> tuple[str, str]:
    """解析连接，返回 (实际使用的 conn_id, cookie)。

    为什么要兜底（2026-09-27 实测）：用户重新登录后连接 ID 会变，
    而前端/脚本可能还拿着旧 ID。旧 ID 查不到就直接返回空 cookie，
    界面显示"没有 Cookie，请先保存连接"——看起来像登录丢了，
    实际只是引用了过期的 ID。

    策略：
      1. 传入的 ID 存在**且未禁用** → 用它
      2. 不存在（或**被禁用**）但给了 platform → 回退到该平台**最近更新的未禁用连接**
      3. 都没有 → 返回 ("", "")

    ## ⚠️ 用户主动禁用的连接**一律不返回**（2026-10-01 加）

    这条很关键：前端让用户能"禁用"某个连接（风控期停一阵）。
    如果这里不排除禁用项，会出现：

      · 用户点了禁用 → 前端传旧 conn_id → 这里照样返回它的 cookie
        → **禁用形同虚设**，请求还在打那个账号

    所以两处都要排除：显式传的 ID 若已禁用，也走回退逻辑。
    """
    from app.db.database import SessionLocal
    from app.db.models.platform_connection import (
        ConnectionStatus,
        PlatformConnection,
    )

    session = SessionLocal()
    try:
        if conn_id:
            row = session.get(PlatformConnection, conn_id)
            if row and row.status != ConnectionStatus.DISABLED:
                return row.id, (row.cookie_content or "")
            if row:
                # 显式传了一条**已禁用**的连接 —— 不回退也不返回它。
                # 返回空让上层报"该连接已禁用"，比默默使用它好：
                # 后者会让用户以为"禁用了还在跑"（实测过这类困惑）。
                logger.info(
                    "[login-health] conn_id=%s 已被用户禁用，不返回凭证", conn_id
                )
                return row.id, ""

        if platform:
            from sqlmodel import select

            # 平台名必须是 PG 枚举里的合法值，否则查询会抛
            # `DataError: invalid input value for enum platformtype`
            # （实测：传 "NOSUCHPLATFORM" 直接 500）。
            #
            # 注意枚举的 value 是**小写**（douyin/xhs），但调用方常传大写
            # （DOUYIN/XHS，因为 PG 里存的是 name）。两种都接受。
            from app.db.models.platform_connection import PlatformType

            plat_enum = None
            raw = (platform or "").strip()
            for candidate in (raw, raw.lower(), raw.upper()):
                try:
                    plat_enum = PlatformType(candidate)
                    break
                except ValueError:
                    continue
            if plat_enum is None:
                try:
                    plat_enum = PlatformType[raw.upper()]
                except KeyError:
                    logger.warning(
                        "[login-health] 非法平台名 %r，跳过兜底查询", platform,
                    )
                    return "", ""

            # ⚠️ **必须排除用户主动禁用的连接**（2026-10-01）
            #
            # 这个兜底是"conn_id 失效时回退到该平台最新连接"。
            # 如果最新那条**被用户禁用了**，回退过去就等于**禁用失效** ——
            # 用户点了禁用，却仍在用那个账号发请求（正是他想避免的）。
            #
            # 所以按 updated_at 倒序找**第一条未禁用的**。
            from app.db.models.platform_connection import ConnectionStatus

            stmt = (
                select(PlatformConnection)
                .where(PlatformConnection.platform == plat_enum)
                .where(PlatformConnection.status != ConnectionStatus.DISABLED)
                .order_by(PlatformConnection.updated_at.desc())
                .limit(1)
            )
            row = session.exec(stmt).first()
            if row:
                logger.info(
                    "[login-health] conn_id=%s 不存在，回退到该平台最新**未禁用**连接 %s",
                    conn_id, row.id,
                )
                return row.id, (row.cookie_content or "")
            # 全被禁用了 → 返回空，让上层报"该平台连接已全部禁用"
            # （比默默用一个禁用连接好 —— 后者会让用户以为禁用没生效）
            logger.info("[login-health] %s 的连接都已禁用，不返回凭证", platform)
        return "", ""
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
