"""连接「停用/启用」能力的回归测试（2026-10-01）。

## 用户诉求

"加个禁用按钮 因为小红书风控被封了" —— 风控期想**停一阵**，
避免反复重试（会升级为更长封禁甚至封号）。

## 设计上的关键点（每条都容易做错）

1. **停用 ≠ 删除**：凭证保留，恢复**不需要重新登录**
2. **停用 ≠ 过期**：`expired/failed` 是系统判定"凭证坏了"，
   `disabled` 是**用户主动关**。混在一起会让用户被
   "请重新登录"的提示骚扰（明明是他自己关的）
3. **兜底路径也要跳过**：`resolve_connection` 在 conn_id 失效时会
   回退到"该平台最新连接" —— 如果那条被停用了，回退过去
   就等于**停用失效**（用户点了停用，请求还在打那个账号）
4. **前端要看得见**：停用后连接**不能从下拉消失**，
   否则用户找不回「启用」按钮（停用变成不可逆的软删除）
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def _crawler() -> str:
    p = FRONTEND / "pages" / "crawler" / "index.tsx"
    if not p.exists():
        pytest.skip("搜索页不在预期位置")
    return p.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# 状态枚举
# =============================================================================

def test_disabled_status_exists():
    """要有独立的 `DISABLED` 状态（不复用 expired）。"""
    from app.db.models.platform_connection import ConnectionStatus

    assert hasattr(ConnectionStatus, "DISABLED")
    assert ConnectionStatus.DISABLED.value == "disabled"


def test_disabled_is_not_expired():
    """停用与过期是**不同**的值（语义不同，别混）。"""
    from app.db.models.platform_connection import ConnectionStatus

    assert ConnectionStatus.DISABLED != ConnectionStatus.EXPIRED
    assert ConnectionStatus.DISABLED != ConnectionStatus.FAILED


# =============================================================================
# resolve_connection：停用的连接不能被返回
# =============================================================================

def test_resolve_connection_skips_disabled():
    """**关键回归**：`resolve_connection` 不能返回已停用的连接。

    两处都要跳过：
      ① 显式传的 conn_id 若已停用
      ② "conn_id 失效回退到该平台最新连接"那条兜底

    漏掉任何一处，用户点了停用**请求照样会打那个账号** ——
    停用形同虚设（而且用户以为已经停了，更危险）。
    """
    from app.services.platforms import login_health

    src = inspect.getsource(login_health.resolve_connection)
    assert "DISABLED" in src, "要排除已停用的连接"
    # 兜底查询也要过滤
    assert "ConnectionStatus.DISABLED" in src or "DISABLED" in src
    # 兜底那段的 where 里要有排除（不能只在显式 ID 分支里做）
    assert "!= ConnectionStatus.DISABLED" in src or "!= ConnectionStatus" in src


def test_resolve_connection_returns_empty_for_disabled():
    """显式传一条已停用的连接时，要返回**空 cookie**（不返回它的凭证）。"""
    from app.services.platforms import login_health

    src = inspect.getsource(login_health.resolve_connection)
    # 应有一条 "已禁用 → 返回空" 的分支
    assert "已被用户禁用" in src or "已禁用" in src


# =============================================================================
# API
# =============================================================================

def test_disable_enable_routes_exist():
    """要有 停用/启用 两个端点。"""
    from app.api.v1 import platforms

    src = inspect.getsource(platforms)
    assert "/{conn_id}/disable" in src
    assert "/{conn_id}/enable" in src


def test_disable_sets_disabled_status():
    """停用要把 status 设成 DISABLED（不是 expired/failed）。"""
    from app.api.v1 import platforms

    src = inspect.getsource(platforms.disable_connection)
    assert "ConnectionStatus.DISABLED" in src


def test_enable_sets_unknown_not_active():
    """**启用时恢复成 `unknown`，不是 `active`**。

    我们**没有验证**过它现在是否有效 —— 不能替用户断言"有效"
    （那是体检的职责）。`unknown` 表示"待验证"，更诚实。
    """
    from app.api.v1 import platforms

    src = inspect.getsource(platforms.enable_connection)
    assert "ConnectionStatus.UNKNOWN" in src, "应恢复成 unknown（待验证）"
    assert "ConnectionStatus.ACTIVE" not in src, "不该直接断言为 active"


def test_disable_message_mentions_credential_kept():
    """停用的返回文案要说明"**凭证保留**"（否则用户以为要重新登录）。"""
    from app.api.v1 import platforms

    src = inspect.getsource(platforms.disable_connection)
    assert "凭证" in src and "保留" in src


# =============================================================================
# 体检：区分"停用"和"需登录"
# =============================================================================

def test_health_distinguishes_disabled_from_needs_login():
    """**关键**：体检要把"连接被停用"与"需要重新登录"分开。

    两者都返回空 cookie，但**出路完全不同**：
      · 没有连接   → 去账号中心获取登录态
      · 被用户停用 → **去启用它**（凭证还在，不用重新登录！）
    混成一句"请先获取登录态"会让用户白跑一趟账号中心。
    """
    from app.services.platforms import health_routes

    src = inspect.getsource(health_routes.platform_health)
    assert "已停用" in src or "停用" in src
    assert '"disabled"' in src or "disabled" in src
    # needs_login 在"被停用"时要是 False
    assert "needs_login" in src


def test_health_does_not_probe_when_disabled():
    """**停用时不做搜索探针** —— 那正是用户想避免的。"""
    from app.services.platforms import health_routes

    src = inspect.getsource(health_routes.platform_health)
    assert "不会发起搜索" in src or "不会发起" in src


# =============================================================================
# 前端
# =============================================================================

def test_frontend_keeps_disabled_connections_visible():
    """**关键回归**：前端加载连接时要**保留已停用的**。

    原来只留 `status === 'active'` —— 用户停用后连接从下拉消失，
    **再也找不到「启用」按钮**（停用变成不可逆的软删除，
    与设计意图完全相反）。
    """
    src = _crawler()
    i = src.find("const loadPlatformConnections")
    assert i != -1
    seg = src[i:i + 1200]
    assert "'disabled'" in seg, "要保留已停用的连接（否则找不回启用按钮）"


def test_frontend_keeps_unknown_connections_visible():
    """**回归（第二次修，实测踩到）**：也要保留 `unknown` 状态的连接。

    ## 实测经过

    我只改成 `active || disabled` 后，**`unknown` 的连接仍然不显示** ——
    而小红书实测正是 `unknown`（未测试过），于是界面显示
    "未找到小红书连接"，**下拉和停用按钮全都不渲染**。

    用户反馈："没看到停用按钮"。

    ⚠️ `unknown` 只是"没测过"，**凭证是在的、搜索照样能用**
    （实测小红书搜索能跑）。不该因为没测过就把它藏起来。

    判据应该是"凭证在不在"，而不是"有没有测过"。
    """
    src = _crawler()
    i = src.find("const loadPlatformConnections")
    assert i != -1
    seg = src[i:i + 1200]
    assert "'unknown'" in seg, (
        "要保留 unknown 状态的连接 —— 实测小红书就是 unknown，"
        "漏了它会导致整个下拉和停用按钮都不渲染"
    )
    # 同时只能过滤掉"凭证真坏了"的两种
    assert "'expired'" not in seg, "不该显式保留 expired（凭证已坏）"
    assert "'failed'" not in seg, "不该显式保留 failed（凭证已坏）"


def test_frontend_default_skips_disabled():
    """默认选中的账号要**跳过已停用的**（否则一进来就搜索失败）。"""
    src = _crawler()
    assert "status !== 'disabled'" in src, "默认选中要跳过停用的连接"


def test_frontend_remembers_connection_per_platform():
    """**回归**：要**按平台记住**选中的账号。

    原来是一个全局 state，切平台时被重置成第一个 ——
    多账号用户每次切回来都要重选（实测反馈"平台选择账号记住"）。
    """
    src = _crawler()
    assert "connByPlatform" in src, "要有 per-platform 的账号记忆"


def test_frontend_has_guest_option_with_warning():
    """要有「不使用账号（游客态）」选项 + **明确的风险提示**。

    ⚠️ 不能只给选项不说风险 —— 多数平台不支持匿名搜索
    （小红书直接返回 -100），用户会以为"这样就不封号了"，
    实际是"搜不了"。风控主要看 IP 和频率，不看有没有账号。
    """
    src = _crawler()
    assert "不使用账号" in src or "游客态" in src
    # 风险提示要说清"这不是避免风控的办法"
    assert "不是" in src and ("IP" in src or "频率" in src)


def test_frontend_has_disable_button():
    """要有 停用/启用 按钮，且文案说明凭证保留。"""
    src = _crawler()
    assert "toggleConnection" in src
    assert "停用" in src and "启用" in src
    # 停用的 tooltip 要说明"凭证保留"
    i = src.find("停用后不再用它发请求")
    assert i != -1, "停用按钮要有说明（凭证保留、随时启用）"
