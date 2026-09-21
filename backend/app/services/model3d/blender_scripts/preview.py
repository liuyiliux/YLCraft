"""Blender 无头脚本：给 3D 模型渲一张预览图。

由 `core/blender.py` 调用：

    blender --background --python preview.py -- <源> <输出.png> [--resolution 512]

要点：
- 相机位置由**模型包围盒**算出，不写死——图生 3D 的产物尺寸被归一化过，
  而手工模型可能是真人尺度（实测 1.9 米高），写死距离不是拍得太远就是穿模；
- 默认 EEVEE（Blender 4.x 叫 BLENDER_EEVEE_NEXT），无头也能跑，比 Cycles 快得多；
- 透明背景：预览图常要叠在深色/浅色卡片上，硬编码背景色会留一块补丁。
"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy


def _argv() -> list[str]:
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1:]


def _import(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    else:
        raise SystemExit(f"unsupported input format: {suffix}")


def _frame_objects(camera: bpy.types.Object) -> None:
    """把相机拉到能框住全部网格的位置（等距视角）。"""
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        return

    import mathutils

    minimum = [float("inf")] * 3
    maximum = [float("-inf")] * 3
    for obj in meshes:
        for corner in obj.bound_box:
            world = obj.matrix_world @ mathutils.Vector(corner)
            for axis in range(3):
                minimum[axis] = min(minimum[axis], world[axis])
                maximum[axis] = max(maximum[axis], world[axis])

    center = mathutils.Vector(
        ((minimum[0] + maximum[0]) / 2, (minimum[1] + maximum[1]) / 2, (minimum[2] + maximum[2]) / 2)
    )
    size = max(maximum[0] - minimum[0], maximum[1] - minimum[1], maximum[2] - minimum[2])
    distance = max(size * 2.2, 0.5)

    camera.location = center + mathutils.Vector((distance * 0.9, -distance * 1.6, distance * 0.8))
    direction = center - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.data.clip_end = max(distance * 20, 100.0)


def main() -> None:
    args = _argv()
    if len(args) < 2:
        raise SystemExit("usage: preview.py -- <source> <output.png> [--resolution 512]")
    source = Path(args[0])
    output = Path(args[1])
    resolution = 512
    if "--resolution" in args:
        index = args.index("--resolution")
        if index + 1 < len(args):
            resolution = int(args[index + 1])

    if not source.is_file():
        raise SystemExit(f"source not found: {source}")

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    _import(source)

    camera_data = bpy.data.cameras.new("YLCraftPreviewCamera")
    camera = bpy.data.objects.new("YLCraftPreviewCamera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    _frame_objects(camera)

    light_data = bpy.data.lights.new("YLCraftPreviewLight", type="SUN")
    light_data.energy = 3.0
    light = bpy.data.objects.new("YLCraftPreviewLight", light_data)
    bpy.context.scene.collection.objects.link(light)
    light.location = (4, -4, 6)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.filepath = str(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    bpy.ops.render.render(write_still=True)
    print(f"YLCRAFT_OK {output}")


if __name__ == "__main__":
    main()
