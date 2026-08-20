/**
 * YLCraft — 程序化人形占位（胶囊人）
 *
 * 用胶囊/球/圆柱组合出轻量人形，参照 storyai-3d-director-desk 的
 * ProceduralMannequin（MIT）分层关节思路，但为本项目自写实现：
 * 肢体为胶囊几何体，关节为球体，肩/肘/髋/膝分层旋转应用姿势；
 * 头部带眼睛/鼻子/嘴等五官，手带手指/拇指，脚带脚趾，增强人偶辨识度。
 * 无外部模型文件、无版权风险；姿势只存 metadata.pose（预设 key），
 * 不承载 Story 业务状态。
 */

export type HumanProxyPoseKey = 'stand' | 'tpose' | 'walk' | 'sit' | 'wave' | 'point'

export interface HumanProxyPose {
  /** [pitch, twist, spread]，单位度：pitch 绕 X（前后摆），twist 绕 Y（内旋），spread 绕 Z（侧举） */
  leftShoulder?: [number, number, number]
  rightShoulder?: [number, number, number]
  /** 屈肘角度（度），负值为前臂前弯 */
  leftElbow?: number
  rightElbow?: number
  /** [pitch, twist, spread]，pitch 正值大腿向后（远离相机） */
  leftHip?: [number, number, number]
  rightHip?: [number, number, number]
  /** 屈膝角度（度），负值为小腿后弯 */
  leftKnee?: number
  rightKnee?: number
}

export const HUMAN_PROXY_POSES: Record<HumanProxyPoseKey, { label: string; pose: HumanProxyPose }> = {
  stand: { label: '站立', pose: {} },
  tpose: { label: 'T 字', pose: { leftShoulder: [0, 0, 85], rightShoulder: [0, 0, -85] } },
  walk: {
    label: '行走',
    pose: {
      leftHip: [18, 0, 8],
      rightHip: [-14, 0, -6],
      leftKnee: -32,
      rightKnee: 16,
      leftShoulder: [0, 0, 16],
      rightShoulder: [0, 0, -18],
      leftElbow: -20,
      rightElbow: -24,
    },
  },
  sit: {
    label: '坐姿',
    pose: {
      leftHip: [80, 0, 5],
      rightHip: [80, 0, -5],
      leftKnee: -100,
      rightKnee: -100,
      leftShoulder: [0, 0, 10],
      rightShoulder: [0, 0, -10],
      leftElbow: -45,
      rightElbow: -45,
    },
  },
  wave: {
    label: '挥手',
    pose: {
      rightShoulder: [0, -60, -30],
      rightElbow: -45,
      leftShoulder: [0, 0, 8],
      leftElbow: -12,
    },
  },
  point: {
    label: '指向',
    pose: {
      rightShoulder: [0, 20, -60],
      rightElbow: -10,
      leftShoulder: [0, 0, 8],
    },
  },
}

export function humanProxyPoseKey(value: unknown): HumanProxyPoseKey {
  return typeof value === 'string' && value in HUMAN_PROXY_POSES ? (value as HumanProxyPoseKey) : 'stand'
}

const D = Math.PI / 180

// 参考身高：所有固定尺寸按此比例布局，实际身高通过整体 scale 缩放。
const H = 1.7
// 默认身体色（storyai 风格蓝），细节（眼睛/嘴）用深色
const DEFAULT_BODY = '#4F8EF7'
const DETAIL = '#0a1020'

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

/** 头：主球 + 面部凸起 + 眼睛/鼻子/嘴，朝 +Z。 */
function Head({ color, position, rotation, headR }: { color: string; position: [number, number, number]; rotation: [number, number, number]; headR: number }) {
  const eyeY = headR * 0.16
  const eyeX = headR * 0.24
  const faceZ = headR * 0.52
  const eyeZ = headR * 0.78
  return (
    <group position={position} rotation={rotation}>
      <mesh name="humanoid-head">
        <sphereGeometry args={[headR, 26, 22]} />
        <LimbMaterial color={color} />
      </mesh>
      {/* 面部凸起，让头不是纯圆球 */}
      <mesh name="humanoid-face" position={[0, -headR * 0.08, headR * 0.45]} scale={[0.74, 0.56, 0.4]}>
        <sphereGeometry args={[headR * 0.5, 16, 12]} />
        <LimbMaterial color={color} />
      </mesh>
      {/* 眼睛 */}
      <mesh name="humanoid-left-eye" position={[-eyeX, eyeY, eyeZ]} scale={[1, 0.6, 0.35]}>
        <sphereGeometry args={[headR * 0.14, 10, 8]} />
        <LimbMaterial color={DETAIL} />
      </mesh>
      <mesh name="humanoid-right-eye" position={[eyeX, eyeY, eyeZ]} scale={[1, 0.6, 0.35]}>
        <sphereGeometry args={[headR * 0.14, 10, 8]} />
        <LimbMaterial color={DETAIL} />
      </mesh>
      {/* 鼻子 */}
      <mesh name="humanoid-nose" position={[0, -headR * 0.02, headR * 0.88]} scale={[0.5, 0.72, 0.5]}>
        <sphereGeometry args={[headR * 0.09, 10, 8]} />
        <LimbMaterial color={color} />
      </mesh>
      {/* 嘴 */}
      <mesh name="humanoid-mouth" position={[0, -headR * 0.24, headR * 0.8]} scale={[1, 0.55, 0.4]}>
        <sphereGeometry args={[headR * 0.09, 10, 8]} />
        <LimbMaterial color={DETAIL} />
      </mesh>
    </group>
  )
}

/** 手：主球 + 手指 + 拇指。 */
function Hand({ side, color, position, handR }: { side: -1 | 1; color: string; position: [number, number, number]; handR: number }) {
  const sideName = side > 0 ? 'right' : 'left'
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
  const sideName = side > 0 ? 'right' : 'left'
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

/** 手臂：肩旋转 → 上臂 → 肘旋转 → 前臂 → 手。 */
function Arm({ side, shoulderRot, elbow, color }: { side: 1 | -1; shoulderRot: [number, number, number]; elbow: number; color: string }) {
  const upperLen = 0.28
  const foreLen = 0.24
  const radius = 0.05
  const handR = 0.055
  const shoulderY = 1.28
  const sideName = side > 0 ? 'right' : 'left'
  return (
    <group position={[side * 0.21, shoulderY, 0]} rotation={shoulderRot}>
      <Cap position={[0, -(upperLen / 2 + radius), 0]} radius={radius} length={upperLen} color={color} name={`humanoid-${sideName}-upper-arm`} />
      <group position={[0, -(upperLen + radius * 2), 0]} rotation={[0, 0, deg(elbow)]}>
        <Ball position={[0, 0, 0]} radius={0.045} color={color} name={`humanoid-${sideName}-elbow`} />
        <Cap position={[0, -(foreLen / 2 + radius * 0.9), 0]} radius={radius * 0.9} length={foreLen} color={color} name={`humanoid-${sideName}-forearm`} />
        <Hand side={side} color={color} position={[0, -(foreLen + radius * 1.8 + handR), 0.02]} handR={handR} />
      </group>
    </group>
  )
}

/** 腿：髋旋转 → 大腿 → 膝旋转 → 小腿 → 脚。 */
function Leg({ side, hipRot, knee, color }: { side: 1 | -1; hipRot: [number, number, number]; knee: number; color: string }) {
  const thighLen = 0.36
  const calfLen = 0.33
  const radius = 0.058
  const footR = 0.05
  const hipY = 0.9
  const sideName = side > 0 ? 'right' : 'left'
  return (
    <group position={[side * 0.1, hipY, 0]} rotation={hipRot}>
      <Cap position={[0, -(thighLen / 2 + radius), 0]} radius={radius} length={thighLen} color={color} name={`humanoid-${sideName}-thigh`} />
      <group position={[0, -(thighLen + radius * 2), 0]} rotation={[deg(knee), 0, 0]}>
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
  const headR = 0.15
  const chestR = 0.2
  const chestLen = 0.28
  const pelvisR = 0.12
  const scale = (height || H) / H
  return (
    <group scale={scale}>
      {/* 躯干与头 */}
      <Cap position={[0, 1.22, 0]} radius={chestR} length={chestLen} color={color} name="humanoid-chest" />
      <Ball position={[0, 0.9, 0]} radius={pelvisR} color={color} name="humanoid-pelvis" />
      <mesh position={[0, 1.43, 0]}>
        <cylinderGeometry args={[headR * 0.45, headR * 0.55, 0.07, 12]} />
        <LimbMaterial color={color} />
      </mesh>
      <Head color={color} position={[0, 1.56, 0]} rotation={[0, 0, 0]} headR={headR} />
      {/* 手臂 */}
      <Arm side={-1} shoulderRot={[deg(poseDef.leftShoulder?.[0]), deg(poseDef.leftShoulder?.[1]), deg(poseDef.leftShoulder?.[2])]} elbow={poseDef.leftElbow ?? 0} color={color} />
      <Arm side={1} shoulderRot={[deg(poseDef.rightShoulder?.[0]), deg(poseDef.rightShoulder?.[1]), deg(poseDef.rightShoulder?.[2])]} elbow={poseDef.rightElbow ?? 0} color={color} />
      {/* 腿 */}
      <Leg side={-1} hipRot={[deg(poseDef.leftHip?.[0]), deg(poseDef.leftHip?.[1]), deg(poseDef.leftHip?.[2])]} knee={poseDef.leftKnee ?? 0} color={color} />
      <Leg side={1} hipRot={[deg(poseDef.rightHip?.[0]), deg(poseDef.rightHip?.[1]), deg(poseDef.rightHip?.[2])]} knee={poseDef.rightKnee ?? 0} color={color} />
    </group>
  )
}
