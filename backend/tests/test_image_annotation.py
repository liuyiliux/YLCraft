"""图生图「画面批注」服务层测试。

重点覆盖三类回归：
1. **不批注时行为完全不变**——这是接入的前提，任何"空批注也往 prompt 里塞东西"的实现
   都会让所有既有生图请求悄悄改变效果。
2. 坐标归一化与非法输入的报错边界。
3. 批注原文不进日志/血缘摘要。
"""

from __future__ import annotations

import pytest

from app.services.image_annotation import (
    MARKED_IMAGE_HINT,
    MAX_ANNOTATIONS,
    MAX_COMMENT_LEN,
    MAX_INSTRUCTIONS_LEN,
    SCHEMA_VERSION,
    AnnotationError,
    annotation_payload_summary,
    build_effective_prompt,
    compose_annotation_prompt,
    normalize_annotations,
)


def _rect(x1: float, y1: float, x2: float, y2: float) -> dict[str, float]:
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}


class TestNoAnnotationKeepsPromptUntouched:
    """无批注必须等于"什么都没发生"。"""

    @pytest.mark.parametrize(
        "payload",
        [None, [], {}, {"annotations": []}, {"annotations": None}],
    )
    def test_empty_payloads_are_no_ops(self, payload):
        assert normalize_annotations(payload) == []
        assert compose_annotation_prompt([], base_prompt="原提示词") == ""

    def test_box_without_comment_is_dropped_not_rejected(self):
        """只框不写话 = 还没提要求，不该让整次提交失败。"""
        result = normalize_annotations(
            [{"id": "1", "comment": "   ", "rectangle": _rect(0.1, 0.1, 0.5, 0.5)}]
        )
        assert result == []

    def test_all_comments_empty_yields_empty_prompt(self):
        result = normalize_annotations(
            [{"id": "1", "comment": "", "rectangle": _rect(0, 0, 1, 1)}]
        )
        assert result == []
        assert compose_annotation_prompt(result, base_prompt="原提示词") == ""


class TestCoordinateNormalization:
    def test_out_of_range_is_clipped_not_rejected(self):
        """拖框到边缘外一点点是常态，夹取比报错更符合直觉。"""
        result = normalize_annotations(
            [{"comment": "a", "rectangle": _rect(-0.2, -0.1, 1.4, 1.3)}]
        )
        assert result[0]["rectangle"] == {"x1": 0.0, "y1": 0.0, "x2": 1.0, "y2": 1.0}

    def test_reversed_corners_are_reordered(self):
        """从右下往左上拖也会产生 x2<x1 的框，这里统一成 x1<x2。"""
        result = normalize_annotations(
            [{"comment": "a", "rectangle": _rect(0.8, 0.9, 0.2, 0.3)}]
        )
        assert result[0]["rectangle"] == {"x1": 0.2, "y1": 0.3, "x2": 0.8, "y2": 0.9}

    def test_zero_area_box_is_rejected(self):
        """退化成一条线的框没有意义，必须报错而不是静默通过。"""
        with pytest.raises(AnnotationError, match="范围为空"):
            normalize_annotations([{"comment": "a", "rectangle": _rect(0.5, 0.2, 0.5, 0.8)}])
        with pytest.raises(AnnotationError, match="范围为空"):
            normalize_annotations([{"comment": "a", "rectangle": _rect(0.2, 0.5, 0.8, 0.5)}])

    @pytest.mark.parametrize("bad", ["0.5", None, True, {"a": 1}])
    def test_non_numeric_coordinate_is_rejected(self, bad):
        with pytest.raises(AnnotationError):
            normalize_annotations(
                [{"comment": "a", "rectangle": _rect(bad, 0.1, 0.5, 0.8)}]
            )

    def test_missing_rectangle_is_rejected(self):
        with pytest.raises(AnnotationError, match="rectangle"):
            normalize_annotations([{"comment": "a"}])

    def test_nan_coordinate_is_rejected(self):
        with pytest.raises(AnnotationError):
            normalize_annotations(
                [{"comment": "a", "rectangle": _rect(float("nan"), 0.1, 0.5, 0.8)}]
            )

    def test_accepts_wrapped_object_form(self):
        """前端按 schema 包一层 annotations 也要能吃下。"""
        result = normalize_annotations(
            {"annotations": [{"comment": "a", "rectangle": _rect(0.1, 0.1, 0.2, 0.2)}]}
        )
        assert len(result) == 1


class TestLimits:
    def test_too_many_annotations_is_rejected(self):
        payload = [
            {"comment": f"意见{i}", "rectangle": _rect(0.1, 0.1, 0.2, 0.2)}
            for i in range(MAX_ANNOTATIONS + 1)
        ]
        with pytest.raises(AnnotationError, match="最多"):
            normalize_annotations(payload)

    def test_oversized_comment_is_rejected(self):
        with pytest.raises(AnnotationError, match="超过"):
            normalize_annotations(
                [{"comment": "长" * (MAX_COMMENT_LEN + 1), "rectangle": _rect(0.1, 0.1, 0.2, 0.2)}]
            )


class TestDeduplication:
    def test_identical_annotation_at_identical_place_collapses(self):
        """用户双击误加了两条一样的，不该让 prompt 里出现两遍。"""
        result = normalize_annotations(
            [
                {"comment": "同样的意见", "rectangle": _rect(0.1, 0.1, 0.4, 0.4)},
                {"comment": "同样的意见", "rectangle": _rect(0.1, 0.1, 0.4, 0.4)},
            ]
        )
        assert len(result) == 1

    def test_same_comment_different_place_is_kept(self):
        """同一句意见圈在不同位置是两件不同的事，必须都留着。"""
        result = normalize_annotations(
            [
                {"comment": "改这里", "rectangle": _rect(0.1, 0.1, 0.2, 0.2)},
                {"comment": "改这里", "rectangle": _rect(0.6, 0.6, 0.8, 0.8)},
            ]
        )
        assert len(result) == 2


class TestPromptComposition:
    def _one(self) -> list[dict]:
        return normalize_annotations(
            [{"comment": "这只手多了一根手指", "rectangle": _rect(0.1, 0.2, 0.4, 0.6)}]
        )

    def test_position_is_described_in_words_and_percent(self):
        """同时给构图语义和百分比锚点，模型才不会找错地方。"""
        prompt = compose_annotation_prompt(self._one(), base_prompt="一个女孩")
        assert "这只手多了一根手指" in prompt
        assert "%" in prompt
        # 主提示词不会被复制进追加段——那段只承载批注，避免整段重复占用上下文。
        assert "一个女孩" not in prompt

    def test_top_left_and_bottom_right_are_distinguished(self):
        tl = compose_annotation_prompt(
            normalize_annotations([{"comment": "x", "rectangle": _rect(0.05, 0.05, 0.3, 0.3)}])
        )
        br = compose_annotation_prompt(
            normalize_annotations([{"comment": "x", "rectangle": _rect(0.7, 0.7, 0.95, 0.95)}])
        )
        assert "上左" in tl
        assert "下右" in br

    def test_duplicate_with_base_prompt_is_not_repeated(self):
        """主提示词里已经写了的话不再重复强调，避免挤占预算。"""
        annotations = self._one()
        prompt = compose_annotation_prompt(annotations, base_prompt="一个女孩，这只手多了一根手指")
        assert prompt == ""

    def test_numbers_are_sequential_and_one_based(self):
        annotations = normalize_annotations(
            [
                {"comment": "第一条", "rectangle": _rect(0.1, 0.1, 0.2, 0.2)},
                {"comment": "第二条", "rectangle": _rect(0.5, 0.5, 0.7, 0.7)},
            ]
        )
        prompt = compose_annotation_prompt(annotations)
        assert "1. " in prompt
        assert "2. " in prompt

    def test_result_respects_total_length_budget(self):
        """超长批注不能顶破总长度上限。"""
        annotations = normalize_annotations(
            [
                {"comment": "长" * MAX_COMMENT_LEN, "rectangle": _rect(0.1, 0.1, 0.2, 0.2)}
                for _ in range(20)
            ]
        )
        prompt = compose_annotation_prompt(annotations)
        assert 0 < len(prompt) <= MAX_INSTRUCTIONS_LEN


class TestPrivacyOfSummary:
    """批注原文常含私人备注，不能借日志/血缘这条路被复制走。"""

    def test_summary_excludes_comment_text(self):
        secret = "这是我的私人备注不要外传"
        annotations = normalize_annotations(
            [{"comment": secret, "rectangle": _rect(0.1, 0.1, 0.2, 0.2)}]
        )
        summary = annotation_payload_summary(annotations)
        assert secret not in str(summary)
        assert summary["count"] == 1
        assert summary["schema_version"] == SCHEMA_VERSION

    def test_summary_of_empty_is_still_well_formed(self):
        summary = annotation_payload_summary([])
        assert summary["count"] == 0
        assert summary["rects"] == []


class TestEndpointContract:
    """`POST /images/generate` 的行为契约，重点是**坏请求不能被吞成生成失败**。"""

    def _build(self, monkeypatch, result=None):
        from fastapi import HTTPException
        from app.api.v1 import images as M

        captured: dict = {}

        class _FakeManager:
            def is_loaded(self):
                return True

            async def generate_image(self, req):
                captured["prompt"] = req.prompt
                return result

        monkeypatch.setattr(M, "get_ai_service", lambda: _FakeManager())
        return M, HTTPException, captured

    class _FailedResult:
        """构造一个必然走失败分支的结果，避免测试依赖真实供应商。"""

        success = False
        error = "boom"
        status = "failed"
        task_id = ""
        provider = ""
        model = ""
        urls = []
        url = None
        local_path = None
        all_local_paths = []
        latency_ms = 0
        seed = None
        progress = 0
        diagnostics = None

    @pytest.mark.asyncio
    async def test_invalid_annotation_raises_400_not_generation_failure(self, monkeypatch):
        """批注不合法属于请求错误，必须是 HTTP 400。

        端点的 try 会把所有异常转成 `ImageResponse(success=False)`，那表示「生成失败」。
        如果校验留在 try 内部，外部 Agent（ylk_ Key）就无法区分「我该改请求」和
        「供应商挂了」，只会反复重试一个永远不会成功的请求。
        """
        M, HTTPException, captured = self._build(monkeypatch, result=self._FailedResult())

        req = M.ImageGenerateRequest(
            prompt="原提示词",
            annotations=[{"comment": "a", "rectangle": _rect(0.5, 0.2, 0.5, 0.8)}],
        )
        with pytest.raises(HTTPException) as excinfo:
            await M.generate_image(req, principal=None, session=None)
        assert excinfo.value.status_code == 400
        # 关键：必须在调用供应商**之前**就拒掉，不能白白花钱。
        assert "prompt" not in captured

    @pytest.mark.asyncio
    async def test_absent_annotations_keep_prompt_byte_identical(self, monkeypatch):
        """回归红线：不传批注时，送去模型的 prompt 必须与原来一字不差。"""
        M, _HTTPException, captured = self._build(monkeypatch, result=self._FailedResult())

        req = M.ImageGenerateRequest(prompt="ORIGINAL")
        await M.generate_image(req, principal=None, session=None)
        assert captured["prompt"] == "ORIGINAL"

    @pytest.mark.asyncio
    async def test_annotations_are_appended_to_prompt(self, monkeypatch):
        M, _HTTPException, captured = self._build(monkeypatch, result=self._FailedResult())

        req = M.ImageGenerateRequest(
            prompt="ORIGINAL",
            annotations=[
                {"comment": "这只手多了一根手指", "rectangle": _rect(0.1, 0.2, 0.4, 0.6)}
            ],
        )
        await M.generate_image(req, principal=None, session=None)
        assert captured["prompt"].startswith("ORIGINAL")
        assert "这只手多了一根手指" in captured["prompt"]

    @pytest.mark.asyncio
    async def test_only_unwritten_boxes_leave_prompt_untouched(self, monkeypatch):
        """只框没写字不应改变 prompt，也不应报错。"""
        M, _HTTPException, captured = self._build(monkeypatch, result=self._FailedResult())

        req = M.ImageGenerateRequest(
            prompt="ORIGINAL",
            annotations=[{"comment": "", "rectangle": _rect(0.1, 0.1, 0.5, 0.5)}],
        )
        await M.generate_image(req, principal=None, session=None)
        assert captured["prompt"] == "ORIGINAL"

    def test_retry_payload_carries_annotations(self, monkeypatch):
        """重发必须带上批注：漏了会重生成一张"没带批注"的图，且无处查因。"""
        M, _HTTPException, _captured = self._build(monkeypatch, result=self._FailedResult())
        req = M.ImageGenerateRequest(
            prompt="ORIGINAL",
            annotations=[{"comment": "改这里", "rectangle": _rect(0.1, 0.1, 0.3, 0.3)}],
        )
        payload = M._image_retry_payload(req)
        assert len(payload["annotations"]) == 1

    def test_retry_payload_defaults_to_empty_annotations(self, monkeypatch):
        """旧载荷没有这个字段时补空列表，保证重发链路读键不炸。"""
        M, _HTTPException, _captured = self._build(monkeypatch, result=self._FailedResult())
        payload = M._image_retry_payload(M.ImageGenerateRequest(prompt="ORIGINAL"))
        assert payload["annotations"] == []


class TestMarkedReferenceImage:
    """带框标注图：框被渲染成一张**额外参考图**，随原图一起发给模型。

    动机：只报中心点坐标时，「圈一小撮头发」和「整头改色」生成的指令几乎一样，
    模型分不出于是有时只改一撮、有时整张脸被重画。画出来就没有这个歧义——
    这是 Gemini 图像标记工具与 Set-of-Mark 那类方法的核心思路。
    """

    _ANNOT = [
        {"comment": "改为红色", "rectangle": {"x1": 0.4, "y1": 0.0, "x2": 0.6, "y2": 0.4}}
    ]

    def _req(self, M, **kwargs):
        params = {
            "prompt": "原始提示词",
            "annotations": self._ANNOT,
            "reference_images": ["data:image/png;base64,ORIGINAL"],
        }
        params.update(kwargs)
        return M.ImageGenerateRequest(**params)

    @pytest.mark.asyncio
    async def test_marked_flag_explains_image_and_forbids_drawing_boxes(self, monkeypatch):
        M, _HTTPException, captured = TestEndpointContract()._build(
            monkeypatch, result=TestEndpointContract._FailedResult
        )
        await M.generate_image(
            self._req(M, annotation_marked_reference=True),
            principal=None,
            session=None,
        )
        prompt = captured["prompt"]
        assert "原始提示词" in prompt
        # 必须明确「不要把框画进结果」——不说的话模型会把青框当成画面内容。
        assert "不要把框线和编号画进结果" in prompt
        # 说明要排在意见清单**之前**：模型先知道去哪儿找，再读每条意见。
        assert prompt.index("不要把框线") < prompt.index("改为红色")

    @pytest.mark.asyncio
    async def test_text_mode_does_not_mention_marked_image(self, monkeypatch):
        """切到「只用文字」时不应再解释标注图，否则提示词与实际参考图不符。"""
        M, _HTTPException, captured = TestEndpointContract()._build(
            monkeypatch, result=TestEndpointContract._FailedResult
        )
        await M.generate_image(
            self._req(M, annotation_marked_reference=False),
            principal=None,
            session=None,
        )
        assert "不要把框线" not in captured["prompt"]
        assert "改为红色" in captured["prompt"]

    @pytest.mark.asyncio
    async def test_marked_flag_without_annotations_is_a_no_op(self, monkeypatch):
        """回归红线：没有批注却开着 marked 开关，不应往提示词里塞任何标注说明。"""
        M, _HTTPException, captured = TestEndpointContract()._build(
            monkeypatch, result=TestEndpointContract._FailedResult
        )
        req = M.ImageGenerateRequest(prompt="原始提示词", annotation_marked_reference=True)
        await M.generate_image(req, principal=None, session=None)
        assert captured["prompt"] == "原始提示词"

    def test_retry_payload_keeps_marked_flag(self, monkeypatch):
        """重发必须带上开关：标注图虽在 reference_images 里，但提示词说明靠它触发。

        丢了它，重发会生成一张把青框画进画面的图，而用户完全不知道为什么。
        """
        M, _HTTPException, _captured = TestEndpointContract()._build(
            monkeypatch, result=TestEndpointContract._FailedResult
        )
        payload = M._image_retry_payload(
            self._req(M, annotation_marked_reference=True)
        )
        assert payload["annotation_marked_reference"] is True

    def test_retry_payload_defaults_marked_flag_to_false(self, monkeypatch):
        M, _HTTPException, _captured = TestEndpointContract()._build(
            monkeypatch, result=TestEndpointContract._FailedResult
        )
        payload = M._image_retry_payload(
            M.ImageGenerateRequest(prompt="原始提示词")
        )
        assert payload["annotation_marked_reference"] is False


class TestAnnotationNumbering:
    """编号必须与图上角标一致——否则模型会把意见安到错误的框上。

    历史 bug：提示词用 `enumerate` 编号，而「只框没写字」的批注会被过滤掉，
    于是图上的「第 2 个角标」与提示词里的「第 2 条意见」错位一格。
    """

    def test_numbering_skips_empty_comments(self):
        raw = [
            {"comment": "改成红色", "rectangle": _rect(0.1, 0.1, 0.2, 0.2)},
            {"comment": "", "rectangle": _rect(0.3, 0.3, 0.4, 0.4)},  # 中间的空框
            {"comment": "改成蓝色", "rectangle": _rect(0.5, 0.5, 0.6, 0.6)},
        ]
        kept = normalize_annotations(raw)
        assert [item["comment"] for item in kept] == ["改成红色", "改成蓝色"]
        # 空框不占号，所以两条有效批注是 1 和 2，不是 1 和 3。
        assert [item["number"] for item in kept] == [1, 2]

    def test_prompt_uses_assigned_numbers_not_enumeration(self):
        raw = [
            {"comment": "改成红色", "rectangle": _rect(0.1, 0.1, 0.2, 0.2)},
            {"comment": "", "rectangle": _rect(0.3, 0.3, 0.4, 0.4)},
            {"comment": "改成蓝色", "rectangle": _rect(0.5, 0.5, 0.6, 0.6)},
        ]
        prompt = compose_annotation_prompt(normalize_annotations(raw))
        assert "1. " in prompt and "2. " in prompt
        assert "3. " not in prompt  # 不能出现被跳过的第 3 号

    def test_numbering_survives_dedup(self):
        """去重发生在编号之前，否则被去掉的那条会留一个空洞号。"""
        raw = [
            {"comment": "同样的意见", "rectangle": _rect(0.1, 0.1, 0.2, 0.2)},
            {"comment": "同样的意见", "rectangle": _rect(0.1, 0.1, 0.2, 0.2)},
            {"comment": "另一条", "rectangle": _rect(0.5, 0.5, 0.6, 0.6)},
        ]
        kept = normalize_annotations(raw)
        assert [item["number"] for item in kept] == [1, 2]

    def test_summary_numbers_do_not_enter_the_prompt(self):
        """摘要（进日志/血缘）不参与提示词拼装，两者互不干扰。"""
        kept = normalize_annotations(
            [{"comment": "x", "rectangle": _rect(0.1, 0.1, 0.2, 0.2)}]
        )
        assert "number" not in annotation_payload_summary(kept)


class TestEffectivePromptBuilder:
    """`build_effective_prompt` 是预览与生成的**共同实现**。

    一旦这里和端点各写各的，用户照着预览调半天、生成出来却不一样——这是本组测试
    要守住的最主要风险。
    """

    _ANNOT = [
        {"comment": "改为红色", "rectangle": {"x1": 0.4, "y1": 0.0, "x2": 0.6, "y2": 0.4}}
    ]

    def test_block_order_puts_hint_before_annotations(self):
        """标注图说明排在意见清单之前：模型先知道去哪儿找，再读每条意见。"""
        built = build_effective_prompt(
            base_prompt="原始提示词",
            annotations=self._ANNOT,
            marked_reference=True,
        )
        keys = [block["key"] for block in built["blocks"]]
        assert keys == ["marked_hint", "base", "annotations"]
        assert built["prompt"].index("不要把框线") < built["prompt"].index("改为红色")

    def test_system_added_flags_only_machine_written_blocks(self):
        """必须能区分「用户自己写的」与「系统加的」——否则用户会把默认文案当成自己写的。"""
        built = build_effective_prompt(
            base_prompt="原始提示词",
            annotations=self._ANNOT,
            marked_reference=True,
        )
        assert "base" not in built["system_added"]
        assert set(built["system_added"]) == {"marked_hint", "annotations"}

    def test_empty_hint_disables_the_block_entirely(self):
        """`""` 表示用户主动关掉这句，与「用默认」必须能区分开。"""
        built = build_effective_prompt(
            base_prompt="原始提示词",
            annotations=self._ANNOT,
            marked_reference=True,
            marked_hint="",
        )
        assert "marked_hint" not in [b["key"] for b in built["blocks"]]
        assert "不要把框线" not in built["prompt"]
        # 关掉说明后，批注段仍要保留。
        assert "改为红色" in built["prompt"]

    def test_custom_hint_replaces_default(self):
        built = build_effective_prompt(
            base_prompt="原始提示词",
            annotations=self._ANNOT,
            marked_reference=True,
            marked_hint="只改框内，别动其他部分",
        )
        assert "只改框内，别动其他部分" in built["prompt"]
        assert "不要把框线" not in built["prompt"]

    def test_hint_not_added_without_marked_reference(self):
        """没发标注图就别解释它——提示词与实际参考图必须对得上。"""
        built = build_effective_prompt(
            base_prompt="原始提示词",
            annotations=self._ANNOT,
            marked_reference=False,
        )
        assert "marked_hint" not in [b["key"] for b in built["blocks"]]

    def test_hint_not_added_without_annotations(self):
        built = build_effective_prompt(
            base_prompt="原始提示词",
            annotations=[],
            marked_reference=True,
        )
        assert built["prompt"] == "原始提示词"

    def test_empty_prompt_without_annotations_yields_empty_string(self):
        """既没提示词又没批注：返回空串，交给上层做「无从下手」的提示。"""
        built = build_effective_prompt(base_prompt="", annotations=[])
        assert built["prompt"] == ""
        assert built["blocks"] == []


class TestPromptPreviewEndpoint:
    """`POST /images/prompt-preview`：只拼装，不调模型、不产生费用。"""

    def _run(self, monkeypatch, **kwargs):
        import asyncio

        from app.api.v1 import images as M

        async def _go():
            return await M.preview_image_prompt(M.ImagePromptPreviewRequest(**kwargs))

        return asyncio.run(_go())

    def test_returns_full_prompt_with_blocks(self, monkeypatch):
        resp = self._run(
            monkeypatch,
            prompt="原始提示词",
            annotations=[
                {"comment": "改为红色", "rectangle": {"x1": 0.4, "y1": 0.0, "x2": 0.6, "y2": 0.4}}
            ],
            annotation_marked_reference=True,
        )
        assert resp.success is True
        assert "原始提示词" in resp.prompt
        assert "改为红色" in resp.prompt
        assert "不要把框线" in resp.prompt
        assert set(resp.system_added) == {"marked_hint", "annotations"}
        # 供前端「恢复默认」用
        assert resp.default_hint_text == MARKED_IMAGE_HINT

    def test_preview_matches_generate_byte_for_byte(self, monkeypatch):
        """核心红线：预览出来的必须和真发出去的一字不差。

        两边都调 build_effective_prompt，所以这里锁的是「端点有没有绕过它自己拼」。
        """
        import asyncio

        from app.api.v1 import images as M

        captured = {}

        class _R:
            success = False
            error = "stop"
            status = "failed"
            task_id = ""
            provider = ""
            model = ""
            urls = []
            url = None
            local_path = None
            all_local_paths = []
            latency_ms = 0
            seed = None
            progress = 0
            diagnostics = None

        class _Mgr:
            def is_loaded(self):
                return True

            async def generate_image(self, req):
                captured["prompt"] = req.prompt
                return _R()

        monkeypatch.setattr(M, "get_ai_service", lambda: _Mgr())

        annot = [
            {"comment": "改为红色", "rectangle": {"x1": 0.4, "y1": 0.0, "x2": 0.6, "y2": 0.4}}
        ]

        preview = asyncio.run(
            M.preview_image_prompt(
                M.ImagePromptPreviewRequest(
                    prompt="原始提示词",
                    annotations=annot,
                    annotation_marked_reference=True,
                )
            )
        )
        asyncio.run(
            M.generate_image(
                M.ImageGenerateRequest(
                    prompt="原始提示词",
                    annotations=annot,
                    annotation_marked_reference=True,
                ),
                principal=None,
                session=None,
            )
        )
        assert preview.prompt == captured["prompt"]

    def test_invalid_annotation_is_400(self, monkeypatch):
        import asyncio

        from fastapi import HTTPException

        from app.api.v1 import images as M

        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(
                M.preview_image_prompt(
                    M.ImagePromptPreviewRequest(
                        prompt="x",
                        annotations=[
                            {"comment": "a", "rectangle": {"x1": 0.5, "y1": 0.2, "x2": 0.5, "y2": 0.8}}
                        ],
                    )
                )
            )
        assert excinfo.value.status_code == 400