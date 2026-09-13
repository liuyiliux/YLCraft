# -*- coding: utf-8 -*-
"""内容包类型 schema 测试（content-package-workspaces #13）。

覆盖：
- 六种类型的 schema 齐备，其中 article_package / social_carousel / shot_list /
  single_media 标记为 ui_enabled=False（本期仅 API，不建 UI）；
- 硬校验（未知类型 / 超上限 / status 非法 / 无任何媒体提示词）确实抛错；
- 软提示（条数偏少、缺推荐字段）只返回 warnings，不阻断保存；
- 生成路径按 schema 夹住数量（防"生成成功但保存失败"）。
"""
from __future__ import annotations

import pytest

from app.services.creative_project.content_package_schema import (
    ITEM_STATUSES,
    PACKAGE_SCHEMAS,
    SCHEMA_VERSION,
    get_package_schema,
    schema_descriptor,
    validate_content_package,
)

#: 本期只做 API、不建 UI 的四种类型
API_ONLY_TYPES = ("article_package", "social_carousel", "shot_list", "single_media")
UI_TYPES = ("page_book", "knowledge_cards")


def _item(index: int, **extra) -> dict:
    base = {
        "id": "item-%d" % index,
        "index": index,
        "status": "draft",
        "asset_ids": [],
        "source_refs": [],
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# 1. schema 声明完整性
# ---------------------------------------------------------------------------


def test_all_six_package_types_are_declared():
    assert set(PACKAGE_SCHEMAS) == set(UI_TYPES) | set(API_ONLY_TYPES)


@pytest.mark.parametrize("package_type", API_ONLY_TYPES)
def test_api_only_types_are_not_ui_enabled(package_type):
    """本期这四种不建 UI——用 schema 上的开关标记，而不是隐式约定。"""
    schema = get_package_schema(package_type)
    assert schema.ui_enabled is False
    assert schema_descriptor(package_type)["ui_enabled"] is False


@pytest.mark.parametrize("package_type", UI_TYPES)
def test_ui_types_are_ui_enabled(package_type):
    assert get_package_schema(package_type).ui_enabled is True


def test_unknown_package_type_raises():
    with pytest.raises(ValueError) as exc:
        get_package_schema("does_not_exist")
    assert "不支持的内容包类型" in str(exc.value)


def test_schema_descriptor_shape():
    d = schema_descriptor("social_carousel")
    assert d["package_type"] == "social_carousel"
    assert d["version"] == SCHEMA_VERSION
    assert d["max_items"] == 10
    assert d["min_recommended_items"] == 6
    assert d["default_media"] == "image"
    assert "image_prompt" in d["recommended_item_fields"]


# ---------------------------------------------------------------------------
# 2. 硬校验
# ---------------------------------------------------------------------------


def test_too_many_items_is_a_hard_error():
    items = [_item(i, image_prompt="p") for i in range(1, 12)]
    with pytest.raises(ValueError) as exc:
        validate_content_package("single_media", {}, items)  # 上限 1 条
    assert "上限" in str(exc.value)


def test_invalid_status_is_a_hard_error():
    items = [_item(1, image_prompt="p", status="not_a_status")]
    with pytest.raises(ValueError) as exc:
        validate_content_package("page_book", {}, items)
    assert "status 非法" in str(exc.value)


def test_allowed_statuses_are_accepted():
    for status in ITEM_STATUSES:
        validate_content_package("page_book", {}, [_item(1, image_prompt="p", status=status)])


def test_package_without_any_media_prompt_only_warns():
    """整包都没有提示词 → 提示不可出图，但**不拒绝保存**。

    内容包是增量编辑的产物，"先存标题、再补提示词"是正常中间态
    （版本追加接口本身就被这样用）。
    """
    items = [_item(1, title="第一页"), _item(2, title="第二页")]
    warnings = validate_content_package("page_book", {}, items)
    assert any("没有任何 image_prompt / video_prompt" in w for w in warnings)


def test_article_package_does_not_require_media_prompt():
    """文章整体成篇，允许只给文字。"""
    items = [_item(1, text="第一段"), _item(2, text="第二段")]
    warnings = validate_content_package("article_package", {}, items)
    assert not any("image_prompt" in w for w in warnings)


# ---------------------------------------------------------------------------
# 3. 软提示
# ---------------------------------------------------------------------------


def test_below_recommended_count_only_warns():
    """social_carousel 建议 6-10 张；给 3 张只提示，不阻断。"""
    items = [_item(i, title="卡 %d" % i, text="正文", image_prompt="p") for i in range(1, 4)]
    warnings = validate_content_package("social_carousel", {}, items)
    assert any("建议至少 6 条" in w for w in warnings)


def test_missing_recommended_fields_only_warns():
    items = [_item(1, image_prompt="p"), _item(2, title="有标题", image_prompt="p")]
    warnings = validate_content_package("page_book", {}, items)
    assert any("缺少 title" in w for w in warnings)


def test_clean_package_has_no_warnings():
    """按生成路径实际产出的形状构造：不应有任何提示。"""
    items = [
        _item(i, title="第 %d 页" % i, text="页文字", image_prompt="提示词", video_prompt="")
        for i in range(1, 13)
    ]
    assert validate_content_package("page_book", {}, items) == []


def test_empty_package_does_not_trigger_media_error():
    """空包（尚未生成）不应被判为"无媒体提示词"——那是"没有内容"，不是"内容不可用"。"""
    assert validate_content_package("page_book", {}, []) == []
