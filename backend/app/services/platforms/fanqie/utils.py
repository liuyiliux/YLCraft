"""
YLCraft — 番茄小说工具函数

包含：
  - 异常类型（按番茄返回 code/message 分类）
  - Netscape / 原始 Cookie 解析与规范化
  - Markdown → 番茄正文 HTML（<p> 段落）转换
  - 从 Cookie 中提取作家标识（writer_id）
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List
import html as _html

logger = logging.getLogger("ylcraft.platforms.fanqie.utils")


# =============================================================================
# 异常类型
# =============================================================================

class FanqieError(Exception):
    """番茄接口通用异常"""


class CookieExpiredError(FanqieError):
    """登录态失效（需重新登录番茄，刷新 cookie）"""


class ParamError(FanqieError):
    """请求参数错误（book_id / item_id 不对、缺少字段等）"""


class RiskControlError(FanqieError):
    """触发风控 / 内容审核拦截"""


# 登录失效常见 code / 关键词
_LOGIN_EXPIRED_CODES = {-100, -101, -102, 10001, 10002}
_LOGIN_EXPIRED_KEYWORDS = ("未登录", "登录失效", "请先登录", "login", "not login", "登录过期")


def classify_fanqie_error(code: int, message: str) -> FanqieError:
    """根据返回 code / message 生成对应异常类型"""
    msg = (message or "").lower()
    raw_msg = message or ""

    if code in _LOGIN_EXPIRED_CODES or any(k in raw_msg for k in _LOGIN_EXPIRED_KEYWORDS):
        return CookieExpiredError(f"番茄登录态失效（code={code}）：{message or '未知'}")

    if code in (-110, -111) or "参数" in raw_msg or "param" in msg or "缺失" in raw_msg:
        return ParamError(f"番茄请求参数错误（code={code}）：{message or '未知'}")

    if "风险" in raw_msg or "风控" in raw_msg or "审核" in raw_msg or "risk" in msg:
        return RiskControlError(f"番茄触发风控/审核（code={code}）：{message or '未知'}")

    return FanqieError(f"番茄接口返回失败（code={code}）：{message or '未知'}")


# =============================================================================
# Cookie 解析 / 规范化
# =============================================================================

def parse_netscape_cookie(text: str) -> Dict[str, str]:
    """
    解析 Netscape cookie 文件格式为 {name: value} 字典。

    Netscape 格式示例：
        # Netscape HTTP Cookie File
        fanqienovel.com\tFALSE\t/\tFALSE\t0\tsessionid\tabc123

    Args:
        text: Netscape 格式文本（可能为多行，含 # 注释行）

    Returns:
        {cookie_name: cookie_value}
    """
    cookies: Dict[str, str] = {}
    if not text:
        return cookies

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Netscape 格式用 \t 分隔，第 6 列为 name，第 7 列为 value
        parts = line.split("\t")
        if len(parts) >= 7:
            name, value = parts[5], parts[6]
        elif "=" in line:
            # 兼容裸 "name=value" 行
            name, value = line.split("=", 1)
        else:
            continue
        cookies[name.strip()] = value.strip()

    return cookies


def normalize_cookie(cookie_str: str) -> str:
    """
    将任意格式的 cookie 规范化为可直接放入 HTTP `Cookie` 头的字符串。

    ⚠️ 命名陷阱（务必读完）：
    `CookieManager` 里也有一个 `normalize_cookie(platform, content)`，**名字相同但方向相反**
    ——那个是「转成 Netscape 文件」，本函数是「转成可放进 header 的 `k=v; k2=v2`」。
    两者不可互换。新代码请优先用 `BasePlatformClient.header_cookie()`（公共基类，唯一实现）。

    本函数已改为委托给公共的 `CookieManager.extract_raw()`：实测对 Netscape / `k=v` / 空
    三种输入与原实现输出**完全一致**，并额外支持 JSON 数组（浏览器扩展导出）输入——原实现
    对 JSON 数组会原样返回，导致整段 JSON 被塞进 Cookie 头。

    Args:
        cookie_str: 任意格式的 cookie 文本

    Returns:
        可直接用于 `headers["Cookie"] = ...` 的字符串
    """
    if not cookie_str:
        return ""
    try:
        from app.services.cookies.manager import CookieManager

        return CookieManager().extract_raw(cookie_str) or ""
    except Exception:  # noqa: BLE001 - 规范化失败时回退到原实现，绝不因解析问题阻塞请求
        s = cookie_str.strip()
        if "\t" in s or s.startswith("# Netscape"):
            parsed = parse_netscape_cookie(s)
            return "; ".join(f"{k}={v}" for k, v in parsed.items())
        return "; ".join(seg.strip() for seg in s.split(";") if seg.strip())


def extract_writer_id_from_cookie(cookie_str: str) -> str:
    """
    从 Cookie 中尽力提取番茄作家标识（writer_id）。

    番茄作家后台 URL 形如 /main/writer/{writer_id}/publish/{book_id}。
    但 writer_id 通常不直接出现在 cookie 中；这里退而求其次：
      - 优先返回 cookie 中的 `sessionid`（作为登录态标识，可用于诊断）
      - 若调用方已通过接口拿到真实 writer_id，应以接口返回为准

    Args:
        cookie_str: 任意格式 cookie

    Returns:
        writer_id 或 sessionid 或 ""
    """
    cookies = parse_netscape_cookie(cookie_str) if ("\t" in cookie_str or cookie_str.startswith("#")) \
        else dict(item.split("=", 1) for item in cookie_str.split(";") if "=" in item)

    # 番茄作家后台没有标准的 writer_id cookie；优先 sessionid 用于诊断
    for key in ("sessionid", "sid_tt", "uid_tt"):
        if cookies.get(key):
            return cookies[key]
    return ""


# =============================================================================
# Markdown → 番茄正文 HTML
# =============================================================================

def _inline_markdown_to_html(text: str) -> str:
    """处理行内 Markdown（粗体 / 斜体 / 行内代码），先做 HTML 转义。"""
    text = _html.escape(text)
    # 行内代码 `code`
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # 粗体 **text** 或 __text__
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", r"<strong>\1\2</strong>", text)
    # 斜体 *text* 或 _text_
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*(?!\*)|(?<!_)_(?!_)(.+?)_(?!_)", r"<em>\1\2</em>", text)
    return text


def markdown_to_fanqie_html(md: str) -> str:
    """
    将简易 Markdown 转换为番茄正文 HTML。

    规则（对齐番茄 <p> 段落存储）：
      - 两个及以上换行 → 分段，每段包 <p>...</p>
      - 单个换行 → 段内 <br>
      - 行内：**粗体** / *斜体* / `代码`
      - 全文先做 HTML 转义，防止注入

    Args:
        md: Markdown 文本（可为空）

    Returns:
        番茄可用的 HTML 字符串，例如 "<p>第一段</p><p>第二段</p>"
    """
    if not md:
        return ""

    # 按空行分段
    blocks = re.split(r"\n\s*\n", md.strip())
    html_parts: List[str] = []

    for block in blocks:
        if not block.strip():
            continue
        # 段内换行转 <br>
        lines = block.split("\n")
        inline = "<br>".join(_inline_markdown_to_html(ln) for ln in lines)
        html_parts.append(f"<p>{inline}</p>")

    return "".join(html_parts)
