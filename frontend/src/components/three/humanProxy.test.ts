import { describe, expect, it } from 'vitest'
import * as THREE from 'three'
import {
  HUMAN_PROXY_ARM,
  HUMAN_PROXY_BODY_JOINTS,
  HUMAN_PROXY_HEAD_PIVOT_Y,
  HUMAN_PROXY_HEIGHT,
  HUMAN_PROXY_LEG,
  HUMAN_PROXY_POSES,
  HUMAN_PROXY_TORSO,
  HUMAN_PROXY_TORSO_PIVOT_Y,
  applyPoseToJoints,
  humanProxyElbowRotation,
  humanProxyHeadRotation,
  humanProxyHeight,
  humanProxyHipRotation,
  humanProxyJointName,
  humanProxyKneeRotation,
  humanProxyShoulderRotation,
  humanProxyTorsoRotation,
  resolveHumanProxyPose,
  sanitizeHumanProxyPose,
  type HumanProxyPose,
} from './humanProxy'

/**
 * 姿势缺陷回归测试。
 *
 * 这组断言存在的原因：`humanProxy.tsx` 的六个姿势曾有一半以上是坏的——
 * 肩/髋忘了按侧镜像（T 字两臂对穿）、肘关节绕错轴（挥手时手穿进躯干）、
 * 膝的符号反了（行走膝盖反折）、髋的 spread 未镜像（两脚收到中线）。
 * 这些问题在 320×480 的视口里肉眼很难稳定判断，只能靠数值钉住。
 *
 * 反向解算刻意复刻 `ProceduralHumanProxy` 的 JSX 嵌套（肩→肘→手、髋→膝→脚），
 * 但**复用组件导出的尺寸常量与关节语义函数**——所以改尺寸或改轴向时测试会跟着动，
 * 只有"改嵌套顺序"才需要同步这里（那也只有两行）。
 */
function limbJoints(pose: HumanProxyPose, side: -1 | 1) {
  const suffix = side > 0 ? 'right' : 'left'
  // 层级必须与 `ProceduralHumanProxy` 一致：重心组 → 躯干组 → 手臂，腿挂在重心组上。
  // 躯干/头颈/重心的语义由下面的专题断言钉住；这里先把它们接进来，
  // 否则"鞠躬时手臂没跟着走"这类缺陷在反向解算里根本看不见。
  const root = new THREE.Object3D()
  root.position.set(0, pose.bodyOffsetY ?? 0, 0)
  const torso = new THREE.Object3D()
  torso.position.set(0, HUMAN_PROXY_TORSO_PIVOT_Y, 0)
  torso.rotation.fromArray(humanProxyTorsoRotation(pose.torso))
  root.add(torso)
  const head = new THREE.Object3D()
  head.position.set(0, HUMAN_PROXY_HEAD_PIVOT_Y - HUMAN_PROXY_TORSO_PIVOT_Y, 0)
  head.rotation.fromArray(humanProxyHeadRotation(pose.head))
  torso.add(head)
  // 两个朝向标记：鼻子在头局部 +Z（角色朝 +Z），头顶在 +Y。
  // 低头/转头看鼻子，侧头看头顶——只用其中一个会漏掉另外两个轴的错误。
  const nose = new THREE.Object3D()
  nose.position.set(0, 0, 0.09)
  head.add(nose)
  const crown = new THREE.Object3D()
  crown.position.set(0, 0.09, 0)
  head.add(crown)

  const { shoulderX, shoulderY, upperLen, foreLen, radius, handR } = HUMAN_PROXY_ARM
  const shoulder = new THREE.Object3D()
  shoulder.position.set(side * shoulderX, shoulderY - HUMAN_PROXY_TORSO_PIVOT_Y, 0)
  shoulder.rotation.fromArray(humanProxyShoulderRotation(side, pose[`${suffix}Shoulder`]))
  const elbow = new THREE.Object3D()
  elbow.position.set(0, -(upperLen + radius * 2), 0)
  elbow.rotation.fromArray(humanProxyElbowRotation(pose[`${suffix}Elbow`]))
  const hand = new THREE.Object3D()
  hand.position.set(0, -(foreLen + radius * 1.8 + handR), 0.02)
  shoulder.add(elbow)
  elbow.add(hand)
  torso.add(shoulder)

  const { hipX, hipY, thighLen, calfLen, radius: legR, footR } = HUMAN_PROXY_LEG
  const hip = new THREE.Object3D()
  hip.position.set(side * hipX, hipY, 0)
  hip.rotation.fromArray(humanProxyHipRotation(side, pose[`${suffix}Hip`]))
  const knee = new THREE.Object3D()
  knee.position.set(0, -(thighLen + legR * 2), 0)
  knee.rotation.fromArray(humanProxyKneeRotation(pose[`${suffix}Knee`]))
  const foot = new THREE.Object3D()
  foot.position.set(0, -(calfLen + legR * 1.8 + footR), 0.02)
  hip.add(knee)
  knee.add(foot)
  root.add(hip)

  root.updateMatrixWorld(true)
  return {
    hand: hand.getWorldPosition(new THREE.Vector3()),
    elbow: elbow.getWorldPosition(new THREE.Vector3()),
    knee: knee.getWorldPosition(new THREE.Vector3()),
    foot: foot.getWorldPosition(new THREE.Vector3()),
    head: head.getWorldPosition(new THREE.Vector3()),
    nose: nose.getWorldPosition(new THREE.Vector3()),
    crown: crown.getWorldPosition(new THREE.Vector3()),
    torso,
  }
}

/**
 * 手是否落进躯干胶囊。
 *
 * 判据在**躯干局部坐标系**里做（把点用躯干世界矩阵的逆变换回去）：躯干前倾后，
 * 若仍按世界坐标判"沿 Y 轴的胶囊"，一个正确的前倾姿势会被误判成"手穿进身体"。
 * 胶囊的绝对高度常量要减去躯干支点，因为躯干组的原点在髋高度。
 */
function insideTorso(point: THREE.Vector3, torso: THREE.Object3D) {
  const local = point.clone().applyMatrix4(new THREE.Matrix4().copy(torso.matrixWorld).invert())
  return (
    Math.abs(local.x) < HUMAN_PROXY_TORSO.chestR &&
    Math.abs(local.z) < HUMAN_PROXY_TORSO.chestR &&
    local.y > HUMAN_PROXY_TORSO.chestBottom - HUMAN_PROXY_TORSO_PIVOT_Y &&
    local.y < HUMAN_PROXY_TORSO.chestTop - HUMAN_PROXY_TORSO_PIVOT_Y
  )
}

/**
 * 膝盖相对大腿的弯曲方向：把小腿方向转进大腿局部坐标系。
 * 用局部系而不是世界系，是因为**跨步时前腿的小腿本来就朝前**（世界系判据会把正确的
 * 行走姿势误判成"反折"）；真正要禁的是"小腿相对大腿向前折"，即局部 z 不得为正。
 */
function kneeBendLocal(side: -1 | 1, pose: HumanProxyPose, knee: THREE.Vector3, foot: THREE.Vector3) {
  const suffix = side > 0 ? 'right' : 'left'
  const hip = new THREE.Vector3(side * HUMAN_PROXY_LEG.hipX, HUMAN_PROXY_LEG.hipY, 0)
  const inverse = new THREE.Matrix4()
    .makeRotationFromEuler(new THREE.Euler(...humanProxyHipRotation(side, pose[`${suffix}Hip`])))
    .invert()
  const thigh = knee.clone().sub(hip).applyMatrix4(inverse)
  const shin = foot.clone().sub(knee).applyMatrix4(inverse)
  return shin.z - thigh.z
}

const POSES = Object.entries(HUMAN_PROXY_POSES) as [keyof typeof HUMAN_PROXY_POSES, { label: string; pose: HumanProxyPose }][]

describe('人形占位姿势的解剖不变量', () => {
  for (const [key, { pose }] of POSES) {
    for (const side of [-1, 1] as const) {
      const label = `${key} / side=${side}`

      it(`${label}：手不越过身体中线`, () => {
        const { hand } = limbJoints(pose, side)
        // 允许极小偏移（正前方/正后方），但不能出现明显的对穿
        if (Math.abs(hand.x) > 0.02) {
          expect(Math.sign(hand.x)).toBe(side)
        }
      })

      it(`${label}：手不穿进躯干`, () => {
        const { hand, torso } = limbJoints(pose, side)
        expect(insideTorso(hand, torso)).toBe(false)
      })

      it(`${label}：膝盖不反折（相对大腿只向后弯）`, () => {
        const { knee, foot } = limbJoints(pose, side)
        expect(kneeBendLocal(side, pose, knee, foot)).toBeLessThanOrEqual(0.02)
      })

      it(`${label}：脚底不陷入地面`, () => {
        const { foot } = limbJoints(pose, side)
        expect(foot.y - HUMAN_PROXY_LEG.footR).toBeGreaterThan(-0.01)
      })
    }
  }

  it('T 字：两臂向两侧水平伸展，且互不交叉', () => {
    const pose = HUMAN_PROXY_POSES.tpose.pose
    const left = limbJoints(pose, -1).hand
    const right = limbJoints(pose, 1).hand
    expect(left.x).toBeLessThan(0)
    expect(right.x).toBeGreaterThan(0)
    expect(Math.abs(left.x)).toBeGreaterThan(0.8)
    expect(Math.abs(right.x)).toBeGreaterThan(0.8)
    // 水平：手腕高度接近肩高，且没有明显前后偏移
    expect(Math.abs(left.y - HUMAN_PROXY_ARM.shoulderY)).toBeLessThan(0.15)
    expect(Math.abs(right.y - HUMAN_PROXY_ARM.shoulderY)).toBeLessThan(0.15)
    expect(Math.abs(right.z - left.z)).toBeLessThan(0.01)
  })

  it('行走：两脚不收到中线，且前后分开', () => {
    const pose = HUMAN_PROXY_POSES.walk.pose
    const { foot: leftFoot } = limbJoints(pose, -1)
    const { foot: rightFoot } = limbJoints(pose, 1)
    expect(Math.abs(leftFoot.x)).toBeGreaterThan(0.04)
    expect(Math.abs(rightFoot.x)).toBeGreaterThan(0.04)
    // 一前一后（z 方向分离），否则看不出是行走
    expect(Math.abs(leftFoot.z - rightFoot.z)).toBeGreaterThan(0.15)
  })

  it('挥手：举手到肩以上，且落在身体前方', () => {
    const pose = HUMAN_PROXY_POSES.wave.pose
    const { hand } = limbJoints(pose, 1)
    // 举起来是这条姿势的意义；"不在躯干里"由上面的通用断言负责
    expect(hand.y).toBeGreaterThan(HUMAN_PROXY_ARM.shoulderY + 0.15)
    expect(hand.z).toBeGreaterThan(0)
  })

  it('指向：手伸到身体前方', () => {
    const pose = HUMAN_PROXY_POSES.point.pose
    const { hand } = limbJoints(pose, 1)
    expect(hand.z).toBeGreaterThan(0.3)
  })

  it('坐姿：小腿垂下而不是向前踢', () => {
    const pose = HUMAN_PROXY_POSES.sit.pose
    const { knee, foot } = limbJoints(pose, -1)
    // 大腿前抬
    expect(knee.z).toBeGreaterThan(0.2)
    // 小腿基本竖直（脚在膝下方，且几乎不再向前）
    expect(foot.y).toBeLessThan(knee.y - 0.3)
    expect(Math.abs(foot.z - knee.z)).toBeLessThan(0.12)
  })
})

describe('逐帧写入关节（applyPoseToJoints）', () => {
  const JOINTS = ['shoulder', 'elbow', 'hip', 'knee'] as const

  function jointTree() {
    const root = new THREE.Group()
    for (const side of [-1, 1] as const) {
      for (const joint of JOINTS) {
        const node = new THREE.Object3D()
        node.name = humanProxyJointName(side, joint)
        root.add(node)
      }
    }
    return root
  }

  it('按关节语义写入，且左右镜像（同一个 spread 值在两侧朝相反方向张开）', () => {
    const root = jointTree()
    applyPoseToJoints(root, { leftShoulder: [10, 0, 80], leftElbow: -30, rightKnee: 20 })
    const leftShoulder = root.getObjectByName(humanProxyJointName(-1, 'shoulder'))!
    const rightShoulder = root.getObjectByName(humanProxyJointName(1, 'shoulder'))!
    const leftElbow = root.getObjectByName(humanProxyJointName(-1, 'elbow'))!
    const rightKnee = root.getObjectByName(humanProxyJointName(1, 'knee'))!
    const D = Math.PI / 180
    expect(leftShoulder.rotation.x).toBeCloseTo(10 * D, 6)
    expect(leftShoulder.rotation.z).toBeCloseTo(-80 * D, 6)
    expect(rightShoulder.rotation.z).toBeCloseTo(0, 6)
    // 肘绕 X（向前屈）、膝绕 X（向后收），符号由语义函数决定
    expect(leftElbow.rotation.x).toBeCloseTo(-30 * D, 6)
    expect(rightKnee.rotation.x).toBeCloseTo(20 * D, 6)
  })

  it('只覆盖姿势里出现过的关节，不把其它关节复位', () => {
    const root = jointTree()
    applyPoseToJoints(root, { leftKnee: 40 })
    const leftKnee = root.getObjectByName(humanProxyJointName(-1, 'knee'))!
    const rightKnee = root.getObjectByName(humanProxyJointName(1, 'knee'))!
    rightKnee.rotation.x = 0.5
    // 再写一条"只动手臂"的动作：腿上的值必须原样保留
    applyPoseToJoints(root, { leftElbow: -15 })
    expect(leftKnee.rotation.x).toBeCloseTo(40 * (Math.PI / 180), 6)
    expect(rightKnee.rotation.x).toBeCloseTo(0.5, 6)
  })

  it('根节点或姿势缺失时安全返回（渲染层每帧都会调它）', () => {
    expect(() => applyPoseToJoints(null, { leftKnee: 10 })).not.toThrow()
    expect(() => applyPoseToJoints(new THREE.Group(), null)).not.toThrow()
    expect(() => applyPoseToJoints(new THREE.Group(), undefined)).not.toThrow()
  })

  function bodyJointTree() {
    const root = jointTree()
    for (const name of [HUMAN_PROXY_BODY_JOINTS.root, HUMAN_PROXY_BODY_JOINTS.torso, HUMAN_PROXY_BODY_JOINTS.head]) {
      const node = new THREE.Object3D()
      node.name = name
      root.add(node)
    }
    return root
  }

  it('躯干 / 头颈按轴序写入；重心是**位移**而不是旋转', () => {
    const root = bodyJointTree()
    applyPoseToJoints(root, { torso: [10, 20, 30], head: [40, 0, 0], bodyOffsetY: -0.2 })
    const D = Math.PI / 180
    const torso = root.getObjectByName(HUMAN_PROXY_BODY_JOINTS.torso)!
    const head = root.getObjectByName(HUMAN_PROXY_BODY_JOINTS.head)!
    const bodyRoot = root.getObjectByName(HUMAN_PROXY_BODY_JOINTS.root)!
    expect(torso.rotation.x).toBeCloseTo(10 * D, 6)
    expect(torso.rotation.y).toBeCloseTo(20 * D, 6)
    expect(torso.rotation.z).toBeCloseTo(30 * D, 6)
    expect(head.rotation.x).toBeCloseTo(40 * D, 6)
    expect(bodyRoot.position.y).toBeCloseTo(-0.2, 6)
  })

  it('重心通道缺失时不写（与其它通道一致：动作没说到就保持）', () => {
    const root = bodyJointTree()
    const bodyRoot = root.getObjectByName(HUMAN_PROXY_BODY_JOINTS.root)!
    bodyRoot.position.y = -0.3
    applyPoseToJoints(root, { torso: [10, 0, 0] })
    expect(bodyRoot.position.y).toBeCloseTo(-0.3, 6)
  })
})

describe('身高收敛', () => {
  it('缺省与非法值回落到默认身高', () => {
    expect(humanProxyHeight(undefined)).toBe(HUMAN_PROXY_HEIGHT.default)
    expect(humanProxyHeight('1.8')).toBe(HUMAN_PROXY_HEIGHT.default)
    expect(humanProxyHeight(Number.NaN)).toBe(HUMAN_PROXY_HEIGHT.default)
  })

  it('超范围收敛到边界（负身高或身高 100 不是"夸张"，是坏数据）', () => {
    expect(humanProxyHeight(-3)).toBe(HUMAN_PROXY_HEIGHT.min)
    expect(humanProxyHeight(0)).toBe(HUMAN_PROXY_HEIGHT.min)
    expect(humanProxyHeight(100)).toBe(HUMAN_PROXY_HEIGHT.max)
  })

  it('正常范围内原样返回', () => {
    expect(humanProxyHeight(1.75)).toBe(1.75)
  })
})

describe('姿势解析、合并与生理限位（design D10）', () => {
  it('没有任何 metadata 时回落到站立（重心通道总会显式给值）', () => {
    // bodyOffsetY 是"缺失即 0"的单值通道，解析入口总会补上它，
    // 这样"从动作切回静态姿势"时命令式写入的下沉量一定被复位
    expect(resolveHumanProxyPose(undefined)).toEqual({ bodyOffsetY: 0 })
    expect(resolveHumanProxyPose({})).toEqual({ bodyOffsetY: 0 })
  })

  it('只有预设 key 时用预设', () => {
    expect(resolveHumanProxyPose({ pose: 'tpose' })).toEqual({ ...HUMAN_PROXY_POSES.tpose.pose, bodyOffsetY: 0 })
  })

  it('自定义按字段覆盖预设，未给的字段保留预设值', () => {
    const resolved = resolveHumanProxyPose({ pose: 'wave', poseJoints: { leftKnee: 30 } })
    expect(resolved.leftKnee).toBe(30)
    // 挥手是举起手臂的姿势，覆盖一个膝角度不该把手臂拉直
    expect(resolved.rightElbow).toBe(HUMAN_PROXY_POSES.wave.pose.rightElbow)
    expect(resolved.rightShoulder).toEqual(HUMAN_PROXY_POSES.wave.pose.rightShoulder)
  })

  it('肘不允许反折、膝不允许反折（生理不可能的方向被夹到 0）', () => {
    const resolved = resolveHumanProxyPose({ poseJoints: { leftElbow: 40, leftKnee: -20 } })
    expect(resolved.leftElbow).toBe(0)
    expect(resolved.leftKnee).toBe(0)
  })

  it('超出范围夹到边界，而不是丢弃', () => {
    const resolved = resolveHumanProxyPose({ poseJoints: { leftShoulder: [999, 999, 999] } })
    expect(resolved.leftShoulder).toEqual([70, 90, 170])
  })

  it('非法字段只丢自己，其余字段照常生效', () => {
    const resolved = resolveHumanProxyPose({
      poseJoints: { leftElbow: 'x', leftKnee: 45, rightShoulder: ['a', 0, 0] },
    })
    expect(resolved.leftElbow).toBeUndefined()
    expect(resolved.leftKnee).toBe(45)
    expect(resolved.rightShoulder).toBeUndefined()
  })

  it('自定义整体不可用时回落预设', () => {
    expect(resolveHumanProxyPose({ pose: 'sit', poseJoints: 'nope' })).toEqual({ ...HUMAN_PROXY_POSES.sit.pose, bodyOffsetY: 0 })
  })

  it('sanitize 拒绝非对象输入', () => {
    expect(sanitizeHumanProxyPose(null)).toBeNull()
    expect(sanitizeHumanProxyPose([])).toBeNull()
    expect(sanitizeHumanProxyPose('stand')).toBeNull()
    expect(sanitizeHumanProxyPose(12)).toBeNull()
  })

  it('NaN / Infinity 被视为非法而不是夹成边界', () => {
    expect(sanitizeHumanProxyPose({ leftKnee: Number.NaN })).toBeNull()
    expect(sanitizeHumanProxyPose({ rightKnee: Number.POSITIVE_INFINITY })).toBeNull()
  })
})

/**
 * 躯干与头颈的朝向语义。
 *
 * 这几个断言存在的原因：中线部位的**正 pitch 是"向前低"**，与四肢的"正 pitch = 向身后摆"
 * 含义相反（旋向其实是同一个，因为部位朝向相反）。这一条只能靠数值钉住——
 * 在 320×480 的视口里，"低头 30°"与"抬头 30°"看起来都只是"头有点怪"。
 */
describe('躯干与头颈的朝向语义', () => {
  it('轴向映射：三元组下标即轴序 [pitch(X), yaw(Y), roll(Z)]，且中线部位不镜像', () => {
    const D = Math.PI / 180
    expect(humanProxyTorsoRotation([10, 20, 30])).toEqual([10 * D, 20 * D, 30 * D])
    expect(humanProxyHeadRotation([10, 20, 30])).toEqual([10 * D, 20 * D, 30 * D])
    // 没有 side 参数：中线部位镜像只会变成"往同一边歪"
    expect(humanProxyTorsoRotation(undefined)).toEqual([0, 0, 0])
    expect(humanProxyHeadRotation(undefined)).toEqual([0, 0, 0])
  })

  it('躯干正 pitch = 前倾：头往前（+Z）并降低', () => {
    const rest = limbJoints({}, -1)
    const bow = limbJoints({ torso: [50, 0, 0] }, -1)
    expect(bow.head.z).toBeGreaterThan(rest.head.z + 0.1)
    expect(bow.head.y).toBeLessThan(rest.head.y - 0.05)
  })

  it('躯干前倾会带动手臂（肩长在胸上，不是兄弟节点）', () => {
    const rest = limbJoints({}, -1)
    const bow = limbJoints({ torso: [50, 0, 0] }, -1)
    // 肘随肩前移并下降；若手臂仍是躯干的兄弟节点，这两个值不会变
    expect(bow.elbow.z).toBeGreaterThan(rest.elbow.z + 0.05)
    expect(bow.elbow.y).toBeLessThan(rest.elbow.y - 0.02)
    // 手臂本身没有变形：肘-手距离不变
    expect(bow.hand.distanceTo(bow.elbow)).toBeCloseTo(rest.hand.distanceTo(rest.elbow), 6)
  })

  it('头颈正 pitch = 低头：鼻子下降', () => {
    const rest = limbJoints({}, -1)
    const down = limbJoints({ head: [40, 0, 0] }, -1)
    expect(down.nose.y).toBeLessThan(rest.nose.y - 0.02)
  })

  it('头颈正 yaw = 转向画面右侧（+X）', () => {
    const rest = limbJoints({}, -1)
    const turned = limbJoints({ head: [0, 60, 0] }, -1)
    expect(turned.nose.x).toBeGreaterThan(rest.nose.x + 0.05)
  })

  it('头颈正 roll = 向画面左侧倾（头顶倒向 −X）', () => {
    const rest = limbJoints({}, -1)
    const tilted = limbJoints({ head: [0, 0, 20] }, -1)
    expect(tilted.crown.x).toBeLessThan(rest.crown.x - 0.02)
  })

  it('整体下沉是位移：单独下沉会让脚陷地（所以蹲姿必须配髋膝屈曲）', () => {
    const standing = limbJoints({}, -1)
    const sunk = limbJoints({ bodyOffsetY: -0.2 }, -1)
    expect(standing.foot.y - HUMAN_PROXY_LEG.footR).toBeCloseTo(0, 2)
    expect(sunk.foot.y - HUMAN_PROXY_LEG.footR).toBeLessThan(-0.15)
  })

  it('半蹲：与后端 `crouch` 同一组数值下脚底仍然贴地', () => {
    // 数值与 backend/app/services/previs/motion_seed.py 的 _CROUCH 保持一致（改一边要改另一边）
    const crouch: HumanProxyPose = {
      bodyOffsetY: -0.165,
      leftHip: [-52, 0, 7],
      rightHip: [-52, 0, 7],
      leftKnee: 52,
      rightKnee: 52,
      torso: [20, 0, 0],
      head: [-12, 0, 0],
    }
    for (const side of [-1, 1] as const) {
      const { foot } = limbJoints(crouch, side)
      expect(Math.abs(foot.y - HUMAN_PROXY_LEG.footR)).toBeLessThan(0.03)
    }
  })
})

describe('新增通道的限位与坏数据', () => {
  it('躯干 / 头颈超范围被夹到边界', () => {
    const pose = sanitizeHumanProxyPose({ torso: [200, -200, 0], head: [0, 0, 90] })
    expect(pose?.torso).toEqual([60, -60, 0])
    expect(pose?.head).toEqual([0, 0, 30])
  })

  it('重心下沉超范围被夹到边界；非数值只丢自己', () => {
    expect(sanitizeHumanProxyPose({ bodyOffsetY: -5 })?.bodyOffsetY).toBe(-0.8)
    expect(sanitizeHumanProxyPose({ bodyOffsetY: 3 })?.bodyOffsetY).toBe(0.25)
    // 唯一字段非法 → 整个姿势不可用
    expect(sanitizeHumanProxyPose({ bodyOffsetY: 'low' })).toBeNull()
  })

  it('坏字段只丢自己：躯干非法不影响头颈与四肢', () => {
    const pose = sanitizeHumanProxyPose({ torso: 'x', head: [0, 30, 0], leftKnee: 40 })
    expect(pose?.torso).toBeUndefined()
    expect(pose?.head).toEqual([0, 30, 0])
    expect(pose?.leftKnee).toBe(40)
  })

  it('中线通道由逐帧求值还原（下标即轴序）', () => {
    const pose = sanitizeHumanProxyPose({ torso: [12, 0, 0], head: [0, 24, 0], bodyOffsetY: -0.1 })
    expect(pose).toEqual({ torso: [12, 0, 0], head: [0, 24, 0], bodyOffsetY: -0.1 })
  })
})
