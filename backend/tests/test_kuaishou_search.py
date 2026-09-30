"""快手搜索的回归测试（2026-09-30，用 skill 加的第二个平台）。

## 背景：这次是**照着 `ylcraft-add-platform` skill 做的**

用户："做成一个skill，然后添加快手试试这个skill"

过程里 skill 抓出了好几个问题（见 `test_platform_not_implemented.py`），
本文件覆盖**搜索实现本身**。

## 接口（**全部实测抓包**，不是猜的）

用已登录的持久化 profile 打开搜索页，拦截真实请求：

    POST /rest/v/search/feed?__NS_hxfalcon=<签名>
    Headers: content-type: application/json
             kww: <与 cookie 的 kwfv1 完全相同>
             referer: https://www.kuaishou.com/search/video?searchKey=<编码关键词>
    Body:   {"keyword":"美食","page":"search","webPageArea":"","pcursor":""}
    → {"result":1,"pcursor":"1",
       "feeds":[{type,tags,author,photo:{id,caption,duration,coverUrl,
                                         viewCount,likeCount,photoUrls}}]}

## ⚠️ 签名 `__NS_hxfalcon` 是必需的（实测）

    无签名 / 只带 kww  → {"result":50,"error_msg":"**签名验证失败**"}

**纯 HTTP 拿不到它** —— 快手签名库是混淆 JS
（`kws-10-0.0.1-obfuscated.*.js`），`window` 上也没有可调函数
（和小红书的 `_webmsxyw` 一样被打包进闭包）。

## ✅ 但发现一条可行路径：**签名可复用**

    ① 浏览器打开一次搜索页 → 页面自己发请求 → 拦截到带签名的 URL
    ② 在**同一页面上下文**里复用该 URL + 换关键词 → **成功**

实测：

    旅行 19 条 / 宠物 19 条 / 健身 20 条
    翻页 pcursor="" → "1" → "2"   各 19~20 条

**签名与关键词无关**（会话级），抓一次能用很久。

## 实测结果（客户端直连）

    '在海口吃石山乳羊…'      作者=达哥在上海    赞145923 播放10252085 时长344s 视频✓
    '30元吃个南京夜市地摊炸串…' 作者=刘金良正能量  赞75010 播放1252289 时长297s 视频✓
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest


# =============================================================================
# 接口常量（实测字段，不能瞎改）
# =============================================================================

def test_endpoints_match_capture():
    """**回归**：接口路径要与抓包一致。"""
    from app.services.platforms.kuaishou import apis

    assert apis.SEARCH_FEED == "/rest/v/search/feed"
    assert apis.SEARCH_USER == "/rest/v/search/user"
    assert apis.BASE == "https://www.kuaishou.com"


def test_feed_body_matches_capture():
    """**回归**：请求体字段要与抓包一致。

    实测：`{"keyword":..,"page":"search","webPageArea":"","pcursor":""}`
    —— `page` 是**固定字符串 "search"**（不是页码！）
    """
    from app.services.platforms.kuaishou.apis import build_feed_body

    b = build_feed_body("美食")
    assert b["keyword"] == "美食"
    assert b["page"] == "search", "page 是固定值 'search'，不是页码"
    assert b["webPageArea"] == ""
    assert b["pcursor"] == ""


def test_user_body_matches_capture():
    """搜用户的请求体（实测）。"""
    from app.services.platforms.kuaishou.apis import build_user_body

    b = build_user_body("美食")
    assert b["keyword"] == "美食"
    assert b["pcursor"] == ""
    assert "searchSessionId" in b


def test_search_page_url_encodes_keyword():
    """搜索页 URL 要编码关键词（签名就从这个页面的请求里抓）。"""
    from app.services.platforms.kuaishou.apis import search_page_url

    u = search_page_url("美食")
    assert "/search/video" in u
    assert "searchKey=" in u
    assert "%E7%BE%8E%E9%A3%9F" in u, "中文要 URL 编码"


# =============================================================================
# 解析（字段实测）
# =============================================================================

def test_parse_feed_real_shape():
    """**回归**：解析实测形状的 feed。

    关键字段：`photo.id` / `photo.caption` / `photo.duration`（**毫秒**）/
    `photo.coverUrl` / `photo.viewCount` / `photo.likeCount` /
    `photo.photoUrls[0].url`（视频直链）。
    """
    from app.services.platforms.kuaishou.apis import parse_feed

    feed = {
        "type": 1,
        "tags": [{"name": "蜜汁排骨", "type": 1}],
        "author": {"id": "123", "name": "某作者"},
        "photo": {
            "id": "3xbfmxwduhwpm79",
            "caption": "在广东珠海斗门镇吃烧排骨",
            "duration": 286566,          # 毫秒
            "coverUrl": "https://p5.a.yximgs.com/x.jpg",
            "viewCount": 7485492,
            "likeCount": 134024,
            "photoUrls": [{"url": "https://x.mp4"}],
        },
    }
    p = parse_feed(feed)
    assert p is not None
    assert p["id"] == "3xbfmxwduhwpm79"
    assert p["title"].startswith("在广东珠海")
    assert p["author"] == "某作者"
    assert p["cover"] == "https://p5.a.yximgs.com/x.jpg"
    assert p["video_url"] == "https://x.mp4", "视频直链在 photoUrls[0].url"
    assert p["duration"] == 286, "**时长是毫秒**，要转秒"
    assert p["views"] == 7485492
    assert p["likes"] == 134024
    assert p["type"] == "video", "feed.type=1 是视频"
    assert p["tags"] == ["蜜汁排骨"]


def test_parse_feed_skips_invalid():
    """没有 `photo.id` 的条目跳过（不产出空壳）。"""
    from app.services.platforms.kuaishou.apis import parse_feed

    assert parse_feed({}) is None
    assert parse_feed({"type": 1}) is None
    assert parse_feed({"photo": {}}) is None, "没有 id 要跳过"
    assert parse_feed("not-a-dict") is None


def test_parse_feed_handles_string_numbers():
    """**回归**：快手的数值可能是**字符串**（和抖音一样）。"""
    from app.services.platforms.kuaishou.apis import parse_feed

    p = parse_feed({
        "type": 1,
        "photo": {"id": "x", "caption": "c", "duration": "286566",
                  "viewCount": "7485492", "likeCount": "134024"},
    })
    assert p["duration"] == 286
    assert p["views"] == 7485492


def test_parse_feed_no_video_url_when_absent():
    """**回归**：没有视频地址就**留空**，不要兜底。

    （这是本仓库踩过两次的坑：`video_url` 拿"原文链接"兜底
    会让图集被判成视频。）
    """
    from app.services.platforms.kuaishou.apis import parse_feed

    p = parse_feed({"type": 1, "photo": {"id": "x", "caption": "c"}})
    assert p["video_url"] == "", "没有直链要留空"
    assert p["url"] != p["video_url"], "页面地址与媒体直链要分开"


def test_parse_user_real_shape():
    """`users[]` 的解析（实测字段 `user_name` / `headurl` / `fan`）。"""
    from app.services.platforms.kuaishou.apis import parse_user

    u = parse_user({
        "id": "456", "user_name": "快手美食",
        "headurl": "https://x.jpg", "fan": 12345,
        "user_text": "平台美食账号", "verified": True,
    })
    assert u["id"] == "456"
    assert u["name"] == "快手美食"
    assert u["followers"] == 12345
    assert u["verified"] is True


# =============================================================================
# 客户端
# =============================================================================

def test_client_registered():
    """**回归**：客户端要注册（含别名 ks）。"""
    from app.services.platforms import supported_platforms

    got = supported_platforms()
    assert "kuaishou" in got
    assert "ks" in got


def test_client_uses_browser_for_signature():
    """**回归（核心设计）**：签名要**从浏览器抓**，纯 HTTP 做不到。

    实测：无签名 → `{"result":50,"error_msg":"签名验证失败"}`。
    """
    from app.services.platforms.kuaishou import client as ks

    src = inspect.getsource(ks.KuaishouClient)
    assert "__NS_hxfalcon" in src, "要识别带签名的 URL"
    assert "page.on(\"request\"" in src, "要拦截页面请求拿签名"
    assert "signature" not in src.lower() or "签名" in src, "要说明签名机制"


def test_signature_is_cached():
    """**回归**：签名要缓存（与关键词无关，抓一次能用很久）。"""
    from app.services.platforms.kuaishou import client as ks

    assert hasattr(ks, "_signed_urls"), "要有签名缓存"
    src = inspect.getsource(ks.KuaishouClient._ensure_signed_url)
    # 缓存 key 是 `{conn}:{uri}`（**签名绑路径**，不能按 conn 存一个）
    assert "_signed_urls.get(cache_key)" in src, "要先查缓存"
    assert "asyncio.Lock" in inspect.getsource(ks._lock_for), "并发要加锁"


def test_session_key_matches_base_format():
    """**回归**：会话 key 用**竖线**（与 `base._init_patchright` 一致）。

    微博那边踩过：key 格式不一致 → 两条路各建各的上下文 → 打架。
    """
    from app.services.platforms.kuaishou import client as ks

    assert "|" in ks._POOL_KEY_FMT
    assert ":" not in ks._POOL_KEY_FMT


def test_session_is_headless():
    """**回归**：搜索会话要**无头**（不弹窗）。

    用户反馈过"为啥个人中心的微博老是打开浏览器了" ——
    搜索这类后台操作不该弹窗。
    """
    from app.services.platforms.kuaishou import client as ks

    src = inspect.getsource(ks.KuaishouClient._get_session)
    assert "headless=True" in src


def test_sets_has_more():
    """**回归**：搜索结果要带 `_has_more`（前端靠它显示「下一页」）。"""
    from app.services.platforms.kuaishou import client as ks

    src = inspect.getsource(ks.KuaishouClient.search)
    assert "_has_more" in src


def test_pagination_uses_pcursor():
    """翻页用 **pcursor 游标**（不是页码）。"""
    from app.services.platforms.kuaishou import client as ks

    src = inspect.getsource(ks.KuaishouClient.search)
    assert "pcursor" in src


def test_missing_signature_gives_actionable_error():
    """**回归**：抓不到签名时要给**可操作**错误，不能静默返回空。"""
    from app.services.platforms.kuaishou import client as ks

    src = inspect.getsource(ks.KuaishouClient._post)
    assert "RuntimeError" in src
    assert "账号中心" in src, "要告诉用户去哪儿检查登录态"


def test_has_more_true_on_first_page():
    """**回归**：第 1 页拿满时要 `has_more=True`。

    实测 bug：原来把读游标写在 `break` **之后** ——
    "本页拿满 want" 直接 break 时游标没记，于是：

        page=1  10条  has_more=**False**   ← 其实还有更多！
        page=2  10条  has_more=True

    **用户看到第 1 页没有「下一页」按钮。**

    修法：**先记游标，再决定要不要继续**。
    """
    from app.services.platforms.kuaishou import client as ks

    src = inspect.getsource(ks.KuaishouClient.search)
    i_next = src.find("next_cursor = str(payload.get")
    i_full = src.find("if len(out) >= want:")
    assert i_next != -1 and i_full != -1
    assert i_next < i_full, "要先读游标，再判断是否拿满（否则 has_more 恒为 False）"


def test_pagination_sequentially_walks_cursor():
    """翻页是**游标顺序推进**（没有页码参数），要说明这个代价。

    实测：page=5 需要请求 5 次 → 5.1 秒。
    """
    from app.services.platforms.kuaishou import client as ks

    src = inspect.getsource(ks.KuaishouClient.search)
    assert "page_no" in src, "要把页码换算成翻页次数"


def test_session_injects_cookies():
    """**回归（关键）**：新建会话时**必须注入 cookie**。

    ## 实测踩的坑（我一度误判成"限流"）

    原来 `_get_session` 只靠持久化 profile、不注入 cookie，
    而那个 profile 里**没有登录态**（`userId=None`）。后果：

        · 搜索页不发**带签名的请求**（未登录时不发）→ "抓不到签名"
        · `result:2`（需登录的接口拒绝）

    **我把它误判成"快手限流了，等恢复"** —— 直到手动注入 cookie 后
    立刻抓到 3 个带签名的请求、搜索恢复正常。

    ## 与微博那次是**同一个坑**

    `base._init_patchright` 会注入 cookie，平台自己的 `_get_session`
    不注入 → **两条路行为不一致**。快手这次又踩了一遍。

    ## 判据补充

    即使 cookie **在**，也可能**过期** —— 实测注入登录态的 cookie 后：
        · `document.cookie` 有 `userId` / `webday7_st` ✅
        · 但页面 UI 仍显示"登录即可享受"（JS 不认）
        · `profile/get` 返回 `result:2`
    → 所以"cookie 存在" ≠ "登录态有效"，**过期要重新登录**。
    """
    from app.services.platforms.kuaishou import client as ks

    src = inspect.getsource(ks.KuaishouClient._get_session)
    assert "_inject_cookies" in src, (
        "新建会话要注入 cookie（否则未登录 → 拿不到签名 → 误判成限流）"
    )
    inj = inspect.getsource(ks.KuaishouClient._inject_cookies)
    assert "add_cookies" in inj
    assert ".kuaishou.com" in inj
    assert "userId" in inj, "要能报告登录 cookie 是否存在"


def test_detector_does_not_use_signed_api():
    """**回归**：检测器**不能**用需要签名的接口做判据。

    ## 我踩的第三次坑

    为了修"访客也有 webday7_st"的假阳性，我改用
    `/rest/v/profile/get` 做确认 —— **但它在签名白名单里**
    （调研报告 `SIG4_WHITELIST`），检测器拿不到签名，于是返回：

        {"result":50,"error_msg":"签名验证失败"}

    **`50` 是签名失败，不是未登录**（未登录是 `2`）。我把它当成
    "未登录" → 用户明明登录了（左下角有头像），检测器却报未登录。

    ## 正确判据（实测）

        未登录 → 页面出现「登录即可享受…立即登录」
        已登录 → 该文案消失

    `LOGIN_HINT_TEXTS` 就是这两个文案。
    """
    from app.services.cookies.platforms import kuaishou

    assert "登录即可享受" in kuaishou.LOGIN_HINT_TEXTS
    assert hasattr(kuaishou, "UNUSABLE_SIGNED_API"), "要留档不可用的接口"
    src = inspect.getsource(kuaishou.KuaishouDetector.detect)
    assert "LOGIN_HINT_TEXTS" in src
    assert "PROFILE_API" not in src, "不该用需要签名的接口"

    # 账号信息也不该读 DOM（那是**别人的**昵称）
    ext = inspect.getsource(kuaishou.KuaishouDetector.extract_account_info)
    assert "query_selector" not in ext


def test_self_profile_parses_flat_fields():
    """**回归**：`/rest/v/profile/get` 的字段是**扁平的**，不是 `data.user`。

    ## 实测响应（登录态有效时）

        {"result":1, "userName":"逸流AI", "userId":5372574395,
         "userHead":"https://…jpg", "fans":20, "follows":2,
         "like":312, "sex":"M", "mobile":"131****1644"}

    **我第一版按 `data.user` 嵌套解析 → 拿到空**（字段名也对不上，
    比如关注数是 `follows` 而不是 `following`）。
    """
    from app.services.platforms.kuaishou import client as ks

    src = inspect.getsource(ks.KuaishouClient.get_self_profile)
    # 直接读顶层
    assert 'payload.get("userName")' in src
    assert 'payload.get("userId")' in src
    # 不该走嵌套
    assert 'data.get("user")' not in src, "字段在顶层，不该按 data.user 解析"
    # 快手的关注数叫 follows
    assert 'payload.get("follows")' in src


def test_route_supports_kuaishou():
    """**回归**：`/users/*` 路由要支持快手（含别名 ks）。

    漏了这一层 → 「我的数据」页面报"平台不支持"。
    （skill 第 6 步：路由的 SUPPORTED 是必改项。）
    """
    from app.api.v1.users import SUPPORTED

    assert "kuaishou" in SUPPORTED
    assert "ks" in SUPPORTED
    assert SUPPORTED["kuaishou"]["conn_platform"] == "KUAISHOU"


def test_frontend_dropdowns_have_kuaishou():
    """**回归**：前端下拉都要有快手（我**第二次**犯同一个错）。

    用户截图：「我的数据」下拉里没有快手 —— 而**后端已经打通了**
    （20:46 实测拿到「逸流AI 粉丝20」）。

    ⚠️ 这和 **X 那次一模一样**（后端可用、前端漏加）。
    skill 第 7 步专门写了"至少两处下拉"，我还是漏了一次。

    所以这条测试**把两个下拉都钉住**。
    """
    from pathlib import Path

    fe = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages"
    for rel in ("my-platform-data/index.tsx", "platform-users/index.tsx"):
        p = fe / rel
        if not p.exists():
            pytest.skip(f"{rel} 不在预期位置")
        src = p.read_text(encoding="utf-8", errors="ignore")
        assert "value: 'kuaishou'" in src, f"{rel} 的下拉缺快手（用户选不到）"


def test_script_checks_both_frontend_dropdowns():
    """**回归**：校验脚本要查**两个**前端下拉，不只「我的数据」。

    我第一版只查了 `my-platform-data` —— 于是「博主中心」漏快手时
    校验仍然全绿（假阴性）。
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts import check_platform_registry as cpr

    src = inspect.getsource(cpr.check_capability_layers)
    assert "my-platform-data" in src
    assert "platform-users" in src, "也要查博主中心下拉"
    assert hasattr(cpr, "_USER_SEARCH_PLATFORMS")


def test_login_expiry_error_is_actionable():
    """**回归**：快手登录态失效时要给**可操作**错误。

    ## 实测：快手登录态很短命

        20:46  扫码成功 → profile/get result=1（拿到「逸流AI 粉丝20」）
        21:0x  → result=**109**
        21:0x  → result=**2**（未登录）

    **约 20 分钟就失效**。而**搜索不需要登录**（公开数据）——
    所以"搜索能用"会让用户误以为登录态还好。

    而原来 `profile/*` 失败只 `logger.warning` + `return None`，
    用户看到**空白**，不知道该重新登录。
    """
    from app.services.platforms.kuaishou import client as ks

    src = inspect.getsource(ks.KuaishouClient._post)
    assert "RuntimeError" in src, "profile 类接口失败要抛可操作错误"
    assert "账号中心" in src, "要告诉用户去哪儿重新登录"
    assert "搜索不需要登录" in src, "要点明'搜索能用≠登录有效'"
    assert "109" in src, "要留档中间态错误码"


def test_expiry_codes_documented():
    """要记录错误码迁移（1 → 109 → 2）与短命事实。"""
    from app.services.platforms.kuaishou import client as ks

    doc = inspect.getsource(ks)
    assert "20 分钟" in doc, "要记录实测的失效时长"
    assert "109" in doc
