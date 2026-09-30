"""用户搜索 / 资料 / 作品列表 的 HTTP 路由（抖音 + 小红书共用形状）。

## 为什么两个平台合成一个路由文件

两边能力与返回结构**完全一致**（都是 UserProfile + SearchResult），
前端可以共用同一个面板，只是 platform 参数不同。

## 实测（2026-09-27）

    抖音：搜索「李子柒」→ 5657万粉；资料 → 4830万粉/获赞2.55亿/作品774
    小红书：搜索「美食」→ 吕小厨爱美食 140.9万粉；资料/作品均通

## 为什么不做成"平台各自的路由"

B站已有 `/api/v1/bilibili/up/profile` 与 `/up/videos`（历史原因）。
新平台若也各写一套，前端要为每个平台写一份面板。
这里统一成 `/api/v1/users/*?platform=xxx`，B站保持原样（不破坏既有调用）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.platforms.login_health import (
    netscape_to_header,
    resolve_connection,
)
# ⚠️ 登录失效的**统一异常** —— `/users/me` 要把它映射成 401（不是 500）
#
# 语义：需要用户**重新登录**（≠ 风控，风控是 PlatformUnavailableError）。
# 详见 `platforms/types.py::LoginExpiredError` 的说明。
from app.services.platforms.types import LoginExpiredError

logger = logging.getLogger("ylcraft.api.users")

router = APIRouter()

# 支持"用户搜索/资料/作品列表"的平台及其连接平台名
#
# 抖音/小红书已实测；B站用既有 /bilibili/up/* 路由，不在这里重复。
SUPPORTED = {
    "douyin": {"conn_platform": "DOUYIN", "cookie_domain": "douyin"},
    "xiaohongshu": {"conn_platform": "XHS", "cookie_domain": "xiaohongshu"},
    # 别名，容忍前端传 xhs
    "xhs": {"conn_platform": "XHS", "cookie_domain": "xiaohongshu"},
    # 微博：用户搜索**免登录可用**（实测）；「我的数据」需登录
    "weibo": {"conn_platform": "WEIBO", "cookie_domain": "weibo"},
    "wb": {"conn_platform": "WEIBO", "cookie_domain": "weibo"},
    # X（原 Twitter）：纯 HTTP，需 auth_token + ct0
    "twitter": {"conn_platform": "TWITTER", "cookie_domain": "x.com"},
    "x": {"conn_platform": "TWITTER", "cookie_domain": "x.com"},
    "tw": {"conn_platform": "TWITTER", "cookie_domain": "x.com"},
    # 快手：搜索/搜博主/「我的数据」都已打通（2026-09-30）
    # ⚠️ 签名要从浏览器抓（`__NS_hxfalcon` 是混淆 JS，纯 HTTP 拿不到）
    "kuaishou": {"conn_platform": "KUAISHOU", "cookie_domain": "kuaishou"},
    "ks": {"conn_platform": "KUAISHOU", "cookie_domain": "kuaishou"},
}


class UserItem(BaseModel):
    """统一用户结构。"""
    id: str = ""
    name: str = ""
    avatar: str = ""
    platform: str = ""
    followers: int = 0
    following: int = 0
    total_likes: int = 0
    total_videos: int = 0
    desc: str = ""
    verified: bool = False
    # 各平台特有：抖音的 sec_uid（查作品列表要用）、小红书的 xsec_token
    sec_uid: str = ""
    xsec_token: str = ""
    raw_data: Dict[str, Any] = {}


class UserSearchResponse(BaseModel):
    success: bool
    data: List[UserItem] = []
    message: str = ""


class UserProfileResponse(BaseModel):
    success: bool
    data: Optional[UserItem] = None
    message: str = ""


class UserVideoItem(BaseModel):
    id: str = ""
    title: str = ""
    cover: str = ""
    url: str = ""
    type: str = ""
    likes: int = 0


class UserVideosResponse(BaseModel):
    success: bool
    data: List[UserVideoItem] = []
    message: str = ""


def _resolve(platform: str) -> Dict[str, str]:
    cfg = SUPPORTED.get((platform or "").strip().lower())
    if not cfg:
        raise HTTPException(
            status_code=400,
            detail=(
                f"平台 {platform!r} 不支持用户查询。"
                f"当前支持：{', '.join(sorted(SUPPORTED))}。"
                "（B站请用 /api/v1/bilibili/up/* 系列接口）"
            ),
        )
    return cfg


def _to_item(p) -> UserItem:
    raw = p.raw_data or {}
    return UserItem(
        id=p.id,
        name=p.name,
        avatar=p.avatar,
        platform=p.platform,
        followers=p.followers,
        following=p.following,
        total_likes=p.total_likes,
        total_videos=p.total_videos,
        desc=p.desc,
        verified=p.verified,
        # 抖音：查作品列表必须用 sec_uid
        sec_uid=raw.get("sec_uid") or "",
        # 小红书：部分接口需要 xsec_token
        xsec_token=raw.get("xsec_token") or "",
        raw_data=raw,
    )


def _get_cookie_for(platform: str) -> str:
    """取某平台的 cookie（`k=v; k2=v2` 形式）。取不到返回空串。

    与 `_client_for` 的区别：这个**不建客户端**，只给需要裸 cookie
    的调用方（如创作者中心接口 —— 它们不走平台客户端）。
    """
    try:
        cfg = _resolve(platform)
        _conn_id, raw = resolve_connection("", cfg["conn_platform"])
        if not raw:
            return ""
        return netscape_to_header(raw, cfg["cookie_domain"]) or ""
    except Exception as exc:
        logger.warning("[users] 取 %s cookie 失败：%s", platform, exc)
        return ""


async def _client_for(platform: str):
    """按连接取 cookie，建平台客户端。"""
    cfg = _resolve(platform)
    _conn_id, raw = resolve_connection("", cfg["conn_platform"])
    if not raw:
        raise HTTPException(
            status_code=400,
            detail=(
                f"没有可用的{platform}连接。请先在「账号中心」获取并保存"
                "该平台的登录态，再使用用户查询。"
            ),
        )
    from app.services.platforms import create_client
    from app.services.platforms.types import LoginExpiredError

    cookie = netscape_to_header(raw, cfg["cookie_domain"])
    # mode 按平台选：
    #   · 抖音 / 小红书 / X → api
    #       （小红书内部自己签名；X 纯 HTTP，需 transaction-id）
    #   · 微博 → patchright（依赖 Service Worker，见
    #     `services/platforms/weibo/search_patchright.py`）
    #   · 快手 → **api（但它内部会开浏览器）**
    #       签名 `__NS_hxfalcon` 是混淆 JS，纯 HTTP 拿不到 ——
    #       客户端自己起一个**无头**会话抓签名（见 `kuaishou/client.py`）。
    #       所以这里传 `api` 是对的，浏览器由客户端内部管理。
    client_name = platform
    if client_name in ("xhs",):
        client_name = "xiaohongshu"
    elif client_name in ("wb",):
        client_name = "weibo"
    elif client_name in ("x", "tw"):
        client_name = "twitter"
    elif client_name in ("ks",):
        client_name = "kuaishou"
    mode = "patchright" if client_name == "weibo" else "api"
    client = create_client(client_name, mode=mode, cookie=cookie,
                           conn_id=conn_id_str(platform))
    if client is None:
        raise HTTPException(status_code=500, detail=f"{platform} 客户端未注册")
    return client


def conn_id_str(platform: str) -> str:
    """取该平台的连接 id（连不上就给空串，不影响纯 HTTP 路径）。"""
    try:
        cfg = _resolve(platform)
        cid, _raw = resolve_connection("", cfg["conn_platform"])
        return cid or ""
    except Exception:
        return ""


@router.get(
    "/search",
    response_model=UserSearchResponse,
    summary="搜索用户（抖音/小红书）",
)
async def search_users(
    platform: str = Query(..., description="平台：douyin / xiaohongshu"),
    keyword: str = Query(..., description="搜索关键词"),
    max_results: int = Query(20, ge=1, le=50),
):
    """按关键词搜用户。

    实测：抖音「李子柒」→ 5657万粉博主；小红书「美食」→ 140.9万粉博主。
    """
    client = await _client_for(platform)
    try:
        async with client:
            users = await client.search_users(keyword, max_results=max_results)
        return UserSearchResponse(
            success=True, data=[_to_item(u) for u in users],
            message=f"找到 {len(users)} 个用户",
        )
    except HTTPException:
        raise
    except Exception as exc:
        # ⚠️ 限流要返回 **429**（不是 500）—— 它是"稍后重试"，
        # 不是服务端故障。前端据此提示"等一会儿再试"
        # 而不是"服务器错误"（2026-09-29）。
        if type(exc).__name__ == "DouyinSearchRateLimited":
            raise HTTPException(status_code=429, detail=str(exc))
        logger.error("[users/search] %s %r 失败: %s", platform, keyword, exc)
        raise HTTPException(status_code=500, detail=f"搜索用户失败: {exc}")


@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="获取自己账号的资料（抖音/小红书）",
)
async def get_self_profile(
    platform: str = Query(..., description="平台：douyin / xiaohongshu"),
):
    """查**当前连接账号自己**的资料（「我的数据」用）。

    与 `/users/profile` 的区别：不需要传 user_id / sec_uid，
    直接用连接里的登录态。

    实测：
        抖音   逸流AI | 粉丝122 关注3 获赞2735 作品22
        小红书 逸流AI | 粉丝195 关注2 获赞2930 作品73
    """
    client = await _client_for(platform)
    if not hasattr(client, "get_self_profile"):
        raise HTTPException(
            status_code=400,
            detail=f"{platform} 不支持查询自己的资料",
        )
    try:
        async with client:
            profile = await client.get_self_profile()
        if profile is None:
            # 平台没抛 LoginExpiredError，但也拿不到 ——
            # 仍然返回 success=False（前端显示"未获取到"），
            # 但**提示要可操作**（指向重新登录）。
            return UserProfileResponse(
                success=False, data=None,
                message="未能获取自己的资料 —— 登录态可能已失效，"
                        "请在「账号中心」重新获取该平台登录态",
            )
        return UserProfileResponse(success=True, data=_to_item(profile), message="获取成功")
    except HTTPException:
        raise
    except LoginExpiredError as exc:
        # ⚠️ **登录失效要 401，不是 500**（2026-09-30）
        #
        # 语义不同：500 = 服务端故障（用户什么都做不了）；
        # 401 = 需要重新登录（用户可以自己解决）。前端据此提示
        # "请重新登录"，而不是"加载失败"。
        logger.warning("[users/me] %s 登录态失效: %s", platform, str(exc)[:160])
        raise HTTPException(status_code=401, detail=str(exc))
    except Exception as exc:
        logger.error("[users/me] %s 失败: %s", platform, exc)
        raise HTTPException(status_code=500, detail=f"获取我的资料失败: {exc}")


@router.get(
    "/creator/overview",
    summary="创作者中心：账号总览（仅号主可见的运营数据）",
)
async def get_creator_overview(
    platform: str = Query("douyin", description="平台：目前支持 douyin"),
    days: int = Query(7, description="时间范围：7 / 15 / 30"),
):
    """取**创作者中心**的账号总览（含每日趋势）。

    ## 与 `/users/me` 的区别

    `/users/me` 拿的是**公开资料**（别人也能看到的粉丝/获赞）。
    这里拿的是**只有号主能看**的运营数据：

        播放量 / 主页访问量 / 作品点赞 / 作品分享 / 作品评论
        净增粉丝 / 取关粉丝 / 粉丝总数 / 搜索来源 / 音乐创作

    ## 实测（2026-09-29）

    抖音创作者中心**纯 HTTP + 裸 cookie 即可**，不需要签名：

        GET creator.douyin.com/aweme/janus/creator/data/overview/all/
        → data.{play,new_fans,profile,digg,comment,share,...}
            每个 {current_count, last_period_incr, option_list[{date,count}]}

    实测与创作者中心页面显示的数字**一致**（播放量 16 / 主页访问 1 / 点赞 1）。
    """
    if platform not in ("douyin", "dy"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"创作者中心总览暂只支持抖音（当前 {platform}）。"
                "小红书请用 `/users/creator/xhs/overview`。"
            ),
        )

    from app.services.platforms.douyin import creator as dy_creator

    cookie = _get_cookie_for("douyin")
    if not cookie:
        raise HTTPException(
            status_code=400,
            detail="没有可用的抖音连接 —— 请先在「账号中心」登录抖音。",
        )
    try:
        data = await dy_creator.fetch_overview(cookie, days=days)
    except Exception as exc:
        logger.error("[users/creator/overview] 失败: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    if data is None:
        return {
            "success": False, "data": None,
            "message": "创作者中心没有返回数据 —— 该账号可能还没有创作数据",
        }
    return {"success": True, "data": data, "message": "获取成功"}


@router.get(
    "/creator/xhs/overview",
    summary="小红书创作服务平台：账号总览",
)
async def get_xhs_creator_overview(
    period: str = Query("seven", description="时间范围：seven（近7天）/ thirty（近30天）"),
):
    """取**小红书创作服务平台**的账号总览。

    ## 与 `/users/me` 的区别

    普通站只有公开数据（点赞/收藏）。创作服务平台有**只有号主能看**的：
    曝光数 / 观看数 / 封面点击率 / 视频完播率 / 平均观看时长 /
    净涨粉 / 取消关注 / 主页访客 …

    ## 实测（2026-09-29，与创作者后台页面完全一致）

        曝光数 759（环比 +96%）  观看数 157（环比 +503%）
        封面点击率 4.4%          视频完播率 3.4%
        主页访客 9（环比 -40%）  净涨粉 1

    ## 登录态**与主站通用**

    不需要单独登录（cookie domain 是 `.xiaohongshu.com`）。
    但**过期的 web_session 依然存在** —— 若报 401，请重新扫码登录。
    """
    from app.services.platforms.xiaohongshu import creator as xhs_creator

    cookie = _get_cookie_for("xiaohongshu")
    if not cookie:
        raise HTTPException(
            status_code=400,
            detail="没有可用的小红书连接 —— 请先在「账号中心」登录小红书。",
        )
    try:
        data = await xhs_creator.fetch_overview(cookie, period=period)
    except Exception as exc:
        logger.error("[users/creator/xhs/overview] 失败: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    return {"success": True, "data": data, "message": "获取成功"}


@router.get(
    "/creator/xhs/fans",
    summary="小红书创作服务平台：粉丝数据",
)
async def get_xhs_creator_fans(
    period: str = Query("seven", description="seven / thirty"),
):
    """取涨粉/掉粉/粉丝总数及日趋势。"""
    from app.services.platforms.xiaohongshu import creator as xhs_creator

    cookie = _get_cookie_for("xiaohongshu")
    if not cookie:
        raise HTTPException(
            status_code=400, detail="没有可用的小红书连接。"
        )
    try:
        data = await xhs_creator.fetch_fans(cookie, period=period)
    except Exception as exc:
        logger.error("[users/creator/xhs/fans] 失败: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))
    return {"success": True, "data": data, "message": "获取成功"}


@router.get(
    "/creator/works",
    summary="创作者中心：作品列表（含完播率等深度指标）",
)
async def get_creator_works(
    platform: str = Query("douyin", description="平台：目前支持 douyin"),
    count: int = Query(20, description="每页条数"),
    max_cursor: int = Query(0, description="翻页游标（上一页返回的 max_cursor）"),
):
    """取创作者中心的**作品列表**，含普通接口拿不到的深度指标：

        完播率 / 5 秒完播率 / 2 秒跳出率 / 平均观看时长
        粉丝观看占比 / 净增粉丝 / 下载数 / 不喜欢数 …

    ⚠️ **单作品的「粉丝增量」抖音没有 API**（只在投稿列表 DOM 里），
    所以这里不提供 —— 不编造。
    """
    if platform not in ("douyin", "dy"):
        raise HTTPException(
            status_code=400,
            detail=f"创作者中心暂只支持抖音（当前 {platform}）。",
        )

    from app.services.platforms.douyin import creator as dy_creator

    cookie = _get_cookie_for("douyin")
    if not cookie:
        raise HTTPException(
            status_code=400,
            detail="没有可用的抖音连接 —— 请先在「账号中心」登录抖音。",
        )
    try:
        data = await dy_creator.fetch_works(
            cookie, count=count, max_cursor=max_cursor
        )
    except Exception as exc:
        logger.error("[users/creator/works] 失败: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    return {"success": True, "data": data, "message": "获取成功"}


@router.get(
    "/profile",
    response_model=UserProfileResponse,
    summary="获取用户资料（抖音/小红书）",
)
async def get_user_profile(
    platform: str = Query(..., description="平台：douyin / xiaohongshu"),
    user_id: str = Query("", description="用户 ID（小红书用数字 id）"),
    sec_uid: str = Query("", description="抖音专用：sec_uid（**抖音必须用它**）"),
):
    """取用户资料。

    ⚠️ **抖音必须传 `sec_uid`**（不是数字 uid）——实测用数字 uid 得到空页面。
    `sec_uid` 从 `/users/search` 的返回里拿。
    """
    client = await _client_for(platform)
    target = sec_uid if (sec_uid and platform.lower() == "douyin") else user_id
    if not target:
        raise HTTPException(
            status_code=400,
            detail="缺少用户标识：抖音请传 sec_uid，小红书请传 user_id",
        )
    try:
        async with client:
            profile = await client.get_user_profile(target)
        if profile is None:
            return UserProfileResponse(
                success=False, data=None, message="用户不存在或资料不可见"
            )
        return UserProfileResponse(success=True, data=_to_item(profile), message="获取成功")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[users/profile] %s %s 失败: %s", platform, target[:16], exc)
        raise HTTPException(status_code=500, detail=f"获取用户资料失败: {exc}")


@router.get(
    "/videos",
    response_model=UserVideosResponse,
    summary="获取用户作品列表（抖音/小红书/微博/X/B站）",
)
async def get_user_videos(
    platform: str = Query(..., description="平台：douyin / xiaohongshu / weibo / twitter"),
    user_id: str = Query("", description="用户 ID（各平台含义见下）"),
    sec_uid: str = Query("", description="抖音专用：sec_uid（**抖音必须用它**）"),
    max_results: int = Query(20, ge=1, le=50),
):
    """取用户作品列表（含图文与视频，带分页）。

    ## 各平台的 `user_id` 含义（**实测确认**）

        抖音     sec_uid（**必须**，用 user_id 会失败）
        小红书   数字 id
        微博     数字 uid
        X        数字 userId **或 handle**（后端会自动转换）

    实测：
        微博  15 条（`containerid=107603{uid}` → `cards[].mblog`）
        X     2 条（`UserTweets`，handle 自动转数字 id）
    """
    client = await _client_for(platform)
    target = sec_uid if (sec_uid and platform.lower() == "douyin") else user_id
    if not target:
        raise HTTPException(
            status_code=400,
            detail="缺少用户标识：抖音请传 sec_uid，其余平台请传 user_id",
        )
    try:
        async with client:
            items = await client.get_user_videos(target, max_results=max_results)
        return UserVideosResponse(
            success=True,
            data=[
                UserVideoItem(
                    id=v.id, title=v.title, cover=v.cover, url=v.url,
                    type=v.type, likes=v.likes,
                )
                for v in items
            ],
            message=f"获取到 {len(items)} 个作品",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[users/videos] %s %s 失败: %s", platform, target[:16], exc)
        raise HTTPException(status_code=500, detail=f"获取作品列表失败: {exc}")
