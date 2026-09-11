/**
 * 创作项目工作台：components/writer-room-parts.tsx。
 *
 * 从 story/index.tsx 拆出（拆分计划 creative-project-ui-redesign #9），
 * 仅做物理搬迁，内容与原文件逐字一致。
 */
import { writerRoomDiffColumnsStyle, writerRoomDiffListStyle, writerRoomDiffRowStyle, writerRoomDiffTextStyle, writerRoomIssueStyle, writerRoomLogBlockStyle, writerRoomQualityStyle, writerRoomTeamAvatarStyle, writerRoomTeamGridStyle, writerRoomTeamJoinStyle, writerRoomTeamRoleBodyStyle, writerRoomTeamRoleHeaderStyle, writerRoomTeamRoleStyle } from '../styles'
import { ProjectGenerationLog, WriterRoomQualitySummary } from '../types'
import { buildProseDiffRows, writerRoomStepLabelMap } from '../utils'
import { DownOutlined } from '@ant-design/icons'
import { Button, Empty, Modal, Space, Tag, Tooltip, Typography } from 'antd'
import { useMemo, useState } from 'react'

const { Text, Title, Paragraph } = Typography

export function ProseParagraphDiff({ approvedText, candidateText }: { approvedText: string; candidateText: string }) {
  const rows = useMemo(() => buildProseDiffRows(approvedText, candidateText), [approvedText, candidateText])
  if (!rows.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="候选与当前正文内容一致，没有段落差异" />
  }
  return (
    <div style={writerRoomDiffListStyle}>
      <Text type="secondary" style={{ fontSize: 12 }}>仅展示 {rows.length} 处变更；未变段落已折叠。此视图只用于审阅，不会改写正文。</Text>
      {rows.map((row, index) => (
        <div key={`${row.kind}-${index}`} style={writerRoomDiffRowStyle}>
          <Tag color={row.kind === 'added' ? 'green' : row.kind === 'removed' ? 'red' : 'gold'}>
            {row.kind === 'added' ? '新增' : row.kind === 'removed' ? '删除' : '改写'}
          </Tag>
          <div style={writerRoomDiffColumnsStyle}>
            <div style={{ ...writerRoomDiffTextStyle, background: row.approved ? 'rgba(207, 19, 34, 0.08)' : 'transparent' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>当前正文</Text>
              <Text style={{ display: 'block', marginTop: 4, whiteSpace: 'pre-wrap' }}>{row.approved || '—'}</Text>
            </div>
            <div style={{ ...writerRoomDiffTextStyle, background: row.candidate ? 'rgba(56, 158, 13, 0.08)' : 'transparent' }}>
              <Text type="secondary" style={{ fontSize: 12 }}>候选正文</Text>
              <Text style={{ display: 'block', marginTop: 4, whiteSpace: 'pre-wrap' }}>{row.candidate || '—'}</Text>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

export function WriterRoomQualitySummaryPanel({ summary }: { summary: WriterRoomQualitySummary }) {
  return (
    <div style={writerRoomQualityStyle}>
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Space wrap>
          <Tag color={summary.overallScore >= 80 ? 'green' : summary.overallScore >= 60 ? 'orange' : 'red'}>
            总分 {summary.overallScore || '-'}
          </Tag>
          <Tag color={summary.aiSmellScore >= 70 ? 'red' : summary.aiSmellScore >= 40 ? 'orange' : 'green'}>
            AI味 {summary.aiSmellScore || '-'}
          </Tag>
          {summary.tags.slice(0, 8).map((tag) => (
            <Tag key={tag}>{tag}</Tag>
          ))}
        </Space>
        {summary.checks.length ? (
          <Space direction="vertical" size={4} style={{ width: '100%' }}>
            <Text type="secondary">AI味检查</Text>
            {summary.checks.slice(0, 6).map((check, index) => (
              <Text key={`${check}-${index}`} style={{ fontSize: 12 }}>
                {index + 1}. {check}
              </Text>
            ))}
          </Space>
        ) : null}
      </Space>
    </div>
  )
}

export function CharacterRehearsalCard({
  character,
  performance,
  index,
}: {
  character: string
  performance: string
  index: number
}) {
  const [open, setOpen] = useState(index === 0)
  const initial = (character || '?').trim().charAt(0)
  return (
    <div style={writerRoomTeamRoleStyle}>
      <div
        style={writerRoomTeamRoleHeaderStyle}
        role="button"
        tabIndex={0}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            setOpen((value) => !value)
          }
        }}
        aria-expanded={open}
      >
        <span style={writerRoomTeamAvatarStyle}>{initial}</span>
        <span style={{ flex: 1, minWidth: 0 }}>
          <Text strong ellipsis={{ tooltip: character }} style={{ fontSize: 14, color: 'var(--textPrimary)' }}>
            {character || `角色 ${index + 1}`}
          </Text>
        </span>
        <Tag color="geekblue" style={{ fontSize: 11, marginInlineEnd: 0 }}>子智能体</Tag>
        <DownOutlined
          style={{
            fontSize: 12,
            color: 'var(--textSecondary)',
            transition: 'transform 0.2s ease',
            transform: open ? 'rotate(180deg)' : 'none',
          }}
        />
      </div>
      {open ? (
        <div style={writerRoomTeamRoleBodyStyle}>
          <Text style={{ display: 'block', whiteSpace: 'pre-wrap', lineHeight: 1.8, fontSize: 13, color: 'var(--textPrimary)' }}>
            {performance || '该角色本轮没有产出'}
          </Text>
        </div>
      ) : null}
    </div>
  )
}

export function TeamRehearsalPanel({
  performances,
  joined,
}: {
  performances: Array<{ character: string; performance: string; child_run_id?: string }>
  joined?: string
}) {
  const [showJoined, setShowJoined] = useState(true)
  if (!performances.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无角色演绎产出" />
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={writerRoomTeamGridStyle}>
        {performances.map((item, index) => (
          <CharacterRehearsalCard
            key={item.character || index}
            character={item.character}
            performance={item.performance}
            index={index}
          />
        ))}
      </div>
      {joined ? (
        <div style={writerRoomTeamJoinStyle}>
          <div
            style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}
            role="button"
            tabIndex={0}
            onClick={() => setShowJoined((value) => !value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                setShowJoined((value) => !value)
              }
            }}
          >
            <Text strong style={{ fontSize: 13 }}>编辑连接</Text>
            <Tag style={{ fontSize: 11 }}>汇合</Tag>
            <DownOutlined
              style={{
                fontSize: 11,
                color: 'var(--textSecondary)',
                transition: 'transform 0.2s ease',
                transform: showJoined ? 'rotate(180deg)' : 'none',
              }}
            />
          </div>
          {showJoined ? (
            <Paragraph style={{ margin: '8px 0 0', whiteSpace: 'pre-wrap', lineHeight: 1.7, fontSize: 13, color: 'var(--textPrimary)' }}>
              {joined}
            </Paragraph>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

export function WriterRoomLogSummary({ log }: { log: ProjectGenerationLog }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Space size={4} wrap>
        <Tag color={log.status === 'success' ? 'green' : log.status === 'success_repaired' ? 'blue' : 'red'}>
          {log.status}
        </Tag>
        <Tag>{log.provider || 'provider'}</Tag>
        <Tag>{log.model || 'model'}</Tag>
        {log.created_at ? <Tag>{log.created_at}</Tag> : null}
        {log.prompt_template ? (
          <Tooltip title={log.prompt_template.description || log.prompt_template.platform || ''}>
            <Tag color="purple">{log.prompt_template.name || writerRoomStepLabelMap[log.stage] || log.stage}</Tag>
          </Tooltip>
        ) : (
          <Tag>内置默认</Tag>
        )}
        <Button size="small" type="link" onClick={() => setOpen(true)}>
          查看请求
        </Button>
      </Space>
      <Modal
        title="写作室生成日志"
        open={open}
        onCancel={() => setOpen(false)}
        footer={null}
        width={920}
      >
        <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
          <Space wrap>
            <Tag>{writerRoomStepLabelMap[log.stage] || log.stage}</Tag>
            <Tag color={log.status === 'success' ? 'green' : 'red'}>{log.status}</Tag>
            <Tag>{log.provider || '-'}</Tag>
            <Tag>{log.model || '-'}</Tag>
          </Space>
          {log.validation_error ? (
            <div style={writerRoomIssueStyle}>
              <Text type="danger">{log.validation_error}</Text>
            </div>
          ) : null}
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <Text strong>Prompt</Text>
            <Paragraph style={writerRoomLogBlockStyle}>{log.prompt || '无'}</Paragraph>
          </Space>
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <Text strong>请求参数</Text>
            <Paragraph style={writerRoomLogBlockStyle}>{JSON.stringify(log.request || {}, null, 2)}</Paragraph>
          </Space>
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <Text strong>标准化结果</Text>
            <Paragraph style={writerRoomLogBlockStyle}>{JSON.stringify(log.normalized || {}, null, 2)}</Paragraph>
          </Space>
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <Text strong>原始返回</Text>
            <Paragraph style={writerRoomLogBlockStyle}>{log.raw_response || '无'}</Paragraph>
          </Space>
        </Space>
      </Modal>
    </>
  )
}

