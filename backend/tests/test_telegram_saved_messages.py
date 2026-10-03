"""Telegram「我的频道」与「我的收藏」是**两件不同的事**（2026-10-03 澄清）。

## 用户澄清

之前我一直在做「我的频道」（`iter_dialogs` = 我加入的频道/群组），
用户要的是**收藏夹** —— 客户端里那个固定的 **Saved Messages** 对话。
截图确认：图标是一个书签、标题 "Saved Messages"。

## MTProto 里它们是两个不同的 peer

| 功能 | 调用 | peer 实体 |
|---|---|---|
| 我的频道 | `iter_dialogs()` | `Channel` / `Chat`（群组、频道） |
| **我的收藏** | `iter_messages("me")` | **你自己**（`InputPeerSelf`） |

`list_dialogs` 显式**跳过** `User`（私聊）——
所以收藏夹**永远不会**出现在「我的频道」列表里。
这不是 bug，是两个不同的东西；两个都要有，各占一个 tab。

telethon 原生支持 `'me'`（`get_input_entity` 里
`if peer in ('me','self'): return InputPeerSelf()`），不需要手工构造。

## 这些断言锁住
  1. 两者的 MTProto 调用**不能**混用（混了就永远拿不到收藏）
  2. 「我的收藏」tab 不需要关键词（与「我的频道」同）
  3. 未登录时报 401 + 指路，**不是**空列表
  4. 收藏项标记为 `type="saved"`，前端才能渲染成"收藏"而非频道
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

MT_DATA = (Path(__file__).resolve().parents[1]
           / "app" / "services" / "platforms" / "telegram" / "mtproto_data.py")
CLIENT = (Path(__file__).resolve().parents[1]
          / "app" / "services" / "platforms" / "telegram" / "client.py")
TG_API = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "telegram.py"
CRAWLER = (Path(__file__).resolve().parents[2]
           / "frontend" / "src" / "pages" / "crawler" / "index.tsx")


def _src(p: Path) -> str:
    if not p.exists():
        pytest.skip(f"{p.name} not found")
    return p.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# 后端：两条路径必须分开
# =============================================================================

def test_list_saved_messages_exists():
    """必须有独立的收藏夹读取函数（不能复用 list_dialogs）。"""
    src = _src(MT_DATA)
    assert "async def list_saved_messages" in src
    ast.parse(src)


def test_saved_uses_input_peer_self():
    """收藏夹必须读 `'me'`（= InputPeerSelf），不是 iter_dialogs。"""
    src = _src(MT_DATA)
    i = src.find("async def list_saved_messages")
    # 去掉注释后再查（docstring 里为了说明差异**会**提到 iter_dialogs，
    # 那不算调用 —— 第一版就因为没去注释而误报）
    code_lines = [ln for ln in src[i:i + 2500].splitlines()
                  if not ln.strip().startswith("#")]
    code = "\n".join(code_lines)
    # 去掉 docstring（第一个三引号块）
    parts = code.split('"""')
    code_no_doc = "".join(parts[0::2]) if len(parts) > 1 else code

    assert 'iter_messages("me"' in code_no_doc or "iter_messages('me'" in code_no_doc, (
        "收藏夹必须用 iter_messages('me') —— 那才是 Saved Messages"
    )
    assert "iter_dialogs(" not in code_no_doc, (
        "收藏夹不能用 iter_dialogs —— 那里跳过 User，永远拿不到"
    )


def test_list_dialogs_still_skips_user():
    """我的频道仍然跳过 User —— 收藏夹不是"一个频道"，不该混进去。"""
    src = _src(MT_DATA)
    i = src.find("async def list_dialogs")
    seg = src[i:i + 1200]
    assert 'kind not in ("Channel"' in seg, "list_dialogs 应只收 Channel/Chat"


def test_client_dispatches_saved_separately():
    """client 必须按 search_type 分派，且 `saved` 不走 dialogs 分支。"""
    src = _src(CLIENT)
    ast.parse(src)
    assert 'st == "saved"' in src, "client.search 没分派 saved"
    assert "async def _list_saved" in src, "缺少 _list_saved 实现"
    # saved 分支必须在 dialogs 分支**之后**且独立
    i_dlg = src.find('if st in ("dialogs"')
    i_saved = src.find('if st == "saved"')
    assert 0 < i_dlg < i_saved, "saved 分支应与 dialogs 分支并列（不是同一个）"


def test_saved_results_marked_as_saved_type():
    """收藏项要标 `type="saved"`，前端才能渲染成「收藏」而不是频道条目。"""
    src = _src(CLIENT)
    i = src.find("async def _list_saved")
    seg = src[i:i + 1500]
    assert 'r.type = "saved"' in seg, "收藏项未标记 type='saved'"
    assert 'r.channel = "saved"' in seg, "收藏项 channel 应固定为 saved"


# =============================================================================
# API：独立端点
# =============================================================================

def test_saved_endpoint_exists():
    src = _src(TG_API)
    ast.parse(src)
    assert '@router.get("/saved"' in src, "缺少 GET /telegram/saved 端点"
    assert '@router.get("/channels"' in src, "我的频道端点应保留（两个都要）"


def test_saved_endpoint_requires_login():
    """未登录必须 401（`get_authorized_client` 会抛），不能返回空列表。"""
    src = _src(TG_API)
    i = src.find('@router.get("/saved"')
    seg = src[i:i + 2000]
    assert "get_authorized_client" in seg, "收藏夹应走登录态（它是私有数据）"
    assert "status_code=401" in seg, "未登录应 401，而不是空列表"


# =============================================================================
# 前端
# =============================================================================

def test_frontend_has_saved_tab():
    src = _src(CRAWLER)
    assert "value: 'saved'" in src, "前端缺「我的收藏」tab"
    assert "我的收藏" in src, "tab 应有中文标签"
    # 必须与 dialogs 并列存在（两个都要）
    assert "value: 'dialogs'" in src


def test_saved_tab_needs_no_keyword():
    """「我的频道」和「我的收藏」都**不需要关键词** —— 别拦住用户。"""
    src = _src(CRAWLER)
    assert "telegramNoKeyword" in src, (
        "收藏夹/我的频道列的是『我的东西』，不该被『必须先输关键词』拦住"
    )
    i = src.find("telegramNoKeyword")
    seg = src[i:i + 400]
    assert "'dialogs'" in seg and "'saved'" in seg, (
        "两个免关键词 tab 都要放行"
    )
