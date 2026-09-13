# -*- coding: utf-8 -*-
"""内容包规划器测试（content-package-workspaces #6）。

覆盖两件事：
1. **提取后的兼容性**——`outline_service.generate_outline` 的响应结构逐字段不变，
   `/images/generate-outline` 不需要任何改动；
2. **新规划器的复用能力**——平台大纲可转换为内容包契约（items 化），失败平台进
   warnings 而不是伪造 item。
"""
from __future__ import annotations

from typing import Any

from app.services.ai.content_package_planner import ContentPackagePlanner
from app.services.ai.outline_service import (
    _parse_outline_text,
    generate_outline,
)


# ---------------------------------------------------------------------------
# 最小假件：规划器只调用 session.execute(...).scalars().all() 与 manager.chat(...)
# ---------------------------------------------------------------------------


class _FakeScalars:
    def __init__(self, items: list[Any]):
        self._items = items

    def all(self) -> list[Any]:
        return self._items


class _FakeResult:
    """`session.execute(...)` 的返回：需要 `.scalars()` 再 `.all()`（两层）。"""

    def __init__(self, items: list[Any]):
        self._items = items

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._items)


class _FakeSession:
    def __init__(self, templates: list[Any]):
        self.templates = templates

    async def execute(self, _stmt: Any) -> _FakeResult:
        return _FakeResult(self.templates)


class _FakeTemplate:
    """模板渲染后的提示词内嵌自身名称，便于假 manager 分辨是哪个平台。"""

    def __init__(self, platform: str, name: str, outline_template: str = ""):
        self.platform = platform
        self.name = name
        # 只允许 {topic} / {page_structure} 两个占位符（与真实模板一致）
        self.outline_template = outline_template or (
            "【%s】主题：{topic}\n结构：{page_structure}" % name
        )
        self.page_structure = {"cover": "封面"}


class _FakeResp:
    def __init__(self, content: str = "", success: bool = True, error: Any = None):
        self.content = content
        self.success = success
        self.error = error


class _FakeManager:
    """按 platform 返回预设内容；未预设的返回失败。"""

    def __init__(self, by_prompt_keyword: dict[str, str]):
        self.by_keyword = by_prompt_keyword
        self.calls: list[dict[str, Any]] = []

    async def chat(self, messages, backend_name=None, model=None):  # noqa: ANN001
        self.calls.append({"messages": messages, "backend_name": backend_name, "model": model})
        # 用第一条消息的文本内容来判断是哪个平台（模板里带平台名）
        first = messages[0]
        text = first.content if isinstance(first.content, str) else str(first.content)
        for kw, content in self.by_keyword.items():
            if kw in text:
                return _FakeResp(content=content)
        return _FakeResp(content="", success=False, error="no preset")


SAMPLE_OUTLINE = """【标题】十二生肖的故事
【文案】带孩子认识生肖
【图片提示词】[封面] 剪纸风格的十二生肖围成一圈
【图片提示词】[内容] 机灵的小老鼠在灯下
"""


# ---------------------------------------------------------------------------
# 1. 兼容性：响应结构不变
# ---------------------------------------------------------------------------


async def test_generate_outline_response_shape_is_preserved():
    """`generate_outline` 必须返回原有的按平台聚合结构（键与层级都不能变）。"""
    session = _FakeSession([_FakeTemplate("xiaohongshu", "小红书")])
    manager = _FakeManager({"小红书": SAMPLE_OUTLINE})
    planner = ContentPackagePlanner(manager=manager)

    # 直接调规划器（wrapper 只是委托，见下一个测试）
    outlines = await planner.plan_platform_outlines(session, "十二生肖", ["xiaohongshu"])

    assert set(outlines) == {"xiaohongshu"}
    one = outlines["xiaohongshu"]
    # 原结构要求：title / copywriting / pages / platform / platform_name
    assert set(one) >= {"title", "copywriting", "pages", "platform", "platform_name"}
    assert one["title"] == "十二生肖的故事"
    assert one["copywriting"] == "带孩子认识生肖"
    assert one["platform"] == "xiaohongshu"
    assert one["platform_name"] == "小红书"
    assert [p["type"] for p in one["pages"]] == ["封面", "内容"]
    assert one["pages"][0]["prompt"] == "剪纸风格的十二生肖围成一圈"


async def test_outline_service_wrapper_delegates_and_keeps_shape():
    """`outline_service.generate_outline` 委托后行为不变：无模板时返回 {}。"""
    empty = await generate_outline(_FakeSession([]), "任意主题", ["xiaohongshu"])
    assert empty == {}


async def test_parse_outline_text_alias_still_works():
    """兼容别名 `_parse_outline_text` 必须继续可用（深层引用不会断）。"""
    parsed = _parse_outline_text(SAMPLE_OUTLINE)
    assert parsed["title"] == "十二生肖的故事"
    assert len(parsed["pages"]) == 2


async def test_failed_platform_keeps_legacy_fallback_structure():
    """单平台失败时仍返回兜底结构（含 error），且不影响其它平台。"""
    session = _FakeSession([
        _FakeTemplate("xiaohongshu", "小红书"),
        _FakeTemplate("weibo", "微博"),
    ])
    manager = _FakeManager({"小红书": SAMPLE_OUTLINE})
    planner = ContentPackagePlanner(manager=manager)

    outlines = await planner.plan_platform_outlines(session, "主题X", ["xiaohongshu", "weibo"])

    assert set(outlines) == {"xiaohongshu", "weibo"}
    assert outlines["weibo"]["pages"] == []
    assert outlines["weibo"]["title"] == "主题X"
    assert outlines["weibo"]["error"] == "no preset"
    # 兄弟平台不受影响
    assert len(outlines["xiaohongshu"]["pages"]) == 2


# ---------------------------------------------------------------------------
# 2. 复用能力：转换成内容包契约
# ---------------------------------------------------------------------------


def test_platform_outlines_to_package_builds_contract_shaped_items():
    """一页 ⇒ 一个 item，键集与内容包契约一致，且记录来源平台。"""
    outlines = {
        "xiaohongshu": {
            "title": "十二生肖的故事",
            "copywriting": "带孩子认识生肖",
            "pages": [
                {"type": "封面", "prompt": "剪纸风格的十二生肖"},
                {"type": "内容", "prompt": "小老鼠在灯下"},
            ],
            "platform": "xiaohongshu",
            "platform_name": "小红书",
        }
    }
    package = ContentPackagePlanner.platform_outlines_to_package(
        outlines, package_type="page_book", topic="十二生肖"
    )

    assert package["package_type"] == "page_book"
    assert package["topic"] == "十二生肖"
    assert package["title"] == "十二生肖的故事"
    assert package["brief"] == "带孩子认识生肖"
    assert package["version"] == 1
    assert package["outputs"] == []
    assert package["source_context"]["platforms"] == ["xiaohongshu"]
    assert package["warnings"] == []

    assert [i["index"] for i in package["items"]] == [1, 2]
    assert [i["title"] for i in package["items"]] == ["封面", "内容"]
    assert package["items"][0]["image_prompt"] == "剪纸风格的十二生肖"
    assert package["items"][0]["source_refs"] == [{"platform": "xiaohongshu"}]
    assert package["items"][0]["status"] == "draft"
    # 契约键集固定（防两处形状漂移）
    expected = {
        "index", "title", "text", "fact", "source", "source_url",
        "image_prompt", "video_prompt", "source_refs", "asset_ids", "status",
    }
    for item in package["items"]:
        assert set(item) == expected


def test_failed_platform_does_not_create_fake_items_and_warns():
    """规划失败的平台不得伪造 item（否则用户会拿到空卡）；必须进 warnings。"""
    outlines = {
        "weibo": {"title": "T", "copywriting": "", "pages": [], "error": "boom"},
    }
    package = ContentPackagePlanner.platform_outlines_to_package(outlines, topic="T")

    assert package["items"] == []
    assert len(package["warnings"]) == 1
    assert "weibo" in package["warnings"][0]
    assert "boom" in package["warnings"][0]


def test_empty_outlines_yield_empty_package():
    package = ContentPackagePlanner.platform_outlines_to_package({}, topic="空主题")
    assert package["items"] == []
    assert package["source_context"]["platforms"] == []
    assert package["title"] == "空主题"


def test_build_outline_messages_supports_multimodal():
    """有参考图时必须构造多模态 content 数组（原行为）。"""
    msgs = ContentPackagePlanner.build_outline_messages("提示词", ["data:image/png;base64,AAA"])
    assert len(msgs) == 1
    content = msgs[0].content
    assert isinstance(content, list)
    assert content[0] == {"type": "text", "text": "提示词"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"] == "data:image/png;base64,AAA"

    # 无参考图时为纯文本
    plain = ContentPackagePlanner.build_outline_messages("提示词", None)
    assert plain[0].content == "提示词"
