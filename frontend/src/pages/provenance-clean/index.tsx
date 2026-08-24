/**
 * YLCraft — 元数据 / AI 标记清理（独立工具页）
 *
 * 从素材库选择资产 → 审计（EXIF/XMP/C2PA、隐形/双向控制符、容器元数据）
 * → 生成不覆盖原文件的清理副本（derived_from 血缘）。
 * 与图片编辑器「视觉水印」、平台采集「无水印下载」是不同能力。
 */
import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Card, Descriptions, Input, Radio, Select, Space, Spin, Typography, message } from 'antd'
import { ClearOutlined, DeleteOutlined, RadarChartOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { cleanAssetProvenance, detectAssetDeepWatermark, listAssets, removeAssetVisualWatermark } from '../../api'

const { Title, Text } = Typography

export default function ProvenanceCleanPage() {
  const [assets, setAssets] = useState<any[]>([])
  const [assetsLoading, setAssetsLoading] = useState(false)
  const [assetId, setAssetId] = useState('')
  const [report, setReport] = useState<any>(null)
  const [deepReport, setDeepReport] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [deepLoading, setDeepLoading] = useState(false)
  const [authorized, setAuthorized] = useState('')
  const [wmMethod, setWmMethod] = useState('delogo')
  const [wmCorner, setWmCorner] = useState('top_right')
  const [wmRemoving, setWmRemoving] = useState(false)

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
    if (!id) { setReport(null); setDeepReport(null); return }
    setLoading(true)
    setReport(null)
    setDeepReport(null)
    try {
      const res: any = await cleanAssetProvenance(id, {})
      if (res?.success) setReport(res.report)
    } catch (error: any) {
      message.error(error?.message || '审计失败')
    } finally {
      setLoading(false)
    }
  }, [])

  const detectDeep = useCallback(async () => {
    if (!assetId) return
    setDeepLoading(true)
    setDeepReport(null)
    try {
      const res: any = await detectAssetDeepWatermark(assetId)
      if (res?.success) setDeepReport(res.report)
    } catch (error: any) {
      message.error(error?.message || '深度水印检测失败')
    } finally {
      setDeepLoading(false)
    }
  }, [assetId])

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

  const removeWm = useCallback(async () => {
    if (!assetId) return
    setWmRemoving(true)
    try {
      const res: any = await removeAssetVisualWatermark(assetId, {
        method: wmMethod,
        region: { corner: wmCorner, inset: 0 },
      })
      if (res?.success) {
        message.success(`已生成去水印副本（原资产保留）：${res.derived_asset_id}`)
      }
    } catch (error: any) {
      message.error(error?.message || '去水印失败')
    } finally {
      setWmRemoving(false)
    }
  }, [assetId, wmMethod, wmCorner])

  return (
    <div style={{ maxWidth: 860, margin: '0 auto', padding: 24 }}>
      <Space align="center" style={{ marginBottom: 6 }}>
        <SafetyCertificateOutlined style={{ fontSize: 22, color: 'var(--primary)' }} />
        <Title level={4} style={{ margin: 0 }}>素材审计与去水印</Title>
      </Space>
      <Text type="secondary">
        一站式处理素材：① 审计/去除隐形 AI 来源标记与文件元数据（EXIF/XMP/C2PA、隐形 Unicode、容器元数据、
        文档核心属性），② 只读检测合成水印痕迹，③ 去除画面上肉眼可见的显性水印（图片/视频）。
        全部生成不覆盖原文件的派生副本（带 derived_from 血缘），适合短剧等成片场景消除影响观感的水印。
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
                {report.unicode_breakdown && Object.keys(report.unicode_breakdown).length ? (
                  <Descriptions.Item label="Unicode 标记明细">
                    {Object.entries(report.unicode_breakdown)
                      .map(([k, v]) => `${k}=${v}`)
                      .join('，')}
                  </Descriptions.Item>
                ) : null}
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
              <Button
                icon={<RadarChartOutlined />}
                loading={deepLoading}
                onClick={detectDeep}
              >
                只读检测合成水印（CtrlRegen/SynthID）
              </Button>
            </Space>
          ) : null}

          {deepReport ? (
            <Card size="small" style={{ marginTop: 4 }} title="深度水印检测（只读，不修改文件）">
              <Alert
                type="info"
                showIcon
                message={deepReport.supported ? `载体：${deepReport.media_kind}` : `当前载体（${deepReport.media_kind}）暂只支持只读审计`}
                description={deepReport.notes?.length ? deepReport.notes.join('；') : undefined}
              />
              <Descriptions column={1} size="small" bordered style={{ marginTop: 12 }}>
                <Descriptions.Item label="CtrlRegen 统计得分">{deepReport.ctrlregen?.score ?? '—'}</Descriptions.Item>
                <Descriptions.Item label="置信度">{deepReport.ctrlregen?.confidence ?? '—'}</Descriptions.Item>
                <Descriptions.Item label="SynthID">
                  {deepReport.synthid?.status === 'enabled'
                    ? `已启用（${deepReport.synthid?.provider}）`
                    : deepReport.synthid?.status === 'skipped'
                      ? '未启用（默认跳过，不引入 GPU/ML 硬依赖）'
                      : deepReport.synthid?.status ?? '—'}
                </Descriptions.Item>
              </Descriptions>
            </Card>
          ) : null}

          <Card size="small" title="显性可见水印去除（图片/视频）" style={{ marginTop: 4 }}>
            <Alert
              type="info"
              showIcon
              message="去除画面上肉眼可见的水印（角落 logo、文字、台标），生成不覆盖原文件的派生副本"
              description="适合短剧等成片场景消除影响观感的水印。选择水印所在位置与方法后点击去除。"
            />
            <Space direction="vertical" size={12} style={{ width: '100%', marginTop: 12 }}>
              <div>
                <Text strong>水印位置</Text>
                <Radio.Group
                  style={{ marginLeft: 12 }}
                  value={wmCorner}
                  onChange={(e) => setWmCorner(e.target.value)}
                >
                  <Radio.Button value="top_left">左上</Radio.Button>
                  <Radio.Button value="top_right">右上</Radio.Button>
                  <Radio.Button value="bottom_left">左下</Radio.Button>
                  <Radio.Button value="bottom_right">右下</Radio.Button>
                  <Radio.Button value="top">顶部</Radio.Button>
                  <Radio.Button value="bottom">底部</Radio.Button>
                  <Radio.Button value="center">居中</Radio.Button>
                </Radio.Group>
              </div>
              <div>
                <Text strong>去除方法</Text>
                <Radio.Group
                  style={{ marginLeft: 12 }}
                  value={wmMethod}
                  onChange={(e) => setWmMethod(e.target.value)}
                >
                  <Radio.Button value="delogo">插值填充（推荐·静态logo）</Radio.Button>
                  <Radio.Button value="blur">区域模糊（半透明水印）</Radio.Button>
                  <Radio.Button value="crop">裁剪边缘（贴边水印）</Radio.Button>
                </Radio.Group>
              </div>
              <Button
                type="primary"
                danger
                icon={<DeleteOutlined />}
                disabled={!assetId}
                loading={wmRemoving}
                onClick={removeWm}
              >
                去除显性水印并生成副本
              </Button>
            </Space>
          </Card>
        </Space>
      </Card>
    </div>
  )
}
