"""用户搜索 / 资料 / 作品列表 的契约测试（抖音 + 小红书）。

## 实测打通记录（2026-09-27）

    抖音：搜索「李子柒」→ 5657万粉；资料 → 4830万粉/获赞2.55亿/作品774
          作品列表 → 5 条（赞1168万/703万/1251万）
    小红书：搜索「美食」→ 吕小厨爱美食 140.9万粉
            资料 → 逸流AI 粉丝195/关注2/获赞2930/作品73
            作品列表 → 20 条 + has_more + cursor

## 实现过程中踩的坑（都要钉住）

1. **抖音用户搜索不在 general/search/single**。给它加
   `search_channel=aweme_user` 完全不生效（返回和综合一样）。
   用户搜索在 `discover/search`。

2. **抖音主页必须用 sec_uid**，数字 uid 打开是空页面。

3. **`parse_search_item` 要兼容两种结构**：
   · 搜索接口：`data[].aweme_info.{...}`（有包装）
   · 作品列表：`aweme_list[].{...}`（**裸 aweme 对象**）
   早先只认第一种 → `get_user_videos` 拿到 5 条数据却解析成 0 条，
   表现为"这个 UP 主没有作品"。

4. **抖音 UA 版本必须够新**：实测 Chrome/120 → **返回空 body（HTTP 200）**，
   Chrome/154 → 正常。这个坑最隐蔽：报错是 `Expecting value: line 1 column 1`，
   看起来像接口坏了。现在空 body 会显式报成"被拒绝"。

5. **小红书必须签名**（抖音不用）。`xhshow` 纯 Python 可用。
   浏览器内签名**不可行**（`window._webmsxyw` 是 undefined，被打包进闭包了）。

6. **小红书字段位置**：粉丝数**不在** `basic_info` 里 ——
   在 `data.interactions[]` 里按 `type="fans"/"follows"/"interaction"` 找，
   且 count 是**字符串**（可能是 "140.9万"）。

7. **两平台作品列表方法名不同**：抖音 `get_user_videos`、
   小红书历史命名 `get_user_notes`。统一路由调 `get_user_videos`，
   所以小红书加了别名，否则运行时 AttributeError。

## 一个方法论教训

我一开始用「响应体含 nickname + follower_count」过滤响应来找接口，
**没命中**就错误地推断"小红书做不了用户搜索/资料"。
实际两个接口都存在，只是字段名不同。

✅ 正确做法：**按 URL 路径过滤，不要按响应体字段猜。**
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# 端点常量
# =============================================================================

def test_douyin_user_endpoints():
    from app.services.platforms.douyin.apis import (
        DISCOVER_SEARCH,
        PROFILE_OTHER,
        USER_POST,
        USER_SEARCH_CHANNEL,
    )

    assert DISCOVER_SEARCH == "/aweme/v1/web/discover/search/"
    assert PROFILE_OTHER == "/aweme/v1/web/user/profile/other/"
    assert USER_POST == "/aweme/v1/web/aweme/post/"
    # 社区一致取值
    assert USER_SEARCH_CHANNEL == "aweme_user_web"


def test_douyin_user_search_documents_channel_binding():
    """要记录"channel 与路径一一绑定"这个坑，避免后人再传到 general/search。"""
    from app.services.platforms.douyin import apis

    src = inspect.getsource(apis)
    assert "aweme_general" in src
    assert "不生效" in src or "无效" in src, "应说明传给 general/search 无效"


def test_xhs_user_endpoints():
    from app.services.platforms.xiaohongshu.apis_user import (
        USER_OTHERINFO,
        USER_POSTED,
        USER_SEARCH,
    )

    assert USER_SEARCH == "/api/sns/web/v1/search/usersearch"
    assert USER_OTHERINFO == "/api/sns/web/v1/user/otherinfo"
    assert USER_POSTED == "/api/sns/web/v1/user_posted"


def test_xhs_search_is_post_not_get():
    """小红书用户搜索是 **POST + JSON body**（不像抖音是 GET query）。"""
    from app.services.platforms.xiaohongshu import user as xhs_user

    src = inspect.getsource(xhs_user.search_users)
    assert "_post_json" in src, "应用 POST"
    assert "search_id" in src, "必须带 search_id"


# =============================================================================
# 解析（用实测结构）
# =============================================================================

def test_douyin_parse_user_info():
    """解析实测字段：uid/nickname/follower_count/total_favorited/aweme_count。"""
    from app.services.platforms.douyin.client import parse_user_info

    p = parse_user_info({
        "uid": "68310389333",
        "sec_uid": "MS4wLjABAAAAPCnT",
        "nickname": "李子柒",
        "signature": "李家有女",
        "follower_count": 48307767,
        "following_count": 1,
        "total_favorited": 255322280,
        "aweme_count": 774,
        "custom_verify": "传统文化创作者",
        "avatar_thumb": {"url_list": ["https://x/a.jpeg"]},
    })
    assert p.id == "68310389333"
    assert p.name == "李子柒"
    assert p.followers == 48307767
    assert p.total_likes == 255322280
    assert p.total_videos == 774
    assert p.verified is True
    assert p.avatar == "https://x/a.jpeg"
    # sec_uid 必须带出来（查作品列表要用）
    assert p.raw_data["sec_uid"] == "MS4wLjABAAAAPCnT"


def test_douyin_parse_item_accepts_bare_aweme():
    """**回归**：作品列表返回的是裸 aweme 对象（没有 aweme_info 包装）。

    只认 aweme_info 会让 get_user_videos 把 5 条数据解析成 0 条。
    """
    from app.services.platforms.douyin.client import parse_search_item

    bare = {
        "aweme_id": "7436613508646702348",
        "desc": "送给所有知道我名字的人",
        "create_time": 1700000000,
        "author": {"nickname": "李子柒", "uid": "68310389333"},
        "statistics": {"digg_count": 11688478},
        "video": {"duration": 1000, "cover": {"url_list": ["http://x/c.jpg"]}},
    }
    r = parse_search_item(bare)
    assert r is not None, "裸 aweme 对象也要能解析"
    assert r.id == "7436613508646702348"
    assert r.likes == 11688478


def test_douyin_parse_item_still_supports_wrapped():
    """搜索接口的 aweme_info 包装仍要支持（回归）。"""
    from app.services.platforms.douyin.client import parse_search_item

    wrapped = {
        "type": 1,
        "aweme_info": {
            "aweme_id": "123",
            "desc": "x",
            "author": {"nickname": "a", "uid": "1"},
            "statistics": {"digg_count": 1},
            "video": {"duration": 1, "cover": {"url_list": ["http://x"]}},
        },
    }
    r = parse_search_item(wrapped)
    assert r is not None and r.id == "123"


def test_xhs_parse_count_handles_suffixes():
    """小红书计数是字符串，可能带 "万"/"K" 后缀。"""
    from app.services.platforms.xiaohongshu.user import parse_count

    assert parse_count("195") == 195
    assert parse_count("2930") == 2930
    assert parse_count("140.9万") == 1409000
    assert parse_count("2.9K") == 2900
    assert parse_count(195) == 195
    assert parse_count("") == 0


def test_xhs_parse_user_otherinfo_reads_interactions():
    """**回归**：粉丝数在 `interactions` 里，不在 `basic_info`。

    实测 basic_info 只有 {nickname, red_id, desc, images, imageb,
    gender, ip_location} —— 没有粉丝数。
    """
    from app.services.platforms.xiaohongshu.user import parse_user_otherinfo

    body = {
        "basic_info": {
            "nickname": "逸流AI", "red_id": "95645311698",
            "desc": "分享ai知识", "ip_location": "辽宁",
            "imageb": "https://x/avatar.webp",
        },
        "interactions": [
            {"type": "follows", "count": "2"},
            {"type": "fans", "count": "195"},
            {"type": "interaction", "count": "2930"},
        ],
        "posted": 73,
    }
    p = parse_user_otherinfo(body, "678bc288000000000e01f6f5")
    assert p.name == "逸流AI"
    assert p.followers == 195
    assert p.following == 2
    assert p.total_likes == 2930
    assert p.total_videos == 73
    assert p.raw_data["red_id"] == "95645311698"


def test_xhs_parse_search_user():
    from app.services.platforms.xiaohongshu.user import parse_search_user

    p = parse_search_user({
        "id": "5caf29f90000000017017c17",
        "name": "吕小厨爱美食",
        "fans": "140.9万",
        "image": "https://x/a.webp",
        "red_official_verified": True,
    })
    assert p.id == "5caf29f90000000017017c17"
    assert p.name == "吕小厨爱美食"
    assert p.followers == 1409000
    assert p.verified is True


# =============================================================================
# 签名
# =============================================================================

def test_xhs_signing_module_exists():
    from app.services.platforms.xiaohongshu import signing

    assert hasattr(signing, "sign_get")
    assert hasattr(signing, "sign_post")
    assert hasattr(signing, "get_search_id")
    assert hasattr(signing, "SigningUnavailableError")


def test_xhs_signing_requires_a1():
    """缺 a1 时给可读原因（否则只会看到签名失败，不知道是 a1 的问题）。"""
    from app.services.platforms.xiaohongshu.signing import (
        SigningUnavailableError,
        sign_get,
    )

    with pytest.raises(SigningUnavailableError) as exc:
        sign_get("/api/x", "web_session=abc")
    assert "a1" in str(exc.value)


def test_xhs_signing_does_not_silently_degrade():
    """签名失败要抛错，不能退化成"没有数据"。"""
    from app.services.platforms.xiaohongshu.signing import SigningUnavailableError

    assert issubclass(SigningUnavailableError, RuntimeError)


def test_xhs_signature_check_distinguishes_error():
    """签名失效的错误信息要可识别（不说成"没数据"）。"""
    from app.services.platforms.xiaohongshu.user import _check_code

    with pytest.raises(RuntimeError) as exc:
        _check_code({"code": -1, "msg": "create invalid signature"}, "测试")
    msg = str(exc.value)
    assert "签名" in msg
    assert "a1" in msg, "应提示检查 a1"


def test_xhs_check_code_accepts_both_success_codes():
    """小红书成功码有 0 和 1000 两种（实测：搜索返回 1000）。"""
    from app.services.platforms.xiaohongshu.user import _check_code

    _check_code({"code": 0}, "x")
    _check_code({"code": 1000}, "x")


# =============================================================================
# UA / 空 body（最隐蔽的坑）
# =============================================================================

def test_douyin_ua_is_recent():
    """**回归**：UA 版本必须够新。

    实测 Chrome/120 → aweme/post 返回**空 body**（HTTP 200）；
    Chrome/154 → 正常。旧 UA 会让作品列表静默失败。
    """
    from app.services.platforms.douyin.client import DouyinClient
    from app.services.platforms.types import ClientConfig, ClientMode

    c = DouyinClient(ClientConfig(platform="douyin", mode=ClientMode.API))
    ua = c._get_default_user_agent()
    assert "Chrome/" in ua
    ver = int(ua.split("Chrome/")[1].split(".")[0])
    assert ver >= 130, f"UA 版本过低（Chrome/{ver}）会被抖音拒绝"


def test_douyin_empty_body_raises_readable_error():
    """空 body 要显式报成"被拒绝"，而不是 JSON 解析错误。"""
    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient._call)
    assert "空响应体" in src, "应识别空 body"
    assert "User-Agent" in src, "应提示 UA 版本这个常见原因"


def test_douyin_403_raises_platform_unavailable():
    """403 要报成风控拦截，不是"没有数据"。"""
    from app.services.platforms.douyin.client import DouyinClient

    src = inspect.getsource(DouyinClient._call)
    assert "PlatformUnavailableError" in src
    assert "ArgusSecurityPlugin" in src or "风控" in src


# =============================================================================
# 方法名一致性
# =============================================================================

def test_both_clients_have_get_user_videos():
    """**回归**：统一路由调的是 `get_user_videos`。

    小红书历史命名是 `get_user_notes`，没有别名会运行时 AttributeError
    （实测踩过）。
    """
    from app.services.platforms.douyin.client import DouyinClient
    from app.services.platforms.xiaohongshu.client import XiaohongshuClient

    assert hasattr(DouyinClient, "get_user_videos")
    assert hasattr(XiaohongshuClient, "get_user_videos")
    assert hasattr(XiaohongshuClient, "get_user_notes")


def test_both_clients_have_user_methods():
    from app.services.platforms.douyin.client import DouyinClient
    from app.services.platforms.xiaohongshu.client import XiaohongshuClient

    for cls in (DouyinClient, XiaohongshuClient):
        assert hasattr(cls, "search_users"), f"{cls.__name__} 缺 search_users"
        assert hasattr(cls, "get_user_profile"), f"{cls.__name__} 缺 get_user_profile"


# =============================================================================
# HTTP 路由
# =============================================================================

def test_users_router_mounted():
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    for p in ("/api/v1/users/search", "/api/v1/users/profile", "/api/v1/users/videos"):
        assert p in paths, f"{p} 未挂载"


def test_users_router_supports_both_platforms():
    from app.api.v1 import users as users_api

    assert "douyin" in users_api.SUPPORTED
    assert "xiaohongshu" in users_api.SUPPORTED
    assert "xhs" in users_api.SUPPORTED, "应容忍前端传 xhs 别名"


def test_users_router_requires_sec_uid_for_douyin():
    """抖音必须用 sec_uid（数字 uid 打开是空页面），路由应说明这点。"""
    from app.api.v1 import users as users_api

    src = inspect.getsource(users_api.get_user_profile)
    assert "sec_uid" in src
    assert "抖音必须" in src or "必须传" in src
