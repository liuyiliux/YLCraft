from types import SimpleNamespace

import pytest

from app.services.character.portrait_prompt import (
    PROMPT_TEMPLATE_VERSION,
    build_portrait_prompt,
    normalize_preset,
)


def test_identity_board_prompt_contains_reference_layout_rules():
    character = SimpleNamespace(
        id="char-1",
        name="林昭",
        role="protagonist",
        age_range="20-25岁",
        appearance="黑色短发，凤眼，左眼下有小痣",
        costume_hint="白衬衫，黑色长风衣，银色吊坠",
        personality="冷静克制",
        signature_items='["银色吊坠"]',
        expressions='["冷静", "愤怒", "震惊"]',
        poses='["正面站姿", "回头", "蹲姿"]',
        tags='["都市", "悬疑"]',
        visual_consistency="发型、吊坠和风衣不要变化",
    )

    result = build_portrait_prompt(character=character, preset="identity_board_16_9")

    assert result["preset"] == "identity_board_16_9"
    assert result["prompt_template_version"] == PROMPT_TEMPLATE_VERSION
    assert "16:9" in result["prompt"]
    assert "Summary Board" in result["prompt"]
    assert "不作为作画生产基准" in result["prompt"]
    assert "极小缩略预览" in result["prompt"]
    assert "不要把完整三视图" in result["prompt"]
    assert "银色吊坠" in result["prompt"]
    assert "脸部崩坏" in result["negative_prompt"]


def test_character_sheet_16_9_prompt_has_director_friendly_layout():
    character = SimpleNamespace(
        name="设定板角色",
        role="supporting",
        appearance="短发",
        costume_hint="风衣",
        signature_items='["吊坠"]',
        expressions='["冷静"]',
        poses='[]',
        visual_consistency="发型和吊坠保持一致",
    )
    result = build_portrait_prompt(character=character, preset="character_sheet_16_9")
    assert result["preset"] == "character_sheet_16_9"
    assert "左侧约 34%" in result["prompt"]
    assert "正面/侧面/背面三视图" in result["prompt"]
    assert "不要生成大段说明文字" in result["prompt"]


def test_prompt_builder_accepts_visual_profile_overrides():
    character = SimpleNamespace(
        name="测试角色",
        role="supporting",
        age_range="",
        appearance="默认外貌",
        costume_hint="默认服装",
        personality="",
        signature_items="[]",
        expressions="[]",
        poses="[]",
        tags="[]",
        visual_consistency="",
    )

    result = build_portrait_prompt(
        character=character,
        preset="expression_pack",
        visual_profile={
            "face": "尖下巴，蓝色眼睛",
            "expression_set": ["微笑", "哭泣"],
            "negative_constraints": ["换发型"],
        },
    )

    assert "尖下巴，蓝色眼睛" in result["prompt"]
    assert "微笑、哭泣" in result["prompt"]
    assert "换发型" in result["negative_prompt"]
    assert result["visual_profile_snapshot"]["face"] == "尖下巴，蓝色眼睛"


def test_expression_grid_prompt_is_cutting_friendly_and_has_preset_negative_rules():
    character = SimpleNamespace(
        name="测试角色",
        role="supporting",
        age_range="",
        appearance="银色短发，绿色眼睛",
        costume_hint="黑色夹克",
        personality="",
        signature_items="[]",
        expressions='["冷静", "大笑"]',
        poses="[]",
        tags="[]",
        visual_consistency="",
    )

    result = build_portrait_prompt(character=character, preset="expression_grid_3x3")

    assert result["preset"] == "expression_grid_3x3"
    assert "严格 3x3 grid" in result["prompt"]
    assert "便于后续按固定 3x3 网格切割" in result["prompt"]
    assert "不要在格子内生成文字标签" in result["prompt"]
    assert "非九宫格" in result["negative_prompt"]
    assert "人物跨格" in result["negative_prompt"]


def test_pose_grid_prompt_is_cutting_friendly_and_has_preset_negative_rules():
    character = SimpleNamespace(
        name="测试角色",
        role="supporting",
        age_range="",
        appearance="黑发",
        costume_hint="白色战斗服",
        personality="",
        signature_items='["长刀"]',
        expressions="[]",
        poses='["拔刀", "跳跃"]',
        tags="[]",
        visual_consistency="",
    )

    result = build_portrait_prompt(character=character, preset="pose_grid")

    assert result["preset"] == "pose_grid_3x3"
    assert "严格 3x3 grid" in result["prompt"]
    assert "每格一个完整身体动作姿态" in result["prompt"]
    assert "便于后续按固定 3x3 网格切割" in result["prompt"]
    assert "动作融合" in result["negative_prompt"]
    assert "肢体缺失" in result["negative_prompt"]


def test_key_visual_and_headshot_presets_have_distinct_intent():
    character = SimpleNamespace(
        name="测试角色",
        role="supporting",
        age_range="",
        appearance="蓝眼睛，短发",
        costume_hint="黑色制服",
        personality="",
        signature_items="[]",
        expressions="[]",
        poses="[]",
        tags="[]",
        visual_consistency="",
    )

    key_visual = build_portrait_prompt(character=character, preset="key_visual")
    headshot = build_portrait_prompt(character=character, preset="portrait")

    assert key_visual["preset"] == "key_visual"
    assert "宣传立绘 Key Visual" in key_visual["prompt"]
    assert "不能作为修改三视图比例" in key_visual["prompt"]
    assert headshot["preset"] == "headshot_icon"
    assert "头像/半身图标" in headshot["prompt"]
    assert "全身图" in headshot["negative_prompt"]


def test_prompt_builder_includes_character_bible_fields():
    character = SimpleNamespace(
        name="测试角色",
        role="supporting",
        age_range="",
        appearance="黑发",
        costume_hint="黑色制服",
        personality="",
        signature_items="[]",
        expressions="[]",
        poses="[]",
        tags="[]",
        visual_consistency="",
        identity_json='{"organization":"灰塔","position":"情报商","logline":"用情报交换命运"}',
        motivation_json='{"desire":"找到失踪妹妹","fear":"被组织抹除"}',
        speech_json='{"tone":"低声、克制"}',
        behavior_json='{"never_do":"不会无理由背叛交易"}',
        ability_json='{"skills":"密码破译"}',
    )

    result = build_portrait_prompt(character=character, preset="main_portrait")

    assert "灰塔" in result["prompt"]
    assert "情报商" in result["prompt"]
    assert "找到失踪妹妹" in result["prompt"]
    assert "不会无理由背叛交易" in result["prompt"]


def test_normalize_preset_rejects_unknown_value():
    with pytest.raises(ValueError):
        normalize_preset("unknown")
