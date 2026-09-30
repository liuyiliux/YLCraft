"""小红书风控检测（纯 Python，基于实测的响应特征）。

## 为什么需要

用户反馈"小红书触发自动化收到风控了"。实测发现**症状极具误导性**：

    搜索 → 461，但响应体是 {"code":0,"success":true,"data":{}}   ← 看着像"成功"
    详情 → 461，{"code":300011,"msg":"账号异常，请稍后重试"}

如果不识别这些信号，程序会把它当成"没搜到"（返回空列表），
用户**完全不知道是被风控了** —— 这正是本仓库反复出现的老毛病。

## 实测事实（2026-09-29，本机账号）

    接口                  状态      信号
    GET  /user/selfinfo   200 ✅    登录态**有效**（posted=73 等正常返回）
    POST /search/notes    **461**   `Verifytype: 217`（CAPTCHA 头）+ data 空
    POST /feed            **461**   body `{"code":300011,"msg":"账号异常"}`

**结论：账号被限制搜索/详情，但登录态本身没坏。**
即"风控"是**按接口**的，不是整号封禁。

## 信号来源（调研确认，非我方猜测）

来自 MediaCrawler `media_platform/xhs/client.py` 的错误码表：

| 信号 | 含义 |
|------|------|
| HTTP **461 / 471** | CAPTCHA 人机验证（读 `Verifytype` / `Verifyuuid` 响应头） |
| HTTP 401 / 403 / 429 | 访问被拦截 |
| HTTP **406** | 签名被拒（body 通常 `{"code":-1,"success":false}`） |
| body `code 300011` | **账号安全限制**（"检测到账号异常，请稍后重启试试"） |
| body `code 300012` | **IP 被封** / 网络错误 |
| body `code -510000` | 笔记不存在 |
| body `code -510001` | 笔记状态异常 |

## 恢复方式（一手反馈）

    一手反馈："重新刷新页面或重登账号都不行还是提示461"
    回答："**更换 ip 和账号即可**"

**即：同一账号在同一 IP 上被标记后，重登无效** —— 必须换 IP + 换账号。
（"未找到"权威的自动解除时长。）

## 降级

搜索被风控时，用「去官网搜」在浏览器里手动搜索
（真人浏览器操作几乎不触发风控）。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger("ylcraft.platforms.xiaohongshu.risk")

# ---- HTTP 状态码 ----
RISK_HTTP_CODES = {
    461: "CAPTCHA 人机验证（读 Verifytype/Verifyuuid 响应头）",
    471: "CAPTCHA 人机验证",
    406: "签名被拒（body 通常是 {\"code\":-1,\"success\":false}）",
    401: "访问被拦截（未授权）",
    403: "访问被拦截（禁止）",
    429: "访问过于频繁",
}

# ---- 业务错误码（MediaCrawler 归纳，非官方公开表）----
RISK_BODY_CODES = {
    300011: "账号安全限制（检测到账号异常，请稍后重启试试）",
    300012: "IP 被封 / 网络错误",
}

# **不影响使用**的错误码（笔记级问题，不是风控）
BENIGN_BODY_CODES = {
    -510000: "笔记不存在",
    -510001: "笔记状态异常",
}

# 响应头里指示 CAPTCHA 的字段
VERIFY_HEADERS = ("Verifytype", "Verifyuuid")


@dataclass
class RiskSignal:
    """一条风控信号。"""

    kind: str          # "captcha" / "account" / "ip" / "signature" / "rate_limit"
    reason: str        # 人话说明
    http_status: int = 0
    body_code: Optional[int] = None
    verify_type: str = ""
    verify_uuid: str = ""

    def message(self) -> str:
        """给用户看的可操作说明。"""
        base = f"小红书风控：{self.reason}"
        if self.verify_type:
            base += f"（Verifytype={self.verify_type}）"
        if self.kind == "ip":
            tail = "请**更换网络/IP**（换 IP 通常比换账号有效）。"
        elif self.kind == "account":
            tail = "按实测反馈，**重登无效，需更换 IP 和账号**。"
        elif self.kind == "captcha":
            tail = "可用搜索框旁的「去官网搜」在浏览器里手动搜索。"
        elif self.kind == "signature":
            tail = "签名可能已过期——小红书约每月调整一次算法。"
        elif self.kind == "rate_limit":
            tail = "降低频率后重试（建议翻页间隔 ≥ 2 秒）。"
        else:
            tail = "稍后重试。"
        return f"{base}。{tail}"


def detect_risk(
    *,
    status_code: int = 0,
    headers: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
) -> Optional[RiskSignal]:
    """从一次响应里识别风控信号；没有则返回 None。

    ## 判据优先级（**具体 → 笼统**）

    1. **body 里的业务码**（最具体）——
       `300012`（IP 封）比 `300011`（账号）更需要区分，因为解法不同
    2. **响应头 `Verifytype` / `Verifyuuid`** —— CAPTCHA 的直接证据
    3. **HTTP 状态码** —— 461/471/406/401/403/429

    注意 **`300011` 优先于 `Verifytype`**：前者说明"账号被限制"，
    后者只说明"这次请求被要求过人机验证" —— 前者信息更多。
    """
    h = headers or {}
    verify_type = str(h.get("Verifytype") or h.get("verifytype") or "")
    verify_uuid = str(h.get("Verifyuuid") or h.get("verifyuuid") or "")

    # ---- ① body 业务码 ----
    code: Optional[int] = None
    if isinstance(body, dict):
        raw_code = body.get("code")
        if isinstance(raw_code, int):
            code = raw_code
    if code in RISK_BODY_CODES:
        kind = "ip" if code == 300012 else "account"
        return RiskSignal(
            kind=kind,
            reason=RISK_BODY_CODES[code],
            http_status=status_code,
            body_code=code,
            verify_type=verify_type,
            verify_uuid=verify_uuid,
        )

    # ---- ② Verify 头（CAPTCHA 的直接证据）----
    if verify_type or verify_uuid:
        return RiskSignal(
            kind="captcha",
            reason="被要求人机验证（CAPTCHA）",
            http_status=status_code,
            body_code=code,
            verify_type=verify_type,
            verify_uuid=verify_uuid,
        )

    # ---- ③ HTTP 状态码 ----
    if status_code in RISK_HTTP_CODES:
        if status_code == 406:
            kind = "signature"
        elif status_code == 429:
            kind = "rate_limit"
        elif status_code in (461, 471):
            kind = "captcha"
        else:
            kind = "account"
        return RiskSignal(
            kind=kind,
            reason=RISK_HTTP_CODES[status_code],
            http_status=status_code,
            body_code=code,
        )

    # 笔记级问题**不是风控**（别误报）
    if code in BENIGN_BODY_CODES:
        logger.debug("[xhs-risk] 非风控的业务码 %s：%s", code, BENIGN_BODY_CODES[code])
        return None

    return None


# =============================================================================
# 探针：判断"当前是否被风控"（而不是等搜索返回空）
# =============================================================================

# 开销最小的健康检查接口（无需 xsec_token）
#
# 来源：MediaCrawler 的 `pong()` 就用它做登录态/可用性检测。
# 实测（本机）：HTTP 200 + `code:0` + 正常返回 posted/liked 等。
SELFINFO_URI = "/api/sns/web/v1/user/selfinfo"


def looks_healthy(*, status_code: int, body: Optional[Dict[str, Any]]) -> bool:
    """`selfinfo` 的返回是否说明"登录态健康"。

    ⚠️ **注意**：实测本机账号 `selfinfo` 200 正常、
    但 `search` 依然 461 —— 说明**风控是按接口的**。
    所以这个探针只能证明"登录态没坏"，
    **不能证明"搜索能用"**。别把它当成万能判据。
    """
    if status_code != 200:
        return False
    if not isinstance(body, dict):
        return False
    if body.get("code") != 0 or not body.get("success"):
        return False
    data = body.get("data") or {}
    result = data.get("result") or {}
    return bool(result.get("success"))
