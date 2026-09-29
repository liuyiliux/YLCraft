"""YLCraft — 抖音创作者中心数据（**纯 HTTP**）

## 为什么单独做这个

普通抖音站（`www.douyin.com`）只能拿到**公开数据**（别人也能看到的
播放/点赞）。而**创作者中心**（`creator.douyin.com`）有**只有号主能看**的
运营数据：

    播放量 / 主页访问量 / 作品点赞 / 作品分享 / 作品评论 / 净增粉丝
    取关数 / 粉丝总数 / 搜索来源 / 音乐创作 …
    单作品的：完播率、5 秒完播率、2 秒跳出率、平均观看时长、
              粉丝观看占比、下载数、不喜欢数 …

## 实测（2026-09-29）

**裸 Cookie 即可，不需要签名**（无 a_bogus / X-Bogus）：

    GET /aweme/janus/creator/data/overview/all/?last_days_type=1
    → 200, data.{play,new_fans,profile,digg,comment,share,cancel_fans,fans}
         每个是 {option_list: [{date, count, last_day_incr_rate}, ...]}

    GET /janus/douyin/creator/pc/work_list?scene=star_atlas&...
    → 200, items[12], 每项 metrics 有 25 个字段
         view_count=8, like_count=2, completion_rate=0.111, ...

实测与创作者中心页面显示的数字**一致**（粉丝数 122、播放量 1）。

## 数据来源

调研结论（多份独立开源实现交叉验证）：
  · `weizhichao1027-collab/douyin-creator-data-scraper-skill`
    —— **裸 `urllib` + Cookie 直连成功**（决定性证据：不需要签名）
  · `BobXu2358/social-creator-collector` —— `overview/all` 端点与字段路径

## ⚠️ 已知边界（不要承诺做不到的）

  · **单作品「粉丝增量」没有 API** —— 只在投稿列表的 DOM 里
  · 单作品「流量来源 / 进度曲线 / 搜索词」需要浏览器拦截（签名头由页面注入）
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("ylcraft.platforms.douyin.creator")

BASE = "https://creator.douyin.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
)

# 时间范围：接口取值
LAST_DAYS = {7: 1, 15: 2, 30: 3}

# `overview/all` 返回的指标段 → 中文名（用于前端展示）
METRIC_LABELS = {
    "play": "播放量",
    "profile": "主页访问量",
    "digg": "作品点赞",
    "comment": "作品评论",
    "share": "作品分享",
    "new_fans": "净增粉丝",
    "cancel_fans": "取关粉丝",
    "fans": "粉丝总数",
    "account_search": "账号搜索",
    "post_search": "作品搜索",
    "music_create": "音乐创作",
}


def _num(v: Any) -> Any:
    """把接口返回的数值转成数字。

    ## ⚠️ 抖音创作者中心**所有数值都是字符串**

    实测原始响应：

        {"view_count": "8", "completion_rate": "0.111111",
         "avg_view_second": "32.000000", "current_count": "16"}

    如果只认 `isinstance(v, (int, float))` 会**全部过滤成 0**
    （实测踩过：作品指标看起来"全 0"，其实数据都在）。

    整数返回 int，小数返回 float —— 保持前端渲染友好。
    """
    if isinstance(v, bool):
        return 0
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return 0
        try:
            f = float(s)
        except ValueError:
            return 0
        return int(f) if f.is_integer() else f
    return 0


def _headers(cookie: str) -> Dict[str, str]:
    return {
        "user-agent": UA,
        "referer": "https://creator.douyin.com/",
        "accept": "application/json,text/plain,*/*",
        "cookie": cookie,
    }


async def fetch_overview(cookie: str, days: int = 7) -> Optional[Dict[str, Any]]:
    """取账号总览（含每日趋势）。

    Args:
        days: 7 / 15 / 30（接口用 `last_days_type` = 1/2/3）

    Returns:
        {
          "days": 7,
          "metrics": {
             "play": {"label": "播放量", "total": N, "series": [{date, count}, ...]},
             ...
          },
          "raw": <原始 data>
        }
        失败返回 None（调用方决定怎么报）。
    """
    if not cookie:
        raise RuntimeError(
            "[douyin.creator] 需要抖音登录 Cookie —— 创作者中心数据仅号主可见。"
            "请先在「账号中心」登录抖音。"
        )

    last_days_type = LAST_DAYS.get(days, 1)
    url = (f"{BASE}/aweme/janus/creator/data/overview/all/"
           f"?last_days_type={last_days_type}")

    async with httpx.AsyncClient(timeout=40, follow_redirects=True) as c:
        r = await c.get(url, headers=_headers(cookie))

    if r.status_code in (401, 403):
        raise RuntimeError(
            f"[douyin.creator] 创作者中心拒绝访问（HTTP {r.status_code}）——"
            "登录态可能已失效，请在「账号中心」重新登录抖音。"
        )
    if r.status_code != 200:
        raise RuntimeError(
            f"[douyin.creator] 总览接口返回 HTTP {r.status_code}。"
            f"（body 前 120：{r.text[:120]!r}）"
        )

    payload = r.json()
    data = payload.get("data") or {}
    if not data:
        logger.info("[douyin.creator] 总览接口没有 data")
        return None

    metrics: Dict[str, Any] = {}
    for key, seg in data.items():
        if not isinstance(seg, dict):
            continue
        opts = seg.get("option_list")
        if not isinstance(opts, list):
            continue
        series: List[Dict[str, Any]] = []
        for o in opts:
            if not isinstance(o, dict):
                continue
            series.append({
                "date": o.get("date") or "",
                "count": _num(o.get("count")),
                "incr_rate": o.get("last_day_incr_rate"),
            })
        metrics[key] = {
            "label": METRIC_LABELS.get(key, key),
            # ⚠️ 用 `current_count` 作为"当期合计" —— 这是接口直接给的
            # （`data.play.current_count = "16"`）。
            # **不要**自己把 series 里的 count 加起来：
            # `fans` 那类是"总数快照"（每天都记 122），累加会得到 854 这种
            # 无意义数字（实测踩过）。
            "total": _num(seg.get("current_count")),
            # 环比增量（接口给的 `last_period_incr`）
            "period_incr": _num(seg.get("last_period_incr")),
            "series": series,
        }

    logger.info(
        "[douyin.creator] 总览 %d 天，%d 个指标", days, len(metrics)
    )
    return {"days": days, "metrics": metrics, "raw": data}


async def fetch_works(
    cookie: str,
    count: int = 20,
    max_cursor: int = 0,
) -> Dict[str, Any]:
    """取作品列表（含每条的详细 metrics）。

    ⚠️ **19 位 `aweme_id` 有精度陷阱** —— JS 的 `JSON.parse` 会把它
    四舍五入（末几位变 0）。httpx 用 Python 的 json 解析（int 无损），
    所以这里是安全的；但**前端拿到后不要再经 JS Number 处理**。
    """
    if not cookie:
        raise RuntimeError("[douyin.creator] 需要抖音登录 Cookie。")

    url = (
        f"{BASE}/janus/douyin/creator/pc/work_list"
        f"?scene=star_atlas&device_platform=android&aid=1128"
        f"&status=0&count={int(count)}&max_cursor={int(max_cursor)}"
        f"&cookie_enabled=true&screen_width=1920&screen_height=1080"
    )
    async with httpx.AsyncClient(timeout=40, follow_redirects=True) as c:
        r = await c.get(url, headers=_headers(cookie))

    if r.status_code in (401, 403):
        raise RuntimeError(
            f"[douyin.creator] 作品列表被拒绝（HTTP {r.status_code}）——"
            "登录态可能已失效。"
        )
    if r.status_code != 200:
        raise RuntimeError(
            f"[douyin.creator] 作品列表返回 HTTP {r.status_code}。"
        )

    payload = r.json()
    # 两代形态都兼容
    items = payload.get("items") or payload.get("aweme_list") or []
    works = [w for w in (parse_work(it) for it in items) if w is not None]

    return {
        "works": works,
        "has_more": bool(payload.get("has_more")),
        "max_cursor": payload.get("max_cursor") or 0,
    }


def parse_work(it: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """解析一条作品。取不到的字段留空/0，**不编造**。"""
    if not isinstance(it, dict):
        return None

    wid = str(it.get("id") or it.get("aweme_id") or "")
    if not wid:
        return None

    # 两代形态：新版在 `metrics`，旧版在 `statistics`
    m = it.get("metrics") or it.get("statistics") or {}
    if not isinstance(m, dict):
        m = {}

    def num(*keys):
        for k in keys:
            v = m.get(k)
            if v is None:
                continue
            got = _num(v)
            if got:
                return got
        return 0

    return {
        "id": wid,
        "title": str(it.get("description") or ""),
        "create_time": it.get("create_time") or 0,
        "cover": _cover_url(it.get("cover")),
        "type": it.get("type"),
        # 核心运营指标
        "play_count": num("view_count", "play_count"),
        "like_count": num("like_count", "digg_count"),
        "comment_count": num("comment_count"),
        "share_count": num("share_count"),
        "favorite_count": num("favorite_count", "collect_count"),
        "danmaku_count": num("danmaku_count"),
        # 只有创作者中心才有的指标
        "subscribe_count": num("subscribe_count"),          # 净增粉丝
        "completion_rate": num("completion_rate"),          # 完播率
        "completion_rate_5s": num("completion_rate_5s"),    # 5 秒完播
        "bounce_rate_2s": num("bounce_rate_2s"),            # 2 秒跳出
        "avg_view_second": num("avg_view_second"),          # 平均观看时长
        "avg_view_proportion": num("avg_view_proportion"),
        "fan_view_proportion": num("fan_view_proportion"),  # 粉丝观看占比
        "cover_show": num("cover_show"),
        "download_count": num("download_count"),
        "dislike_count": num("dislike_count"),
        "raw": it,
    }


def _cover_url(cover: Any) -> str:
    """从 cover 结构里取一张图。"""
    if not isinstance(cover, dict):
        return ""
    urls = cover.get("url_list") or cover.get("urlList") or []
    if isinstance(urls, list) and urls:
        return str(urls[0])
    return ""
