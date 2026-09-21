"""3D 预演台的受限操作：校验、差异预览与落库变更（design §5.3 / #18）。

设计意图：Agent 不该"凭文本臆造镜头"，而是先读 #17 给的场景摘要，再提出**受限操作**；
这些操作要先经过校验、在预演台显示差异预览、由人工确认后才落库。

本模块只做**纯计算**（输入场景 dict，输出新场景 dict + 校验/差异结果），不碰数据库——
加载与保存由调用方负责，因此这里可以完整单测。

四条硬性规则（来自 design §5.3）：
1. 操作类型必须在白名单内；
2. **revision 不匹配时整批拒绝**——不是逐条。场景已经动过，Agent 的前提就过期了，
   挑几条能用的去执行只会拼出一个谁都没预料的中间态；
3. **被锁定的节点/机位只能读不能写**；
4. 落库必须重新校验一次（"预览通过"不代表"落库时仍然通过"，两次之间场景可能已变）。
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from app.services.previs.motion import HUMAN_PARAM_CHANNELS, channel_limit_reason, pose_field_reasons

#: design §5.3 的操作词表。与前端 `types.ts` 的 `PrevisOperationType` 一致。
PREVIS_OPERATION_TYPES = (
    "add_node",
    "update_transform",
    "set_camera",
    "add_keyframe",
    "remove_keyframe",
    "capture_reference",
    # 语义操作（design §5.3 扩展）：让外部（含 AI）说"这个人身高 1.8m、做行走"，
    # 而不是让它往 `metadata` 里塞键值。与底层操作并存是刻意的：
    # 底层操作管"精确改一个值"，语义操作管"按意图改一个对象"。
    "set_human_proxy",
    "assign_motion",
    # 初稿生成（tasks 4.1–4.4）需要的两个词：**没有它们，初稿就没法独立成立**——
    # 未绑定机位的独立场景无法给出"景别与镜头角度"，也无法把分镜格时长写进场景，
    # 只能产出一堆"人身位对但没机位"的半成品。二者在前端操作词表里本来就有
    # （`add_camera` / `set_duration` 是本地编辑产生的），补到这里是**对齐**而不是新造概念。
    "add_camera",
    "set_duration",
)

#: 需要指向已存在目标的操作（add_node 不需要，它是新建）
_TARGETED_TYPES = (
    "update_transform",
    "set_camera",
    "add_keyframe",
    "remove_keyframe",
    "set_human_proxy",
    "assign_motion",
)

#: 节点种类白名单，与前端 `types.ts` 的 `PrevisNodeKind` 一致。
#:
#: 为什么必须有：`add_node` 原来整包接收 `payload.node`，一个幻觉出来的 `kind: "dragon"`
#: 会被**静默存进场景**，前端 `normalizeSceneData` 再把它丢掉——结果是"落库成功但节点消失"，
#: 两边都以为是对面的问题。校验阶段拒绝、原因写清楚，代价只是一次比较。
NODE_KINDS = ("asset_model", "human_proxy", "primitive", "panorama", "light")
PRIMITIVE_KINDS = ("box", "sphere", "cylinder", "plane")
LIGHT_KINDS = ("point", "spot", "directional")

#: 人形占位的姿势预设，与前端 `HUMAN_PROXY_POSES` 的 key 一致。
HUMAN_PROXY_POSES = ("stand", "tpose", "walk", "sit", "wave", "point")
#: 身高范围（米），与前端 `HUMAN_PROXY_HEIGHT` 一致。
HUMAN_PROXY_HEIGHT = (0.5, 2.5)
#: 动作引用前缀，与前端 `motionRuntime.ts` 的 `MOTION_REF_PREFIX` 一致。
MOTION_REF_PREFIX = "motion:"

_TRANSFORM_KEYS = ("position", "rotation", "scale")
_KEYFRAME_PROPERTIES = ("position", "rotation", "scale", "camera_target", "camera_fov", "animation_clip")

#: 成像面宽度（mm），与前端 `optics.ts` 的 SENSOR_FORMATS 保持一致。
#: 前端是渲染的事实来源；这里只用于让落库的数据自洽（fov 与焦距不能各说各话）。
_SENSOR_WIDTH_MM = {
    "full_frame": 36.0,
    "super_35": 24.89,
    "alexa_lf": 36.7,
    "aps_c": 23.5,
    "m4_3": 17.3,
    "super_16": 12.52,
}
#: 变形宽银幕的横向压缩比
_SENSOR_SQUEEZE = {"anamorphic_2x": 2}
_DEFAULT_SENSOR = "full_frame"

_MAX_NODES = 200
_MAX_CAMERAS = 50
_MAX_KEYFRAMES = 2000


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _effective_width_mm(sensor_format: str) -> float:
    width = _SENSOR_WIDTH_MM.get(sensor_format, _SENSOR_WIDTH_MM[_DEFAULT_SENSOR])
    return width * _SENSOR_SQUEEZE.get(sensor_format, 1)


def _focal_from_fov(fov_deg: float, sensor_format: str) -> float:
    """由水平视角反求焦距——与前端 `focalLengthFromFov` 同一公式。

    为什么后端也要算：若只改 `fov` 而不动 `focalLength`，前端 `normalizeCamera` 会
    在载入时按旧焦距把 fov 重算回去，等于这次改动被静默丢弃。
    """
    import math

    # 与前端 `cameraMoves.ts` 的 FOV_RANGE 一致（8–120）：两处都夹同一个区间，
    # 否则"校验放过的值"和"派生出的焦距"会各说各话。
    fov = max(8.0, min(120.0, float(fov_deg)))
    width = _effective_width_mm(sensor_format)
    return round(width / (2 * math.tan(math.radians(fov) / 2)), 1)


def fov_from_focal(focal_mm: float, sensor_format: str = _DEFAULT_SENSOR) -> float:
    """由焦距反求水平视角——与前端 `fovFromFocalLength` 同一公式，是 `_focal_from_fov` 的逆。

    为什么需要它：`set_camera` 是"改 fov，焦距跟着变"；而 `add_camera` 与初稿生成是从
    **焦距**出发的（摄影上"用哪支镜头"才是意图）。若不把 fov 一起算对，前端 `normalizeCamera`
    载入时会按焦距把 fov 重算成另一个值，这次改动等于白做——这正是 `set_camera` 那条注释
    里记过的同一个坑，方向相反而已。
    """
    import math

    width = _effective_width_mm(sensor_format)
    focal = max(1.0, float(focal_mm))
    return round(math.degrees(2 * math.atan(width / (2 * focal))), 2)


def _number_reason(label: str, value: Any, low: float, high: float) -> Optional[str]:
    """数值范围校验，返回人话原因（合法返回 `None`）。

    布尔值单独挡：Python 里 `True` 是 `int` 的实例，`{"height": True}` 会静默变成 1.0 米
    （与 `motion._clean_keys`、`channel_limit_reason` 同一条理由）。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return f"{label} 需要一个数值，收到 {value!r}"
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return f"{label} 需要一个有限数值，收到 {value!r}"
    if number < low or number > high:
        return f"{label}={number:g} 超出范围 {low:g}–{high:g}"
    return None


def _human_proxy_pose_reason(pose: Any) -> Optional[str]:
    """姿势必须是**已知预设 key**：未知值不会被渲染层认出来，只会静默回落成站立。"""
    if not isinstance(pose, str) or pose not in HUMAN_PROXY_POSES:
        return f"未知的姿势：{pose!r}；可用姿势为 {'/'.join(HUMAN_PROXY_POSES)}"
    return None


def _human_proxy_joints_reasons(joints: Any) -> list[str]:
    """校验自定义关节角度（**按字段**组织的姿势，与前端 `HumanProxyPose` 同形）：坏字段只报自己。"""
    if not isinstance(joints, dict):
        return [f"poseJoints 需要一个对象（字段 → 角度），收到 {type(joints).__name__}"]
    return pose_field_reasons(joints)


def _motion_ref_reason(value: Any, motion_carriers: Optional[Mapping[str, str]]) -> Optional[str]:
    """校验动作引用：`''` 表示清除（合法），其余必须是存在且载体匹配的 `motion:<slug>`。

    **清单不可用时选择拒绝而不是放过**：一个拼错的动作标识落库后的表现是"下拉里没有它、
    选了没反应"，排查成本远高于当场拒绝。这与 `capture_reference` 的处理同一条原则。
    """
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not value.startswith(MOTION_REF_PREFIX):
        return (
            f"动作引用必须形如 '{MOTION_REF_PREFIX}<动作标识>'（收到 {value!r}）；"
            "动作标识见 list_previs_motions"
        )
    slug = value[len(MOTION_REF_PREFIX):].strip()
    if not slug:
        return f"动作引用缺少动作标识：{value!r}"
    if motion_carriers is None:
        return "动作清单当前不可用，无法校验动作引用；请稍后重试，或这次先不引用动作"
    if slug not in motion_carriers:
        return f"动作不存在：{slug}（可用动作见 list_previs_motions）"
    carrier = str(motion_carriers.get(slug) or "")
    if carrier != "params":
        return (
            f"动作 {slug} 的载体是 {carrier or '(未记录)'}，不能驱动人形占位——"
            "人形占位只接受 params（参数型）动作"
        )
    return None


def _node_reasons(node: dict[str, Any], *, motion_carriers: Optional[Mapping[str, str]]) -> list[str]:
    """校验一个新节点，返回原因列表（空列表 = 通过）。"""
    kind = str(node.get("kind") or "")
    if kind not in NODE_KINDS:
        return [f"未知的节点种类：{kind or '(空)'}；可用种类为 {'/'.join(NODE_KINDS)}"]
    if node.get("metadata") is not None and not isinstance(node.get("metadata"), dict):
        return [f"metadata 需要一个对象，收到 {type(node.get('metadata')).__name__}"]

    metadata = _as_dict(node.get("metadata"))
    reasons: list[str] = []

    if kind == "human_proxy":
        if "height" in metadata:
            reason = _number_reason("height", metadata["height"], *HUMAN_PROXY_HEIGHT)
            if reason:
                reasons.append(reason)
        if "pose" in metadata:
            reason = _human_proxy_pose_reason(metadata["pose"])
            if reason:
                reasons.append(reason)
        if "poseJoints" in metadata:
            reasons.extend(_human_proxy_joints_reasons(metadata["poseJoints"]))
        if metadata.get("animationClip"):
            reason = _motion_ref_reason(metadata["animationClip"], motion_carriers)
            if reason:
                reasons.append(f"animationClip：{reason}")
    elif kind == "primitive":
        primitive = str(metadata.get("primitive") or "box")
        if primitive not in PRIMITIVE_KINDS:
            reasons.append(f"未知的几何体种类：{primitive}；可用 {'/'.join(PRIMITIVE_KINDS)}")
    elif kind == "light":
        light = str(metadata.get("light") or "point")
        if light not in LIGHT_KINDS:
            reasons.append(f"未知的灯光种类：{light}；可用 {'/'.join(LIGHT_KINDS)}")
    elif kind == "asset_model" and not str(node.get("assetId") or ""):
        # 模型节点必须指向素材库资产（只存引用，不复制二进制）
        reasons.append("asset_model 节点需要 assetId（模型来自素材库，二进制不复制进场景）")

    return reasons


def _vec3_reason(label: str, value: Any) -> Optional[str]:
    """校验 `[x, y, z]` 三元组，返回人话原因（合法返回 `None`）。"""
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return f"{label} 需要 [x, y, z] 三个数值，收到 {value!r}"
    for index, item in enumerate(value):
        if isinstance(item, bool) or not isinstance(item, (int, float)) or item != item:
            return f"{label}[{index}] 需要数值，收到 {item!r}"
    return None


def _camera_reasons(payload: dict[str, Any]) -> list[str]:
    """校验新建机位的参数。机位是"光学事实"的载体，因此焦距与画幅要一起自洽。"""
    if not any(key in payload for key in ("position", "target", "fov", "focalLength")):
        return ["add_camera 需要至少提供 position / target / fov / focalLength 之一"]

    reasons: list[str] = []
    for key in ("position", "target"):
        if key in payload:
            reason = _vec3_reason(key, payload[key])
            if reason:
                reasons.append(reason)
    if "sensorFormat" in payload and str(payload["sensorFormat"]) not in _SENSOR_WIDTH_MM:
        reasons.append(f"未知的画幅：{payload['sensorFormat']}；可用 {'/'.join(_SENSOR_WIDTH_MM)}")
    if "fov" in payload:
        reason = _number_reason("fov", payload["fov"], 8.0, 120.0)
        if reason:
            reasons.append(reason)
    if "focalLength" in payload:
        reason = _number_reason("focalLength", payload["focalLength"], 4.0, 400.0)
        if reason:
            reasons.append(reason)
    if "name" in payload and not isinstance(payload["name"], str):
        reasons.append("name 需要字符串")
    return reasons


def find_target(scene: dict[str, Any], target_id: str) -> tuple[str, dict[str, Any] | None]:
    """按稳定 ID 找目标，返回 `(kind, 对象)`，kind 为 node / camera / ''。"""
    if not target_id:
        return "", None
    for node in _as_list(scene.get("nodes")):
        if isinstance(node, dict) and str(node.get("id") or "") == target_id:
            return "node", node
    for camera in _as_list(scene.get("cameras")):
        if isinstance(camera, dict) and str(camera.get("id") or "") == target_id:
            return "camera", camera
    return "", None


def _describe(operation_type: str, target_id: str, payload: dict[str, Any]) -> str:
    """给操作一句人看的摘要——操作历史是审计线索，不是机器日志。"""
    if operation_type == "add_node":
        name = str(_as_dict(payload.get("node")).get("name") or "")
        return f"新增节点 {name or target_id or '(新建)'}"
    if operation_type == "update_transform":
        channels = [key for key in _TRANSFORM_KEYS if key in payload]
        return f"更新 {target_id} 的 {'/'.join(channels) or '变换'}"
    if operation_type == "set_camera":
        channels = [key for key in ("position", "target", "fov") if key in payload]
        return f"设置机位 {target_id} 的 {'/'.join(channels) or '参数'}"
    if operation_type == "add_keyframe":
        return f"第 {payload.get('frame')} 帧给 {target_id} 的 {payload.get('property')} 打点"
    if operation_type == "remove_keyframe":
        return f"删除 {target_id} 在第 {payload.get('frame')} 帧的 {payload.get('property')} 关键帧"
    if operation_type == "set_human_proxy":
        channels = [key for key in ("height", "pose", "poseJoints") if key in payload]
        return f"设置 {target_id} 的 {'/'.join(channels) or '人形参数'}"
    if operation_type == "assign_motion":
        motion = str(payload.get("motion") or "")
        return f"给 {target_id} {'清除动作' if not motion else f'指定动作 {motion}'}"
    if operation_type == "add_camera":
        return f"新增机位 {payload.get('name') or '(新建)'}"
    if operation_type == "set_duration":
        if "frames" in payload:
            return f"把场景时长设为 {payload.get('frames')} 帧"
        return f"把场景时长设为 {payload.get('seconds')} 秒"
    return f"{operation_type} {target_id}".strip()


def validate_operations(
    scene: dict[str, Any],
    operations: list[Any],
    *,
    expected_revision: int,
    current_revision: int,
    motion_carriers: Optional[Mapping[str, str]] = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """校验一批操作，返回 `(accepted, rejected)`。

    不做任何修改。**revision 不匹配时整批拒绝**（理由见模块文档）。

    `motion_carriers` 是 `动作标识 → 载体` 的映射（由调用方查库后传入，见
    `motion_service.motion_carriers`）。本模块是纯函数、不碰数据库，因此"动作是否存在、
    载体是否匹配"这条事实必须由外部喂进来；**传 None 表示清单不可用，此时任何动作引用
    都会被拒绝**而不是放过（放过一个拼错的引用，表现是"下拉里没有它、选了没反应"）。
    """
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    #: 进行中的场景副本：每通过一条操作就把它应用上去，于是**同一批里的后续操作能引用
    #: 前面刚建出来的对象**（初稿就是"先建人、再给这个人打位移关键帧"这种形状）。
    #: 不这么做的话，这类批次会"落库能成功、校验先拒绝"——`apply_operations` 本来就是顺序应用的，
    #: 两边语义不一致本身就是缺陷。
    working: dict[str, Any] = scene

    def reject(index: int, operation_type: str, target_id: str, reason: str) -> None:
        rejected.append({
            "index": index,
            "type": operation_type,
            "target_id": target_id,
            "reason": reason,
        })

    def accept(operation_type: str, target_id: str, payload: dict[str, Any]) -> None:
        entry = {"type": operation_type, "targetId": target_id, "payload": payload,
                 "summary": _describe(operation_type, target_id, payload)}
        accepted.append(entry)
        nonlocal working
        working, _ = apply_operations(working, [entry])

    if int(expected_revision) != int(current_revision):
        # 整批拒绝：场景已变，Agent 的前提过期了
        for index, operation in enumerate(operations or []):
            raw = _as_dict(operation)
            reject(
                index,
                str(raw.get("type") or ""),
                str(raw.get("targetId") or ""),
                f"场景已被修改（期望 revision {expected_revision}，当前 {current_revision}），整批操作作废，请重新读取摘要后再提",
            )
        return accepted, rejected

    for index, operation in enumerate(operations or []):
        raw = _as_dict(operation)
        operation_type = str(raw.get("type") or "")
        target_id = str(raw.get("targetId") or "")
        payload = _as_dict(raw.get("payload"))

        if operation_type not in PREVIS_OPERATION_TYPES:
            reject(index, operation_type, target_id, f"未知操作类型：{operation_type or '(空)'}")
            continue

        if operation_type == "capture_reference":
            # 截图必须由预演台客户端发起（需要浏览器渲染），工具无法代替。
            # 与其静默接受一个做不到的事，不如明确拒绝并说明原因。
            reject(index, operation_type, target_id, "截图回流必须由预演台客户端发起，工具无法代替（需要浏览器渲染与上传）")
            continue

        if operation_type == "add_node":
            node = _as_dict(payload.get("node"))
            if not node:
                reject(index, operation_type, target_id, "add_node 需要 payload.node")
                continue
            # 白名单 + metadata 校验：宁可拒掉一个幻觉节点，也不要存进去一个"落库成功但前端不认"的对象
            reasons = _node_reasons(node, motion_carriers=motion_carriers)
            if reasons:
                reject(index, operation_type, target_id, "；".join(reasons))
                continue
            if len(_as_list(scene.get("nodes"))) >= _MAX_NODES:
                reject(index, operation_type, target_id, f"节点数已达上限 {_MAX_NODES}")
                continue
            accept(operation_type, target_id, payload)
            continue

        if operation_type == "add_camera":
            reasons = _camera_reasons(payload)
            if reasons:
                reject(index, operation_type, target_id, "；".join(reasons))
                continue
            if len(_as_list(scene.get("cameras"))) >= _MAX_CAMERAS:
                reject(index, operation_type, target_id, f"机位数已达上限 {_MAX_CAMERAS}")
                continue
            accept(operation_type, target_id, payload)
            continue

        if operation_type == "set_duration":
            try:
                fps = max(1, int(scene.get("fps") or 24))
            except (TypeError, ValueError):
                fps = 24
            max_frames = 60 * fps  # 与前端时长输入的上限（60 秒）一致
            frames: int | None = None
            reason: str | None = None
            if "frames" in payload:
                raw_frames = payload.get("frames")
                if isinstance(raw_frames, bool) or not isinstance(raw_frames, (int, float)):
                    reason = f"frames 需要数值，收到 {raw_frames!r}"
                else:
                    frames = int(round(float(raw_frames)))
            elif "seconds" in payload:
                raw_seconds = payload.get("seconds")
                if isinstance(raw_seconds, bool) or not isinstance(raw_seconds, (int, float)):
                    reason = f"seconds 需要数值，收到 {raw_seconds!r}"
                else:
                    frames = int(round(float(raw_seconds) * fps))
            else:
                reason = "set_duration 需要 frames 或 seconds"
            if reason is None and frames is not None and not 1 <= frames <= max_frames:
                reason = f"时长 {frames} 帧超出范围 1–{max_frames}（{fps}fps × 60 秒）"
            if reason:
                reject(index, operation_type, target_id, reason)
                continue
            # 秒与帧只保留一个真值：校验阶段就把 seconds 归一成 frames 写回 payload，
            # 落库与预览用同一个数——两处各算一遍迟早会漂。
            accept(operation_type, target_id, {**payload, "frames": frames})
            continue

        # 以下都是针对已有目标的操作（在**进行中的副本**上找，见 `accept` 的注释）
        kind, target = find_target(working, target_id)
        if target is None:
            reject(index, operation_type, target_id, f"场景中不存在 id 为 {target_id or '(空)'} 的节点或机位")
            continue

        if target.get("locked"):
            reject(index, operation_type, target_id,
                   f"{'节点' if kind == 'node' else '机位'} {target_id} 已锁定，只能读取，不能更新")
            continue

        if operation_type == "update_transform":
            if kind != "node":
                reject(index, operation_type, target_id, "update_transform 只能作用于节点")
                continue
            if not any(key in payload for key in _TRANSFORM_KEYS):
                reject(index, operation_type, target_id,
                       f"update_transform 需要至少提供 {'/'.join(_TRANSFORM_KEYS)} 之一")
                continue
            accept(operation_type, target_id, payload)
            continue

        if operation_type == "set_camera":
            if kind != "camera":
                reject(index, operation_type, target_id, "set_camera 只能作用于机位")
                continue
            if not any(key in payload for key in ("position", "target", "fov")):
                reject(index, operation_type, target_id, "set_camera 需要至少提供 position/target/fov 之一")
                continue
            accept(operation_type, target_id, payload)
            continue

        if operation_type in ("add_keyframe", "remove_keyframe"):
            property_name = str(payload.get("property") or "")
            if property_name not in _KEYFRAME_PROPERTIES:
                reject(index, operation_type, target_id, f"关键帧属性不合法：{property_name or '(空)'}")
                continue
            try:
                frame = int(payload.get("frame"))
            except Exception:
                reject(index, operation_type, target_id, "关键帧需要一个整数 frame")
                continue
            if frame < 0:
                reject(index, operation_type, target_id, "frame 不能为负")
                continue
            if operation_type == "add_keyframe" and "value" not in payload:
                reject(index, operation_type, target_id, "add_keyframe 需要 payload.value")
                continue
            accept(operation_type, target_id, payload)
            continue

        # 语义操作：只作用于人形占位节点（身高 / 姿势 / 动作都是"人形载体"的概念）
        if operation_type in ("set_human_proxy", "assign_motion"):
            if kind != "node":
                reject(index, operation_type, target_id, f"{operation_type} 只能作用于节点，不能作用于机位")
                continue
            node_kind = str(target.get("kind") or "")
            if node_kind != "human_proxy":
                reject(
                    index, operation_type, target_id,
                    f"{operation_type} 只能作用于人形占位节点；该节点是 {node_kind or '未知种类'}。"
                    "非人形对象请用 update_transform，或给它指定通用变换动作",
                )
                continue

            if operation_type == "set_human_proxy":
                if not any(key in payload for key in ("height", "pose", "poseJoints")):
                    reject(index, operation_type, target_id,
                           "set_human_proxy 需要至少提供 height / pose / poseJoints 之一")
                    continue
                if "motion" in payload:
                    reject(index, operation_type, target_id,
                           "动作请用 assign_motion：set_human_proxy 只负责身高与姿势")
                    continue
                reasons = []
                if "height" in payload:
                    reason = _number_reason("height", payload["height"], *HUMAN_PROXY_HEIGHT)
                    if reason:
                        reasons.append(reason)
                if "pose" in payload:
                    reason = _human_proxy_pose_reason(payload["pose"])
                    if reason:
                        reasons.append(reason)
                if "poseJoints" in payload:
                    reasons.extend(_human_proxy_joints_reasons(payload["poseJoints"]))
                if reasons:
                    reject(index, operation_type, target_id, "；".join(reasons))
                    continue
            else:  # assign_motion
                if "motion" not in payload:
                    reject(index, operation_type, target_id,
                           "assign_motion 需要 payload.motion（用 '' 表示清除当前动作）")
                    continue
                reason = _motion_ref_reason(payload.get("motion"), motion_carriers)
                if reason:
                    reject(index, operation_type, target_id, reason)
                    continue

            accept(operation_type, target_id, payload)
            continue

        reject(index, operation_type, target_id, "该操作类型尚未实现")

    return accepted, rejected


def apply_operations(scene: dict[str, Any], accepted: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """把已校验通过的操作落到场景副本上，返回 `(新场景, 已应用摘要)`。

    调用方必须先 `validate_operations`，本函数不再复核（校验与落库是两步，
    第二步之前场景若又变了，由调用方的 revision CAS 兜住）。
    """
    import copy
    import uuid

    next_scene = copy.deepcopy(scene)
    applied: list[dict[str, Any]] = []

    nodes = _as_list(next_scene.get("nodes"))
    cameras = _as_list(next_scene.get("cameras"))
    keyframes = _as_list(next_scene.get("keyframes"))

    for operation in accepted:
        # 每一轮先把本地集合同步回场景：`find_target` 读的是场景字典，而新建的节点/机位/关键帧
        # 先在本地列表里。不同步的话**同一批里后面的操作看不见前面刚建出来的对象**——
        # 表现是初稿这类"先建人、再给这个人打关键帧"的批次静默少做几步（不报错，只是没生效）。
        next_scene["nodes"] = nodes
        next_scene["cameras"] = cameras
        next_scene["keyframes"] = keyframes

        operation_type = str(operation.get("type") or "")
        target_id = str(operation.get("targetId") or "")
        payload = _as_dict(operation.get("payload"))

        if operation_type == "add_node":
            node = _as_dict(payload.get("node"))
            if not str(node.get("id") or ""):
                node["id"] = f"node_{uuid.uuid4().hex[:12]}"
            node.setdefault("visible", True)
            node.setdefault("locked", False)
            node.setdefault("metadata", {})
            nodes.append(node)
            applied.append({"type": operation_type, "target_id": node["id"], "summary": operation.get("summary") or ""})
            continue

        if operation_type == "add_camera":
            sensor_format = str(payload.get("sensorFormat") or _DEFAULT_SENSOR)
            fov_payload = payload.get("fov")
            focal_payload = payload.get("focalLength")
            # 焦距与 fov 必须同时自洽：前端 `normalizeCamera` 载入时会按焦距重算 fov，
            # 只写一个的后果是"落库的值和画面上看到的不是一个"（`set_camera` 那条注释记过同一个坑）
            if fov_payload is not None:
                fov = float(fov_payload)
                focal = float(focal_payload) if focal_payload is not None else _focal_from_fov(fov, sensor_format)
            else:
                focal = float(focal_payload) if focal_payload is not None else 35.0
                fov = fov_from_focal(focal, sensor_format)
            camera_id = str(payload.get("id") or f"camera_{uuid.uuid4().hex[:12]}")
            cameras.append({
                "id": camera_id,
                "name": str(payload.get("name") or f"机位 {len(cameras) + 1}"),
                "transform": {
                    "position": list(payload.get("position") or [4, 3, 6]),
                    "rotation": [0, 0, 0, 1],
                },
                "target": list(payload.get("target") or [0, 0.8, 0]),
                "fov": fov,
                "focalLength": focal,
                "sensorFormat": sensor_format,
                "locked": False,
            })
            # 场景本来没有活动机位时顺手设为活动机位：截图回流与导出**只在活动机位下可用**，
            # 新建了机位却不激活，用户下一步就撞上"截不了图"
            if not str(next_scene.get("activeCameraId") or ""):
                next_scene["activeCameraId"] = camera_id
            applied.append({"type": operation_type, "target_id": camera_id, "summary": operation.get("summary") or ""})
            continue

        if operation_type == "set_duration":
            next_scene["durationFrames"] = int(payload.get("frames"))
            applied.append({"type": operation_type, "target_id": "", "summary": operation.get("summary") or ""})
            continue

        kind, target = find_target(next_scene, target_id)
        if target is None:
            continue

        if operation_type == "update_transform":
            transform = _as_dict(target.get("transform"))
            for key in _TRANSFORM_KEYS:
                if key in payload:
                    transform[key] = payload[key]
            target["transform"] = transform
            applied.append({"type": operation_type, "target_id": target_id, "summary": operation.get("summary") or ""})
            continue

        if operation_type == "set_camera":
            if "position" in payload:
                transform = _as_dict(target.get("transform"))
                transform["position"] = payload["position"]
                target["transform"] = transform
            if "target" in payload:
                target["target"] = payload["target"]
            if "fov" in payload:
                try:
                    fov = float(payload["fov"])
                except Exception:
                    fov = None
                if fov is not None:
                    sensor_format = str(target.get("sensorFormat") or _DEFAULT_SENSOR)
                    target["fov"] = fov
                    # 同步焦距：否则前端 normalizeCamera 会按旧焦距把 fov 改回去，这次改动等于白做
                    target["focalLength"] = _focal_from_fov(fov, sensor_format)
                    target["sensorFormat"] = sensor_format
            applied.append({"type": operation_type, "target_id": target_id, "summary": operation.get("summary") or ""})
            continue

        if operation_type == "add_keyframe":
            if len(keyframes) >= _MAX_KEYFRAMES:
                continue
            frame = int(payload.get("frame"))
            property_name = str(payload.get("property"))
            keyframes = [
                item for item in keyframes
                if not (isinstance(item, dict) and str(item.get("targetId") or "") == target_id
                        and str(item.get("property") or "") == property_name and int(item.get("frame", -1)) == frame)
            ]
            keyframes.append({
                "id": str(payload.get("id") or f"kf_{uuid.uuid4().hex[:12]}"),
                "targetId": target_id,
                "property": property_name,
                "frame": frame,
                "value": payload.get("value"),
                # 旋转缺省 slerp、动画 clip 缺省 step，与前端 `interpolationFor` 一致
                "interpolation": str(payload.get("interpolation") or ("slerp" if property_name == "rotation"
                                                                      else "step" if property_name == "animation_clip"
                                                                      else "linear")),
            })
            applied.append({"type": operation_type, "target_id": target_id, "summary": operation.get("summary") or ""})
            continue

        if operation_type == "remove_keyframe":
            frame = int(payload.get("frame"))
            property_name = str(payload.get("property"))
            keyframes = [
                item for item in keyframes
                if not (isinstance(item, dict) and str(item.get("targetId") or "") == target_id
                        and str(item.get("property") or "") == property_name and int(item.get("frame", -1)) == frame)
            ]
            applied.append({"type": operation_type, "target_id": target_id, "summary": operation.get("summary") or ""})
            continue

        if operation_type == "set_human_proxy":
            metadata = _as_dict(target.get("metadata"))
            if "height" in payload:
                metadata["height"] = float(payload["height"])
            if "pose" in payload:
                metadata["pose"] = str(payload["pose"])
                # 与前端一致：**选预设 = 放弃自定义关节角度**。前端 `resolveHumanProxyPose` 是
                # "自定义按字段覆盖预设"，若不清掉自定义值，会出现"设了姿势却没变化"
                metadata.pop("poseJoints", None)
            if "poseJoints" in payload:
                # 值保持原样（三元组字段是数组、单值字段是数字）：这里已校验过，
                # 前端 `sanitizeHumanProxyPose` 还会再夹一次（两道防线）
                metadata["poseJoints"] = {
                    str(channel): value
                    for channel, value in _as_dict(payload["poseJoints"]).items()
                }
            target["metadata"] = metadata
            applied.append({"type": operation_type, "target_id": target_id, "summary": operation.get("summary") or ""})
            continue

        if operation_type == "assign_motion":
            metadata = _as_dict(target.get("metadata"))
            # 写**静态值**（`metadata.animationClip`）：这是"当前动作"的落点，前端的动作下拉读它。
            # 不打关键帧——需要"第几帧换动作"时用 add_keyframe(animation_clip)，两件事互不覆盖。
            metadata["animationClip"] = str(payload.get("motion") or "")
            target["metadata"] = metadata
            applied.append({"type": operation_type, "target_id": target_id, "summary": operation.get("summary") or ""})
            continue

    next_scene["nodes"] = nodes
    next_scene["cameras"] = cameras
    next_scene["keyframes"] = keyframes
    return next_scene, applied


def diff_operations(scene: dict[str, Any], accepted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """预览：逐条给出「改前 / 改后」的**相关字段**，供预演台渲染差异。

    刻意只给被改动的字段——整份场景塞进预览既读不出重点，也会把提示词撑爆。
    """
    import copy

    preview: list[dict[str, Any]] = []
    for operation in accepted:
        operation_type = str(operation.get("type") or "")
        target_id = str(operation.get("targetId") or "")
        payload = _as_dict(operation.get("payload"))

        if operation_type == "add_node":
            node = _as_dict(payload.get("node"))
            preview.append({
                "index": len(preview),
                "type": operation_type,
                "target_id": str(node.get("id") or "(新建)"),
                "summary": operation.get("summary") or "",
                "before": None,
                # metadata 必须一起给：身高/姿势/动作都住在它里面，只给 name/kind/transform
                # 会让人（和 AI）看不出"新建的人形是站着还是走着"
                "after": {
                    "name": node.get("name"),
                    "kind": node.get("kind"),
                    "assetId": node.get("assetId"),
                    "transform": node.get("transform"),
                    "metadata": node.get("metadata"),
                },
            })
            continue

        # 新建类与场景级操作**不指向已有对象**，必须在 `find_target` 之前处理：
        # 否则会被"目标不存在就跳过"那条守卫吞掉，预览里什么都不显示
        if operation_type == "add_camera":
            preview.append({
                "index": len(preview),
                "type": operation_type,
                "target_id": "(新建)",
                "summary": operation.get("summary") or "",
                "before": None,
                # 焦距与 fov 一起给：同一支镜头的两种表达，改一个另一个会跟着变
                "after": {
                    "name": payload.get("name"),
                    "position": payload.get("position"),
                    "target": payload.get("target"),
                    "fov": payload.get("fov"),
                    "focalLength": payload.get("focalLength"),
                    "sensorFormat": payload.get("sensorFormat"),
                },
            })
            continue

        if operation_type == "set_duration":
            preview.append({
                "index": len(preview),
                "type": operation_type,
                "target_id": "(场景)",
                "summary": operation.get("summary") or "",
                "before": {"frames": int(scene.get("durationFrames") or 0)},
                "after": {"frames": int(payload.get("frames"))},
            })
            continue

        kind, target = find_target(scene, target_id)
        if target is None:
            continue
        before = copy.deepcopy(target)

        if operation_type == "update_transform":
            keys = [key for key in _TRANSFORM_KEYS if key in payload]
            after = {key: payload[key] for key in keys}
            preview.append({
                "index": len(preview),
                "type": operation_type,
                "target_id": target_id,
                "target_kind": kind,
                "summary": operation.get("summary") or "",
                "before": {key: _as_dict(before.get("transform")).get(key) for key in keys},
                "after": after,
            })
            continue

        if operation_type == "set_camera":
            changed = {}
            for key in ("position", "target", "fov"):
                if key in payload:
                    changed[key] = {"before": (before.get(key) if key != "position"
                                               else _as_dict(before.get("transform")).get("position")),
                                    "after": payload[key]}
            if "fov" in payload:
                sensor_format = str(target.get("sensorFormat") or _DEFAULT_SENSOR)
                changed["focalLength"] = {"before": before.get("focalLength"),
                                         "after": _focal_from_fov(float(payload["fov"]), sensor_format)}
            preview.append({
                "index": len(preview),
                "type": operation_type,
                "target_id": target_id,
                "target_kind": kind,
                "summary": operation.get("summary") or "",
                "before": changed and {key: item["before"] for key, item in changed.items()} or {},
                "after": {key: item["after"] for key, item in changed.items()},
            })
            continue

        if operation_type in ("add_keyframe", "remove_keyframe"):
            preview.append({
                "index": len(preview),
                "type": operation_type,
                "target_id": target_id,
                "target_kind": kind,
                "summary": operation.get("summary") or "",
                "before": {"frame": payload.get("frame"), "property": payload.get("property")},
                "after": ({"frame": payload.get("frame"), "property": payload.get("property"), "value": payload.get("value")}
                          if operation_type == "add_keyframe" else None),
            })
            continue

        if operation_type == "set_human_proxy":
            metadata = _as_dict(before.get("metadata"))
            keys = [key for key in ("height", "pose", "poseJoints") if key in payload]
            preview.append({
                "index": len(preview),
                "type": operation_type,
                "target_id": target_id,
                "target_kind": kind,
                "summary": operation.get("summary") or "",
                "before": {key: metadata.get(key) for key in keys},
                "after": {key: payload[key] for key in keys},
            })
            continue

        if operation_type == "assign_motion":
            metadata = _as_dict(before.get("metadata"))
            preview.append({
                "index": len(preview),
                "type": operation_type,
                "target_id": target_id,
                "target_kind": kind,
                "summary": operation.get("summary") or "",
                "before": {"motion": str(metadata.get("animationClip") or "")},
                "after": {"motion": str(payload.get("motion") or "")},
            })
            continue

    return preview
