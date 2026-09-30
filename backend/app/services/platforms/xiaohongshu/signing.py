"""小红书请求签名（纯 Python，基于 xhshow）。

## 为什么需要这一层

小红书**所有** API 都要求 `X-s` / `X-s-common` / `xsc` 签名，
缺签名会得到 `{"code": -1, "msg": "create invalid signature"}`。
这是与抖音最大的区别——抖音实测当前不需要签名。

## 为什么用 xhshow

`Cloxl/xhshow` 是**纯 Python** 复现（MIT，零 JS 文件），
MediaCrawler 与 XHS-Downloader 都已迁移过去。
上一代的方案是「Playwright 注入 JS 调用页面的 `_webmsxyw`」，
但那需要一个常驻浏览器 + stealth 脚本，成本和脆弱度都高得多。

**我方实测确认浏览器内签名不可行**：在已登录页面里
`window._webmsxyw` / `webmsxyw` / `sign` 全部是 `undefined`
（被打包进闭包了），所以只能走 xhshow。

## 依赖 cookie 的 a1

签名算法依赖 cookie 里的 `a1`，且**必须与 cookie 一致**——
`a1` 对不上时签名一直失败，但报错信息不会提示是 a1 的问题。
所以这里显式检查并在缺失时给出可读原因。

## 缺少 xhshow 时怎么办

**不静默降级**：直接抛错说明装什么包，而不是退化成"没有数据"。
"""
from __future__ import annotations

import logging
import random
import string
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("ylcraft.platforms.xiaohongshu.signing")


class SigningUnavailableError(RuntimeError):
    """签名依赖缺失或签名失败——与"没有数据"是两回事，必须区分。"""


def get_search_id() -> str:
    """生成小红书 `search_id`（搜索接口必需参数）。

    做法参照 ReaJason/xhs：毫秒时间戳的 16 进制 + 16 位随机串。
    实测能被服务端接受（返回 code=1000 成功）。
    """
    now = int(time.time() * 1000)
    chars = string.ascii_letters + string.digits
    return f"{now:x}" + "".join(random.choices(chars, k=16))


def _load_signer():
    """延迟导入 xhshow；缺依赖时给可读错误。

    ## ⚠️ 签名模板版本可能过期（2026-09-29 调研发现）

    `xhshow` 0.2.0 的 `SIGNATURE_DATA_TEMPLATE` 是：

        {"x0": "4.3.5", "x1": "xhs-pc-web", "x2": "Windows",
         "x3": "", "x4": "object"}

    而上游 **issue #110**（2026-09-13，仍 open）报告当前应为
    `x0 = "4.4.3"`、`x4 = ""` —— 否则**翻页请求（非空 cursor）
    会被静默返回空 data**。

    所以这里支持用环境变量覆盖模板，**不改 site-packages**
    （改 site-packages 会被 `pip install -U` 冲掉，也不好追溯）：

        YLCRAFT_XHS_SDK_VERSION=4.4.3    # 覆盖 x0
        YLCRAFT_XHS_X4=                  # 覆盖 x4（空串）

    ⚠️ `CryptoConfig` 是 **frozen dataclass**（实测 `FrozenInstanceError`），
    所以要 `dataclasses.replace` **重建实例**，不能直接赋值。

    默认**不改** —— 保持 xhshow 原样，避免引入未经验证的行为。
    被风控（461）时可以试着手动覆盖来 A/B 验证。
    """
    try:
        from xhshow import Xhshow
    except ImportError as exc:  # pragma: no cover - 依赖缺失路径
        raise SigningUnavailableError(
            "[xhs] 缺少签名依赖 xhshow。请安装：pip install xhshow。"
            "小红书所有 API 都要求 X-s 签名，没有它拿不到任何数据"
            "（报错是 create invalid signature，不是\"没数据\"）。"
        ) from exc

    signer = Xhshow()
    _apply_template_overrides(signer)
    return signer


def _apply_template_overrides(signer) -> None:
    """按环境变量覆盖签名模板（默认不动）。

    见 `_load_signer` 的说明：上游 issue #110 报告模板版本过期。
    这里给一个**可回退的开关**，而不是硬改依赖包。

    ⚠️ 实测 `CryptoConfig` 是 frozen dataclass —— 直接赋值抛
    `FrozenInstanceError`，必须 `dataclasses.replace` 重建。
    """
    import dataclasses
    import os as _os

    sdk = _os.environ.get("YLCRAFT_XHS_SDK_VERSION", "").strip()
    x4 = _os.environ.get("YLCRAFT_XHS_X4", None)
    if not sdk and x4 is None:
        return
    try:
        cfg = signer.config
        tpl = dict(cfg.SIGNATURE_DATA_TEMPLATE)
        if sdk:
            tpl["x0"] = sdk
        if x4 is not None:
            tpl["x4"] = x4
        signer.config = dataclasses.replace(cfg, SIGNATURE_DATA_TEMPLATE=tpl)
        logger.warning(
            "[xhs] 已覆盖签名模板（YLCRAFT_XHS_SDK_VERSION/X4）：%s", tpl,
        )
    except Exception as exc:  # pragma: no cover - 依赖内部结构变化
        logger.warning("[xhs] 覆盖签名模板失败（忽略）：%s: %s",
                       type(exc).__name__, exc)


_signer = None


def _signer_instance():
    global _signer
    if _signer is None:
        _signer = _load_signer()
    return _signer


def _require_a1(cookie: str) -> None:
    """签名依赖 cookie 里的 a1。缺失时给可读原因（否则只会看到签名失败）。"""
    if "a1=" not in (cookie or ""):
        raise SigningUnavailableError(
            "[xhs] Cookie 缺少 a1 字段——签名算法依赖它，缺失时签名必然失败。"
            "请在「账号中心」重新获取小红书 Cookie。"
        )


def sign_get(
    uri: str,
    cookie: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """给 GET 请求生成签名头。

    返回可直接 `headers.update(...)` 的 dict（X-s / X-t / X-s-common 等）。
    """
    _require_a1(cookie)
    signer = _signer_instance()
    try:
        return signer.sign_headers_get(
            uri=uri, cookies=cookie, params=params or {}
        )
    except Exception as exc:
        raise SigningUnavailableError(
            f"[xhs] GET 签名失败（{uri}）：{type(exc).__name__}: {exc}"
        ) from exc


def sign_post(
    uri: str,
    cookie: str,
    payload: Dict[str, Any],
    x_rap: bool = False,
) -> Dict[str, str]:
    """给 POST 请求生成签名头。

    Args:
        x_rap: 是否额外生成 **`x-rap-param`** 风控头。

            `/api/sns/web/v1/feed`（笔记详情）属于风控接口，
            xhshow README 明写 **feed / 搜索 / 笔记发布等需要**它。

            实测 2026-09-29：`/feed` 不带也能拿到 200（我们成功过），
            但风控策略会变 —— **保守起见详情一律带上**。
    """
    _require_a1(cookie)
    signer = _signer_instance()
    try:
        kwargs: Dict[str, Any] = {
            "uri": uri, "cookies": cookie, "payload": payload or {},
        }
        if x_rap:
            kwargs["x_rap"] = True
        try:
            return signer.sign_headers_post(**kwargs)
        except TypeError:
            # 旧版 xhshow 没有 x_rap 参数 —— 退回不带风控头
            # （搜索接口就是这样工作的，所以仍能跑）
            if not x_rap:
                raise
            logger.warning(
                "[xhs] 当前 xhshow 不支持 x_rap，退回不带 x-rap-param（%s）", uri
            )
            kwargs.pop("x_rap", None)
            return signer.sign_headers_post(**kwargs)
    except Exception as exc:
        raise SigningUnavailableError(
            f"[xhs] POST 签名失败（{uri}）：{type(exc).__name__}: {exc}"
        ) from exc


def signing_available() -> bool:
    """xhshow 是否可用（用于体检/自检，不抛错）。"""
    try:
        import xhshow  # noqa: F401
    except ImportError:
        return False
    return True
