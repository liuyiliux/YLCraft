"""预演动作资产：通道契约与**逐帧纯函数求值**。

动作求值必须是"给一帧算一帧"的纯函数（design D2）。原因不是洁癖：导出参考视频走的是
逐帧渲染 → 服务端按固定帧率合成，一旦求值依赖播放状态（播放头、墙上时钟、视口帧率），
同一帧就会在不同时刻给出不同姿态，导出的视频会时长漂移、节奏不匀——这一点在
`3d-director-previs` 的导出可行性实测里已经踩过。

通道命名（前端与后端共用同一份约定）：

- 人形参数载体（与前端 `HumanProxyPose` 一一对应）：
  - 四肢：`leftShoulder.0/1/2`（前后 / 内外旋 / 张开）、`leftElbow`、`leftHip.0/1/2`、
    `leftKnee`，右侧同理；
  - 中线：`torso.0/1/2`（前后倾 / 转身 / 侧倾）、`head.0/1/2`（低头抬眼 / 转头 / 侧头）、
    `bodyOffsetY`（整体重心升降，米）。
  **三元组的下标一律等于轴序**（0 = 绕 X、1 = 绕 Y、2 = 绕 Z）。注意中线部位的
  "正 pitch"是**前倾 / 低头**，与四肢的"正 pitch = 向身后摆"含义相反——因为部位朝向相反，
  旋向其实是同一个（详见前端 `HumanProxyPose` 注释）。
- 通用变换载体：`position.0/1/2`、`rotation.0/1/2`、`scale.0/1/2`。

载体的 `payload_json` 形状：

```json
{
  "channels": {"leftKnee": [[0, 22], [6, 40], [24, 22]], "...": [[frame, value]]},
  "stride_meters": 0.65,
  "steps_per_cycle": 2
}
```

每条通道是 `[帧号, 数值]` 的列表，**线性插值**；关键帧之间不引入缓动，因为预演的用途是
给出可读的走势，缓动只会让"第几帧是什么姿态"变得难以用手算核对。
"""

from __future__ import annotations

from typing import Any, Optional

#: 人形参数载体的通道清单（顺序与前端 HumanProxyPose 的字段顺序一致）
HUMAN_PARAM_CHANNELS: tuple[str, ...] = (
    "leftShoulder.0",
    "leftShoulder.1",
    "leftShoulder.2",
    "rightShoulder.0",
    "rightShoulder.1",
    "rightShoulder.2",
    "leftElbow",
    "rightElbow",
    "leftHip.0",
    "leftHip.1",
    "leftHip.2",
    "rightHip.0",
    "rightHip.1",
    "rightHip.2",
    "leftKnee",
    "rightKnee",
    "torso.0",
    "torso.1",
    "torso.2",
    "head.0",
    "head.1",
    "head.2",
    "bodyOffsetY",
)

#: 通用变换载体的通道清单
TRANSFORM_CHANNELS: tuple[str, ...] = (
    "position.0",
    "position.1",
    "position.2",
    "rotation.0",
    "rotation.1",
    "rotation.2",
    "scale.0",
    "scale.1",
    "scale.2",
)

#: 生理约束：肘只能向前屈（≤0）、膝只能向后收（≥0）。种子动作必须全部满足。
#: 与前端 `HUMAN_PROXY_LIMITS` 是同一条规则的两种表达，改动时两边都要动。
CHANNEL_SIGN_RULES: dict[str, tuple[str, float]] = {
    "leftElbow": ("<=", 0.0),
    "rightElbow": ("<=", 0.0),
    "leftKnee": (">=", 0.0),
    "rightKnee": (">=", 0.0),
}

#: 点名生理规则的人话（拒绝原因用）：只说"超出范围"会让人以为只是数值大小问题。
_CHANNEL_SIGN_HINT: dict[str, str] = {
    "leftElbow": "肘只能向前屈（上限 0）",
    "rightElbow": "肘只能向前屈（上限 0）",
    "leftKnee": "膝只能向后收（下限 0）",
    "rightKnee": "膝只能向后收（下限 0）",
}

#: 每个通道的允许范围（度；`bodyOffsetY` 的单位是米），与前端 `HUMAN_PROXY_LIMITS` 是
#: **同一条规则的两种表达**，改动时两边都要动（与 `CHANNEL_SIGN_RULES` 同一约定）。
#:
#: 为什么后端也要留一份：AI 提交的姿势若超范围，前端 `sanitizeHumanProxyPose` 会**静默夹到
#: 边界**——那是"悄悄改掉别人的意图"，事后无从发现。在校验阶段拒绝并写出范围，代价只是一次比较。
#: 注意 `*Elbow` 的上界 0 与 `*Knee` 的下界 0 **已经蕴含**了反折规则；`CHANNEL_SIGN_RULES`
#: 仍然保留，是为了让拒绝原因能点名那条生理规则（见 `channel_limit_reason`）。
HUMAN_PARAM_LIMITS: dict[str, tuple[float, float]] = {
    # 肩 / 髋：三元组下标 0 = 绕 X（前后）、1 = 绕 Y（内外旋）、2 = 绕 Z（张开）
    "leftShoulder.0": (-160, 70),
    "leftShoulder.1": (-90, 90),
    "leftShoulder.2": (-45, 170),
    "rightShoulder.0": (-160, 70),
    "rightShoulder.1": (-90, 90),
    "rightShoulder.2": (-45, 170),
    "leftHip.0": (-120, 40),
    "leftHip.1": (-45, 45),
    "leftHip.2": (-30, 45),
    "rightHip.0": (-120, 40),
    "rightHip.1": (-45, 45),
    "rightHip.2": (-30, 45),
    "leftElbow": (-150, 0),
    "rightElbow": (-150, 0),
    "leftKnee": (0, 140),
    "rightKnee": (0, 140),
    # 躯干 / 头颈 / 重心（design D11 扩充的 7 个通道）
    "torso.0": (-15, 60),
    "torso.1": (-60, 60),
    "torso.2": (-25, 25),
    "head.0": (-45, 55),
    "head.1": (-75, 75),
    "head.2": (-30, 30),
    "bodyOffsetY": (-0.8, 0.25),
}


#: 按字段组织的姿势键（前端 `HumanProxyPose` 的字段名）：三元组字段与单值字段，
#: **从通道清单推导**而不是再写一份——通道是唯一真值，字段只是它的"无轴"形式。
TRIPLE_FIELDS = tuple(sorted({channel.split(".")[0] for channel in HUMAN_PARAM_CHANNELS if "." in channel}))
SINGLE_FIELDS = tuple(channel for channel in HUMAN_PARAM_CHANNELS if "." not in channel)


def pose_field_reasons(pose_fields: Mapping[str, Any]) -> list[str]:
    """校验**按字段组织**的姿势（前端 `poseJoints` 的形状：`leftShoulder: [前,内外旋,张开]`）。

    为什么不是逐通道校验：`poseJoints` 是"字段 → 角度(或三元组)"，与通道名（`leftShoulder.0`）
    是两种形状——早期版本拿字段名当通道名校验，结果**连前端自己写的姿势都会被拒**
    （`leftShoulder` 被当成未知通道）。三元组字段按轴拆成通道再校验，规则与种子数据共用。
    """
    reasons: list[str] = []
    if not pose_fields:
        return ["poseJoints 不能为空对象：要么不传，要么给至少一个字段"]
    for field, value in pose_fields.items():
        if field in TRIPLE_FIELDS:
            if not isinstance(value, (list, tuple)) or len(value) != 3:
                reasons.append(f"poseJoints.{field} 需要 [x, y, z] 三个数值，收到 {value!r}")
                continue
            for axis, item in enumerate(value):
                reason = channel_limit_reason(f"{field}.{axis}", item)
                if reason:
                    reasons.append(f"poseJoints 的 {reason}")
        elif field in SINGLE_FIELDS:
            reason = channel_limit_reason(field, value)
            if reason:
                reasons.append(f"poseJoints 的 {reason}")
        else:
            reasons.append(f"poseJoints 的 未知的姿势字段：{field}")
    return reasons


def channel_limit_reason(channel: str, value: Any) -> Optional[str]:
    """通道取值不合法时返回**人话原因**，合法返回 `None`。

    供 `operations.validate_operations` 逐条拒绝外部（含 AI）提交的姿势，而不是让越界值
    流到前端被静默夹到边界。布尔值单独挡：Python 里 `True` 是 `int` 的实例，
    `{"leftKnee": True}` 会静默变成 1.0（与 `_clean_keys` 同一条理由）。
    """
    if channel not in HUMAN_PARAM_CHANNELS:
        return f"未知的姿势通道：{channel}"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return f"{channel} 需要一个数值，收到 {value!r}"
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return f"{channel} 需要一个有限数值，收到 {value!r}"
    low, high = HUMAN_PARAM_LIMITS[channel]
    if number < low or number > high:
        # 肘/膝的限位**就是**反折规则（上界 0 / 下界 0），但只有往被禁的那个方向越界才算反折：
        # `leftKnee=999` 是"超出范围"，说成"违反生理约束"会把人引到错误的方向（限制是 140，不是 0）
        hint = _CHANNEL_SIGN_HINT.get(channel)
        sign_violation = bool(hint) and ((number > high and high == 0) or (number < low and low == 0))
        if sign_violation:
            return f"{channel}={number:g} 违反生理约束：{hint}"
        return f"{channel}={number:g} 超出范围 {low:g}–{high:g}"
    return None


def resolve_frame(frame: int, *, frame_count: int, loopable: bool) -> int:
    """把任意帧号折算到动作的有效区间内。

    - 负数一律当第 0 帧（前端的播放头不会给负数，但外部写入可能给）；
    - 可循环动作取模（因此 `frame_count` 必须等于一个完整循环的长度，且首尾关键帧同值）；
    - 不可循环动作超出末帧时**保持末帧**，而不是回到起点——预演的"坐姿""指向"这类
      一次性动作停在结束姿态才合理。
    """
    if frame <= 0:
        return 0
    if frame_count <= 0:
        return frame
    if loopable:
        return frame % frame_count
    return min(frame, frame_count)


def _clean_keys(keys: Any) -> list[tuple[float, float]]:
    """把关键帧列表收敛成"按帧号排序的 (帧, 值) 列表"，坏元素只丢自己。

    `bool` 要单独挡：Python 里 `True` 是 `int` 的实例，不挡的话 `True` 会被当成 1.0，
    于是一个手滑写成布尔值的关键帧会静默变成第 1.0 帧的 1.0——这类错误不会报错，
    只会让动作悄悄变形。
    """
    cleaned: list[tuple[float, float]] = []
    if not isinstance(keys, (list, tuple)):
        return cleaned
    for item in keys:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        frame, value = item[0], item[1]
        if isinstance(frame, bool) or isinstance(value, bool):
            continue
        if not isinstance(frame, (int, float)) or not isinstance(value, (int, float)):
            continue
        cleaned.append((float(frame), float(value)))
    cleaned.sort(key=lambda pair: pair[0])
    return cleaned


def sample_channel(keys: Any, frame: int) -> Optional[float]:
    """单通道线性取样。无可用关键帧时返回 None（由调用方决定回落到什么默认值）。"""
    pairs = _clean_keys(keys)
    if not pairs:
        return None
    if frame <= pairs[0][0]:
        return pairs[0][1]
    if frame >= pairs[-1][0]:
        return pairs[-1][1]
    for (frame_a, value_a), (frame_b, value_b) in zip(pairs, pairs[1:]):
        if frame_a <= frame <= frame_b:
            if frame_b == frame_a:
                return value_b
            ratio = (frame - frame_a) / (frame_b - frame_a)
            return value_a + (value_b - value_a) * ratio
    return pairs[-1][1]


def sample_channels(
    payload: Any,
    frame: int,
    *,
    frame_count: int,
    loopable: bool,
) -> dict[str, float]:
    """按帧号取样整条动作，返回 `{通道名: 数值}`。

    缺关键帧的通道不进入结果（而不是填 0）：调用方据此区分"这条动作不管这个通道"与
    "这条动作明确把它设为 0"，否则一条只描述手臂的动作会把腿悄悄拉直。
    """
    channels = payload.get("channels") if isinstance(payload, dict) else None
    if not isinstance(channels, dict):
        return {}
    resolved = resolve_frame(frame, frame_count=frame_count, loopable=loopable)
    sampled: dict[str, float] = {}
    for name, keys in channels.items():
        value = sample_channel(keys, resolved)
        if value is not None:
            sampled[str(name)] = value
    return sampled


def recommended_speed_mps(payload: Any, duration_seconds: float) -> Optional[float]:
    """由"步幅 × 每循环步数 ÷ 周期"反推位移速度（米/秒）。

    这是消除"脚下打滑"的依据：滑步的本质是位移速度与步频不匹配，而参数型动作**能**算这个
    关系（骨骼动画做不到自适应）。预演里把位移速度设成这个值，脚就不会打滑。
    """
    if not isinstance(payload, dict) or not duration_seconds or duration_seconds <= 0:
        return None
    stride = payload.get("stride_meters")
    steps = payload.get("steps_per_cycle", 2)
    for value in (stride, steps):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            return None
    return round(float(stride) * float(steps) / float(duration_seconds), 4)


def violates_sign_rule(channel: str, value: float) -> bool:
    """判断取样值是否违反生理约束（肘/膝的反折方向）。供种子数据与外部写入共用。"""
    rule = CHANNEL_SIGN_RULES.get(channel)
    if rule is None:
        return False
    operator, limit = rule
    return value > limit if operator == "<=" else value < limit
