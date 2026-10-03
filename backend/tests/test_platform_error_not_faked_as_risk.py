"""平台侧错误**不得被误报成风控**（2026-10-03）。

## 用户截图暴露的问题

搜 `@kshelfs` 时，前端弹出**两段互相矛盾**的内容（连着显示）：

    这个频道**存在**，但 Telegram **没有开放网页端的消息列表**。…
    这是**平台侧拒绝**（触发风控或人机验证），不是「没搜到」。可尝试：
      1. 稍等一会儿再试（风控常是临时性的）
      2. 到「账号中心」重新获取该平台登录态
      3. 用搜索框旁的「去官网搜」在浏览器里手动搜索

既然"频道存在、只是没开放"，那"触发风控"、"等一会再试"、
"重新获取登录态"**全部是错的方向** —— 会把用户引去做三件没用的事，
其中"等一会儿再试"尤其糟糕：它暗示这是暂时的，实际永远不会变。

## 根因

`TelegramPublicError` 继承了 `RiskControlError`，于是 API 层
`isinstance(e, RiskControlError)` 命中，给它套上统一的"风控"文案。

而实测这四类**都不是风控**（见 `parser.detect_structure_change`）：
    · 频道不存在（`Contact @xxx`）
    · 输入的是频道标题而非 username（中文）
    · 频道存在但 Telegram 未开放网页端（`kshelfs`）
    · Telegram 改了页面结构（唯一勉强算"平台侧变化"的）

## 修法

`TelegramPublicError` 改挂到 `PlatformError` 之下 → 不再命中风控分支；
API 层补 `except PlatformError` → 400（而不是掉进 500）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.platforms.telegram.web_preview import TelegramPublicError
from app.services.platforms.types import NetworkError, PlatformError, RiskControlError

CRAWLER_API = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "crawler.py"


# =============================================================================
# 分类：不能再冒充风控
# =============================================================================

def test_not_risk_control_subclass():
    """核心回归：一旦又继承 RiskControlError，API 就会套上"风控"文案。"""
    assert not issubclass(TelegramPublicError, RiskControlError), (
        "TelegramPublicError 又继承 RiskControlError —— "
        "「频道不存在/未开放/用户名错了」会被报成「触发风控、人机验证」，"
        "把用户引去做三件没用的事"
    )


def test_still_platform_error():
    """仍要在类型体系内（API 层靠它兜底成 400，而不是 500）。"""
    assert issubclass(TelegramPublicError, PlatformError)


def test_network_error_still_distinguishable():
    """网络问题必须**继续**与其它情况区分（VPN 断了 ≠ 频道不存在）。"""
    assert not issubclass(NetworkError, TelegramPublicError), (
        "NetworkError 不该被 TelegramPublicError 吞掉 —— "
        "否则「VPN 断了」会被报成「频道不存在」，用户会去查没拼错的频道名"
    )


def test_not_retryable_not_fallback():
    """频道不存在重试没用、也不该降级到 yt-dlp（会把「被拒」伪装成「没搜到」）。"""
    assert TelegramPublicError.retryable is False
    assert TelegramPublicError.should_fallback is False


# =============================================================================
# API 层：不得再拼上风控文案
# =============================================================================

def _api_src() -> str:
    if not CRAWLER_API.exists():
        pytest.skip("crawler api not found")
    return CRAWLER_API.read_text(encoding="utf-8", errors="ignore")


def test_api_has_generic_platform_error_branch():
    """必须显式处理 PlatformError（否则掉进 500 = 「服务端故障」，误导）。"""
    src = _api_src()
    i = src.find("isinstance(e, PlatformError)")
    assert i > 0, "缺 PlatformError 分支 —— 平台侧明确说了原因的错误会掉进 500"

    # ⚠️ 只看**这个分支自己**的 raise 语句，不能往后扫固定长度：
    # 分支结束后紧跟的就是 `logger.error(...500...)` 那两行（合法的兜底），
    # 按窗口一刀切会误判"分支里出现了 500"。
    seg = src[i:i + 900]
    end = seg.find("logger.error")
    branch = seg[:end] if end > 0 else seg
    assert "status_code=400" in branch, (
        f"PlatformError 分支应给 400（请求本身有问题），实际片段：{branch[:160]!r}"
    )
    assert "status_code=500" not in branch, (
        "PlatformError 分支里出现 500 —— 会让用户以为是应用崩了"
    )


def test_risk_control_branch_only_for_real_risk():
    """"平台侧拒绝（风控/人机验证）"这段文案只该出现在 RiskControlError 分支。"""
    src = _api_src()
    i = src.find("isinstance(e, RiskControlError)")
    assert i > 0, "找不到 RiskControlError 分支"
    # 确认该分支的 status_code 是 429（真风控才 429）
    seg = src[i:i + 700]
    assert "status_code=429" in seg, "真风控才该是 429"
