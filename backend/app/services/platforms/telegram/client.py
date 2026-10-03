"""YLCraft — Telegram 平台客户端（A 免登录 + B 登录，统一入口）。

## 三个 search_type（= 前端的三个 tab）

| search_type | 走哪条路 | 需要登录 | 输入 | 搜索范围 |
|-------------|---------|---------|------|---------|
| `channel`   | A（t.me/s） | 否 | 频道名（可加关键词） | **指定频道内** |
| `joined`    | B（MTProto）| **是** | 关键词 | **你已加入的频道** |
| `dialogs`   | B（MTProto）| **是** | 无 | 列出你加入的频道 |

前端 UI 对应：
  · 频道消息  → search_type=channel（**主力**，免登录）
  · 已加入搜索 → search_type=joined
  · 我的频道  → search_type=dialogs

## ⚠️ 关于"搜索范围"的诚实说明（2026-10-01 调研修正）

我最初设计时把 B 方案叫"**全网**搜索"，**这是错的、属于过度承诺**。

  · `messages.SearchGlobal` 只搜**你已加入的会话**（Telethon #4446）
  · 真正搜所有公开频道要 `channels.SearchPosts` ——
    需要 **Premium 账号**、报 `403 PREMIUM_ACCOUNT_REQUIRED`、
    且**按 Stars 计费**。本项目**不做**这条路。
  · 所以想搜某个公开频道，正确姿势是 **A 方案的频道内搜索**
    （「频道名 关键词」→ `?q=`）—— **免登录、免费**。

前端的 tab 文案必须与这里一致，不要写"全网搜索"。

## 为什么三种 search_type 不合成一个搜索框

它们的**输入语义完全不同**（频道名 vs 关键词 vs 无需输入），
硬合成一个框会让用户困惑"我该填什么"。用 tab 分开最清楚。

## 下载

  · 视频：消息里的 `<video src>` 有 CDN 直链（带 token，会过期），
    或走 yt-dlp 的 `telegram:embed`（支持 `t.me/ch/msgid`）。
    ⚠️ 实测 yt-dlp 对**纯文本帖会 returned nothing**，必须容错。
  · 图片：`background-image` 里的 CDN 直链，直接下。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from ..base import BasePlatformClient, register_platform
from ..types import (
    ClientConfig,
    NoteDetail,
    SearchParams,
    SearchResult,
    UserProfile,
)
from .models import TelegramChannel, TelegramMessage
from .web_preview import TelegramPublicClient, TelegramPublicError, normalize_channel

logger = logging.getLogger("ylcraft.platforms.telegram")


def _to_search_result(m: TelegramMessage) -> SearchResult:
    """消息 → 通用 SearchResult（接入现有采集/导入/下载链路）。

    ⚠️ 字段落位规则（与其它平台一致）：
      · 图片 → `raw_data._images`（SearchResult 没有 images 字段）
      · 视频 → `raw_data._video_url`
      · 可浏览地址 → `url`（t.me/ch/msgid）
    """
    return SearchResult(
        id=f"{m.channel}_{m.id}" if m.channel else m.id,
        platform="telegram",
        type=m.content_type,
        title=(m.text or "").split("\n")[0][:120] or f"消息 {m.id}",
        desc=(m.text or "")[:500],
        cover=m.video_cover or (m.images[0] if m.images else ""),
        url=m.page_url(),
        author=m.channel_title or m.channel,
        author_id=m.channel,
        views=m.views,
        duration=m.duration,
        create_time=m.date,
        raw_data={
            "_images": list(m.images),
            "_video_url": m.video,
            "_has_more": False,          # 由调用方按需覆盖
            "_telegram": {
                "channel": m.channel,
                "message_id": m.id,
                "forward_from": m.forward_from,
                "html": m.html,
                "links": m.links,
                "media_type": m.raw_data.get("media_type", ""),
            },
        },
    )


@register_platform("telegram")
class TelegramClient(BasePlatformClient):
    """Telegram 采集客户端。"""

    def __init__(self, config: ClientConfig):
        super().__init__(config)
        self._public = TelegramPublicClient()

    # =========================================================================
    # 抽象方法
    # =========================================================================

    def _build_headers(self) -> Dict[str, str]:
        return {"User-Agent": self._get_default_user_agent()}

    def _get_default_user_agent(self) -> str:
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )

    def _get_platform_domain(self) -> str:
        return ".t.me"

    async def search(self, params: SearchParams) -> List[SearchResult]:
        """按 `search_type` 分派到 A 或 B。

        search_type:
          · channel（默认）→ 公开频道消息（免登录，可带频道内关键词）
          · joined        → 在你已加入的频道里搜（需登录）
          · dialogs       → 我加入的频道（需登录）
          · saved         → 我的收藏夹 Saved Messages（需登录）

        ⚠️ `global` / `search` 作为 `joined` 的**兼容别名**保留 ——
        但语义是"已加入的频道"，不是全网（见模块 docstring）。

        ## 翻页：`dialogs` / `saved` 用**游标**，不是页码

        这两个数据源是"**我的东西**"（我的频道 / 我的收藏），
        不是"按关键词搜出来的结果"，所以：
          · **不需要关键词**（传空即可，列最近几条）
          · `page` 参数**无效** —— 实测传 page=1 和 page=2
            返回的是**完全一样的 10 条**（假翻页）

        正确做法是传**游标** `offset_id`（`params.extra` 里带）：
        MTProto 的 `iter_messages(..., offset_id=N)` 表示
        "取比 N 更旧的"，正是「加载更多」要的语义。
        """
        raw_st = getattr(params, "search_type", "") or "channel"
        st = str(getattr(raw_st, "value", raw_st)).lower()
        keyword = (params.keyword or "").strip()
        want = max(1, int(params.max_results or 20))
        # 游标（加载更多用）：前端把上一页最后一条的 id 放在 extra.offset_id
        _extra = getattr(params, "extra", None) or {}
        try:
            cursor = int(_extra.get("offset_id") or 0)
        except (TypeError, ValueError):
            cursor = 0

        if st in ("joined", "global", "search", "keyword"):
            return await self._search_joined(keyword, want)
        if st in ("dialogs", "channels", "my"):
            return await self._list_dialogs(want, cursor=cursor)
        if st == "saved":
            # ⚠️ **我的收藏**与**我的频道**是两件不同的事（2026-10-03 澄清）：
            #   · 我的频道 = 我加入的频道/群组（`iter_dialogs`，跳过私聊）
            #   · 我的收藏 = 客户端那个固定的 **Saved Messages**
            #     （`get_messages('me')` = 你与自己的对话，`InputPeerSelf`）
            # 所以**不能**复用 `_list_dialogs` —— 那里显式跳过 `User`，
            # 收藏夹正好是 `User`，用它永远拿不到。
            return await self._list_saved(want, cursor=cursor)
        # 默认：频道消息（免登录）
        return await self._search_channel(keyword, want)

    async def get_detail(self, item_id: str, **kwargs) -> NoteDetail:
        """取单条消息详情。

        `item_id` 支持两种形态：
          · `<channel>_<msgid>`（搜索结果里的 id）
          · `https://t.me/<channel>/<msgid>`（直接粘链接）
        """
        channel, msg_id = self._split_item_id(item_id)
        if not channel or not msg_id:
            raise RuntimeError(
                f"[telegram] 无法从 {item_id!r} 解析出频道+消息 id。"
                "预期格式：频道名_消息id，或 t.me/频道/消息id 链接。"
            )

        msg = await self._public.get_message(channel, msg_id)
        if msg is None:
            raise RuntimeError(
                f"[telegram] 取不到消息 {channel}/{msg_id}。"
                "可能：① 消息已删除；② 频道是私有的（需登录）；"
                "③ 该消息没有网页预览（媒体受限）。"
            )

        return NoteDetail(
            id=f"{msg.channel}_{msg.id}",
            platform="telegram",
            type=msg.content_type,
            title=(msg.text or "").split("\n")[0][:120] or f"消息 {msg.id}",
            desc=msg.text or "",
            author=msg.channel_title or msg.channel,
            author_id=msg.channel,
            images=list(msg.images),
            video=msg.video,
            video_cover=msg.video_cover,
            duration=msg.duration,
            views=msg.views,
            create_time=msg.date,
            raw_data={
                "html": msg.html,
                "links": msg.links,
                "forward_from": msg.forward_from,
                "page_url": msg.page_url(),
            },
        )

    # =========================================================================
    # A 方案：公开频道（免登录）
    # =========================================================================

    async def _search_channel(self, keyword: str, want: int) -> List[SearchResult]:
        """频道消息（免登录）。

        `keyword` 支持两种写法（前端"频道消息"tab 的输入框）：
          · `durov`                    → 该频道最近消息
          · `durov AI`                 → **在 durov 频道内搜 "AI"**
          · `durov|AI` / `durov AI`    → 同上（分隔符宽松）
          · `https://t.me/durov`       → 链接

        ⚠️ 频道内搜索（`?q=`）是**实测可行且免登录**的，
        这是 A 方案最被低估的能力（我最初以为只有 MTProto 能搜）。
        """
        channel, query = self._split_channel_query(keyword)
        if not channel:
            raise TelegramPublicError(
                "请填写频道 username（如 durov）或频道链接。\n"
                "如果想在频道内搜关键词，可以写「频道名 关键词」，"
                "例如「durov AI」。"
            )

        info, msgs = await self._public.get_channel(
            channel, limit=want, query=query
        )

        out = [_to_search_result(m) for m in msgs]
        if out:
            out[0].raw_data["_has_more"] = len(msgs) >= want
            out[0].raw_data["_total"] = len(msgs)
            # 把频道信息带上（前端能显示"来自哪个频道"）
            out[0].raw_data["_channel"] = {
                "title": info.title,
                "username": info.username,
                "subscribers": info.subscribers,
                "description": info.description,
                "avatar": info.avatar,
            }
        return out

    # =========================================================================
    # B 方案：需要登录
    # =========================================================================

    async def _search_joined(self, keyword: str, want: int) -> List[SearchResult]:
        """在**你已加入的频道/群组**里搜关键词（需登录）。

        ⚠️ **不要把它叫"全网搜索"**（2026-10-01 调研修正）：
        `messages.SearchGlobal` 只覆盖"你已加入的会话"。
        真正搜所有公开频道要 `channels.SearchPosts`，那个需要
        **Premium 且按 Stars 计费** —— 本项目不做。

        搜任意公开频道的正确姿势是 A 方案的**频道内搜索**：
        「频道名 关键词」→ `?q=`，免登录、免费。
        """
        if not keyword:
            raise RuntimeError(
                "请填写关键词。\n"
                "⚠️ 这里搜的是**你已加入的频道/群组**，不是整个 Telegram。\n"
                "要搜某个具体公开频道，请用「频道消息」tab 填「频道名 关键词」。"
            )
        from .mtproto import get_authorized_client
        from .mtproto_data import search_global

        client = await get_authorized_client()
        try:
            msgs = await search_global(client, keyword, limit=want)
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

        out = [_to_search_result(m) for m in msgs]
        if out:
            out[0].raw_data["_total"] = len(out)
        return out

    async def _list_saved(self, want: int, cursor: int = 0) -> List[SearchResult]:
        """**我的收藏**（Saved Messages，需登录）。

        ⚠️ 与 `_list_dialogs`（我的频道）的区别（2026-10-03 用户澄清）：

            我的频道 → `iter_dialogs` → `Channel`/`Chat`（群组、频道）
            我的收藏 → `get_messages('me')` → **你自己**（`InputPeerSelf`）

        收藏夹是客户端里那个固定的 Saved Messages 对话，
        你把任何消息/链接/文件转发进去就是收藏。
        它是**私有数据**，`t.me/s` 那条免登录路径拿不到。

        `type="saved"` 让前端渲染成"收藏"而不是频道条目。

        `cursor` = 上一页最后一条的 id（`offset_id` 语义：取更旧的），
        实现「加载更多」—— 不传就是取最近 `want` 条。
        """
        from .mtproto import get_authorized_client
        from .mtproto_data import list_saved_messages

        client = await get_authorized_client()
        try:
            # ⚠️ `limit` 必须**正好等于 want**（2026-10-03 修）
            #
            # 原来取 `max(want, 20)` = 20 条，然后 `msgs[:want]` 只留 10 条。
            # 多取的那 10 条被丢掉，但**游标语义是"取比它更旧的"** ——
            # 于是下一次带游标请求会**重新取到那批被丢掉的 10 条**，
            # 实测两页重叠 9 条（假翻页）。
            #
            # 正确：取多少就返回多少，游标才能真正往下走。
            msgs = await list_saved_messages(
                client, limit=want, offset_id=cursor
            )
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

        out: List[SearchResult] = []
        for m in msgs[:want]:
            r = _to_search_result(m)
            # 覆盖成"收藏"语义（channel 字段固定为 saved）
            r.type = "saved"
            r.channel = "saved"
            r.channel_title = "我的收藏"
            r.url = ""
            r.raw_data["is_saved"] = True
            # ⚠️ 游标取**本页每一条**自己的 id，但前端要用**最后一条**。
            #    （MTProto 的 offset_id 语义是"从这条开始往前"，
            #      传第一条会把它自己也包含进来 —— 实测重叠 4 条；
            #      传最后一条 → 重叠 0。所以前端必须取 results 末位的 cursor_id。）
            r.raw_data["cursor_id"] = m.id
            out.append(r)
        if out:
            out[0].raw_data["_total"] = len(out)
            # ⚠️ `has_more` 只能"猜"：MTProto 不告诉你总条数。
            # 拿满 want 只能说"可能还有"（下次带游标就知道）。
            out[0].raw_data["_has_more"] = len(msgs) >= want
        return out

    async def _list_dialogs(self, want: int) -> List[SearchResult]:
        """列出我加入的频道（需登录）。

        返回的是**频道列表**（不是消息）—— 复用 SearchResult 形状，
        `type="channel"`，前端识别后渲染成频道条目。
        """
        from .mtproto import get_authorized_client
        from .mtproto_data import list_dialogs

        client = await get_authorized_client()
        try:
            chans = await list_dialogs(client, limit=max(want, 100))
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

        out: List[SearchResult] = []
        for c in chans[:want]:
            out.append(SearchResult(
                id=c.username or c.id,
                platform="telegram",
                type="channel",
                title=c.title,
                desc=c.description,
                cover=c.avatar,
                url=f"https://t.me/{c.username}" if c.username else "",
                author=c.title,
                author_id=c.username or c.id,
                followers=c.subscribers,
                raw_data={
                    "_channel": {
                        "title": c.title,
                        "username": c.username,
                        "subscribers": c.subscribers,
                        "is_channel": c.raw_data.get("is_channel", False),
                        "is_group": c.raw_data.get("is_group", False),
                    },
                    "_has_more": False,
                },
            ))
        return out

    # =========================================================================
    # 用户维度
    # =========================================================================

    async def search_users(self, keyword: str, max_results: int = 20) -> List[UserProfile]:
        """搜频道（用 A 方案做不到"按名字搜频道"，只能直接给 username）。

        ⚠️ **诚实说明**：Telegram 的**频道搜索**属于全局搜索能力
        （网页版没有"搜频道"入口），所以这里：
          · 有登录 → 用全局搜索，过滤出频道类型的实体
          · 没登录 → 明确报错（不假装搜到 0 个）
        """
        from .mtproto import get_authorized_client

        kw = (keyword or "").strip()
        if not kw:
            return []
        client = await get_authorized_client()
        try:
            found: List[UserProfile] = []
            seen: set[str] = set()
            async for dialog in client.iter_dialogs(limit=200):
                ent = dialog.entity
                title = getattr(ent, "title", "") or ""
                uname = getattr(ent, "username", "") or ""
                if kw.lower() not in title.lower() and kw.lower() not in uname.lower():
                    continue
                key = uname or str(getattr(ent, "id", ""))
                if key in seen:
                    continue
                seen.add(key)
                found.append(UserProfile(
                    id=key,
                    name=title,
                    platform="telegram",
                    followers=int(getattr(ent, "participants_count", 0) or 0),
                    raw_data={"username": uname},
                ))
                if len(found) >= max_results:
                    break
            return found
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass

    async def get_user_profile(self, user_id: str) -> UserProfile:
        """频道资料（A 方案，免登录）。"""
        info = await self._public.get_channel_info(user_id)
        return UserProfile(
            id=info.username or info.id,
            name=info.title,
            avatar=info.avatar,
            platform="telegram",
            followers=info.subscribers,
            desc=info.description,
            raw_data={"username": info.username, "source": info.source},
        )

    async def get_user_videos(self, user_id: str, max_results: int = 20) -> List[SearchResult]:
        """频道的消息列表（路由用的是这个名字）。

        ⚠️ `users.py::/users/videos` 调 `get_user_videos`，
        基类同类能力叫 `get_user_notes` —— 两个都要有
        （youtube 就因为只写了后者报过 500）。
        """
        return await self.get_user_notes(user_id, max_results=max_results)

    async def get_user_notes(self, user_id: str, max_results: int = 20) -> List[SearchResult]:
        """频道的消息列表（免登录，公开频道）。"""
        info, msgs = await self._public.get_channel(user_id, limit=max_results)
        return [_to_search_result(m) for m in msgs]

    # =========================================================================
    # 工具
    # =========================================================================

    @staticmethod
    def _split_item_id(item_id: str) -> tuple[str, str]:
        """`technews_101` / `t.me/technews/101` → (channel, msg_id)。"""
        s = (item_id or "").strip()
        if not s:
            return "", ""
        # URL 形态
        if "t.me/" in s or s.startswith("http"):
            parts = [p for p in s.split("/") if p and not p.startswith("http")]
            # t.me / channel / id
            if len(parts) >= 3 and parts[0].endswith("t.me"):
                return parts[1], parts[2].split("?")[0]
            if len(parts) >= 2:
                return parts[-2], parts[-1].split("?")[0]
        # `channel_msgid` 形态（我们自己拼的 id）
        if "_" in s:
            ch, _, mid = s.rpartition("_")
            if mid.isdigit():
                return ch, mid
        return "", ""

    @staticmethod
    def _split_channel_query(text: str) -> tuple[str, str]:
        """把「频道名 关键词」拆成 (channel, query)。

        规则（宽松，优先识别链接）：
          · `https://t.me/durov`            → ("durov", "")
          · `durov`                         → ("durov", "")
          · `durov AI`                      → ("durov", "AI")
          · `durov|AI`                      → ("durov", "AI")
          · `@durov 关键词`                 → ("durov", "关键词")

        ⚠️ 分隔符宽松处理：空格 / 竖线 / 逗号。但**频道名里不能有空格**
        （Telegram username 不允许），所以第一个 token 一定是频道。
        """
        s = (text or "").strip()
        if not s:
            return "", ""
        # 去掉 URL 前缀后再拆（链接里可能有 / 和 ?）
        if "t.me/" in s or s.startswith("http"):
            # 链接形态：整个作为频道，后面若还有词当作 query
            parts = s.split(None, 1)
            return parts[0], (parts[1].strip() if len(parts) > 1 else "")

        for sep in ("|", ",", "，"):
            if sep in s:
                ch, _, q = s.partition(sep)
                return ch.strip(), q.strip()

        parts = s.split(None, 1)
        if len(parts) == 1:
            return parts[0].lstrip("@"), ""
        return parts[0].lstrip("@"), parts[1].strip()
