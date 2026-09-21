import { useCallback, useMemo, useRef, useState } from 'react'
import { Alert, Button, Empty, Input, Space, Spin, Tooltip, Typography } from 'antd'
import { CloseOutlined, SendOutlined } from '@ant-design/icons'

import { agentChat } from '../../api/agent'
import { previewPrevisOperations } from '../../api'
import {
  ASSISTANT_PROFILE_ID,
  appendAssistantMessage,
  buildAssistantContext,
  makeAssistantMessage,
  type AssistantContext,
  type AssistantMessage,
} from './assistantSession'
import type { PrevisCamera, PrevisNode } from './types'

const { Text, Paragraph } = Typography

/**
 * 预演台里的助手对话栏。
 *
 * 三条刻意的取舍：
 *
 * 1. **真的发出去**：走既有的 `agentChat`（`POST /agent/chat`），`profile_id` 指定只做预演的助手，
 *    `context` 带上当前场景——不自造第二套对话通道，也不做一个"点了没反应"的框。
 * 2. **助手改不了场景**：它的角色里**没有写工具**（见 `profile.py` 的 `previs-assistant`），
 *    所以这里不存在"它自己把场景改了"的可能；要落库得由你在界面上确认（走既有应用链路）。
 * 3. **取不到回复就如实说**：响应形状对不上时给出可读提示，而不是显示一句假的"已收到"。
 */
/**
 * 从助手的回复里取出它给的操作方案。
 *
 * 约定：助手要把方案放在 ```json 代码块里，形如 `{"operations": [{...}]}`。
 * 取不到就返回 null——**回复里没有方案是正常的**（用户可能在问"这个机位多少毫米"），
 * 不该因此报错或假装有个空方案。
 */
function extractOperations(reply: string): unknown[] | null {
  const fenced = reply.match(/```(?:json)?\s*([\s\S]*?)```/i)
  const candidates = [fenced?.[1], reply]
  for (const candidate of candidates) {
    if (!candidate) continue
    const start = candidate.indexOf('{')
    const end = candidate.lastIndexOf('}')
    if (start < 0 || end <= start) continue
    try {
      const parsed = JSON.parse(candidate.slice(start, end + 1))
      if (Array.isArray(parsed?.operations)) return parsed.operations
    } catch {
      // 不是合法 JSON 就试下一个候选：模型输出里夹着解释文字是常态
    }
  }
  return null
}

/**
 * 修复动作标识里模型最常见的一类拼造：**把前缀叠了一遍**（`motion:motionwave` → `motion:wave`）。
 *
 * 只做确定性清理（去空白、补/去 `motion:` 前缀、去掉叠写的前缀）并在**库里有完全同名条目**时才替换；
 * 修不出来就原样保留——交给校验去拒，并附上可用清单，绝不模糊猜测（"sit" ⊂ "sit-down" 这类
 * 包含关系匹配会修出错误的动作）。
 */
export function repairMotionSlug(value: unknown, slugs: string[]): string | null {
  if (typeof value !== 'string') return null
  const raw = value.trim()
  if (!raw) return null
  const withPrefix = raw.startsWith('motion:') ? raw : `motion:${raw}`
  if (slugs.includes(withPrefix)) return withPrefix
  const stripped = `motion:${withPrefix.slice('motion:'.length).replace(/^motion/, '')}`
  if (stripped !== withPrefix && slugs.includes(stripped)) return stripped
  return null
}

export function PrevisAssistantPanel({
  scene,
  nodes,
  cameras,
  durationFrames,
  fps,
  activeCameraId,
  selectedNode,
  motionSlugs = [],
  onClose,
  /** 把"通过校验的方案"交给工作区渲染成幽灵预览（只读预览，落库仍要用户确认）。 */
  onPropose,
}: {
  scene: { id: string; revision: number }
  nodes: PrevisNode[]
  cameras: PrevisCamera[]
  durationFrames: number
  fps: number
  activeCameraId: string
  selectedNode?: PrevisNode | null
  /** 库里的动作标识（原样可用）。**必须写进消息正文**：实测模型会编造 `motion:motionwave`
   * 这类不存在的标识（正确的是 `motion:wave`），只靠系统提示里"不要编造"拦不住。 */
  motionSlugs?: string[]
  onClose: () => void
  onPropose?: (proposal: Record<string, any>) => void
}) {
  /**
   * 上下文**在面板里算**，而不是由父组件算好传进来。
   *
   * 这不是风格问题：父组件里那些变量（`durationFrames` / `fps` / `selectedNode`…）的声明位置
   * 分散且靠后，在它们之前写 memo 会直接踩到"先用后声明"（实测连踩两次）。子组件渲染时
   * 它们都已就绪，所以把上下文的构造留在子组件里。
   */
  const context = useMemo<AssistantContext>(
    () =>
      buildAssistantContext({
        scene: { ...scene, durationFrames, fps },
        nodes,
        cameras,
        activeCameraId,
        selectedNode: selectedNode ?? null,
      }),
    [activeCameraId, cameras, durationFrames, fps, nodes, scene, selectedNode],
  )
  const [messages, setMessages] = useState<AssistantMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const sequence = useRef(0)
  const nextId = () => `m${Date.now()}-${(sequence.current += 1)}`

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    setError('')
    setMessages(prev =>
      appendAssistantMessage(prev, makeAssistantMessage('user', text, { id: nextId(), at: Date.now() })),
    )
    setSending(true)
    try {
      // **场景事实必须写进消息正文**，而不是只塞进 `context` 字段：实测后端不会把 `context`
      // 呈现给模型，助手于是说「当前会话没有可用的画面场景」、反过来向用户要场景 ID（实测截图）。
      // 写进正文是唯一保证它读到的路径；`context` 仍然带上，供后端记录与排查。
      // 输出要求里约定了 json 代码块格式——外层界面靠它把方案变成半透明预览。
      const outgoing = [
        `【当前场景】id=${context.scene_id}（版本 ${context.scene_revision}；时长 ${context.duration_frames} 帧 @${context.fps}fps；活动机位「${context.active_camera_name}」）`,
        `【锁定不可改】节点：${context.locked_nodes.map(item => `${item.name}(${item.id})`).join('、') || '无'}；机位：${context.locked_cameras.map(item => item.name).join('、') || '无'}`,
        context.selected_node
          ? `【用户当前选中】${context.selected_node.name}（id=${context.selected_node.id}）`
          : '',
        // 动作标识**原样列出**：实测模型会编造 `motion:motionwave`（正确是 `motion:wave`），
        // 与其指望它先查清单再用对，不如把合法值直接摆在消息里——它照抄就行。
        motionSlugs.length
          ? `【可用动作（assign_motion 的 motion 值必须是下面这些，原样使用，不要改动或拼造）】${motionSlugs.join('、')}`
          : '',
        // 什么时候用动作、什么时候用姿势：**库里没有的动作就别硬凑标识**（打斗、拥抱、拔刀…）。
        // 预演台要的是"站位 / 朝向 / 景别 / 机位"可读，不是接触级的动作细节；
        // 说清"这一版只能表达到哪一步"比编一个不存在的动作强。
        '【姿势 vs 动作】库里有现成动作用 assign_motion（照抄上面的清单）；库里没有的动作（打斗、拥抱、拔刀等）不要编造动作标识，改用 pose 静态姿势 + 站位/朝向/间距表达，并明确说明这一版只能表达到哪一步（例如"只能到对峙，看不出打中"）。',
        '【输出要求】若你给出改场景的方案，请把操作数组放进 ```json 代码块（形如 {"operations":[...]}），界面会拿它去校验并渲染半透明预览；没有方案时正常回答即可。',
        `【用户】${text}`,
      ]
        .filter(Boolean)
        .join('\n')
      const response: any = await agentChat({
        message: outgoing,
        profile_id: ASSISTANT_PROFILE_ID,
        context: context as unknown as Record<string, any>,
      })
      const data = response?.data ?? response
      // 回复字段按优先级取多种可能：响应形状以服务端为准，这里做兜底而不是假设一种
      const reply =
        typeof data?.reply === 'string'
          ? data.reply
          : typeof data?.message === 'string'
            ? data.message
            : typeof data?.content === 'string'
              ? data.content
              : typeof data?.text === 'string'
                ? data.text
                : ''
      setMessages(prev =>
        appendAssistantMessage(
          prev,
          makeAssistantMessage('assistant', reply || '（助手这次没有给出文字回复）', {
            id: nextId(),
            at: Date.now(),
          }),
        ),
      )
      if (!reply) setError('助手返回里没有拿到文字回复（可能需要先配置模型或查看任务日志）')

      // 回复里带了方案就把它变成**幽灵预览**：先走后端校验（只读），通过了才交给工作区渲染。
      // 校验不通过**不渲染预览**——否则用户会以为"看到的就是能落库的"，而实际会被拒。
      let operations = reply ? extractOperations(reply) : null
      if (operations && motionSlugs.length) {
        // 校验前的确定性修复：叠写的前缀（motion:motionwave）直接修好并提示，
        // 免得"明明能自动修对的小错"也要用户重发一轮
        operations = operations.map((op: any) => {
          if (op?.type !== 'assign_motion') return op
          const fixed = repairMotionSlug(op?.payload?.motion, motionSlugs)
          if (!fixed || fixed === op.payload.motion) return op
          return { ...op, payload: { ...op.payload, motion: fixed } }
        })
      }
      if (operations && onPropose) {
        try {
          const preview: any = await previewPrevisOperations(scene.id, {
            operations,
            expectedRevision: context.scene_revision,
          })
          const data = preview?.data ?? {}
          if (data?.valid) {
            onPropose(data)
          } else {
            const reasons = (data?.rejected ?? []).map((item: any) => item?.reason).filter(Boolean)
            const motionMiss = reasons.some((reason: string) => reason.includes('动作'))
            setError(
              `方案有 ${(data?.rejected ?? []).length} 条没通过校验，已不渲染预览：${reasons[0] || '未知原因'}` +
                (motionMiss ? `（可用动作只有：${motionSlugs.join('、')}）` : ''),
            )
          }
        } catch (exc: any) {
          setError(exc?.message || '校验助手方案失败')
        }
      }
    } catch (exc: any) {
      setError(exc?.message || '发送失败')
    } finally {
      setSending(false)
    }
  }, [context, input, sending])

  return (
    <div
      style={{
        width: 340,
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        borderLeft: '1px solid var(--border)',
        background: 'var(--bgContainer)',
      }}
    >
      <div
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '8px 10px', borderBottom: '1px solid var(--border)',
        }}
      >
        <Text strong style={{ fontSize: 13 }}>预演助手</Text>
        <Space size={4}>
          <Text type="secondary" style={{ fontSize: 11 }}>
            第 {context.scene_revision} 版 · {context.active_camera_name}
          </Text>
          <Tooltip title="收起">
            <Button size="small" type="text" icon={<CloseOutlined />} onClick={onClose} />
          </Tooltip>
        </Space>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: 10 }}>
        {messages.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <Text type="secondary" style={{ fontSize: 12 }}>
                描述你要改什么，例如「把桌子挪到人物右侧、机位推近一点」。
                <br />
                **它只提方案，落库要你确认。**
              </Text>
            }
          />
        ) : (
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            {messages.map(item => (
              <div
                key={item.id}
                style={{
                  alignSelf: item.role === 'user' ? 'flex-end' : 'flex-start',
                  maxWidth: '92%',
                  padding: '6px 10px',
                  borderRadius: 8,
                  background: item.role === 'user' ? 'var(--bgLayout)' : 'rgba(34,211,238,.1)',
                }}
              >
                <Paragraph style={{ margin: 0, fontSize: 12, whiteSpace: 'pre-wrap' }}>{item.text}</Paragraph>
              </div>
            ))}
            {sending && (
              <div style={{ padding: '6px 10px' }}>
                <Space size={6}>
                  <Spin size="small" />
                  <Text type="secondary" style={{ fontSize: 11 }}>助手在想…</Text>
                </Space>
              </div>
            )}
          </Space>
        )}
      </div>

      {error && (
        <div style={{ padding: '0 10px 8px' }}>
          <Alert type="warning" showIcon message={<Text style={{ fontSize: 12 }}>{error}</Text>} />
        </div>
      )}

      <div style={{ padding: 10, borderTop: '1px solid var(--border)' }}>
        <Space.Compact style={{ width: '100%' }}>
          <Input.TextArea
            autoSize={{ minRows: 2, maxRows: 4 }}
            value={input}
            onChange={event => setInput(event.target.value)}
            onPressEnter={event => {
              // Shift+Enter 换行；单独回车发送（聊天框的通行习惯）
              if (!event.shiftKey) {
                event.preventDefault()
                void send()
              }
            }}
            placeholder="说一句，例如：把这个人移到画面左侧"
          />
          <Button type="primary" icon={<SendOutlined />} loading={sending} onClick={() => void send()}>
            发送
          </Button>
        </Space.Compact>
      </div>
    </div>
  )
}
