# -*- coding: utf-8 -*-
"""内容包平台适配器测试（content-package-workspaces #15）。

覆盖：
- 五个适配器都能产出，且每条输出带齐溯源字段；
- **不复制 items**：平台产物只按 item_id 回引，输出记录自身不含 items 副本；
- 单个适配器抛错**不影响其它**适配器（失败可独立重建）；
- 未知适配器名在构建前报错；
- 各平台产物的关键形状（公众号摘要上限、小红书 3:4 卡片、抖音 9:16 镜头表、
  PDF 分页与文件名、素材包三件套）。
"""
from __future__ import annotations

import pytest

from app.services.creative_project.content_package_adapters import (
    ADAPTERS,
    ADAPTER_TYPES,
    DOUYIN_VIDEO,
    WECHAT_DIGEST_LIMIT,
    XHS_CARD,
    AdapterInput,
    AdapterSpec,
    adapter_catalog,
    adapter_input_from_package,
    build_package_outputs,
)

PACKAGE = {
    "package_type": "page_book",
    "title": "十二生肖绘本",
    "topic": "十二生肖",
    "brief": "给孩子看的十二生肖入门绘本，一页一个生肖。",
    "style": "中国剪纸",
    "aspect_ratio": "4:3",
    "items": [
        {
            "id": "item-1",
            "index": 1,
            "title": "鼠",
            "text": "老鼠靠机灵拿下了第一名的位置。",
            "image_prompt": "剪纸风格的小老鼠",
            "video_prompt": "小老鼠跑动",
            "asset_ids": ["asset-1"],
            "status": "ready",
        },
        {
            "id": "item-2",
            "index": 2,
            "title": "牛",
            "text": "老牛勤恳踏实，甘愿排在第二。",
            "image_prompt": "剪纸风格的老牛",
            "video_prompt": "",
            "asset_ids": [],
            "status": "draft",
        },
    ],
}


def _input(**overrides) -> AdapterInput:
    base = adapter_input_from_package(PACKAGE, package_id="pkg-1", package_version=3)
    return AdapterInput(**{**base.__dict__, **overrides}) if overrides else base


# ---------------------------------------------------------------------------
# 1. 目录与基本产出
# ---------------------------------------------------------------------------


def test_catalog_lists_all_adapters():
    catalog = adapter_catalog()
    assert [item["adapter_type"] for item in catalog] == list(ADAPTER_TYPES)
    # 抖音与 PDF 目前只产规划数据，目录里要如实标注
    by_type = {item["adapter_type"]: item for item in catalog}
    assert by_type["douyin_short_video"]["planning_only"] is True
    assert by_type["pdf_ebook"]["planning_only"] is True
    assert by_type["wechat_official_account"]["planning_only"] is False


def test_all_adapters_produce_ready_outputs_with_provenance():
    outputs = build_package_outputs(_input(), list(ADAPTER_TYPES))
    assert len(outputs) == len(ADAPTER_TYPES)
    for out in outputs:
        assert out["status"] == "ready", out
        # 溯源四件套 + 生成时间
        assert out["source_package_id"] == "pkg-1"
        assert out["source_package_version"] == 3
        assert out["source_item_ids"] == ["item-1", "item-2"]
        assert out["adapter_type"] in ADAPTER_TYPES
        assert out["generated_at"]


def test_outputs_do_not_duplicate_source_items():
    """平台产物只按 item_id 回引，输出记录自身不得携带 items 副本。"""
    outputs = build_package_outputs(_input(), list(ADAPTER_TYPES))
    for out in outputs:
        assert "items" not in out, "%s 的输出不应包含 items 副本" % out["adapter_type"]
        payload = out["payload"]
        # 逐条产物必须能回溯到源 item
        for key in ("cards", "shots", "pages"):
            for entry in payload.get(key) or []:
                assert entry["item_id"], "%s.%s 缺少 item_id 回引" % (out["adapter_type"], key)


# ---------------------------------------------------------------------------
# 2. 失败隔离与参数校验
# ---------------------------------------------------------------------------


def test_unknown_adapter_raises_before_building():
    with pytest.raises(ValueError) as exc:
        build_package_outputs(_input(), ["wechat_official_account", "not_an_adapter"])
    assert "不支持的内容包适配器" in str(exc.value)


def test_one_failing_adapter_does_not_break_the_others(monkeypatch):
    def _boom(_inp):
        raise RuntimeError("平台模板缺失")

    # AdapterSpec 是 frozen dataclass，不能改字段——替换整个注册项
    monkeypatch.setitem(
        ADAPTERS,
        "xiaohongshu_carousel",
        AdapterSpec(adapter_type="xiaohongshu_carousel", label="小红书轮播卡", build=_boom),
    )

    outputs = build_package_outputs(_input(), ["wechat_official_account", "xiaohongshu_carousel", "asset_bundle"])
    by_type = {out["adapter_type"]: out for out in outputs}

    assert by_type["xiaohongshu_carousel"]["status"] == "failed"
    assert "平台模板缺失" in by_type["xiaohongshu_carousel"]["error"]
    # 失败那条也保留溯源，便于独立重建
    assert by_type["xiaohongshu_carousel"]["source_package_version"] == 3
    # 兄弟适配器不受影响
    assert by_type["wechat_official_account"]["status"] == "ready"
    assert by_type["asset_bundle"]["status"] == "ready"


def test_empty_adapter_list_returns_empty():
    assert build_package_outputs(_input(), []) == []


# ---------------------------------------------------------------------------
# 3. 各平台产物形状
# ---------------------------------------------------------------------------


def test_wechat_payload_shape():
    out = build_package_outputs(_input(), ["wechat_official_account"])[0]
    payload = out["payload"]
    assert payload["title"] == "十二生肖绘本"
    assert len(payload["digest"]) <= WECHAT_DIGEST_LIMIT
    assert "老鼠靠机灵" in payload["html"]
    assert "<h2>鼠</h2>" in payload["html"]
    assert payload["cover_asset_ids"] == ["asset-1"]
    assert payload["body_image_asset_ids"] == ["asset-1"]
    # 草稿 payload 形状对齐微信，但不发送
    assert payload["draft_payload"]["title"] == payload["title"]


def test_wechat_html_escapes_markup():
    item = {**PACKAGE["items"][0], "text": "<script>alert(1)</script>"}
    inp = _input(items=(item,))
    html = build_package_outputs(inp, ["wechat_official_account"])[0]["payload"]["html"]
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_xiaohongshu_card_shape():
    payload = build_package_outputs(_input(), ["xiaohongshu_carousel"])[0]["payload"]
    assert payload["card_size"] == XHS_CARD
    assert [card["order"] for card in payload["cards"]] == [1, 2]
    assert payload["cards"][0]["title"] == "鼠"
    assert payload["cards"][0]["image_asset_ids"] == ["asset-1"]
    # 未显式给 tags 时退到包的 style，保证卡片有话题标签
    assert payload["cards"][0]["tags"] == ["中国剪纸"]


def test_douyin_shot_list_shape():
    out = build_package_outputs(_input(), ["douyin_short_video"])[0]
    payload = out["payload"]
    assert payload["video_params"] == DOUYIN_VIDEO
    assert payload["orientation"] == "portrait"
    assert payload["total_shots"] == 2
    assert payload["shots"][0]["action_prompt"] == "小老鼠跑动"
    assert payload["shots"][0]["voiceover"] == "老鼠靠机灵拿下了第一名的位置。"
    assert payload["captions_text"]
    # 只产规划数据这件事必须在 warnings 里说清楚
    assert any("只产出规划数据" in w for w in out["warnings"])


def test_pdf_ebook_page_shape_and_renderer_warning():
    out = build_package_outputs(_input(), ["pdf_ebook"])[0]
    payload = out["payload"]
    assert payload["filename"] == "十二生肖绘本.pdf"
    assert payload["page_count"] == 2
    assert payload["page_size"] == "A4"
    assert payload["pages"][0]["text"].startswith("老鼠")
    # 本环境没有 PDF 生成库，只给分页数据——必须如实提示
    assert any("只产出规划数据" in w or "渲染" in w for w in out["warnings"])


def test_asset_bundle_contains_three_files_and_manifest():
    payload = build_package_outputs(_input(), ["asset_bundle"])[0]["payload"]
    paths = [f["path"] for f in payload["files"]]
    assert paths == ["package.json", "content.md", "prompts.tsv"]
    assert payload["manifest"]["version"] == 3
    assert payload["manifest"]["item_count"] == 2
    markdown = next(f["content"] for f in payload["files"] if f["path"] == "content.md")
    assert "# 十二生肖绘本" in markdown
    assert "## 1. 鼠" in markdown


def test_wechat_html_keeps_asset_placeholder_when_urls_unresolved():
    """后端不解析资产 URL（由前端负责）：此时必须留 asset 占位，不能悄悄少图。"""
    html = build_package_outputs(_input(), ["wechat_official_account"])[0]["payload"]["html"]
    assert 'data-asset-id="asset-1"' in html


def test_adapter_input_injects_asset_urls():
    inp = adapter_input_from_package(
        PACKAGE,
        package_id="pkg-1",
        package_version=1,
        asset_urls={"item-1": ["https://cdn.example.com/a.png"]},
    )
    payload = build_package_outputs(inp, ["xiaohongshu_carousel"])[0]["payload"]
    assert payload["cards"][0]["image_urls"] == ["https://cdn.example.com/a.png"]
    assert payload["cards"][1]["image_urls"] == []
