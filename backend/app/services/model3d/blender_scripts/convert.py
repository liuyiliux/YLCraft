"""Blender 无头脚本：3D 模型格式转换 / 剥离骨骼 / 减面。

由 `core/blender.py` 的 BlenderService 调用：

    blender --background --python convert.py -- <源> <目标> [--strip-armature] [--ratio 0.3]

几个实测要点：
- `--` 之后才是我们自己的参数，Blender 会把前面的都吃掉；
- 4.x 的 OBJ 走 `wm.obj_import` / `wm.obj_export`（老的 `import_scene.obj` 已移除）；
- 删骨架前必须先把当前姿势烘焙成 rest pose，否则删完网格会弹回绑定姿势，
  T-Pose 就白摆了。
"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy


def _argv() -> list[str]:
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1:]


def _clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


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


def _export(path: Path) -> None:
    suffix = path.suffix.lower()
    path.parent.mkdir(parents=True, exist_ok=True)
    if suffix == ".glb":
        bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB")
    elif suffix == ".gltf":
        bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLTF")
    elif suffix == ".fbx":
        bpy.ops.export_scene.fbx(filepath=str(path))
    elif suffix == ".obj":
        bpy.ops.wm.obj_export(filepath=str(path))
    else:
        raise SystemExit(f"unsupported output format: {suffix}")


def strip_armature() -> int:
    """把骨骼姿态烘焙进网格，再删掉骨架，得到**无骨骼的静态网格**。

    为什么需要它：腾讯云绑骨的输入应当是没绑过的网格；拿一个已经带 56 根骨骼的
    模型去"再绑一次"没有意义。而删骨架不等于丢姿势——先 `armature_apply`
    把当前姿势固化为 rest pose，删掉后网格仍保持 T-Pose 的形状。
    """
    removed = 0
    for obj in list(bpy.data.objects):
        if obj.type != "ARMATURE":
            continue
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode="POSE")
        bpy.ops.pose.armature_apply(selected=False)
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.data.objects.remove(obj, do_unlink=True)
        removed += 1
    return removed


def rename_bones(mapping: dict) -> int:
    """按映射给骨骼改名（用于把非 Mixamo 谱系规整成 Mixamo 标准名）。

    这里有两个**必须一起做**的动作，缺一个都会静默出问题：

    1. **两阶段改名**：直接 `A → B`，若 B 此刻仍被另一根骨头占着（还没轮到它改），
       Blender 会自动把 A 变成 `B.001`，映射就悄悄失效了。所以先全改成临时名再改目标名。
    2. **同步网格的顶点组名**：蒙皮权重是按顶点组名去找骨骼的，只改骨骼名会让权重
       整体失配——表现是模型"僵住不动"或"散架"，而且不会报任何错。
    """
    targets = {src: dst for src, dst in (mapping or {}).items() if src and dst and src != dst}
    if not targets:
        return 0

    renamed = 0
    for obj in bpy.data.objects:
        if obj.type != "ARMATURE":
            continue
        for bone in obj.data.bones:
            if bone.name in targets:
                bone.name = f"__ylc_tmp__{bone.name}"
        for bone in obj.data.bones:
            if bone.name.startswith("__ylc_tmp__"):
                original = bone.name[len("__ylc_tmp__"):]
                bone.name = targets[original]
                renamed += 1

    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        for group in obj.vertex_groups:
            target = targets.get(group.name)
            if target:
                group.name = target
    return renamed


def decimate(ratio: float) -> int:
    """按网格减面。`ratio=0.3` 表示保留 30% 面数。

    为什么需要它：腾讯绑骨有 **60MB** 上限，而图生 3D 默认出 50 万面高模，
    实测素材库里就有一个 75MB 的模型直接撞线。减面是送绑骨前必需的预处理。
    """
    processed = 0
    for obj in list(bpy.data.objects):
        if obj.type != "MESH":
            continue
        bpy.context.view_layer.objects.active = obj
        modifier = obj.modifiers.new(name="YLCraftDecimate", type="DECIMATE")
        modifier.ratio = max(0.01, min(1.0, ratio))
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        processed += 1
    return processed


def main() -> None:
    args = _argv()
    if len(args) < 2:
        raise SystemExit(
            "usage: convert.py -- <source> <target> "
            "[--strip-armature] [--ratio 0.3] [--bone-map map.json]"
        )
    source = Path(args[0])
    target = Path(args[1])
    do_strip = "--strip-armature" in args
    ratio = 0.0
    if "--ratio" in args:
        index = args.index("--ratio")
        if index + 1 < len(args):
            ratio = float(args[index + 1])
    bone_map_path = ""
    if "--bone-map" in args:
        index = args.index("--bone-map")
        if index + 1 < len(args):
            bone_map_path = args[index + 1]

    if not source.is_file():
        raise SystemExit(f"source not found: {source}")

    _clear_scene()
    _import(source)
    if do_strip:
        strip_armature()
    if bone_map_path:
        import json

        map_file = Path(bone_map_path)
        if not map_file.is_file():
            raise SystemExit(f"bone map not found: {map_file}")
        mapping = json.loads(map_file.read_text(encoding="utf-8"))
        # 允许 {"a": "b"} 或 {"bones": {"a": "b"}} 两种形态
        if isinstance(mapping, dict) and "bones" in mapping and isinstance(mapping["bones"], dict):
            mapping = mapping["bones"]
        print(f"YLCRAFT_BONES_RENAMED {rename_bones(mapping)}")
    if ratio > 0:
        decimate(ratio)
    _export(target)
    print(f"YLCRAFT_OK {target}")


if __name__ == "__main__":
    main()
