"""YLCraft — **统一**登录态体检（所有平台一个入口）。

## 为什么需要统一入口（2026-10-01）

原来体检是**各平台各写一份**：
  · `/api/v1/bilibili/login-health`（最早，6 个分项，最详细）
  · `/api/v1/douyin/login-health`
  · `/api/v1/xhs/login-health`

结果是**前端只接了 B站那个**（体检按钮只在 B站分支渲染）——
用户看到"为什么只有 B站有体检按钮"，而抖音/小红书的接口其实**早就实现了**。
又是本仓库反复犯的"后端实现了但前端没接上"。

而且每个平台各写一份还有个问题：**新平台要重写一遍**，
写的人不写就没有（快手/微博/X/YouTube/Telegram 全都没有）。

所以这里提供 `/api/v1/platforms/{platform}/health` ——
**一个入口覆盖所有平台**，用统一的 **"最小搜索探针"** 做体检。

## 探针思路（比"逐项检查 cookie"更通用）

不管什么平台，**"能不能搜到东西"才是用户关心的**。
所以体检 = 真的跑一次最小搜索（`max_results=1`），然后：

  · 搜到了            → 全部通过 ✅
  · 登录态失效（401） → 报"需重新登录" ❌
  · 风控（429）       → 报"被风控，稍后重试" ⚠️
  · 网络问题（503）   → 报"网络/代理问题" ⚠️
  · 未实现（501）     → 报"该平台未实现采集" ❌

⚠️ **免登录平台（YouTube/Telegram）也能体检** —— 它们没有"登录态"，
但"搜索是否可用"依然是有效信息（VPN 断了就搜不到）。

## 与各平台专属体检的关系

专属体检（B站那 6 项）**更细**，保留不动（它检查字幕/评论/发评论等
B站特有能力的授权）。统一体检是**通用兜底**，两者互补：

    前端"体检"按钮 → 调统一接口（所有平台都有）
    B站详情里额外有"登录态体检" → 调 B站的详细接口
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger("ylcraft.platforms.health")

router = APIRouter()

# 体检用的关键词：短、通用、各平台都有大量结果
PROBE_KEYWORD = "美食"

# 每个平台体检时用的 search_type（要选该平台**默认可用**的那种）
PROBE_SEARCH_TYPE = {
    "bili": "video",
    "bilibili": "video",
    "telegram": "channel",
    "wechat_mp": "account",
    "fanqie": "",          # 番茄没有内容搜索，跳过探针
}

# 探针用的关键词（部分平台语义特殊，见注释）
PROBE_KEYWORD_BY_PLATFORM = {
    # Telegram 的"频道消息"tab 填的是**频道名**而不是关键词
    "telegram": "telegram",
}


def _item(key: str, label: str, ok: bool, message: str,
          data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """体检条目（与 B站 login-health 同构，前端复用同一渲染）。"""
    from app.services.platforms.login_health import health_item

    return health_item(key, label, ok, message, data)


@router.get("/{platform}/health", summary="平台体检（统一入口，所有平台可用）")
async def platform_health(
    platform: str,
    conn_id: str = Query("", description="平台连接 ID（免登录平台可不传）"),
    keyword: str = Query("", description="自定义探针关键词（默认用通用词）"),
):
    """对**任意平台**做一次体检。

    ## 体检什么

      1. **平台是否已实现**（未实现 → 501，直接说清楚"不是搜不到"）
      2. **连接/凭证状态**（需要登录的平台，检查有没有连接）
      3. **真的搜一次**（最小搜索探针 —— 这才是"能不能用"的最终判据）

    ## 返回

    ```json
    {
      "success": true,
      "data": {
        "platform": "xiaohongshu",
        "ready": false,
        "needs_login": true,
        "checks": {
          "implemented": {...},
          "credential":  {...},
          "search":      {...}
        }
      }
    }
    ```
    """
    from app.services.platforms import supported_platforms

    p = (platform or "").strip().lower()
    if not p:
        raise HTTPException(status_code=400, detail="缺少 platform 参数")

    checks: Dict[str, Dict[str, Any]] = {}

    # ---- ① 平台是否已实现 ----
    implemented = p in supported_platforms()
    checks["implemented"] = _item(
        "implemented", "平台支持", implemented,
        "该平台已实现采集" if implemented
        else (
            f"平台 {p!r} **尚未实现采集** —— 这不是「搜不到」，"
            f"是功能没做。当前可用：{', '.join(sorted(supported_platforms()))}"
        ),
    )
    if not implemented:
        return {
            "success": True,
            "data": {
                "platform": p,
                "ready": False,
                "needs_login": False,
                "checks": checks,
            },
        }

    # ---- ② 凭证状态（免登录平台跳过这条）----
    no_login = p in ("youtube", "telegram")
    if no_login:
        checks["credential"] = _item(
            "credential", "登录态", True,
            "该平台**免登录**（取公开数据），无需凭证",
        )
    else:
        from app.services.platforms.login_health import resolve_connection

        conn_platform = {
            "xhs": "XHS", "xiaohongshu": "XHS",
            "douyin": "DOUYIN", "dy": "DOUYIN",
            "bili": "BILIBILI", "bilibili": "BILIBILI",
            "weibo": "WEIBO", "wb": "WEIBO",
            "twitter": "TWITTER", "x": "TWITTER", "tw": "TWITTER",
            "kuaishou": "KUAISHOU", "ks": "KUAISHOU",
        }.get(p, p.upper())
        try:
            actual_id, raw = resolve_connection(conn_id, conn_platform)
        except Exception as exc:
            actual_id, raw = "", ""
            logger.warning("[health] %s 取连接失败：%s", p, exc)

        has_conn = bool(raw)
        checks["credential"] = _item(
            "credential", "登录态", has_conn,
            (
                f"已找到连接（{str(actual_id)[:8]}…，凭证长度 {len(raw)}）"
                if has_conn else
                "**没有可用的连接** —— 请先到「账号中心」获取并保存登录态"
            ),
            {"conn_id": str(actual_id)[:20], "length": len(raw)},
        )
        if not has_conn:
            # 没凭证就不用探针了（探针必然失败，白等 30 秒）
            checks["search"] = _item(
                "search", "搜索", False,
                "没有登录态，无法搜索；请先获取该平台的登录态",
            )
            return {
                "success": True,
                "data": {
                    "platform": p, "ready": False, "needs_login": True,
                    "checks": checks,
                },
            }

    # ---- ③ 最小搜索探针（**真正的判据**）----
    st = PROBE_SEARCH_TYPE.get(p, "note")
    kw = keyword.strip() or PROBE_KEYWORD_BY_PLATFORM.get(p, PROBE_KEYWORD)

    if not st and p == "fanqie":
        # 番茄没有内容搜索能力 —— 如实说明，不假装失败
        checks["search"] = _item(
            "search", "搜索", True,
            "该平台是章节式发布，**没有内容搜索**（不是故障）",
        )
        ready = all(c["ok"] for c in checks.values())
        return {
            "success": True,
            "data": {"platform": p, "ready": ready, "needs_login": False,
                     "checks": checks},
        }

    t0 = time.monotonic()
    try:
        from app.services.crawler.service import CrawlerService

        svc = CrawlerService()
        results = await svc.search_videos(
            platform=p, keyword=kw, max_results=1,
            search_type=st, conn_id=conn_id,
        )
        elapsed = int((time.monotonic() - t0) * 1000)
        n = len(results or [])
        checks["search"] = _item(
            "search", "搜索", n > 0,
            (
                f"搜索正常（用「{kw}」搜到 {n} 条，耗时 {elapsed}ms）"
                if n > 0 else
                f"搜索**返回 0 条**（用「{kw}」探测，耗时 {elapsed}ms）。\n"
                "⚠️ 注意区分两种情况：\n"
                "  · 若该关键词本身内容少 → 换个词再试\n"
                "  · 若**任何词都 0 条** → 多半是登录态失效或风控"
            ),
            {"elapsed_ms": elapsed, "count": n, "keyword": kw},
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        # ⚠️ 按**异常类型**分类（不靠文案匹配 —— 见 error_taxonomy 测试）
        from app.services.platforms.types import (
            ContentNotFoundError,
            LoginExpiredError,
            NetworkError,
            RiskControlError,
        )

        name = type(exc).__name__
        msg = str(exc)
        if isinstance(exc, LoginExpiredError):
            label, hint, needs = "登录态失效", "请到「账号中心」重新获取登录态", True
        elif isinstance(exc, RiskControlError):
            label, hint, needs = "被风控拦截", "稍后重试；必要时换网络/IP", False
        elif isinstance(exc, NetworkError):
            label, hint, needs = "网络问题", "检查网络/代理后重试", False
        elif isinstance(exc, ContentNotFoundError):
            label, hint, needs = "内容不存在", "换个关键词再试", False
        else:
            label, hint, needs = f"搜索失败（{name}）", "请查看下方原因", False

        checks["search"] = _item(
            "search", "搜索", False,
            f"{label}：{msg[:400]}\n\n建议：{hint}",
            {"elapsed_ms": elapsed, "error_type": name},
        )
        ready = False
        return {
            "success": True,
            "data": {"platform": p, "ready": ready, "needs_login": needs,
                     "checks": checks},
        }

    ready = all(c["ok"] for c in checks.values())
    return {
        "success": True,
        "data": {
            "platform": p,
            "ready": ready,
            "needs_login": False,
            "checks": checks,
        },
    }
