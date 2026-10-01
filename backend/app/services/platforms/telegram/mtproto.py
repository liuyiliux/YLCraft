"""YLCraft — Telegram MTProto 会话管理（B 方案，需登录）。

## 为什么单独一个模块

MTProto 的登录是**有状态、多步交互**的（api_id/api_hash → 手机号 →
验证码 → 可选两步验证密码），与其它平台的"抓 cookie"完全不同。
把这套状态机收在这里，别混进账号中心的 cookie 流程。

## 会话文件

`data/telegram/account.session`（telethon 的 SQLiteSession）。

⚠️ **这个文件等于你账号的登录凭证** —— 必须：
  · 不进 git（`.gitignore` 已加）
  · 不通过任何 API 返回给前端
  · 只存 api_hash，不存明文密码

## ⚠️ 与 An 方案的边界

A 方案（`web_preview.py`，免登录抓 `t.me/s`）能覆盖：
  · 列公开频道消息、**频道内关键词搜索**（`?q=`）

B 方案（本模块）才能：
  · **跨频道全局关键词搜索**（`messages.SearchGlobal`）
  · 列出**你加入的频道**（`messages.GetDialogs`）
  · 读**私有频道**

所以两者是互补的，不是替代关系。
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ylcraft.platforms.telegram.mtproto")

# 会话文件目录（与其它敏感凭证一致，放 data/ 下）
DATA_DIR = Path(__file__).resolve().parents[4] / "data" / "telegram"
SESSION_NAME = "account"

# 登录状态机：一次登录只允许有一个进行中的流程（api_hash 不落盘到配置以外）
_LOGIN_STATE: Dict[str, Any] = {
    "phone": "",
    "phone_code_hash": "",
    "client": None,
    "api_id": 0,
    "api_hash": "",
    "needs_password": False,
}


def session_path() -> Path:
    """session 文件的绝对路径（不带 .session 后缀）。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / SESSION_NAME


def has_session() -> bool:
    """是否已有会话文件（不代表仍然有效）。"""
    p = session_path().with_suffix(".session")
    return p.exists() and p.stat().st_size > 0


def delete_session() -> bool:
    """退出登录：删除会话文件。"""
    p = session_path().with_suffix(".session")
    try:
        if p.exists():
            p.unlink()
            logger.info("[telegram] 已删除会话文件")
            return True
    except Exception as exc:
        logger.warning("[telegram] 删除会话文件失败：%s", exc)
    return False


def load_credentials() -> Dict[str, str]:
    """读取已保存的 api_id / api_hash。

    存哪：`data/telegram/credentials.json`（不进 git）。
    ⚠️ api_hash 是敏感信息，**不要**写进代码或返回前端。
    """
    import json

    p = DATA_DIR / "credentials.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return {"api_id": str(d.get("api_id") or ""), "api_hash": d.get("api_hash") or ""}
    except Exception:
        return {}


def save_credentials(api_id: str, api_hash: str) -> None:
    """保存 api_id / api_hash（0600 权限，尽量）。"""
    import json

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    p = DATA_DIR / "credentials.json"
    p.write_text(
        json.dumps({"api_id": str(api_id), "api_hash": api_hash}, ensure_ascii=False),
        encoding="utf-8",
    )
    try:
        os.chmod(p, 0o600)
    except Exception:
        pass  # Windows 上 chmod 语义有限，失败不影响功能


def _build_client(api_id: int, api_hash: str):
    """构造 telethon client（不连接）。"""
    from telethon import TelegramClient

    return TelegramClient(str(session_path()), api_id, api_hash)


async def send_code(api_id: str, api_hash: str, phone: str) -> Dict[str, Any]:
    """第一步：发送验证码。

    Returns:
        {"ok": True, "phone_code_hash": "..."}
    Raises:
        RuntimeError（可读原因）
    """
    from telethon.errors import ApiIdInvalidError, PhoneNumberInvalidError

    if not api_id or not api_hash:
        raise RuntimeError(
            "缺少 api_id / api_hash。请到 https://my.telegram.org 的 "
            "「API development tools」申请（免费），然后填到这里。"
        )
    if not phone or not phone.strip():
        raise RuntimeError("请填写手机号（国际格式，如 +8613800138000）。")

    try:
        aid = int(api_id)
    except ValueError:
        raise RuntimeError("api_id 必须是数字（在 my.telegram.org 页面上的 App api_id）。")

    client = _build_client(aid, api_hash)
    try:
        await client.connect()
    except Exception as exc:
        raise RuntimeError(
            f"无法连接 Telegram（{type(exc).__name__}）。"
            "MTProto 走的是 **Telegram 服务器直连**，"
            "需要 VPN/代理可用；若代理是 PAC 模式，"
            "请设置环境变量 HTTPS_PROXY。"
        ) from exc

    try:
        sent = await client.send_code_request(phone)
    except PhoneNumberInvalidError as exc:
        await client.disconnect()
        raise RuntimeError(
            "手机号格式不对。要用**国际格式**（含国家码），如 +8613800138000。"
        ) from exc
    except ApiIdInvalidError as exc:
        await client.disconnect()
        raise RuntimeError(
            "api_id / api_hash 无效。请确认是从 https://my.telegram.org 申请的那一对。"
        ) from exc
    except Exception as exc:
        await client.disconnect()
        raise RuntimeError(f"发送验证码失败：{type(exc).__name__}: {str(exc)[:150]}") from exc

    _LOGIN_STATE.update({
        "phone": phone,
        "phone_code_hash": sent.phone_code_hash,
        "client": client,
        "api_id": aid,
        "api_hash": api_hash,
        "needs_password": False,
    })
    # 记住凭证，下次不用再填
    save_credentials(api_id, api_hash)
    logger.info("[telegram] 验证码已发送（phone=%s）", phone[:5] + "****")
    return {"ok": True, "phone_code_hash": sent.phone_code_hash}


async def sign_in(code: str, password: str = "") -> Dict[str, Any]:
    """第二步：提交验证码（必要时提交两步验证密码）。

    Returns:
        {"ok": True, "username": "...", "needs_password": bool}
    """
    from telethon.errors import (
        PhoneCodeExpiredError,
        PhoneCodeInvalidError,
        SessionPasswordNeededError,
    )

    st = _LOGIN_STATE
    client = st.get("client")
    if client is None:
        raise RuntimeError(
            "登录流程已失效（服务可能重启过）。请重新点击「发送验证码」。"
        )
    if not (code or "").strip():
        raise RuntimeError("请填写收到的验证码。")

    try:
        await client.sign_in(
            phone=st["phone"],
            code=code.strip(),
            phone_code_hash=st["phone_code_hash"],
        )
    except SessionPasswordNeededError:
        # 账号开了两步验证 —— 需要密码
        if not password:
            st["needs_password"] = True
            return {"ok": False, "needs_password": True,
                    "message": "该账号开启了两步验证，请填写密码后再次提交。"}
        try:
            await client.sign_in(password=password)
        except Exception as exc:
            raise RuntimeError(
                f"两步验证密码错误或失败：{type(exc).__name__}。请检查密码。"
            ) from exc
    except PhoneCodeInvalidError as exc:
        raise RuntimeError("验证码不对，请检查后重试。") from exc
    except PhoneCodeExpiredError as exc:
        raise RuntimeError(
            "验证码已过期。请重新点击「发送验证码」获取新验证码。"
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"登录失败：{type(exc).__name__}: {str(exc)[:150]}") from exc

    me = await client.get_me()
    username = getattr(me, "username", "") or ""
    logger.info("[telegram] 登录成功 username=%s", username)
    st["needs_password"] = False
    return {"ok": True, "username": username, "needs_password": False}


async def get_status() -> Dict[str, Any]:
    """查询登录状态（不抛异常 —— 未登录是正常状态）。"""
    creds = load_credentials()
    out: Dict[str, Any] = {
        "has_session": has_session(),
        "has_credentials": bool(creds.get("api_id") and creds.get("api_hash")),
        "api_id": creds.get("api_id", ""),
        "logged_in": False,
        "username": "",
        "needs_password": bool(_LOGIN_STATE.get("needs_password")),
    }
    if not out["has_credentials"] or not out["has_session"]:
        return out

    client = None
    try:
        client = _build_client(int(creds["api_id"]), creds["api_hash"])
        await asyncio.wait_for(client.connect(), timeout=20)
        if not await client.is_user_authorized():
            return out
        me = await client.get_me()
        out["logged_in"] = True
        out["username"] = getattr(me, "username", "") or ""
        out["display_name"] = " ".join(
            x for x in [getattr(me, "first_name", ""), getattr(me, "last_name", "")] if x
        )
        out["user_id"] = getattr(me, "id", 0)
    except Exception as exc:
        logger.warning("[telegram] 查询登录态失败：%s", exc)
        out["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    finally:
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass
    return out


async def logout() -> Dict[str, Any]:
    """退出登录（尝试通知服务器 + 删本地会话）。"""
    creds = load_credentials()
    if creds.get("api_id") and creds.get("api_hash") and has_session():
        client = None
        try:
            client = _build_client(int(creds["api_id"]), creds["api_hash"])
            await asyncio.wait_for(client.connect(), timeout=15)
            await client.log_out()
        except Exception as exc:
            logger.warning("[telegram] 服务端登出失败（仍会删本地会话）：%s", exc)
        finally:
            if client is not None:
                try:
                    await client.disconnect()
                except Exception:
                    pass
    deleted = delete_session()
    _LOGIN_STATE.update({"client": None, "phone": "", "phone_code_hash": ""})
    return {"ok": True, "deleted": deleted}


async def get_authorized_client(timeout: int = 25):
    """取一个**已连接且已授权**的 client（调用方负责 disconnect）。

    Raises:
        RuntimeError: 未登录 / 连接失败（**可操作**提示）
    """
    creds = load_credentials()
    if not (creds.get("api_id") and creds.get("api_hash")):
        raise RuntimeError(
            "尚未配置 Telegram API 凭证。请到「账号中心 → Telegram」"
            "填写 api_id / api_hash（在 my.telegram.org 免费申请）。"
        )
    if not has_session():
        raise RuntimeError(
            "尚未登录 Telegram 账号。请到「账号中心 → Telegram」完成登录"
            "（手机号 + 验证码）。\n"
            "⚠️ 注意：跨频道搜索和「我的频道」**必须登录**；"
            "只看公开频道用「频道消息」即可，无需登录。"
        )
    client = _build_client(int(creds["api_id"]), creds["api_hash"])
    try:
        await asyncio.wait_for(client.connect(), timeout=timeout)
    except Exception as exc:
        raise RuntimeError(
            f"无法连接 Telegram（{type(exc).__name__}）。请确认 VPN/代理可用。"
        ) from exc
    if not await client.is_user_authorized():
        try:
            await client.disconnect()
        except Exception:
            pass
        raise RuntimeError(
            "Telegram 登录态已失效。请到「账号中心 → Telegram」重新登录。"
        )
    return client
