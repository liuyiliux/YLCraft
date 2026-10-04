"""YLCraft — Telegram MTProto 数据获取（B 方案，需登录）。

这里实现 A 方案（`web_preview.py`）**做不到**的两件事：
  1. **跨频道全局关键词搜索**（`messages.SearchGlobal`）
  2. **列出你加入的频道**（`messages.GetDialogs`）

外加一件 A 方案能做但这里更完整的：读任意频道（含私有）的消息历史。

## ⚠️ 与 A 方案的分工

| 需求 | 用哪个 | 需要登录 |
|------|--------|---------|
| 看公开频道消息 | A（t.me/s） | 否 |
| **在某个公开频道内搜关键词** | **A（`?q=`）** | 否 |
| 跨频道全局搜关键词 | B（本模块） | 是 |
| 看我加入的频道 | B（本模块） | 是 |
| 看私有频道 | B（本模块） | 是 |

所以前端"频道消息"tab 用 A，"全网搜索"/"我的频道"tab 用 B。

## 速率限制

Telegram 对 API 有 FloodWait。这里：
  · 不并发（一次一个请求）
  · 遇到 FloodWait 转成**可操作错误**（告诉用户还要等多少秒），
    而不是静默重试（那会越等越久）
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .models import TelegramChannel, TelegramMessage

logger = logging.getLogger("ylcraft.platforms.telegram.mtproto_data")


def _flood_wait_message(exc: Exception) -> Optional[str]:
    """把 FloodWait 转成可读提示。不是 FloodWait 返回 None。"""
    name = type(exc).__name__
    if "FloodWait" in name:
        secs = getattr(exc, "seconds", 0)
        return (
            f"[telegram] 操作过于频繁，被 Telegram 限流（FloodWait）。"
            f"请等待约 **{secs} 秒**后再试。\n"
            "（这是 Telegram 服务端的限制，不是程序错误 —— "
            "短时间内大量请求会触发，等待后自然恢复。）"
        )
    return None


async def _msg_to_model(msg: Any, channel: str = "", channel_title: str = "") -> TelegramMessage:
    """把 telethon 的 Message 转成我们的模型。

    ⚠️ 媒体下载不在这里做 —— 只记录"有没有媒体"和元数据。
    真正下载走 yt-dlp（`t.me/ch/msgid`）或 telethon 的 download_media。
    """
    text = getattr(msg, "message", "") or ""
    date = getattr(msg, "date", None)
    out = TelegramMessage(
        id=str(getattr(msg, "id", "")),
        channel=channel,
        channel_title=channel_title,
        text=text,
        date=date.isoformat() if date else "",
        views=int(getattr(msg, "views", 0) or 0),
    )
    # 媒体：图片 / 视频
    media = getattr(msg, "media", None)
    if media is not None:
        kind = type(media).__name__
        if kind == "MessageMediaPhoto":
            out.raw_data["media_type"] = "photo"
        elif kind == "MessageMediaDocument":
            doc = getattr(media, "document", None)
            mime = ""
            if doc is not None:
                for attr in (getattr(doc, "attributes", None) or []):
                    if type(attr).__name__ == "DocumentAttributeVideo":
                        out.raw_data["media_type"] = "video"
                        out.duration = int(getattr(attr, "duration", 0) or 0)
                    if type(attr).__name__ == "DocumentAttributeFilename":
                        out.raw_data["filename"] = getattr(attr, "file_name", "")
                mime = getattr(doc, "mime_type", "") or ""
            out.raw_data["media_type"] = out.raw_data.get("media_type") or "document"
            out.raw_data["mime_type"] = mime
    # 转发来源
    fwd = getattr(msg, "forward", None) or getattr(msg, "fwd_from", None)
    if fwd is not None:
        out.forward_from = (
            getattr(fwd, "from_name", "")
            or str(getattr(fwd, "channel_post", "") or "")
            or ""
        )
    return out


async def search_global(
    client,
    keyword: str,
    limit: int = 20,
) -> List[TelegramMessage]:
    """关键词搜索（**范围诚实说明，别夸大**）。

    ## ⚠️ 它搜的不是"全网"（2026-10-01 调研修正）

    我最初把它叫"跨频道全局搜索"，**这是不准确的**。
    telethon 的 `client.iter_messages(None, search=...)` 底层是
    `messages.SearchGlobal`，而**它只覆盖"你已加入的会话"**
    （官方行为，见 Telethon issue #4446）。

    真正搜**所有公开频道**要用 `channels.SearchPosts`，但它：
      · 需要 **Premium 账号**
      · 报 `403 PREMIUM_ACCOUNT_REQUIRED`
      · **按 Stars 计费**

    所以本函数的能力应当如实描述为：
        **「在你已加入的频道/群组里搜关键词」**

    前端文案也必须这么写（见 `frontend` 的 telegram tab 标签）。
    把它说成"全网搜索"会让用户以为能搜到所有公开频道 ——
    那是**做不到**的，属于过度承诺。

    ## 那要搜"不在我频道列表里的公开频道"怎么办？

    用 A 方案的**频道内搜索**（`?q=`，免登录）：
    先知道频道名 → `Channel 名 + 关键词` → 只搜那个频道。
    这条路**不需要登录、也不收费**。
    """
    from telethon.tl.types import InputPeerEmpty

    kw = (keyword or "").strip()
    if not kw:
        return []

    out: List[TelegramMessage] = []
    try:
        async for msg in client.iter_messages(None, search=kw, limit=limit):
            # 取频道名（可能要额外请求，失败就算了）
            chat = getattr(msg, "chat", None)
            ch_name = ""
            ch_title = ""
            if chat is not None:
                ch_name = getattr(chat, "username", "") or ""
                ch_title = getattr(chat, "title", "") or ""
            out.append(await _msg_to_model(msg, channel=ch_name, channel_title=ch_title))
    except Exception as exc:
        hint = _flood_wait_message(exc)
        if hint:
            raise RuntimeError(hint) from exc
        raise RuntimeError(
            f"[telegram] 关键词搜索失败：{type(exc).__name__}: {str(exc)[:150]}"
        ) from exc
    return out


async def list_dialogs(client, limit: int = 100) -> List[TelegramChannel]:
    """**列出你加入的频道/群组**（A 方案做不到）。

    只返回**频道/群组**（跳过私聊）—— 用户要的是"我加入的频道"。
    """
    out: List[TelegramChannel] = []
    try:
        async for dialog in client.iter_dialogs(limit=limit):
            ent = dialog.entity
            kind = type(ent).__name__
            # 频道 / 超级群 / 普通群 —— 只要这些，跳过 User（私聊）
            if kind not in ("Channel", "Chat", "ChatForbidden", "ChannelForbidden"):
                continue
            if kind == "User":
                continue
            out.append(TelegramChannel(
                id=str(getattr(ent, "id", "")),
                username=getattr(ent, "username", "") or "",
                title=getattr(ent, "title", "") or dialog.name or "",
                subscribers=int(getattr(ent, "participants_count", 0) or 0),
                source="mtproto",
                raw_data={
                    "is_channel": bool(getattr(ent, "broadcast", False)),
                    "is_group": bool(getattr(ent, "megagroup", False)),
                    "is_creator": bool(getattr(ent, "creator", False)),
                },
            ))
    except Exception as exc:
        hint = _flood_wait_message(exc)
        if hint:
            raise RuntimeError(hint) from exc
        raise RuntimeError(
            f"[telegram] 获取频道列表失败：{type(exc).__name__}: {str(exc)[:150]}"
        ) from exc
    # 频道排前面，其次按订阅数
    out.sort(key=lambda c: (not c.raw_data.get("is_channel"), -c.subscribers))
    return out


async def search_channels(
    client,
    keyword: str,
    limit: int = 30,
) -> List[TelegramChannel]:
    """**按标题/用户名搜频道**（需登录）—— 这才是"在客户端里搜频道"。

    ## 为什么必须有这个（2026-10-03 实测）

    `t.me/s/<username>` 路径**搜不了频道**：它只认 username，
    而客户端里输入中文能搜到频道 —— 客户端走的是**另一条路径**：
    服务端按**标题**匹配。所以「频道消息」tab 无论怎么输中文都失败。

    MTProto 的 `contacts.Search` 正是这条路径：

        contacts.SearchRequest(q=<关键词>, limit=N, broadcasts=True)

    `broadcasts=True` = 只要**频道/超级群**（不要私聊用户）。

    ## ⚠️ 与 `channels.SearchPosts` 的区别（不要混）

    真正"搜所有公开频道的**内容**"要用 `channels.SearchPosts`，
    它要 **Premium 且按 Stars 计费** —— 本项目**不做**（属于过度承诺）。

    本函数搜的是**频道实体**（名字/标题），不搜内容、不收费。

    ## 返回

    `TelegramChannel` 列表（title / username / subscribers），
    前端渲染成可点击的频道条目 → 点进去用「频道消息」读它的消息。
    """
    from telethon.tl.functions.contacts import SearchRequest

    kw = (keyword or "").strip()
    if not kw:
        return []

    out: List[TelegramChannel] = []
    try:
        found = await client(SearchRequest(
            q=kw, limit=max(1, min(limit, 100)), broadcasts=True,
        ))
        for ent in (getattr(found, "chats", None) or [])[:limit]:
            kind = type(ent).__name__
            if kind not in ("Channel", "Chat", "ChannelForbidden", "ChatForbidden"):
                continue
            username = getattr(ent, "username", "") or ""
            out.append(TelegramChannel(
                id=str(getattr(ent, "id", "")),
                username=username,
                title=getattr(ent, "title", "") or "",
                description=getattr(ent, "about", "") or "",
                subscribers=int(getattr(ent, "participants_count", 0) or 0),
                source="mtproto",
                raw_data={
                    "is_channel": bool(getattr(ent, "broadcast", False)),
                    "is_group": bool(getattr(ent, "megagroup", False)),
                },
            ))
    except Exception as exc:
        hint = _flood_wait_message(exc)
        if hint:
            raise RuntimeError(hint) from exc
        raise RuntimeError(
            f"[telegram] 搜频道失败：{type(exc).__name__}: {str(exc)[:150]}"
        ) from exc

    # 频道排前面，其次按订阅数
    out.sort(key=lambda c: (not c.raw_data.get("is_channel"), -c.subscribers))
    return out


async def list_saved_messages(
    client,
    limit: int = 50,
    query: str = "",
    offset_id: int = 0,
) -> List[TelegramMessage]:
    """**读取「收藏夹」（Saved Messages）**（A 方案绝对做不到）。

    ## 它是什么

    Telegram 客户端里那个固定的 **Saved Messages / 已收藏** 对话 ——
    你把任意消息、链接、文件转发进这个对话就等于收藏了。
    MTProto 里它就是你**自己**（`User`）与自己的对话历史：

        client.get_messages("me", limit=N)
                    ↓ 解析为
        messages.GetHistory(peer=InputPeerSelf)

    telethon 原生支持 `'me'` / `'self'` 这个写法
    （`get_input_entity` 里 `if peer in ('me','self'): return InputPeerSelf()`），
    不需要手工构造 `InputPeerSelf`。

    ## ⚠️ 与 `list_dialogs`（我的频道）是**两件不同的事**（2026-10-03 澄清）

    | 功能 | 数据源 | 实体类型 |
    |------|--------|---------|
    | **我的频道** | `iter_dialogs` | `Channel` / `Chat`（群组、频道） |
    | **我的收藏** | `get_messages('me')` | `User`（**你自己**） |

    `list_dialogs` 显式**跳过** `User`（私聊），
    所以收藏夹**永远不会**出现在「我的频道」列表里 —— 这是对的，
    它本来就不是一个"频道"。用户要的是两个都能看。

    ## 参数

    * `limit` —— 取多少条（客户端默认一页 20）
    * `query` —— 收藏夹内按关键词过滤
      （⚠️ 这是**你的收藏里**搜，不是全网；全网要 `channels.SearchPosts`，
      需 Premium 且按 Stars 计费 —— 本项目不做，见 `search_global` 的说明）
    * `offset_id` —— **向前翻**（取比该 id 更旧的），实现「加载更多」
    """
    kw = (query or "").strip()
    out: List[TelegramMessage] = []
    try:
        kwargs: Dict[str, Any] = {"limit": limit}
        if kw:
            kwargs["search"] = kw
        # ⚠️ `offset_id` 语义是"**从这条开始往前翻**"（比它更旧的），
        # 所以要用**本页最后一条的 id**，不是页码。
        # 不传则每次都从最新开始 → 前端点"下一页"会拿到完全重复的数据
        # （实测踩过：page=1 和 page=2 一模一样 10 条）。
        if offset_id:
            kwargs["offset_id"] = offset_id
        async for msg in client.iter_messages("me", **kwargs):
            # ⚠️ 收藏夹里什么都能存：文本、图片、视频、文件、纯链接转发。
            #    channel 一律标成 "saved"，前端据此显示「收藏」而不是频道名。
            m = await _msg_to_model(msg, channel="saved", channel_title="我的收藏")
            m.raw_data["is_saved"] = True
            out.append(m)
    except Exception as exc:
        hint = _flood_wait_message(exc)
        if hint:
            raise RuntimeError(hint) from exc
        raise RuntimeError(
            f"[telegram] 读取收藏夹失败：{type(exc).__name__}: {str(exc)[:150]}"
        ) from exc
    return out


async def fetch_channel_messages(
    client,
    channel: str,
    limit: int = 20,
    keyword: str = "",
) -> tuple[TelegramChannel, List[TelegramMessage]]:
    """用 MTProto 读某频道消息（**能读私有频道**，A 方案不行）。

    也支持频道内关键词（`search=` 参数）—— 与 A 方案的 `?q=` 等价，
    但这里能搜**私有频道**。
    """
    target = (channel or "").strip()
    if not target:
        raise RuntimeError("请填写频道（username、@username 或 t.me 链接）。")

    try:
        ent = await client.get_entity(target)
    except Exception as exc:
        hint = _flood_wait_message(exc)
        if hint:
            raise RuntimeError(hint) from exc
        raise RuntimeError(
            f"[telegram] 找不到频道 {target!r}（{type(exc).__name__}）。\n"
            "可能：① 拼写错误；② 私有频道需先加入；"
            "③ 公开频道可以改用「频道消息」tab（免登录）。"
        ) from exc

    title = getattr(ent, "title", "") or ""
    username = getattr(ent, "username", "") or ""
    info = TelegramChannel(
        id=str(getattr(ent, "id", "")),
        username=username,
        title=title,
        subscribers=int(getattr(ent, "participants_count", 0) or 0),
        source="mtproto",
    )

    out: List[TelegramMessage] = []
    try:
        kwargs: Dict[str, Any] = {"limit": limit}
        if keyword.strip():
            kwargs["search"] = keyword.strip()
        async for msg in client.iter_messages(ent, **kwargs):
            out.append(await _msg_to_model(msg, channel=username or target, channel_title=title))
    except Exception as exc:
        hint = _flood_wait_message(exc)
        if hint:
            raise RuntimeError(hint) from exc
        raise RuntimeError(
            f"[telegram] 读取频道消息失败：{type(exc).__name__}: {str(exc)[:150]}"
        ) from exc

    out.sort(key=lambda m: int(m.id) if m.id.isdigit() else 0)
    return info, out
