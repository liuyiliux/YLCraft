"""按**文件事实**体检 GLB/glTF 模型（绑定验收用）。

为什么需要它：网页里能预览动作，不等于导出的 GLB 真的带骨骼和动画。
验收一个绑骨结果时，要打开导出文件数清楚网格数、顶点/面数、骨骼根数、
动画段数与帧范围——这是 `3d-rigging-digital-human` #16 的验收动作，
每次拿回一个新模型都要做一遍。

用法：
    python tools/inspect_model3d.py <a.glb> [b.glb ...]

只读文件，不联网、不调用任何模型服务。
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path


def read_gltf_json(path: Path) -> dict:
    """读 GLB 的 JSON chunk，或 .gltf 的整个文件。"""
    if path.suffix.lower() == ".gltf":
        return json.loads(path.read_text(encoding="utf-8"))
    with path.open("rb") as handle:
        if handle.read(4) != b"glTF":
            raise ValueError("不是 GLB 文件（magic 不是 glTF）")
        handle.read(8)
        while True:
            header = handle.read(8)
            if len(header) < 8:
                raise ValueError("GLB 结构不完整")
            length, chunk_type = struct.unpack("<I4s", header)
            data = handle.read(length)
            if chunk_type == b"JSON":
                return json.loads(data.decode("utf-8"))


def inspect(path: Path) -> dict:
    gltf = read_gltf_json(path)
    accessors = gltf.get("accessors") or []
    meshes = gltf.get("meshes") or []

    vertices = 0
    faces = 0
    # 包围盒：从 POSITION accessor 的 min/max 聚合。
    # 送绑骨前要看一眼尺寸——人形通常"高 >> 宽≈深"，桌子之类则宽深接近。
    lower = [None, None, None]
    upper = [None, None, None]
    for mesh in meshes:
        for primitive in mesh.get("primitives") or []:
            position = (primitive.get("attributes") or {}).get("POSITION")
            if isinstance(position, int) and 0 <= position < len(accessors):
                vertices += int(accessors[position].get("count") or 0)
                accessor = accessors[position]
                minimum = accessor.get("min")
                maximum = accessor.get("max")
                if isinstance(minimum, list) and isinstance(maximum, list):
                    for axis in range(3):
                        if axis < len(minimum) and axis < len(maximum):
                            lower[axis] = minimum[axis] if lower[axis] is None else min(lower[axis], minimum[axis])
                            upper[axis] = maximum[axis] if upper[axis] is None else max(upper[axis], maximum[axis])
            indices = primitive.get("indices")
            if isinstance(indices, int) and 0 <= indices < len(accessors):
                faces += int(accessors[indices].get("count") or 0) // 3

    size = {}
    if all(value is not None for value in lower + upper):
        size = {
            "width": round(upper[0] - lower[0], 3),
            "height": round(upper[1] - lower[1], 3),
            "depth": round(upper[2] - lower[2], 3),
        }

    # 骨骼数按骨架 joints 的并集：多套 skin 可能共用骨骼，
    # 直接数 skins 会严重低估（vanguard.glb：2 套 skin / 49 根骨骼）。
    joints: set[int] = set()
    for skin in gltf.get("skins") or []:
        for joint in skin.get("joints") or []:
            if isinstance(joint, int):
                joints.add(joint)

    animations = []
    for index, animation in enumerate(gltf.get("animations") or []):
        channels = animation.get("channels") or []
        samplers = animation.get("samplers") or []
        start = None
        end = None
        for channel in channels:
            sampler_index = channel.get("sampler", 0)
            if not isinstance(sampler_index, int) or sampler_index >= len(samplers):
                continue
            accessor_index = samplers[sampler_index].get("input")
            if not isinstance(accessor_index, int) or accessor_index >= len(accessors):
                continue
            accessor = accessors[accessor_index]
            minimum = (accessor.get("min") or [None])[0]
            maximum = (accessor.get("max") or [None])[0]
            if minimum is not None:
                start = minimum if start is None else min(start, minimum)
            if maximum is not None:
                end = maximum if end is None else max(end, maximum)
        animations.append({
            "name": animation.get("name") or f"anim_{index}",
            "channels": len(channels),
            "start": start,
            "end": end,
        })

    return {
        "file": path.name,
        "size_mb": round(path.stat().st_size / 1024 / 1024, 2),
        "generator": (gltf.get("asset") or {}).get("generator", ""),
        "size": size,
        "meshes": len(meshes),
        "vertices": vertices,
        "faces": faces,
        "materials": len(gltf.get("materials") or []),
        "images": len(gltf.get("images") or []),
        "skins": len(gltf.get("skins") or []),
        "bones": len(joints),
        "animations": animations,
    }


def main() -> int:
    targets = sys.argv[1:]
    if not targets:
        print(__doc__)
        return 1
    for target in targets:
        path = Path(target)
        if not path.exists():
            print(f"{target}: 文件不存在")
            continue
        try:
            info = inspect(path)
        except Exception as exc:  # noqa: BLE001
            print(f"{path.name}: 解析失败 —— {exc}")
            continue
        print(f"\n== {info['file']}  {info['size_mb']}MB  生成器：{info['generator'] or '未标注'}")
        if info["size"]:
            print(
                f"  尺寸 宽 {info['size']['width']} × 高 {info['size']['height']} × 深 {info['size']['depth']}"
                f"（宽高比 1:{info['size']['height'] / info['size']['width']:.2f}）"
            )
        print(f"  网格 {info['meshes']} · 顶点 {info['vertices']} · 三角面 {info['faces']}")
        print(f"  材质 {info['materials']} · 贴图 {info['images']}")
        print(f"  骨架 {info['skins']} 套 · 骨骼 {info['bones']} 根")
        if info["animations"]:
            for item in info["animations"]:
                span = f"{item['start']}–{item['end']}s" if item["start"] is not None else "未标注时间轴"
                print(f"  动画 · {item['name']}（{item['channels']} 通道，{span}）")
        else:
            print("  动画 0 段（网页预览能动不等于文件里有动画）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
