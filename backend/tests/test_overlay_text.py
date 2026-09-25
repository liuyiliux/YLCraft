"""漫画页贴字引擎的单元测试。

引擎是从 workbuddy 的 manga-page-comic skill 移植过来的，绘制逻辑原样保留；
这里守的是**移植后我们自己加的部分与它的对外契约**：
框位校验（越界/顶点顺序/重叠）、dry_run 出预览图而不写正式产物、塞不下时报 warning、
以及"未知类型要报错而不是静默画空"。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from app.services.creative_project.overlay_text import (
    ITEM_TYPES,
    overlay_spec,
    validate_items,
)


@pytest.fixture()
def page_png(tmp_path: Path) -> Path:
    """一张空白"漫画页"，代替真实生图产物——引擎只关心尺寸与像素，不关心内容。"""
    path = tmp_path / "page.png"
    Image.new("RGB", (600, 900), (240, 240, 240)).save(path)
    return path


def test_validate_rejects_out_of_range_box() -> None:
    warns = validate_items([{"type": "text", "box": [0.1, 0.1, 1.4, 0.2], "text": "x"}])
    assert any("超出 0~1" in w for w in warns)


def test_validate_rejects_reversed_vertices() -> None:
    warns = validate_items([{"type": "text", "box": [0.5, 0.5, 0.2, 0.8], "text": "x"}])
    assert any("顶点顺序错误" in w for w in warns)


def test_validate_flags_overlapping_bubbles() -> None:
    """重叠是最常见的翻车点（气泡压住人物脸），必须报出来。"""
    warns = validate_items([
        {"type": "bubble", "box": [0.1, 0.1, 0.4, 0.3], "text": "a"},
        {"type": "bubble", "box": [0.2, 0.15, 0.5, 0.35], "text": "b"},
    ])
    assert any("重叠" in w for w in warns)


def test_validate_skips_patch_overlap() -> None:
    """`patch` 是覆盖操作，与别的元素重叠是它的正常用法，不该报警。"""
    warns = validate_items([
        {"type": "bubble", "box": [0.1, 0.1, 0.4, 0.3], "text": "a"},
        {"type": "patch", "box": [0.15, 0.12, 0.35, 0.28]},
    ])
    assert not any("重叠" in w for w in warns)


def test_dry_run_writes_preview_alongside_source(page_png: Path, tmp_path: Path) -> None:
    """dry_run 也必须出预览图——写 `_preview.png`，不写正式产物。

    「不出图」是旧行为，实测会让前端「检查框位」点了没反应；现改为用同一个渲染引擎
    出预览，让预览与成品所见即所得（编辑态字体是 DOM 占位，跟真实渲染对不上）。

    这里按**真实调用契约**构造：`creative_projects.py` 的贴字端点只传
    `image`/`font`/`items`，不传 `output`，由实现决定落盘名。
    """
    result = overlay_spec(
        {"image": str(page_png), "items": [{"type": "text", "box": [0, 0, 1, 1], "text": "x"}]},
        dry_run=True,
    )
    assert result["dry_run"] is True
    preview = Path(result["output"])
    assert preview.name.endswith("_preview.png")
    assert preview.exists()
    # 预览不得写成正式产物名（`_text.png` 是 dry_run=False 的落盘名）
    assert not (page_png.parent / f"{page_png.stem}_text.png").exists()


def test_renders_and_preserves_size(page_png: Path, tmp_path: Path) -> None:
    """超采样后必须缩回原尺寸——尺寸变了会让它在整个页面里错位。"""
    out = tmp_path / "lettered.png"
    result = overlay_spec({
        "image": str(page_png),
        "output": str(out),
        "items": [
            {"type": "text", "box": [0.1, 0.05, 0.6, 0.15], "text": "我们这里，有一座山。"},
            {"type": "bubble", "box": [0.1, 0.3, 0.5, 0.42], "text": "你看，又是他。", "tail": [0.3, 0.5]},
            {"type": "narration", "box": [0.05, 0.6, 0.95, 0.7], "text": "那年夏天……"},
            {"type": "sfx", "box": [0.5, 0.75, 0.95, 0.9], "text": "沙沙——", "font_size": 40},
        ],
    })
    assert out.exists()
    assert result["size"] == [600, 900]
    assert Image.open(out).size == (600, 900)


def test_warns_when_text_cannot_be_placed_legibly(page_png: Path, tmp_path: Path) -> None:
    """框小到写不清时必须报 warning——两种情况都要覆盖。

    原脚本这里是**静默**的，实测踩过两次：
    ① 文字被裁切：把 "那是什么？" 裁成 "那是"，成图看上去只是"少了个字"；
    ② 字号被压到不可读：引擎会一路缩到 6px 让文字"塞得下"，校验通过，
       但印出来根本看不清——只判"塞不下"会整类漏掉。
    """
    result = overlay_spec({
        "image": str(page_png),
        "output": str(tmp_path / "tiny.png"),
        "items": [{"type": "text", "box": [0.01, 0.01, 0.04, 0.03], "text": "这句话绝对塞不进这么小的框里"}],
    })
    assert any(("塞不下" in w) or ("不可读" in w) for w in result["warnings"]), result["warnings"]


def test_unknown_type_raises(page_png: Path) -> None:
    """未知类型必须报错，不能静默跳过——静默跳过等于用户以为贴上了。"""
    with pytest.raises(ValueError):
        overlay_spec({"image": str(page_png), "items": [{"type": "wat", "box": [0, 0, 1, 1], "text": "x"}]})


def test_missing_box_raises(page_png: Path) -> None:
    with pytest.raises(ValueError):
        overlay_spec({"image": str(page_png), "items": [{"type": "text", "text": "x"}]})


def test_item_types_cover_skill_set() -> None:
    """与 skill 的 page.json 保持同构——少一个类型会让迁移过来的脚本静默失效。"""
    assert set(ITEM_TYPES) == {"bubble", "narration", "sfx", "text", "patch"}
