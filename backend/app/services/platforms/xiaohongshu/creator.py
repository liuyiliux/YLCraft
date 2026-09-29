"""YLCraft — 小红书创作服务平台数据（**纯 HTTP**）

## 为什么做这个

普通小红书站只能拿到**公开数据**（点赞/收藏，谁都看得到）。
**创作服务平台**（`creator.xiaohongshu.com`）有**只有号主能看**的
运营数据：

    曝光数 / 观看数 / 封面点击率 / 视频完播率 / 平均观看时长
    净涨粉 / 取消关注 / 主页访客 / 弹幕数 …

## 签名：与主站是**两套算法**（实测 2026-09-29）

    主站 edith         → `XYS_`（xhshow 默认）
    创作中心 creator   → 也可以用 `XYS_`，但要用**带参数的 GET 签名**

⚠️ 我第一版手写了 `XYW_`（MD5 → AES-128-CBC）签名 —— 算法是对的
（调研从 `jackwener/xiaohongshu-cli` 取得），但手写版少了字段导致
**406**。改用 `xhshow.sign_headers_get()` 后两种格式都返回 200。

**结论：直接用 xhshow 的 GET 签名即可**，不必手写 AES。保留 `_sign_creator`
作为参考实现（万一 xhshow 将来不适用）。

## 登录态：**与主站通用**（实测确认）

不需要单独登录 —— cookie 的 domain 是 `.xiaohongshu.com`，
creator/customer 子域都能收到。

⚠️ 但**过期的 `web_session` 依然存在**，所以"有 cookie"不等于"已登录"。
实测登录态失效时主站正文会写"**电脑设备登录超限，请重新登录**"。

## 实测数据（与创作者后台页面完全一致）

    曝光数 impl_count  = 759
    观看数 view_count  = 157
    净涨粉 net_rise_fans_count = 1
    主页访客 home_view_count   = 9

## ⚠️ 字段命名不统一（调研明确警告）

    总览接口      → `impl_count` / `cover_click_rate`（snake_case）
    作品列表接口  → `imp_count`  / `coverClickRate`（camelCase）

**不能复用同一个解析器** —— 本模块按需处理。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("ylcraft.platforms.xiaohongshu.creator")

CREATOR_BASE = "https://creator.xiaohongshu.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
)

# 账号总览（7/30 日 + 全部日趋势）
ACCOUNT_BASE = "/api/galaxy/v2/creator/datacenter/account/base"
# 粉丝数据
FANS_OVERALL = "/api/galaxy/creator/data/fans/overall_new"
# 作品列表（数据页）
NOTE_ANALYZE_LIST = "/api/galaxy/creator/datacenter/note/analyze/list"
# 账号信息
USER_INFO = "/api/galaxy/user/info"

# 总览指标 → 中文名
#
# ⚠️ **这个字典同时充当白名单** —— 接口的 `seven`/`thirty` 里混着
# 一堆非指标字段（`begin_time`/`end_time`/`summary`/`publish_*_rate` 等），
# 如果遍历所有字段会把它们当指标吐给前端（实测踩过）。
# 只输出这里列出的键。
METRIC_LABELS = {
    # 核心
    "impl_count": "曝光数",
    "view_count": "观看数",
    "cover_click_rate": "封面点击率",
    "like_count": "点赞数",
    "collect_count": "收藏数",
    "comment_count": "评论数",
    "share_count": "分享数",
    "rise_fans_count": "新增关注",
    "loss_fans_count": "取消关注",
    "net_rise_fans_count": "净涨粉",
    "home_view_count": "主页访客",
    "avg_view_time": "平均观看时长",
    "video_full_view_rate": "视频完播率",
    "view_time_avg": "人均观看时长",
    "publish_note_num": "发布笔记数",
    "publish_video_note_num": "发布视频数",
    "publish_normal_note_num": "发布图文数",
    "danmaku_count": "弹幕数",
    "quote_count": "引用数",
}

# 比率类指标（前端按百分比展示）
RATE_KEYS = frozenset({
    "cover_click_rate", "video_full_view_rate",
    "like_count_rate", "collect_count_rate",
    "comment_count_rate", "share_count_rate",
})


def _get_headers(cookie: str) -> Dict[str, str]:
    return {
        "user-agent": UA,
        "origin": CREATOR_BASE,
        "referer": f"{CREATOR_BASE}/",
        "content-type": "application/json;charset=UTF-8",
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "cookie": cookie,
    }


def _sign_get(api_with_query: str, cookie: str) -> Dict[str, str]:
    """给 GET 签名（用 xhshow）。

    ⚠️ `api_with_query` **必须含完整 query 串** —— 签名是对整条 URI
    做的摘要，少一个参数签名就对不上。
    """
    from .signing import sign_get

    # sign_get 内部会把 params 拼进去；这里直接传完整 uri、params 留空
    return sign_get(api_with_query, cookie, {})


async def _request(
    cookie: str,
    api: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """带签名的 GET。返回接口的 `data`。

    异常要**可操作**（不静默返回空）。
    """
    if not cookie:
        raise RuntimeError(
            "[xhs.creator] 需要小红书登录 Cookie —— 创作中心数据仅号主可见。"
            "请先在「账号中心」登录小红书。"
        )

    query = ""
    if params:
        from urllib.parse import urlencode

        query = "?" + urlencode(params)
    api_with_query = f"{api}{query}"

    headers = _get_headers(cookie)
    headers.update(_sign_get(api_with_query, cookie))

    async with httpx.AsyncClient(timeout=40, follow_redirects=True) as c:
        r = await c.get(f"{CREATOR_BASE}{api_with_query}", headers=headers)

    if r.status_code == 401:
        raise RuntimeError(
            "[xhs.creator] 创作中心返回 401 —— 登录态已失效。"
            "请在「账号中心」重新登录小红书"
            "（注意：过期的 web_session 依然存在，所以需要重新扫码）。"
        )
    if r.status_code == 406:
        raise RuntimeError(
            "[xhs.creator] 创作中心返回 406（签名格式被拒）。"
            "请检查 uri 是否带了完整 query 串 —— 签名是对整条 URI 做的。"
        )
    if r.status_code != 200:
        raise RuntimeError(
            f"[xhs.creator] 创作中心返回 HTTP {r.status_code}。"
            f"（body 前 120：{r.text[:120]!r}）"
        )

    payload = r.json()
    if not payload.get("success"):
        code = payload.get("code")
        msg = payload.get("msg")
        if code in (-100, -1):
            raise RuntimeError(
                f"[xhs.creator] 创作中心报未登录（code={code} {msg}）——"
                "请在「账号中心」重新登录小红书。"
            )
        raise RuntimeError(f"[xhs.creator] 创作中心返回失败：code={code} msg={msg!r}")

    return payload.get("data") or {}


async def fetch_overview(cookie: str, period: str = "seven") -> Dict[str, Any]:
    """取账号总览（含每日趋势）。

    Args:
        period: `seven`(近7天) / `thirty`(近30天)

    Returns:
        {
          "period": "seven",
          "metrics": {
             "impl_count": {"label": "曝光数", "value": 759,
                            "is_rate": False, "trend": [{date, count}, ...]},
             ...
          },
          "summary": {...},
        }
    """
    data = await _request(cookie, ACCOUNT_BASE)
    seg = data.get(period) or {}
    if not isinstance(seg, dict):
        seg = {}

    metrics: Dict[str, Any] = {}
    # ⚠️ 只遍历白名单键 —— `seven` 里混着 `begin_time`/`end_time`/`summary`
    # 等非指标字段，遍历全部会把它们当指标吐出去（实测踩过）。
    for key in METRIC_LABELS:
        if key not in seg:
            continue
        val = seg.get(key)
        if not isinstance(val, (int, float, str)):
            continue
        trend = _pair_trend(seg, key)
        rate = _num(seg.get(f"{key}_rate"))
        cycle_rate = _num(seg.get(f"{key}_cycle_rate"))
        metrics[key] = {
            "label": METRIC_LABELS[key],
            "value": _num(val),
            "is_rate": key in RATE_KEYS,
            "rate": rate,                 # 环比（%）
            "cycle_rate": cycle_rate,     # 周期环比（%）
            "trend": trend,
        }

    logger.info(
        "[xhs.creator] 总览 %s：%d 个指标", period, len(metrics)
    )
    return {
        "period": period,
        "metrics": metrics,
        "summary": seg.get("summary") or {},
        "raw": seg,
    }


def _pair_trend(seg: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    """把指标与它的日趋势数组配对。

    实测总览里趋势数组的命名**不统一**：

        impl_count    → impl_count_list
        view_count    → **view_list**        （不带 _count）
        like_count    → **like_list**
        home_view_count → **home_view_list**
        rise_fans_count → rise_fans_list

    所以按"去掉 `_count` 后缀"再试一次。
    """
    cands = [f"{key}_list", f"{key}_count_list"]
    if key.endswith("_count"):
        cands.append(f"{key[:-6]}_list")   # view_count → view_list
    for cand in cands:
        arr = seg.get(cand)
        if not isinstance(arr, list):
            continue
        out = []
        for it in arr:
            if not isinstance(it, dict):
                continue
            out.append({
                "date": _date_str(it.get("date")),
                "count": _num(it.get("count")),
            })
        if out:
            return out
    return []


def _date_str(ms: Any) -> str:
    """毫秒时间戳 → `YYYY-MM-DD`。"""
    try:
        from datetime import datetime, timezone

        n = float(ms)
        if n > 1e12:
            n = n / 1000
        return datetime.fromtimestamp(n, tz=timezone.utc).astimezone().strftime(
            "%Y-%m-%d"
        )
    except Exception:
        return ""


async def fetch_fans(cookie: str, period: str = "seven") -> Dict[str, Any]:
    """取粉丝数据（涨粉/掉粉/总数 + 日趋势）。"""
    data = await _request(cookie, FANS_OVERALL)
    seg = data.get(period) or {}
    if not isinstance(seg, dict):
        seg = {}

    return {
        "period": period,
        "rise_fans_count": _num(seg.get("rise_fans_count")),
        "leave_fans_count": _num(seg.get("leave_fans_count")),
        "fans_count": _num(seg.get("fans_count")),
        "rise_trend": _list_of(seg, "rise_fans_list"),
        "leave_trend": _list_of(seg, "leave_fans_list"),
        "fans_trend": _list_of(seg, "fans_list"),
        "raw": seg,
    }


def _list_of(seg: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    arr = seg.get(key)
    if not isinstance(arr, list):
        return []
    out = []
    for it in arr:
        if not isinstance(it, dict):
            continue
        out.append({
            "date": _date_str(it.get("date")),
            "count": _num(it.get("count")),
        })
    return out


async def fetch_account(cookie: str) -> Dict[str, Any]:
    """取创作者账号信息（昵称/头像/小红书号）。"""
    data = await _request(cookie, USER_INFO)
    return {
        "user_id": str(data.get("userId") or ""),
        "name": str(data.get("userName") or ""),
        "avatar": str(data.get("userAvatar") or ""),
        "desc": str(data.get("userDesc") or ""),
        "red_id": str(data.get("redId") or ""),
        "raw": data,
    }


async def fetch_notes(
    cookie: str,
    days: int = 7,
    page: int = 1,
    page_size: int = 10,
) -> Dict[str, Any]:
    """取作品列表（含曝光/封面点击率/平均观看时长等深度指标）。

    ⚠️ 字段命名与总览**不一致**：这里用 `imp_count` / `coverClickRate`
    （camelCase），总览用 `impl_count` / `cover_click_rate`（snake）。
    所以单独解析，不复用总览的映射。
    """
    import time

    now_ms = int(time.time() * 1000)
    begin_ms = now_ms - days * 24 * 3600 * 1000

    data = await _request(cookie, NOTE_ANALYZE_LIST, {
        "post_begin_time": begin_ms,
        "post_end_time": now_ms,
        "type": 0,
        "page_size": page_size,
        "page_num": page,
    })

    infos = data.get("note_infos") or []
    notes = [n for n in (parse_note(it) for it in infos) if n is not None]
    return {"notes": notes, "total": _num(data.get("total")), "raw": data}


def parse_note(it: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """解析一条作品数据。取不到留空/0，**不编造**。"""
    if not isinstance(it, dict):
        return None

    nid = str(it.get("id") or "")
    if not nid:
        return None

    return {
        "id": nid,
        "title": str(it.get("title") or ""),
        "type": it.get("type"),
        "post_time": _num(it.get("post_time")),
        "cover": str(it.get("cover_url") or ""),
        # ⚠️ 这里字段是 camelCase（`imp_count` / `coverClickRate`），
        # 与总览接口的 snake_case 不同 —— 调研明确警告过，不要复用解析器。
        "read_count": _num(it.get("read_count")),
        "imp_count": _num(it.get("imp_count")),
        "cover_click_rate": _num(it.get("coverClickRate")),
        "view_time_avg": _num(it.get("view_time_avg")),
        "like_count": _num(it.get("like_count")),
        "fav_count": _num(it.get("fav_count")),
        "comment_count": _num(it.get("comment_count")),
        "share_count": _num(it.get("share_count")),
        "increase_fans_count": _num(it.get("increase_fans_count")),
        "danmaku_count": _num(it.get("danmaku_count")),
        "raw": it,
    }


def _num(v: Any) -> Any:
    """把接口返回的数值转成数字。

    ⚠️ 小红书创作者中心的数值**可能是字符串**（同抖音）——
    只认 int/float 会把它们全过滤成 0。
    """
    if isinstance(v, bool):
        return 0
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        s = v.strip().rstrip("%")
        if not s:
            return 0
        try:
            f = float(s)
        except ValueError:
            return 0
        return int(f) if f.is_integer() else f
    return 0
