"""`FFmpegService.images_to_video` 的契约测试。

这个方法存在的理由（见 `docs/research/research_report_previs_export_feasibility.md`）：
浏览器实时录制按墙上时钟打时间戳，视口稳定不了 24fps 就会录出时长漂移的视频；
服务端按 `-framerate` 读序列是「真 24fps」的唯一可靠解。因此这里断言的重点不是
「ffmpeg 被调用了」，而是**几个一旦写错就会静默产出坏视频的参数**：
帧率必须直接给 `-framerate`、序列起始编号必须与落盘命名一致、
像素格式必须是 yuv420p（否则浏览器放不出来）、奇数尺寸必须有兜底。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core import ffmpeg as ffmpeg_module
from app.core.ffmpeg import FFmpegService


class _Result:
    def __init__(self, returncode: int = 0, stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = ""
        self.stderr = stderr


@pytest.fixture()
def frames_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "frames"
    directory.mkdir()
    for index in (1, 2, 3):
        (directory / f"frame_{index:04d}.jpg").write_bytes(b"jpeg")
    return directory


def _patch_run(monkeypatch, result: _Result) -> dict:
    recorded: dict = {}

    def _fake_run(cmd, **kwargs):
        recorded["cmd"] = cmd
        recorded["kwargs"] = kwargs
        return result

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", _fake_run)
    return recorded


@pytest.mark.asyncio
async def test_images_to_video_passes_exact_frame_rate(monkeypatch, frames_dir: Path, tmp_path: Path):
    recorded = _patch_run(monkeypatch, _Result())

    await FFmpegService().images_to_video(frames_dir, tmp_path / "out.mp4", fps=24, start_number=1)

    cmd = recorded["cmd"]
    # -framerate 必须在 -i 之前：放在后面会被当成输出选项，序列按默认 25fps 读
    assert cmd.index("-framerate") < cmd.index("-i")
    assert cmd[cmd.index("-framerate") + 1] == "24"
    assert cmd[cmd.index("-start_number") + 1] == "1"
    assert cmd[cmd.index("-i") + 1] == str(frames_dir / "frame_%04d.jpg")


@pytest.mark.asyncio
async def test_images_to_video_sets_playable_pixel_format_and_even_dimensions(
    monkeypatch, frames_dir: Path, tmp_path: Path
):
    """两个「写错了也能跑、但产出没人能放」的参数。"""
    recorded = _patch_run(monkeypatch, _Result())

    await FFmpegService().images_to_video(frames_dir, tmp_path / "out.mp4")

    cmd = recorded["cmd"]
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    # 视口尺寸可能是奇数（1441×901），yuv420p 的 2×2 色度下采样要求偶数
    assert cmd[cmd.index("-vf") + 1] == "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    assert cmd[-1] == str(tmp_path / "out.mp4")


@pytest.mark.asyncio
async def test_images_to_video_rejects_missing_directory(tmp_path: Path):
    with pytest.raises(ValueError, match="帧序列目录不存在"):
        await FFmpegService().images_to_video(tmp_path / "nope", tmp_path / "out.mp4")


@pytest.mark.asyncio
async def test_images_to_video_rejects_empty_sequence(monkeypatch, tmp_path: Path):
    empty = tmp_path / "frames"
    empty.mkdir()
    # 目录存在但不是空的：这里刻意**不** mock subprocess——如果校验漏了，
    # 就会真的去调 ffmpeg 并失败，从而暴露出「空序列没被拦住」
    with pytest.raises(ValueError, match="帧序列为空"):
        await FFmpegService().images_to_video(empty, tmp_path / "out.mp4")


@pytest.mark.asyncio
async def test_images_to_video_raises_on_ffmpeg_failure(monkeypatch, frames_dir: Path, tmp_path: Path):
    _patch_run(monkeypatch, _Result(returncode=1, stderr="boom"))

    with pytest.raises(RuntimeError, match="boom"):
        await FFmpegService().images_to_video(frames_dir, tmp_path / "out.mp4")
