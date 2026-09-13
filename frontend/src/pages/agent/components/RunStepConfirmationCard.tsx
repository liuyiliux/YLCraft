import { Button, Popconfirm, Space, Tag, Tooltip, Typography } from 'antd'
import { ToolOutlined, WarningOutlined } from '@ant-design/icons'
import { useTheme } from '../../../constants/theme'
import type { AgentRunStep } from '../../../types/agent'

const { Text } = Typography

/** 单个入参值最多显示多少字符，超出折叠并由 Tooltip 给出全文 */
const ARG_VALUE_LIMIT = 160

const MONO = 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'

/**
 * 运行步骤的人工确认卡片。
 *
 * 单独抽成组件有两个原因：
 *
 * 1. 原先这段 JSX 内联在 `pages/agent/index.tsx`（4000+ 行）里、并被抄了多份，
 *    改一处确认交互就要动整个巨型组件，所以长期没人愿意改；
 * 2. **更实质的是**：原实现只显示工具名与摘要，**不显示入参**——等于让人确认一个
 *    写入/删除/消耗型操作，却看不到它到底要做什么。入参本来就在
 *    `step.input.arguments` 里（后端 `tool_call_to_dict` 写入），只是没有被渲染。
 *
 * 样式一律取自 `useTheme()` 的设计 token（`radiusMD` / `warning` / `bgPage` …），
 * 不再硬编码圆角与色值——项目早就有 token 体系，此前只是这个页面没用。
 */

interface RunStepConfirmationCardProps {
  step: AgentRunStep
  loading?: boolean
  onConfirm: (stepId: number) => void
  /** 拒绝：后端没有 step 级 reject 端点，实际语义是"取消整个运行" */
  onReject: () => void
}

/** 把入参值渲染成可读文本；对象/数组走 JSON，过长由调用方再截断 */
function formatArgValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

export function RunStepConfirmationCard({
  step,
  loading = false,
  onConfirm,
  onReject,
}: RunStepConfirmationCardProps) {
  const { theme: THEME } = useTheme()

  // 后端把完整的工具调用写在 input 里：{ id, name, arguments }
  const args = (step.input?.arguments ?? null) as Record<string, unknown> | null
  const argEntries = args && typeof args === 'object' ? Object.entries(args) : []

  return (
    <div
      style={{
        border: `1px solid ${THEME.warning}`,
        borderLeft: `4px solid ${THEME.warning}`,
        borderRadius: THEME.radiusMD,
        padding: '12px 14px',
        background: THEME.primaryAlpha(0.06),
      }}
    >
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        <Space wrap size={6}>
          <Tag color="warning" icon={<WarningOutlined />}>
            待确认
          </Tag>
          {step.tool_name && <Tag icon={<ToolOutlined />}>{step.tool_name}</Tag>}
          {step.summary && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              {step.summary}
            </Text>
          )}
        </Space>

        {/*
          入参明细：这是本组件存在的理由。
          确认写入/删除前必须能看清"要写什么、写到哪里"。
        */}
        {argEntries.length > 0 ? (
          <div
            style={{
              borderRadius: THEME.radiusSM,
              background: THEME.bgPage,
              border: `1px solid ${THEME.borderLight}`,
              padding: '8px 10px',
              maxHeight: 220,
              overflow: 'auto',
            }}
          >
            <Text type="secondary" style={{ fontSize: 11 }}>
              将执行的操作
            </Text>
            <div style={{ marginTop: 6, display: 'grid', gap: 4 }}>
              {argEntries.map(([key, value]) => {
                const text = formatArgValue(value)
                const long = text.length > ARG_VALUE_LIMIT
                const shown = long ? `${text.slice(0, ARG_VALUE_LIMIT)}…` : text
                return (
                  <div key={key} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                    <Text
                      style={{
                        fontSize: 12,
                        minWidth: 92,
                        flex: '0 0 auto',
                        color: THEME.textSecondary,
                        fontFamily: MONO,
                      }}
                    >
                      {key}
                    </Text>
                    <Tooltip
                      title={
                        long ? (
                          <pre style={{ margin: 0, maxHeight: 320, overflow: 'auto' }}>{text}</pre>
                        ) : (
                          ''
                        )
                      }
                    >
                      <Text
                        style={{
                          fontSize: 12,
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word',
                          fontFamily: MONO,
                        }}
                      >
                        {shown}
                      </Text>
                    </Tooltip>
                  </div>
                )
              })}
            </div>
          </div>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>
            该步骤未记录入参，确认前建议先在工具页试跑一次。
          </Text>
        )}

        <Space wrap size={8}>
          <Button type="primary" size="small" onClick={() => onConfirm(step.id)} loading={loading}>
            确认执行
          </Button>
          {/* 后端没有 step 级 reject 端点：拒绝 = 取消整个运行。
              后果必须由二次确认明确告知，不能让用户以为只是跳过这一步。 */}
          <Popconfirm
            title="拒绝这个工具调用？"
            description="后端暂不支持只跳过这一步，拒绝会取消当前整个运行。"
            okText="仍要拒绝并取消运行"
            cancelText="返回"
            okButtonProps={{ danger: true }}
            onConfirm={onReject}
          >
            <Button size="small" danger loading={loading}>
              拒绝
            </Button>
          </Popconfirm>
          <Text type="secondary" style={{ fontSize: 12 }}>
            仅写入、删除或消耗型工具需要确认
          </Text>
        </Space>
      </Space>
    </div>
  )
}

export default RunStepConfirmationCard
