"""B站子回复的回归测试（2026-10-04 修）。

## 发现的 bug（假支持 + 指向虚空的出路）

`meta.py` 与 `comments.py` 都写着：

> B站子回复**随顶层评论一起返回**（在每条评论的 `replies` 字段里）——
> 直接看顶层返回即可。

**实测（BV1UAaS6KEgs，20 条顶层评论）**：

    6~7 条带 reply_count（16/8/13/1/4/7/12…），`replies` 数组**全空**

原因：项目取顶层走 **WBI 新接口** `x/v2/reply/wbi/main?mode=3`，
它**不内嵌** replies（那是老接口 `mode=1` 的行为）。

于是：接口返回 **501**「不支持单独取子回复」+ **一个看不到的出路**
（"直接看顶层返回即可"，而那里什么都没有）—— 比直接说"不支持"更糟。

## 但 B站其实**能取**到

实测两条路（oid=117371205322627, root=319481921680）：

    WBI  + root → code=-403「访问权限不足」  ❌
    老接口 + root → code=0，20 条真实数据    ✅

所以补了 `BilibiliClient.get_replies`（走老接口
`/x/v2/reply/main?root=<rpid>`），并把 `replies` 加进 meta.capabilities。

## 另一个坑：total 语义不同

老接口带 `root=` 时，`cursor.all_count` 返回的是**整个视频的评论总数**
（实测 1944），**不是**这条主楼的子回复数（16）。
第一版直接用它当 `total`，前端会显示"1944 条回复"——差 110 倍。

## 这些断言锁住
  1. meta 必须声明 `replies`（否则 API 层 501，功能不可达）
  2. client 必须有 `get_replies`，且用**老接口**（WBI 403）
  3. `get_replies` 必须返回 **dict**（`comments.py` 统一按 dict 读）
  4. `total` 不得取 `cursor.all_count`（那是整个视频的数）
  5. 报错文案不得再说"随顶层一起返回"（实测为空）
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

BILI_CLIENT = (Path(__file__).resolve().parents[1]
               / "app" / "services" / "platforms" / "bilibili" / "client.py")
BILI_META = (Path(__file__).resolve().parents[1]
             / "app" / "services" / "platforms" / "bilibili" / "meta.py")
COMMENTS_API = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "comments.py"


def _src(p: Path) -> str:
    if not p.exists():
        pytest.skip(f"{p.name} not found")
    return p.read_text(encoding="utf-8", errors="ignore")


def _code_only(src: str) -> str:
    """去掉注释与 docstring（否则我写的说明文字会让断言误报）。"""
    lines = [ln for ln in src.splitlines() if not ln.strip().startswith("#")]
    code = "\n".join(lines)
    parts = code.split('"""')
    return "".join(parts[0::2]) if len(parts) > 1 else code


# =============================================================================
# 能力声明
# =============================================================================

def test_bili_declares_replies():
    """meta 必须声明 `replies`，否则 API 层直接 501，功能不可达。"""
    from app.services.platforms.meta import supports
    assert supports("bili", "replies") is True, (
        "bili 未声明 replies —— /comments?parent_id= 会返回 501，"
        "实测 B站**能**取到子回复（老接口 root=）"
    )


def test_meta_comment_not_lying_again():
    """meta 的注释不得再断言"随顶层一起返回"（实测 replies 数组全空）。"""
    src = _src(BILI_META)
    i = src.find("capabilities")
    seg = src[i:i + 900]
    for claim in ("没有 \"replies\"", '没有 "replies"', "没有独立的\"取子回复\"接口"):
        assert claim not in seg, (
            f"meta 里还留着旧结论 {claim!r} —— "
            f"实测 WBI 接口不内嵌 replies，数组全空"
        )


# =============================================================================
# client.get_replies
# =============================================================================

def test_client_has_get_replies():
    from app.services.platforms.bilibili.client import BilibiliClient
    assert hasattr(BilibiliClient, "get_replies"), "缺少 get_replies"


def test_get_replies_signature_matches_caller():
    """`comments.py` 调的是 `(item, parent_id, max_results=, cursor=)`。

    ⚠️ 第一版签名写成 `page=`，运行时报
       `got an unexpected keyword argument 'cursor'`（500）。
    """
    from app.services.platforms.bilibili.client import BilibiliClient
    sig = inspect.signature(BilibiliClient.get_replies)
    for name in ("item_id", "root", "max_results", "cursor"):
        assert name in sig.parameters, f"get_replies 缺参数 {name}"
    assert "page" not in sig.parameters, (
        "参数应叫 cursor（调用方传的是 cursor）"
    )


def test_get_replies_uses_legacy_endpoint():
    """必须用**老接口** `/x/v2/reply/main`（WBI + root 实测 -403）。"""
    src = _src(BILI_CLIENT)
    i = src.find("async def get_replies")
    seg = _code_only(src[i:i + 4000])
    assert "x/v2/reply/main" in seg, "必须用老接口 /x/v2/reply/main"
    assert "wbi/main" not in seg, (
        "不要用 WBI 接口取子回复 —— 实测 `wbi/main?root=` 返回 "
        "code=-403「访问权限不足」"
    )
    assert '"root"' in seg or "'root'" in seg, "必须传 root=<主楼rpid>"


def test_get_replies_returns_dict():
    """必须返回 **dict**（`comments.py` 统一 `reply_data.get("comments")`）。"""
    from app.services.platforms.bilibili.client import BilibiliClient
    hints = inspect.getdoc(BilibiliClient.get_replies) or ""
    src = _src(BILI_CLIENT)
    i = src.find("async def get_replies")
    j = src.find("\n    async def ", i + 10)
    body = _code_only(src[i:j if j > 0 else i + 4000])
    assert '"comments"' in body, "返回体必须有 comments 键"
    assert '"total"' in body, "返回体必须有 total 键"
    assert '"has_more"' in body, "返回体必须有 has_more 键"


def test_get_replies_total_not_global_count():
    """`total` **不得**取 `cursor.all_count`。

    实测带 `root=` 时它返回**整个视频的评论总数**（1944），
    而这条主楼只有 16 条子回复 —— 差 110 倍。
    """
    src = _src(BILI_CLIENT)
    i = src.find("async def get_replies")
    j = src.find("\n    async def ", i + 10)
    body = _code_only(src[i:j if j > 0 else i + 4000])
    assert "all_count" not in body, (
        "不能拿 cursor.all_count 当子回复总数 —— "
        "实测它返回的是整个视频的评论数（1944 vs 16）"
    )


# =============================================================================
# API 层文案
# =============================================================================

def test_api_no_longer_claims_replies_inline():
    """API 层不得再让用户"直接看顶层返回"（那里 replies 数组是空的）。"""
    src = _src(COMMENTS_API)
    i = src.find("不支持单独取子回复")
    seg = src[max(0, i - 900):i + 700]
    assert "随顶层评论一起返回" not in seg, (
        "报错文案还在让用户『直接看顶层返回』—— 实测那个 replies 数组是空的，"
        "等于给了一个指向虚空的出路"
    )


# =============================================================================
# 语法
# =============================================================================

def test_syntax_valid():
    ast.parse(_src(BILI_CLIENT))
    ast.parse(_src(BILI_META))
    ast.parse(_src(COMMENTS_API))
