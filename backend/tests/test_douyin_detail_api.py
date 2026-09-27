"""抖音详情接口 + 图文图集的契约测试。

## 发现过程（2026-09-27）

旧的 iesdouyin 分享页方案**已失效**——抖音把数据改成前端异步加载：

    HTTP 200、_ROUTER_DATA 在，但 loaderData['video_(id)/page']
    只剩 ['ua','isSpider','webId','query','renderInSSR','lastPath']
    整页 HTML 里 videoInfoRes / aweme_detail / play_addr 出现次数**均为 0**

最终用 Playwright 的 page.on('request') 监听**全部**请求（含 worker）
才抓到真实端点：

    GET https://www-hj.douyin.com/aweme/v1/web/aweme/detail/

⚠️ **域名是 www-hj.douyin.com，不是 www.douyin.com** ——
这就是它长期没被发现的原因（自己拼 www 域名拿不到数据）。

## 实测结果

作品 7656457812507817841（图文笔记）：
    9 张原图，均可直接下载（291~462 KB image/webp）
    type=note  author=Rinchyan  赞17261 评47 转5046 藏2418
"""

from __future__ import annotations

import inspect

import pytest


# =============================================================================
# 端点常量
# =============================================================================

def test_detail_endpoint_constants():
    """详情端点必须记录 www-hj 这个域名。"""
    from app.services.platforms.douyin.apis import AWEME_DETAIL, DETAIL_BASE_URL

    assert DETAIL_BASE_URL == "https://www-hj.douyin.com"
    assert AWEME_DETAIL == "/aweme/v1/web/aweme/detail/"
    assert "www-hj" in DETAIL_BASE_URL, "域名是 www-hj，不是 www"


def test_endpoint_documents_discovery():
    """留下发现过程，避免后人重复排查。"""
    from app.services.platforms.douyin import apis

    src = inspect.getsource(apis)
    assert "page.on('request')" in src or "Playwright" in src, "应说明怎么找到的"
    assert "www-hj" in src
    assert "download_url_list" in src, "应记录原图字段"


# =============================================================================
# 解析（用实测结构）
# =============================================================================

def _aweme_detail(*, with_images: bool = True) -> dict:
    detail = {
        "aweme_id": "7656457812507817841",
        "desc": "回到千禧年",
        "create_time": 1782658001,
        "author": {"nickname": "Rinchyan", "uid": "999"},
        "statistics": {
            "digg_count": 17261, "comment_count": 47,
            "share_count": 5046, "collect_count": 2418,
        },
    }
    if with_images:
        detail["images"] = [
            {
                "url_list": ["https://x/thumb1.webp"],
                "download_url_list": ["https://x/orig1.webp"],
                "width": 2160, "height": 2880,
            },
            {
                "url_list": ["https://x/thumb2.webp"],
                "download_url_list": ["https://x/orig2.webp"],
                "width": 2160, "height": 2880,
            },
        ]
        # 实测坑：图文笔记的 play_addr 指向的是配乐 mp3
        detail["video"] = {
            "play_addr": {"url_list": [
                "https://lf9-music-east.douyinstatic.com/obj/ies-music-hj/1.mp3"
            ]},
            "cover": {"url_list": ["https://x/cover.webp"]},
        }
    else:
        detail["video"] = {
            "play_addr": {"url_list": ["https://v.douyin.com/nowm.mp4"]},
            "cover": {"url_list": ["https://x/cover.webp"]},
            "duration": 43000,
        }
    return detail


def test_detail_parses_images():
    """图集：应取到全部图片，且优先原图（download_url_list）。"""
    from app.services.platforms.douyin.client import _detail_from_aweme

    d = _detail_from_aweme(_aweme_detail(), "7656457812507817841")
    assert len(d.images) == 2
    assert d.images[0] == "https://x/orig1.webp", "应优先原图而不是压缩图"
    assert d.type == "note"
    assert d.likes == 17261
    assert d.author == "Rinchyan"


def test_image_post_has_no_video_url():
    """图文笔记不能把配乐当视频地址。

    实测：图文笔记的 video.play_addr 指向 ies-music-hj/xxx.mp3，
    当成视频会让前端误判成视频作品。
    """
    from app.services.platforms.douyin.client import _detail_from_aweme

    d = _detail_from_aweme(_aweme_detail(), "7656457812507817841")
    assert d.video == "", "图文笔记不应有 video_url"
    assert d.type == "note"


def test_video_post_keeps_video_url():
    """视频作品仍要正常取到视频地址。"""
    from app.services.platforms.douyin.client import _detail_from_aweme

    d = _detail_from_aweme(_aweme_detail(with_images=False), "1")
    assert d.video == "https://v.douyin.com/nowm.mp4"
    assert d.type == "video"
    assert d.duration == 43, "毫秒应换算成秒"


def test_looks_like_audio():
    """音频判定：图文笔记的 play_addr 是 mp3，要能识别出来。"""
    from app.services.platforms.douyin.client import _looks_like_audio

    assert _looks_like_audio(
        "https://lf9-music-east.douyinstatic.com/obj/ies-music-hj/1.mp3"
    )
    assert _looks_like_audio("https://x/a.m4a")
    assert not _looks_like_audio("https://v.douyin.com/nowm.mp4")


def test_detail_tolerates_missing_fields():
    """字段缺失不能崩。"""
    from app.services.platforms.douyin.client import _detail_from_aweme

    d = _detail_from_aweme({"aweme_id": "1"}, "1")
    assert d.id == "1"
    assert d.images == []
    assert d.video == ""
    assert d.likes == 0


# =============================================================================
# ID 提取（供「去水印解析」页使用）
# =============================================================================

@pytest.mark.parametrize(
    "url",
    [
        "https://www.douyin.com/video/7656457812507817841",
        "https://www.douyin.com/note/7656457812507817841",
        "https://www.douyin.com/jingxuan?modal_id=7656457812507817841",
        "https://www.iesdouyin.com/share/video/7656457812507817841/",
    ],
)
def test_extract_aweme_id(url):
    from app.services.platforms.douyin.detail_adapter import extract_aweme_id

    assert extract_aweme_id(url) == "7656457812507817841"


def test_extract_aweme_id_returns_none_for_short_link():
    """短链接需要先重定向，这里返回 None（由上层决定是否解析）。"""
    from app.services.platforms.douyin.detail_adapter import extract_aweme_id

    assert extract_aweme_id("https://v.douyin.com/abc") is None


# =============================================================================
# 接线
# =============================================================================

def test_parser_uses_new_adapter():
    """video/parser.py 的抖音分支必须用新适配器，不能再用失效的 iesdouyin。"""
    from app.services.video import parser as video_parser

    src = inspect.getsource(video_parser)
    assert "fetch_douyin_detail" in src, "应改用真实详情接口"
    assert "parse_douyin" not in src, "不应再调用失效的 iesdouyin 解析器"


def test_old_parser_documents_failure():
    """旧解析器要留下"为什么失效"的说明，避免后人重新启用。"""
    from app.services.video import parser_douyin

    doc = parser_douyin.__doc__ or ""
    assert "失效" in doc, "应标注已失效"
    assert "videoInfoRes" in doc or "异步加载" in doc, "应说明原因"


# =============================================================================
# 「去水印解析」响应必须带图集
# =============================================================================

def test_parse_response_has_image_fields():
    """ParseResponse 必须有 images/content_type。

    踩过：响应模型缺这两个字段，抖音图文解析出 9 张原图，
    到前端却只剩一张封面（字段被 Pydantic 丢弃）。
    """
    from app.api.v1.download import ParseResponse

    fields = ParseResponse.model_fields
    assert "images" in fields, "应有 images"
    assert "content_type" in fields, "应有 content_type"
    assert "image_count" in fields, "应有 image_count"


def test_parse_endpoint_returns_images():
    """端点构造响应时必须填 images，且图文不填 video_url。

    图文笔记没有视频——把页面 URL 塞进 video_url 会让前端误判成视频。
    """
    import inspect

    from app.api.v1 import download as dl

    src = inspect.getsource(dl.parse_download_url)
    assert "images=parse_images" in src, "应传 images"
    assert "content_type=content_type" in src, "应传 content_type"
    assert "not parse_images" in src, "图文时应跳过 yt-dlp 清晰度枚举"


def test_parse_response_defaults_are_video():
    """默认仍是视频，避免影响既有平台。"""
    from app.api.v1.download import ParseResponse

    r = ParseResponse(success=True)
    assert r.content_type == "video"
    assert r.images == []
    assert r.image_count == 0
