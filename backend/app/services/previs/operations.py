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

from typing import Any

#: design §5.3 的操作词表。与前端 `types.ts` 的 `PrevisOperationType` 一致。
PREVIS_OPERATION_TYPES = (
    "add_node",
    "update_transform",
    "set_camera",
    "add_keyframe",
    "remove_keyframe",
    "capture_reference",
)

#: 需要指向已存在目标的操作（add_node 不需要，它是新建）
_TARGETED_TYPES = ("update_transform", "set_camera", "add_keyframe", "remove_keyframe")

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

    fov = max(10.0, min(120.0, float(fov_deg)))
    width = _effective_width_mm(sensor_format)
    return round(width / (2 * math.tan(math.radians(fov) / 2)), 1)


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
    return f"{operation_type} {target_id}".strip()


def validate_operations(
    scene: dict[str, Any],
    operations: list[Any],
    *,
    expected_revision: int,
    current_revision: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """校验一批操作，返回 `(accepted, rejected)`。

    不做任何修改。**revision 不匹配时整批拒绝**（理由见模块文档）。
    """
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    def reject(index: int, operation_type: str, target_id: str, reason: str) -> None:
        rejected.append({
            "index": index,
            "type": operation_type,
            "target_id": target_id,
            "reason": reason,
        })

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
            if len(_as_list(scene.get("nodes"))) >= _MAX_NODES:
                reject(index, operation_type, target_id, f"节点数已达上限 {_MAX_NODES}")
                continue
            accepted.append({"type": operation_type, "targetId": target_id, "payload": payload,
                             "summary": _describe(operation_type, target_id, payload)})
            continue

        # 以下都是针对已有目标的操作
        kind, target = find_target(scene, target_id)
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
            accepted.append({"type": operation_type, "targetId": target_id, "payload": payload,
                             "summary": _describe(operation_type, target_id, payload)})
            continue

        if operation_type == "set_camera":
            if kind != "camera":
                reject(index, operation_type, target_id, "set_camera 只能作用于机位")
                continue
            if not any(key in payload for key in ("position", "target", "fov")):
                reject(index, operation_type, target_id, "set_camera 需要至少提供 position/target/fov 之一")
                continue
            accepted.append({"type": operation_type, "targetId": target_id, "payload": payload,
                             "summary": _describe(operation_type, target_id, payload)})
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
            accepted.append({"type": operation_type, "targetId": target_id, "payload": payload,
                             "summary": _describe(operation_type, target_id, payload)})
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
                "after": {"name": node.get("name"), "kind": node.get("kind"), "transform": node.get("transform")},
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

    return preview
