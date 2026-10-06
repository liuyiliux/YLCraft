"""微博平台契约测试。

## 调研与实测结论（2026-09-27）

### 1. 微博**必须走浏览器**（httpx 全部失败）

实测所有 HTTP 直连方案都返回 `ok=-100`：

    httpx 直连搜索 API            → HTTP 432 / ok=-100
    走 visitor 两步换访客 Cookie   → 拿到 SUB/SUBP 仍 ok=-100
    补 _T_WM / MLOGIN / XSRF 等    → 仍 ok=-100
    换桌面 UA / 加 sec-fetch 头    → 仍 ok=-100

根因（`bsk debug` 捕获确认）：**`from_service_worker = True`** ——
微博注册了 Service Worker（`m.weibo.cn/`，实测 active），
由它代理请求并注入 httpx 无法复现的上下文。

而在真实浏览器里（**连登录都不需要**）同一 URL 返回
`{"ok":1,"total":870,"cards":[...]}`。

所以微博走 Patchright（与小红书同一套 SessionPool），
但原因不同：小红书要**签名**，微博要 **Service Worker 上下文**。

### 2. 图片原图 URL 的规律

    pics[0].url       = .../orj360/<pid>.jpg    缩略图
    pics[0].large.url = .../mw2000/<pid>.jpg    2048 宽
    original_pic      = .../large/<pid>.jpg     真原图（只有第一张）

**文件名（pid）相同，只有路径段不同** → 每张都能推导原图：
把 `/mw2000/` 等尺寸段换成 `/large/`。

实测：`large` 版 1.88MB vs `mw2000` 版 962KB，都 HTTP 200 可下载。
**下载不需要 Cookie**（httpx 直连成功）。

### 3. 翻页限制

`page=1` 正常（约 9 条正文），**`page=2` 返回 173 字节 HTML 错误页**。
微博真翻页依赖 `since_id` 游标，不是纯 `page`。

所以：**翻页失败不整体报错** —— 第 1 页的数据是有效的。
（踩过：一开始抛错，导致用户连第一页都看不到。）
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend" / "src"


def _read_frontend(rel: str) -> str:
    p = FRONTEND / rel
    if not p.exists():
        pytest.skip(f"前端源码不在预期位置: {rel}")
    return p.read_text(encoding="utf-8", errors="ignore")


# =============================================================================
# 注册完整性（照 docs/platform/ADDING_A_PLATFORM.md 的 8 项清单）
# =============================================================================

def test_platform_type_has_weibo():
    from app.db.models.platform_connection import PlatformType

    assert hasattr(PlatformType, "WEIBO"), "PlatformType 缺 WEIBO"


def test_supported_platforms_has_weibo():
    from app.api.v1 import platforms as platforms_api

    values = {p["value"] for p in platforms_api.SUPPORTED_PLATFORMS}
    assert "weibo" in values, "SUPPORTED_PLATFORMS 缺 weibo"


@pytest.mark.parametrize("table", ["PLATFORM_LOGIN_URLS", "PLATFORM_DOMAINS",
                                   "PLATFORM_TEST_URLS"])
def test_cookie_tables_have_weibo(table: str):
    from app.services.cookies import base as cookie_base

    data = getattr(cookie_base, table)
    assert "weibo" in data, f"{table} 缺 weibo（浏览器取 Cookie 会失败）"


def test_detector_registry_has_weibo():
    from app.services.cookies.platforms import _detector_registry

    assert "weibo" in _detector_registry, "缺微博 detector（账号中心点浏览器会报不支持）"


def test_detector_class_exists():
    from app.services.cookies.platforms.weibo import WeiboDetector

    assert WeiboDetector is not None


def test_frontend_platform_meta_has_weibo():
    src = _read_frontend("pages/accounts/index.tsx")
    assert "'weibo'" in src, "账号中心 PLATFORM_METAS 缺 weibo（用户看不到入口）"


def test_client_registered():
    from app.services.platforms import PlatformClientFactory

    assert "weibo" in PlatformClientFactory._registry, "weibo 客户端未注册"


# =============================================================================
# API 端点定义
# =============================================================================

def test_search_endpoint_and_params():
    from app.services.platforms.weibo.apis import build_search_params

    p = build_search_params("美食", 1, "note")
    # containerid 里**直接拼关键词**（不是独立的 q 参数）——实测确认
    assert p["containerid"] == "100103type=1&q=美食"
    assert p["page_type"] == "searchall"
    assert p["page"] == "1"


@pytest.mark.parametrize("alias,expected", [
    ("note", "1"), ("all", "1"), ("default", "1"),
    ("realtime", "61"), ("popular", "60"), ("hot", "60"),
    ("video", "64"),
])
def test_search_type_aliases(alias: str, expected: str):
    from app.services.platforms.weibo.apis import resolve_search_type

    assert resolve_search_type(alias) == expected


def test_unknown_search_type_falls_back():
    """未知类型回退到综合（给结果比报错有用）。"""
    from app.services.platforms.weibo.apis import resolve_search_type

    assert resolve_search_type("不存在的类型") == "1"
    assert resolve_search_type(None) == "1"


# =============================================================================
# 解析
# =============================================================================

MBLOG_IMAGE = {
    "id": "5120000000000001",
    "text": "今天做了一道<b>红烧肉</b>&nbsp;超好吃！<a href='#'>#美食#</a>",
    "user": {"id": 1234567890, "screen_name": "测试博主"},
    "original_pic": "https://wx1.sinaimg.cn/large/abc.jpg",
    "pics": [
        {"url": "https://wx1.sinaimg.cn/orj360/abc.jpg",
         "large": {"url": "https://wx1.sinaimg.cn/mw2000/abc.jpg", "size": "large"}},
        {"url": "https://wx1.sinaimg.cn/orj360/def.jpg",
         "large": {"url": "https://wx1.sinaimg.cn/mw2000/def.jpg", "size": "large"}},
    ],
    "attitudes_count": 1234,
    "comments_count": 56,
    "reposts_count": 78,
}

MBLOG_VIDEO = {
    "id": "5120000000000002",
    "text": "中秋家宴菜单来啦",
    "user": {"id": 99, "screen_name": "美食视频号"},
    "attitudes_count": 500,
    "page_info": {
        "type": "video",
        "page_pic": {"url": "https://wx4.sinaimg.cn/orj480/cover.jpg"},
        "duration": 135.566,
        "media_info": {"stream_url": "https://f.video.weibocdn.com/hd.mp4"},
        "urls": {
            "mp4_720p_mp4": "https://f.video.weibocdn.com/720p.mp4",
            "mp4_hd_mp4": "https://f.video.weibocdn.com/hd.mp4",
            "mp4_ld_mp4": "https://f.video.weibocdn.com/ld.mp4",
        },
    },
}


def test_parse_mblog_basic():
    from app.services.platforms.weibo.client import parse_mblog

    r = parse_mblog(MBLOG_IMAGE)
    assert r is not None
    assert r.id == "5120000000000001"
    assert r.author == "测试博主"
    assert r.platform == "weibo"
    assert r.likes == 1234 and r.comments == 56 and r.shares == 78
    assert r.url == "https://m.weibo.cn/detail/5120000000000001"


def test_parse_mblog_strips_html():
    """正文是富文本 HTML，要清干净（实测 `<a>` 包话题）。"""
    from app.services.platforms.weibo.client import parse_mblog

    r = parse_mblog(MBLOG_IMAGE)
    assert "<b>" not in r.desc and "<a" not in r.desc
    assert "红烧肉" in r.desc
    assert "#美食#" in r.desc
    assert "&nbsp;" not in r.desc


def test_images_upgraded_to_original():
    """**核心**：每张图都要推导成原图（mw2000 → large）。

    `pics[].large.url` 只有 2048 宽，`original_pic` 才是原图，
    但 `original_pic` 只给第一张 —— 所以要从 pid 推导。
    """
    from app.services.platforms.weibo.client import parse_mblog

    r = parse_mblog(MBLOG_IMAGE)
    imgs = r.raw_data["_images"]
    assert len(imgs) == 2
    assert all("/large/" in u for u in imgs), f"应都升到原图：{imgs}"
    assert "/mw2000/" not in "".join(imgs)


def test_to_original_url_variants():
    from app.services.platforms.weibo.client import _to_original_url

    cases = {
        "https://wx1.sinaimg.cn/mw2000/abc.jpg": "https://wx1.sinaimg.cn/large/abc.jpg",
        "https://wx1.sinaimg.cn/orj360/abc.jpg": "https://wx1.sinaimg.cn/large/abc.jpg",
        "https://wx1.sinaimg.cn/bmiddle/abc.jpg": "https://wx1.sinaimg.cn/large/abc.jpg",
        "https://wx1.sinaimg.cn/thumbnail/abc.jpg": "https://wx1.sinaimg.cn/large/abc.jpg",
    }
    for src, want in cases.items():
        assert _to_original_url(src) == want, src
    # 已经是原图/无关域名 → 原样返回
    already = "https://wx1.sinaimg.cn/large/abc.jpg"
    assert _to_original_url(already) == already
    assert _to_original_url("") == ""


def test_parse_video_picks_highest_quality():
    """视频要取最高清晰度（720p > hd > ld）。"""
    from app.services.platforms.weibo.client import parse_mblog

    r = parse_mblog(MBLOG_VIDEO)
    assert r.type == "video"
    assert "720p" in r.raw_data["_video_url"]


def test_parse_video_cover():
    from app.services.platforms.weibo.client import parse_mblog

    r = parse_mblog(MBLOG_VIDEO)
    assert r.cover.endswith("cover.jpg")


def test_parse_details():
    from app.services.platforms.weibo.client import parse_mblog_detail

    d = parse_mblog_detail(MBLOG_IMAGE)
    assert d is not None and len(d.images) == 2
    dv = parse_mblog_detail(MBLOG_VIDEO)
    assert dv is not None and dv.type == "video" and dv.duration == 135


@pytest.mark.parametrize("bad", [{}, {"text": "无 id"}, None, "字符串"])
def test_parse_tolerates_bad_input(bad):
    from app.services.platforms.weibo.client import parse_mblog, parse_mblog_detail

    assert parse_mblog(bad) is None
    assert parse_mblog_detail(bad) is None


def test_parse_text_only_no_crash():
    from app.services.platforms.weibo.client import parse_mblog

    r = parse_mblog({"id": "1", "text": "纯文字"})
    assert r is not None and r.raw_data["_images"] == []


# =============================================================================
# 「必须走浏览器」这个结论要被钉住
# =============================================================================

def test_client_search_uses_patchright():
    """**回归**：微博搜索必须走 patchright，不能改回 httpx。

    httpx 会拿 ok=-100（Service Worker 依赖），
    改回去会让搜索完全不可用。
    """
    from app.services.platforms.weibo.client import WeiboClient

    src = inspect.getsource(WeiboClient.search)
    assert "search_via_patchright" in src, "应转交 patchright 路径"
    # 不应在 search 里直接调 httpx 出口（`await self._call(...)`）
    assert "await self._call(" not in src, "不应直接走 httpx _call"


def test_wb_alias_registered():
    """**回归**：必须注册 `wb` 别名。

    前端「内容搜索」页的平台列表用的是 `wb`
    （`{ value: 'wb', label: '微博' }`），
    只注册 `weibo` 的话用户在界面选微博会报
    `ValueError: Unsupported platform: wb`。
    """
    from app.services.platforms import PlatformClientFactory, create_client

    assert "wb" in PlatformClientFactory._registry, "wb 别名未注册"
    assert "weibo" in PlatformClientFactory._registry, "weibo 未注册"
    # 两个名字都要能造出客户端
    for name in ("wb", "weibo"):
        client = create_client(name, mode="patchright")
        assert type(client).__name__ == "WeiboClient", name


def test_crawler_dispatches_weibo_to_browser():
    """`wb`/`weibo` 在 crawler 层要被分派到 patchright 模式。"""
    from app.services.crawler import service as crawler_service

    src = inspect.getsource(crawler_service.CrawlerService._search_via_platforms)
    assert "weibo" in src and "wb" in src, "分派表应含微博"
    assert "BROWSER_ONLY" in src or "patchright" in src


def test_patchright_module_exists_with_pool():
    from app.services.platforms.weibo import search_patchright as sp

    assert callable(sp.search_via_patchright)
    assert callable(sp.close_pool)
    # 复用 SessionPool（避免每次冷启动浏览器）
    assert sp._pool is not None


def test_patchright_waits_for_service_worker():
    """要等 SW 注册完成（太短会让搜索仍走无 SW 路径 → ok=-100）。

    ⚠️ 2026-10-04：原来断言 `inspect.getsource(sp._get_session)` 里有
    `wait_for_timeout` + `9000`。等待逻辑**没被删**，是被提取到
    `_warm_up()` 了（`_get_session` 只管建/借会话）。
    断言跟着搬了家 —— 这就是源码文本断言的固有毛病：
    行为没变，重构一下就红，红了容易被误当成"功能坏了"而去改产品代码。
    """
    from app.services.platforms.weibo import search_patchright as sp

    src = inspect.getsource(sp._warm_up)
    assert "wait_for_timeout" in src, "应有等待"
    # 实测需要 ~9s
    assert "9000" in src, "等待时间不应短于实测所需的 9s"
    # 确认 _get_session 确实会走 _warm_up（否则等待等于没接上）
    assert "_warm_up" in inspect.getsource(sp._get_session)


def test_later_page_login_failure_does_not_abort_search():
    """**回归**：被踢到登录页不能吞成空列表。

    ⚠️ 2026-10-07 改语义：现在**只取一页**（`page` 是页码，
    `max_results` 是这一页的上限）。所以"这一页要登录"是明确的失败信号，
    必须抛 `LoginExpiredError`（API 层映射 401），
    **不能** `return []` —— 那会把"要登录"伪装成"没内容"，
    正是用户搜『营口』得到 0 条的成因。
    """
    from app.services.platforms.weibo import search_patchright as sp

    src = inspect.getsource(sp._search_via_browser)
    idx = src.find("except DesktopLoginRequired")
    assert idx != -1, "要单独接住'被踢到登录页'"
    end = src.find("except Exception", idx)
    seg = src[idx:end if end != -1 else idx + 400]
    assert "LoginExpiredError" in seg, "要抛 LoginExpiredError → 401"
    assert "return []" not in seg, "不能吞成空列表"


def test_page_param_is_honoured():
    """⭐ `page` 是**页码**，`max_results` 是**这一页的上限** —— 两件事。

    ⚠️ 2026-10-07 修：原来把 `max_results` 当成"总共凑够多少条"，
       于是 `max_results=30, page=2` 会从第 2 页再往后连翻，
       "第 2 页"返回的其实是"第2~4页的混合"。用户实测：要 30 条只给 23 条，
       而且**不含**前 10 条。

    ⇒ 正确语义：取第 `page` 页，最多 `max_results` 条；要更多请翻页。
    """
    from app.services.platforms.weibo import search_patchright as sp

    http_src = inspect.getsource(sp._search_http)
    assert "pages_to_try = 1" in http_src, \
        "直连只取这一页（不能连翻几页凑 max_results）"
    assert "out[:want]" in http_src, "仍要按 max_results 截断"

    br_src = inspect.getsource(sp._search_via_browser)
    assert "for i in range(pages_to_try)" not in br_src, \
        "浏览器兜底也只取一页，不该有翻页循环"
    assert "params.keyword, page" in br_src, "要请求用户点的那一页"


def test_search_type_enum_value_extracted():
    """**回归**：`SearchParams.search_type` 是枚举，要取 `.value`。

    直接 str() 会得到 "SearchType.NOTE"，派生出错误的分类值。
    """
    from app.services.platforms.weibo import search_patchright as sp

    src = inspect.getsource(sp.search_via_patchright)
    assert "value" in src, "应从枚举取 .value（getattr 的第二个参数）"


def test_login_error_is_distinguishable():
    """`ok=-100` 要报成"未登录"，不能报成"没搜到"。"""
    from app.services.platforms.weibo.client import WeiboLoginRequiredError

    assert issubclass(WeiboLoginRequiredError, RuntimeError)
    src = inspect.getsource(WeiboLoginRequiredError)
    assert "未登录" in src or "登录" in src
