"""回归：角色立绘九宫格切图**必须走公共切片组件**。

## 为什么有这条测试

`api/v1/characters.py` 原先把切图逻辑**内联写死**：

```python
left = round(col * width / req.cols)
upper = round(row * height / req.rows)
crop = image.crop((left, upper, right, lower))
```

而动图侧用的是 `slicing.slice_grid()`（**整除 + 余数并进末格**）。
**两套算法不一样** —— 同一张 1024px 图，立绘切法与动图切法可能切出
不同的格边界，而两边都"看起来正常"，不会报错。

已改为调用 `slicing.slice_grid`（用户的要求：**基础功能做通用一点当公共组件，
然后给高级功能用**）。

## 这条测试防什么

防"以后有人又把内联 crop 写回去"。判据是**读端点源码**，
而不是跑端点 —— 跑它要建角色、建素材节点、写库，成本高且与本条要防的问题无关。
`slice_grid` 本身的几何正确性由 `test_image_slicing.py` 覆盖。
"""

from __future__ import annotations

import inspect
import re


class TestCharacterSliceUsesSharedComponent:
    def _source(self) -> str:
        from app.api.v1 import characters as characters_api

        return inspect.getsource(characters_api.slice_character_portrait_grid)

    def test_calls_the_shared_slice_grid(self):
        src = self._source()
        assert "slicing.slice_grid" in src, (
            "立绘切图没有调用公共组件 slicing.slice_grid —— "
            "内联 crop 会与动图切法算出不同的格边界，且不会报错"
        )

    def test_has_no_inline_crop_left(self):
        """端点里不该再出现自己算坐标 + crop 的写法。"""
        src = self._source()
        assert not re.search(r"image\.crop\(", src), (
            "端点里仍有内联 image.crop(...) —— 应该交给 slicing.slice_grid"
        )
        assert "round(col * width" not in src and "round(row * height" not in src, (
            "端点里仍在自己算格坐标 —— 那正是与动图切法漂移的根源"
        )

    def test_imports_the_shared_module(self):
        from app.api.v1 import characters as characters_api

        assert hasattr(characters_api, "slicing"), (
            "characters.py 没有导入 app.services.image.slicing"
        )


class TestSharedSliceGridProducesSameGeometry:
    """立绘与动图**对同一张图**必须切出同样的格（这是迁移的实际意义）。"""

    def test_same_boxes_for_both_callers(self):
        from PIL import Image

        from app.services.image import slicing

        sheet = Image.new("RGB", (1024, 1024), (255, 255, 255))

        # 动图侧（也是切片网格）的格边界
        via_grid = slicing.SheetGrid.uniform(3, 3).cell_boxes(*sheet.size)
        # 立绘侧实际调用的函数
        via_helper = [im.size for im in slicing.slice_grid(sheet, 3, 3)]

        assert len(via_helper) == len(via_grid) == 9
        for box, size in zip(via_grid, via_helper):
            assert (box[2] - box[0], box[3] - box[1]) == size, (
                "两边的格尺寸不一致 —— 说明还在各算各的"
            )

    def test_remnant_pixels_are_not_lost(self):
        """非整除尺寸时余数并进末格（内联写法用 round 会丢像素）。"""
        from PIL import Image

        from app.services.image import slicing

        sheet = Image.new("RGB", (100, 100), (255, 255, 255))
        cells = slicing.slice_grid(sheet, 3, 3)
        assert sum(c.width for c in cells[:3]) == 100, "横向像素没覆盖满整张图"
        assert sum(c.height for c in cells[::3]) == 100, "纵向像素没覆盖满整张图"
