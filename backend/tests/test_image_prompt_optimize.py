"""生图提示词优化的动图/视觉能力测试。

三条行为，改动前**都不成立**，每条都有对应回归：

1. `optimized` 后不再追加系统块，而系统块含多格图约束 —— 所以优化时若不把
   动图参数告诉 LLM，AI 会按单张图写，产出「高清立绘」这种描述，
   而多格图约束又因为"已优化"被丢掉 —— **两头落空**。
2. 参考图要**按顺序全传**，只传第一张会丢掉"图 2 是剖面图"这类分工信息。
3. 模型不支持视觉时**不能报错**（用户只是选了别的模型，不该因此整单失败）。
"""

from __future__ import annotations

import pytest

from app.services.ai import prompt_optimize as P


@pytest.fixture
def vision_yes(monkeypatch):
    monkeypatch.setattr(P, "_connector_supports_vision", lambda provider: True)


@pytest.fixture
def vision_no(monkeypatch):
    monkeypatch.setattr(P, "_connector_supports_vision", lambda provider: False)


def _img(n: int) -> str:
    return f"data:image/png;base64,IMG{n}"


class TestBuildUserContent:
    def test_no_images_returns_plain_text(self, vision_no):
        out = P._build_user_content("文本", [], "p")
        assert isinstance(out, str)

    def test_no_images_returns_plain_text_even_when_vision_supported(self, vision_yes):
        out = P._build_user_content("文本", None, "p")
        assert isinstance(out, str)

    def test_unsupported_vision_falls_back_to_text(self, vision_no):
        """不支持视觉时静默降级成纯文本 —— 不能抛错。"""
        out = P._build_user_content("文本", [_img(1)], "p")
        assert isinstance(out, str)
        assert out == "文本"

    def test_supported_vision_builds_multimodal_array(self, vision_yes):
        out = P._build_user_content("文本", [_img(1)], "p")
        assert isinstance(out, list)
        assert out[0] == {"type": "text", "text": "文本"}
        assert out[1]["type"] == "image_url"
        assert out[1]["image_url"]["url"] == _img(1)

    def test_multiple_images_all_passed_in_order(self, vision_yes):
        """多张按传入顺序全传 —— 只传第一张会丢掉图与图的分工信息。"""
        imgs = [_img(1), _img(2), _img(3)]
        out = P._build_user_content("文本", imgs, "p")
        assert isinstance(out, list)
        urls = [part["image_url"]["url"] for part in out[1:]]
        assert urls == imgs

    def test_caps_number_of_images(self, vision_yes):
        many = [_img(i) for i in range(20)]
        out = P._build_user_content("文本", many, "p")
        assert len(out) - 1 == P.MAX_REFERENCE_IMAGES

    def test_blanks_and_non_strings_are_dropped(self, vision_yes):
        out = P._build_user_content("文本", ["", "  ", None, 123, _img(9)], "p")
        assert isinstance(out, list)
        assert [p["image_url"]["url"] for p in out[1:]] == [_img(9)]


class TestMotionGifSystemPrompt:
    @pytest.mark.parametrize("rows,cols,cells", [(2, 4, 8), (4, 4, 16), (1, 4, 4)])
    def test_mentions_grid_and_continuity(self, rows, cols, cells):
        """动图系统提示词必须同时说清「分几格」和「这几格是连续的一段」。"""
        text = P.MOTION_GIF_OPTIMIZE_SYSTEM.format(
            rows=rows,
            cols=cols,
            cells=cells,
            motion_label="相机环绕",
            motion_hint="背景横移",
        )
        assert f"{rows} 行 × {cols} 列" in text
        assert "连续动作" in text
        assert "不得在换行处重新开始" in text

    def test_uses_motion_hint_not_generic_text(self):
        """写法提示要按动效类型给 —— 四类不能互相照抄。"""
        text = P.MOTION_GIF_OPTIMIZE_SYSTEM.format(
            rows=2, cols=4, cells=8, motion_label="表情包", motion_hint="机位完全锁死"
        )
        assert "表情包" in text
        assert "机位完全锁死" in text

    def test_static_system_prompt_stays_unchanged(self):
        """静态图的 system prompt 不能被动图改动污染（不给 motion_gif 时行为一致）。"""
        assert "frame sheet" not in P.IMAGE_PROMPT_OPTIMIZE_SYSTEM
        assert "多格图" not in P.IMAGE_PROMPT_OPTIMIZE_SYSTEM


class TestOptimizeCarriesMotionParams:
    """端到端（不调模型）：确认参数真的进到了 system prompt 与重发载荷里。"""

    @staticmethod
    def _sys(captured: dict) -> str:
        # LLMMessage 是 dataclass，不是 dict
        return captured["messages"][0].content

    @staticmethod
    def _user(captured: dict):
        return captured["messages"][1].content

    @pytest.mark.asyncio
    async def test_motion_params_reach_llm(self, monkeypatch, vision_no):
        captured: dict = {}

        class FakeAI:
            def is_loaded(self):
                return True

            async def chat(self, **kwargs):
                captured.update(kwargs)
                return type("R", (), {"success": True, "content": "优化后的提示词", "error": None})()

        monkeypatch.setattr(P, "get_ai_service", lambda: FakeAI())

        result = await P.optimize_image_prompt(
            prompt="做一个青瓷茶壶的环绕动图",
            motion_gif={"motion_kind": "orbit", "rows": 2, "cols": 4, "cells": 8},
        )
        assert result["optimized_prompt"] == "优化后的提示词"

        system = self._sys(captured)
        assert "frame sheet" in system
        assert "2 行 × 4 列" in system
        # 动效写法提示应来自 motion_prompt（背景横移是环绕类专属）
        assert "背景" in system

        user_text = self._user(captured)
        assert isinstance(user_text, str)
        assert "多格图" in user_text

    @pytest.mark.asyncio
    async def test_no_motion_params_keeps_static_behavior(self, monkeypatch, vision_no):
        """不给 motion_gif → system prompt 与接入前完全一致（向后兼容）。"""
        captured: dict = {}

        class FakeAI:
            def is_loaded(self):
                return True

            async def chat(self, **kwargs):
                captured.update(kwargs)
                return type("R", (), {"success": True, "content": "X", "error": None})()

        monkeypatch.setattr(P, "get_ai_service", lambda: FakeAI())

        await P.optimize_image_prompt(prompt="一只猫")
        assert self._sys(captured) == P.IMAGE_PROMPT_OPTIMIZE_SYSTEM
        assert isinstance(self._user(captured), str)

    @pytest.mark.asyncio
    async def test_unknown_motion_kind_does_not_crash(self, monkeypatch, vision_no):
        """未知动效类型不能整单失败 —— 降级成"按用户的动作描述"。"""
        captured: dict = {}

        class FakeAI:
            def is_loaded(self):
                return True

            async def chat(self, **kwargs):
                captured.update(kwargs)
                return type("R", (), {"success": True, "content": "X", "error": None})()

        monkeypatch.setattr(P, "get_ai_service", lambda: FakeAI())

        result = await P.optimize_image_prompt(
            prompt="x",
            motion_gif={"motion_kind": "不存在的类型", "rows": 2, "cols": 4, "cells": 8},
        )
        assert result["success"] if "success" in result else result["optimized_prompt"] == "X"

    @pytest.mark.asyncio
    async def test_retry_payload_records_image_count_not_images(
        self, monkeypatch, vision_yes
    ):
        """重发载荷只记张数 —— base64 动辄几十万字符，塞进去会炸日志/DB。"""
        import app.services.ai.prompt_optimize as mod

        captured: dict = {}

        class FakeAI:
            def is_loaded(self):
                return True

            async def chat(self, **kwargs):
                captured.update(kwargs)
                return type("R", (), {"success": True, "content": "X", "error": None})()

        monkeypatch.setattr(mod, "get_ai_service", lambda: FakeAI())

        real_ctx = mod.ai_call_context

        def spy_ctx(**kwargs):
            captured["retry_payload"] = kwargs.get("retry_payload")
            return real_ctx(**{k: v for k, v in kwargs.items() if k != "retry_payload"})

        monkeypatch.setattr(mod, "ai_call_context", spy_ctx)

        await mod.optimize_image_prompt(
            prompt="一只猫",
            provider="p",
            reference_images=[_img(1), _img(2)],
        )
        payload = captured.get("retry_payload") or {}
        assert payload.get("reference_image_count") == 2
        assert "reference_images" not in payload
