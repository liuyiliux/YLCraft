"""微博「老是打开浏览器」+「我的数据拿不到」的回归测试。

## 用户反馈

    "为啥个人中心的微博老是打开浏览器了？"

以及之前：扫码登录成功、cookie 也存了，但「我的数据」一直拿不到。

## 根因（两个叠加）

### ① 无头模式没用上 —— 旧注释误导

代码里写着"无头会被甩验证码页"——**那个结论过时了**。实测：

    无头：搜索返回 JSON，cards=14  ✅
    有头：搜索返回 JSON，cards=13  ✅

**两者都能搜到**，所以没理由再弹窗口。

### ② 两个会话同时打开同一个 profile，互相打架（真 bug）

实测日志暴露的竞争：

    12:04:50.936  [base] Cookies set to browser → 新建会话（**有 cookie**）
    12:04:50.941  [weibo] **又启动了一次持久化 profile**   ← 覆盖！
    12:04:51.397  [weibo] 新建浏览器会话（无头，**没注入 cookie**）

**两个上下文同时打开同一个持久化 profile**，第二个覆盖第一个 ——
m 站的登录 cookie（`SSOLoginState` 等）没生效 → `login=False`。

而且两处的**会话 key 格式还不一致**：

    base:      f"{platform}|{conn_id or '-'}"   ← 竖线
    weibo:     f"weibo:{conn_key}"              ← 冒号（同一个 profile！）

**修法**：`_get_session` 优先**复用 client 已建好的会话**
（base 那条已经注入过 cookie），不再新建第二个上下文。

## 实测修复后

    搜索: 5 条      搜博主: 3 个      我的数据: ✅ 想见雪- 粉丝8
    **chrome 进程 = 0** ← 不再弹窗口
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# ① 无头模式
# =============================================================================

def test_weibo_session_is_headless():
    """**回归**：微博搜索会话要用**无头**（不弹窗口）。

    实测无头同样能搜到（cards=14 vs 13），所以没理由弹窗。
    """
    from app.services.platforms.weibo import search_patchright as wb

    src = inspect.getsource(wb._get_session)
    assert "headless=True" in src, "微博会话应无头"
    assert "headless=False" not in src, "不该再有有头会话"


def test_base_makes_weibo_headless():
    """**回归**：`base._init_patchright` 对微博也要无头。

    否则"个人中心"那条路仍会弹窗。
    """
    from app.services.platforms import base as base_mod

    src = inspect.getsource(base_mod.BasePlatformClient._init_patchright)
    assert "weibo" in src, "应对微博特判"
    assert "headless = True" in src or "headless=True" in src


def test_headless_reason_documented():
    """要记录"无头实测可用"（推翻旧注释）。"""
    from app.services.platforms.weibo import search_patchright as wb

    src = inspect.getsource(wb._get_session)
    assert "无头" in src
    # 要说明实测数据，避免后人改回有头
    assert "cards=14" in src or "无头：搜索返回 JSON" in src


# =============================================================================
# ② 会话复用（避免两个上下文打架）
# =============================================================================

def test_get_session_accepts_client():
    """**回归**：`_get_session` 要能接收 `client`（复用它的会话）。"""
    from app.services.platforms.weibo import search_patchright as wb

    sig = inspect.signature(wb._get_session)
    assert "client" in sig.parameters, "应接收 client 参数"


def test_get_session_prefers_client_page():
    """**回归**：优先复用 client 已建好的 page。

    实测：不复用会**同时打开两个持久化 profile**，
    第二个（没注入 cookie）覆盖第一个 → `login=False`。
    """
    from app.services.platforms.weibo import search_patchright as wb

    src = inspect.getsource(wb._get_session)
    assert "_patchright_page" in src, "应读 client 的 page"
    # 复用的分支要在"新建"之前
    i_borrow = src.find("_patchright_page")
    i_new = src.find("new_context")
    assert i_borrow != -1 and i_new != -1
    assert i_borrow < i_new, "应先尝试复用，再考虑新建"


def test_session_key_matches_base():
    """**回归**：会话 key 格式要与 base 一致（竖线分隔）。

    原来是 `weibo:{conn}`（冒号），base 是 `weibo|{conn}`（竖线）——
    **两个 key 指向同一个 profile**，各建各的。
    """
    from app.services.platforms.weibo import search_patchright as wb

    src = inspect.getsource(wb._get_session)
    assert 'f"weibo|{conn_key' in src, "key 应与 base 一致（竖线）"


def test_all_call_sites_pass_client():
    """**回归**：四个入口都要把 client 传下去。

    漏一个就会出现"有的功能复用会话、有的自己新建"的混乱。
    """
    from app.services.platforms.weibo import search_patchright as wb

    src = inspect.getsource(wb)
    n = src.count("_get_session(conn_key, client=client)")
    assert n >= 4, f"四个入口都应传 client，实际 {n} 个"


def test_weibo_client_passes_self():
    """**回归**：`WeiboClient` 调用时要把 `self` 传下去。"""
    from app.services.platforms.weibo import client as wb_client

    src = inspect.getsource(wb_client)
    assert src.count("client=self") >= 4, "四处调用都要传 self"


# =============================================================================
# 借用会话的所有权
# =============================================================================

def test_borrowed_session_not_dropped_from_pool():
    """**回归**：借用 base 的会话时，预热失败**不能**把它从池里摘掉。

    它不是池的会话（归 base 所有），摘了会破坏 base 的状态。
    """
    from app.services.platforms.weibo import search_patchright as wb

    src = inspect.getsource(wb._warm_up)
    assert "borrowed" in src, "预热要区分是否为借用的会话"
    assert "_pool.drop" in src
