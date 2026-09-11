"""强度语义测试：subtle / balanced / strong 必须产生真实的注入差异。

此前强度只是写进标题的一个词，三种取值在提示词里完全等价；
这里锁定"规则条数、示例条数、优先级指令"三处差异，防止回归。
"""
from app.services.creative_project.writing_style import (
    INTENSITY_POLICY,
    build_style_prompt_block,
    intensity_policy,
)


def _profile(intensity: str, rules: int = 30, examples: int = 6) -> dict:
    return {
        "name": "测试档案",
        "version": 3,
        "checksum": "a" * 32,
        "intensity": intensity,
        "prompt_contract": {
            "rules": [f"规则{i}" for i in range(rules)],
            "new_examples": [f"示例{i}" for i in range(examples)],
        },
    }


class TestIntensityPolicy:
    def test_policy_scales_monotonically(self):
        assert (
            INTENSITY_POLICY["subtle"]["max_rules"]
            < INTENSITY_POLICY["balanced"]["max_rules"]
            < INTENSITY_POLICY["strong"]["max_rules"]
        )
        assert (
            INTENSITY_POLICY["subtle"]["max_examples"]
            < INTENSITY_POLICY["strong"]["max_examples"]
        )

    def test_unknown_intensity_falls_back_to_balanced(self):
        assert intensity_policy(None) == INTENSITY_POLICY["balanced"]
        assert intensity_policy("") == INTENSITY_POLICY["balanced"]
        assert intensity_policy("wild") == INTENSITY_POLICY["balanced"]

    def test_intensity_lookup_is_case_insensitive(self):
        assert intensity_policy("STRONG") == INTENSITY_POLICY["strong"]


class TestStylePromptBlock:
    def test_block_scales_rules_and_examples(self):
        subtle = build_style_prompt_block(_profile("subtle"))
        balanced = build_style_prompt_block(_profile("balanced"))
        strong = build_style_prompt_block(_profile("strong"))

        assert subtle.count("- 规则") == INTENSITY_POLICY["subtle"]["max_rules"]
        assert balanced.count("- 规则") == INTENSITY_POLICY["balanced"]["max_rules"]
        assert strong.count("- 规则") == INTENSITY_POLICY["strong"]["max_rules"]

        assert subtle.count("- 示例") == INTENSITY_POLICY["subtle"]["max_examples"]
        assert strong.count("- 示例") == INTENSITY_POLICY["strong"]["max_examples"]

        # 三种强度的注入文本必须互不相同（否则强度就是空语义）
        assert len({subtle, balanced, strong}) == 3

    def test_block_carries_intensity_tag_and_identity(self):
        strong = build_style_prompt_block(_profile("strong"))
        assert INTENSITY_POLICY["strong"]["tag"] in strong
        assert "测试档案" in strong
        assert "v3" in strong
        assert "aaaaaaaaaaaaaaaa" in strong  # checksum 前 16 位

    def test_block_does_not_add_extra_lines(self):
        """强度只影响条数与标签，不额外占行：T6 层预算仅 1200 字符且与技能包共用。"""
        block = build_style_prompt_block(_profile("strong"))
        header = block.split("\n", 1)[0]
        assert header.startswith("[风格档案")
        assert block.split("\n")[1].startswith("- 规则")

    def test_block_tolerates_missing_contract_fields(self):
        empty = {"name": "空档案", "version": 1, "checksum": "b" * 32, "intensity": "subtle"}
        block = build_style_prompt_block(empty)
        assert "空档案" in block
        assert "- " not in block
