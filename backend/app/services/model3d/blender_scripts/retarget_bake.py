"""Blender 无头脚本：把 A 模型的动作"套"到 B 模型的骨架上，烘焙后导出。

    blender --background --python retarget_bake.py -- <目标模型> <源模型> <动作名> <输出>

## 核心：只搬运"动作增量"，不动目标自己的骨骼朝向

对每根配对骨骼、每一帧：

    Δ_world      = S_rest · S_basis · S_rest⁻¹      # 源的"自身增量"转到世界空间
    basis_target = T_rest⁻¹ · Δ_world · T_rest      # 再转进目标自己的骨骼空间

`S_basis` 是源骨骼的 `matrix_basis`——**"相对它自己 rest 动了多少"**，不含父级影响。
前后两次 `rest` 夹持就是**轴系桥接**，让同一个"动作"在两套朝向完全不同的骨骼之间
无损搬运；父级的连锁影响交给 Blender 的层级自动传导，绝不重复叠加。
这样目标骨架的骨骼朝向、骨长、层级关系**原样保留**，只把"动作"搬过来。

## 为什么不能用"世界朝向对齐"（曾经的做法）

曾经的实现是给目标骨骼加 `COPY_ROTATION` 约束、`target_space = owner_space = "WORLD"`，
即"让目标骨骼的**绝对世界朝向**等于源的"。对人形布局规整的模型看着没问题，但它有个
**致命前提：两套骨架的骨骼朝向必须语义一致**。实测 Khronos 的 BrainStem（机器人）：
它的**腿骨是向上长的**（大腿 0.87 → 脚 1.61，越往末端越高，因为网格靠蒙皮权重显示，
肉眼完全看不出骨骼是反的），而 Xbot 的腿骨朝下。硬把朝向对齐 → 朝上的腿被**翻转 180°**
→ 表现就是用户看到的"上半身站着、腿对折、脚翻到上面"。

**判断依据**：与其相信"世界朝向"，不如只相信"相对自己 rest 动了多少"——后者与
骨骼怎么摆放无关，是跨骨架复用动作唯一稳妥的量。

## 两个取舍

1. 源模型的**每段动作都会搬一遍**（而不是只搬点名的那段）：一次操作就把整个动作库
   搬过去，这正是"通用动作库"想要的。
2. 目标骨架缺的部位（锁骨、手指）没有对应骨骼，自然不参与——表现是肩部略僵，
   这是可接受的损失，不是错误。
3. 只保留**旋转**：位移/缩放会让目标角色飘走或沉下去（两套骨架骨长不同），
   位置本来由导演在预演台摆。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import bpy


def _argv() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def _clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def _import_model(path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path))
    else:
        raise SystemExit(f"unsupported input format: {suffix}")


def _armatures() -> list:
    return [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]


def _bind_action(armature, action) -> None:
    """把 action 挂到骨架上，并兼容 Blender 4.4+ 的 Action Slots。"""
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = action
    slot = getattr(armature.animation_data, "action_slot", None)
    if slot is None and hasattr(action, "slots"):
        slots = list(getattr(action, "slots", []) or [])
        if slots:
            armature.animation_data.action_slot = slots[0]


def _clean_clip_name(name: str) -> str:
    """去掉导入器可能加的前缀（如 `Xbot|walk`、`Armature|Idle`）。"""
    tail = str(name or "").split("|")[-1].strip()
    return re.sub(r"\.\d+$", "", tail) or "clip"


def _hierarchy_order(armature, shared: set[str]) -> list[str]:
    """按"父先子后"排出要处理的骨骼。

    顺序不能省：父骨骼的世界矩阵一变，子骨骼的绝对位置就跟着变，
    所以子必须等父写完之后再算。
    """
    ordered: list[str] = []

    def walk(bone) -> None:
        if bone.name in shared:
            ordered.append(bone.name)
        for child in bone.children:
            walk(child)

    for bone in armature.data.bones:
        if bone.parent is None:
            walk(bone)
    return ordered


def _capture_source(source_armature, ordered: list[str], frame_start: int, frame_end: int) -> dict:
    """先把源骨架**每一帧的 `matrix_basis`**（相对自身 rest 的局部变换）采集下来。

    采的是"骨骼相对自己 rest 的旋转"，**不含父级带来的影响**——这正是要搬运的那个量。
    若改采 `pose_bone.matrix`（armature 空间），它已经把父级的旋转算进去了，
    再逐根骨骼应用就会**把父级的旋转重复算一遍**（越靠末端的骨骼转得越离谱：
    实测表现为"手臂扭过去、身体歪"，因为它位于最末端）。

    分两阶段（先全采集、再全写入）而不是边读边写：写入阶段要往目标的 action 里插
    关键帧，而 `scene.frame_set()` 会把已经插进去的关键帧应用回目标骨架，
    两个骨架互相污染，采到的源数据就不干净了。
    """
    snapshots: dict[int, dict] = {}
    scene = bpy.context.scene
    for frame in range(frame_start, frame_end + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        snapshots[frame] = {
            name: source_armature.pose.bones[name].matrix_basis.copy() for name in ordered
        }
    return snapshots


def _retarget_clip(
    target_armature,
    source_armature,
    ordered: list[str],
    snapshots: dict,
    name: str,
) -> tuple[str, list]:
    """把采集好的源姿势逐帧写到目标骨架上，生成一段新 action。

    每根骨骼的取值在**它自己的骨骼空间**里算：

        Δ_world      = S_rest · S_basis · S_rest⁻¹      # 源的"自身增量"转到世界空间
        basis_target = T_rest⁻¹ · Δ_world · T_rest      # 再转进目标的骨骼空间

    夹在中间的两次 `rest` 变换就是**轴系桥接**：源骨骼和目标骨骼的局部轴朝向可以
    完全不同（实测 BrainStem 的腿骨甚至"向上长"），但只要都经由世界空间中转，
    搬过来的就是同一个"动作"。父级的连锁影响由 Blender 的层级自动传导，这里
    只写"每根骨骼相对自己 rest 动了多少"，绝不重复叠加。

    返回 (动作名, 新建的 action 列表)。
    """
    target_rest = {
        bone.name: bone.matrix_local.to_3x3() for bone in target_armature.data.bones
    }
    source_rest = {
        bone.name: bone.matrix_local.to_3x3() for bone in source_armature.data.bones
    }

    action = bpy.data.actions.new(name)
    if target_armature.animation_data is None:
        target_armature.animation_data_create()
    target_armature.animation_data.action = None
    _bind_action(target_armature, action)

    # 切 POSE 模式再写 pose 数据；切模式前骨架必须处于选中态，否则操作符会静默取消
    bpy.ops.object.select_all(action="DESELECT")
    target_armature.select_set(True)
    bpy.context.view_layer.objects.active = target_armature
    bpy.ops.object.mode_set(mode="POSE")

    for frame in sorted(snapshots):
        snapshot = snapshots[frame]
        for bone_name in ordered:
            source_basis = snapshot[bone_name].to_quaternion().to_matrix()
            delta_world = (
                source_rest[bone_name] @ source_basis @ source_rest[bone_name].inverted()
            )
            local_rotation = (
                target_rest[bone_name].inverted() @ delta_world @ target_rest[bone_name]
            )
            # 直接写旋转，不碰位移：位置由层级与 rest 偏移决定，
            # 写位移会让骨骼脱离父级、角色飘走
            target_armature.pose.bones[bone_name].rotation_quaternion = (
                local_rotation.to_quaternion()
            )
        for bone_name in ordered:
            target_armature.pose.bones[bone_name].keyframe_insert(
                "rotation_quaternion", frame=frame
            )

    bpy.ops.object.mode_set(mode="OBJECT")
    target_armature.animation_data.action = None
    return action.name, [action]


def _keep_rotation_only(action) -> tuple[int, int]:
    """删掉位移/缩放曲线，只留旋转。返回 (保留, 删除)。"""
    kept = 0
    removed = 0
    for fcurve in list(action.fcurves):
        path = fcurve.data_path or ""
        if path.endswith("rotation_quaternion") or path.endswith("rotation_euler"):
            kept += 1
            continue
        action.fcurves.remove(fcurve)
        removed += 1
    return kept, removed


def main() -> None:
    args = _argv()
    if len(args) < 4:
        raise SystemExit("usage: retarget_bake.py -- <target.glb> <source.glb> <clip> <out.glb>")
    target_path, source_path = Path(args[0]), Path(args[1])
    clip_name, output_path = args[2], Path(args[3])
    for path in (target_path, source_path):
        if not path.is_file():
            raise SystemExit(f"file not found: {path}")

    _clear_scene()
    _import_model(target_path)
    target_objects = set(bpy.data.objects)
    target_actions = {action.name for action in bpy.data.actions}
    target_armatures = _armatures()
    if not target_armatures:
        raise SystemExit("目标模型没有骨架，无法重定向")
    target_armature = target_armatures[0]
    target_bones = {bone.name for bone in target_armature.data.bones}

    _import_model(source_path)
    source_armatures = [arm for arm in _armatures() if arm is not target_armature]
    if not source_armatures:
        raise SystemExit("源模型没有骨架")
    source_armature = source_armatures[0]

    source_bones = {bone.name for bone in source_armature.data.bones}
    shared = source_bones & target_bones
    if not shared:
        raise SystemExit(
            "两套骨架没有同名骨骼，无法重定向；"
            "请先用 skeleton_report.py + convert.py --bone-map 把目标骨架统一到 Mixamo 标准名"
        )

    # 源模型带来的动作（排除目标原有的）
    source_action_list = [
        action for action in bpy.data.actions if action.name not in target_actions
    ]
    if not source_action_list:
        raise SystemExit("源模型没有动画，没什么可套的")
    # 点名的动作排在最前，其余按名字稳定排序
    source_action_list.sort(key=lambda item: (clip_name.lower() not in item.name.lower(), item.name))

    ordered = _hierarchy_order(target_armature, shared)

    #: (动作产物的临时名, 期望的正式名)。源 action 此刻还在（要驱动源骨架），
    #: 若直接起正式名，Blender 会因重名自动加 `.001` 后缀——所以先挂临时名，
    #: 收尾删掉源 action 之后再统一改回正式名。
    pending: list[tuple[str, str]] = []
    dropped = 0
    for index, source_action in enumerate(source_action_list):
        if target_armature.animation_data:
            target_armature.animation_data.action = None   # 解绑，避免带着上一段的状态
        _bind_action(source_armature, source_action)
        start = int(source_action.frame_range[0])
        end = max(int(source_action.frame_range[1]), start + 1)

        snapshots = _capture_source(source_armature, ordered, start, end)
        produced_name, _ = _retarget_clip(
            target_armature,
            source_armature,
            ordered,
            snapshots,
            f"__ylc_bake_{index}",
        )
        if produced_name:
            pending.append((produced_name, _clean_clip_name(source_action.name)))

    # 删掉源模型带进来的**原始** action：它们存的是源骨架局部坐标系下的旋转，
    # 既会和重定向结果重名（导出时变成 `walk.001` 这种），也可能被误选——
    # 而选中它们恰恰会重现"套上就不对"的老毛病。要的是搬过来的版本，不是原件。
    for action in source_action_list:
        try:
            bpy.data.actions.remove(action)
        except Exception:  # noqa: BLE001
            pass

    # 源 action 已经腾位置了，把产物改成正式名
    baked: list[str] = []
    for temp_name, final_name in pending:
        action = bpy.data.actions.get(temp_name)
        if not action:
            continue
        candidate = final_name
        index = 1
        while bpy.data.actions.get(candidate) not in (None, action):
            candidate = f"{final_name}_{index}"
            index += 1
        action.name = candidate
        baked.append(candidate)

    # 只留旋转：位移/缩放会让目标角色飘走或沉下去（两套骨架骨长不同）
    for action in bpy.data.actions:
        if action.name in target_actions:
            continue
        _, removed = _keep_rotation_only(action)
        dropped += removed

    for obj in list(bpy.data.objects):
        if obj not in target_objects:
            bpy.data.objects.remove(obj, do_unlink=True)

    bpy.ops.export_scene.gltf(
        filepath=str(output_path),
        export_format="GLB",
        export_animations=True,
        export_skins=True,
        use_selection=False,
    )
    print(
        f"YLCRAFT_RETARGET shared_bones={len(shared)} ordered={len(ordered)} "
        f"clips={len(baked)} dropped_curves={dropped}"
    )
    print(f"YLCRAFT_OK {output_path}")


if __name__ == "__main__":
    main()
