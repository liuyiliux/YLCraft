import { Button, InputNumber, Slider, Space, Tooltip, Typography } from 'antd'
import { HUMAN_PROXY_HEIGHT, HUMAN_PROXY_LIMITS, type HumanProxyPose } from '../../components/three/humanProxy'

const { Text } = Typography

type TripleField = 'leftShoulder' | 'rightShoulder' | 'leftHip' | 'rightHip' | 'torso' | 'head'
type SingleField = 'leftElbow' | 'rightElbow' | 'leftKnee' | 'rightKnee' | 'bodyOffsetY'

interface Channel {
  label: string
  hint: string
  limit: readonly [number, number]
  /** 三轴字段取哪一轴（0=绕X、1=绕Y、2=绕Z）；单轴通道省略 */
  axis?: 0 | 1 | 2
  /** 数值单位，缺省为度 */
  unit?: 'm'
  step?: number
}

const SHOULDER_CHANNELS: Channel[] = [
  { label: '肩·前后', hint: '正值 = 手臂向后摆', limit: HUMAN_PROXY_LIMITS.shoulderPitch, axis: 0 },
  { label: '肩·内外旋', hint: '绕手臂自身的竖轴旋转', limit: HUMAN_PROXY_LIMITS.shoulderTwist, axis: 1 },
  { label: '肩·张开', hint: '正值 = 向体侧张开（90° 为水平）', limit: HUMAN_PROXY_LIMITS.shoulderSpread, axis: 2 },
]

const HIP_CHANNELS: Channel[] = [
  { label: '髋·前后', hint: '正值 = 大腿向后；负值 = 抬腿向前', limit: HUMAN_PROXY_LIMITS.hipPitch, axis: 0 },
  { label: '髋·内外旋', hint: '绕大腿自身轴旋转', limit: HUMAN_PROXY_LIMITS.hipTwist, axis: 1 },
  { label: '髋·张开', hint: '正值 = 向体侧张开', limit: HUMAN_PROXY_LIMITS.hipSpread, axis: 2 },
]

/**
 * 躯干与头颈。**正值含义与四肢相反**（这些部位朝上，见 `HumanProxyPose` 注释）：
 * 正 pitch 是"向前低"、正 yaw 是"转向画面右侧"、正 roll 是"向画面左侧倾"。
 * 提示里逐条写明，避免照搬四肢的经验——这正是这类语义最容易看错的地方。
 */
const BODY_CHANNELS: (Channel & { field: 'torso' | 'head' })[] = [
  { field: 'torso', label: '躯干·前后', hint: '正值 = 前倾（上身向镜头前方低下去）', limit: HUMAN_PROXY_LIMITS.torsoPitch, axis: 0 },
  { field: 'torso', label: '躯干·转身', hint: '正值 = 上身转向画面右侧', limit: HUMAN_PROXY_LIMITS.torsoYaw, axis: 1 },
  { field: 'torso', label: '躯干·侧倾', hint: '正值 = 上身向画面左侧倾', limit: HUMAN_PROXY_LIMITS.torsoRoll, axis: 2 },
  { field: 'head', label: '头·低头', hint: '正值 = 低头；负值 = 抬眼', limit: HUMAN_PROXY_LIMITS.headPitch, axis: 0 },
  { field: 'head', label: '头·转头', hint: '正值 = 转向画面右侧', limit: HUMAN_PROXY_LIMITS.headYaw, axis: 1 },
  { field: 'head', label: '头·侧头', hint: '正值 = 向画面左侧歪头', limit: HUMAN_PROXY_LIMITS.headRoll, axis: 2 },
]

/** 整体重心：**位移**而不是旋转，单位是米（1.7m 基准）。 */
const BODY_OFFSET_CHANNEL: Channel = {
  label: '重心升降',
  hint: '负值 = 整体下沉（蹲、坐）；只调它会让脚陷进地面，要和髋/膝一起调',
  limit: HUMAN_PROXY_LIMITS.bodyOffsetY,
  unit: 'm',
  step: 0.01,
}

function ChannelRow({
  channel,
  value,
  disabled,
  onChange,
}: {
  channel: Channel
  value: number
  disabled?: boolean
  onChange: (value: number) => void
}) {
  const isMeters = channel.unit === 'm'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <Tooltip title={channel.hint}>
        <Text style={{ fontSize: 11, width: 68, flexShrink: 0 }}>{channel.label}</Text>
      </Tooltip>
      <Slider
        style={{ flex: 1, margin: '2px 0' }}
        min={channel.limit[0]}
        max={channel.limit[1]}
        step={channel.step ?? 1}
        value={value}
        disabled={disabled}
        onChange={onChange}
      />
      <Text type="secondary" style={{ fontSize: 11, width: 44, textAlign: 'right', flexShrink: 0 }}>
        {isMeters ? `${value.toFixed(2)} m` : `${Math.round(value)}°`}
      </Text>
    </div>
  )
}

export interface HumanProxyJointPanelProps {
  /** 当前生效的完整姿势（已合并预设与自定义） */
  pose: HumanProxyPose
  /** 当前身高（米） */
  height: number
  /** 是否处于自定义状态（决定"重置为预设"是否可用） */
  custom: boolean
  disabled?: boolean
  onChange: (next: HumanProxyPose) => void
  onHeightChange: (height: number) => void
  onReset: () => void
}

/**
 * 人形微调面板：身高 + 逐关节姿势。
 *
 * 只改一个通道时，其余通道从**当前生效的完整姿势**出发整体写回——这样"从预设出发微调"
 * 的结果是确定的，也不会因为只写一个字段而把别的关节悄悄拉成 0。
 * 滑块范围来自 `HUMAN_PROXY_LIMITS`：肘只能向前屈、膝只能向后收，界面层先挡一道。
 */
export default function HumanProxyJointPanel({
  pose,
  height,
  custom,
  disabled,
  onChange,
  onHeightChange,
  onReset,
}: HumanProxyJointPanelProps) {
  // 三元组的下标就是轴序（0=前后、1=内外旋、2=张开），与关节语义函数一一对应
  const setTriple = (field: TripleField, axis: 0 | 1 | 2, value: number) => {
    const next = [...((pose[field] ?? [0, 0, 0]) as [number, number, number])] as [number, number, number]
    next[axis] = value
    onChange({ ...pose, [field]: next })
  }

  const setSingle = (field: SingleField, value: number) => onChange({ ...pose, [field]: value })

  return (
    <div style={{ width: 326 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <Text style={{ fontSize: 11, width: 62, flexShrink: 0 }}>身高</Text>
        <InputNumber
          size="small"
          min={HUMAN_PROXY_HEIGHT.min}
          max={HUMAN_PROXY_HEIGHT.max}
          step={0.05}
          value={height}
          disabled={disabled}
          onChange={value => onHeightChange(typeof value === 'number' ? value : HUMAN_PROXY_HEIGHT.default)}
          style={{ flex: 1 }}
          addonAfter="m"
        />
      </div>
      <Text type="secondary" style={{ fontSize: 11 }}>
        方向已按关节语义固定；肘只能向前屈、膝只能向后收。躯干与头颈的"正值"是前倾 / 转向画面右 / 向画面左倾。
      </Text>
      <div style={{ marginTop: 10 }}>
        <Text strong style={{ fontSize: 12 }}>躯干与头</Text>
        {BODY_CHANNELS.map(channel => (
          <ChannelRow
            key={`${channel.field}-${channel.axis}`}
            channel={channel}
            value={(pose[channel.field] ?? [0, 0, 0])[channel.axis as number] ?? 0}
            disabled={disabled}
            onChange={value => setTriple(channel.field, channel.axis as 0 | 1 | 2, value)}
          />
        ))}
        <ChannelRow
          channel={BODY_OFFSET_CHANNEL}
          value={pose.bodyOffsetY ?? 0}
          disabled={disabled}
          onChange={value => setSingle('bodyOffsetY', value)}
        />
      </div>
      {(
        [
          { side: 'left' as const, label: '画面左侧', shoulder: 'leftShoulder' as const, elbow: 'leftElbow' as const, hip: 'leftHip' as const, knee: 'leftKnee' as const },
          { side: 'right' as const, label: '画面右侧', shoulder: 'rightShoulder' as const, elbow: 'rightElbow' as const, hip: 'rightHip' as const, knee: 'rightKnee' as const },
        ]
      ).map(block => (
        <div key={block.side} style={{ marginTop: 10 }}>
          <Text strong style={{ fontSize: 12 }}>{block.label}</Text>
          {SHOULDER_CHANNELS.map(channel => (
            <ChannelRow
              key={`${block.side}-shoulder-${channel.axis}`}
              channel={channel}
              value={(pose[block.shoulder] ?? [0, 0, 0])[channel.axis as number] ?? 0}
              disabled={disabled}
              onChange={value => setTriple(block.shoulder, channel.axis as 0 | 1 | 2, value)}
            />
          ))}
          <ChannelRow
            channel={{ label: '肘·屈', hint: '负值 = 屈肘（手向前抬）；不允许反折', limit: HUMAN_PROXY_LIMITS.elbow }}
            value={pose[block.elbow] ?? 0}
            disabled={disabled}
            onChange={value => setSingle(block.elbow, value)}
          />
          {HIP_CHANNELS.map(channel => (
            <ChannelRow
              key={`${block.side}-hip-${channel.axis}`}
              channel={channel}
              value={(pose[block.hip] ?? [0, 0, 0])[channel.axis as number] ?? 0}
              disabled={disabled}
              onChange={value => setTriple(block.hip, channel.axis as 0 | 1 | 2, value)}
            />
          ))}
          <ChannelRow
            channel={{ label: '膝·屈', hint: '正值 = 屈膝（小腿向后收）；不允许反折', limit: HUMAN_PROXY_LIMITS.knee }}
            value={pose[block.knee] ?? 0}
            disabled={disabled}
            onChange={value => setSingle(block.knee, value)}
          />
        </div>
      ))}
      <Space style={{ marginTop: 10 }}>
        <Button size="small" onClick={onReset} disabled={disabled || !custom}>
          重置为预设
        </Button>
        <Text type="secondary" style={{ fontSize: 11 }}>
          {custom ? '当前：自定义' : '当前：跟随预设'}
        </Text>
      </Space>
    </div>
  )
}
