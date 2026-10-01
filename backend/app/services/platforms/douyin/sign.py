"""抖音 a_bogus 签名（用 MediaCrawler 的 `libs/douyin.js`）。

## 为什么需要这个（2026-10-01 调研 + 实测）

抖音**评论**接口**必须**带 `a_bogus`。决定性对照实验（同一 cookie、
同一条视频、同一时刻）：

    不带 a_bogus → HTTP 200，**响应体 0 字节**
    带 a_bogus   → HTTP 200，**19 条评论**

⚠️ 注意这与**搜索**不同：我们 `apis.py` 里"抖音搜索不需要 a_bogus"
的结论是对的（MediaCrawler 源码里有一条
`if "/v1/web/general/search" not in uri` 才加签名的判断），
**别把搜索的结论照搬到评论**。

## ⚠️ 关于第三方混淆 JS 的安全审查（重要）

这个文件是**混淆过的 JS**（变量名无意义、控制流打乱），
肉眼无法确认它在做什么。所以在引入前做了**静态审查**（2026-10-01）：

| 检查项 | 结果 |
|--------|------|
| 网络请求（XMLHttpRequest/fetch/sendBeacon/WebSocket） | **0** |
| 文件/系统（require/child_process/fs/process） | **0** |
| 动态执行（eval / new Function） | **0**（`function(e){}` 是普通匿名函数） |
| DOM/全局（document/window/navigator/localStorage） | **0** |

结论：**纯计算** —— 只做加密（RC4 / SM3）与签名拼接，
不联网、不读文件、不执行命令。函数清单：
`rc4_encrypt` / `SM3` / `generate_random_str` / `sign` /
`sign_datail`（主评论）/ `sign_reply`（子评论）。

与 2026-09-26 拒绝的那份 528KB `dy_ab.js` **不是同一个文件**
（这份 15KB，小 35 倍，出入口干净）。

## 用法

    from .sign import sign_comment_params
    params = sign_comment_params({"aweme_id": "...", "cursor": 0,
                                 "count": 20, "item_type": 0}, ua)
    # params 现在多了 a_bogus

签名依赖 `py_mini_racer`（纯 Python 绑定 V8，不需要 Node.js）——
比 execjs 更适合：execjs 需要外部 Node 运行时。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode

logger = logging.getLogger("ylcraft.platforms.douyin.sign")

_JS_PATH = Path(__file__).resolve().parent / "libs" / "douyin.js"

# py_mini_racer 的 MiniRacer 实例（懒加载 + 复用，编译 JS 有成本）
_ctx: Optional[Any] = None
_ctx_error: Optional[str] = None


def _get_ctx():
    """加载并编译 douyin.js（只做一次）。"""
    global _ctx, _ctx_error
    if _ctx is not None:
        return _ctx
    if _ctx_error is not None:
        raise RuntimeError(_ctx_error)

    if not _JS_PATH.exists():
        _ctx_error = f"[douyin] 签名文件缺失：{_JS_PATH}"
        raise RuntimeError(_ctx_error)
    try:
        from py_mini_racer import py_mini_racer
    except ImportError as exc:
        _ctx_error = (
            "[douyin] 缺 py_mini_racer（pip install py-mini-racer）—— "
            "抖音评论签名需要它。"
        )
        raise RuntimeError(_ctx_error) from exc

    # ⚠️ 文件是 UTF-8 BOM 开头（实测），用 utf-8-sig 读，否则编译报语法错
    src = _JS_PATH.read_text(encoding="utf-8-sig")
    _ctx = py_mini_racer.MiniRacer()
    _ctx.eval(src)
    return _ctx


def _sign(fn_name: str, params: Dict[str, Any], ua: str) -> str:
    """调 JS 里的签名函数。

    ⚠️ 签名输入是**签名前的 query string**（不含 a_bogus 本身）。
    """
    ctx = _get_ctx()
    qs = urlencode(params)
    return ctx.call(fn_name, qs, ua)


def sign_comment_params(
    params: Dict[str, Any],
    ua: str,
    *,
    is_reply: bool = False,
) -> Dict[str, Any]:
    """给评论请求参数加上 `a_bogus`。

    Args:
        params: 请求参数（**不含** a_bogus）
        ua: User-Agent（签名函数需要它）
        is_reply: 是子评论（用 sign_reply）还是主评论（sign_datail）

    Returns:
        带 a_bogus 的新 dict（不改原 dict）。

    ⚠️ 实测生成的 a_bogus 是 164 字符。
    """
    out = dict(params)
    fn = "sign_reply" if is_reply else "sign_datail"
    out["a_bogus"] = _sign(fn, out, ua)
    return out
