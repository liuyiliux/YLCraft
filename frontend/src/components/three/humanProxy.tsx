/**
 * YLCraft — 程序化人形占位（胶囊人）
 *
 * 用胶囊/球/圆柱组合出轻量人形，参照 storyai-3d-director-desk 的
 * ProceduralMannequin（MIT）分层关节思路，但为本项目自写实现：
 * 肢体为胶囊几何体，关节为球体，肩/肘/髋/膝分层旋转应用姿势；
 * 头部带眼睛/鼻子/嘴等五官，手带手指/拇指，脚带脚趾，增强人偶辨识度。
 * 无外部模型文件、无版权风险；姿势只存 metadata.pose（预设 key），
 * 不承载 Story 业务状态。
 *
 * **坐标与命名约定**：角色朝 +Z（前方），+Y 向上；左右按**画面视角**命名
 * （+X 在画面右侧，即代码里的 `right*` 字段与 `humanoid-right-*` 网格）。
 * 这与 Mixamo 等骨架的"角色自身左右"相反——接骨骼型动作时不要用这里的左右。
 *
 * **载体只剩通用胶囊人一种**（原可切到 UE 白模，已下线）：实测
 * `frontend/public/models/ue-mannequin.glb` 自带 **0 条动画**（`animations: []`，
 * 73 节点 / 1 蒙皮 / 67 关节），而参数型动作驱动的是这里的 16 个关节通道——
 * 选中它只能站着不动，而"能选却动不了"比没有这个选项更像 bug。造型化示范模型同理
 * 不在选项内（会把无关的形状与颜色暗示喂给下游生成模型，仍可从素材库作为普通模型添加）。
 * 白模的文件与许可记录保留（`ue-mannequin.glb` + 同目录 `LICENSE-UE-MANNEQUIN.txt`），
 * 等"参数型动作烘焙成 GLB 动画"落地后接回来，作为**仓库里唯一的带蒙皮人形**验证
 * 蒙皮变形与穿模——这里是刚性零件拼的，验证不了那件事。
 * 历史场景中的 `metadata.proxyStyle`（`ue` / `vanguard`）一律忽略、按通用人形渲染。
 */

import type { Object3D } from 'three'

export type HumanProxyPoseKey = 'stand' | 'tpose' | 'walk' | 'sit' | 'wave' | 'point'

/**
 * 姿势是**关节角度**而不是任意欧拉角：每个字段的轴向与正方向都是固定的，
 * 两侧由 `side` 自动镜像，因此同一个数值在左右两侧表示同一个"相对动作"。
 * **三元组的下标一律等于轴序**（0 = 绕 X，1 = 绕 Y，2 = 绕 Z）。
 *
 * **肢体（肩 / 肘 / 髋 / 膝）**——这些部位朝下，绕 +X 正转会把末端送向身后：
 * - `pitch`（绕 X）：**正值 = 肢体向身后摆（−Z）**；两侧同号同义。
 * - `spread`（绕 Z）：**正值 = 向体侧张开（远离身体中线）**；两侧镜像。
 * - `twist`（绕 Y）：正值 = 同一旋转方向；两侧镜像。
 * - `elbow`：**负值 = 屈肘**（前臂向前抬）。
 * - `knee`：**正值 = 屈膝**（小腿向后收）。
 *
 * **躯干与头颈（`torso` / `head`）**——这些部位朝上，所以**同一个"绕 +X 正转"在这里
 * 表现为向前低**。这不是另一套坐标，只是部位朝向相反；后果是照抄外部动作数值时
 * 不必反号，但**含义正好相反**，这正是最容易看错的地方，由测试钉住：
 * - `pitch`（下标 0，绕 X）：**正值 = 前倾 / 低头**（上身与面朝 +Z 低下去）。
 * - `yaw`（下标 1，绕 Y）：**正值 = 转向画面右侧**（面朝 +X）。
 * - `roll`（下标 2，绕 Z）：**正值 = 向画面左侧倾**（头顶倒向 −X）。
 * 中线部位**不做侧镜像**（`side` 对它们没有意义）。
 *
 * `bodyOffsetY`：整体重心升降（米，1.7m 基准），**负值 = 下沉**（蹲、坐），正值 = 抬升。
 * 它是位移不是旋转：**单独下沉会让脚陷进地面**，蹲姿必须与髋/膝屈曲配合
 * （数值见种子动作里的 `crouch`，判据见 `humanProxy.test.ts` 的"脚底贴地"断言）。
 *
 * 肘往前弯、膝往后弯——两者都是"生理方向的弯曲"却符号相反，这是刻意的，不是笔误。
 *
 * 这套语义与数值由 `humanProxy.test.ts` 用反向解算钉住（手不越中线、手不穿躯干、
 * 膝不反折、脚底不陷地）。之前的实现里肩/髋忘记按侧镜像、肘关节绕错了轴，
 * 六个姿势中有一半以上是坏的（T 字两臂对穿、挥手时手穿进躯干、行走膝盖反折、
 * 两脚收到中线）——这类缺陷肉眼很难稳定判断，必须靠数值测试兜住。
 */
export interface HumanProxyPose {
  leftShoulder?: [number, number, number]
  rightShoulder?: [number, number, number]
  leftElbow?: number
  rightElbow?: number
  leftHip?: [number, number, number]
  rightHip?: [number, number, number]
  leftKnee?: number
  rightKnee?: number
  /** 躯干 [前后倾, 转身, 侧倾]（正值含义见上）。 */
  torso?: [number, number, number]
  /** 头颈（含脖子）[低头/抬眼, 转头, 侧头]（正值含义见上）。 */
  head?: [number, number, number]
  /** 整体重心升降（米，1.7m 基准）：负值 = 下沉。 */
  bodyOffsetY?: number
}

/** 手臂链尺寸。导出是为了让回归测试能用**同一份常量**反向解算出手/肘位置。 */
export const HUMAN_PROXY_ARM = {
  shoulderX: 0.19,
  shoulderY: 1.42,
  upperLen: 0.28,
  foreLen: 0.24,
  radius: 0.046,
  handR: 0.05,
} as const

/** 腿链尺寸，同上。 */
export const HUMAN_PROXY_LEG = {
  hipX: 0.095,
  hipY: 0.92,
  thighLen: 0.31,
  calfLen: 0.29,
  radius: 0.058,
  footR: 0.05,
} as const

/** 躯干胶囊半径；试测用，判断手是否穿进身体。 */
export const HUMAN_PROXY_TORSO = { chestR: 0.155, chestBottom: 1.2 - 0.12 - 0.155, chestTop: 1.2 + 0.12 + 0.155 } as const

/**
 * 躯干旋转支点（髋高度）。取髋而不是胸口：鞠躬、前倾都是**绕髋铰链**，
 * 绕胸口转会让上半身与骨盆错开一道缝。
 */
export const HUMAN_PROXY_TORSO_PIVOT_Y = HUMAN_PROXY_LEG.hipY

/** 头颈旋转支点（颈根）。头与脖子一起转，避免只转头留下断开的脖子。 */
export const HUMAN_PROXY_HEAD_PIVOT_Y = 1.47

/** 中线关节组名。躯干与头颈没有左右之分，所以不走 `humanProxyJointName`（那个要 side）。 */
export const HUMAN_PROXY_BODY_JOINTS = {
  root: 'humanoid-root',
  torso: 'humanoid-torso-joint',
  head: 'humanoid-head-joint',
} as const

/**
 * 肩：pitch 绕 X（正=向后）、twist 绕 Y、spread 绕 Z（正=向外）。
 * **twist 与 spread 必须乘 side**：两侧肩点分居 ∓X 却共用同一套局部轴，
 * 不镜像的话"同一个 spread 值"会让两条手臂朝同一侧移动——T 字姿势会直接对穿。
 */
export function humanProxyShoulderRotation(
  side: -1 | 1,
  rot?: [number, number, number],
): [number, number, number] {
  const [pitch = 0, twist = 0, spread = 0] = rot ?? []
  return [deg(pitch), deg(side * twist), deg(side * spread)]
}

/**
 * 肘：绕 **X**，负值 = 前臂向前抬。
 * **不要改成绕 Z**：绕 Z 是左右横扫，屈肘会让前臂扫过身体、手穿进躯干。
 */
export function humanProxyElbowRotation(elbow?: number): [number, number, number] {
  return [deg(elbow), 0, 0]
}

/** 髋：语义与镜像规则同肩。 */
export function humanProxyHipRotation(
  side: -1 | 1,
  rot?: [number, number, number],
): [number, number, number] {
  const [pitch = 0, twist = 0, spread = 0] = rot ?? []
  return [deg(pitch), deg(side * twist), deg(side * spread)]
}

/** 膝：绕 X，正值 = 小腿向后收（与肘方向相反，见 HumanProxyPose 注释）。 */
export function humanProxyKneeRotation(knee?: number): [number, number, number] {
  return [deg(knee), 0, 0]
}

/**
 * 躯干 / 头颈：三元组下标即轴序（0 = 绕 X 前倾、1 = 绕 Y 转身、2 = 绕 Z 侧倾）。
 *
 * 与肩/髋的区别只有一条：**不乘 side**（中线部位没有左右，镜像会变成"往同一边歪"）。
 * 与肢体的"正值 = 向身后摆"共用同一个旋向，但因为部位朝上，含义表现为"正值 = 前倾/低头"
 * ——这条最容易看错，见 `HumanProxyPose` 的注释与 `humanProxy.test.ts` 的朝向断言。
 */
export function humanProxyTorsoRotation(rot?: [number, number, number]): [number, number, number] {
  const [pitch = 0, yaw = 0, roll = 0] = rot ?? []
  return [deg(pitch), deg(yaw), deg(roll)]
}

/** 头颈：轴向与正方向同 `humanProxyTorsoRotation`。 */
export function humanProxyHeadRotation(rot?: [number, number, number]): [number, number, number] {
  const [pitch = 0, yaw = 0, roll = 0] = rot ?? []
  return [deg(pitch), deg(yaw), deg(roll)]
}

export const HUMAN_PROXY_POSES: Record<HumanProxyPoseKey, { label: string; pose: HumanProxyPose }> = {
  stand: { label: '站立', pose: {} },
  // 两侧同为 +85（不是一正一负）：spread 已按 side 镜像，正值在两侧都表示"向外张开"
  tpose: { label: 'T 字', pose: { leftShoulder: [0, 0, 85], rightShoulder: [0, 0, 85] } },
  walk: {
    label: '行走',
    // 左腿在后、右腿在前；手臂与**对侧腿**同向（左臂前摆、右臂后摆），膝只向后弯
    pose: {
      leftHip: [18, 0, 6],
      rightHip: [-14, 0, 6],
      leftKnee: 22,
      rightKnee: 6,
      leftShoulder: [-20, 0, 8],
      rightShoulder: [16, 0, 8],
      leftElbow: -22,
      rightElbow: -26,
    },
  },
  sit: {
    label: '坐姿',
    // 大腿前抬、小腿垂下。旋转式姿势不含整体下沉，落到坐具上需要使用者把对象下移
    pose: {
      leftHip: [-82, 0, 5],
      rightHip: [-82, 0, 5],
      leftKnee: 84,
      rightKnee: 84,
      leftShoulder: [-6, 0, 12],
      rightShoulder: [-6, 0, 12],
      leftElbow: -38,
      rightElbow: -38,
    },
  },
  wave: {
    label: '挥手',
    // 举起手臂靠的是 pitch（负值=向前上抬），不是 spread：spread 把手臂摊到水平后，
    // 肘的弯曲面会变成水平面，前臂只能前后摆、抬不起来。抬到前上方再屈肘，手才在头侧。
    pose: {
      rightShoulder: [-120, 0, 25],
      rightElbow: -60,
      leftShoulder: [0, 0, 8],
      leftElbow: -12,
    },
  },
  point: {
    label: '指向',
    // 手臂前伸（pitch 负值 = 向前），肘基本伸直、略向外偏，避免指向正好落在身体中线上
    pose: {
      rightShoulder: [-80, 0, 12],
      rightElbow: -8,
      leftShoulder: [0, 0, 8],
    },
  },
}

export function humanProxyPoseKey(value: unknown): HumanProxyPoseKey {
  return typeof value === 'string' && value in HUMAN_PROXY_POSES ? (value as HumanProxyPoseKey) : 'stand'
}

/**
 * 各关节的允许范围（度 / 米）。**只硬挡生理不可能的方向**：
 * 肘不能反折（上限 0）、膝不能反折（下限 0）；其余只做范围收敛，
 * 故意不挡"手交叉到身体另一侧"这类现实中可能的动作（那是构图需求，不是错误）。
 *
 * 躯干与头颈按真人活动度取保守值（颈椎与腰椎加起来才有更大的转角，这里分给两个关节），
 * `bodyOffsetY` 是米：下沉 0.8m 已经接近"完全蹲下"，再低脚必然穿地。
 */
export const HUMAN_PROXY_LIMITS = {
  shoulderPitch: [-160, 70],
  shoulderTwist: [-90, 90],
  shoulderSpread: [-45, 170],
  elbow: [-150, 0],
  hipPitch: [-120, 40],
  hipTwist: [-45, 45],
  hipSpread: [-30, 45],
  knee: [0, 140],
  torsoPitch: [-15, 60],
  torsoYaw: [-60, 60],
  torsoRoll: [-25, 25],
  headPitch: [-45, 55],
  headYaw: [-75, 75],
  headRoll: [-30, 30],
  bodyOffsetY: [-0.8, 0.25],
} as const satisfies Record<string, readonly [number, number]>

/** 关节字段清单（三轴与单轴分开，便于逐字段校验）。 */
export const HUMAN_PROXY_TRIPLE_FIELDS = ['leftShoulder', 'rightShoulder', 'leftHip', 'rightHip', 'torso', 'head'] as const
export const HUMAN_PROXY_SINGLE_FIELDS = ['leftElbow', 'rightElbow', 'leftKnee', 'rightKnee', 'bodyOffsetY'] as const

type TripleField = (typeof HUMAN_PROXY_TRIPLE_FIELDS)[number]
type SingleField = (typeof HUMAN_PROXY_SINGLE_FIELDS)[number]

/**
 * 逐字段的限位表。**不要再写 `field.endsWith('Shoulder') ? … : …` 那种三目链**：
 * 每加一个部位就要改一处判断，漏掉一个字段的表现是"该字段静默不受限"。
 * 这张表与 `HUMAN_PROXY_TRIPLE_FIELDS` 一一对应，新增字段时类型会直接报缺项。
 * 三元组下标即轴序：0 = 绕 X、1 = 绕 Y、2 = 绕 Z（见 `HumanProxyPose` 注释）。
 */
const TRIPLE_LIMITS: Record<TripleField, readonly [readonly [number, number], readonly [number, number], readonly [number, number]]> = {
  leftShoulder: [HUMAN_PROXY_LIMITS.shoulderPitch, HUMAN_PROXY_LIMITS.shoulderTwist, HUMAN_PROXY_LIMITS.shoulderSpread],
  rightShoulder: [HUMAN_PROXY_LIMITS.shoulderPitch, HUMAN_PROXY_LIMITS.shoulderTwist, HUMAN_PROXY_LIMITS.shoulderSpread],
  leftHip: [HUMAN_PROXY_LIMITS.hipPitch, HUMAN_PROXY_LIMITS.hipTwist, HUMAN_PROXY_LIMITS.hipSpread],
  rightHip: [HUMAN_PROXY_LIMITS.hipPitch, HUMAN_PROXY_LIMITS.hipTwist, HUMAN_PROXY_LIMITS.hipSpread],
  torso: [HUMAN_PROXY_LIMITS.torsoPitch, HUMAN_PROXY_LIMITS.torsoYaw, HUMAN_PROXY_LIMITS.torsoRoll],
  head: [HUMAN_PROXY_LIMITS.headPitch, HUMAN_PROXY_LIMITS.headYaw, HUMAN_PROXY_LIMITS.headRoll],
}

const SINGLE_LIMITS: Record<SingleField, readonly [number, number]> = {
  leftElbow: HUMAN_PROXY_LIMITS.elbow,
  rightElbow: HUMAN_PROXY_LIMITS.elbow,
  leftKnee: HUMAN_PROXY_LIMITS.knee,
  rightKnee: HUMAN_PROXY_LIMITS.knee,
  bodyOffsetY: HUMAN_PROXY_LIMITS.bodyOffsetY,
}

function clampToLimit(value: unknown, [min, max]: readonly [number, number]): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return Math.min(max, Math.max(min, value))
}

/**
 * 把任意输入收敛成合法的自定义姿势。
 *
 * 与时间轴"坏数据只丢当前通道"同一策略：**坏字段只丢自己**，不因为一个值有问题就把
 * 整个姿势丢掉。全部字段都不可用时返回 null，调用方据此回落到预设。
 * 限位在这里生效——所以界面上的滑块与外部写入（含 AI 提交）走的是同一套约束。
 */
export function sanitizeHumanProxyPose(value: unknown): HumanProxyPose | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const source = value as Record<string, unknown>
  const result: HumanProxyPose = {}

  for (const field of HUMAN_PROXY_TRIPLE_FIELDS) {
    const raw = source[field]
    if (!Array.isArray(raw)) continue
    const triple = TRIPLE_LIMITS[field].map((limit, index) => clampToLimit(raw[index], limit))
    if (triple.every(item => item !== null)) {
      result[field] = triple as [number, number, number]
    }
  }

  for (const field of HUMAN_PROXY_SINGLE_FIELDS) {
    const value = clampToLimit(source[field], SINGLE_LIMITS[field])
    if (value !== null) result[field] = value
  }

  return Object.keys(result).length > 0 ? result : null
}

/** 取某姿势（预设 key 或自定义对象）的关节角度副本，供"从当前姿势出发微调"。 */
export function humanProxyPoseJoints(pose: HumanProxyPoseKey | HumanProxyPose): HumanProxyPose {
  return typeof pose === 'string' ? { ...(HUMAN_PROXY_POSES[pose]?.pose ?? {}) } : { ...pose }
}

/**
 * 允许的身高范围（米）。
 *
 * 超范围一律**收敛到边界**而不是拒绝：预演里"比对手高一头"是有用信息，但负身高或
 * 身高 100 会把模型压成不可见或整根穿透地面，那不是"夸张"，是坏数据。
 */
export const HUMAN_PROXY_HEIGHT = { min: 0.5, max: 2.5, default: 1.7 } as const

export function humanProxyHeight(value: unknown): number {
  const num = typeof value === 'number' && Number.isFinite(value) ? value : HUMAN_PROXY_HEIGHT.default
  return Math.min(HUMAN_PROXY_HEIGHT.max, Math.max(HUMAN_PROXY_HEIGHT.min, num))
}

/** 左右按**画面视角**命名（+X 在画面右侧），与 `humanoid-*` 网格名同一套约定。 */
export function humanProxySideName(side: -1 | 1): 'left' | 'right' {
  return side > 0 ? 'right' : 'left'
}

/** 关节组名。逐帧写姿势时靠它定位，因此渲染层与求值层共用这一个函数，不要各写一半。 */
export function humanProxyJointName(side: -1 | 1, joint: 'shoulder' | 'elbow' | 'hip' | 'knee'): string {
  return `humanoid-${humanProxySideName(side)}-${joint}-joint`
}

const JOINT_SPECS = [
  { side: -1, joint: 'shoulder', field: 'leftShoulder' },
  { side: -1, joint: 'elbow', field: 'leftElbow' },
  { side: -1, joint: 'hip', field: 'leftHip' },
  { side: -1, joint: 'knee', field: 'leftKnee' },
  { side: 1, joint: 'shoulder', field: 'rightShoulder' },
  { side: 1, joint: 'elbow', field: 'rightElbow' },
  { side: 1, joint: 'hip', field: 'rightHip' },
  { side: 1, joint: 'knee', field: 'rightKnee' },
] as const satisfies readonly {
  side: -1 | 1
  joint: 'shoulder' | 'elbow' | 'hip' | 'knee'
  field: keyof HumanProxyPose
}[]

/**
 * 把姿势**直接写进关节组**（命令式，不走 React 状态）。
 *
 * 为什么不用"每帧把新姿势塞进 props 再重渲染"：播放头由 three 的渲染循环推进，每帧重渲染
 * 一棵几十个 mesh 的子树既浪费，也和 `NodeMesh` 里处理 transform 的方式不一致（那边同样
 * 是每帧直接写 `group.position`）。这里保持同一种做法：**求值是纯函数，写入是命令式**。
 *
 * 只覆盖姿势里**出现过的**关节——动作没描述的关节保持原值（通常来自静态姿势），
 * 因此"一条只动手臂的动作"不会把腿复位成 0。
 */
export function applyPoseToJoints(root: Object3D | null, pose?: HumanProxyPose | null): void {
  if (!root || !pose) return
  for (const spec of JOINT_SPECS) {
    const value = pose[spec.field]
    if (value === undefined) continue
    const target = root.getObjectByName(humanProxyJointName(spec.side, spec.joint))
    if (!target) continue
    if (Array.isArray(value)) {
      const rotation =
        spec.joint === 'shoulder'
          ? humanProxyShoulderRotation(spec.side, value as [number, number, number])
          : spec.joint === 'hip'
            ? humanProxyHipRotation(spec.side, value as [number, number, number])
            : null
      if (rotation) target.rotation.set(rotation[0], rotation[1], rotation[2])
      continue
    }
    const rotation =
      spec.joint === 'elbow'
        ? humanProxyElbowRotation(value as number)
        : spec.joint === 'knee'
          ? humanProxyKneeRotation(value as number)
          : null
    if (rotation) target.rotation.set(rotation[0], rotation[1], rotation[2])
  }

  // 躯干与头颈：中线关节，走同一套"下标即轴序"的语义函数
  if (Array.isArray(pose.torso)) {
    const target = root.getObjectByName(HUMAN_PROXY_BODY_JOINTS.torso)
    if (target) {
      const r = humanProxyTorsoRotation(pose.torso)
      target.rotation.set(r[0], r[1], r[2])
    }
  }
  if (Array.isArray(pose.head)) {
    const target = root.getObjectByName(HUMAN_PROXY_BODY_JOINTS.head)
    if (target) {
      const r = humanProxyHeadRotation(pose.head)
      target.rotation.set(r[0], r[1], r[2])
    }
  }
  // 整体重心是**位移**而不是旋转，所以单独写 position
  if (typeof pose.bodyOffsetY === 'number') {
    const target = root.getObjectByName(HUMAN_PROXY_BODY_JOINTS.root)
    if (target) target.position.y = pose.bodyOffsetY
  }
}

/**
 * 节点 metadata 的**唯一姿势解析入口**：自定义关节角度优先、按字段覆盖预设，最后回落站立。
 *
 * 按字段合并（而不是整体替换）是刻意的：这样"只改了肘"的自定义姿势不会把其余关节
 * 悄悄拉成 0，也允许外部（含 AI）只提交它关心的那几个关节。
 */
export function resolveHumanProxyPose(metadata?: Record<string, unknown> | null): HumanProxyPose {
  const base = humanProxyPoseJoints(humanProxyPoseKey(metadata?.pose))
  const custom = sanitizeHumanProxyPose(metadata?.poseJoints)
  const merged = custom ? { ...base, ...custom } : base
  // 整体重心是"缺失即 0"的单值通道：这里显式补齐，让"从动作切回静态姿势"时
  // 命令式写入的下沉量一定被复位（其余关节是"动作没说到就保持"，语义不同）。
  return { ...merged, bodyOffsetY: merged.bodyOffsetY ?? 0 }
}

const D = Math.PI / 180

// 参考身高：所有固定尺寸按此比例布局，实际身高通过整体 scale 缩放。
const H = 1.7
// 默认身体色：中性中灰。不用纯白是因为纯白容易被下游模型读成"白衣/白皮肤"这类
// 具体材质，且打光下高光溢出让形体结构糊掉；也不用彩色（旧版为 storyai 风格蓝），
// 彩色会被当作真实配色传给生成模型。真正决定"看得清"的是**与背景的明度对比**，
// 所以这里把颜色做成可覆盖项（节点 metadata.color），默认给中性灰。
const DEFAULT_BODY = '#A8ADB5'
const DETAIL = '#0a1020'
/**
 * 头发与后脑勺的色。比身体深一档的**中性灰**（不是黑、也不是发色）：
 * 它的唯一职责是让"哪边是脸"在几十像素的视口里也能读出来，不该被读成"这个人染了头发"。
 */
const HAIR = '#6E747D'

function deg(value?: number) {
  return (value ?? 0) * D
}

function LimbMaterial({ color }: { color: string }) {
  return <meshStandardMaterial color={color} metalness={0.04} roughness={0.74} />
}

/** 胶囊肢体：中心在 position，顶端贴 group 原点。 */
function Cap({ position, radius, length, color, name }: { position: [number, number, number]; radius: number; length: number; color: string; name?: string }) {
  return (
    <mesh name={name} position={position}>
      <capsuleGeometry args={[radius, length, 8, 14]} />
      <LimbMaterial color={color} />
    </mesh>
  )
}

/** 球形关节/头。 */
function Ball({ position, radius, color, name }: { position: [number, number, number]; radius: number; color: string; name?: string }) {
  return (
    <mesh name={name} position={position}>
      <sphereGeometry args={[radius, 16, 12]} />
      <LimbMaterial color={color} />
    </mesh>
  )
}

/**
 * 头：主球 + **可读的方向线索**（五官 + 只盖后半侧的头发），朝 +Z。
 *
 * 三条刻意的夸张，都是为了"在预演视口里能看出朝向"：
 *
 * 1. **五官按"能被看见"而不是"真实比例"做**：真实人头宽 0.15m、眼睛宽约 3cm，在 320px 的
 *    视口里角色只有几十像素高——照真实比例画的五官等于不存在，而**看不出朝向的头等于没有头**。
 *    所以眼睛加大加深、加眉毛、鼻子改成凸出的锥体（侧视能看到剪影）。
 * 2. **头发只覆盖头顶与后脑勺**（碗状球壳 + 向后偏移）：这是"哪边是脸"最省事、最可靠的线索，
 *    从背后看只有一个深色后脑勺，从正面看得到脸。
 * 3. 与前一轮"人形占位只要中性、不要造型"不冲突：这些是**方向标记**而不是角色特征——
 *    全身仍是同一个中性灰，没有任何"具体是谁/穿什么"的暗示（详见 design D13）。
 */
function Head({ color, position, rotation, headR }: { color: string; position: [number, number, number]; rotation: [number, number, number]; headR: number }) {
  const eyeY = headR * 0.1
  const eyeX = headR * 0.3
  const eyeZ = headR * 0.82
  return (
    <group position={position} rotation={rotation}>
      <mesh name="humanoid-head">
        <sphereGeometry args={[headR, 26, 22]} />
        <LimbMaterial color={color} />
      </mesh>
      {/* 头发：碗状球壳（thetaLength 0.62π = 从头顶罩到赤道下方一点），向头顶与后脑偏移 */}
      <mesh name="humanoid-hair" position={[0, headR * 0.14, -headR * 0.18]} scale={[1.06, 1.0, 1.06]}>
        <sphereGeometry args={[headR, 22, 16, 0, Math.PI * 2, 0, Math.PI * 0.62]} />
        <LimbMaterial color={HAIR} />
      </mesh>
      {/* 后脑勺：额外的圆凸，从背后一眼能认出"这是后脑" */}
      <mesh name="humanoid-occiput" position={[0, -headR * 0.05, -headR * 0.72]} scale={[0.62, 0.72, 0.5]}>
        <sphereGeometry args={[headR * 0.55, 14, 12]} />
        <LimbMaterial color={HAIR} />
      </mesh>
      {/* 眼睛（加深加大）与眉毛（给出"上下"的第二个读数） */}
      {[-1, 1].map(side => (
        <group key={side}>
          <mesh name={`humanoid-${humanProxySideName(side as -1 | 1)}-eye`} position={[side * eyeX, eyeY, eyeZ]} scale={[1, 0.92, 0.5]}>
            <sphereGeometry args={[headR * 0.2, 12, 10]} />
            <LimbMaterial color={DETAIL} />
          </mesh>
          <mesh
            name={`humanoid-${humanProxySideName(side as -1 | 1)}-brow`}
            position={[side * eyeX, eyeY + headR * 0.26, eyeZ * 0.94]}
            scale={[1, 0.26, 0.42]}
          >
            <sphereGeometry args={[headR * 0.2, 12, 8]} />
            <LimbMaterial color={DETAIL} />
          </mesh>
        </group>
      ))}
      {/* 鼻子：锥体朝 +Z，尖端凸出球面约 0.04·headR —— 侧视看得见剪影 */}
      <mesh name="humanoid-nose" position={[0, -headR * 0.04, headR * 0.86]} rotation={[Math.PI / 2, 0, 0]}>
        <coneGeometry args={[headR * 0.13, headR * 0.36, 12]} />
        <LimbMaterial color={color} />
      </mesh>
      {/* 嘴 */}
      <mesh name="humanoid-mouth" position={[0, -headR * 0.32, headR * 0.8]} scale={[1.3, 0.4, 0.5]}>
        <sphereGeometry args={[headR * 0.14, 12, 8]} />
        <LimbMaterial color={DETAIL} />
      </mesh>
    </group>
  )
}

/** 手：主球 + 手指 + 拇指。 */
function Hand({ side, color, position, handR }: { side: -1 | 1; color: string; position: [number, number, number]; handR: number }) {
  const sideName = humanProxySideName(side)
  return (
    <group position={position}>
      <Ball position={[0, 0, 0]} radius={handR} color={color} name={`humanoid-${sideName}-hand`} />
      {/* 手指 */}
      <mesh name={`humanoid-${sideName}-fingers`} position={[0, -handR * 0.32, handR * 0.42]} rotation={[0.3, 0, 0]} scale={[0.6, 0.5, 0.8]}>
        <capsuleGeometry args={[handR * 0.3, handR * 0.55, 6, 10]} />
        <LimbMaterial color={color} />
      </mesh>
      {/* 拇指 */}
      <mesh name={`humanoid-${sideName}-thumb`} position={[side * handR * 0.62, -handR * 0.12, handR * 0.18]} rotation={[0.22, 0, side * 0.5]} scale={[0.42, 0.6, 0.5]}>
        <capsuleGeometry args={[handR * 0.24, handR * 0.5, 6, 10]} />
        <LimbMaterial color={color} />
      </mesh>
    </group>
  )
}

/** 脚：水平胶囊 + 脚趾帽。 */
function Foot({ side, color, position, footR }: { side: -1 | 1; color: string; position: [number, number, number]; footR: number }) {
  const sideName = humanProxySideName(side)
  return (
    <group position={position}>
      <mesh name={`humanoid-${sideName}-foot`} rotation={[Math.PI / 2, 0, 0]}>
        <capsuleGeometry args={[footR, footR * 1.7, 8, 12]} />
        <LimbMaterial color={color} />
      </mesh>
      {/* 脚趾 */}
      <mesh name={`humanoid-${sideName}-toe`} position={[0, -footR * 0.05, footR * 0.7]} scale={[0.85, 0.6, 0.55]}>
        <sphereGeometry args={[footR, 12, 10]} />
        <LimbMaterial color={color} />
      </mesh>
    </group>
  )
}

/** 手臂：肩旋转 → 上臂 → 肘旋转 → 前臂 → 手。旋转一律经语义函数，不要在 JSX 里手写欧拉角。 */
function Arm({ side, shoulder, elbow, color }: { side: 1 | -1; shoulder?: [number, number, number]; elbow?: number; color: string }) {
  const { shoulderX, shoulderY, upperLen, foreLen, radius, handR } = HUMAN_PROXY_ARM
  const sideName = humanProxySideName(side)
  // 肩点是**绝对高度** shoulderY（1.42m），但父级是躯干组（支点在髋高度），
  // 所以这里要减去支点；尺寸常量保持绝对值，测试反向解算才不用换算两套坐标。
  const shoulderAnchorY = shoulderY - HUMAN_PROXY_TORSO_PIVOT_Y
  return (
    <group
      name={humanProxyJointName(side, 'shoulder')}
      position={[side * shoulderX, shoulderAnchorY, 0]}
      rotation={humanProxyShoulderRotation(side, shoulder)}
    >
      <Cap position={[0, -(upperLen / 2 + radius), 0]} radius={radius} length={upperLen} color={color} name={`humanoid-${sideName}-upper-arm`} />
      <group name={humanProxyJointName(side, 'elbow')} position={[0, -(upperLen + radius * 2), 0]} rotation={humanProxyElbowRotation(elbow)}>
        <Ball position={[0, 0, 0]} radius={0.04} color={color} name={`humanoid-${sideName}-elbow`} />
        <Cap position={[0, -(foreLen / 2 + radius * 0.9), 0]} radius={radius * 0.9} length={foreLen} color={color} name={`humanoid-${sideName}-forearm`} />
        <Hand side={side} color={color} position={[0, -(foreLen + radius * 1.8 + handR), 0.02]} handR={handR} />
      </group>
    </group>
  )
}

/** 腿：髋旋转 → 大腿 → 膝旋转 → 小腿 → 脚。 */
function Leg({ side, hip, knee, color }: { side: 1 | -1; hip?: [number, number, number]; knee?: number; color: string }) {
  const { hipX, hipY, thighLen, calfLen, radius, footR } = HUMAN_PROXY_LEG
  const sideName = humanProxySideName(side)
  return (
    <group
      name={humanProxyJointName(side, 'hip')}
      position={[side * hipX, hipY, 0]}
      rotation={humanProxyHipRotation(side, hip)}
    >
      <Cap position={[0, -(thighLen / 2 + radius), 0]} radius={radius} length={thighLen} color={color} name={`humanoid-${sideName}-thigh`} />
      <group name={humanProxyJointName(side, 'knee')} position={[0, -(thighLen + radius * 2), 0]} rotation={humanProxyKneeRotation(knee)}>
        <Ball position={[0, 0, 0]} radius={0.052} color={color} name={`humanoid-${sideName}-knee`} />
        <Cap position={[0, -(calfLen / 2 + radius * 0.9), 0]} radius={radius * 0.9} length={calfLen} color={color} name={`humanoid-${sideName}-calf`} />
        <Foot side={side} color={color} position={[0, -(calfLen + radius * 1.8 + footR), 0.02]} footR={footR} />
      </group>
    </group>
  )
}

export function ProceduralHumanProxy({ pose, color = DEFAULT_BODY, height = 1.7 }: { pose?: HumanProxyPoseKey | HumanProxyPose; color?: string; height?: number }) {
  const poseDef: HumanProxyPose =
    typeof pose === 'string' ? (HUMAN_PROXY_POSES[pose]?.pose ?? {}) : (pose ?? {})
  // 真人比例（1.70m 基准）：头身比 1/7.6（头高 0.224m）、腿长占身高 54%、
  // 胸宽 0.31m、脚底正好落在 y=0。比例预演是预演台的立身功能，失真即缺陷。
  const headR = 0.112
  const chestR = 0.155
  const chestLen = 0.24
  const pelvisR = 0.11
  const scale = (height || H) / H
  const torsoPivot = HUMAN_PROXY_TORSO_PIVOT_Y
  const headPivot = HUMAN_PROXY_HEAD_PIVOT_Y
  const offsetY = poseDef.bodyOffsetY ?? 0
  return (
    <group scale={scale}>
      {/* 重心组：整体升降挂在这里。放在缩放之内，所以"下沉 0.2m"是按身高比例缩放的 */}
      <group name={HUMAN_PROXY_BODY_JOINTS.root} position={[0, offsetY, 0]}>
        {/*
          躯干组：胸腔、头颈与**两条手臂**都是它的子级。
          手臂必须挂进来——肩长在胸上，躯干前倾时手臂要跟着走；若保持兄弟节点，
          鞠躬会出现"上身转了、双臂留在原地"的断体（这正是外部实现的常见缺陷）。
        */}
        <group
          name={HUMAN_PROXY_BODY_JOINTS.torso}
          position={[0, torsoPivot, 0]}
          rotation={humanProxyTorsoRotation(poseDef.torso)}
        >
          <Cap position={[0, 1.2 - torsoPivot, 0]} radius={chestR} length={chestLen} color={color} name="humanoid-chest" />
          {/*
            胸前方向标记：圆柱躯干绕自身轴转 20° 在画面上几乎看不出差别，因此给正面一个深色小标记。
            与头部的五官同一性质——**方向线索**，不是角色造型（见 design D13）。
          */}
          <mesh name="humanoid-chest-marker" position={[0, 1.2 - torsoPivot + 0.02, chestR * 0.9]} scale={[0.42, 0.3, 0.2]}>
            <sphereGeometry args={[chestR, 14, 12]} />
            <LimbMaterial color={DETAIL} />
          </mesh>
          {/* 头颈组：脖子与头一起转，避免"只转头"留下断开的脖子 */}
          <group
            name={HUMAN_PROXY_BODY_JOINTS.head}
            position={[0, headPivot - torsoPivot, 0]}
            rotation={humanProxyHeadRotation(poseDef.head)}
          >
            <mesh position={[0, 1.47 - headPivot, 0]}>
              <cylinderGeometry args={[headR * 0.45, headR * 0.55, 0.07, 12]} />
              <LimbMaterial color={color} />
            </mesh>
            <Head color={color} position={[0, 1.588 - headPivot, 0]} rotation={[0, 0, 0]} headR={headR} />
          </group>
          <Arm side={-1} shoulder={poseDef.leftShoulder} elbow={poseDef.leftElbow} color={color} />
          <Arm side={1} shoulder={poseDef.rightShoulder} elbow={poseDef.rightElbow} color={color} />
        </group>
        {/* 骨盆与腿**不从躯干分支**：它们是髋部。跟着前倾一起转会把"鞠躬"变成整体前倒 */}
        <Ball position={[0, 0.92, 0]} radius={pelvisR} color={color} name="humanoid-pelvis" />
        <Leg side={-1} hip={poseDef.leftHip} knee={poseDef.leftKnee} color={color} />
        <Leg side={1} hip={poseDef.rightHip} knee={poseDef.rightKnee} color={color} />
      </group>
    </group>
  )
}
