"""分镜格 → 预演初稿：把**已经写好的文字**翻译成受限操作集（design D5 / D8、tasks 4.1–4.4）。

这一层的职责是**翻译，不是创作**。分镜格里已经写好了谁在场、怎么调度、什么景别、什么角度、
镜头多长；预演台要的是"谁站在哪、机位在哪、镜头多长"。翻译可以对账，创作只能碰运气——
"AI 出初稿"这条路线能被信任的前提就在这里。

五条自我约束：

1. **只读、不落库**：产出是一批受限操作（与人工编辑、Agent 用的是同一套词汇），要不要落库由
   既有的"预览 → 人工确认 → CAS 落库"链路决定。本模块不写任何数据库。
2. **纯函数 + 事实注入**：`build_previs_draft(scene, panel, prop_assets=...)` 只做计算，
   分镜格与"道具匹配到的素材"由调用方读好传进来，因此可以完整单测。
3. **默认值必须显式**：任何靠默认值填出来的字段都记进 `defaults[]`。**把"猜的"说成"推导的"**
   是这类功能最快失去信任的方式——用户改了三处，才发现另外五处是假装的。
4. **新建节点自带稳定 ID**：初稿要在同一批里"先建人、再给这个人打位移关键帧"，所以
   `add_node` 必须显式带 id（否则 id 由落库时生成，后续操作无从引用）。
5. **不确定就不做**：文字调度、镜头运动、背景这些"无法可靠换算成参数"的字段，宁可只写一条
   `warnings[]` 说明"本版没翻译、你可以怎么补"，也不凭空生成一堆看着很像那么回事的关键帧。

字段口径（与 `creative_project.service` 组装提示词时读的是同一套键）：
`characters`（人名字数组）、`blocking`、`shot_size`、`camera_angle`、`camera_motion`、`composition`、
`duration_seconds`/`duration`、`props`、`location`、`movement_path`、`panel_number`。
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Optional, Sequence

DEFAULT_FPS = 24
#: 眼睛高度占身高的比例：机位对准眼睛而不是脚下（1.70m 的人 ≈ 1.58m）
EYE_RATIO = 0.93
#: 默认画幅与成像面宽度（与 `operations._SENSOR_WIDTH_MM` 同一套取值）
DEFAULT_SENSOR = "full_frame"
SENSOR_WIDTH_MM = 36.0
#: 机位高度上限：鸟瞰在大距离下按俯角算会算出十几米高，那对预演没有意义（预演看的是"俯视感"）
MAX_CAMERA_HEIGHT = 6.0

#: 尺寸锚点（米）。**极薄一层**，只放"预演构图必须知道"的参照物，用来给人的身高一个默认档；
#: 素材库模型一律以自带包围盒为准、**不手写尺寸**（写错的尺寸比没有尺寸更糟，见 design 4.2）。
SIZE_ANCHORS: dict[str, Any] = {
    "person": {"short": 1.55, "medium": 1.70, "tall": 1.85},
    "desk": 0.75,
    "chair": 0.45,
    "door": 2.00,
    "car": {"height": 1.50, "length": 4.60},
    "tree": 6.00,
}
DEFAULT_HEIGHT = 1.70

# 档位匹配一律"最长命中优先"（`_match_ladder`）：否则 `medium close-up` 会先撞上 `medium`，
# 近景被当成中景——这类错在画面上只表现为"机位比想象的远一点"，很难被发现。
Ladder = Sequence[tuple[str, str, float, float]]

SHOT_SIZE_LADDER: tuple[tuple[str, str, float, float], ...] = (
    # (匹配词（`|` 分隔的备选**短语**，命中任一即可）, 档位名, 机位到主体距离 m, 焦距 mm)
    ("大特写|特写|extreme close|ecu|close-up|closeup|close", "特写", 1.4, 85.0),
    ("中近|近景|medium close|mcu", "近景", 2.5, 50.0),
    ("中景|medium shot", "中景", 4.0, 35.0),
    ("全景|全身|full shot|long shot", "全景", 6.0, 28.0),
    ("大远景|远景|wide shot|wide|extreme long", "远景", 12.0, 24.0),
)
DEFAULT_SHOT_SIZE = ("中景", 4.0, 35.0)

CAMERA_ANGLE_LADDER: tuple[tuple[str, str, float], ...] = (
    # (匹配词, 档位名, 俯仰角：正 = 俯视)。**高度由俯角与距离算出**，见 `_camera_position`。
    ("鸟瞰|顶视|bird|overhead", "鸟瞰", 55.0),
    ("俯视|略俯|高角度|high angle|slightly high", "俯视", 18.0),
    ("平视|eye level|eye-level|正拍|水平", "平视", 0.0),
    ("仰视|低角度|low angle|slightly low|微微仰", "仰视", -12.0),
    ("主观|第一人称|pov|point of view|screen pov", "主观", 0.0),
)
DEFAULT_CAMERA_ANGLE = ("平视", 0.0)

#: 机位绕主体的方位角（度，0 = 正对主体正面）
AZIMUTH_HINTS: tuple[tuple[str, str, float], ...] = (
    ("背面|背影|背后|from behind|back view", "背面", 170.0),
    ("侧拍|侧面|profile|side view|侧向", "侧面", 80.0),
    ("过肩|over the shoulder|over-the-shoulder|ots", "过肩", 35.0),
)

#: 构图 → 主体偏离画面中心的量（占画面宽度的比例，正 = 画面右侧）
COMPOSITION_HINTS: tuple[tuple[str, str, float], ...] = (
    ("左三分|left third", "左三分", -1 / 6),
    ("右三分|right third", "右三分", 1 / 6),
    ("三分|rule of thirds|thirds", "三分", 1 / 6),
    ("偏左|left", "偏左", -0.25),
    ("偏右|right", "偏右", 0.25),
    ("居中|中心|center|centre|中间|balanced", "居中", 0.0),
)
DEFAULT_COMPOSITION = ("居中", 0.0)

#: 分镜的动作描述 → 该角色的**动作库动作**（会动，用 assign_motion 指定）。
#: **刻意不含"走/跑"**：位移类动作单独演是"原地走"，而位移必须与关键帧配合——
#: 那类意图由 `movement_path` 或手动打关键帧表达，混进来只会得到一个原地踏步的角色。
ACTION_MOTION_HINTS: tuple[tuple[str, str], ...] = (
    ("鞠躬|弯腰", "bow"),
    ("蹲|蹲下|半蹲", "crouch"),
    ("沉思|思考|琢磨", "ponder"),
    ("挥手|招手|打招呼", "wave"),
    ("点头|同意", "nod"),
    ("摇头|否定", "shake-head"),
    ("回头|回望|回头看", "look-back"),
    ("低头", "look-down"),
    ("张望|环顾|四处看", "look-side"),
    ("抬眼|抬头看", "look-up"),
    ("指向|指着|指了指", "point"),
    ("坐下|坐在", "sit"),
)

#: 动作库里没有、但**预演高频**的动作，用自定义关节角度表达。"端托盘"就是典型：
#: 双臂前抬 + 屈肘，手落在身前腰胸之间。数值受 `HUMAN_PARAM_LIMITS` 约束，可安全过校验。
ACTION_JOINTS_HINTS: tuple[tuple[str, str, dict[str, Any]], ...] = (
    (
        "端|托|捧",
        "端着托盘（双臂前抬屈肘）",
        {
            "leftShoulder": [-55, 0, 6],
            "rightShoulder": [-55, 0, -6],
            "leftElbow": -78,
            "rightElbow": -78,
            "torso": [4, 0, 0],
        },
    ),
    ("抱臂|交叉|抱胸", "抱臂", {
        "leftShoulder": [-25, 0, 24],
        "rightShoulder": [-25, 0, -24],
        "leftElbow": -118,
        "rightElbow": -118,
    }),
)
BLOCKING_X_HINTS: tuple[tuple[str, float], ...] = (
    ("左|left", -0.8),
    ("右|right", 0.8),
    ("中央|居中|中间|center|centre", 0.0),
)
BLOCKING_Z_HINTS: tuple[tuple[str, float], ...] = (
    ("前景|靠近|身前|foreground|front", 0.6),
    ("背景|远处|身后|background|behind|far", -0.6),
    ("中央|居中|中间|center|centre", 0.0),
)
DEFAULT_SPACING_M = 0.8
#: 取"名字后多长一段文字"作为这个人的调度描述窗口
BLOCKING_WINDOW = 16


def _text(value: Any) -> str:
    return str(value or "").strip()


def _alternatives(markers: str) -> list[str]:
    """把 `|` 分隔的备选词拆开并小写化。

    **不能用空格分隔**：`medium close-up` 这类写法必须作为一个短语参与"最长命中"比较，
    拆成 `medium` 与 `close` 两个词之后，`medium`（中景）会赢过 `close`（特写），
    结果是"近景被判成中景"——画面上只表现为机位远了一点，很难发现。
    """
    return [item.strip().lower() for item in str(markers).split("|") if item.strip()]


def _match_ladder(text: str, ladder: Sequence[tuple[Any, ...]]) -> Optional[tuple[Any, ...]]:
    """最长命中优先的档位匹配，返回去掉匹配词后的元组；**没命中返回 `None`**。

    刻意不在这里回落到默认档：调用方需要区分"分镜写了、且命中了档位"与"分镜写了、但一个档位都没命中"
    ——后者必须记进 `defaults[]` 与 `warnings[]`。用"结果等于默认值"来判断会出假阳性：
    分镜写的正好就是默认档（比如"中景"）时会被误报成"没有对应档位"。
    """
    haystack = text.lower()
    best: tuple[int, tuple[Any, ...]] | None = None
    for entry in ladder:
        markers, *rest = entry
        for marker in _alternatives(str(markers)):
            if marker in haystack and (best is None or len(marker) > best[0]):
                best = (len(marker), tuple(rest))
    return best[1] if best else None


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return None if number != number else number


def _fov_from_focal(focal_mm: float) -> float:
    """由焦距求水平视角（与前端 `fovFromFocalLength` 同一公式）。

    初稿必须自己算：机位参数最终要过前端 `normalizeCamera`，只给焦距时它会重算 fov；
    若初稿给的 fov 与它算出来的不一致，人工在预演台看到的画面会与落库结果不同。
    """
    return round(math.degrees(2 * math.atan(SENSOR_WIDTH_MM / (2 * max(1.0, focal_mm)))), 2)


def _camera_position(
    *,
    anchor: tuple[float, float],
    distance: float,
    pitch_deg: float,
    azimuth_deg: float,
    eye_y: float,
) -> list[float]:
    """机位位置：由**俯角与距离**反推高度（而不是直接写高度）。

    这样"俯视/仰视"在几何上就是真的俯视/仰视——高度与角度自洽，换距离也不会破坏俯仰关系。
    上限 `MAX_CAMERA_HEIGHT`：鸟瞰在 12m 距离下按 55° 会算出十几米，那对预演没有意义。
    """
    height = eye_y + distance * math.tan(math.radians(pitch_deg))
    height = max(0.2, min(MAX_CAMERA_HEIGHT, height))
    azimuth = math.radians(azimuth_deg)
    return [
        round(anchor[0] + math.sin(azimuth) * distance, 3),
        round(height, 3),
        round(anchor[1] + math.cos(azimuth) * distance, 3),
    ]


def _composition_target(
    *,
    position: Sequence[float],
    target: list[float],
    anchor: tuple[float, float],
    distance: float,
    focal_mm: float,
    fraction: float,
) -> list[float]:
    """按构图偏移**注视点**（不是挪机位）：机位代表"从哪拍"，构图代表"主体落在画面哪里"。

    偏移量按真实光学换算（画面宽度 = 成像面宽 ÷ 焦距 × 距离），因此"三分线"在任何焦距下
    都落在真正的三分线上，而不是一个凭感觉的常数。
    """
    if not fraction:
        return target
    frame_width = SENSOR_WIDTH_MM / max(1.0, focal_mm) * distance
    # 视线方向是"注视点 − 机位"；写成"机位 − 注视点"会把画面的右向算成左向，
    # 于是"左三分"跑到右边去（这类符号错误在画面上只表现为构图反了，很容易被当成美学习惯放过去）
    view = [target[0] - position[0], 0.0, target[2] - position[2]]
    length = math.hypot(view[0], view[2]) or 1.0
    view = [view[0] / length, 0.0, view[2] / length]
    # 画面右向 = 视线 × up。见 `cameraMoves.ts` 里对同一条符号的注释
    right = [-view[2], 0.0, view[0]]
    offset = frame_width * float(fraction)
    return [round(anchor[0] + right[0] * offset, 3), target[1], round(anchor[1] + right[2] * offset, 3)]


def _match_value(text: str, hints: Sequence[tuple[str, float]], default: float) -> tuple[float, bool]:
    """最长命中优先地取一个数值，返回 `(值, 是否没命中)`。"""
    haystack = text.lower()
    best: tuple[int, float] | None = None
    for markers, value in hints:
        for marker in _alternatives(markers):
            if marker in haystack and (best is None or len(marker) > best[0]):
                best = (len(marker), value)
    return (best[1], False) if best else (default, True)


def _character_position(
    name: str,
    blocking: str,
    index: int,
    total: int,
    others: Sequence[str] = (),
) -> tuple[float, float, bool]:
    """从调度描述里取某个人的站位，返回 `(x, z, 是否完全没命中方向词)`。

    窗口规则：从**这个名字之后**开始，最多 `BLOCKING_WINDOW` 字，**遇到下一个名字就截断**。
    两步都不能省：只按字数截，"萧然站在画面左侧，苏棠站在右侧"里萧然会连"右侧"一起吃掉
    （名字是这段文字里天然的语义分段符）；不截断则会串到全文。

    左右与前后**分别匹配**；只给了一个轴时另一个轴落在原点——"站在左侧"本来就意味着
    "与主体同深度"，这不是缺省失误。
    """
    if blocking and name:
        at = blocking.find(name)
        if at >= 0:
            start = at + len(name)
            end = start + BLOCKING_WINDOW
            for other in others:
                if other and other != name:
                    other_at = blocking.find(other, start)
                    if other_at >= 0:
                        end = min(end, other_at)
            window = blocking[start:end].lower()
            x, missed_x = _match_value(window, BLOCKING_X_HINTS, 0.0)
            z, missed_z = _match_value(window, BLOCKING_Z_HINTS, 0.0)
            if not (missed_x and missed_z):
                return round(x, 3), round(z, 3), False
    # 默认：横向等距排列（design 映射表的口径）
    return round((index - (total - 1) / 2) * DEFAULT_SPACING_M, 3), 0.0, True


def _action_for(
    name: str,
    action_text: str,
    others: Sequence[str],
) -> tuple[str, str, dict[str, Any] | None, str, bool]:
    """从动作描述里取某个人的姿势/动作，返回 `(姿势预设, 动作标识, 自定义关节, 说明, 是否识别)`。

    判定优先级：**动作库动作 > 自定义关节角度 > 静态姿势预设**——能动的不用摆位的，
    因为"会动"在参考视频里比"摆到位"信息量大。

    窗口规则与站位一致（名字后开始、遇到下一个名字截断）；**名字没出现在动作描述里时
    视为整格共用**：分镜的 `action` 通常描述整个画面（"两人对峙"），这时所有人都按它摆。
    """
    if not action_text:
        return "", "", None, "站立（默认）", False
    window = _action_window(action_text, name, others)
    motion = _match_ladder(window, [(markers, slug) for markers, slug in ACTION_MOTION_HINTS])
    if motion:
        return "", motion[0], None, f"动作 {motion[0]}", True
    joints_entry = _match_ladder(
        window, [(markers, label, joints) for markers, label, joints in ACTION_JOINTS_HINTS]
    )
    if joints_entry:
        return "stand", "", dict(joints_entry[1]), joints_entry[0], True
    return "", "", None, "站立（默认）", False


def _action_window(action: str, name: str, others: Sequence[str]) -> str:
    at = action.find(name)
    if at < 0:
        return action
    start = at + len(name)
    end = len(action)
    for other in others:
        if other != name:
            other_at = action.find(other, start)
            if other_at >= 0:
                end = min(end, other_at)
    return action[start:end]


def _movement_coordinates(value: Any) -> list[list[float]]:
    """把 `movement_path` 里**成对的坐标**取出来；纯文字描述返回空列表。

    只有拿到坐标才敢打位移关键帧——从"从门口走到床边"这种文字里猜一条路径，
    结果是一条看起来很像那么回事、实际与分镜无关的运动。
    """
    if not isinstance(value, (list, tuple)):
        return []
    points: list[list[float]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            return []
        x, y = _number(item[0]), _number(item[1])
        z = _number(item[2]) if len(item) >= 3 else 0.0
        if x is None or y is None or z is None:
            return []
        points.append([round(x, 3), round(y, 3), round(z, 3)])
    return points


def _node(kind: str, node_id: str, name: str, position: Sequence[float],
          metadata: Mapping[str, Any], asset_id: str = "") -> dict[str, Any]:
    """构造一个 `add_node` 操作。**id 显式给**：同一批里后面还要按 id 给它打关键帧。"""
    node: dict[str, Any] = {
        "id": node_id,
        "kind": kind,
        "name": name,
        "transform": {"position": [round(float(v), 3) for v in position],
                      "rotation": [0, 0, 0, 1], "scale": [1, 1, 1]},
        "visible": True,
        "locked": False,
        "metadata": dict(metadata),
    }
    if asset_id:
        node["assetId"] = asset_id
    return {"type": "add_node", "payload": {"node": node}}


def build_previs_draft(
    scene: Mapping[str, Any],
    panel: Mapping[str, Any],
    *,
    prop_assets: Optional[Mapping[str, Mapping[str, Any]]] = None,
    fps: Optional[int] = None,
) -> dict[str, Any]:
    """把一格分镜翻译成一批受限操作 + 默认值清单 + 提示。

    `prop_assets` 是 `道具名 → {asset_id, name, model_url}`（调用方查素材库后传入）；
    查不到的道具只写一条提示，**不报错、也不编一个模型**。
    """
    operations: list[dict[str, Any]] = []
    defaults: list[dict[str, Any]] = []
    warnings: list[str] = []

    def note_default(field: str, value: Any, reason: str) -> None:
        defaults.append({"field": field, "value": value, "reason": reason})

    try:
        frame_rate = int(fps or scene.get("fps") or DEFAULT_FPS)
    except (TypeError, ValueError):
        frame_rate = DEFAULT_FPS
    panel_number = int(_number(panel.get("panel_number")) or 0)
    prefix = f"draft-p{panel_number}"

    # ---------------------------------------------------------------- 人物 → 人形占位
    characters = [_text(item) for item in (panel.get("characters") or []) if _text(item)]
    if not characters:
        characters = ["角色 1"]
        note_default("characters", characters[0], "分镜格没有写明人物")
        warnings.append("分镜格没有写明人物，已按 1 个人形占位处理；请确认是否需要补人。")

    height = DEFAULT_HEIGHT
    raw_height = _number(panel.get("character_height"))
    if raw_height is None:
        # 分镜格本身没有身高字段，所以这一条**几乎总会**出现在 defaults 里——这是诚实的结果，
        # 不要为了"defaults 看起来短"而假装它是从分镜推出来的
        note_default("height", height, "分镜格没有身高信息，取尺寸锚点默认档 1.70m")
    else:
        person = SIZE_ANCHORS["person"]
        height = max(float(person["short"]), min(float(person["tall"]), raw_height))

    blocking = _text(panel.get("blocking"))
    if not blocking:
        note_default("blocking", f"横向等距 {DEFAULT_SPACING_M:g}m", "分镜格没有调度描述")

    positions: list[tuple[str, float, float]] = []
    hero_ids: list[str] = []
    character_poses: list[str] = []
    action_text = _text(panel.get("action") or panel.get("panel_goal"))
    for index, name in enumerate(characters):
        x, z, used_default = _character_position(name, blocking, index, len(characters), characters)
        if used_default and blocking:
            note_default(f"blocking:{name}", [x, z], "调度描述里没有这个人的方向词，按等距站位处理")
        positions.append((name, x, z))

        # 动作描述 → 姿势/动作：这是"端着托盘"这类信息唯一的落点，不翻译就全站成默认姿势
        pose_key, motion_slug, joints, label, matched = _action_for(name, action_text, characters)
        if not matched:
            note_default(f"action:{name}", "站立", "动作描述里没有可识别的姿势词")
        character_poses.append(f"{name}：{label}")

        metadata: dict[str, Any] = {"height": height, "pose": pose_key or "stand"}
        if joints:
            metadata["poseJoints"] = joints
        hero_id = f"{prefix}-hero-{index + 1}"
        hero_ids.append(hero_id)
        operations.append(_node("human_proxy", hero_id, name, [x, 0.0, z], metadata))
        if motion_slug:
            # 动作走 assign_motion（写静态引用）；需要"第几帧换动作"时用 add_keyframe
            operations.append({
                "type": "assign_motion",
                "targetId": hero_id,
                "payload": {"motion": f"motion:{motion_slug}"},
            })

    anchor = (
        round(sum(item[1] for item in positions) / len(positions), 3),
        round(sum(item[2] for item in positions) / len(positions), 3),
    )
    eye_y = round(height * EYE_RATIO, 3)

    # ---------------------------------------------------------------- 机位与镜头
    shot_text = _text(panel.get("shot_size"))
    shot = _match_ladder(shot_text, SHOT_SIZE_LADDER)
    if not shot_text:
        shot = DEFAULT_SHOT_SIZE
        note_default("shot_size", shot[0], "分镜格没有景别，按中景处理")
    elif shot is None:
        shot = DEFAULT_SHOT_SIZE
        note_default("shot_size", shot[0], f"景别「{shot_text}」不在档位表里，按中景处理")
        warnings.append(f"景别「{shot_text}」没有对应档位，已按中景（{shot[1]:g}m / {shot[2]:g}mm）处理。")

    angle_text = _text(panel.get("camera_angle"))
    angle = _match_ladder(angle_text, CAMERA_ANGLE_LADDER)
    if not angle_text:
        angle = DEFAULT_CAMERA_ANGLE
        note_default("camera_angle", angle[0], "分镜格没有镜头角度，按平视处理")
    elif angle is None:
        angle = DEFAULT_CAMERA_ANGLE
        note_default("camera_angle", angle[0], f"镜头角度「{angle_text}」不在档位表里，按平视处理")
        warnings.append(f"镜头角度「{angle_text}」没有对应档位，已按平视处理。")
    if angle[0] == "主观":
        note_default("camera_angle", "平视", "主观镜头按平视处理：预演里机位代表角色视线")

    azimuth_text = _text(panel.get("camera_hint")) or angle_text
    azimuth = _match_ladder(azimuth_text, AZIMUTH_HINTS) or ("正面", 0.0)
    if azimuth[0] != "正面":
        note_default("camera_angle:方位", azimuth[0], f"从「{azimuth_text}」识别出机位方位 {azimuth[1]:g}°")

    composition_text = _text(panel.get("composition"))
    composition = _match_ladder(composition_text, COMPOSITION_HINTS)
    if not composition_text:
        composition = DEFAULT_COMPOSITION
        note_default("composition", "居中", "分镜格没有构图描述")
    elif composition is None:
        composition = DEFAULT_COMPOSITION
        note_default("composition", "居中", f"构图「{composition_text}」不在档位表里，按居中处理")
    elif composition[0] == "三分":
        note_default("composition", "右三分", f"构图「{composition_text}」没指明左右，按右三分线处理")

    position = _camera_position(
        anchor=anchor, distance=shot[1], pitch_deg=angle[1], azimuth_deg=azimuth[1], eye_y=eye_y,
    )
    target = [anchor[0], eye_y, anchor[1]]
    target = _composition_target(position=position, target=target, anchor=anchor,
                                 distance=shot[1], focal_mm=shot[2], fraction=composition[1])

    camera_payload: dict[str, Any] = {
        "position": position,
        "target": target,
        "focalLength": shot[2],
        "sensorFormat": DEFAULT_SENSOR,
        "fov": _fov_from_focal(shot[2]),
    }
    active_camera_id = _text(scene.get("activeCameraId"))
    cameras = [item for item in (scene.get("cameras") or []) if isinstance(item, dict)]
    if active_camera_id:
        operations.append({"type": "set_camera", "targetId": active_camera_id, "payload": camera_payload})
    elif cameras:
        operations.append({"type": "set_camera",
                           "targetId": str(cameras[0].get("id") or ""),
                           "payload": camera_payload})
    else:
        operations.append({"type": "add_camera",
                           "payload": {**camera_payload, "id": f"{prefix}-camera", "name": f"{shot[0]}机位"}})
        note_default("camera", f"{shot[0]}机位", "场景里还没有机位，按分镜景别新建了一个")

    # ---------------------------------------------------------------- 时长
    from app.services.creative_project.service import CreativeProjectService

    # 直接复用既有口径（3–6 秒；特写取短、远景取长），避免"预演"与"生视频"对同一格给出两个时长
    seconds = CreativeProjectService._normalize_storyboard_duration(dict(panel))
    frames = max(1, int(round(seconds * frame_rate)))
    operations.append({"type": "set_duration", "payload": {"frames": frames}})
    if not _text(panel.get("duration_seconds") or panel.get("duration")):
        note_default("duration_seconds", seconds, f"分镜格没有时长，按景别取 {seconds} 秒")

    # ---------------------------------------------------------------- 道具
    props = [_text(item) for item in (panel.get("props") or []) if _text(item)]
    prop_count = 0
    for index, prop in enumerate(props):
        asset = (prop_assets or {}).get(prop)
        if not asset:
            warnings.append(f"道具「{prop}」在素材库里没有匹配到模型，未放置（可手动添加或先补素材）。")
            continue
        asset_id = _text(asset.get("asset_id"))
        operations.append(_node(
            "asset_model", f"{prefix}-prop-{index + 1}", _text(asset.get("name")) or prop,
            [round(anchor[0] + 1.1 + index * 0.9, 3), 0.0, round(anchor[1] - 0.5, 3)],
            {"assetId": asset_id, "modelUrl": _text(asset.get("model_url"))},
            asset_id=asset_id,
        ))
        prop_count += 1
        # 位置只是占位：素材库模型以自带包围盒为准，本版不做尺寸解析，因此也不写 scale
        note_default(f"props:{prop}", "主体旁约 1.1m", "道具位置是占位：模型以自带包围盒为准，未做尺寸解析")

    # ---------------------------------------------------------------- 明确不翻译的字段
    movement = panel.get("movement_path")
    if movement:
        points = _movement_coordinates(movement)
        if len(points) >= 2:
            base = positions[0]
            start = [round(base[1] + points[0][0], 3), points[0][1], round(base[2] + points[0][2], 3)]
            end = [round(base[1] + points[-1][0], 3), points[-1][1], round(base[2] + points[-1][2], 3)]
            operations.append({"type": "add_keyframe", "targetId": hero_ids[0],
                               "payload": {"property": "position", "frame": 0, "value": start}})
            operations.append({"type": "add_keyframe", "targetId": hero_ids[0],
                               "payload": {"property": "position", "frame": frames, "value": end}})
            note_default("movement_path", "已按坐标打首末帧位移关键帧",
                         f"{characters[0]} 的路径来自分镜坐标，已转成位置关键帧")
        else:
            warnings.append(
                "分镜格写了 movement_path，但它是文字描述、无法可靠换算成坐标：本版不自动打位移关键帧。"
                "可在预演台给角色挂「行走/奔跑」动作，再补首末帧位置关键帧。"
            )
            note_default("movement_path", "未翻译", "路径是文字描述，无法可靠换算")

    camera_motion = _text(panel.get("camera_motion"))
    if camera_motion and _match_ladder(camera_motion, (("静止|static|still|固定", "静止", 0.0),)) is None:
        warnings.append(
            f"镜头运动「{camera_motion}」未翻译：本版不自动生成机位关键帧，"
            "可在预演台机位面板用「运镜模板」一键套用（26 类）后再微调。"
        )
        note_default("camera_motion", "静止", "本版不自动生成机位关键帧")

    location = _text(panel.get("location"))
    if location:
        warnings.append(
            f"背景未自动设置：分镜格写了场地「{location}」，而全景背景当前只支持纯色（贴图未接入）。"
            "本版不生成背景节点——生成一个渲染不出来的节点比不生成更糟。"
        )
        note_default("location", location, "全景只支持纯色，未生成背景节点")

    return {
        "operations": operations,
        "defaults": defaults,
        "warnings": warnings,
        "summary": {
            "panel_number": panel_number,
            "characters": characters,
            "character_poses": character_poses,
            "shot_size": shot[0],
            "camera_angle": angle[0],
            "camera_azimuth": azimuth[0],
            "composition": composition[0],
            "focal_length": shot[2],
            "camera_distance": shot[1],
            "camera_position": position,
            "duration_seconds": seconds,
            "duration_frames": frames,
            "fps": frame_rate,
            "human_proxy_count": len(characters),
            "prop_count": prop_count,
        },
    }


def load_storyboard_panel(content: Any, panel_number: int) -> Optional[dict[str, Any]]:
    """从一个 `ProjectContent`（`content_type=storyboard`）里取出指定格。

    面板号只在各自的分镜内容内唯一，因此调用方必须带上 `storyboard_content_id`——
    与 `context_pack._storyboard_panels` 用 `(content_id, panel_number)` 组键是同一条理由。
    """
    from app.services.creative_project.service import loads_json

    if content is None or str(getattr(content, "content_type", "")) != "storyboard":
        return None
    data = loads_json(getattr(content, "data_json", None))
    for panel in data.get("panels") or []:
        if not isinstance(panel, dict):
            continue
        number = _number(panel.get("panel_number"))
        if number is not None and int(number) == int(panel_number):
            return panel
    return None
