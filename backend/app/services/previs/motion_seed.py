"""首批内置动作与姿势（程序化定义，无第三方素材，因此无许可风险）。

**作者视角是"第几帧摆什么姿势"，存储形状是"逐通道关键帧"**——`_pose_channels` 做这次
转置。这样种子数据写起来是人话，落库后仍是与前端 `timeline.ts` 同一套通道曲线语义。

两条自我约束（由 `tests/test_previs_motions.py` 断言，不靠人眼）：

1. **肘只能向前屈、膝只能向后收**——参数级就挡住反折，不必等到渲染出来才发现；
2. **可循环动作的首尾必须同值**——否则循环回绕的那一刻会出现一次跳变，而"跳变"在
   逐帧导出的视频里表现为角色突然抽一下。

左右相位用 `_mirror` 把 left/right 字段对调得到。这是可行的，因为关节语义已经按侧镜像
（见前端 `humanProxyShoulderRotation`）：同一个数值在两侧表示同一个"相对动作"，
所以"换相位"就是"换边"。
"""

from __future__ import annotations

from typing import Any

from app.services.previs.motion import HUMAN_PARAM_CHANNELS, TRANSFORM_CHANNELS

_TRIPLE_FIELDS = ("leftShoulder", "rightShoulder", "leftHip", "rightHip", "torso", "head")
_SINGLE_FIELDS = ("leftElbow", "rightElbow", "leftKnee", "rightKnee", "bodyOffsetY")


def _pose(**partial: Any) -> dict[str, Any]:
    """补全成 16 通道齐全的姿势；未给的通道显式为 0。

    刻意补全而不是留空：留空会让"这条动作不管这个通道"与"这条动作明确把它设成 0"变得
    无法区分，于是某条只描述手臂的动作会把腿悄悄拉直。
    """
    full: dict[str, Any] = {field: [0.0, 0.0, 0.0] for field in _TRIPLE_FIELDS}
    full.update({field: 0.0 for field in _SINGLE_FIELDS})
    full.update(partial)
    return full


def _mirror(pose: dict[str, Any]) -> dict[str, Any]:
    """左右对调，得到相位相反的那一帧。

    中线部位（`torso` / `head` / `bodyOffsetY`）**原样保留**：换相位换的是左右腿，
    不是"整个上身镜像"——把躯干也镜像会让"看左侧"变成"看右侧"。
    """
    mirrored: dict[str, Any] = {}
    for field, value in pose.items():
        if field.startswith("left"):
            mirrored["right" + field[4:]] = value
        elif field.startswith("right"):
            mirrored["left" + field[5:]] = value
        else:
            mirrored[field] = value
    return mirrored


def _pose_channels(keys: list[tuple[int, dict[str, Any]]]) -> dict[str, list[list[float]]]:
    """把 `[(帧号, 姿势)]` 转置成 `{通道名: [[帧号, 值]]}`。

    值统一转成 float：JSON 里 22 与 22.0 等价，但统一之后测试断言与前端取到的类型一致。
    """
    channels: dict[str, list[list[float]]] = {}
    for frame, pose in keys:
        for field, value in pose.items():
            if field in _TRIPLE_FIELDS:
                for index, component in enumerate(value):
                    channels.setdefault(f"{field}.{index}", []).append([float(frame), float(component)])
            else:
                channels.setdefault(field, []).append([float(frame), float(value)])
    for name in channels:
        channels[name].sort(key=lambda pair: pair[0])
    return channels


def _params(
    slug: str,
    name: str,
    category: str,
    tags: list[str],
    fps: int,
    frame_count: int,
    loopable: bool,
    keys: list[tuple[int, dict[str, Any]]],
    *,
    stride_meters: float | None = None,
    steps_per_cycle: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"channels": _pose_channels(keys)}
    if stride_meters is not None:
        payload["stride_meters"] = stride_meters
    if steps_per_cycle is not None:
        payload["steps_per_cycle"] = steps_per_cycle
    return {
        "slug": slug,
        "name": name,
        "carrier": "params",
        "skeleton": "ylcraft-humanoid-v1",
        "category": category,
        "tags": tags,
        "fps": fps,
        "frame_count": frame_count,
        "duration_seconds": round(frame_count / fps, 4),
        "loopable": loopable,
        "payload": payload,
    }


def _transform(
    slug: str,
    name: str,
    category: str,
    tags: list[str],
    fps: int,
    frame_count: int,
    loopable: bool,
    channels: dict[str, list[list[float]]],
) -> dict[str, Any]:
    return {
        "slug": slug,
        "name": name,
        "carrier": "transform",
        "skeleton": None,
        "category": category,
        "tags": tags,
        "fps": fps,
        "frame_count": frame_count,
        "duration_seconds": round(frame_count / fps, 4),
        "loopable": loopable,
        "payload": {"channels": channels},
    }


# --- 人形参数载体：六个基础动作 -------------------------------------------------

_STAND = _pose()

# 行走：一个循环 24 帧 @24fps = 1 秒、两步。这是动画通行口径（"走循环一秒"），
# 步幅 0.65m 与两步/秒搭配正好是真人常速 1.3 m/s —— 位移按这个速度设就不会滑步。
_WALK_CONTACT = _pose(
    leftHip=[18, 0, 6], rightHip=[-14, 0, 6], leftKnee=22, rightKnee=6,
    leftShoulder=[-20, 0, 8], rightShoulder=[16, 0, 8], leftElbow=-22, rightElbow=-26,
)
_WALK_PASSING = _pose(
    leftHip=[4, 0, 6], rightHip=[2, 0, 6], leftKnee=40, rightKnee=4,
    leftShoulder=[-2, 0, 8], rightShoulder=[0, 0, 8], leftElbow=-20, rightElbow=-22,
)

# 跑：16 帧 @24fps ≈ 0.667 秒一个循环、两步 → 步频 3 步/秒；步幅 1.2m 得 3.6 m/s（中速跑）。
_RUN_CONTACT = _pose(
    leftHip=[22, 0, 6], rightHip=[-30, 0, 6], leftKnee=30, rightKnee=58,
    leftShoulder=[-26, 0, 10], rightShoulder=[22, 0, 10], leftElbow=-72, rightElbow=-78,
)
_RUN_FLIGHT = _pose(
    leftHip=[-6, 0, 6], rightHip=[8, 0, 6], leftKnee=78, rightKnee=30,
    leftShoulder=[-4, 0, 10], rightShoulder=[2, 0, 10], leftElbow=-72, rightElbow=-74,
)

# 待机：一个呼吸循环 72 帧 = 3 秒，只动肩、肘与膝的一点点
_IDLE_INHALE = _pose(
    leftShoulder=[2, 0, 1.5], rightShoulder=[2, 0, 1.5], leftElbow=-5, rightElbow=-5,
    leftKnee=2, rightKnee=2,
)

_WAVE_UP = _pose(rightShoulder=[-120, 0, 25], rightElbow=-60, leftShoulder=[0, 0, 8], leftElbow=-12)
_WAVE_SWING_OUT = _pose(rightShoulder=[-120, 0, 25], rightElbow=-78, leftShoulder=[0, 0, 8], leftElbow=-12)
_WAVE_SWING_IN = _pose(rightShoulder=[-120, 0, 25], rightElbow=-48, leftShoulder=[0, 0, 8], leftElbow=-12)

_SIT = _pose(
    leftHip=[-82, 0, 5], rightHip=[-82, 0, 5], leftKnee=84, rightKnee=84,
    leftShoulder=[-6, 0, 12], rightShoulder=[-6, 0, 12], leftElbow=-38, rightElbow=-38,
)

_POINT = _pose(rightShoulder=[-80, 0, 12], rightElbow=-8, leftShoulder=[0, 0, 8])

# --- 视线 / 交流 / 姿态：只靠躯干与头颈就能表达的动作 ---------------------------------
#
# 符号提醒（最容易写错的一处）：中线部位朝上，**正 pitch = 前倾 / 低头**，
# 与四肢的"正 pitch = 向身后摆"含义相反（旋向其实是同一个）。所以"低头 32°"写 `+32`、
# "抬眼 26°"写 `-26`。yaw 正值 = 转向画面右侧；roll 正值 = 向画面左侧倾。
_LOOK_DOWN = _pose(head=[32, 0, 0])
_LOOK_UP = _pose(head=[-26, 0, 0], torso=[-6, 0, 0])
_LOOK_SIDE = _pose(head=[2, 38, 6])
_LOOK_BACK = _pose(torso=[0, 34, 0], head=[4, 46, 0])
_NOD_DOWN = _pose(head=[26, 0, 0])
_NOD_UP = _pose(head=[-8, 0, 0])
_SHAKE_LEFT = _pose(head=[0, 26, 0])
_SHAKE_RIGHT = _pose(head=[0, -26, 0])
# 鞠躬绕髋铰链（躯干支点就在髋高度，见前端 HUMAN_PROXY_TORSO_PIVOT_Y），手臂自然下垂
_BOW = _pose(
    torso=[54, 0, 0], head=[12, 0, 0],
    leftShoulder=[-8, 0, 7], rightShoulder=[-8, 0, 7], leftElbow=-12, rightElbow=-12,
)
# 沉思：低头 + 侧头 + 右手抬到下颌附近（手落在躯干胶囊之外，见不变量测试）
_PONDER = _pose(
    torso=[6, 8, 0], head=[12, 20, 6],
    rightShoulder=[-52, 0, 16], rightElbow=-102,
    leftShoulder=[6, 0, 10], leftElbow=-24,
)
# 半蹲：**重心下沉必须与髋/膝屈曲配套**，否则脚陷进地面。
# 数值来源：脚底高度 = 髋高(0.92) + 下沉量 − 大腿垂直投影(0.426·cos52°) − 小腿(0.4444)
#           − 脚半径(0.05) ≈ 0，即大腿前抬 52°、膝后收 52° 时下沉 0.165m 正好踩实。
# 该判据由 `humanProxy.test.ts` 的"脚底贴地"断言钉住。
_CROUCH = _pose(
    bodyOffsetY=-0.165,
    leftHip=[-52, 0, 7], rightHip=[-52, 0, 7], leftKnee=52, rightKnee=52,
    torso=[20, 0, 0], head=[-12, 0, 0],
    leftShoulder=[-20, 0, 12], rightShoulder=[-20, 0, 12], leftElbow=-44, rightElbow=-44,
)


def seed_motion_specs() -> list[dict[str, Any]]:
    """返回内置动作规格（幂等 upsert 的输入，按 `slug` 认）。"""
    return [
        _params(
            "idle", "待机", "待机", ["待机", "呼吸", "站立"], 24, 72, True,
            [(0, _STAND), (36, _IDLE_INHALE), (72, _STAND)],
        ),
        _params(
            "walk", "行走", "移动", ["走路", "移动", "循环"], 24, 24, True,
            [(0, _WALK_CONTACT), (6, _WALK_PASSING), (12, _mirror(_WALK_CONTACT)),
             (18, _mirror(_WALK_PASSING)), (24, _WALK_CONTACT)],
            stride_meters=0.65, steps_per_cycle=2,
        ),
        _params(
            "run", "奔跑", "移动", ["跑步", "移动", "循环"], 24, 16, True,
            [(0, _RUN_CONTACT), (4, _RUN_FLIGHT), (8, _mirror(_RUN_CONTACT)),
             (12, _mirror(_RUN_FLIGHT)), (16, _RUN_CONTACT)],
            stride_meters=1.2, steps_per_cycle=2,
        ),
        _params(
            "wave", "挥手", "互动", ["打招呼", "挥手", "一次性"], 24, 36, False,
            [(0, _STAND), (10, _WAVE_UP), (18, _WAVE_SWING_OUT), (26, _WAVE_SWING_IN), (36, _STAND)],
        ),
        _params(
            "sit", "坐下", "姿态", ["坐姿", "一次性"], 24, 36, False,
            [(0, _STAND), (36, _SIT)],
        ),
        _params(
            "point", "指向", "互动", ["指向", "一次性"], 24, 18, False,
            [(0, _STAND), (18, _POINT)],
        ),
        # --- 第二批：只靠躯干与头颈就能表达的动作（对应外部动作库的「视线 / 交流」两类）--
        # 时长口径同第一批：一次性的"到位"动作给 0.75–1.5 秒，到末帧保持不动（见 resolve_frame）
        _params(
            "look-down", "低头", "视线", ["低头", "视线", "一次性"], 24, 18, False,
            [(0, _STAND), (12, _LOOK_DOWN), (18, _LOOK_DOWN)],
        ),
        _params(
            "look-up", "抬眼", "视线", ["抬眼", "视线", "一次性"], 24, 18, False,
            [(0, _STAND), (12, _LOOK_UP), (18, _LOOK_UP)],
        ),
        _params(
            "look-side", "侧头张望", "视线", ["侧头", "张望", "视线", "一次性"], 24, 24, False,
            [(0, _STAND), (12, _LOOK_SIDE), (24, _LOOK_SIDE)],
        ),
        _params(
            "look-back", "回望", "视线", ["回头", "回望", "视线", "一次性"], 24, 30, False,
            [(0, _STAND), (16, _LOOK_BACK), (30, _LOOK_BACK)],
        ),
        _params(
            "nod", "点头", "交流", ["点头", "同意", "一次性"], 24, 24, False,
            [(0, _STAND), (7, _NOD_DOWN), (14, _NOD_UP), (24, _STAND)],
        ),
        _params(
            "shake-head", "摇头", "交流", ["摇头", "否定", "一次性"], 24, 24, False,
            [(0, _STAND), (6, _SHAKE_LEFT), (12, _SHAKE_RIGHT), (18, _SHAKE_LEFT), (24, _STAND)],
        ),
        _params(
            "bow", "鞠躬", "姿态", ["鞠躬", "致意", "姿态", "一次性"], 24, 36, False,
            [(0, _STAND), (16, _BOW), (26, _BOW), (36, _STAND)],
        ),
        _params(
            "ponder", "沉思", "情绪", ["思考", "沉思", "情绪", "一次性"], 24, 48, False,
            [(0, _STAND), (18, _PONDER), (48, _PONDER)],
        ),
        _params(
            "crouch", "半蹲", "姿态", ["蹲下", "半蹲", "姿态", "一次性"], 24, 36, False,
            [(0, _STAND), (20, _CROUCH), (36, _CROUCH)],
        ),
        # --- 通用变换载体：不需要骨骼，任何对象都能用（非人形的兜底）-----------------
        _transform(
            "move-forward-2m", "向前移动 2 米", "移动", ["位移", "一次性"], 24, 48, False,
            {"position.2": [[0.0, 0.0], [48.0, 2.0]]},
        ),
        _transform(
            "turn-around", "原地转身 180°", "移动", ["旋转", "一次性"], 24, 36, False,
            {"rotation.1": [[0.0, 0.0], [36.0, 180.0]]},
        ),
        _transform(
            "hover-loop", "上下浮动（循环）", "氛围", ["浮动", "循环"], 24, 48, True,
            {"position.1": [[0.0, 0.0], [24.0, 0.15], [48.0, 0.0]]},
        ),
    ]


def assert_channels_known(spec: dict[str, Any]) -> None:
    """确认规格里的通道名都属于该载体的合法通道（种子数据写错通道名时立刻报错）。"""
    allowed = HUMAN_PARAM_CHANNELS if spec["carrier"] == "params" else TRANSFORM_CHANNELS
    unknown = sorted(set(spec["payload"].get("channels") or {}) - set(allowed))
    if unknown:
        raise ValueError(f"motion {spec['slug']} has unknown channels: {unknown}")
