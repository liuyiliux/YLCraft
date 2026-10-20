"""通用图片切片（frame sheet slicing）测试。

这个模块是**公共组件**，动图与立绘九宫格都要用，所以重点锁两件事：

1. 几何正确（切出来的格位置、尺寸、余数像素不丢）
2. **来源语义不被下标漂移**（删格 + 补上传图之后，仍能说清"第几帧来自原图第几格"）
"""

from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from app.services.image import slicing

#: 测试用格子边长。必须 >= slicing.MIN_CELL_SIDE，否则会先被"单格过小"拦下。
CELL = 20


def _sheet(rows: int, cols: int, cell: int = CELL) -> Image.Image:
    """造一张每格颜色不同的多格图，便于断言切出来的位置对不对。"""
    sheet = Image.new("RGB", (cols * cell, rows * cell), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    index = 1
    for r in range(rows):
        for c in range(cols):
            left, top = c * cell, r * cell
            fill = (index * 20 % 256, index * 40 % 256, index * 60 % 256)
            draw.rectangle([left, top, left + cell - 1, top + cell - 1], fill=fill)
            index += 1
    return sheet


class TestSliceGrid:
    def test_splits_into_expected_count(self):
        cells = slicing.slice_grid(_sheet(2, 4), 2, 4)
        assert len(cells) == 8

    def test_cell_size_is_division_of_sheet(self):
        # 2 行 4 列切正方形图：格子是扁的（宽 > 高），这正是 2x4 的几何事实。
        # 不在这里强凑成方形——是否统一取景由调用方用 apply_global_crop 决定。
        cells = slicing.slice_grid(_sheet(2, 4, cell=40), 2, 4)
        assert cells[0].size == (40, 40)
        assert len({c.size for c in cells}) == 1

    def test_non_square_cells_for_tall_grid(self):
        """竖排布（行 > 列）时格子是高的，这是正常结果。"""
        sheet = Image.new("RGB", (80, 160), (0, 0, 0))
        cells = slicing.slice_grid(sheet, 4, 2)
        assert cells[0].size == (40, 40)

    def test_reading_order_is_row_major(self):
        """阅读顺序必须与肉眼一致：先从左到右，再换行。

        否则拼出来的动图会出现"跳到下一排又从头开始"的错觉。
        """
        cells = slicing.slice_grid(_sheet(2, 2), 2, 2)
        colors = [c.getpixel((5, 5)) for c in cells]
        assert colors == sorted(colors), "顺序应与绘制顺序一致（逐行）"

    def test_remnant_pixels_go_to_last_row_and_column(self):
        """尺寸不能被 cols/rows 整除时，余数像素必须并进最后一格，不能丢。"""
        sheet = Image.new("RGB", (101, 101), (0, 0, 0))
        cells = slicing.slice_grid(sheet, 2, 2)
        assert cells[0].size == (50, 50)
        assert cells[-1].size == (51, 51)  # 101-50 = 51

    def test_rejects_too_many_cells_for_source(self):
        """格数过多导致单格过小必须明确报错，而不是产出几像素的废格。"""
        with pytest.raises(ValueError, match="单格尺寸过小"):
            slicing.slice_grid(Image.new("RGB", (64, 64)), 8, 8)

    @pytest.mark.parametrize("rows,cols", [(0, 4), (4, 0), (-1, 2)])
    def test_rejects_non_positive_grid(self, rows, cols):
        with pytest.raises(ValueError, match="正整数"):
            slicing.slice_grid(_sheet(1, 1), rows, cols)


class TestOriginRefs:
    def test_origin_refs_are_one_based_and_sequential(self):
        refs = slicing.origin_refs(4)
        assert [r.origin_index for r in refs] == [1, 2, 3, 4]
        assert all(r.kind == "origin" for r in refs)


class TestResolveFrames:
    def test_default_order_returns_all_cells_in_order(self):
        sheet = _sheet(2, 2)
        frames = slicing.resolve_frames(sheet, 2, 2, slicing.origin_refs(4))
        assert len(frames) == 4
        assert [f.getpixel((5, 5)) for f in frames] == [
            f.getpixel((5, 5)) for f in slicing.slice_grid(sheet, 2, 2)
        ]

    def test_reordered_order_changes_frame_sequence(self):
        sheet = _sheet(1, 4)
        refs = [slicing.SliceRef({"kind": "origin", "index": i}) for i in (3, 1, 4)]
        frames = slicing.resolve_frames(sheet, 1, 4, refs)
        grid = slicing.slice_grid(sheet, 1, 4)
        assert frames[0].getpixel((5, 5)) == grid[2].getpixel((5, 5))
        assert frames[1].getpixel((5, 5)) == grid[0].getpixel((5, 5))

    def test_upload_substitutes_its_own_pixels(self):
        """上传补位必须用用户那张图，而不是悄悄退回原图。

        悄悄退回会让面板显示的格与真正合成的格对不上。
        """
        sheet = _sheet(1, 3)
        upload = Image.new("RGB", (CELL, CELL), (7, 7, 7))
        refs = [
            slicing.SliceRef({"kind": "origin", "index": 1}),
            slicing.SliceRef({"kind": "upload", "index": 1}),
        ]
        frames = slicing.resolve_frames(sheet, 1, 3, refs, uploads={1: upload})
        assert frames[1].getpixel((5, 5)) == (7, 7, 7)

    def test_missing_upload_raises_instead_of_silently_substituting(self):
        sheet = _sheet(1, 3)
        refs = [slicing.SliceRef({"kind": "upload", "index": 9})]
        with pytest.raises(ValueError, match="不存在"):
            slicing.resolve_frames(sheet, 1, 3, refs, uploads={})

    def test_out_of_range_origin_index_raises(self):
        sheet = _sheet(1, 2)
        refs = [slicing.SliceRef({"kind": "origin", "index": 5})]
        with pytest.raises(ValueError, match="格"):
            slicing.resolve_frames(sheet, 1, 2, refs)

    def test_region_kind_crops_explicit_box(self):
        sheet = Image.new("RGB", (40, 40), (0, 0, 0))
        draw = ImageDraw.Draw(sheet)
        draw.rectangle([0, 0, 19, 19], fill=(255, 0, 0))
        refs = [slicing.SliceRef({"kind": "region", "box": [0, 0, 20, 20]})]
        frames = slicing.resolve_frames(sheet, 1, 1, refs)
        assert frames[0].size == (20, 20)
        assert frames[0].getpixel((5, 5)) == (255, 0, 0)

    def test_region_without_box_raises(self):
        refs = [slicing.SliceRef({"kind": "region"})]
        with pytest.raises(ValueError, match="自选区域"):
            slicing.resolve_frames(_sheet(1, 1), 1, 1, refs)


class TestSliceIdentity:
    """顺序信息只认来源，不认数组下标。"""

    def test_label_distinguishes_origin_from_upload(self):
        assert slicing.SliceRef({"kind": "origin", "index": 4}).label() == "原4"
        assert slicing.SliceRef({"kind": "upload", "index": 1}).label() == "上传1号"
        assert slicing.SliceRef({"kind": "region"}).label() == "自选区域"

    def test_dropped_cell_shows_as_gap_in_order_labels(self):
        """删掉原 3 之后，顺序标签必须能看出中间少了一格。"""
        refs = [
            slicing.SliceRef({"kind": "origin", "index": 1}),
            slicing.SliceRef({"kind": "origin", "index": 2}),
            slicing.SliceRef({"kind": "origin", "index": 4}),
        ]
        assert slicing.describe_order(refs) == ["原1", "原2", "原4"]


class TestDropMissingOrigin:
    def test_removes_refs_pointing_beyond_new_grid(self):
        """换更小的排布后旧 order 会失效，应剔除而不是整单失败。"""
        refs = [
            slicing.SliceRef({"kind": "origin", "index": 1}),
            slicing.SliceRef({"kind": "origin", "index": 9}),
        ]
        kept = slicing.drop_missing_origin(refs, total_cells=4)
        assert [r.origin_index for r in kept] == [1]

    def test_keeps_uploads_even_when_beyond_grid(self):
        """上传图与格数无关，不能因为新排布更小就被丢掉。"""
        refs = [slicing.SliceRef({"kind": "upload", "index": 1})]
        assert slicing.drop_missing_origin(refs, total_cells=1) == refs


class TestGlobalCrop:
    def _frames_with_padding(self):
        frames = []
        for offset in (0, 6, 12):
            frame = Image.new("RGB", (100, 100), (245, 245, 245))
            draw = ImageDraw.Draw(frame)
            draw.rectangle(
                [20 + offset // 2, 20, 60 + offset // 2, 60], fill=(10, 20, 30)
            )
            frames.append(frame)
        return frames

    def test_all_frames_get_same_box(self):
        """统一裁切是合成的前提：尺寸不一致会导致播放时画面跳动。"""
        cropped = slicing.apply_global_crop(self._frames_with_padding())
        assert len({f.size for f in cropped}) == 1

    def test_uniform_background_returns_original_size(self):
        """全平背景（测不出主体）时不要瞎裁，保持原尺寸即可。"""
        flat = [Image.new("RGB", (50, 60), (200, 200, 200)) for _ in range(3)]
        cropped = slicing.apply_global_crop(flat)
        assert {f.size for f in cropped} == {(50, 60)}

    def test_crop_box_stays_inside_frame(self):
        """裁切框必须夹在图内，否则负坐标会把相邻格卷进来。"""
        frames = self._frames_with_padding()
        box = slicing.union_bbox(frames)
        assert box is not None
        width, height = frames[0].size
        assert 0 <= box[0] < box[2] <= width
        assert 0 <= box[1] < box[3] <= height


# ---------------------------------------------------------------------------
# SheetGrid：可拖分割线的规整网格
# ---------------------------------------------------------------------------


class TestSheetGrid:
    def test_uniform_matches_plain_slice_grid(self):
        """均匀网格必须和老的 slice_grid 逐像素一致 —— 不然立绘切片会变样。"""
        sheet = _sheet(2, 4, cell=CELL)
        grid = slicing.SheetGrid.uniform(2, 4)
        for a, b in zip(grid.slice(sheet), slicing.slice_grid(sheet, 2, 4)):
            assert list(a.getdata()) == list(b.getdata())
        assert grid.is_uniform()

    def test_dragged_edge_moves_only_its_own_cells(self):
        """拖第 1 条横线：上排两格变高，下排两格不动。"""
        sheet = _sheet(2, 2, cell=40)  # 80x80
        grid = slicing.SheetGrid.from_edges(2, 2, ys=[0.25])
        boxes = grid.cell_boxes(*sheet.size)
        assert boxes[0][1] == 0 and boxes[0][3] == 20
        assert boxes[2][1] == 20 and boxes[2][3] == 80
        assert not grid.is_uniform()

    def test_edges_are_normalized_so_a_new_sheet_still_works(self):
        """边界是归一化的：换一张不同大小的图，同一组边界仍然落在同一位置。"""
        xs = [0.3, 0.6]
        small = slicing.SheetGrid.from_edges(1, 3, xs=xs).cell_boxes(100, 50)
        large = slicing.SheetGrid.from_edges(1, 3, xs=xs).cell_boxes(1000, 50)
        assert small[0][2] == 30 and large[0][2] == 300

    def test_missing_edge_is_filled_with_uniform_value(self):
        grid = slicing.SheetGrid.from_edges(2, 4, xs=[0.5])
        assert len(grid.xs) == 5
        assert grid.xs[0] == 0.0 and grid.xs[-1] == 1.0
        assert grid.xs[1] == pytest.approx(0.5, abs=1e-3)
        assert grid.xs[2] == pytest.approx(0.5, abs=1e-3)
        assert grid.xs[3] == pytest.approx(0.75)

    def test_out_of_range_edges_are_clamped_not_rejected(self):
        """拖分割线过程中的中间态（越界/重合）不能直接抛错，否则合成整单失败。"""
        grid = slicing.SheetGrid.from_edges(1, 3, xs=[-5.0, 9.0])
        assert grid.xs[1] == pytest.approx(0.0, abs=1e-3)
        assert grid.xs[2] == pytest.approx(1.0, abs=1e-3)

    def test_non_increasing_edges_are_forced_strictly_increasing(self):
        """重合的两条线会让格子宽 0，min() 夹不出来，必须靠"推进"保证严格递增。"""
        grid = slicing.SheetGrid.from_edges(1, 3, xs=[0.5, 0.5])
        assert grid.xs[1] < grid.xs[2]

    def test_too_narrow_cell_raises_with_actionable_message(self):
        sheet = _sheet(1, 4, cell=CELL)
        grid = slicing.SheetGrid.from_edges(1, 4, xs=[0.0])
        with pytest.raises(ValueError, match="过小|拖"):
            grid.slice(sheet)

    def test_rejects_non_positive_grid(self):
        with pytest.raises(ValueError):
            slicing.SheetGrid.uniform(0, 3)

    @pytest.mark.parametrize("rows,cols", [(2, 4), (4, 4), (1, 4), (3, 3), (2, 2), (1, 1)])
    def test_edges_with_both_endpoints_are_accepted(self, rows, cols):
        """前端 ``uniformEdges`` 与 slice-preview 回传的**都含两端点**。

        早期只按"只含内部线"读，于是把开头的 0 当成第一条内部线 ——
        第一格宽度塌成 0，整单报"单格尺寸过小 0x0"。用户实测 2×4 直接踩到。
        """
        full = [i / cols for i in range(cols + 1)]
        full_y = [i / rows for i in range(rows + 1)]
        grid = slicing.SheetGrid.from_edges(rows, cols, full, full_y)
        assert grid.is_uniform(), "含两端点的均匀边界必须还原成均匀网格"
        assert grid.cell_boxes(1024, 1024)[0] == (0, 0, 1024 // cols, 1024 // rows)

    def test_edges_without_endpoints_still_work(self):
        """只给内部线（rows-1 / cols-1 个）也必须能用。"""
        grid = slicing.SheetGrid.from_edges(2, 4, xs=[0.3], ys=[0.4])
        assert grid.xs == (0.0, 0.3, 0.5, 0.75, 1.0)
        assert grid.ys == (0.0, 0.4, 1.0)
        assert not grid.is_uniform()

    def test_roundtrip_of_uniform_edges_is_stable(self):
        """回传 → 再发回必须幂等，否则每刷新一次网格就漂一次。"""
        base = slicing.SheetGrid.uniform(4, 4)
        once = slicing.SheetGrid.from_edges(4, 4, list(base.xs), list(base.ys))
        twice = slicing.SheetGrid.from_edges(4, 4, list(once.xs), list(once.ys))
        assert once.xs == base.xs == twice.xs
        assert once.ys == base.ys == twice.ys

    def test_cells_never_overlap_and_cover_the_whole_sheet(self):
        """拖过的网格也必须无缝无重叠覆盖整张图，否则会丢画面。"""
        sheet = _sheet(3, 3, cell=40)  # 120x120
        grid = slicing.SheetGrid.from_edges(3, 3, xs=[0.2, 0.5], ys=[0.4])
        boxes = grid.cell_boxes(*sheet.size)
        assert boxes[0][:2] == (0, 0)
        assert boxes[-1][2:] == (sheet.width, sheet.height)
        for r in range(3):
            for c in range(3):
                # 同一行的格子左右必须接得上；下一行的上边必须正好贴住上一行的下边
                if c < 2:
                    assert boxes[r * 3 + c][2] == boxes[r * 3 + c + 1][0]
                if r < 2:
                    assert boxes[r * 3 + c][3] == boxes[(r + 1) * 3 + c][1]


class TestResolveFramesWithGrid:
    def test_custom_grid_changes_which_pixels_land_in_a_frame(self):
        sheet = _sheet(1, 2, cell=40)
        flat = slicing.resolve_frames(sheet, 1, 2, slicing.origin_refs(2), None)
        grid = slicing.SheetGrid.from_edges(1, 2, xs=[0.75])
        tall = slicing.resolve_frames(
            sheet, 1, 2, slicing.origin_refs(2), None, grid=grid
        )
        assert flat[0].size != tall[0].size
        assert tall[0].width > flat[0].width

    def test_uniform_grid_object_is_treated_as_no_grid(self):
        """传进来的均匀网格不该改变结果（前端初始值就是均匀的）。"""
        sheet = _sheet(2, 2, cell=CELL)
        grid = slicing.SheetGrid.uniform(2, 2)
        a = slicing.resolve_frames(sheet, 2, 2, slicing.origin_refs(4), None)
        b = slicing.resolve_frames(sheet, 2, 2, slicing.origin_refs(4), None, grid=grid)
        for x, y in zip(a, b):
            assert list(x.getdata()) == list(y.getdata())


class TestDraggedGridProducesMixedSizes:
    """回归：**拖过分割线后各格尺寸不同**，这条路径要正确处理。

    踩过两次（都是拖分割线引起的）：

    1. **`IndexError` → 接口 500**：`align_frames_by_content` 用 `images[0].size`
       当所有帧的画布，拿大尺寸去取小帧的边缘像素越界。
    2. **宽度差异被抹平 → "拖了看不出变化"**（用户反馈）：修 1 时改成
       "取最大宽高、小帧补边"，结果窄的那列被**补边撑回最宽**，
       用户刚拖窄的一列在结果里看不出来。

    最终语义：**各帧尺寸不同时不做对齐** —— 对齐的前提就是"共用一块画布"，
    每格宽高比都不同时谈"主体居中"没有参照，保住用户拖出来的真实几何更重要。
    """

    def _uneven_frames(self):
        """造出**宽窄不同但都合法**的两格，且**第 1 格更小**。

        图 200x100，竖线拖到 0.25：第 1 格 50px、第 2 格 150px，都 ≥ 16px。
        """
        sheet = _sheet(1, 2, cell=100)  # 200x100
        grid = slicing.SheetGrid.from_edges(1, 2, xs=[0.25])
        return grid.slice(sheet)

    def test_frames_really_have_different_sizes(self):
        frames = self._uneven_frames()
        assert frames[0].size != frames[1].size, (
            "这组 fixture 的前提是尺寸不同；若相同则本类测不到目标问题"
        )

    def test_align_does_not_raise_on_mixed_sizes(self):
        """不能因为尺寸不同就崩（曾经直接 IndexError → 500）。"""
        frames = self._uneven_frames()
        aligned = slicing.align_frames_by_content(frames)
        assert len(aligned) == len(frames)

    def test_mixed_sizes_are_preserved_not_padded(self):
        """⚠️ 核心不变式：**尺寸不同时不能被统一成同一个尺寸**。

        一旦统一（无论取最大还是第一个），用户刚拖窄的那一列就看不出来了 ——
        这正是用户反馈的"我拖动以后点确认，下面没有变化，应该最后两个被切一半了"。
        """
        frames = self._uneven_frames()
        aligned = slicing.align_frames_by_content(frames)
        assert [f.size for f in aligned] == [f.size for f in frames], (
            "对齐把不同尺寸的帧统一了 —— 拖出来的宽度差异会被抹掉，用户看不出变化"
        )

    def test_uneven_sizes_keep_their_relative_width(self):
        """窄格必须仍然比宽格窄（比例不能被抹平）。"""
        frames = self._uneven_frames()
        aligned = slicing.align_frames_by_content(frames)
        assert aligned[0].width < aligned[1].width, (
            "第 1 格本来更窄，对齐后却不窄了 —— 宽度信息丢了"
        )

    def test_uniform_sizes_still_get_aligned(self):
        """尺寸一致时**仍要**对齐（不能因为上面这条把正常对齐也关掉）。"""
        sheet = _sheet(2, 4, cell=40)
        frames = slicing.slice_grid(sheet, 2, 4)
        aligned = slicing.align_frames_by_content(frames)
        assert len(aligned) == 8
        assert len({f.size for f in aligned}) == 1

    def test_resolve_then_align_end_to_end(self):
        """完整链路：拖过的网格 → 取帧 → 对齐，不应抛错。"""
        sheet = _sheet(2, 4, cell=40)  # 160x80
        grid = slicing.SheetGrid.from_edges(2, 4, xs=[0.2, 0.55, 0.8])
        frames = slicing.resolve_frames(
            sheet, 2, 4, slicing.origin_refs(8), None, grid=grid
        )
        aligned = slicing.align_frames_by_content(frames)
        assert len(aligned) == 8


# ---------------------------------------------------------------------------
# FrameAdjust：每格像素级微调（零模型调用）
# ---------------------------------------------------------------------------


class TestFrameAdjust:
    def _grey(self, value: int = 128) -> Image.Image:
        return Image.new("RGB", (10, 10), (value, value, value))

    def test_neutral_adjust_is_detected(self):
        assert slicing.FrameAdjust().is_neutral
        assert slicing.FrameAdjust.from_source(None) is None
        assert slicing.FrameAdjust.from_source({"kind": "origin", "index": 1}) is None
        # 写了但全是中性值 → 仍当作没有，不做无谓的重采样
        assert slicing.FrameAdjust.from_source({"adjust": {"brightness": 1.0}}) is None

    def test_brightness_brightens_and_darkens(self):
        up = slicing.FrameAdjust(brightness=1.5).apply(self._grey(100))
        down = slicing.FrameAdjust(brightness=0.5).apply(self._grey(100))
        assert up.getpixel((5, 5))[0] > 100
        assert down.getpixel((5, 5))[0] < 100

    def test_saturation_zero_is_grey(self):
        colored = Image.new("RGB", (10, 10), (200, 60, 60))
        grey = slicing.FrameAdjust(saturation=0.0).apply(colored)
        r, g, b = grey.getpixel((5, 5))
        assert abs(r - g) < 3 and abs(g - b) < 3

    def test_hue_shift_changes_colour(self):
        colored = Image.new("RGB", (10, 10), (200, 60, 60))
        assert colored.getpixel((5, 5)) != slicing.FrameAdjust(hue=0.5).apply(colored).getpixel((5, 5))

    def test_rotate_keeps_size_and_leaves_no_black_corner(self):
        """旋转用边缘像素补边 —— 与主体对齐同一教训，不能补出黑角。"""
        white = Image.new("RGB", (40, 40), (255, 255, 255))
        rotated = slicing.FrameAdjust(rotate=10.0).apply(white)
        assert rotated.size == white.size
        assert rotated.getpixel((2, 2)) != (0, 0, 0)

    def test_out_of_range_values_are_clamped_not_rejected(self):
        """前端滑块可能带上旧值；夹住比整个合成失败好。"""
        adj = slicing.FrameAdjust.from_source({"adjust": {"brightness": 99, "rotate": -900}})
        assert adj is not None
        assert adj.brightness == pytest.approx(slicing.ADJUST_RANGES["brightness"][1])
        assert adj.rotate == pytest.approx(slicing.ADJUST_RANGES["rotate"][0])

    def test_resolve_frames_applies_per_frame_adjust_independently(self):
        """只调第 2 格，第 1 格必须原样不动。"""
        sheet = _sheet(1, 2, cell=CELL)
        order = [
            slicing.SliceRef({"kind": "origin", "index": 1}),
            slicing.SliceRef({"kind": "origin", "index": 2, "adjust": {"brightness": 0.5}}),
        ]
        plain = slicing.resolve_frames(sheet, 1, 2, slicing.origin_refs(2), None)
        tuned = slicing.resolve_frames(sheet, 1, 2, order, None)
        assert list(plain[0].getdata()) == list(tuned[0].getdata())
        mean = lambda im: sum(sum(p) for p in im.getdata()) / (im.width * im.height * 3)
        assert mean(tuned[1]) < mean(plain[1])

    def test_adjust_applies_to_uploads_too(self):
        upload = Image.new("RGB", (10, 10), (200, 200, 200))
        order = [slicing.SliceRef({"kind": "upload", "index": 1, "adjust": {"saturation": 0}})]
        out = slicing.resolve_frames(
            _sheet(1, 1), 1, 1, order, {1: upload}
        )
        r, g, b = out[0].getpixel((5, 5))
        assert abs(r - g) < 3
