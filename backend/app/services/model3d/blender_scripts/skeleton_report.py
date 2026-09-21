"""Blender 无头脚本：导出模型的骨骼树（名字 / 父级 / 世界坐标 / 左右侧）。

用途：把非 Mixamo 谱系的模型（骨骼叫 `torso_joint_1`、`node3` 这种）规整成
Mixamo 标准名之前，得先看清它到底有哪些骨头、谁是谁的孩子、各自站在哪儿——
否则"哪根是左大腿"这件事没有任何依据，只能靠猜。

    blender --background --python skeleton_report.py -- <模型> <输出.json>

输出是纯 JSON，可直接喂给 `convert.py --bone-map`。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
import mathutils


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def _import_model(path: Path) -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    suffix = path.suffix.lower()
    if suffix in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    else:
        raise SystemExit(f"unsupported input format: {suffix}")


#: Mixamo 标准骨架名（事实标准：动作库里所有 clip 的通道都指向这套名字）
MIXAMO_PREFIX = "mixamorig:"


def _subtree_depth(name: str, by_name: dict, guard: int = 0) -> int:
    if guard > 64:
        return guard
    children = by_name[name]["children"]
    if not children:
        return guard
    return max(_subtree_depth(child, by_name, guard + 1) for child in children)


def _chain(start: str, by_name: dict, limit: int = 6) -> list[str]:
    """沿"唯一子骨"往下取一条链；遇到分叉就停（分叉处就是需要判断角色的地方）。"""
    result = [start]
    current = start
    while len(by_name[current]["children"]) == 1 and len(result) < limit:
        current = by_name[current]["children"][0]
        result.append(current)
    return result


def suggest_mixamo_map(bones: list[dict]) -> dict:
    """按骨骼树的**顺序与层级**推断 Mixamo 对应关系。

    为什么能推断：人形骨架的结构是固定的——根骨分叉出"往上的脊柱"和"往下的两条腿"，
    脊柱顶端再分叉出"脖子"和"两条手臂"。名字可以是任何语言（`torso_joint_1`、
    `node3`），但**谁是谁的孩子、谁更高**不会骗人。

    两个必须说明的前提：
    1. **左右按 x 坐标符号判定**（+x 归 Left）。这依赖模型朝向一致——本批模型
       都面向 -Z（glTF 约定），实测 RiggedFigure 的 `arm_joint_L_1` 的 x 为正，
       与 Xbot 的 `mixamorig:LeftArm` 一致。**若某模型朝向相反，左右会整体颠倒**，
       表现是走路像顺拐——所以生成的映射必须人工过一眼。
    2. 目标骨架缺的部位（锁骨、手指）无法凭空映射，对应通道在重定向时会被跳过——
       表现是肩部略僵，这是可接受的损失，不是错误。
    """
    by_name = {bone["name"]: bone for bone in bones}
    roots = [bone["name"] for bone in bones if not bone["parent"]]
    if not roots:
        return {}

    # 有多个根时取子树最大的那根：有些导出会带一个不参与蒙皮的定位骨
    hips = max(roots, key=lambda name: _subtree_depth(name, by_name))
    mapping = {hips: f"{MIXAMO_PREFIX}Hips"}
    hips_children = [child for child in by_name[hips]["children"] if child in by_name]
    if not hips_children:
        return mapping

    # 脊柱 = 从胯出发"最高的那条链"；它的最后一根就是胸（手臂与脖子的分叉处）
    spine_entry = max(hips_children, key=lambda name: by_name[name]["height"])
    spine_chain = _chain(spine_entry, by_name)
    spine_names = [f"{MIXAMO_PREFIX}Spine", f"{MIXAMO_PREFIX}Spine2"]
    if len(spine_chain) >= 3:
        spine_names = [f"{MIXAMO_PREFIX}Spine", f"{MIXAMO_PREFIX}Spine1", f"{MIXAMO_PREFIX}Spine2"]
    for index, name in enumerate(spine_chain):
        # 链比目标名少时，最后一段仍应是 Spine2（手臂挂在它下面，与 Mixamo 一致）
        mapping[name] = spine_names[min(index, len(spine_names) - 1)]

    chest = spine_chain[-1]
    chest_children = [child for child in by_name[chest]["children"] if child in by_name]
    if chest_children:
        neck_entry = max(chest_children, key=lambda name: by_name[name]["height"])
        neck_chain = _chain(neck_entry, by_name)
        for index, name in enumerate(neck_chain):
            mapping[name] = f"{MIXAMO_PREFIX}Neck" if index == 0 else f"{MIXAMO_PREFIX}Head"

        for child in chest_children:
            if child == neck_entry:
                continue
            side = "Left" if by_name[child]["head"][0] > 0 else "Right"
            for index, name in enumerate(_chain(child, by_name, limit=3)):
                mapping[name] = f"{MIXAMO_PREFIX}{side}{['Arm', 'ForeArm', 'Hand'][min(index, 2)]}"

    for child in hips_children:
        if child == spine_entry:
            continue
        side = "Left" if by_name[child]["head"][0] > 0 else "Right"
        for index, name in enumerate(_chain(child, by_name, limit=4)):
            mapping[name] = f"{MIXAMO_PREFIX}{side}{['UpLeg', 'Leg', 'Foot', 'ToeBase'][min(index, 3)]}"

    return mapping


def _report() -> dict:
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if not armatures:
        return {"armatures": [], "note": "该模型没有骨架"}

    result: list[dict] = []
    for armature in armatures:
        bones: list[dict] = []
        for bone in armature.data.bones:
            world_head = armature.matrix_world @ bone.head_local
            world_tail = armature.matrix_world @ bone.tail_local
            bones.append({
                "name": bone.name,
                "parent": bone.parent.name if bone.parent else "",
                "children": [child.name for child in bone.children],
                "head": [round(value, 4) for value in world_head],
                "tail": [round(value, 4) for value in world_tail],
                # y 是"高度"轴（glTF 导入后 Blender 里 z 向上，导出时再转回去）
                "height": round(world_head.z, 4),
                "side": "L" if world_head.x > 0.001 else ("R" if world_head.x < -0.001 else "C"),
            })

        # 按高度排序，方便人判断"最高的那根通常是 Head、最矮分叉的是脚"
        by_height = sorted(bones, key=lambda item: item["height"])
        result.append({
            "armature": armature.name,
            "bone_count": len(bones),
            "bones": bones,
            "lowest": [item["name"] for item in by_height[:4]],
            "highest": [item["name"] for item in by_height[-4:]],
            # 自动推断的 Mixamo 对应关系；**需要人工确认左右**后再喂给 convert.py
            "suggested_map": suggest_mixamo_map(bones),
        })
    return {"armatures": result}


def main() -> None:
    args = _argv()
    if len(args) < 2:
        raise SystemExit("usage: skeleton_report.py -- <model> <output.json>")
    source = Path(args[0])
    output = Path(args[1])
    if not source.is_file():
        raise SystemExit(f"source not found: {source}")

    _import_model(source)
    report = _report()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"YLCRAFT_OK {output}")


if __name__ == "__main__":
    main()
