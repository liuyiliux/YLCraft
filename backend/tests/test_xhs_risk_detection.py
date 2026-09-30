"""小红书风控识别的回归测试（2026-09-29）。

## 起因

用户："小红书触发自动化什么的收到风控了 可能得暂时不用"

## 实测发现：症状**极具误导性**

    接口                  状态      信号
    GET  /user/selfinfo   200 ✅    登录态**有效**（posted=73 等正常返回）
    POST /search/notes    **461**   `Verifytype: 217`（CAPTCHA 头）+ **data 空**
    POST /feed            **461**   body `{"code":300011,"msg":"账号异常，请稍后重试"}`

**关键**：搜索那条的 body 是 `{"code":0,"success":true,"data":{}}` ——
**看着像"成功但没数据"**，会被当成"没搜到"。

## 结论

  · **风控是按接口的**，不是整号封禁（`selfinfo` 正常，`search`/`feed` 被拦）
  · **重登无效**（一手反馈："重新刷新页面或重登账号都不行还是提示461"）
  · **解法是换 IP + 换账号**（@World9566 的回复）

## 信号来源（调研确认，非我方猜测）

来自 MediaCrawler `media_platform/xhs/client.py` 的错误码表：

    461 / 471      CAPTCHA（读 Verifytype / Verifyuuid 响应头）
    401/403/429    访问被拦截
    406            签名被拒
    code 300011    账号安全限制
    code 300012    IP 被封
    code -510000   笔记不存在（**不是风控**，别误报）
    code -510001   笔记状态异常

## 为什么需要这个模块

没有它，461 会被 `except Exception: return []` 吞掉 →
响应变成 `{"success": true, "results": [], "message": "找到 0 条结果"}`
—— **用户完全不知道是被风控了**（本仓库反复出现的老毛病）。
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# 风控识别
# =============================================================================

def test_detect_returns_none_for_healthy():
    """**回归**：正常响应不该被误判成风控。"""
    from app.services.platforms.xiaohongshu.risk import detect_risk

    assert detect_risk(status_code=200, headers={},
                       body={"code": 0, "success": True,
                             "data": {"result": {"success": True}}}) is None


def test_detect_ignores_benign_codes():
    """**回归**：笔记级错误（-510000/-510001）**不是风控**，别误报。

    误报会让用户以为"被风控了"，去做无谓的换 IP/换账号。
    """
    from app.services.platforms.xiaohongshu.risk import detect_risk

    for code in (-510000, -510001):
        assert detect_risk(status_code=200, headers={}, body={"code": code}) is None


def test_detect_captcha_from_verify_header():
    """**回归（关键）**：`Verifytype` 头是 CAPTCHA 的直接证据。

    实测：搜索 461 时 body 是 `{"code":0,"success":true,"data":{}}`
    —— **看着像成功**，只有这个头能揭示真相。
    """
    from app.services.platforms.xiaohongshu.risk import detect_risk

    s = detect_risk(status_code=461, headers={"Verifytype": "217"},
                    body={"code": 0, "success": True, "data": {}})
    assert s is not None, "有 Verifytype 就该判定为风控"
    assert s.kind == "captcha"
    assert s.verify_type == "217"


def test_detect_account_restriction():
    """`code 300011` = 账号安全限制（解法：换账号）。"""
    from app.services.platforms.xiaohongshu.risk import detect_risk

    s = detect_risk(status_code=461, headers={},
                    body={"code": 300011, "msg": "账号异常，请稍后重试"})
    assert s is not None
    assert s.kind == "account"
    assert s.body_code == 300011


def test_detect_ip_ban():
    """`code 300012` = IP 被封 —— 与账号限制**解法不同**，必须分开。"""
    from app.services.platforms.xiaohongshu.risk import detect_risk

    s = detect_risk(status_code=200, headers={}, body={"code": 300012})
    assert s is not None
    assert s.kind == "ip", "IP 封禁要单独识别（解法是换 IP，不是换账号）"


def test_detect_signature_rejection():
    """406 = 签名被拒（不是账号问题）。"""
    from app.services.platforms.xiaohongshu.risk import detect_risk

    s = detect_risk(status_code=406, headers={},
                    body={"code": -1, "success": False})
    assert s is not None
    assert s.kind == "signature"


def test_body_code_beats_verify_header():
    """**回归**：body 业务码**优先于** Verifytype。

    两者同时出现时，`300011`（账号被限制）信息量更大 ——
    只说"要过人机验证"会误导用户去刷新页面（实测无效）。
    """
    from app.services.platforms.xiaohongshu.risk import detect_risk

    s = detect_risk(status_code=461, headers={"Verifytype": "217"},
                    body={"code": 300011})
    assert s.kind == "account", "更具体的业务码应优先"


def test_signal_messages_are_actionable():
    """**回归**：提示要**可操作**，且不同 kind 给不同建议。

    实测反馈：**重登无效**，必须换 IP + 换账号 ——
    所以不能笼统写"请重新登录"。
    """
    from app.services.platforms.xiaohongshu.risk import RiskSignal

    ip_msg = RiskSignal(kind="ip", reason="IP 被封").message()
    assert "更换网络" in ip_msg or "换 IP" in ip_msg

    acct_msg = RiskSignal(kind="account", reason="账号异常").message()
    assert "重登无效" in acct_msg

    cap_msg = RiskSignal(kind="captcha", reason="验证").message()
    assert "去官网搜" in cap_msg, "CAPTCHA 时该引导去浏览器手动搜"


# =============================================================================
# 健康探针
# =============================================================================

def test_selfinfo_probe():
    """`selfinfo` 探针（开销最小，MediaCrawler `pong()` 同款）。"""
    from app.services.platforms.xiaohongshu.risk import SELFINFO_URI, looks_healthy

    assert "selfinfo" in SELFINFO_URI
    assert looks_healthy(status_code=200, body={
        "code": 0, "success": True, "data": {"result": {"success": True}},
    }) is True
    assert looks_healthy(status_code=200, body={"code": 0, "success": True}) is False
    assert looks_healthy(status_code=461, body={}) is False


def test_probe_documents_its_limitation():
    """**回归**：探针要写明"只能证明登录态没坏，**不能证明搜索能用**"。

    实测本机：`selfinfo` 200 正常，但 `search` 依然 461 ——
    **风控是按接口的**。如果后人把它当万能判据，会误判。
    """
    from app.services.platforms.xiaohongshu import risk

    doc = inspect.getsource(risk.looks_healthy)
    assert "按接口" in doc or "不能证明" in doc


# =============================================================================
# 接进搜索
# =============================================================================

def test_search_uses_risk_detector():
    """**回归**：搜索要用统一的风控识别，而不是只判断状态码。

    原来只看 `status_code == 461` —— 漏掉了 body 里的 `300011`/`300012`
    （它们的**解法不同**）。
    """
    from app.services.platforms.xiaohongshu import search_api

    src = inspect.getsource(search_api.search_via_api)
    assert "detect_risk" in src
    # 不该再硬编码判断
    assert "signal.message()" in src, "要用信号给出可操作提示"


def test_signature_template_override_available():
    """签名模板可覆盖（上游 issue #110 报告模板版本过期）。

    实测 `CryptoConfig` 是 **frozen dataclass**（`FrozenInstanceError`），
    所以必须 `dataclasses.replace` 重建，不能直接赋值。
    """
    from app.services.platforms.xiaohongshu import signing

    src = inspect.getsource(signing)
    assert "YLCRAFT_XHS_SDK_VERSION" in src, "要能覆盖 x0"
    assert "dataclasses.replace" in src, "frozen dataclass 要 replace"
    # 默认不改（避免引入未验证行为）
    assert "默认**不改**" in src or "默认" in src
