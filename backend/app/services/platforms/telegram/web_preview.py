"""YLCraft — Telegram 公开频道抓取（A 方案，免登录）。

## 能力边界（⚠️ 2026-10-01 实测更正 —— 比我最初以为的强）

`t.me/s/<username>` 可以：
  · 看**公开频道**的消息（实测一页固定 20 条）
  · ✅ **频道内关键词搜索**：`?q=<关键词>`（**免登录！**）
  · 翻页：`?before=<msg_id>`（往前）/ `?after=<msg_id>`（往后）
  · `q` 与 `before` **可以组合**

**不能**：
  · ❌ **跨频道全局搜索** —— 实测 `t.me/search?q=x` 会把 "search"
    当成用户名，返回 "Contact @search" 空页。全局搜索只能走 MTProto。
  · ❌ 看私有频道 / 你的账号 / 你加入的频道（需登录）
  · ❌ 看需要 join 才能浏览的受限频道

## ⚠️ 我最初写错的几点（实测纠正，别再犯）

1. ~~"t.me/s 不支持关键词搜索"~~ → **错**。页面上那个搜索框就是
   `<form action="/s/durov"><input name="q">`。实测 `?q=Telegram`
   返回 20 条且正文全部命中；`?q=Apple` 返回跨历史的非连续 ID；
   `?q=zzzqqqxx` 返回 0 条。
2. ~~"频道不存在返回 404"~~ → **错**。实测返回 **HTTP 200**
   + telegram.org 主页壳（~19KB，零个 tgme_* 元素）。
   **必须靠 `tgme_channel_info` 是否存在判断**，不能看状态码。
3. ~~"视频拿不到直链"~~ → **错**。`<video src>` 有直链
   （但带 token 会过期，只适合即时下载）。

## 为什么不用第三方库

`t.me/s` 就是服务端渲染好的 HTML，`beautifulsoup4` + `lxml`
（项目已装）足够。社区上的 telegram-scraper 之类多半也是解析同一个
页面，或是走 MTProto 需要登录 —— 多一层不可控依赖。

## ⚠️ 代理（实测）

本机 t.me 直连会超时，需要走代理。代码从**环境变量**
（`HTTPS_PROXY`/`HTTP_PROXY`）或 Windows 系统代理读取，
**不要硬编码端口**（换台机器就不同了）。
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import List, Optional, Tuple

import httpx

from .models import TelegramChannel, TelegramMessage
from .parser import detect_structure_change, parse_channel_page
from ..types import NetworkError, RiskControlError

logger = logging.getLogger("ylcraft.platforms.telegram")

BASE = "https://t.me"

# ⚠️ 用桌面 UA —— 移动 UA 会拿到不同的页面模板
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# 实测：一页固定 20 条（活跃频道）
PAGE_SIZE = 20


def _proxy_from_env() -> Optional[str]:
    """从环境变量 / Windows 系统代理取代理地址。

    ⚠️ 实测：本机 t.me 直连超时，需要 `http://127.0.0.1:10090`。
    但不硬编码 —— 换机器端口不同。优先环境变量，其次 IE 设置。
    """
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        v = os.environ.get(key)
        if v:
            return v
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
        ) as k:
            enable, _ = winreg.QueryValueEx(k, "ProxyEnable")
            if enable:
                server, _ = winreg.QueryValueEx(k, "ProxyServer")
                if server:
                    return server if "://" in server else f"http://{server}"
    except Exception:
        pass
    return None


class TelegramPublicError(RiskControlError):
    """公开预览页抓取失败（可读原因）。

    与"频道没有消息"区分：这里是"拿不到 / 结构变了"。

    ## ⚠️ 2026-10-01：挂到类型化异常体系下

    继承 `RiskControlError`（`retryable=False` / `should_fallback=False`）——
    因为绝大多数情况是频道不存在 / 私有 / 结构变化，
    这些**重试和降级都没用**。

    ⚠️ **但网络类失败是例外**：`fetch_page` 在检测到
    超时/连不上时会改抛 `NetworkError`（可重试、可降级），
    见那里的实现 —— 否则"VPN 断了"会被当成"频道不存在"，
    用户会去反复检查用户名（明明没拼错）。
    """


_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{4,64}$")


def normalize_channel(text: str) -> str:
    """把用户输入的各种形态归一成 username。

    支持：
        durov
        @durov
        https://t.me/durov
        https://t.me/s/durov
        t.me/durov/123      ← 带消息 id，只取频道部分
        https://telegram.me/durov

    ⚠️ **保留原始大小写**（实测 `data-post` 有 `TGStat/468` 这种大写 T）——
    不要 `.lower()`。

    非法输入抛 `TelegramPublicError`（**可操作**提示，不静默返回空）。
    """
    s = (text or "").strip()
    if not s:
        raise TelegramPublicError(
            "频道名为空。请输入频道 username（如 durov）或频道链接。"
        )

    # 去掉 URL 前缀
    s = re.sub(r"^https?://", "", s, flags=re.I)
    s = re.sub(r"^(www\.)?(t|telegram)\.me/", "", s, flags=re.I)
    s = re.sub(r"^s/", "", s, flags=re.I)
    # 去掉结尾的 /123（消息 id）与查询串
    s = s.split("?")[0].split("#")[0].strip("/")
    if "/" in s:
        s = s.split("/")[0]
    s = s.lstrip("@")

    # ⚠️ `+xxxx` 是**邀请链接**（私有频道），公开预览页看不了
    if s.startswith("+"):
        raise TelegramPublicError(
            "这是**私有频道的邀请链接**，公开预览页（t.me/s）看不了。\n"
            "私有频道需要登录 Telegram 账号后读取（见「我的频道」）。"
        )
    if s.lower() == "joinchat":
        raise TelegramPublicError(
            "这是**私有群组邀请链接**，公开预览页看不了。"
            "需要登录 Telegram 账号后才能读取。"
        )

    if not _USERNAME_RE.match(s):
        raise TelegramPublicError(
            f"频道名 {s!r} 看起来不合法（只允许字母/数字/下划线，4-64 位）。"
            "请检查输入，或直接粘贴频道链接。"
        )
    return s


class TelegramPublicClient:
    """公开频道抓取（免登录）。"""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.proxy = _proxy_from_env()

    async def fetch_page(
        self,
        username: str,
        before: Optional[str] = None,
        after: Optional[str] = None,
        query: Optional[str] = None,
    ) -> str:
        """抓一页 HTML。

        Args:
            before: 取**该 id 之前**的消息（往前翻）
            after:  取**该 id 之后**的消息（往后翻）
            query:  **频道内关键词过滤**（实测有效，免登录）
        """
        url = f"{BASE}/s/{username}"
        params: dict = {}
        if before:
            params["before"] = before
        if after:
            params["after"] = after
        if query:
            params["q"] = query
        headers = {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
        }
        kwargs: dict = {
            "timeout": self.timeout,
            "follow_redirects": True,
            "headers": headers,
        }
        if self.proxy:
            kwargs["proxy"] = self.proxy

        last_err: Optional[Exception] = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(**kwargs) as c:
                    resp = await c.get(url, params=params or None)
                # ⚠️ **不能靠 404 判断频道不存在** —— 实测不存在时返回
                # HTTP 200 + telegram.org 主页壳。这里只处理真错误码。
                if resp.status_code == 429:
                    raise TelegramPublicError(
                        "[telegram] 被限流（HTTP 429）。请稍后重试 —— "
                        "短时间内请求过多会被 Telegram 临时拒绝。"
                    )
                if resp.status_code >= 400:
                    raise TelegramPublicError(
                        f"[telegram] 抓取 @{username} 失败：HTTP {resp.status_code}"
                    )
                return resp.text
            except TelegramPublicError:
                raise
            except Exception as exc:
                last_err = exc
                if attempt < 2:
                    await asyncio.sleep(1.5 * (attempt + 1))

        msg = str(last_err)
        if any(k in msg.lower() for k in ("timeout", "connect", "resolve", "proxy")):
            hint = (
                f"（已尝试代理 {self.proxy}）" if self.proxy
                else "（未检测到代理设置）"
            )
            # ⚠️ 网络问题抛 `NetworkError`（不是 TelegramPublicError）——
            # 它声明 retryable=True / should_fallback=True，
            # 而"频道不存在/私有"是 TelegramPublicError（不可重试）。
            # 两者混在一起的话，"VPN 断了"会被当成"频道名拼错了"，
            # 用户会去反复检查一个没拼错的名字（2026-10-01）。
            raise NetworkError(
                f"[telegram] 无法连接 t.me（{type(last_err).__name__}）{hint}。"
                "请确认 **VPN 已开启**；若 VPN 是 PAC/规则模式，"
                "可能需要给 python 进程设置 HTTPS_PROXY 环境变量。"
            ) from last_err
        raise TelegramPublicError(f"[telegram] 抓取失败：{msg[:200]}") from last_err

    async def get_channel(
        self,
        channel: str,
        limit: int = PAGE_SIZE,
        before: Optional[str] = None,
        query: str = "",
    ) -> Tuple[TelegramChannel, List[TelegramMessage]]:
        """取频道信息 + 消息（可选关键词过滤 + 自动翻页）。

        ## ⚠️ 翻页要**循环抓**，不能只抓一页

        实测每页固定 20 条，更多要连续翻（`?before=` 用本页最早一条）。
        这里按 `limit` 自动翻页（最多 MAX_PAGES 页，防打爆）。
        """
        username = normalize_channel(channel)
        want = max(1, int(limit or PAGE_SIZE))
        MAX_PAGES = 5  # 最多 5 页（约 100 条）—— 再多应该用登录方案

        channel_info: Optional[TelegramChannel] = None
        collected: List[TelegramMessage] = []
        seen: set[str] = set()
        cursor = before

        for page_no in range(MAX_PAGES):
            html = await self.fetch_page(username, before=cursor, query=query or None)
            info, msgs = parse_channel_page(html)

            if channel_info is None:
                channel_info = info
                if not channel_info.title:
                    channel_info.title = username
                channel_info.username = username
                channel_info.id = username

            if not msgs:
                # 只有**第一页**没消息才可疑（后续页空 = 正常到底）
                if page_no == 0:
                    reason = detect_structure_change(html)
                    if reason:
                        raise TelegramPublicError(f"[telegram] {reason}")
                break

            new = 0
            for m in msgs:
                if m.id in seen:
                    continue
                seen.add(m.id)
                m.channel = m.channel or username
                m.channel_title = m.channel_title or channel_info.title
                collected.append(m)
                new += 1

            if len(collected) >= want or new == 0:
                break
            cursor = msgs[0].id

        # 按 id 升序更自然（页面升序，翻页后是倒着的）
        collected.sort(key=lambda m: int(m.id) if m.id.isdigit() else 0)
        return channel_info, collected[:want]

    async def get_message(self, channel: str, msg_id: str) -> Optional[TelegramMessage]:
        """取**单条消息**（`?embed=1&single`，yt-dlp 走的就是这条路）。

        为什么需要：频道页只能看最近若干条，而**单条 embed 页能拿到
        任意历史消息**（只要知道 id）。
        """
        from .parser import parse_single_message

        username = normalize_channel(channel)
        url = f"{BASE}/{username}/{msg_id}"
        headers = {"User-Agent": UA, "Accept": "text/html,*/*"}
        kwargs: dict = {
            "timeout": self.timeout,
            "follow_redirects": True,
            "headers": headers,
        }
        if self.proxy:
            kwargs["proxy"] = self.proxy
        try:
            async with httpx.AsyncClient(**kwargs) as c:
                resp = await c.get(url, params={"embed": "1", "single": ""})
            if resp.status_code >= 400:
                return None
            msg = parse_single_message(resp.text)
            if msg is not None:
                msg.channel = msg.channel or username
                if not msg.id:
                    msg.id = str(msg_id)
            return msg
        except Exception as exc:
            logger.warning(
                "[telegram] 取单条消息失败 %s/%s: %s", username, msg_id, exc
            )
            return None

    async def get_channel_info(self, channel: str) -> TelegramChannel:
        """只取频道信息（不抓消息，快）。"""
        username = normalize_channel(channel)
        html = await self.fetch_page(username)
        info, _ = parse_channel_page(html)
        if not info.title:
            info.title = username
        info.username = username
        info.id = username
        return info

    async def resolve_username(self, channel: str) -> str:
        """把各种输入归一成 username（供上层复用）。"""
        return normalize_channel(channel)


def channel_exists(html: str) -> bool:
    """判断页面是否是一个**真实存在的频道**。

    ⚠️ **不能看 status_code** —— 实测频道不存在时返回的是
    HTTP 200 + telegram.org 主页壳（零个 tgme_* 元素）。
    判据：有没有 `tgme_channel_info` / `tgme_widget_message`。
    """
    if not html:
        return False
    return "tgme_channel_info" in html or "tgme_widget_message" in html
