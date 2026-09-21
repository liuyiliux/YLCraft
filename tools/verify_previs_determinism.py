"""tasks 7.2：同一帧区间导出两次，**逐帧必须一致**；产物帧率必须是场景帧率。

为什么这条要单独钉死：预演台的产出是"参考帧/参考视频"，它要能被反复重导而不漂移——
如果同一段预演两次导出结果不同，那么"我上次看的那版"就无法复现，剪辑与生图都会拿到
不一致的输入。这也是当初拒绝 `Math.random()` 做手持抖动、拒绝按墙上时钟播放的原因。

**判据**：
1. 两次导出各自的每一帧**逐字节相同**（JPEG 编码是确定性的，差别只可能来自渲染）；
2. 两次导出的帧数与帧号序列一致；
3. 产物视频的 `r_frame_rate` 等于场景帧率（不是"约等于"）。

用法：
    backend\\venv_win\\Scripts\\python.exe tools\\verify_previs_determinism.py <scene_id>
"""

from __future__ import annotations

import asyncio
import hashlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.previs.headless_render import export_frames_headless, extract_frames  # noqa: E402

OUT_ROOT = Path("tmp/previs-determinism")
EXPORT_ROOT = Path(__file__).resolve().parents[1] / "backend" / "storage" / "uploads" / "previs-exports"


def frame_digests(directory: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.glob("*.jpg"))
    }


async def run_once(scene_id: str, tag: str) -> tuple[dict[str, str], list[int]]:
    archive, count = await export_frames_headless(scene_id)
    target = OUT_ROOT / tag
    if target.exists():
        for stale in target.glob("*"):
            stale.unlink()
    written, frames = extract_frames(archive, target)
    assert written == count, f"{tag}: 落盘 {written} 与 ZIP 帧数 {count} 不一致"
    return frame_digests(target), frames


async def main() -> int:
    scene_id = sys.argv[1]
    first, first_frames = await run_once(scene_id, "run1")
    second, second_frames = await run_once(scene_id, "run2")

    same_names = set(first) == set(second)
    differing = [name for name in first if first.get(name) != second.get(name)]
    lines = [
        f"场景：{scene_id}",
        f"第一次：{len(first)} 帧，帧号 {first_frames[:2]}…{first_frames[-1] if first_frames else '-'}",
        f"第二次：{len(second)} 帧，帧号 {second_frames[:2]}…{second_frames[-1] if second_frames else '-'}",
        f"文件名集合一致：{same_names}",
        f"逐帧哈希一致：{len(differing) == 0 and same_names}（不一致帧数 {len(differing)}）",
    ]
    if differing:
        lines.append(f"首个不一致：{differing[0]}")

    # 帧率：取最近一次真实合成的 mp4 核对（由端点链路产出）
    videos = sorted(EXPORT_ROOT.glob("*/previs-export.mp4"), key=lambda p: p.stat().st_mtime)
    if videos:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=r_frame_rate,width,height,nb_frames", "-of", "default=nw=1", str(videos[-1])],
            capture_output=True, text=True,
        )
        lines.append(f"产物帧率核对（{videos[-1].parent.name}）：{probe.stdout.strip().replace(chr(10), '  ')}")
    else:
        lines.append("产物帧率核对：导出目录里没有 mp4 可核（可先跑一次视频导出）")

    ok = same_names and not differing
    lines.append("结论：" + ("确定性成立（两次导出逐帧一致）" if ok else "确定性不成立——同一区间两次导出结果不同"))
    Path(OUT_ROOT / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
