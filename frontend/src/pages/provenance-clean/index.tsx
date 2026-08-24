/**
 * YLCraft — 元数据 / AI 标记清理（独立工具页）
 *
 * 从素材库选择资产 → 审计（EXIF/XMP/C2PA、隐形/双向控制符、容器元数据）
 * → 生成不覆盖原文件的清理副本（derived_from 血缘）。
 * 与图片编辑器「视觉水印」、平台采集「无水印下载」是不同能力。
 */
import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Card, Descriptions, Input, Select, Space, Spin, Typography, message } from 'antd'
import { ClearOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { cleanAssetProvenance, listAssets } from '../../api'

const { Title, Text } = Typography

export default function ProvenanceCleanPage() {
  const [assets, setAssets] = useState<any[]>([])
  const [assetsLoading, setAssetsLoading] = useState(false)
  const [assetId, setAssetId] = useState('')
  const [report, setReport] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [authorized, setAuthorized] = useState('')

  const loadAssetOptions = useCallback(async () => {
    setAssetsLoading(true)
    try {
      const res: any = await listAssets({ page_size: 200 })
      setAssets(res?.data || [])
    } catch {
      setAssets([])
    } finally {
      setAssetsLoading(false)
    }
  }, [])

  useEffect(() => {
    loadAssetOptions()
  }, [loadAssetOptions])

  const audit = useCallback(async (id: string) => {
    if (!id) { setReport(null); return }
    setLoading(true)
    setReport(null)
    try {
      const res: any = await cleanAssetProvenance(id, {})
      if (res?.success) setReport(res.report)
    } catch (error: any) {
      message.error(error?.message || '审计失败')
    } finally {
      setLoading(false)
    }
  }, [])

  const clean = useCallback(async () => {
    if (!assetId) return
    setLoading(true)
    try {
      const res: any = await cleanAssetProvenance(assetId, { confirm: true, authorized_source: authorized })
      if (res?.success) {
        message.success(`已生成清理副本（原资产保留）：${res.derived_asset_id}`)
        setReport(null)
        setAssetId('')
        setAuthorized('')
      }
    } catch (error: any) {
      message.error(error?.message || '清理失败')
    } finally {
      setLoading(false)
    }
  }, [assetId, authorized])

  return (
    <div style={{ maxWidth: 860, margin: '0 auto', padding: 24 }}>
      <Space align="center" style={{ marginBottom: 6 }}>
        <SafetyCertificateOutlined style={{ fontSize: 22, color: 'var(--primary)' }} />
        <Title level={4} style={{ margin: 0 }}>元数据 / AI 标记清理</Title>
      </Space>
      <Text type="secondary">
        审计并去除资产里的 EXIF/XMP/C2PA 元数据、隐形/双向控制符与容器元数据，生成不覆盖原文件的清理副本（带 derived_from 血缘）。
        与「图片编辑器视觉水印」「平台采集无水印下载」不同。
      </Text>

      <Card style={{ marginTop: 16 }}>
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Select
            showSearch
            placeholder="选择要审计的素材（名称搜索）"
            value={assetId || undefined}
            loading={assetsLoading}
            style={{ width: '100%' }}
            options={assets.map((item: any) => ({
              value: item.id,
              label: `${item.title || item.name || item.id} · ${item.asset_type || 'asset'}`,
            }))}
            optionFilterProp="label"
            onChange={(id) => { setAssetId(id); audit(id) }}
          />

          {loading ? (
            <div style={{ display: 'grid', placeItems: 'center', padding: 24 }}><Spin /></div>
          ) : report ? (
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <Alert
                type={report.cleanable ? 'warning' : 'info'}
                showIcon
                message={report.cleanable ? '可生成清理副本（不覆盖原文件）' : '当前文件没有可清理的元数据或标记'}
                description={report.notes?.length ? report.notes.join('；') : undefined}
              />
              <Descriptions column={1} size="small" bordered>
                <Descriptions.Item label="媒体类型">{report.media_kind}</Descriptions.Item>
                <Descriptions.Item label="元数据键">{report.metadata_keys?.length ? report.metadata_keys.join(', ') : '—'}</Descriptions.Item>
                <Descriptions.Item label="隐形字符">{report.invisible_character_count ?? 0}</Descriptions.Item>
                <Descriptions.Item label="双向控制符">{report.bidi_control_count ?? 0}</Descriptions.Item>
              </Descriptions>
              <Input
                placeholder="授权来源（可选）：如 user_upload / platform_authorized"
                value={authorized}
                onChange={(e) => setAuthorized(e.target.value)}
              />
              <Button
                type="primary"
                icon={<ClearOutlined />}
                disabled={!report.cleanable}
                loading={loading}
                onClick={clean}
              >
                生成清理副本
              </Button>
            </Space>
          ) : null}
        </Space>
      </Card>
    </div>
  )
}
