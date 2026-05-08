/**
 * YLCraft — 素材资产库页面
 *
 * 支持：
 * - 多条件过滤（类型/平台/状态/标签）
 * - 搜索
 * - 网格展示 + 详情抽屉
 * - 标签管理
 * - 批量操作
 */

import { useTheme } from '../../constants/theme'

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card,
  Row,
  Col,
  Input,
  Select,
  Tag,
  Button,
  Space,
  Spin,
  message,
  Modal,
  Descriptions,
  Image,
  Pagination,
  Empty,
  Checkbox,
} from 'antd'
import {
  SearchOutlined,
  ReloadOutlined,
  DeleteOutlined,
  DownloadOutlined,
  TagOutlined,
  ThunderboltOutlined,
  VideoCameraOutlined,
  CheckOutlined,
  CloseOutlined,
} from '@ant-design/icons'
import { listAssets, deleteAsset, getTags, createTag } from '../../api'

const { Search } = Input

export default function AssetsPage() {
  const navigate = useNavigate()
  const { theme } = useTheme()
  const [assets, setAssets] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [filters, setFilters] = useState({
    asset_type: undefined as string | undefined,
    platform: undefined as string | undefined,
    status: undefined as string | undefined,
    search: '',
    tags: undefined as string | undefined,
  })
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [detailAsset, setDetailAsset] = useState<any>(null)
  const [tags, setTags] = useState<any[]>([])
  const [batchMode, setBatchMode] = useState(false)

  const loadAssets = async () => {
    setLoading(true)
    try {
      const res = await listAssets({
        ...filters,
        page,
        page_size: pageSize,
      })
      if (res.success) {
        setAssets(res.data)
        setTotal(res.total)
      }
    } catch (e: any) {
      message.error('加载资产失败: ' + e.message)
    } finally {
      setLoading(false)
    }
  }

  const loadTags = async () => {
    try {
      const res = await getTags()
      if (res.success) setTags(res.data)
    } catch {}
  }

  useEffect(() => {
    loadAssets()
  }, [page, filters])

  useEffect(() => {
    loadTags()
  }, [])

  const handleDelete = async (id: string, e?: React.MouseEvent) => {
    if (e) {
      e.stopPropagation()
    }
    Modal.confirm({
      title: '确认删除',
      content: '删除后可在回收站恢复',
      async onOk() {
        await deleteAsset(id)
        message.success('已删除')
        loadAssets()
      },
    })
  }

  const handleBatchDelete = async () => {
    if (selectedIds.length === 0) return
    Modal.confirm({
      title: '确认批量删除',
      content: `确定删除选中的 ${selectedIds.length} 个素材吗？`,
      async onOk() {
        for (const id of selectedIds) {
          await deleteAsset(id)
        }
        message.success(`已删除 ${selectedIds.length} 个素材`)
        setSelectedIds([])
        setBatchMode(false)
        loadAssets()
      },
    })
  }

  const toggleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedIds(assets.map(a => a.id))
    } else {
      setSelectedIds([])
    }
  }

  const toggleSelect = (id: string, checked: boolean) => {
    if (checked) {
      setSelectedIds([...selectedIds, id])
    } else {
      setSelectedIds(selectedIds.filter(i => i !== id))
    }
  }

  return (
    <div>
      {/* 过滤栏 */}
      <Card style={{ marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col flex="auto">
            <Space>
              <Search
                placeholder="搜索标题..."
                prefix={<SearchOutlined />}
                value={filters.search}
                onChange={e => setFilters(f => ({ ...f, search: e.target.value }))}
                onSearch={val => { setPage(1); setFilters(f => ({ ...f, search: val })) }}
                style={{ maxWidth: 300 }}
              />
              {batchMode && (
                <Space>
                  <Checkbox 
                    checked={selectedIds.length === assets.length && assets.length > 0}
                    indeterminate={selectedIds.length > 0 && selectedIds.length < assets.length}
                    onChange={(e) => toggleSelectAll(e.target.checked)}
                  >
                    全选 ({selectedIds.length}/{assets.length})
                  </Checkbox>
                  <Button 
                    danger 
                    icon={<DeleteOutlined />}
                    onClick={handleBatchDelete}
                    disabled={selectedIds.length === 0}
                  >
                    批量删除
                  </Button>
                  <Button 
                    icon={<CloseOutlined />}
                    onClick={() => {
                      setBatchMode(false)
                      setSelectedIds([])
                    }}
                  >
                    退出批量
                  </Button>
                </Space>
              )}
            </Space>
          </Col>
          <Col>
            <Space>
              <Select
                placeholder="类型"
                allowClear
                style={{ width: 120 }}
                value={filters.asset_type}
                onChange={v => { setPage(1); setFilters(f => ({ ...f, asset_type: v })) }}
                options={[
                  { label: '视频', value: 'video' },
                  { label: '图片', value: 'image' },
                  { label: '音频', value: 'audio' },
                ]}
              />
              <Select
                placeholder="平台"
                allowClear
                style={{ width: 120 }}
                value={filters.platform}
                onChange={v => { setPage(1); setFilters(f => ({ ...f, platform: v })) }}
                options={[
                  { label: '抖音', value: 'douyin' },
                  { label: '快手', value: 'kuaishou' },
                  { label: 'B站', value: 'bilibili' },
                ]}
              />
              <Select
                placeholder="状态"
                allowClear
                style={{ width: 120 }}
                value={filters.status}
                onChange={v => { setPage(1); setFilters(f => ({ ...f, status: v })) }}
                options={[
                  { label: '已解析', value: 'parsed' },
                  { label: '下载中', value: 'downloading' },
                  { label: '就绪', value: 'ready' },
                  { label: '错误', value: 'error' },
                ]}
              />
              <Button icon={<ReloadOutlined />} onClick={loadAssets}>
                刷新
              </Button>
              {!batchMode && (
                <Button 
                  icon={<CheckOutlined />}
                  onClick={() => setBatchMode(true)}
                >
                  批量管理
                </Button>
              )}
              <Button 
                type="primary" 
                icon={<ThunderboltOutlined />} 
                onClick={() => navigate('/image-gen')}
              >
                图像生成
              </Button>
              <Button 
                type="primary" 
                icon={<VideoCameraOutlined />} 
                onClick={() => navigate('/video-gen')}
              >
                视频生成
              </Button>
            </Space>
          </Col>
        </Row>
      </Card>

      {/* 资产网格 */}
      <Spin spinning={loading}>
        {assets.length === 0 ? (
          <Empty description="暂无素材资产" />
        ) : (
          <Row gutter={[16, 16]}>
            {assets.map(asset => (
              <Col xs={24} sm={12} md={8} lg={6} key={asset.id}>
                <Card
                  hoverable={!batchMode}
                  style={{
                    border: selectedIds.includes(asset.id) ? '2px solid #1890ff' : undefined
                  }}
                  cover={
                    batchMode ? (
                      <div style={{ position: 'relative', height: 160 }}>
                        {asset.thumbnail_path ? (
                          <Image
                            src={asset.thumbnail_path}
                            height={160}
                            style={{ objectFit: 'cover' }}
                            preview={false}
                          />
                        ) : (
                          <div style={{ height: 160, background: theme.bgElevated, display: 'flex', alignItems: 'center', justifyContent: 'center', color: theme.textSecondary }}>
                            {asset.asset_type === 'video' ? '🎬' : asset.asset_type === 'image' ? '🖼️' : '📄'}
                          </div>
                        )}
                        <div style={{ 
                          position: 'absolute', 
                          top: 8, 
                          left: 8, 
                          background: 'rgba(255,255,255,0.9)',
                          borderRadius: 4,
                          padding: 4
                        }}>
                          <Checkbox 
                            checked={selectedIds.includes(asset.id)}
                            onChange={(e) => toggleSelect(asset.id, e.target.checked)}
                          />
                        </div>
                      </div>
                    ) : (
                      asset.thumbnail_path ? (
                        <Image
                          src={asset.thumbnail_path}
                          height={160}
                          style={{ objectFit: 'cover' }}
                        />
                      ) : (
                        <div style={{ height: 160, background: theme.bgElevated, display: 'flex', alignItems: 'center', justifyContent: 'center', color: theme.textSecondary }}>
                          {asset.asset_type === 'video' ? '🎬' : asset.asset_type === 'image' ? '🖼️' : '📄'}
                        </div>
                      )
                    )
                  }
                  actions={!batchMode ? [
                    <DownloadOutlined key="download" />,
                    <TagOutlined key="tag" />,
                    <DeleteOutlined key="delete" onClick={(e) => handleDelete(asset.id, e)} />,
                  ] : []}
                  onClick={() => {
                    if (!batchMode) {
                      setDetailAsset(asset)
                    } else {
                      toggleSelect(asset.id, !selectedIds.includes(asset.id))
                    }
                  }}
                >
                  <Card.Meta
                    title={<span style={{ fontSize: 13 }}>{asset.title || '无标题'}</span>}
                    description={
                      <Space direction="vertical" size={2} style={{ width: '100%' }}>
                        <div style={{ fontSize: 12, color: theme.textSecondary }}>
                          {asset.platform} · {asset.author || '未知作者'}
                        </div>
                        <Tag color={asset.status === 'ready' ? 'green' : asset.status === 'error' ? 'red' : 'blue'}>
                          {asset.status}
                        </Tag>
                        {asset.tags?.length > 0 && (
                          <Space size={4} wrap>
                            {(asset.tags as string[]).slice(0, 3).map((t: string) => (
                              <Tag key={t} style={{ fontSize: 11 }}>{t}</Tag>
                            ))}
                          </Space>
                        )}
                      </Space>
                    }
                  />
                </Card>
              </Col>
            ))}
          </Row>
        )}
      </Spin>

      {/* 分页 */}
      {total > 0 && (
        <div style={{ marginTop: 24, textAlign: 'right' }}>
          <Pagination
            current={page}
            pageSize={pageSize}
            total={total}
            onChange={setPage}
            showSizeChanger={false}
          />
        </div>
      )}

      {/* 详情抽屉 */}
      {detailAsset && (
        <Modal
          open
          title={detailAsset.title || '资产详情'}
          onCancel={() => setDetailAsset(null)}
          footer={null}
          width={640}
        >
          <Descriptions column={2} size="small">
            <Descriptions.Item label="类型">{detailAsset.asset_type}</Descriptions.Item>
            <Descriptions.Item label="平台">{detailAsset.platform}</Descriptions.Item>
            <Descriptions.Item label="作者">{detailAsset.author}</Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag color={detailAsset.status === 'ready' ? 'green' : 'orange'}>{detailAsset.status}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="大小">{detailAsset.file_size ? `${(detailAsset.file_size / 1024 / 1024).toFixed(1)} MB` : '-'}</Descriptions.Item>
            <Descriptions.Item label="分辨率">{detailAsset.width && detailAsset.height ? `${detailAsset.width}x${detailAsset.height}` : '-'}</Descriptions.Item>
            <Descriptions.Item label="来源URL" span={2}>
              <a href={detailAsset.source_url} target="_blank" rel="noreferrer">{detailAsset.source_url}</a>
            </Descriptions.Item>
            <Descriptions.Item label="创建时间">{detailAsset.created_at}</Descriptions.Item>
            <Descriptions.Item label="下载时间">{detailAsset.downloaded_at || '-'}</Descriptions.Item>
          </Descriptions>
          {detailAsset.tags?.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <strong>标签：</strong>
              {(detailAsset.tags as string[]).map((t: string) => (
                <Tag key={t}>{t}</Tag>
              ))}
            </div>
          )}
        </Modal>
      )}
    </div>
  )
}
