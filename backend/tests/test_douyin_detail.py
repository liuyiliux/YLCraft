"""抖音详情从搜索结果构造（不额外请求）。

## 背景（2026-09-27）

用户截图：点开抖音搜索结果 → "详情加载失败，保留搜索结果"。

原因：`DouyinClient.get_detail` 原来是 `NotImplementedError`
（按仓库硬规则，未抓包确认的接口不猜路径）。

但**搜索结果的 `aweme_info` 已经包含详情所需的一切**：
描述、作者、统计、封面、时长、无水印视频地址、图集。
所以详情不该再发一次请求——既慢又容易撞上风控受限窗口。

现在的做法：
  · 前端点开详情直接用结果里的 record 渲染（抖音分支，不走后端）
  · 后端 `get_detail(raw=...)` 也能从原始条目构造详情（供其它调用方）
  · 没有 raw 时显式报错，说明该怎么办（不静默返回空）
"""

from __future__ import annotations

import pytest


def _raw(
    aweme_id: str = "123",
    desc: str = "古早小吊带",
    *,
    with_video: bool = True,
    with_images: bool = False,
) -> dict:
    info: dict = {
        "aweme_id": aweme_id,
        "desc": desc,
        "create_time": 1700000000,
        "author": {"nickname": "哆啦A梦", "uid": "999"},
        "statistics": {
            "digg_count": 119, "comment_count": 4,
            "share_count": 6, "collect_count": 7, "play_count": 500,
        },
    }
    if with_video:
        info["video"] = {
            "duration": 43000,
            "cover": {"url_list": ["https://p3.douyinpic.com/cover.jpeg"]},
            "play_addr": {"url_list": ["https://v.douyin.com/nowm.mp4"]},
        }
    if with_images:
        info["image_infos"] = [
            {"url_list": ["https://p3.douyinpic.com/img1.jpeg"]},
            {"url_list": ["https://p3.douyinpic.com/img2.jpeg"]},
        ]
    return {"type": 1, "aweme_info": info}


def test_detail_from_raw_basic_fields():
    """基本信息要正确带出。"""
    from app.services.platforms.douyin.client import _detail_from_raw

    d = _detail_from_raw(_raw(), "123")
    assert d.id == "123"
    assert d.title == "古早小吊带"
    assert d.desc == "古早小吊带"
    assert d.author == "哆啦A梦"
    assert d.author_id == "999"
    assert d.platform == "douyin"
    assert d.type == "video"


def test_detail_from_raw_stats():
    """统计要带全（赞/评/转/藏/播放）。"""
    from app.services.platforms.douyin.client import _detail_from_raw

    d = _detail_from_raw(_raw(), "123")
    assert d.likes == 119
    assert d.comments == 4
    assert d.shares == 6
    assert d.collects == 7
    assert d.views == 500


def test_detail_from_raw_video_and_cover():
    """视频地址与封面要取到。

    视频优先用 play_addr（通常是无水印直链）。
    """
    from app.services.platforms.douyin.client import _detail_from_raw

    d = _detail_from_raw(_raw(), "123")
    assert d.video == "https://v.douyin.com/nowm.mp4"
    assert d.video_cover == "https://p3.douyinpic.com/cover.jpeg"
    assert d.duration == 43, "抖音时长是毫秒，应换算成秒"


def test_detail_from_raw_images():
    """图集笔记要带出图片列表，且类型是 note。"""
    from app.services.platforms.douyin.client import _detail_from_raw

    d = _detail_from_raw(_raw(with_images=True), "123")
    assert len(d.images) == 2
    assert d.type == "note", "有图集就是图文笔记"


def test_detail_from_raw_tolerates_missing_fields():
    """字段缺失不能崩（抖音响应结构会变）。"""
    from app.services.platforms.douyin.client import _detail_from_raw

    d = _detail_from_raw({"aweme_info": {"aweme_id": "1"}}, "1")
    assert d.id == "1"
    assert d.images == []
    assert d.video == ""
    assert d.likes == 0


def test_detail_from_raw_accepts_bare_aweme_info():
    """容错：调用方可能直接传 aweme_info（不带外层包装）。"""
    from app.services.platforms.douyin.client import _detail_from_raw

    bare = _raw()["aweme_info"]
    d = _detail_from_raw(bare, "123")
    assert d.id == "123"
    assert d.author == "哆啦A梦"


@pytest.mark.asyncio
async def test_get_detail_requires_raw():
    """没有 raw 时要显式报错，并说明该怎么办。

    不静默返回空——空详情会让前端以为"笔记不存在"，
    实际只是缺了搜索时的原始数据。
    """
    from app.services.platforms.douyin.client import DouyinClient
    from app.services.platforms.types import ClientConfig, ClientMode

    client = DouyinClient(
        ClientConfig(platform="douyin", mode=ClientMode.API, cookie="probe=1")
    )
    with pytest.raises(NotImplementedError) as exc:
        await client.get_detail("123")
    msg = str(exc.value)
    assert "raw" in msg.lower(), "应说明需要 raw_data"
    assert "不猜" in msg or "未抓包" in msg, "应说明为什么不按 id 反查"


@pytest.mark.asyncio
async def test_get_detail_builds_from_raw():
    """传了 raw 就能正常构造详情。"""
    from app.services.platforms.douyin.client import DouyinClient
    from app.services.platforms.types import ClientConfig, ClientMode

    client = DouyinClient(
        ClientConfig(platform="douyin", mode=ClientMode.API, cookie="probe=1")
    )
    d = await client.get_detail("123", raw=_raw())
    assert d.author == "哆啦A梦"
    assert d.video


def test_frontend_uses_record_for_douyin_detail():
    """前端抖音分支应直接用搜索结果渲染，不再请求后端详情。

    搜索结果已含全部详情字段，且后端也没有按 id 反查的接口。
    走一次多余请求既慢又容易撞上抖音的风控受限窗口。
    """
    from pathlib import Path

    page = (
        Path(__file__).resolve().parents[2]
        / "frontend" / "src" / "pages" / "crawler" / "index.tsx"
    )
    if not page.exists():
        pytest.skip("前端源码不在预期位置")
    src = page.read_text(encoding="utf-8", errors="ignore")
    assert "record.platform === 'douyin'" in src, "应有抖音详情分支"
    # 该分支应在 getNoteDetail 调用之前返回
    i_branch = src.find("record.platform === 'douyin'")
    i_call = src.find("await getNoteDetail(")
    assert i_branch != -1 and i_call != -1
    assert i_branch < i_call, "抖音分支应在请求后端之前返回"
