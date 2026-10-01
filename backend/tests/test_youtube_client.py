"""YouTube 平台客户端回归测试（2026-10-01，VPN 打通后实现）。

## 背景

用户开 VPN 之前，本机到 YouTube **完全不通**（DNS 被污染到
Facebook 的 IP、无可用代理），当时保持"未实现 + 显式 501"。
VPN 通了之后用 yt-dlp 实现了采集客户端。

## 实测记录（2026-10-01）

    ytsearch5:python tutorial                → 5 条（相关度，首条 Mosh）
    .../results?...&sp=EgIIAQ%3D%3D          → 54 条（最新，首条 92 秒新视频）
    .../results?...&sp=CAMSAhAB              → 479 条（播放量，首条 4937 万）
    .../results?...&sp=EgIQAg%3D%3D          → 频道（UC... 24 位）
    https://www.youtube.com/@freecodecamp/videos → 1724 条

**三档排序首条互不相同** → 排序真实生效（不是假选项）。
"""

from __future__ import annotations

import inspect


def test_youtube_is_registered():
    """YouTube 必须真的注册进平台注册表。

    这条同时是"假支持"的守门人：`supported_platforms()` 里没有
    youtube 时，搜索会报 501（而不是假装"搜到 0 条"）。
    """
    from app.services.platforms import supported_platforms

    assert "youtube" in supported_platforms(), (
        "youtube 未注册 —— 会退化成 501/假支持"
    )


def test_youtube_in_auto_discover_list():
    """**回归**：漏了自动发现列表，客户端根本不会加载。

    这是 skill 里点名的坑：写了 `platforms/<平台>/` 但没加进
    `_auto_discover_platforms()` 的 `platform_modules`。
    """
    from app.services.platforms import __file__ as init_file

    src = open(init_file, encoding="utf-8").read()
    assert '"youtube"' in src, "youtube 要加进 platform_modules"


def test_search_does_not_use_unsupported_ytsearchdate():
    """**回归**：不要用 `ytsearchdateN:` —— 本版本 yt-dlp 不支持。

    实测报错：`Unsupported url scheme: "ytsearchdate3"`。
    "最新"排序必须走 `sp=EgIIAQ==` 的完整搜索 URL。

    ⚠️ 只查**可执行代码**（去掉注释）—— `apis.py` 的注释里
    特意写了 "ytsearchdateN: 不支持" 来留档，那是说明不是用法。
    """
    import re

    from app.services.platforms.youtube import apis

    # 去掉注释，只看真正会执行的字符串
    src = inspect.getsource(apis)
    code_only = re.sub(r"#[^\n]*", "", src)
    assert "ytsearchdate" not in code_only, (
        "ytsearchdate 语法不被支持，会直接报错（只能在注释里留档）"
    )
    assert "EgIIAQ" in code_only, "最新排序要用 sp 参数"


def test_playlist_entries_are_filtered_out():
    """**回归**：搜索结果里混入的**播放列表**要过滤掉。

    实测：flat entries 里会混进 `PL...` 开头的播放列表卡片
    （id 几十位、duration=None）。它们不是视频，点详情会
    404/打不开 —— 这正是我第一轮实测拿到 404 的原因。

    判据：**视频 ID 恰好 11 位**。
    """
    from app.services.platforms.youtube.client import _entry_to_result

    # 播放列表条目（实测形态）
    pl = _entry_to_result({
        "id": "PLTjRvDozrdlxj5wgH4qkvwSOdHLOCx10f",
        "title": "Python Tutorials",
        "url": "https://www.youtube.com/playlist?list=PL...",
    })
    assert pl is None, "播放列表必须被过滤（它不是视频，详情打不开）"

    # 正常视频（11 位）
    vid = _entry_to_result({
        "id": "rfscVS0vtbw",
        "title": "Learn Python - Full Course for Beginners",
        "duration": 16012,
        "view_count": 49376853,
        "channel": "freeCodeCamp.org",
    })
    assert vid is not None
    assert vid.id == "rfscVS0vtbw"
    assert vid.platform == "youtube"
    assert vid.duration == 16012


def test_channel_id_and_handle_use_different_paths():
    """**回归**：`UC...` 频道 ID 不能当 handle 拼成 `@UC...`。

    实测：这样拼会 **404**（`@UC68KSmHePPePCjW4v57VPQg`）。
    正确路径是 `/channel/{id}/videos`，handle 才走 `/{handle}/videos`。
    """
    from app.services.platforms.youtube.client import YoutubeClient

    for fn in (YoutubeClient.get_user_notes, YoutubeClient.get_user_profile):
        src = inspect.getsource(fn)
        assert "/channel/" in src, f"{fn.__name__} 要识别 UC... 频道 ID 走 /channel/"
        assert '"UC"' in src or "'UC'" in src, f"{fn.__name__} 要判 UC 前缀"


def test_provides_both_user_video_method_names():
    """**回归**：`get_user_videos` 和 `get_user_notes` 两个名字都要有。

    ## 实测踩到的坑

    `users.py::/users/videos` 路由调的是 **`get_user_videos`**，
    而基类里同类能力叫 **`get_user_notes`**。我只实现了后者，
    于是 `/users/videos?platform=youtube` 报：

        HTTP 500: 'YoutubeClient' object has no attribute 'get_user_videos'

    "实现了但路由找不到" —— 又一个"名字对不上"的静默失败。
    两个名字都提供（别名），任一方改名都不会再断。
    """
    from app.services.platforms.youtube.client import YoutubeClient

    assert hasattr(YoutubeClient, "get_user_videos"), (
        "users.py::/users/videos 调 get_user_videos —— 缺了会 500"
    )
    assert hasattr(YoutubeClient, "get_user_notes"), "基类同名能力也要有"
    assert hasattr(YoutubeClient, "search_users"), "频道搜索"


def test_duration_filter_is_client_side():
    """**回归**：时长过滤在**客户端**做，不靠 sp 参数。

    原因：YouTube 只认一个 `sp=`，排序与时长**互斥**。
    实测排序优先，时长按 duration 字段过滤。
    """
    from app.services.platforms.youtube import client as yc

    src = inspect.getsource(yc.YoutubeClient.search)
    assert "_duration_pass" in src, "时长要按 duration 字段过滤"
    # 也要留档：组合时排序优先
    assert "sp" in src.lower()


def test_detail_does_not_fake_video_direct_url():
    """详情**不给** video 直链（YouTube 是分段加密流，直链几分钟失效）。

    下载走 `/api/v1/download` 的 yt-dlp 链路 —— 实测可用
    （parse 返回 googlevideo 720p 直链 + 封面 + 时长）。
    给一个会立刻失效的直链会让前端播放器空转。
    """
    from app.services.platforms.youtube import client as yc

    src = inspect.getsource(yc.YoutubeClient.get_detail)
    assert "video=\"\"" in src or 'video=""' in src, "详情不该给会失效的直链"
    assert "download.py" in src or "download" in src, "要说明下载走哪条链路"


def test_frontend_has_no_rating_sort():
    """**回归**：前端不能有 `rating`（评分）排序 —— YouTube 早已下线该档。

    假选项比没有更糟：选了没反应，用户会以为网络问题。
    实测可用的只有 relevance / date / viewCount 三档。
    """
    from pathlib import Path

    p = (Path(__file__).resolve().parents[2] / "frontend" / "src" /
         "pages" / "crawler" / "index.tsx")
    if not p.exists():
        import pytest
        pytest.skip("搜索页不在预期位置")
    src = p.read_text(encoding="utf-8", errors="ignore")
    i = src.find("youtube: {")
    assert i != -1
    seg = src[i:i + 1200]
    assert "'rating'" not in seg and '"rating"' not in seg, (
        "rating 排序 YouTube 已下线，不能列出来（假选项）"
    )
