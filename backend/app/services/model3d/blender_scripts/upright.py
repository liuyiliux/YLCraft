"""把模型的"绑定姿势"扶正——让 rest pose 变成标准站姿。

## 为什么需要这一步

不是所有模型的绑定姿势都是站着的。实测 Khronos 的 **BrainStem**：它的 rest pose
是**横躺**的（Z 高度 2.00 < 水平跨度 2.83），靠自带动画 `Anim_0` 把自己"扶起来"
（动画中 Z 高度 2.78）——所以有人在查看器里看到站着的（默认播动画），
可一旦套上别人的动作就露馅了：骨骼按新动作摆位，网格却被拽回那个躺着的骨架上，
模型当场躺平。**正因为"它自己会站起来"，这个缺陷一直没被发现。**

跨骨架复用动作的前提是"两边都是标准站姿"，所以扶正必须发生在**套动作之前**。

## 怎么扶正

把"它自己站起来的那个姿势"固化成新的 rest pose。数学是标准的重新绑定：
Blender 的蒙皮变形为 `v_out = Σ w_j · (M_pose_j · M_rest_j⁻¹) · v_rest`，
新 rest 取作当前姿势（`M_rest_new = M_pose_old`）后，新 rest 下 pose 为空、
变形矩阵变成单位阵，于是顶点必须预先吃下那个变形矩阵：

    v_new = Σ w_j · (M_pose_old_j · M_rest_old_j⁻¹) · v_old

**刻意不用 `bpy.ops.pose.armature_apply()`**：它在无头环境下 `{'FINISHED'}` 照常
返回，模型却分毫未动（实测两次），是个会静默失败的坑。

用法：
    blender -b -P upright.py -- <输入.glb> <输出.glb> [--action 名字] [--frame N] [--force]

诊断行（供调用方解析）：
    YLCRAFT_UPRIGHT need=1 ratio=0.72 action=Anim_0 frame=418   已扶正并写出输出文件
    YLCRAFT_UPRIGHT need=0 ratio=1.00                           本来就是站姿，未写出文件
"""

from __future__ import annotations

import sys

import bpy

#: 判定阈值：rest 的"身高"低于动画中"身高"的 92% 才认为绑定姿势不是站姿。
#: 留余量是因为正常模型在动画里也会弯腰低头，不能把动作造成的自然变化当成躺倒。
UPRIGHT_RATIO = 0.92


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def _bounds(objects) -> tuple[float, float, float]:
    """返回 (X 跨度, Y 跨度, Z 跨度)。Blender 导入 glTF 后是 Z-up，**Z 才是身高**。

    排查时曾栽在这个轴上：按"glTF 是 Y-up"去读 Y，把前后厚度当成了身高，
    于是把躺着的模型判成"站立"，白绕一大圈。
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    low = [float("inf")] * 3
    high = [float("-inf")] * 3
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        try:
            mesh = evaluated.to_mesh()
        except Exception:
            continue
        matrix = evaluated.matrix_world
        for vertex in mesh.vertices:
            world = matrix @ vertex.co
            for axis in range(3):
                low[axis] = min(low[axis], world[axis])
                high[axis] = max(high[axis], world[axis])
        evaluated.to_mesh_clear()
    if low[0] == float("inf"):
        return (0.0, 0.0, 0.0)
    return (high[0] - low[0], high[1] - low[1], high[2] - low[2])


def _bind(armature, action) -> None:
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = action
    # Blender 4.4+ 的 slot 机制：光设 action 未必生效，slot 也要绑上
    if getattr(armature.animation_data, "action_slot", None) is None and hasattr(action, "slots"):
        slots = list(getattr(action, "slots", []) or [])
        if slots:
            armature.animation_data.action_slot = slots[0]


def _upright(armature, meshes) -> int:
    """把当前姿势固化成新 rest pose，同步重算网格顶点。返回改动的顶点数。"""
    old_rest = {bone.name: bone.matrix_local.copy() for bone in armature.data.bones}
    deform = {
        pose_bone.name: pose_bone.matrix @ old_rest[pose_bone.name].inverted()
        for pose_bone in armature.pose.bones
        if pose_bone.name in old_rest
    }

    # 先父后子：父骨骼的 rest 一变，子骨骼的绝对位置就跟着漂
    ordered: list[str] = []

    def walk(bone) -> None:
        ordered.append(bone.name)
        for child in bone.children:
            walk(child)

    for bone in armature.data.bones:
        if bone.parent is None:
            walk(bone)

    bpy.ops.object.mode_set(mode="EDIT")
    for name in ordered:
        edit_bone = armature.data.edit_bones.get(name)
        pose_bone = armature.pose.bones.get(name)
        if edit_bone and pose_bone:
            edit_bone.matrix = pose_bone.matrix
    bpy.ops.object.mode_set(mode="OBJECT")

    moved = 0
    for mesh in meshes:
        if not any(modifier.type == "ARMATURE" for modifier in mesh.modifiers):
            continue
        group_names = [group.name for group in mesh.vertex_groups]
        for vertex in mesh.data.vertices:
            old_position = vertex.co.copy()
            blended = None
            for assignment in vertex.groups:
                matrix = deform.get(group_names[assignment.group])
                if matrix is None or assignment.weight <= 0:
                    continue
                term = (matrix @ old_position) * assignment.weight
                blended = term if blended is None else blended + term
            if blended is not None:
                vertex.co = blended
                moved += 1
        mesh.data.update()

    # 原动画是相对旧 rest 定义的，扶正后语义已不成立——留着只会被双重应用
    if armature.animation_data:
        armature.animation_data.action = None
    for pose_bone in armature.pose.bones:
        pose_bone.matrix_basis.identity()
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)
    bpy.context.view_layer.update()
    return moved


def main() -> int:
    argv = _argv()
    if len(argv) < 2:
        print("YLCRAFT_ERROR 需要 <输入.glb> <输出.glb>")
        return 2

    source, output = argv[0], argv[1]
    force = "--force" in argv
    wanted = ""
    frame_arg = 0.0
    # 逐项走而不是先过滤 `--` 开头：`--frame 418` 的取值 418 本身不以 `--` 开头，
    # 过滤后会被误当成动作名（踩过一次）
    index = 2
    while index < len(argv):
        item = argv[index]
        if item in ("--frame", "-f"):
            if index + 1 < len(argv):
                frame_arg = float(argv[index + 1])
            index += 2
            continue
        if item.startswith("--"):
            index += 1
            continue
        wanted = item
        index += 1

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for action in list(bpy.data.actions):
        bpy.data.actions.remove(action)
    bpy.ops.import_scene.gltf(filepath=source)

    armature = next((obj for obj in bpy.data.objects if obj.type == "ARMATURE"), None)
    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    if armature is None:
        print("YLCRAFT_UPRIGHT need=0 ratio=1.000 说明=没有骨架，无需扶正")
        return 0

    bpy.ops.object.select_all(action="DESELECT")
    for mesh in meshes:
        mesh.select_set(True)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    armature.data.pose_position = "POSE"

    actions = list(bpy.data.actions)
    chosen = None
    if wanted:
        chosen = next((item for item in actions if item.name == wanted), None)
    if chosen is None and actions:
        # 最长的那段通常是模型的展示动画，也最可能包含"站起来"的姿势
        chosen = max(actions, key=lambda item: item.frame_range[1] - item.frame_range[0])

    # 先量 rest 的身高
    if armature.animation_data:
        armature.animation_data.action = None
    armature.data.pose_position = "REST"
    bpy.context.view_layer.update()
    _, _, rest_height = _bounds(meshes)
    armature.data.pose_position = "POSE"

    anim_height = 0.0
    used_frame = 0
    if chosen is not None:
        _bind(armature, chosen)
        start, end = chosen.frame_range
        # 不能取中点：实测 BrainStem 的 Anim_0 中点帧本身就是前倾姿势，
        # 拿它当基准等于把"驼背"固化进新 rest。改为扫描整段动画，
        # 挑**站立度最高**的一帧（身高 ÷ 水平最大跨度）。
        if frame_arg > 0:
            used_frame = int(frame_arg)
        else:
            best_score = -1.0
            step = max(1, int((end - start) / 60))
            probe = int(start)
            while probe <= int(end):
                bpy.context.scene.frame_set(probe)
                bpy.context.view_layer.update()
                span_x, span_y, span_z = _bounds(meshes)
                score = span_z - 1.5 * span_x - 0.5 * span_y
                if score > best_score:
                    best_score, used_frame = score, probe
                probe += step
            print(f"YLCRAFT_UPRIGHT scan best_frame={used_frame} score={best_score:.3f}")
        bpy.context.scene.frame_set(used_frame)
        bpy.context.view_layer.update()
        _, _, anim_height = _bounds(meshes)

    ratio = (rest_height / anim_height) if anim_height > 0 else 1.0
    if not (force or (anim_height > 0 and ratio < UPRIGHT_RATIO)):
        print(
            f"YLCRAFT_UPRIGHT need=0 ratio={ratio:.3f} rest={rest_height:.3f} "
            f"anim={anim_height:.3f} 说明=绑定姿势已是站姿，不动它"
        )
        # 不写出输出文件：调用方继续用原文件，避免无意义的 glTF 往返
        return 0

    print(
        f"YLCRAFT_UPRIGHT need=1 ratio={ratio:.3f} rest={rest_height:.3f} "
        f"anim={anim_height:.3f} action={chosen.name} frame={used_frame}"
    )

    moved = _upright(armature, meshes)
    _, _, new_height = _bounds(meshes)

    bpy.ops.export_scene.gltf(
        filepath=output,
        export_format="GLB",
        export_animations=False,
        export_skins=True,
        use_selection=False,
    )
    print(f"YLCRAFT_UPRIGHT rebound verts={moved} height={new_height:.3f}")
    print(f"YLCRAFT_OK {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
