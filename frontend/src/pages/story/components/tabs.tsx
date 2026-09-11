/**
 * 创作项目工作台：components/tabs.tsx。
 *
 * 从 story/index.tsx 拆出（拆分计划 creative-project-ui-redesign #9），
 * 仅做物理搬迁，内容与原文件逐字一致。
 */
import { LogTextBlock } from './common'
import { panelStyle } from '../styles'
import { ProjectAssetLink, ProjectContent, ProjectGenerationLog } from '../types'
import { stageLabels } from '../utils'
import { ReloadOutlined } from '@ant-design/icons'
import { Button, Empty, Input, Select, Space, Table, Tag, Typography } from 'antd'
import { useState } from 'react'

const { Text, Title, Paragraph } = Typography
const { TextArea } = Input

export function LogsTab({
  logs,
  onRefresh,
}: {
  logs: ProjectGenerationLog[]
  onRefresh: () => void
}) {
  const columns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 190,
      render: (value: string) => <Text type="secondary">{value ? new Date(value).toLocaleString() : '-'}</Text>,
    },
    {
      title: '阶段',
      dataIndex: 'stage',
      width: 120,
      render: (value: string) => <Tag>{stageLabels[value] || value}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 130,
      render: (value: string) => (
        <Tag color={value === 'success' ? 'green' : value === 'success_repaired' ? 'blue' : 'red'}>
          {value}
        </Tag>
      ),
    },
    {
      title: '模型',
      key: 'model',
      render: (_: unknown, record: ProjectGenerationLog) => (
        <Space direction="vertical" size={0}>
          <Text>{record.provider || '-'}</Text>
          <Text type="secondary">{record.model || '-'}</Text>
        </Space>
      ),
    },
    {
      title: '模板',
      key: 'template',
      render: (_: unknown, record: ProjectGenerationLog) => (
        record.prompt_template ? (
          <Space direction="vertical" size={0}>
            <Text>{record.prompt_template.name || record.prompt_template.platform || '-'}</Text>
            <Text type="secondary">{record.prompt_template.template_stage || record.stage}</Text>
          </Space>
        ) : (
          <Text type="secondary">内置默认</Text>
        )
      ),
    },
    {
      title: '错误',
      dataIndex: 'validation_error',
      ellipsis: true,
      render: (value: string) => value ? <Text type="danger">{value}</Text> : <Text type="secondary">-</Text>,
    },
  ]

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space style={{ justifyContent: 'space-between', width: '100%' }}>
        <Text type="secondary">记录当前项目的 AI 生成请求、响应、模板、模型和校验错误。</Text>
        <Button icon={<ReloadOutlined />} onClick={onRefresh}>
          刷新日志
        </Button>
      </Space>
      {logs.length ? (
        <Table
          size="small"
          rowKey="id"
          columns={columns}
          dataSource={logs}
          pagination={{ pageSize: 10 }}
          expandable={{
            expandedRowRender: (record: ProjectGenerationLog) => (
              <Space direction="vertical" size={12} style={{ width: '100%', minHeight: 0, overflowY: 'auto' }}>
                <LogTextBlock title="Prompt" value={record.prompt} rows={8} />
                <LogTextBlock title="请求 JSON" value={JSON.stringify(record.request || {}, null, 2)} rows={6} />
                <LogTextBlock title="原始响应" value={record.raw_response || ''} rows={8} />
                <LogTextBlock title="规范化 JSON" value={JSON.stringify(record.normalized || {}, null, 2)} rows={8} />
                {record.validation_error ? (
                  <LogTextBlock title="错误" value={record.validation_error} rows={3} />
                ) : null}
              </Space>
            ),
          }}
        />
      ) : (
        <Empty description="暂无生成日志" />
      )}
    </Space>
  )
}

export function JsonTab({
  outline,
  chapterPlan,
  contents,
  assets,
}: {
  outline: any
  chapterPlan: any
  contents: ProjectContent[]
  assets: ProjectAssetLink[]
}) {
  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Text strong>故事大纲 JSON</Text>
        <TextArea rows={10} value={JSON.stringify(outline || {}, null, 2)} readOnly style={{ marginTop: 8 }} />
      </div>
      <div>
        <Text strong>章节规划 JSON</Text>
        <TextArea rows={10} value={JSON.stringify(chapterPlan || {}, null, 2)} readOnly style={{ marginTop: 8 }} />
      </div>
      <div>
        <Text strong>阶段内容 JSON</Text>
        <TextArea rows={8} value={JSON.stringify(contents || [], null, 2)} readOnly style={{ marginTop: 8 }} />
      </div>
      <div>
        <Text strong>项目素材 JSON</Text>
        <TextArea rows={6} value={JSON.stringify(assets || [], null, 2)} readOnly style={{ marginTop: 8 }} />
      </div>
    </Space>
  )
}

export function AssetsTab({
  assets,
  unavailableAssetIds,
  loading,
  onLinkAsset,
}: {
  assets: ProjectAssetLink[]
  unavailableAssetIds: Record<string, true>
  loading: boolean
  onLinkAsset: (assetId: string, role: string) => void
}) {
  const [assetId, setAssetId] = useState('')
  const [role, setRole] = useState('reference')

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <div style={panelStyle}>
        <Space.Compact style={{ width: '100%' }}>
          <Input
            value={assetId}
            onChange={(event) => setAssetId(event.target.value)}
            placeholder="输入素材 asset_id，先手动关联；后续由生成流程自动回写"
          />
          <Select
            value={role}
            onChange={setRole}
            style={{ width: 140 }}
            options={[
              { label: '参考', value: 'reference' },
              { label: '角色', value: 'character' },
              { label: '背景', value: 'background' },
              { label: '画风', value: 'style' },
              { label: '世界观', value: 'world' },
              { label: '输出', value: 'output' },
              { label: '封面', value: 'cover' },
            ]}
          />
          <Button
            type="primary"
            loading={loading}
            onClick={() => {
              onLinkAsset(assetId, role)
              setAssetId('')
            }}
          >
            关联
          </Button>
        </Space.Compact>
      </div>

      {assets.length ? (
        <Table
          size="small"
          rowKey="id"
          pagination={false}
          dataSource={assets}
          columns={[
            {
              title: '素材 ID',
              dataIndex: 'asset_id',
              ellipsis: true,
              render: (assetId: string) => (
                <Space size={6}>
                  <Text code ellipsis style={{ maxWidth: 190 }}>{assetId}</Text>
                  {unavailableAssetIds[assetId] ? <Tag color="warning">素材库中已不可用</Tag> : null}
                </Space>
              ),
            },
            {
              title: '角色',
              dataIndex: 'role',
              width: 120,
              render: (value: string) => <Tag>{value}</Tag>,
            },
            {
              title: '关系',
              dataIndex: 'relation',
              width: 140,
              render: (value: string) => <Text type="secondary">{value}</Text>,
            },
            {
              title: '时间',
              dataIndex: 'created_at',
              width: 190,
              render: (value: string) => value || '-',
            },
          ]}
        />
      ) : (
        <Empty description="暂无项目素材关联" />
      )}
    </Space>
  )
}

