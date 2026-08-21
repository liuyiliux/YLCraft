/**
 * AssetReferencePicker — 通用「从素材库选择图片」弹窗组件
 *
 * 复用于：图生图(参考图)、图生视频(首帧/参考图)。
 *
 * 行为：
 * - 列出素材库图片资产（默认 asset_type=image），按是否远程来源标注
 * - 所有资产点击后均可「后端转 base64」：仅传素材 ID，由后端读取本地副本转 base64
 *   提交给模型，前端不再 fetch 下载（素材入库时已下载过本地副本）
 * - 素材带远程 http(s) 来源 URL（如 AI 生成结果、小红书/其他渠道下载的图片）
 *   时额外提供「来源 URL 填入」，是否使用由用户自行判断
 *
 * 通过 onSelect 回调返回：{ url, isBase64, asset, assetId }
 *   url: base64 模式下为空串（由后端解析 assetId）；来源 URL 模式为 http(s) URL
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { Modal, Spin, Empty, message, Tag, Button, Tooltip } from 'antd'
import { DatabaseOutlined, CloudOutlined, CloudServerOutlined } from '@ant-design/icons'
import { listAssets } from '../../api'

export interface AssetReferencePayload {
  /** 填入的值：base64 模式下为空串（改由后端解析），来源 URL 模式为 http(s) URL */
  url: string
  isBase64: boolean
  asset: any
  /** 素材 ID：后端按需本地读文件转 base64，前端无需下载 */
  assetId?: string
}

interface AssetReferencePickerProps {
  open: boolean
  onClose: () => void
  onSelect: (payload: AssetReferencePayload) => void
  assetType?: string
  title?: string
  /** 当前供应商是否只支持公网 URL（如 Agnes 图生视频），选 base64 时提示走 COS 上传 */
  requiresPublicUrl?: boolean
}

const pickUrl = (asset: any): string =>
  asset?.file_url || asset?.thumbnail_url || asset?.cover_url || ''

/** 素材带远程 http(s) 来源 URL（AI 生成结果 / 小红书等渠道下载的图片）时可提供「来源 URL 填入」 */
const isRemoteSource = (asset: any): boolean =>
  Boolean(asset?.source_url && /^https?:\/\//.test(String(asset.source_url)))

export default function AssetReferencePicker({
  open,
  onClose,
  onSelect,
  assetType = 'image',
  title = '从素材库选择图片',
  requiresPublicUrl = false,
}: AssetReferencePickerProps) {
  const [assets, setAssets] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(true)
  const [pending, setPending] = useState<any | null>(null)
  const gridRef = useRef<HTMLDivElement>(null)

  const PAGE_SIZE = 24

  const loadAssets = async (nextPage = 1, isRefresh = false) => {
    if (nextPage === 1) setLoading(true)
    else setLoadingMore(true)
    try {
      const data: any = await listAssets({
        asset_type: assetType,
        status: 'READY',
        page: nextPage,
        page_size: PAGE_SIZE,
      })
      const items = data?.items || data?.data || data?.assets || []
      const total = data?.total || 0
      setAssets((prev) => (isRefresh ? items : [...prev, ...items]))
      setPage(nextPage)
      setHasMore((isRefresh ? items.length : assets.length + items.length) < total)
    } catch (error: any) {
      message.warning(error?.message || '加载素材库失败')
      if (nextPage === 1) setAssets([])
    } finally {
      setLoading(false)
      setLoadingMore(false)
    }
  }

  const handleScroll = () => {
    const el = gridRef.current
    if (!el || loading || loadingMore || !hasMore) return
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 100) {
      void loadAssets(page + 1)
    }
  }

  useEffect(() => {
    if (open) {
      setAssets([])
      setPage(1)
      setHasMore(true)
      void loadAssets(1, true)
    } else {
      setPending(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const remoteSource = useMemo(() => (pending ? isRemoteSource(pending) : false), [pending])

  const doUseBase64 = async () => {
    if (!pending) return
    // 方案：前端不下载图片，直接把素材 ID 交给后端，由后端本地读文件转 base64。
    // 素材入库时已下载过本地副本，无需浏览器再 fetch 一遍。
    onSelect({ url: '', isBase64: true, asset: pending, assetId: String(pending.id || '') })
    onClose()
  }

  const handleUseBase64 = () => {
    if (!pending) return
    // 后端统一处理：本地路径/base64 交给模型；若供应商要求公网 URL（如 Agnes），
    // 后端会自动上传 COS 生成公网链接后再提交，前端无需关心。
    doUseBase64()
  }

  const handleUseSourceUrl = () => {
    if (!pending) return
    const url = pending.source_url
    if (!url || !/^https?:\/\//.test(String(url))) {
      message.warning('该素材没有可用的公网来源 URL，请改用 base64 填入')
      return
    }
    onSelect({ url, isBase64: false, asset: pending })
    onClose()
  }

  return (
    <Modal
      title={
        <span>
          <DatabaseOutlined style={{ marginRight: 6 }} />
          {title}
        </span>
      }
      open={open}
      onCancel={onClose}
      footer={null}
      width={760}
    >
      {pending ? (
        <div style={{ padding: 12 }}>
          <div style={{ marginBottom: 12, color: '#cbd5e1' }}>
            已选择：{pending.title || pending.name || pending.id}
            {remoteSource ? (
              <Tag color="blue" style={{ marginLeft: 8 }} icon={<CloudOutlined />}>
                远程来源
              </Tag>
            ) : (
              <Tag style={{ marginLeft: 8 }} icon={<CloudServerOutlined />}>
                本地资产
              </Tag>
            )}
          </div>
          <div
            style={{
              height: 160,
              background: '#000 center/cover no-repeat',
              backgroundImage: `url(${pickUrl(pending)})`,
              borderRadius: 8,
              marginBottom: 12,
            }}
          />
          <div style={{ color: '#8b8ba8', fontSize: 12, marginBottom: 8 }}>
            以何种形式填入参考图？
          </div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <Tooltip title="把素材 ID 交给后端，由后端读取本地副本转为 base64 后提交给模型，前端无需再下载图片">
              <Button type="primary" onClick={handleUseBase64}>
                后端转 base64
              </Button>
            </Tooltip>
            {remoteSource && (
              <Tooltip title="直接使用素材的远程来源 URL（适合接收公网链接的供应商，如 Agnes）">
                <Button onClick={handleUseSourceUrl}>来源 URL 填入</Button>
              </Tooltip>
            )}
            <Button onClick={() => setPending(null)}>返回重选</Button>
          </div>
        </div>
      ) : (
        <Spin spinning={loading}>
          <div
            ref={gridRef}
            onScroll={handleScroll}
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
              gap: 12,
              maxHeight: 420,
              overflowY: 'auto',
            }}
          >
            {assets.map((asset) => {
              const url = pickUrl(asset)
              const remoteItem = isRemoteSource(asset)
              return (
                <div
                  key={asset.id}
                  onClick={() => setPending(asset)}
                  style={{
                    cursor: 'pointer',
                    border: '1px solid #333',
                    borderRadius: 8,
                    overflow: 'hidden',
                    background: '#1e1e2e',
                  }}
                >
                  <img
                    loading="lazy"
                    src={url}
                    alt={asset.title || asset.name || ''}
                    style={{
                      width: '100%',
                      height: 110,
                      objectFit: 'cover',
                      background: '#000',
                      display: 'block',
                    }}
                  />
                  <div
                    style={{
                      padding: '6px 8px',
                      fontSize: 12,
                      color: '#cbd5e1',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                    }}
                  >
                    <span>{asset.title || asset.name || '未命名素材'}</span>
                    {remoteItem ? (
                      <CloudOutlined style={{ color: '#60a5fa' }} />
                    ) : (
                      <CloudServerOutlined style={{ color: '#94a3b8' }} />
                    )}
                  </div>
                </div>
              )
            })}
          </div>
          {!loading && assets.length === 0 && <Empty description="素材库暂无图片资产" />}
          {loadingMore && (
            <div style={{ textAlign: 'center', padding: '12px 0', color: '#94a3b8' }}>
              加载更多…
            </div>
          )}
          {!hasMore && assets.length > 0 && (
            <div style={{ textAlign: 'center', padding: '12px 0', color: '#64748b', fontSize: 12 }}>
              已加载全部
            </div>
          )}
        </Spin>
      )}
    </Modal>
  )
}
