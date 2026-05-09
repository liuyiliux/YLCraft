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
  Tooltip,
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
  const [deleteModal, setDeleteModal] = useState<{
    visible: boolean,
    isBatch: boolean,
    assets: any[]
  }>({ visible: false, isBatch: false, assets: [] })

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

  const handleDelete = async (asset: any, e?: React.MouseEvent) => {
    if (e) {
      e.stopPropagation()
    }
    setDeleteModal({
      visible: true,
      isBatch: false,
      assets: [asset]
    })
  }

  const handleBatchDelete = async () => {
    if (selectedIds.length === 0) return
    const assetsToDelete = assets.filter(a => selectedIds.includes(a.id))
    setDeleteModal({
      visible: true,
      isBatch: true,
      assets: assetsToDelete
    })
  }

  const confirmDelete = async (hard: boolean) => {
    const { assets: assetsToDelete, isBatch } = deleteModal
    try {
      for (const asset of assetsToDelete) {
        await deleteAsset(asset.id, hard)
      }
      message.success(hard 
        ? `已删除 ${assetsToDelete.length} 个素材和文件` 
        : `已删除 ${assetsToDelete.length} 个素材记录`
      )
    } catch (e) {
      message.error('删除失败')
    }
    setDeleteModal({ visible: false, isBatch: false, assets: [] })
    setSelectedIds([])
    setBatchMode(false)
    loadAssets()
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
                  { label: '全部', value: '' },
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
                  { label: '全部', value: undefined },
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
                  { label: '全部', value: '' },
                  { label: '已解析', value: 'parsed' },
                  { label: '下载中', value: 'downloading' },
                  { label: '就绪', value: 'ready' },
                  { label: '错误', value: 'error' },
                ]}
              />
              <Button 
                icon={<ReloadOutlined />} 
                onClick={() => {
                  setFilters({
                    asset_type: '',
                    platform: '',
                    status: '',
                    search: '',
                    tags: '',
                  })
                  setPage(1)
                }}
              >
                重置
              </Button>
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
                      <div style={{ position: 'relative', height: 200 }}>
                        {asset.thumbnail_url ? (
                          <Image
                            src={asset.thumbnail_url}
                            height={200}
                            style={{ objectFit: 'cover' }}
                            preview={false}
                          />
                        ) : (
                          <div style={{ height: 200, background: theme.bgElevated, display: 'flex', alignItems: 'center', justifyContent: 'center', color: theme.textSecondary }}>
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
                      asset.thumbnail_url ? (
                        <Image
                          src={asset.thumbnail_url}
                          height={200}
                          style={{ objectFit: 'cover' }}
                          preview={false}
                        />
                      ) : (
                        <div style={{ height: 200, background: theme.bgElevated, display: 'flex', alignItems: 'center', justifyContent: 'center', color: theme.textSecondary }}>
                          {asset.asset_type === 'video' ? '🎬' : asset.asset_type === 'image' ? '🖼️' : '📄'}
                        </div>
                      )
                    )
                  }
                  actions={!batchMode ? [
                    <Tooltip title="下载" key="download">
                      <DownloadOutlined style={{ color: theme.textSecondary }} onClick={(e) => {
                        e.stopPropagation()
                        // 下载文件
                        const link = document.createElement('a')
                        link.href = `/api/v1/assets/${asset.id}/download`
                        link.download = asset.title || 'asset'
                        link.click()
                      }} />
                    </Tooltip>,
                    <Tooltip title="详情" key="detail">
                      <SearchOutlined style={{ color: theme.textSecondary }} onClick={(e) => {
                        e.stopPropagation()
                        setDetailAsset(asset)
                      }} />
                    </Tooltip>,
                    <Tooltip title="删除" key="delete">
                      <DeleteOutlined style={{ color: theme.textSecondary }} onClick={(e) => handleDelete(asset, e)} />
                    </Tooltip>,
                  ] : []}
                  onClick={() => {
                    if (batchMode) {
                      toggleSelect(asset.id, !selectedIds.includes(asset.id))
                    } else {
                      setDetailAsset(asset)
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
                        {asset.tags?.length > 0 ? (
                          <Space size={4} wrap>
                            {(asset.tags as string[]).slice(0, 3).map((t: string) => (
                              <Tag key={t} style={{ fontSize: 11 }}>{t}</Tag>
                            ))}
                          </Space>
                        ) : (
                          <div style={{ height: 22 }} />
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
          title={<span style={{ color: theme.textPrimary }}>{detailAsset.title || '资产详情'}</span>}
          onCancel={() => setDetailAsset(null)}
          footer={null}
          width={640}
        >
          {/* 预览图 */}
          {detailAsset.thumbnail_url && (
            <div style={{ marginBottom: 16, textAlign: 'center' }}>
              <Image
                src={detailAsset.thumbnail_url}
                alt={detailAsset.title}
                style={{ maxHeight: 300, objectFit: 'contain' }}
              />
            </div>
          )}
          
          <Descriptions column={2} size="small" labelStyle={{ color: theme.textSecondary }} contentStyle={{ color: theme.textPrimary }}>
            <Descriptions.Item label="类型">{detailAsset.asset_type}</Descriptions.Item>
            <Descriptions.Item label="平台">{detailAsset.platform}</Descriptions.Item>
            <Descriptions.Item label="作者">{detailAsset.author}</Descriptions.Item>
            <Descriptions.Item label="状态">
              <Tag color={detailAsset.status === 'ready' ? 'green' : 'orange'}>{detailAsset.status}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="大小">{detailAsset.file_size ? `${(detailAsset.file_size / 1024 / 1024).toFixed(1)} MB` : '-'}</Descriptions.Item>
            <Descriptions.Item label="分辨率">{detailAsset.width && detailAsset.height ? `${detailAsset.width}x${detailAsset.height}` : '-'}</Descriptions.Item>
            <Descriptions.Item label="时长">{detailAsset.duration ? `${Math.floor(detailAsset.duration / 60)}:${String(Math.floor(detailAsset.duration % 60)).padStart(2, '0')}` : '-'}</Descriptions.Item>
            <Descriptions.Item label="来源URL" span={2}>
              <Tooltip title={detailAsset.source_url} placement="topLeft">
                <a href={detailAsset.source_url} target="_blank" rel="noreferrer" style={{
                  display: 'inline-block',
                  maxWidth: 400,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  verticalAlign: 'middle',
                }}>{detailAsset.source_url}</a>
              </Tooltip>
            </Descriptions.Item>
            <Descriptions.Item label="创建时间">{detailAsset.created_at}</Descriptions.Item>
            <Descriptions.Item label="下载时间">{detailAsset.downloaded_at || '-'}</Descriptions.Item>
          </Descriptions>

          {/* 生成参数（从 metadata 中展示） */}
          {detailAsset.metadata && Object.keys(detailAsset.metadata).length > 0 && (() => {
            const meta = detailAsset.metadata
            // 生成参数字段
            const genFields: { key: string; label: string; span?: number }[] = [
              { key: 'prompt', label: '提示词', span: 2 },
              { key: 'negative_prompt', label: '反向提示词', span: 2 },
              { key: 'model', label: '模型' },
              { key: 'provider', label: '提供商' },
              { key: 'seed', label: '种子' },
              { key: 'size', label: '尺寸' },
              { key: 'steps', label: '采样步数' },
              { key: 'cfg_scale', label: 'CFG Scale' },
              { key: 'sampler', label: '采样器' },
              { key: 'lora', label: 'LoRA' },
              { key: 'controlnet', label: 'ControlNet' },
              { key: 'resolution', label: '分辨率' },
              { key: 'aspect_ratio', label: '画幅比例' },
              { key: 'generate_audio', label: '生成音频' },
              { key: 'duration', label: '时长(秒)' },
              { key: 'quality', label: '下载清晰度' },
              { key: 'is_audio', label: '仅音频' },
              { key: 'page_url', label: '原始页面', span: 2 },
            ]
            const visibleFields = genFields.filter(f => meta[f.key] !== undefined && meta[f.key] !== '' && meta[f.key] !== null)
            if (visibleFields.length === 0) return null
            return (
              <div style={{ marginTop: 16 }}>
                <div style={{ marginBottom: 8, fontWeight: 600, color: theme.textPrimary }}>
                  生成参数
                </div>
                <Descriptions column={2} size="small" bordered labelStyle={{ color: theme.textSecondary, width: 100 }} contentStyle={{ color: theme.textPrimary }}>
                  {visibleFields.map(f => (
                    <Descriptions.Item key={f.key} label={f.label} span={f.span}>
                      {f.key === 'page_url' ? (
                        <Tooltip title={meta[f.key]}>
                          <a href={meta[f.key]} target="_blank" rel="noreferrer" style={{
                            display: 'inline-block', maxWidth: 380, overflow: 'hidden',
                            textOverflow: 'ellipsis', whiteSpace: 'nowrap', verticalAlign: 'middle',
                          }}>{meta[f.key]}</a>
                        </Tooltip>
                      ) : f.key === 'prompt' || f.key === 'negative_prompt' ? (
                        <Tooltip title={meta[f.key]}>
                          <span style={{
                            display: 'inline-block', maxWidth: 450, overflow: 'hidden',
                            textOverflow: 'ellipsis', whiteSpace: 'nowrap', verticalAlign: 'middle',
                          }}>{meta[f.key]}</span>
                        </Tooltip>
                      ) : typeof meta[f.key] === 'boolean' ? (
                        meta[f.key] ? '是' : '否'
                      ) : String(meta[f.key])}
                    </Descriptions.Item>
                  ))}
                </Descriptions>

                {/* 参考图/首帧图展示 */}
                {(meta.source_image || (meta.reference_images && meta.reference_images.length > 0) || meta.start_image) && (
                  <div style={{ marginTop: 12 }}>
                    <div style={{ marginBottom: 4, fontSize: 12, color: theme.textSecondary }}>参考图</div>
                    <Space wrap>
                      {meta.source_image && (
                        <Image
                          src={meta.source_image.startsWith('/') ? `/api/v1/assets/0/thumbnail?path=${encodeURIComponent(meta.source_image)}` : meta.source_image}
                          width={80}
                          height={80}
                          style={{ objectFit: 'cover', borderRadius: 4 }}
                          fallback="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iODAiIGhlaWdodD0iODAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjgwIiBoZWlnaHQ9IjgwIiBmaWxsPSIjMzMzIi8+PHRleHQgeD0iNDAiIHk9IjQ1IiBmb250LXNpemU9IjEyIiBmaWxsPSIjOTk5IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj7ml6DnvKnnlaXlm748L3RleHQ+PC9zdmc+"
                        />
                      )}
                      {meta.start_image && (
                        <Image
                          src={meta.start_image.startsWith('/') ? `/api/v1/assets/0/thumbnail?path=${encodeURIComponent(meta.start_image)}` : meta.start_image}
                          width={80}
                          height={80}
                          style={{ objectFit: 'cover', borderRadius: 4 }}
                          fallback="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iODAiIGhlaWdodD0iODAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjgwIiBoZWlnaHQ9IjgwIiBmaWxsPSIjMzMzIi8+PHRleHQgeD0iNDAiIHk9IjQ1IiBmb250LXNpemU9IjEyIiBmaWxsPSIjOTk5IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj7ml6DnvKnnlaXlm748L3RleHQ+PC9zdmc+"
                        />
                      )}
                      {meta.reference_images?.map((img: string, idx: number) => (
                        <Image
                          key={idx}
                          src={img.startsWith('/') ? `/api/v1/assets/0/thumbnail?path=${encodeURIComponent(img)}` : img}
                          width={80}
                          height={80}
                          style={{ objectFit: 'cover', borderRadius: 4 }}
                          fallback="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iODAiIGhlaWdodD0iODAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjgwIiBoZWlnaHQ9IjgwIiBmaWxsPSIjMzMzIi8+PHRleHQgeD0iNDAiIHk9IjQ1IiBmb250LXNpemU9IjEyIiBmaWxsPSIjOTk5IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIj7ml6DnvKnnlaXlm748L3RleHQ+PC9zdmc+"
                        />
                      ))}
                    </Space>
                  </div>
                )}
              </div>
            )
          })()}

          {detailAsset.tags?.length > 0 && (
            <div style={{ marginTop: 12, color: theme.textSecondary }}>
              <strong>标签：</strong>
              {(detailAsset.tags as string[]).map((t: string) => (
                <Tag key={t} style={{ color: theme.textPrimary }}>{t}</Tag>
              ))}
            </div>
          )}
        </Modal>
      )}

      {/* 删除确认弹窗 */}
      <Modal
        open={deleteModal.visible}
        title={deleteModal.isBatch ? '确认批量删除' : '确认删除'}
        onCancel={() => setDeleteModal({ visible: false, isBatch: false, assets: [] })}
        footer={[
          <Button key="cancel" onClick={() => setDeleteModal({ visible: false, isBatch: false, assets: [] })}>
            取消
          </Button>,
          <Button key="soft" onClick={() => confirmDelete(false)}>
            仅删除记录
          </Button>,
          <Button key="hard" type="primary" danger onClick={() => confirmDelete(true)}>
            同时删除文件
          </Button>,
        ]}
      >
        <div>
          <p>删除后不可恢复</p>
          {deleteModal.assets.some(a => a.file_path) && (
            <p>是否同时删除素材文件？</p>
          )}
          {deleteModal.isBatch && (
            <div style={{ marginTop: 12, padding: 12, background: theme.bgElevated, borderRadius: 4 }}>
              <p><strong>将要删除的素材：</strong></p>
              <ul style={{ marginTop: 8, marginLeft: 20 }}>
                {deleteModal.assets.map(a => (
                  <li key={a.id}>{a.title || '无标题'}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </Modal>
    </div>
  )
}
