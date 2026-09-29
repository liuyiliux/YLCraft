"""登录弹窗「一直等待」的回归测试。

## 用户反馈

    "这里为啥一直等待"

截图：微博显示"1 个有效"，但右侧弹窗卡在
「请在浏览器中完成登录」45% **不动了**。

## 根因：前端只靠 WebSocket，会话丢了就永远收不到消息

实测状态：

    后端活跃会话 = 0       ← 会话已结束（后端重启后内存态丢失）
    chrome 进程   = 8       ← 浏览器窗口还开着（但那是**搜索**开的，不是登录会话）

**所以前端在等一个已经不存在的会话** → 永远 45%。

## 为什么会这样

登录会话是**内存态**：

  · 扫码成功 → 保存 cookie（**已持久化到数据库**）→ 会话结束
  · 后端重启 → 内存里的会话记录没了，WS 断开

而前端 `ws.onclose` 原来只做了 `setIsLoading(false)`：
**既不告诉用户"断了"，也不检查"会话是不是已经完成"** —— 于是干等。

实际上**用户的扫码是成功的**（cookie 已保存），只是前端不知道。

## 修法：WS 断开后加轮询兜底

`startSessionWatchdog(sid)`：每 3 秒查会话列表，
会话不在 → 明确告知"会话已结束（后端可能重启过）；
若刚才已扫码成功，登录态已保存，可关闭刷新；否则重新启动"。

## 注意区分

那 8 个 chrome 是**搜索**开的（`session_pool` 复用），不是登录会话 ——
所以"有 chrome 进程"**不等于**"登录会话还在"。判断依据是会话列表，不是进程。
"""

from __future__ import annotations

from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
ACCOUNTS = FRONTEND / "pages" / "accounts" / "index.tsx"


def _src() -> str:
    if not ACCOUNTS.exists():
        pytest.skip("账号中心页不在预期位置")
    return ACCOUNTS.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# 兜底机制
# =============================================================================

def test_watchdog_exists():
    """**回归**：要有 WS 断开后的轮询兜底。"""
    src = _src()
    assert "startSessionWatchdog" in src, (
        "WS 断开后应启动轮询兜底，否则用户永远卡在 45%"
    )


def test_watchdog_called_on_ws_close():
    """**回归**：`ws.onclose` 里要调用兜底（不只是 setIsLoading(false)）。

    注：页面里可能有多处 `ws.onclose`（不同平台/不同流程），
    只要**有一处**接了兜底即可（断言整体行为，不绑定具体位置）。
    """
    import re

    src = _src()
    # 取每个 onclose 之后的一段，看有没有调用兜底
    hits = [m.start() for m in re.finditer(r"ws\.onclose", src)]
    assert hits, "应有 onclose 处理"
    called = any(
        "startSessionWatchdog" in src[i:i + 400] for i in hits
    )
    assert called, (
        "onclose 里应启动轮询兜底 —— 实测后端重启会让 WS 断开，"
        "而会话（内存态）已经没了，用户会一直等"
    )


def test_watchdog_checks_session_list():
    """兜底要查**会话列表**（不是看 chrome 进程）。

    ⚠️ 实测有 8 个 chrome 但同时会话是 0 —— 那些是**搜索**开的。
    所以判断依据是会话列表，不是进程数。
    """
    src = _src()
    i = src.find("startSessionWatchdog")
    seg = src[i:i + 1200]
    assert "listPlaywrightSessions" in seg, "应查会话列表"
    assert "session_id" in seg


def test_watchdog_message_is_actionable():
    """**回归**：兜底提示要**可操作**（说明登录态可能已保存）。

    用户的扫码其实是成功的（cookie 已落库），
    所以提示要区分"已成功 → 刷新即可"与"失败 → 重新启动"。
    """
    src = _src()
    assert "登录会话已结束" in src, "应说明会话已结束"
    assert "后端可能重启过" in src, "应说明可能原因"
    assert "登录态已保存" in src, "应告知登录态可能已保存（用户的扫码其实是成功的）"


def test_watchdog_stops_when_ws_reopens():
    """WS 恢复（后端重新可用）时要停止轮询，别一直跑。"""
    src = _src()
    i = src.find("startSessionWatchdog")
    seg = src[i:i + 1200]
    assert "readyState === WebSocket.OPEN" in seg, "WS 恢复应停掉轮询"


def test_watchdog_has_try_limit():
    """兜底要有次数上限（不能无限轮询）。"""
    src = _src()
    i = src.find("startSessionWatchdog")
    seg = src[i:i + 1200]
    assert "tries >" in seg, "应有重试上限"
    assert "clearInterval" in seg


# =============================================================================
# 文档记录
# =============================================================================

def test_documents_memory_session_trap():
    """要记录"会话是内存态、重启即丢"这件事。"""
    src = _src()
    assert "内存态" in src or "重启" in src
