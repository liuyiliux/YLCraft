import { useMemo, useState } from 'react'
import { Alert, Button, Card, Drawer, Empty, Input, Segmented, Space, Tag, Typography, message } from 'antd'
import { CopyOutlined, ImportOutlined } from '@ant-design/icons'
import { createConnector } from '../../api'
import { useTheme } from '../../constants/theme'

type PresetConnector = Record<string, any>
type PresetFile = { schema_version: number; name: string; description: string; connectors: PresetConnector[] }
const presetModules = import.meta.glob('../../../../examples/ai-connectors/*.json', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>
const typeLabels: Record<string, string> = { all: '全部', llm: '文本', image: '图片', video: '视频', '3d': '图生 3D', tts: '语音', stt: '语音识别', embedding: '向量' }

function loadPresetFiles(): PresetFile[] {
  return Object.entries(presetModules).flatMap(([path, raw]) => {
    try { const data = JSON.parse(raw) as PresetFile; return data?.connectors?.length ? [{ ...data, name: data.name || path.split('/').pop() || 'Preset' }] : [] } catch { return [] }
  })
}

function normalizeType(value: unknown) {
  const type = typeof value === 'string' ? value.trim().toLowerCase() : ''
  return ({ model3d: '3d', model_3d: '3d', image_to_3d: '3d', 'image-to-3d': '3d' } as Record<string, string>)[type] || type || 'llm'
}

function cloneForImport(connector: PresetConnector) {
  const item: PresetConnector = { ...connector, provider_type: normalizeType(connector.provider_type), id: String(connector.id) + '-example-' + Date.now().toString(36), name: String(connector.name || connector.id) + ' (示例)', api_key: '', is_active: false, is_default: false, description: (String(connector.description || '') + ' Imported from the public YLCraft example preset.').trim() }
  for (const key of ['response_config', 'parameter_transforms', 'supported_sizes', 'default_params']) if (item[key] !== undefined && item[key] !== null && typeof item[key] !== 'string') item[key] = JSON.stringify(item[key])
  return item
}

export default function ProviderPresetsPage({ embedded = false }: { embedded?: boolean }) {
  const { theme: THEME } = useTheme()
  const [busy, setBusy] = useState<string | null>(null)
  const [category, setCategory] = useState('all')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<{ connector: PresetConnector; file: PresetFile } | null>(null)
  const files = useMemo(loadPresetFiles, [])
  const entries = useMemo(() => files.flatMap(file => file.connectors.map(connector => ({ connector, file }))).filter(({ connector, file }) => {
    const haystack = [connector.name, connector.provider, connector.default_model, file.name].join(' ').toLowerCase()
    return (category === 'all' || normalizeType(connector.provider_type) === category) && (!search.trim() || haystack.includes(search.trim().toLowerCase()))
  }), [files, category, search])
  const categories = useMemo(() => ['all', ...Array.from(new Set(files.flatMap(file => file.connectors.map(item => normalizeType(item.provider_type)))))], [files])
  const importOne = async (connector: PresetConnector) => { const item = cloneForImport(connector); setBusy(String(connector.id)); try { await createConnector(item); message.success('已填入“' + item.name + '”，默认停用，不会覆盖现有配置') } catch (error: any) { message.error(error?.response?.data?.detail || error?.message || '示例配置填入失败') } finally { setBusy(null) } }
  const copyJson = async (connector: PresetConnector) => { await navigator.clipboard.writeText(JSON.stringify(connector, null, 2)); message.success('配置 JSON 已复制') }
  return <div style={{ maxWidth: embedded ? undefined : 1380, margin: '0 auto' }}>
    <div style={{ marginBottom: 20 }}><Typography.Title level={2} style={{ margin: 0, color: THEME.textPrimary }}>AI 示例配置</Typography.Title><Typography.Paragraph style={{ color: THEME.textPrimary, marginBottom: 0 }}>公开连接器预设。列表只保留摘要，完整请求和响应配置请打开详情。</Typography.Paragraph></div>
    <Alert type="info" showIcon message={<span style={{ color: THEME.textPrimary, fontWeight: 600 }}>公开预设不包含 API Key</span>} description={<span style={{ color: THEME.textPrimary }}>一键填入后请在模型配置中补充密钥并启用。</span>} style={{ marginBottom: 16, background: THEME.bgElevated, border: '1px solid ' + THEME.primary }} />
    <Space wrap style={{ width: '100%', marginBottom: 16 }}><Segmented value={category} onChange={value => setCategory(String(value))} options={categories.map(type => ({ label: typeLabels[type] || type, value: type }))} /><Input allowClear placeholder="搜索供应商、名称或模型" value={search} onChange={event => setSearch(event.target.value)} style={{ width: 260 }} /></Space>
    {!entries.length ? <Empty description="没有匹配的示例配置" /> : <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: 12 }}>{entries.map(({ connector, file }) => { const type = normalizeType(connector.provider_type); return <Card key={file.name + '-' + connector.id} size="small" style={{ background: THEME.bgCard, borderColor: THEME.border }} actions={[<Button type="link" onClick={() => setSelected({ connector, file })}>详情</Button>, <Button type="link" icon={<ImportOutlined />} loading={busy === String(connector.id)} onClick={() => void importOne(connector)}>一键填入</Button>]}><Space direction="vertical" size={6} style={{ width: '100%' }}><Space wrap><Typography.Text strong style={{ color: THEME.textPrimary }}>{connector.name}</Typography.Text><Tag>{typeLabels[type] || type}</Tag>{connector.support_reference_image && <Tag color="green">支持参考图</Tag>}</Space><Typography.Text style={{ color: THEME.textPrimary }}>{connector.provider || '通用供应商'}</Typography.Text><Typography.Text type="secondary">模型：{connector.default_model || '未指定'}</Typography.Text><Typography.Text type="secondary">来源：{file.name}</Typography.Text></Space></Card> })}</div>}
    <Drawer title={selected?.connector.name || '预设详情'} open={Boolean(selected)} onClose={() => setSelected(null)} width={680}>{selected && <Space direction="vertical" size={14} style={{ width: '100%' }}><Typography.Paragraph>{selected.connector.description}</Typography.Paragraph><Typography.Text strong>连接信息</Typography.Text><Typography.Text>供应商：{selected.connector.provider || '通用'}</Typography.Text><Typography.Text>类型：{typeLabels[normalizeType(selected.connector.provider_type)] || normalizeType(selected.connector.provider_type)}</Typography.Text><Typography.Text>Base URL：{selected.connector.base_url || '未指定'}</Typography.Text><Typography.Text>Endpoint：{selected.connector.api_endpoint || '未指定'}</Typography.Text><Typography.Text>模型：{selected.connector.default_model || '未指定'}</Typography.Text><Typography.Text strong>请求模板与响应配置</Typography.Text><pre style={{ maxHeight: 280, overflow: 'auto', whiteSpace: 'pre-wrap' }}>{JSON.stringify({ request_template: selected.connector.request_template, response_config: selected.connector.response_config, default_params: selected.connector.default_params }, null, 2)}</pre><Space><Button type="primary" icon={<ImportOutlined />} loading={busy === String(selected.connector.id)} onClick={() => void importOne(selected.connector)}>一键填入</Button><Button icon={<CopyOutlined />} onClick={() => void copyJson(selected.connector)}>复制 JSON</Button></Space></Space>}</Drawer>
  </div>
}
