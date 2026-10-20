"""动图合成与提示词构建测试。

重点锁三件事：

1. **合成不调用模型** —— ②切帧 / ③合成是"免费"的，这是把切帧从生成里拆出来的理由
2. **预览与生成共用拼装函数** —— 两份实现各写各的，预览就会与实际不一致
3. **optimized 时不再追加系统块** —— 否则会与 AI 优化结果重复甚至冲突
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from app.services.image import motion_gif, motion_prompt, slicing
from app.services.image.motion_gif_service import MotionGifService

CELL = 20


def _sheet(rows: int, cols: int, cell: int = CELL) -> Image.Image:
    """每格一个偏移的方块，用于确认帧确实按顺序取到。"""
    sheet = Image.new("RGB", (cols * cell, rows * cell), (245, 245, 245))
    draw = ImageDraw.Draw(sheet)
    index = 0
    for r in range(rows):
        for c in range(cols):
            left, top = c * cell, r * cell
            inset = 2 + (index % 3)
            draw.rectangle(
                [left + inset, top + inset, left + cell - inset, top + cell - inset],
                fill=(10 + index * 5, 20, 30),
            )
            index += 1
    return sheet


def _options(**overrides) -> motion_gif.MotionGifOptions:
    base = {
        "rows": 2,
        "cols": 4,
        "order": tuple(slicing.origin_refs(8)),
    }
    base.update(overrides)
    return motion_gif.MotionGifOptions(**base)


class TestComposeMotionGif:
    @pytest.mark.asyncio
    async def test_pingpong_doubles_minus_two_frames(self, tmp_path):
        """正放 8 帧 + 倒放中间 6 帧 = 14 帧，首尾不重复。"""
        result = await motion_gif.compose_motion_gif(
            _sheet(2, 4), None, _options(loop="pingpong"), tmp_path
        )
        assert result.frames == 14

    @pytest.mark.asyncio
    async def test_cycle_keeps_frame_count(self, tmp_path):
        result = await motion_gif.compose_motion_gif(
            _sheet(2, 4), None, _options(loop="cycle"), tmp_path
        )
        assert result.frames == 8

    @pytest.mark.asyncio
    async def test_writes_gif_and_webp(self, tmp_path):
        result = await motion_gif.compose_motion_gif(
            _sheet(2, 4), None, _options(), tmp_path
        )
        assert result.gif_path and result.gif_path.exists()
        assert result.webp_path and result.webp_path.exists()
        assert result.gif_kb > 0 and result.webp_kb > 0

    @pytest.mark.asyncio
    async def test_saves_framesheet_alongside_outputs(self, tmp_path):
        """多格图必须随产物留着：没有它就无法"改切帧"重出而不重新生成。"""
        await motion_gif.compose_motion_gif(_sheet(2, 4), None, _options(), tmp_path)
        assert (tmp_path / motion_gif.FRAMESHEET_NAME).exists()

    @pytest.mark.asyncio
    async def test_all_frames_share_one_output_size(self, tmp_path):
        """帧尺寸不一致会让播放时画面跳动，必须统一。"""
        result = await motion_gif.compose_motion_gif(
            _sheet(2, 4), None, _options(size=64), tmp_path
        )
        gif = Image.open(result.gif_path)
        assert gif.size == result.output_size

    @pytest.mark.asyncio
    async def test_rejects_empty_order(self, tmp_path):
        with pytest.raises(ValueError, match="为空"):
            await motion_gif.compose_motion_gif(
                _sheet(2, 4), None, _options(order=()), tmp_path
            )

    @pytest.mark.asyncio
    async def test_rejects_out_of_range_order(self, tmp_path):
        refs = [slicing.SliceRef({"kind": "origin", "index": 99})]
        with pytest.raises(ValueError, match="格"):
            await motion_gif.compose_motion_gif(
                _sheet(2, 4), None, _options(order=tuple(refs)), tmp_path
            )

    @pytest.mark.asyncio
    async def test_ramp_timing_starts_slow_and_ends_fast(self, tmp_path):
        """前慢后快：让观众看清起始画面。"""
        result = await motion_gif.compose_motion_gif(
            _sheet(2, 4), None, _options(loop="cycle", timing="ramp"), tmp_path
        )
        durations = result.frame_durations
        assert durations[0] > durations[-1]

    @pytest.mark.asyncio
    async def test_gif_shrinks_when_over_budget(self, tmp_path):
        """超预算必须降档，而不是交超限文件。

        用**有噪声的大图**才有意义——纯色测试图压缩后本来就极小，
        拿它断言"降档"会测不到任何东西。

        阶梯**有下限**（0.5×尺寸 / 64 色），降到那里还超预算就不降了：
        宁可交一个略超限的文件，也不交一个明显发糊的。所以预算设在
        "降档能达成"的区间。
        """
        import random

        big = Image.new("RGB", (640, 640))
        pixels = big.load()
        rng = random.Random(7)
        for y in range(640):
            for x in range(640):
                pixels[x, y] = (rng.randrange(256), rng.randrange(256), rng.randrange(256))
        roomy = await motion_gif.compose_motion_gif(
            big, None, _options(max_kb=0, size=480), tmp_path / "roomy"
        )
        tight = await motion_gif.compose_motion_gif(
            big, None, _options(max_kb=600, size=480), tmp_path / "tight"
        )
        assert tight.gif_kb < roomy.gif_kb
        assert tight.gif_kb * 1024 <= 600 * 1024 * 1.05

    @pytest.mark.asyncio
    async def test_ladder_stops_at_floor_instead_of_infinite_shrink(self, tmp_path):
        """预算不可能达成时也要正常产出，不能无限降档或报错。"""
        result = await motion_gif.compose_motion_gif(
            _sheet(2, 4), None, _options(max_kb=1, size=256), tmp_path
        )
        assert result.gif_path and result.gif_path.exists()
        # 阶梯下限是 0.5x，不会比它更小
        assert max(result.output_size) >= 128

    @pytest.mark.asyncio
    async def test_respects_size_but_never_upscales_past_source(self, tmp_path):
        """目标长边小于源图时不能反向放大（放大只会发糊）。"""
        small = await motion_gif.compose_motion_gif(
            _sheet(2, 4), None, _options(size=32), tmp_path / "small"
        )
        assert max(small.output_size) <= 32
        large = await motion_gif.compose_motion_gif(
            _sheet(2, 4), None, _options(size=64), tmp_path / "large"
        )
        assert max(large.output_size) == 64

    @pytest.mark.asyncio
    async def test_pixel_art_uses_nearest_and_no_dither(self, tmp_path):
        """像素风必须用 NEAREST：平滑滤镜会把像素网格糊掉。"""
        result = await motion_gif.compose_motion_gif(
            _sheet(2, 4), None, _options(resample="nearest", dither=False, size=64),
            tmp_path,
        )
        assert result.output_size[0] == 64


class TestSlicePreview:
    def test_rejects_asset_id_as_sheet_path(self, tmp_path):
        """回归：切帧只认**文件路径**，不认素材库的 assetId。

        踩过的坑（用户实测）：从素材库选图后切帧报
        `多格图不存在或不在允许的目录内：c475e739-da29-…`。

        根因：`AssetReferencePicker` 在 base64 模式下**只给 assetId**
        （那是给生图接口用的 —— 生图自己会解析 assetId），
        而动图的 `slice-preview` 走 `resolve_asset_file`，
        它只认文件路径与 `/api/v1/assets/download?path=` 这类地址。

        前端已改为「先查详情拿 file_path 再传」。这条测试把**后端也确实不接受
        assetId** 这个前提钉住 —— 万一以后有人把前端改回去，这里能说明原因。
        """
        svc = MotionGifService()
        with pytest.raises(FileNotFoundError):
            svc.slice_preview(
                sheet_path=Path("c475e739-da29-4351-ac88-a7420bbde700"),
                rows=4,
                cols=4,
            )

    def test_reports_expected_and_resolved_counts(self, tmp_path):
        sheet_path = tmp_path / "sheet.png"
        _sheet(2, 4).save(sheet_path)
        svc = MotionGifService()
        out = svc.slice_preview(sheet_path=sheet_path, rows=2, cols=4)
        assert out["expected_cells"] == 8
        assert out["resolved_cells"] == 8
        assert out["order_labels"] == ["原1", "原2", "原3", "原4", "原5", "原6", "原7", "原8"]

    def test_shows_gap_when_cell_dropped(self, tmp_path):
        """删格后标签必须显出缺口，用户才能核对删的是哪一格。"""
        sheet_path = tmp_path / "sheet.png"
        _sheet(2, 4).save(sheet_path)
        refs = [
            slicing.SliceRef({"kind": "origin", "index": 1}),
            slicing.SliceRef({"kind": "origin", "index": 4}),
        ]
        svc = MotionGifService()
        out = svc.slice_preview(sheet_path=sheet_path, rows=2, cols=4, order=refs)
        assert out["order_labels"] == ["原1", "原4"]

    def test_upload_without_map_raises_rather_than_silently_substituting(self, tmp_path):
        sheet_path = tmp_path / "sheet.png"
        _sheet(2, 4).save(sheet_path)
        refs = [slicing.SliceRef({"kind": "upload", "index": 1})]
        svc = MotionGifService()
        with pytest.raises(ValueError, match="不存在"):
            svc.slice_preview(sheet_path=sheet_path, rows=2, cols=4, order=refs)


class TestPreviewUrlsBustCacheOnCutChange:
    """回归：**改了切法，预览小图的 URL 必须跟着变**。

    踩过的坑（用户实测："拖动以后点确认，下面没有变化"）：

    预览目录是按**多格图路径**派生的（`sheet-<hash>`），所以每次切帧都写
    **同一个 `frame_02.png`** —— URL 一个字都不变。浏览器（和 React）
    完全有理由继续用旧位图，尽管磁盘上的文件已经是新的。

    实测症状：接口明明返回了 177×63，页面上仍是旧的 120×120；
    **手动刷新一次就正确了** —— 这正是"缓存问题"的典型特征。

    所以切帧预览的每张小图 URL 都带一个**内容指纹**：
    切法一变指纹就变，URL 随之改变，浏览器必然重新加载。
    """

    def _preview(self, sheet_path, tmp_path, grid=None):
        return MotionGifService().slice_preview(
            sheet_path=sheet_path, rows=2, cols=4, grid=grid, output_dir=tmp_path
        )

    def test_url_changes_when_grid_changes(self, tmp_path):
        sheet_path = tmp_path / "sheet.png"
        _sheet(2, 4, cell=64).save(sheet_path)
        uniform = self._preview(sheet_path, tmp_path)
        dragged = self._preview(
            sheet_path,
            tmp_path,
            slicing.SheetGrid.from_edges(2, 4, xs=[0.15, 0.5, 0.85]),
        )
        assert uniform["frame_urls"][0] != dragged["frame_urls"][0], (
            "改了切法但预览小图 URL 不变 —— 浏览器会继续用旧位图，"
            "表现为『确认切法后下面的帧没反应』"
        )

    def test_url_is_stable_for_the_same_grid(self, tmp_path):
        """同一切法必须得到同一 URL —— 否则来回切会不断产生新缓存。"""
        sheet_path = tmp_path / "sheet.png"
        _sheet(2, 4, cell=64).save(sheet_path)
        grid = slicing.SheetGrid.from_edges(2, 4, xs=[0.15, 0.5, 0.85])
        a = self._preview(sheet_path, tmp_path, grid)
        b = self._preview(sheet_path, tmp_path, grid)
        assert a["frame_urls"] == b["frame_urls"]

    def test_url_changes_when_order_changes(self, tmp_path):
        """删格/换顺序同样要换 URL（否则删掉的那格看起来还在）。"""
        sheet_path = tmp_path / "sheet.png"
        _sheet(2, 4, cell=64).save(sheet_path)
        svc = MotionGifService()
        full = svc.slice_preview(
            sheet_path=sheet_path, rows=2, cols=4,
            order=list(slicing.origin_refs(8)), output_dir=tmp_path,
        )
        fewer = svc.slice_preview(
            sheet_path=sheet_path, rows=2, cols=4,
            order=list(slicing.origin_refs(8))[:6], output_dir=tmp_path,
        )
        assert full["frame_urls"][0] != fewer["frame_urls"][0]

    def test_thumbnail_keeps_relative_width(self, tmp_path):
        """缩略图要按**同一缩放系数**缩，保住各格相对宽度。

        原来给每帧都缩到"长边 = 240"，378px 与 134px 宽的格会变成一样宽，
        拖出来的差异被抹平（用户："应该最后两个被切一半了"）。
        """
        sheet_path = tmp_path / "sheet.png"
        _sheet(2, 4, cell=64).save(sheet_path)
        grid = slicing.SheetGrid.from_edges(2, 4, xs=[0.1, 0.5, 0.9])
        out = MotionGifService().slice_preview(
            sheet_path=sheet_path, rows=2, cols=4, grid=grid, output_dir=tmp_path
        )
        cells = out["cells"]
        # 第 1 列（窄）与第 3 列（宽）的**面板上报尺寸**必须不同
        assert cells[0]["size"][0] < cells[2]["size"][0], (
            "两列原始宽度不同，但面板上报的尺寸一样 —— 差异被抹平了"
        )

    def test_url_changes_when_adjust_changes(self, tmp_path):
        """⚠️ 调色（亮度/对比度等）**必须也换 URL**。

        踩过的坑（用户实测："调帧以后预览怎么生效"）：
        第一版指纹只取"每帧尺寸 + 来源标识"，**漏了 adjust**。
        而调色**不改变尺寸** —— 调完亮度指纹一字未变、URL 完全相同，
        浏览器继续用旧图，**用户看不到任何变化**（后端其实已经重切好了）。

        这条与"改切法要换 URL"是同一类：**凡是会改变像素的输入都要进指纹**。
        """
        sheet_path = tmp_path / "sheet.png"
        _sheet(2, 4, cell=64).save(sheet_path)
        svc = MotionGifService()

        def preview(adjust=None):
            refs = [slicing.SliceRef({"kind": "origin", "index": 1})]
            if adjust:
                refs.append(slicing.SliceRef({"kind": "origin", "index": 2, "adjust": adjust}))
            else:
                refs.append(slicing.SliceRef({"kind": "origin", "index": 2}))
            return svc.slice_preview(
                sheet_path=sheet_path, rows=2, cols=4, order=refs, output_dir=tmp_path
            )

        plain = preview()
        dark = preview({"brightness": 0.4})
        assert plain["frame_urls"][1] != dark["frame_urls"][1], (
            "调了亮度但 URL 没变 —— 浏览器会用旧的缩略图，用户看不到调色效果"
        )

    def test_url_changes_when_adjust_value_changes(self, tmp_path):
        """连**数值变化**也要换 URL（0.4 → 0.5 是两种不同的像素）。"""
        sheet_path = tmp_path / "sheet.png"
        _sheet(2, 4, cell=64).save(sheet_path)
        svc = MotionGifService()

        def preview(brightness):
            refs = [
                slicing.SliceRef({"kind": "origin", "index": 1}),
                slicing.SliceRef(
                    {"kind": "origin", "index": 2, "adjust": {"brightness": brightness}}
                ),
            ]
            return svc.slice_preview(
                sheet_path=sheet_path, rows=2, cols=4, order=refs, output_dir=tmp_path
            )

        assert preview(0.4)["frame_urls"][1] != preview(0.5)["frame_urls"][1]

    def test_url_is_stable_for_same_adjust(self, tmp_path):
        """同一组调色参数重复请求，URL 必须稳定（否则每次滑滑块都重下）。"""
        sheet_path = tmp_path / "sheet.png"
        _sheet(2, 4, cell=64).save(sheet_path)
        svc = MotionGifService()

        def preview():
            refs = [
                slicing.SliceRef({"kind": "origin", "index": 1}),
                slicing.SliceRef(
                    {"kind": "origin", "index": 2, "adjust": {"brightness": 0.4, "contrast": 1.2}}
                ),
            ]
            return svc.slice_preview(
                sheet_path=sheet_path, rows=2, cols=4, order=refs, output_dir=tmp_path
            )

        assert preview()["frame_urls"] == preview()["frame_urls"]

    def test_adjust_key_order_does_not_change_fingerprint(self, tmp_path):
        """`{brightness, contrast}` 与 `{contrast, brightness}` 是同一组参数，指纹该相同。"""
        sheet_path = tmp_path / "sheet.png"
        _sheet(2, 4, cell=64).save(sheet_path)
        svc = MotionGifService()

        def preview(adjust):
            refs = [
                slicing.SliceRef({"kind": "origin", "index": 1}),
                slicing.SliceRef({"kind": "origin", "index": 2, "adjust": adjust}),
            ]
            return svc.slice_preview(
                sheet_path=sheet_path, rows=2, cols=4, order=refs, output_dir=tmp_path
            )

        a = preview({"brightness": 0.4, "contrast": 1.2})
        b = preview({"contrast": 1.2, "brightness": 0.4})
        assert a["frame_urls"] == b["frame_urls"], (
            "参数书写顺序影响了指纹 —— 同样的调色会得到不同 URL，白白失效缓存"
        )

    def test_upload_with_map_resolves(self, tmp_path):
        sheet_path = tmp_path / "sheet.png"
        _sheet(2, 4).save(sheet_path)
        upload = Image.new("RGB", (CELL, CELL), (9, 9, 9))
        refs = [
            slicing.SliceRef({"kind": "origin", "index": 1}),
            slicing.SliceRef({"kind": "upload", "index": 1}),
        ]
        svc = MotionGifService()
        out = svc.slice_preview(
            sheet_path=sheet_path, rows=2, cols=4, order=refs, uploads={1: upload}
        )
        assert out["order_labels"] == ["原1", "上传1号"]


class TestPromptBlocks:
    def test_both_langs_yield_same_block_ids(self):
        """中英两版必须结构对应，否则用户改了一版另一版不跟着变。"""
        zh = motion_prompt.build_prompt_blocks(kind="orbit", layout="2x4", lang="zh")
        en = motion_prompt.build_prompt_blocks_en(kind="orbit", layout="2x4")
        assert [b.id for b in zh] == [b.id for b in en]

    @pytest.mark.parametrize("kind", ["orbit", "character", "speed", "expression"])
    def test_every_kind_builds(self, kind):
        blocks = motion_prompt.build_prompt_blocks(
            kind=kind, layout="2x4", lang="zh", subject="主体"
        )
        assert len(blocks) == 5
        assert all(b.text.strip() for b in blocks)

    def test_continuity_block_forbids_row_restart(self):
        """禁止「每行重开一次」是实测踩出来的关键约束，不能丢。"""
        blocks = motion_prompt.build_prompt_blocks(
            kind="orbit", layout="2x4", lang="zh"
        )
        continuity = next(b for b in blocks if b.id == "continuity")
        assert "不得在每行开头重新开始" in continuity.text
        assert "第 5 格直接接着第 4 格" in continuity.text

    def test_continuity_reflects_actual_column_count(self):
        """4x4 的「第 5 格接第 4 格」必须变成「第 5 格接第 4 格」以外的实际值。"""
        blocks = motion_prompt.build_prompt_blocks(
            kind="orbit", layout="4x4", lang="zh"
        )
        continuity = next(b for b in blocks if b.id == "continuity")
        assert "第 5 格直接接着第 4 格" in continuity.text

    def test_four_kinds_have_different_motion_rules(self):
        """四类动效不能互相照抄——这是原项目的核心结论。"""
        texts = {
            kind: next(
                b for b in motion_prompt.build_prompt_blocks(
                    kind=kind, layout="2x4", lang="zh"
                ) if b.id == "motion"
            ).text
            for kind in ("orbit", "character", "speed", "expression")
        }
        assert len(set(texts.values())) == 4

    def test_grid_spec_step_degrees(self):
        assert motion_prompt.grid_spec("2x4").cells == 8
        assert motion_prompt.grid_spec("4x4").cells == 16
        # 60 度均分到 15 步
        assert round(motion_prompt.grid_spec("4x4").step_degrees, 4) == 4.0

    def test_unknown_layout_raises(self):
        with pytest.raises(ValueError, match="未知的格子排布"):
            motion_prompt.grid_spec("3x3")  # type: ignore[arg-type]

    def test_unknown_kind_raises(self):
        with pytest.raises(ValueError, match="未知的动效类型"):
            motion_prompt.motion_kind_spec("dance")  # type: ignore[arg-type]


class TestComposeFinalPrompt:
    def test_appends_enabled_blocks(self):
        blocks = motion_prompt.build_prompt_blocks(
            kind="orbit", layout="2x4", lang="zh"
        )
        full = motion_prompt.compose_final_prompt(
            user_prompt="做环绕动图", blocks=blocks
        )
        assert "做环绕动图" in full
        assert all(b.text in full for b in blocks)

    def test_disabled_blocks_are_excluded(self):
        blocks = motion_prompt.build_prompt_blocks(
            kind="orbit", layout="2x4", lang="zh"
        )
        full = motion_prompt.compose_final_prompt(
            user_prompt="做环绕动图", blocks=blocks, disabled_ids=["output"]
        )
        assert "【输出】" not in full
        assert "【任务】" in full

    def test_optimized_skips_all_blocks(self):
        """AI 优化过的提示词不再追加——否则会与优化结果重复甚至冲突。"""
        blocks = motion_prompt.build_prompt_blocks(
            kind="orbit", layout="2x4", lang="zh"
        )
        full = motion_prompt.compose_final_prompt(
            user_prompt="优化后的提示词", blocks=blocks, optimized=True
        )
        assert full == "优化后的提示词"
        assert "【任务】" not in full


class TestGenerateEndpointActuallySendsMotionRules:
    """回归：**生成接口必须真的把多格图规则拼进提示词**。

    踩过的坑（用户实测："好像没传最终提示词"）：

    动图的系统规则（"画成 2×4 共 8 格"、"相邻两格变化量相同"…）此前**只在
    前端预览弹窗里出现过** —— 前端调的是 `motion-gif/prompt-preview`，
    而真正的生成请求 `/images/generate` 只发了输入框里那两句话。

    后果很隐蔽：用户在预览里看到完整规则，以为生效了；模型却完全没收到，
    **画出来是单张图或排布随机的图**，而且不报任何错。

    修法与「画面批注」同一条纪律：**预览与生成共用同一个拼装函数**，
    前端只传参数（`motion_gif={...}`），拼装在服务端完成。
    """

    def _req(self, **overrides):
        from app.api.v1.images import ImageGenerateRequest

        base = {"prompt": "跑步下班，无文字"}
        base.update(overrides)
        return ImageGenerateRequest(**base)

    def test_request_accepts_motion_gif_field(self):
        """模型上必须真有这个字段，否则前端传了也会被静默丢掉。"""
        req = self._req(
            motion_gif={"motion_kind": "orbit", "grid_layout": "2x4", "prompt_lang": "zh"}
        )
        assert req.motion_gif is not None
        assert req.motion_gif["grid_layout"] == "2x4"

    def test_without_motion_gif_prompt_is_untouched(self):
        """不带动图参数时**不改变任何行为**（与接入前完全一致）。"""
        req = self._req()
        assert req.motion_gif is None

    def test_lineage_carries_motion_gif_for_retry(self):
        """血缘里必须带上动图参数 —— 重发走同一端点，丢了它就会重生成出单张图。"""
        from app.api.v1.images import _generation_lineage_from_request

        req = self._req(
            motion_gif={"motion_kind": "expression", "grid_layout": "2x4"}
        )
        lineage = _generation_lineage_from_request(req)
        assert lineage.get("motion_gif"), "重发时动图参数会丢 —— 会生成出单张图且不报错"
        assert lineage["motion_gif"]["motion_kind"] == "expression"

    def test_generate_endpoint_source_composes_motion_prompt(self):
        """静态守卫：`/images/generate` 的源码里必须真的调用了拼装。

        用源码断言而不是跑端点：这条路径要真跑就得调图像模型（花钱、慢、不稳定）。
        这里只需要确认"那段拼装代码还在、且用的是共享函数"。
        """
        import inspect

        from app.api.v1 import images as images_api

        src = inspect.getsource(images_api.generate_image)
        assert "motion_gif" in src, (
            "/images/generate 里没有处理 motion_gif —— 动图规则不会被拼进提示词"
        )
        assert "_mp.compose_final_prompt" in src or "compose_final_prompt" in src, (
            "生成路径没有调用 compose_final_prompt —— 预览与实际发送会漂移"
        )

    def test_bad_motion_params_are_400_not_generation_failure(self):
        """参数写错属于**请求写错**（400），不能被吞成"生成失败"。

        与画面批注同一处理：外部 Agent 需要能区分"我该改请求"还是"供应商挂了"。
        """
        import inspect

        from app.api.v1 import images as images_api

        src = inspect.getsource(images_api.generate_image)
        assert "HTTPException(status_code=400" in src, "动图参数不合法没有回 400"

    def test_preview_and_generate_use_same_function(self):
        """预览与生成共用一个函数是硬约束，此测试锁住它。"""
        svc = MotionGifService()
        a = svc.compose_prompt(
            user_prompt="P", kind="orbit", layout="2x4", lang="en"
        )
        b = motion_prompt.compose_final_prompt(
            user_prompt="P",
            blocks=motion_prompt.build_prompt_blocks_en(kind="orbit", layout="2x4"),
        )
        assert a == b


class TestBlockOverrides:
    """提示词块必须**可编辑**（不只是能关）。

    踩过的坑（用户实测："表情包写死了动作不能动"）：

    「表情包」原本写死"除了脸上的表情，画面里任何东西都不变"，
    而用户实际要的是**表情变 + 小动作、但主体不变**（摇尾、抬手、点头）。
    这不是改一句文案能解决的 —— 素材与用法千差万别，
    **能改比写得准更重要**：规则是默认模板，不是圣旨。
    """

    def _blocks(self, kind="expression"):
        return motion_prompt.build_prompt_blocks(kind=kind, layout="2x4", lang="zh")

    def test_override_replaces_text(self):
        out = motion_prompt.apply_block_overrides(
            self._blocks(), {"motion": "【自定义】只做表情，不要动作。"}
        )
        motion = next(b for b in out if b.id == "motion")
        assert motion.text == "【自定义】只做表情，不要动作。"

    def test_untouched_blocks_keep_default_text(self):
        blocks = self._blocks()
        out = motion_prompt.apply_block_overrides(blocks, {"motion": "X"})
        for b in out:
            if b.id != "motion":
                default = next(d for d in blocks if d.id == b.id)
                assert b.text == default.text, f"{b.id} 不该被改动"

    def test_empty_override_drops_the_block(self):
        """空串 = 关掉这一段（与 disabled 等价，前端清空文本框即此语义）。"""
        out = motion_prompt.apply_block_overrides(self._blocks(), {"motion": ""})
        assert not any(b.id == "motion" for b in out)

    def test_overrides_do_not_mutate_originals(self):
        """不能就地改默认块 —— 否则「恢复默认」拿不回原文。"""
        blocks = self._blocks()
        before = [b.text for b in blocks]
        motion_prompt.apply_block_overrides(blocks, {"motion": "改了"})
        assert [b.text for b in blocks] == before

    def test_blocks_to_prompt_applies_both_override_and_disable(self):
        full = motion_prompt.blocks_to_prompt(
            user_prompt="主提示词",
            blocks=self._blocks(),
            overrides={"motion": "【自定义写法】"},
            disabled_ids=["locked"],
        )
        assert "主提示词" in full
        assert "【自定义写法】" in full
        assert "【不得变化】" not in full, "被关掉的段不该出现"

    def test_optimized_still_skips_everything(self):
        """AI 优化后仍不追加任何块 —— 包括用户改过的。（否则会与优化结果冲突）"""
        full = motion_prompt.blocks_to_prompt(
            user_prompt="优化后的",
            blocks=self._blocks(),
            overrides={"motion": "X"},
            optimized=True,
        )
        assert full == "优化后的"


class TestEachMotionKindHasItsOwnMetric:
    """回归：四类动效的"变化量"描述**不能共用一句**。

    踩过的坑：连续性段曾经一律写"每格约 8.571 度" ——
    那是 `60° ÷ 7` 算出来的**相机环绕专用**数值，却被角色动作/速度型/表情包照抄。

    最矛盾的是表情包：它同时要求"机位完全锁死、任何东西都不变"，
    又被告知"每格要转 8.571 度"。这很可能是那几类实测不稳定的原因之一。
    """

    def _continuity(self, kind):
        blocks = motion_prompt.build_prompt_blocks(kind=kind, layout="2x4", lang="zh")
        return next(b for b in blocks if b.id == "continuity").text

    def test_orbit_keeps_degrees(self):
        """环绕是唯一有"角度"概念的，它的描述要保留度数。"""
        assert "度" in self._continuity("orbit")

    def test_non_orbit_kinds_do_not_mention_degrees(self):
        """其余三类**不该出现角度数值** —— 它们没有环绕角度这回事。

        ⚠️ 判据是"数字+度"而不是"含『度』字"：`幅度`（amplitude）里
        天然带一个"度"字，用"含『度』"去判会误报。
        """
        import re

        for kind in ("character", "speed", "expression"):
            text = self._continuity(kind)
            degrees = re.findall(r"\d+(?:\.\d+)?\s*度", text)
            assert not degrees, (
                f"{kind} 的连续性描述里出现了角度数值 {degrees} —— 那是相机环绕的算法，"
                " 塞给这类动效会与它自己的规则矛盾"
            )

    def test_all_four_kinds_differ(self):
        texts = {k: self._continuity(k) for k in ("orbit", "character", "speed", "expression")}
        assert len(set(texts.values())) == 4, (
            f"四类动效的连续性描述有重复：{ {k: v[:24] for k, v in texts.items()} }"
        )

    def test_english_continuity_also_per_kind(self):
        def en(kind):
            blocks = motion_prompt.build_prompt_blocks_en(kind=kind, layout="2x4")
            return next(b for b in blocks if b.id == "continuity").text

        assert "degrees" in en("orbit")
        for kind in ("character", "speed", "expression"):
            assert "degrees" not in en(kind), f"{kind} 英文版也带了 degrees"
        assert len({en(k) for k in ("orbit", "character", "speed", "expression")}) == 4


class TestExpressionAllowsSmallMotion:
    """回归：表情包不能写死"完全不动"。"""

    def _rule(self, kind, lang="zh"):
        blocks = (
            motion_prompt.build_prompt_blocks(kind=kind, layout="2x4", lang=lang)
            if lang == "zh"
            else motion_prompt.build_prompt_blocks_en(kind=kind, layout="2x4")
        )
        return next(b for b in blocks if b.id == "motion").text

    def test_expression_rule_permits_secondary_motion(self):
        """要允许小幅肢体动作（用户的实际需求）。"""
        text = self._rule("expression")
        assert "允许" in text and ("肢体" in text or "动作" in text), (
            "表情包规则仍然写死完全不动 —— 用户实际需要动作+表情"
        )

    def test_expression_still_locks_camera(self):
        """允许动作**不等于**放弃机位锁死（镜头还是不能动）。"""
        text = self._rule("expression")
        assert "锁死" in text or "不动" in text
        assert "不环绕" in text or "镜头不" in text

    def test_english_expression_allows_motion(self):
        text = self._rule("expression", lang="en")
        assert "SMALL" in text.upper() and "MOTION" in text.upper()

    def test_expression_keeps_identity_constraint(self):
        """小动作可以，但**不得改变主体身份特征** —— 否则就不像同一个角色了。"""
        assert "身份" in self._rule("expression")
    def test_exceeds_limit_detects_overlong(self):
        assert motion_prompt.exceeds_limit("x" * (motion_prompt.PROMPT_CHAR_LIMIT + 1))
        assert not motion_prompt.exceeds_limit("x" * 10)

    def test_default_prompts_fit_within_limit(self):
        """实测 6449 字符可用、9213 被接口拒收；默认组合必须留有余量。"""
        for kind in ("orbit", "character", "speed", "expression"):
            for layout in ("4x4", "2x4", "1x4"):
                for lang in ("zh", "en"):
                    svc = MotionGifService()
                    full = svc.compose_prompt(
                        user_prompt="一个产品照片",
                        kind=kind,
                        layout=layout,
                        lang=lang,
                    )
                    assert not motion_prompt.exceeds_limit(full), (
                        f"{kind}/{layout}/{lang} 超出上限"
                    )


class TestDefaultLoop:
    def test_orbit_defaults_to_pingpong(self):
        """环绕类只覆盖单程角度，必须 pingpong 才无缝。"""
        assert motion_prompt.default_loop("orbit") == "pingpong"

    @pytest.mark.parametrize("kind", ["character", "speed", "expression"])
    def test_others_default_to_cycle(self, kind):
        assert motion_prompt.default_loop(kind) == "cycle"


class TestAlignFramesByContent:
    """主体对齐：模型不保证每格主体居中，不对齐就会在动画里上下跳动。

    用户实测反馈：「gif 图主体上下位置有不同的」。
    """

    @staticmethod
    def _misaligned_sheet(shift_step: int = 12):
        """一张"主体在每格内上下移动"的多格图。

        主体画得**足够小、四周留足背景**，才符合真实多格图的样子
        （模型生成时提示词就要求主体居中且留边）。早先的版本把椭圆画得很大、
        贴到格边，那种情况裁切反而会切到主体，测出来的结论是假的。
        """
        from PIL import ImageDraw

        sheet = Image.new("RGB", (800, 400), (240, 240, 240))
        draw = ImageDraw.Draw(sheet)
        for r in range(2):
            for c in range(4):
                i = r * 4 + c
                cx = c * 200 + 100
                cy = r * 200 + 100 + (i - 3.5) * shift_step
                draw.ellipse([cx - 45, cy - 35, cx + 45, cy + 35], fill=(30, 80, 160))
        return sheet

    @staticmethod
    def _subject_jitter(frames):
        import numpy as np

        centres = []
        for frame in frames:
            arr = np.asarray(frame.convert("L"), dtype=np.float32)
            ys = np.nonzero(arr < 200)[0]
            centres.append(ys.mean() if len(ys) else np.nan)
        return float(np.nanmax(centres) - np.nanmin(centres))

    def test_alignment_moves_subject_toward_canvas_center(self):
        """对齐把每帧主体**朝画布中心**移动 —— 这才是它真正保证的事。

        ⚠️ 早先这里断言"抖动减半"，那是用**构造图**测出来的假结论。
        拿真实素材复测（用户 4×4 蓝狗图）时发现：
        - 表情包类（机位锁死）原本抖动只有 3.8px，本来就不需要对齐；
        - 相机环绕类行间差 145px，但那是**模型把 4 行当成 4 个独立画面**，
          **不是切帧能修的**（每格内已无可移动空间）。
        所以这里只锁「朝中心移动」这个可验证的性质，不再吹"能治抖动"。
        """
        order = list(slicing.origin_refs(8))
        frames = slicing.apply_global_crop(
            slicing.resolve_frames(self._misaligned_sheet(), 2, 4, order, None)
        )
        width, height = frames[0].size
        aligned = slicing.align_frames_by_content(frames, threshold=100)

        def distance_to_centre(frame):
            box = slicing.content_bbox(frame, 100)
            assert box is not None
            return abs((box[1] + box[3]) / 2 - height / 2)

        before = sum(distance_to_centre(f) for f in frames)
        after = sum(distance_to_centre(f) for f in aligned)
        assert after < before, "对齐后主体整体应更靠近画布中心"

    def test_apply_global_crop_is_opt_in(self):
        """**默认不裁内容**。

        实测：多格图每格本身已取好景，而「并集包围盒」会切掉留白 ——
        蓝狗图裁完从 256×256 变成 209×239，主体顶满画布、脚被切掉。
        """
        order = list(slicing.origin_refs(8))
        frames = slicing.resolve_frames(self._misaligned_sheet(), 2, 4, order, None)
        untouched = slicing.apply_global_crop(frames)
        assert [f.size for f in untouched] == [f.size for f in frames], "默认不应裁"
        trimmed = slicing.apply_global_crop(frames, enabled=True)
        assert trimmed[0].size != frames[0].size, "显式开启才裁"

    def test_alignment_keeps_frame_size(self):
        order = list(slicing.origin_refs(8))
        frames = slicing.apply_global_crop(
            slicing.resolve_frames(self._misaligned_sheet(), 2, 4, order, None)
        )
        aligned = slicing.align_frames_by_content(frames, threshold=100)
        assert len({f.size for f in aligned}) == 1, "对齐不能改变帧尺寸"
        assert aligned[0].size == frames[0].size

    def test_alignment_is_noop_when_already_centered(self):
        """本来就在中间的帧不该被平移（否则引入不必要的重采样损失）。"""
        from PIL import ImageDraw

        frame = Image.new("RGB", (200, 200), (240, 240, 240))
        draw = ImageDraw.Draw(frame)
        draw.rectangle([60, 60, 140, 140], fill=(0, 0, 0))
        out = slicing.align_frames_by_content([frame], threshold=100)
        assert list(out[0].getdata()) == list(frame.getdata())

    def test_compose_option_defaults_to_align_on(self):
        opts = motion_gif.MotionGifOptions(rows=2, cols=4, order=tuple(slicing.origin_refs(8)))
        assert opts.align_subject is True


class TestServiceOutputPaths:
    def test_work_dir_is_inside_backend_storage(self, tmp_path):
        svc = MotionGifService(work_dir=tmp_path / "out")
        assert svc.work_dir == tmp_path / "out"


class TestComposedOutputRevision:
    """回归：合成产物必须带**内容指纹**，否则重新合成后预览不会变。

    踩过的坑（用户实测："我修改循环或者改了帧重新合成，预览这里没变"）：

    合成产物是**原地覆写**同一个 `animation.gif`，URL 一个字不变，
    浏览器就继续用旧图。切帧小图早已用 `?v=<指纹>` 解决过同一问题，
    但**成品忘了加** —— 同一类问题只修了一半。

    ⚠️ 指纹必须按**内容**算，不能按 mtime：实测"同参数重复合成"会重写文件，
    mtime 每次都变 → 指纹每次都变 → 每次都白让缓存失效，反复重下几 MB 的 GIF。
    """

    def _compose(self, tmp_path, *, loop="cycle", size=480):
        sheet_path = tmp_path / "sheet.png"
        if not sheet_path.exists():
            _sheet(2, 4, cell=64).save(sheet_path)
        svc = MotionGifService(work_dir=tmp_path / "work")
        return asyncio.run(
            svc.compose(
                sheet_path=sheet_path,
                rows=2,
                cols=4,
                order=list(slicing.origin_refs(8)),
                uploads=None,
                output_dir=tmp_path / "out",
                loop=loop,
                size=size,
                write_webp=True,
                write_mp4=False,
            )
        )

    def test_revision_is_present(self, tmp_path):
        result = self._compose(tmp_path)
        assert result.revision, "产物没有版本指纹 —— 重新合成后浏览器会继续显示旧图"

    def test_revision_changes_when_loop_changes(self, tmp_path):
        a = self._compose(tmp_path, loop="cycle")
        b = self._compose(tmp_path, loop="pingpong")
        assert a.revision != b.revision, (
            "换了循环方式但指纹没变 —— 用户重新合成后预览不会变（实测反馈的正是这个）"
        )

    def test_revision_changes_when_size_changes(self, tmp_path):
        a = self._compose(tmp_path, size=480)
        b = self._compose(tmp_path, size=320)
        assert a.revision != b.revision

    def test_revision_is_stable_for_identical_output(self, tmp_path):
        """**同参数重复合成指纹必须不变**。

        否则每次重新合成都让缓存失效，用户来回看几次就反复重下几 MB 的 GIF。
        （按 mtime 算就会踩这个坑 —— 文件每次都被重写。）
        """
        a = self._compose(tmp_path)
        b = self._compose(tmp_path)
        assert a.revision == b.revision, (
            "同参数重复合成指纹变了 —— 每次都会白白让缓存失效（按 mtime 算的典型症状）"
        )

    def test_revision_is_in_payload(self, tmp_path):
        """前端是从 payload 里读 `revision` 的。"""
        payload = self._compose(tmp_path).to_payload()
        assert payload.get("revision"), "payload 里没有 revision，前端拿不到指纹"

    def test_representations_include_framesheet(self, tmp_path):
        """多格图必须作为附属 representation 进清单：它既是重出依据，也可被复用。"""
        sheet_path = tmp_path / "sheet.png"
        _sheet(2, 4).save(sheet_path)
        svc = MotionGifService(work_dir=tmp_path / "work")
        import asyncio

        result = asyncio.run(
            svc.compose(
                sheet_path=sheet_path,
                rows=2,
                cols=4,
                order=list(slicing.origin_refs(8)),
                uploads=None,
                output_dir=tmp_path / "work",
            )
        )
        formats = {rep["format"] for rep in svc.representations(result)}
        assert "framesheet" in formats
        assert "gif" in formats


class TestRepresentationPathsAreResolvable:
    """回归：入库侧必须用 `resolve_asset_file` 判断表示文件是否存在。

    踩过的坑：`representations()` 返回的是**相对项目根**的路径
    （`backend/app/storage/...`），而进程 CWD 通常是 `backend/`。
    入库侧若直接 `Path(x).exists()`，会把每个表示都判成"文件不存在"，
    结果是**合成成功但一个表示都没入库**（HTTP 200，错误只出现在错误信息里）。

    验证方式：把产物放到**允许根内**的目录，此时相对路径必须能被解析器还原；
    解析不了就说明入库侧会拿到 None。
    """

    def test_relative_paths_resolve_under_allowed_root(self, tmp_path, monkeypatch):
        from app.services import asset_file_resolver

        # 用 backend/storage 下的真实子目录：解析器只认允许根内的文件
        storage = Path(asset_file_resolver.project_root()) / "storage" / "_pytest_motion"
        storage.mkdir(parents=True, exist_ok=True)
        try:
            sheet_path = storage / "sheet.png"
            _sheet(2, 4).save(sheet_path)
            svc = MotionGifService(work_dir=storage / "work")
            import asyncio

            result = asyncio.run(
                svc.compose(
                    sheet_path=sheet_path,
                    rows=2,
                    cols=4,
                    order=list(slicing.origin_refs(8)),
                    uploads=None,
                    output_dir=storage / "work",
                )
            )
            reps = svc.representations(result)
            assert reps, "应有产物表示"

            for rep in reps:
                resolved = asset_file_resolver.resolve_asset_file(str(rep["file_path"]))
                assert resolved is not None, (
                    f"representation {rep['format']} 解析失败：{rep['file_path']}"
                    " —— 入库侧会把它当'文件不存在'跳过"
                )
                assert resolved.exists()
        finally:
            import shutil

            shutil.rmtree(storage, ignore_errors=True)


class TestEndpointModelsAreSelfConsistent:
    """回归：端点函数体里读的每个 `req.xxx`，模型上都必须真有这个字段。

    踩过的坑（用户实测）：`save_frames` 只加在了 `MotionGifComposeRequest`，
    `MotionGifSaveRequest` 漏了，而 `save_motion_gif` 里照写了 `req.save_frames`
    → 点「存入素材库」直接 500：`'MotionGifSaveRequest' object has no attribute 'save_frames'`。

    **只跑端点不跑测试就发现不了**：三个请求模型字段高度相似，加一个字段时
    很容易只改一个。这条用静态检查把"模型字段"与"端点读取的字段"对起来 ——
    比等用户点一次按钮便宜得多。
    """

    #: 每个端点函数 → 应当与它读取的字段保持一致的那个请求模型
    PAIRS = [
        ("compose_motion_gif", "MotionGifComposeRequest"),
        ("save_motion_gif", "MotionGifSaveRequest"),
        ("preview_slice", "MotionGifSlicePreviewRequest"),
    ]

    @staticmethod
    def _req_attr_names(source: str) -> set[str]:
        """抓出源码里出现的 `req.<名字>`（含 `req.xxx` 与 `req.xxx!`）。"""
        import re

        return set(re.findall(r"\breq\.([a-zA-Z_][a-zA-Z0-9_]*)", source))

    @pytest.mark.parametrize("func_name,model_name", PAIRS)
    def test_endpoint_only_reads_declared_fields(self, func_name, model_name):
        import inspect

        from app.api.v1 import motion_gif as api

        func = getattr(api, func_name)
        model = getattr(api, model_name)
        used = self._req_attr_names(inspect.getsource(func))
        declared = set(model.model_fields)
        missing = used - declared
        assert not missing, (
            f"{func_name} 读了 {model_name} 上不存在的字段 {sorted(missing)}"
            " —— 运行时必然 AttributeError（HTTP 500），且本轮就是这么被用户撞到的"
        )

    def test_compose_and_save_accept_the_same_knobs(self):
        """合成与存库是**两步**，参数必须对得上，否则"合成能看到、存库就报错"。

        这是本次 500 的另一面：用户能成功合成、点存库才炸 —— 差别只在这两个
        模型的字段集合不同。
        """
        from app.api.v1 import motion_gif as api

        compose = set(api.MotionGifComposeRequest.model_fields)
        save = set(api.MotionGifSaveRequest.model_fields)
        # save 多了入库元信息，这些不该出现在合成参数里
        extra = {
            "name", "prompt", "provider", "model", "motion_kind",
            "node_id", "project_id", "content_id",
        }
        assert compose - save == set(), (
            f"合成能调但存库调不了的参数：{sorted(compose - save)}"
        )
        assert save - compose == extra, (
            f"存库多了不该有的合成参数：{sorted(save - compose - extra)}"
        )


class TestAssetSourceMatchesLibraryConvention:
    """回归：入库用的 `source` 必须是素材库**已知**的那个值。

    踩过的坑（用户实测）："合成后点存入素材库显示成功，再查素材库怎么看不到"。
    资产**确实入库了**（节点、版本、三个代表都在，`asset_type=IMAGE`），
    但 metadata 的 `source` 写的是自创的 `motion_gif` —— 而素材库的「来源」
    筛选是按 `SOURCE_TYPE_OPTIONS` 里的固定几项来的，自创值既不在选项里，
    卡片来源会显示成"未知"，一点「AI生成」筛选就把这张动图排除掉。

    这是**最难查的一类 bug**：后端一切正常、接口返回 success、数据库里躺着，
    只在"用户按正常路径去找"的时候消失。所以用测试把两边钉在一起。
    """

    #: 前端 `pages/assets/index.tsx` 里 SOURCE_TYPE_OPTIONS 的取值
    LIBRARY_SOURCE_OPTIONS = {
        "ai_generated",
        "parse",
        "download",
        "torrent",
        "novel_download",
        "wechat_mp",
        "upload",
        "import",
        "legacy_assets",
    }

    def test_motion_gif_node_source_is_ai_generated(self, tmp_path, monkeypatch):
        """动图的 node.metadata.source 必须落在 AI 生成这一类里。"""
        import asyncio
        from pathlib import Path

        from app.services import asset_file_resolver

        storage = Path(asset_file_resolver.project_root()) / "storage" / "_pytest_source"
        storage.mkdir(parents=True, exist_ok=True)
        try:
            gif = storage / "animation.gif"
            from PIL import Image as _Image

            _Image.new("P", (32, 32)).save(gif, format="GIF")

            captured: dict = {}

            class _FakeNodeService:
                def __init__(self, *_a, **_k):
                    pass

                async def create(self, **kwargs):
                    captured.update(kwargs)

                    class _N:
                        id = "00000000-0000-0000-0000-000000000001"

                    return _N()

                async def update(self, *_a, **_k):
                    return None

            class _FakeVersionService:
                def __init__(self, *_a, **_k):
                    pass

                async def create(self, **_k):
                    class _V:
                        id = "00000000-0000-0000-0000-000000000002"
                        version_number = 1

                    return _V()

            class _FakeRepService:
                def __init__(self, *_a, **_k):
                    pass

                async def create(self, **_k):
                    class _R:
                        id = "00000000-0000-0000-0000-000000000003"

                    return _R()

            from app.services.asset_hub import facade as facade_mod

            monkeypatch.setattr(facade_mod, "AssetNodeService", _FakeNodeService)
            monkeypatch.setattr(facade_mod, "AssetVersionService", _FakeVersionService)
            monkeypatch.setattr(facade_mod, "AssetRepresentationService", _FakeRepService)

            asyncio.run(
                facade_mod.AssetHubFacade(session=None).create_motion_gif(
                    name="t",
                    primary_file_path=str(gif),
                    representations=[
                        {"format": "gif", "mime_type": "image/gif", "file_path": str(gif)}
                    ],
                )
            )

            source = (captured.get("metadata") or {}).get("source")
            assert source == "image_generation", (
                f"动图入库用的 source={source!r}，素材库认不出来。"
                " 自创的 source 值会让卡片显示'未知来源'，并被「AI生成」筛选排除 ——"
                " 表现为'存成功了但素材库里看不到'"
            )
            assert source in self.LIBRARY_SOURCE_OPTIONS | {"image_generation"}, (
                "source 必须落在前端来源筛选的已知集合内"
            )
            # 缩略图字段也要有，否则素材库卡片没图
            assert (captured.get("metadata") or {}).get("source_url"), (
                "缺少 source_url，素材库卡片无法解析预览图"
            )
        finally:
            import shutil

            shutil.rmtree(storage, ignore_errors=True)


class TestMotionOptionsAreServedNotDuplicated:
    """回归：动图排布/循环选项的**唯一来源是 `/motion-gif/options`**。

    踩过的坑：`/options` 早就把"每种排布几行几列几格、循环方式叫什么名"
    全返回了，但前端页面**又硬编码了一份**（`MOTION_GRID_CELLS` /
    `MOTION_GRID_SHAPE` / `loopOptions` 的标签与说明）。
    后端加一种排布时页面不知道 —— 而**算错格数不会报错**，只会切出错帧数。

    这里锁住"端点必须把这些字段全给出来"，前端那份才能退化成兜底值。
    """

    def test_options_endpoint_carries_rows_cols_cells(self):
        """前端换排布时要知道行列格数，必须由端点提供（不能只给 key）。"""
        import asyncio

        from app.api.v1.motion_gif import get_motion_gif_options

        payload = asyncio.run(get_motion_gif_options())
        grids = payload.grid_layouts
        assert grids, "排布选项为空"
        for grid in grids:
            assert {"key", "rows", "cols", "cells"} <= set(grid), (
                f"排布 {grid.get('key')} 缺少行列格数字段，前端只能自己硬编码"
            )
            assert grid["cells"] == grid["rows"] * grid["cols"], (
                f"排布 {grid['key']} 的 cells 与 rows×cols 不一致"
            )

    def test_options_match_the_prompt_module(self):
        """端点的排布必须与提示词模块同源（两处各写一份就会漂移）。"""
        import asyncio

        from app.api.v1.motion_gif import get_motion_gif_options

        payload = asyncio.run(get_motion_gif_options())
        served = [(g["key"], g["rows"], g["cols"], g["cells"]) for g in payload.grid_layouts]
        truth = [(s.key, s.rows, s.cols, s.cells) for s in motion_prompt.GRID_LAYOUTS]
        assert served == truth, (
            f"端点排布 {served} 与 motion_prompt.GRID_LAYOUTS {truth} 不一致"
        )

    def test_loop_modes_carry_label_and_note(self):
        """循环方式的名称与说明也由端点给 —— 前端不该抄那份文案。"""
        import asyncio

        from app.api.v1.motion_gif import get_motion_gif_options

        payload = asyncio.run(get_motion_gif_options())
        assert payload.loop_modes, "循环方式为空"
        for mode in payload.loop_modes:
            assert mode.get("key"), "循环方式缺 key"
            assert mode.get("label"), f"循环方式 {mode.get('key')} 缺中文名"
            assert mode.get("note"), f"循环方式 {mode.get('key')} 缺说明"

    def test_motion_kinds_publish_default_loop(self):
        """每类动效的**推荐循环方式**由后端给，前端不该自己写
        `kind === 'orbit' ? 'pingpong' : 'cycle'` 这种规则。"""
        import asyncio

        from app.api.v1.motion_gif import get_motion_gif_options

        payload = asyncio.run(get_motion_gif_options())
        for kind in payload.motion_kinds:
            assert kind.get("default_loop") in {"pingpong", "cycle", "none"}, (
                f"动效 {kind.get('key')} 的 default_loop 非法：{kind.get('default_loop')}"
            )

    def test_frontend_uses_the_shared_hook(self):
        """前端页面必须走共享 hook，不能自己定义一份排布表。"""
        from pathlib import Path

        page = (
            Path(__file__).resolve().parents[2]
            / "frontend"
            / "src"
            / "pages"
            / "image-gen"
            / "index.tsx"
        )
        if not page.exists():
            pytest.skip("前端源码不在本机（多机开发时）")
        source = page.read_text(encoding="utf-8")
        assert "useMotionGifOptions" in source, (
            "页面没有用 useMotionGifOptions —— 排布格数会退回硬编码，"
            "后端新增排布时算错帧数且不会报错"
        )
        # 只查**代码**里有没有残留：注释里提到旧常量名是正常的（说明来历），
        # 所以先剥掉注释行再断言。
        code_lines = [
            line
            for line in source.splitlines()
            if not line.lstrip().startswith(("*", "//", "/*"))
        ]
        code = "\n".join(code_lines)
        assert "MOTION_GRID_SHAPE[" not in code, (
            "页面代码里还在用 MOTION_GRID_SHAPE 硬编码表"
        )
        assert "MOTION_GRID_CELLS[" not in code, (
            "页面代码里还在用 MOTION_GRID_CELLS 硬编码表"
        )
