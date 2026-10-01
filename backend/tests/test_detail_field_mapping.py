"""详情字段映射的回归测试（2026-10-01 修两个"静默丢字段"）。

## 为什么单独测这个

`get_note_detail` 是「平台对象 → dict → pydantic 模型 → 前端」四层转换，
**每一层都可能静默丢字段**（不报错，只是值为 0/空）：

    ① 平台对象有值（YouTube `duration=16012`）
    ② service 转换字典**漏了这个键**      ← 这次踩的
    ③ pydantic 模型**没定义这个字段**      ← `views` 踩的
    ④ 前端不渲染

②③ 两层都是**静默**的：pydantic 默认忽略多余字段，字典漏键也不会报错。

实测症状：**列表里有数据、点进详情却没有** ——
"YouTube 详情不显示时长/播放量"（列表里明明有）。
"""

from __future__ import annotations

import pytest


# =============================================================================
# 模型字段完整性
# =============================================================================

def test_note_detail_model_has_views():
    """**回归**：`crawler.models.NoteDetail` 必须有 `views` 字段。

    实测：service 层一直在往字典里放 `views`
    （YouTube 4937万、Telegram 151万），但模型**没定义这个字段**
    → pydantic **静默忽略** → 前端永远拿不到播放量。

    ⚠️ 与仓库里 `collect_count` 那个坑**同类**
    （"字段名不对，pydantic 静默忽略"）。
    """
    from app.services.crawler.models import NoteDetail

    assert "views" in NoteDetail.model_fields, (
        "NoteDetail 缺 views 字段 —— service 传了也会被 pydantic 静默丢弃"
    )


def test_note_detail_model_has_video_cover():
    """`video_cover` 同理事（视频封面）。"""
    from app.services.crawler.models import NoteDetail

    assert "video_cover" in NoteDetail.model_fields


def test_note_detail_model_has_duration():
    """`duration` 模型里早就有 —— 但 service 层转换时漏传过。"""
    from app.services.crawler.models import NoteDetail

    assert "duration" in NoteDetail.model_fields


# =============================================================================
# service 转换字典的键完整性
# =============================================================================

def test_service_detail_dict_includes_all_model_fields():
    """**回归（关键）**：service 转换字典要覆盖模型的**所有**字段。

    这是"漏字段"的结构性防线：`get_note_detail` 里那个大字典
    要是漏了某个键，对应字段就永远是默认值（0/空），
    **不报错、测试也全绿**。

    实测踩过两次：
      · `duration`（YouTube 16012 秒 → 前端 0）
      · `video_cover`
    """
    import inspect

    from app.services.crawler.models import NoteDetail
    from app.services.crawler import service as svc

    src = inspect.getsource(svc.CrawlerService.get_note_detail)

    # 模型字段里，除了 raw_data/id/platform 这类必然有的，其余都该出现在字典里
    required = [
        "title", "desc", "images", "video", "video_cover", "author",
        "author_id", "likes", "comments", "shares", "collect_count",
        "duration", "views", "create_time", "tags", "raw_data",
    ]
    missing = [f for f in required if f'"{f}"' not in src]
    assert not missing, (
        f"service 转换字典漏了这些字段：{missing} —— "
        "pydantic 会静默用默认值，前端拿到 0/空"
    )

    # 同时确认模型确实定义了它们（防两边都不对）
    for f in required:
        assert f in NoteDetail.model_fields, f"模型缺 {f}"


# =============================================================================
# 平台侧真的填了这些字段
# =============================================================================

def test_youtube_detail_fills_duration_and_views():
    """YouTube 的 `NoteDetail` 要填 duration/views（实测有值）。

    实测：`duration=16012`（4:26:52）、`views=49377856`。
    """
    import inspect

    from app.services.platforms.youtube import client as yc

    src = inspect.getsource(yc.YoutubeClient.get_detail)
    assert "duration=" in src, "YouTube 详情要填 duration"
    assert "views=" in src, "YouTube 详情要填 views"


def test_telegram_detail_fills_duration_and_views():
    """Telegram 同理（实测 duration=6、views=1510000）。"""
    import inspect

    from app.services.platforms.telegram import client as tc

    src = inspect.getsource(tc.TelegramClient.get_detail)
    assert "duration=" in src
    assert "views=" in src


def test_telegram_detail_carries_rich_fields():
    """Telegram 详情要带**平台特有**字段（前端富文本渲染要用）。

    Telegram 的消息有其它平台没有的东西：
      · `html`     —— 保留 `<a>`/`<br>`/emoji 的富文本
      · `links`    —— 正文里的外链
      · `forward_from` —— 转发来源
    """
    import inspect

    from app.services.platforms.telegram import client as tc

    src = inspect.getsource(tc.TelegramClient.get_detail)
    for key in ("html", "links", "forward_from"):
        assert key in src, f"Telegram 详情要带 {key}（前端渲染要用）"
