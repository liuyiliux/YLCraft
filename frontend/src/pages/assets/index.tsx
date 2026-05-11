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
  PlayCircleOutlined,
  PauseCircleOutlined,
} from '@ant-design/icons'
import { listAssets, deleteAsset, getTags, createTag, getAsset } from '../../api'

const { Search } = Input

// 状态中文映射（键为大写，与数据库一致）
const STATUS_LABELS: Record<string, string> = {
  PENDING: '等待中',
  PARSING: '解析中',
  PARSED: '已解析',
  DOWNLOADING: '下载中',
  DOWNLOADED: '已下载',
  PROCESSING: '处理中',
  READY: '完成',
  ERROR: '错误',
  FAILED: '失败',
}

export default function AssetsPage() {
  const navigate = useNavigate()
  const { theme } = useTheme()
  const [assets, setAssets] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [filters, setFilters] = useState({
    asset_type: '' as string,
    platform: '' as string,
    source_type: '' as string,
    status: '' as string,
    search: '',
    tags: '' as string,
  })
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [detailAsset, setDetailAsset] = useState<any>(null)
  const [tags, setTags] = useState<any[]>([])
  const [batchMode, setBatchMode] = useState(false)
  const [playingAssetId, setPlayingAssetId] = useState<string | null>(null)
  const [deleteModal, setDeleteModal] = useState<{
    visible: boolean,
    isBatch: boolean,
    assets: any[]
  }>({ visible: false, isBatch: false, assets: [] })

  // 判断素材是否来自AI生成（使用 source_type 字段）
  const isAIGenerated = (asset: any) => {
    return asset.source_type?.toLowerCase() === 'ai_generated'
  }

  // 来源类型中文标签
  const SOURCE_TYPE_LABELS: Record<string, string> = {
    'upload': '本地上传',
    'parse': '视频解析',
    'ai_generated': 'AI生成',
    'import': '导入',
    '': '未知',
  }

  // 跳转到对应生成页面（根据来源类型判断）
  const handleJumpToGenerator = async (asset: any, e?: React.MouseEvent) => {
    if (e) e.stopPropagation()
    const metadata = asset.metadata || {}
    const aiParams = metadata.ai_params || {}
    const assetType = asset.type?.toUpperCase()

    // 判断是否有参考图（图生图才有）- 使用新的布尔字段
    const hasReferenceImage = !!(metadata.has_reference_images || metadata.has_source_image || aiParams.reference_image)

    // AI生成的素材 -> 跳转对应AI生成页面
    if (isAIGenerated(asset)) {
      // 如果有参考图，需要先获取详情获取完整base64数据
      let fullMetadata = metadata
      if (hasReferenceImage && !metadata.reference_images?.length) {
        try {
          const res = await getAsset(asset.id)
          if (res.success) {
            fullMetadata = res.data.metadata || {}
          }
        } catch {}
      }

      if (assetType === 'VIDEO') {
        // AI生成的视频 -> 视频生成页面
        const params = new URLSearchParams()
        if (metadata.prompt) params.set('prompt', metadata.prompt)
        if (metadata.negative_prompt) params.set('negative_prompt', metadata.negative_prompt)
        if (metadata.model) params.set('model', metadata.model)
        if (aiParams.aspect_ratio) params.set('aspect_ratio', aiParams.aspect_ratio)
        if (aiParams.duration) params.set('duration', String(aiParams.duration))
        // 只有图生图模式才传参考图
        if (hasReferenceImage) {
          const refImage = fullMetadata.reference_images?.[0] || fullMetadata.source_image || aiParams.reference_image
          if (refImage) {
            const refUrl = refImage.startsWith('/') 
              ? `/api/v1/assets/0/thumbnail?path=${encodeURIComponent(refImage)}`
              : refImage.startsWith('data:') 
                ? refImage  // 保持base64原样
                : `/api/v1/assets/${asset.id}/thumbnail?original=true`
            params.set('reference_image', refUrl)
          }
        }
        navigate(`/video-gen?${params.toString()}`)
      } else if (assetType === 'IMAGE') {
        // AI生成的图片 -> 图片生成页面
        const params = new URLSearchParams()
        if (metadata.prompt) params.set('prompt', metadata.prompt)
        if (metadata.negative_prompt) params.set('negative_prompt', metadata.negative_prompt)
        if (metadata.model) params.set('model', metadata.model)
        if (metadata.size) params.set('size', metadata.size)
        // 只有图生图模式才传参考图
        if (hasReferenceImage) {
          const refImage = fullMetadata.reference_images?.[0] || fullMetadata.source_image || aiParams.reference_image
          if (refImage) {
            const refUrl = refImage.startsWith('/') 
              ? `/api/v1/assets/0/thumbnail?path=${encodeURIComponent(refImage)}`
              : refImage.startsWith('data:') 
                ? refImage  // 保持base64原样
                : `/api/v1/assets/${asset.id}/thumbnail?original=true`
            params.set('reference_image', refUrl)
          }
        }
        navigate(`/image-gen?${params.toString()}`)
      }
    } else {
      // 非AI生成（视频解析/导入等） -> 去水印下载
      const params = new URLSearchParams()
      if (asset.source_url) params.set('url', asset.source_url)
      navigate(`/download?${params.toString()}`)
    }
  }

  const loadAssets = async () => {
    setLoading(true)
    try {
      // 只传递有值的过滤条件
      const queryParams: Record<string, any> = {
        page,
        page_size: pageSize,
      }
      if (filters.asset_type) queryParams.asset_type = filters.asset_type
      if (filters.platform) queryParams.platform = filters.platform
      if (filters.source_type) queryParams.source_type = filters.source_type
      if (filters.status) queryParams.status = filters.status
      if (filters.search) queryParams.search = filters.search
      if (filters.tags) queryParams.tags = filters.tags
      
      const res = await listAssets(queryParams)
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

  // 查看详情（获取完整数据）
  const handleShowDetail = async (asset: any, e?: React.MouseEvent) => {
    if (e) e.stopPropagation()
    try {
      const res = await getAsset(asset.id)
      if (res.success) {
        setDetailAsset(res.data)
      }
    } catch (err) {
      message.error('获取详情失败')
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
                onChange={v => { setPage(1); setFilters(f => ({ ...f, asset_type: v || undefined })) }}
                options={[
                  { label: '全部', value: '' },
                  { label: '视频', value: 'VIDEO' },
                  { label: '图片', value: 'IMAGE' },
                  { label: '音频', value: 'AUDIO' },
                ]}
              />
              <Select
                placeholder="平台"
                allowClear
                style={{ width: 120 }}
                value={filters.platform}
                onChange={v => { setPage(1); setFilters(f => ({ ...f, platform: v || undefined })) }}
                options={[
                  { label: '全部', value: '' },
                  { label: '抖音', value: 'douyin' },
                  { label: '快手', value: 'kuaishou' },
                  { label: 'B站', value: 'bilibili' },
                ]}
              />
              <Select
                placeholder="来源"
                allowClear
                style={{ width: 120 }}
                value={filters.source_type}
                onChange={v => { setPage(1); setFilters(f => ({ ...f, source_type: v || undefined })) }}
                options={[
                  { label: '全部', value: '' },
                  { label: 'AI生成', value: 'ai_generated' },
                  { label: '视频解析', value: 'parse' },
                  { label: '本地上传', value: 'upload' },
                  { label: '导入', value: 'import' },
                ]}
              />
              <Select
                placeholder="状态"
                allowClear
                style={{ width: 120 }}
                value={filters.status}
                onChange={v => { setPage(1); setFilters(f => ({ ...f, status: v || undefined })) }}
                options={[
                  { label: '全部', value: '' },
                  ...Object.entries(STATUS_LABELS).map(([key, label]) => ({ 
                    label, 
                    value: key.toLowerCase() 
                  })),
                ]}
              />
              <Button 
                icon={<ReloadOutlined />} 
                onClick={() => {
                  setFilters({
                    asset_type: '',
                    platform: '',
                    source_type: '',
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
            {assets.map(asset => {
              const status = (asset.status || '').toUpperCase()
              const isReady = status === 'READY'
              const isVideo = (asset.type || '').toUpperCase() === 'VIDEO'
              const isPlaying = playingAssetId === asset.id

              return (
              <Col xs={24} sm={12} md={8} lg={6} key={asset.id}>
                <Card
                  hoverable={!batchMode}
                  style={{
                    border: selectedIds.includes(asset.id) ? '2px solid #1890ff' : undefined
                  }}
                  cover={
                    batchMode ? (
                      <div style={{ position: 'relative', height: 200, overflow: 'hidden' }}>
                        {asset.thumbnail_url ? (
                          <img
                            src={asset.thumbnail_url}
                            style={{ width: '100%', height: 200, objectFit: 'cover', display: 'block' }}
                            onError={(e) => { e.currentTarget.style.display = 'none' }}
                          />
                        ) : (
                          <div style={{ height: 200, background: theme.bgElevated, display: 'flex', alignItems: 'center', justifyContent: 'center', color: theme.textSecondary }}>
                            {isVideo ? '🎬' : (asset.type || '').toUpperCase() === 'IMAGE' ? '🖼️' : '📄'}
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
                    ) : isPlaying && isVideo && isReady ? (
                      <div style={{ height: 200, position: 'relative', background: '#000' }}>
                        <video
                          src={`/api/v1/assets/${asset.id}/download`}
                          controls
                          autoPlay
                          style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                          onEnded={() => setPlayingAssetId(null)}
                        />
                        <Button
                          type="text"
                          icon={<PauseCircleOutlined />}
                          onClick={(e) => { e.stopPropagation(); setPlayingAssetId(null) }}
                          style={{ position: 'absolute', top: 4, right: 4, color: '#fff' }}
                          size="small"
                        />
                      </div>
                    ) : (
                      <div style={{ position: 'relative', height: 200, overflow: 'hidden' }}>
                        {asset.thumbnail_url ? (
                          <img
                            src={asset.thumbnail_url}
                            style={{ width: '100%', height: 200, objectFit: 'cover', display: 'block' }}
                            onError={(e) => { e.currentTarget.style.display = 'none' }}
                          />
                        ) : (
                          <div style={{ height: 200, background: theme.bgElevated, display: 'flex', alignItems: 'center', justifyContent: 'center', color: theme.textSecondary }}>
                            {isVideo ? '🎬' : (asset.type || '').toUpperCase() === 'IMAGE' ? '🖼️' : '📄'}
                          </div>
                        )}
                        {/* 播放按钮 */}
                        {isVideo && isReady && (
                          <div
                            style={{
                              position: 'absolute',
                              top: 0, left: 0, right: 0, bottom: 0,
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              background: 'rgba(0,0,0,0.3)',
                              cursor: 'pointer',
                              zIndex: 10,
                            }}
                            onClick={(e) => { e.stopPropagation(); setPlayingAssetId(asset.id) }}
                          >
                            <PlayCircleOutlined style={{ fontSize: 48, color: '#fff' }} />
                          </div>
                        )}
                      </div>
                    )
                  }
                  actions={!batchMode ? [
                    isVideo && isReady && (
                      <Tooltip title={isPlaying ? "暂停" : "播放"} key="play">
                        {isPlaying ? (
                          <PauseCircleOutlined style={{ color: theme.textSecondary }} onClick={(e) => { e.stopPropagation(); setPlayingAssetId(null) }} />
                        ) : (
                          <PlayCircleOutlined style={{ color: theme.textSecondary }} onClick={(e) => { e.stopPropagation(); setPlayingAssetId(asset.id) }} />
                        )}
                      </Tooltip>
                    ),
                    <Tooltip title={isAIGenerated(asset) ? "再次生成" : "跳转解析"} key="jump">
                      <ThunderboltOutlined style={{ color: theme.textSecondary }} onClick={(e) => handleJumpToGenerator(asset, e)} />
                    </Tooltip>,
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
                      <SearchOutlined style={{ color: theme.textSecondary }} onClick={(e) => handleShowDetail(asset, e)} />
                    </Tooltip>,
                    <Tooltip title="删除" key="delete">
                      <DeleteOutlined style={{ color: theme.textSecondary }} onClick={(e) => handleDelete(asset, e)} />
                    </Tooltip>,
                  ].filter(Boolean) : []}
                  onClick={() => {
                    if (batchMode) {
                      toggleSelect(asset.id, !selectedIds.includes(asset.id))
                    } else if (!isPlaying) {
                      handleShowDetail(asset)
                    }
                  }}
                >
                  <Card.Meta
                    title={
                      <Tooltip title={asset.title || '无标题'} placement="topLeft">
                        <span style={{ fontSize: 13, display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {asset.title || '无标题'}
                        </span>
                      </Tooltip>
                    }
                    description={
                      <div style={{ height: 52, overflow: 'hidden' }}>
                        <div style={{ fontSize: 12, color: theme.textSecondary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {asset.platform} · {asset.author || '未知作者'}
                        </div>
                        <Tag color={status === 'READY' ? 'green' : status === 'ERROR' ? 'red' : 'blue'} style={{ marginTop: 2 }}>
                          {STATUS_LABELS[status] || asset.status}
                        </Tag>
                        {asset.tags?.length > 0 ? (
                          <Space size={4} wrap style={{ marginTop: 4 }}>
                            {(asset.tags as string[]).slice(0, 3).map((t: string) => (
                              <Tag key={t} style={{ fontSize: 11, marginRight: 0 }}>{t}</Tag>
                            ))}
                          </Space>
                        ) : null}
                      </div>
                    }
                  />
                </Card>
              </Col>
              )
            })}
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
      {detailAsset && (() => {
        const detailStatus = (detailAsset.status || '').toUpperCase()
        const detailType = (detailAsset.type || '').toUpperCase()
        const isDetailVideo = detailType === 'VIDEO' && detailStatus === 'READY'
        const meta = detailAsset.metadata || {}
        const aiParams = meta.ai_params || {}
        const isAIGen = isAIGenerated(detailAsset)
        const genFields: { key: string; label: string; span?: number; source?: 'direct' | 'ai_params' | 'meta' }[] = [
          { key: 'ai_prompt', label: '提示词', span: 2, source: 'direct' },
          { key: 'ai_negative_prompt', label: '反向提示词', span: 2, source: 'direct' },
          { key: 'ai_model', label: 'AI模型', source: 'direct' },
          { key: 'prompt', label: '提示词', span: 2, source: 'meta' },
          { key: 'negative_prompt', label: '反向提示词', span: 2, source: 'meta' },
          { key: 'model', label: '模型', source: 'meta' },
          { key: 'provider', label: '提供商', source: 'meta' },
          { key: 'seed', label: '种子', source: 'ai_params' },
          { key: 'size', label: '尺寸', source: 'ai_params' },
          { key: 'steps', label: '采样步数', source: 'ai_params' },
          { key: 'cfg_scale', label: 'CFG Scale', source: 'ai_params' },
          { key: 'sampler', label: '采样器', source: 'ai_params' },
          { key: 'lora', label: 'LoRA', source: 'ai_params' },
          { key: 'controlnet', label: 'ControlNet', source: 'ai_params' },
          { key: 'resolution', label: '分辨率', source: 'ai_params' },
          { key: 'aspect_ratio', label: '画幅比例', source: 'ai_params' },
          { key: 'generate_audio', label: '生成音频', source: 'meta' },
          { key: 'duration', label: '时长(秒)', source: 'ai_params' },
          { key: 'quality', label: '下载清晰度', source: 'meta' },
          { key: 'is_audio', label: '仅音频', source: 'meta' },
          { key: 'page_url', label: '原始页面', span: 2, source: 'meta' },
        ]
        const getValue = (field: typeof genFields[0]) => {
          if (field.source === 'direct') return detailAsset[field.key]
          if (field.source === 'ai_params') return aiParams[field.key]
          return meta[field.key]
        }
        const visibleFields = genFields.filter(f => {
          const value = getValue(f)
          return value !== undefined && value !== '' && value !== null
        })
        const hasMetadata = visibleFields.length > 0

        return (
          <Modal
            open
            title={<span style={{ color: theme.textPrimary }}>{detailAsset.title || '资产详情'}</span>}
            onCancel={() => setDetailAsset(null)}
            footer={null}
            width={640}
          >
            {/* 视频播放或图片预览 */}
            {isDetailVideo ? (
              <div style={{ marginBottom: 16, textAlign: 'center', background: '#000', borderRadius: 8, overflow: 'hidden' }}>
                <video
                  src={`/api/v1/assets/${detailAsset.id}/download`}
                  controls
                  style={{ width: '100%', maxHeight: 400, objectFit: 'contain' }}
                />
              </div>
            ) : detailAsset.thumbnail_url ? (
              <div style={{ marginBottom: 16, textAlign: 'center' }}>
                <Image
                  src={detailAsset.thumbnail_url}
                  alt={detailAsset.title}
                  style={{ maxHeight: 300, objectFit: 'contain' }}
                />
              </div>
            ) : null}

            {/* 操作按钮 */}
            <div style={{ marginBottom: 16 }}>
              {isDetailVideo && (
                <Button
                  type="primary"
                  icon={<DownloadOutlined />}
                  onClick={() => {
                    const link = document.createElement('a')
                    link.href = `/api/v1/assets/${detailAsset.id}/download`
                    link.download = detailAsset.title || 'video'
                    link.click()
                  }}
                  style={{ marginRight: 8 }}
                >
                  下载视频
                </Button>
              )}
              <Button
                icon={<ThunderboltOutlined />}
                onClick={() => handleJumpToGenerator(detailAsset)}
              >
                {isAIGenerated(detailAsset) ? '再次生成' : '跳转解析'}
              </Button>
            </div>

              <Descriptions column={2} size="small" labelStyle={{ color: theme.textSecondary }} contentStyle={{ color: theme.textPrimary }}>
              <Descriptions.Item label="类型">{detailAsset.type}</Descriptions.Item>
              <Descriptions.Item label="来源">
                <Tag color={isAIGenerated(detailAsset) ? 'purple' : 'blue'}>
                  {SOURCE_TYPE_LABELS[detailAsset.source_type] || detailAsset.source_type || '未知'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="平台">{detailAsset.platform || '-'}</Descriptions.Item>
              <Descriptions.Item label="作者">{detailAsset.author || '-'}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={detailStatus === 'READY' ? 'green' : 'orange'}>{STATUS_LABELS[detailStatus] || detailAsset.status}</Tag>
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

            {/* 生成参数 */}
            {hasMetadata && (
              <div style={{ marginTop: 16 }}>
                <div style={{ marginBottom: 8, fontWeight: 600, color: theme.textPrimary }}>
                  生成参数 {isAIGen && <Tag color="purple" style={{ marginLeft: 8 }}>AI生成</Tag>}
                </div>
                <Descriptions column={2} size="small" bordered labelStyle={{ color: theme.textSecondary, width: 100 }} contentStyle={{ color: theme.textPrimary }}>
                  {visibleFields.map(f => {
                    const value = getValue(f)
                    return (
                    <Descriptions.Item key={f.key} label={f.label} span={f.span}>
                      {f.key === 'page_url' ? (
                        <Tooltip title={value}>
                          <a href={value} target="_blank" rel="noreferrer" style={{
                            display: 'inline-block', maxWidth: 380, overflow: 'hidden',
                            textOverflow: 'ellipsis', whiteSpace: 'nowrap', verticalAlign: 'middle',
                          }}>{value}</a>
                        </Tooltip>
                      ) : f.key === 'ai_prompt' || f.key === 'ai_negative_prompt' || f.key === 'prompt' || f.key === 'negative_prompt' ? (
                        <Tooltip title={value}>
                          <span style={{
                            display: 'inline-block', maxWidth: 450, overflow: 'hidden',
                            textOverflow: 'ellipsis', whiteSpace: 'nowrap', verticalAlign: 'middle',
                          }}>{value}</span>
                        </Tooltip>
                      ) : typeof value === 'boolean' ? (
                        value ? '是' : '否'
                      ) : String(value)}
                    </Descriptions.Item>
                  )})}
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
            )}

            {detailAsset.tags?.length > 0 && (
              <div style={{ marginTop: 12, color: theme.textSecondary }}>
                <strong>标签：</strong>
                {(detailAsset.tags as string[]).map((t: string) => (
                  <Tag key={t} style={{ color: theme.textPrimary }}>{t}</Tag>
                ))}
              </div>
            )}
          </Modal>
        )
      })()}

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
