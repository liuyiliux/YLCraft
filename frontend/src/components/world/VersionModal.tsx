/**
 * 地图版本历史模态：revision 列表 + A/B 两版对比 + 回滚（append-only）。
 * 列表数据、对比结果、回滚动作均由父组件注入。
 */
import { Button, Modal, Popconfirm, Space, Table, Typography } from 'antd'
import type { WorldMapRevisionItem } from '../../api/novelSource'

const { Text } = Typography

interface Props {
  open: boolean
  onClose: () => void
  currentRevision?: number | null
  revisions: WorldMapRevisionItem[]
  loading: boolean
  compareA: number | null
  compareB: number | null
  onPickA: (revision: number) => void
  onPickB: (revision: number) => void
  onCompare: () => void
  comparing: boolean
  compareResult: string[]
  onRollback: (revision: number) => void
  rollingBack: number | null
}

export default function VersionModal({
  open,
  onClose,
  currentRevision,
  revisions,
  loading,
  compareA,
  compareB,
  onPickA,
  onPickB,
  onCompare,
  comparing,
  compareResult,
  onRollback,
  rollingBack,
}: Props) {
  return (
    <Modal
      title={`版本历史${currentRevision ? ` · 当前 v${currentRevision}` : ''}`}
      open={open}
      footer={null}
      width={780}
      onCancel={onClose}
    >
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Table
          size="small"
          rowKey="revision"
          loading={loading}
          dataSource={revisions}
          pagination={false}
          columns={[
            {
              title: '版本',
              dataIndex: 'revision',
              key: 'revision',
              width: 70,
              render: (value: number) => `v${value}`,
            },
            {
              title: '时间',
              dataIndex: 'created_at',
              key: 'created_at',
              width: 150,
              render: (value: string | null) => (value ? new Date(value).toLocaleString() : '—'),
            },
            {
              title: '操作者',
              dataIndex: 'operator',
              key: 'operator',
              width: 120,
              render: (value: string) => value || '—',
            },
            { title: '摘要', dataIndex: 'summary', key: 'summary' },
            {
              title: '对比',
              key: 'compare',
              width: 120,
              render: (_: unknown, row: WorldMapRevisionItem) => (
                <Space size={4}>
                  <Button
                    size="small"
                    type={compareA === row.revision ? 'primary' : 'default'}
                    onClick={() => onPickA(row.revision)}
                  >
                    A
                  </Button>
                  <Button
                    size="small"
                    type={compareB === row.revision ? 'primary' : 'default'}
                    onClick={() => onPickB(row.revision)}
                  >
                    B
                  </Button>
                </Space>
              ),
            },
            {
              title: '操作',
              key: 'act',
              width: 90,
              render: (_: unknown, row: WorldMapRevisionItem) => (
                <Popconfirm
                  title={`回滚到 v${row.revision}？（产生新版本，不改写历史）`}
                  okText="回滚"
                  cancelText="取消"
                  onConfirm={() => onRollback(row.revision)}
                >
                  <Button
                    size="small"
                    danger
                    loading={rollingBack === row.revision}
                    disabled={row.revision === currentRevision}
                  >
                    回滚
                  </Button>
                </Popconfirm>
              ),
            },
          ]}
        />
        <Space wrap>
          <Button
            size="small"
            disabled={compareA == null || compareB == null || compareA === compareB}
            loading={comparing}
            onClick={onCompare}
          >
            对比 A / B
          </Button>
          <Text type="secondary" style={{ fontSize: 12 }}>
            先点 A、B 选择两个版本再对比（无先后限制）；回滚会以历史快照产生新版本，历史链不被改写。
          </Text>
        </Space>
        {compareResult.length > 0 && (
          <div
            style={{
              background: '#f5f5f5',
              padding: 12,
              borderRadius: 6,
              fontSize: 12,
              whiteSpace: 'pre-wrap',
            }}
          >
            {compareResult.map((line, index) => (
              <div key={index}>{line}</div>
            ))}
          </div>
        )}
      </Space>
    </Modal>
  )
}
