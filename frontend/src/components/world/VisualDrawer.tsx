/**
 * AI 视觉稿抽屉：生成模式（文生图 / 图生图）、生图后端与模型、尺寸、参考图勾选、
 * 画风、提示词覆盖与 AI 优化、生成动作、最近成图与历史多稿（可设为底图参考层）。
 *
 * 成图是派生视觉资产：抽屉内只产生/引用成图，绝不写回结构化地图（正典在 map_json）。
 * 所有状态与动作由父组件注入，本组件不持有业务逻辑。
 */
import {
  Alert,
  AutoComplete,
  Button,
  Card,
  Drawer,
  Input,
  Segmented,
  Select,
  Space,
  Tag,
  Typography,
  Upload,
} from 'antd'
import { EyeOutlined, PictureOutlined, ThunderboltOutlined } from '@ant-design/icons'
import ProviderModelSelect, { type BackendLike } from '../ai/ProviderModelSelect'
import type { WorldMapVisual, WorldMapVisualResult } from '../../api/novelSource'

const { Text, Paragraph } = Typography

export type VisualMode = 'text2img' | 'img2img'

/**
 * 画风预设：替代原来的自由文本框单一输入（原型反模式第 5 条）。
 * 留空 = 自适应：后端提示词会声明「按项目视觉基准（参考图）自适应，
 * 无参考图时采用克制的写实地图风格」，这与后端 build_map_visual_prompt 一致。
 */
const STYLE_PRESETS = [
  { value: '写实乡村', label: '写实乡村' },
  { value: '古风手绘', label: '古风手绘' },
  { value: '简约线稿', label: '简约线稿' },
  { value: '水墨', label: '水墨' },
  { value: '羊皮纸古地图', label: '羊皮纸古地图' },
]

interface Props {
  open: boolean
  onClose: () => void
  mode: VisualMode
  onModeChange: (mode: VisualMode) => void
  imageBackends: BackendLike[]
  visualProvider: string
  visualModel: string
  onVisualProviderChange: (provider: string, backend: BackendLike | null) => void
  onVisualModelChange: (model: string) => void
  size: string
  sizeOptions: string[]
  onSizeChange: (size: string) => void
  historyVisuals: WorldMapVisual[]
  refAssetIds: string[]
  onToggleRefAsset: (nodeId: string) => void
  refUrls: string[]
  onToggleRefUrl: (url: string) => void
  uploadRefs: string[]
  onAddUploadRef: (dataUrl: string) => void
  onRemoveUploadRef: (index: number) => void
  style: string
  onStyleChange: (style: string) => void
  baselineAssetId?: string | null
  onOpenBaselinePicker: () => void
  onClearBaseline: () => void
  promptOverride: string
  onPromptOverrideChange: (value: string) => void
  onPreview: () => void
  previewLoading: boolean
  onOptimize: () => void
  optimizing: boolean
  onGenerate: () => void
  generating: boolean
  llmBackends: BackendLike[]
  llmProvider: string
  llmModel: string
  onLlmProviderChange: (provider: string, backend: BackendLike | null) => void
  onLlmModelChange: (model: string) => void
  onLoadLastPrompt: () => void
  noImageBackend: boolean
  lastVisual: WorldMapVisualResult | null
  onSetBaseMap: (url: string) => void
}

export default function VisualDrawer({
  open,
  onClose,
  mode,
  onModeChange,
  imageBackends,
  visualProvider,
  visualModel,
  onVisualProviderChange,
  onVisualModelChange,
  size,
  sizeOptions,
  onSizeChange,
  historyVisuals,
  refAssetIds,
  onToggleRefAsset,
  refUrls,
  onToggleRefUrl,
  uploadRefs,
  onAddUploadRef,
  onRemoveUploadRef,
  style,
  onStyleChange,
  baselineAssetId,
  onOpenBaselinePicker,
  onClearBaseline,
  promptOverride,
  onPromptOverrideChange,
  onPreview,
  previewLoading,
  onOptimize,
  optimizing,
  onGenerate,
  generating,
  llmBackends,
  llmProvider,
  llmModel,
  onLlmProviderChange,
  onLlmModelChange,
  onLoadLastPrompt,
  noImageBackend,
  lastVisual,
  onSetBaseMap,
}: Props) {
  return (
    <Drawer
      title="AI 视觉稿（派生视觉资产 · 不影响结构化地图）"
      placement="right"
      width={480}
      open={open}
      onClose={onClose}
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        <Card size="small" title="生成地图视觉成图" style={{ background: '#fafafa' }}>
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <Segmented
              value={mode}
              onChange={(value) => onModeChange(value as VisualMode)}
              options={[
                { value: 'text2img', label: '文生图' },
                { value: 'img2img', label: '图生图（携带参考图）' },
              ]}
            />
            <ProviderModelSelect
              backends={imageBackends}
              provider={visualProvider}
              model={visualModel}
              onProviderChange={onVisualProviderChange}
              onModelChange={onVisualModelChange}
              size="small"
              providerPlaceholder="生图后端"
              providerWidth={170}
              modelWidth={200}
            />
            <Select
              placeholder="尺寸"
              style={{ width: 130 }}
              value={size}
              onChange={onSizeChange}
              options={sizeOptions.map((item) => ({ value: item, label: item }))}
            />

            {mode === 'img2img' && (
              <div style={{ fontSize: 12 }}>
                <Text strong style={{ fontSize: 12 }}>
                  参考图（勾选历史成图或上传，按顺序作为图 1、图 2…）
                </Text>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 6 }}>
                  {historyVisuals
                    .filter((v) => v.url)
                    .map((v) => {
                      const url = v.url as string
                      // 已入素材库的成图按节点 ID 引用（服务端解析为最新版本），避免传 url/base64。
                      const isAssetRef = Boolean(v.node_id)
                      const checked = isAssetRef
                        ? refAssetIds.includes(v.node_id as string)
                        : refUrls.includes(url)
                      const onToggle = () =>
                        isAssetRef ? onToggleRefAsset(v.node_id as string) : onToggleRefUrl(url)
                      return (
                        <div
                          key={url}
                          onClick={onToggle}
                          title={isAssetRef ? '素材库引用（节点 ID）' : 'URL 兜底引用'}
                          style={{
                            width: 72,
                            cursor: 'pointer',
                            position: 'relative',
                            border: checked ? '2px solid #1677ff' : '1px solid #d9d9d9',
                            borderRadius: 6,
                            overflow: 'hidden',
                          }}
                        >
                          <img
                            src={url}
                            alt=""
                            style={{ width: '100%', aspectRatio: '1', objectFit: 'cover', display: 'block' }}
                          />
                          {checked && (
                            <Tag
                              color="blue"
                              style={{
                                position: 'absolute',
                                top: 2,
                                left: 2,
                                marginInlineEnd: 0,
                                fontSize: 10,
                                lineHeight: '16px',
                              }}
                            >
                              {isAssetRef ? '素材库·参考' : '参考'}
                            </Tag>
                          )}
                          {isAssetRef && !checked && (
                            <Tag
                              style={{
                                position: 'absolute',
                                top: 2,
                                left: 2,
                                marginInlineEnd: 0,
                                fontSize: 10,
                                lineHeight: '16px',
                              }}
                            >
                              素材库
                            </Tag>
                          )}
                        </div>
                      )
                    })}
                  <Upload
                    accept="image/*"
                    showUploadList={false}
                    beforeUpload={(file) => {
                      const reader = new FileReader()
                      reader.onload = () => {
                        if (typeof reader.result === 'string') onAddUploadRef(reader.result)
                      }
                      reader.readAsDataURL(file)
                      return false
                    }}
                  >
                    <Button size="small">+ 上传参考图</Button>
                  </Upload>
                </div>
                {uploadRefs.length > 0 && (
                  <Space wrap style={{ marginTop: 6 }}>
                    {uploadRefs.map((url, index) => (
                      <div key={index} style={{ position: 'relative', width: 72 }}>
                        <img
                          src={url}
                          alt=""
                          style={{
                            width: '100%',
                            aspectRatio: '1',
                            objectFit: 'cover',
                            borderRadius: 6,
                            display: 'block',
                          }}
                        />
                        <Button
                          size="small"
                          danger
                          style={{
                            position: 'absolute',
                            top: 2,
                            right: 2,
                            padding: 0,
                            minWidth: 18,
                            height: 18,
                          }}
                          onClick={() => onRemoveUploadRef(index)}
                        >
                          ×
                        </Button>
                      </div>
                    ))}
                  </Space>
                )}
              </div>
            )}

            <Space wrap>
              <AutoComplete
                placeholder="画风（留空=按视觉基准自适应）"
                style={{ width: 200 }}
                value={style}
                onChange={onStyleChange}
                options={STYLE_PRESETS}
                allowClear
              />
              {baselineAssetId ? (
                <Space size={4}>
                  <Tag color="blue" style={{ marginInlineEnd: 0 }}>
                    视觉基准已设置
                  </Tag>
                  <Button size="small" type="link" onClick={onOpenBaselinePicker}>
                    更换
                  </Button>
                  <Button size="small" type="link" onClick={onClearBaseline}>
                    清除
                  </Button>
                </Space>
              ) : (
                <Button size="small" onClick={onOpenBaselinePicker}>
                  选择视觉基准
                </Button>
              )}
              <Button size="small" icon={<EyeOutlined />} loading={previewLoading} onClick={onPreview}>
                预览 Prompt
              </Button>
              <Button
                size="small"
                icon={<ThunderboltOutlined />}
                loading={optimizing}
                disabled={!llmBackends.length}
                onClick={onOptimize}
                title="AI 优化：润色当前预览提示词（保留坐标/方位/区域/路线）"
              >
                AI 优化
              </Button>
              <Button
                size="small"
                type="primary"
                icon={<PictureOutlined />}
                loading={generating}
                onClick={onGenerate}
              >
                生成视觉成图
              </Button>
            </Space>

            <Space wrap size={6}>
              <ProviderModelSelect
                backends={llmBackends}
                provider={llmProvider}
                model={llmModel}
                onProviderChange={onLlmProviderChange}
                onModelChange={onLlmModelChange}
                size="small"
                providerPlaceholder="优化用 LLM 供应商"
                modelPlaceholder="优化用模型"
                providerWidth={170}
                modelWidth={170}
              />
              <Button size="small" onClick={onLoadLastPrompt}>
                载入上次成图 Prompt
              </Button>
            </Space>

            <Input.TextArea
              rows={3}
              placeholder="可选：覆盖提示词（留空按结构化地图自动生成，含坐标/方位/区域/路线）"
              value={promptOverride}
              onChange={(e) => onPromptOverrideChange(e.target.value)}
            />
            {noImageBackend && (
              <Alert
                type="warning"
                showIcon
                message="未检测到生图后端：请先在「AI 连接器」配置 provider_type=image 的 Provider。"
              />
            )}
            {lastVisual && (
              <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                {lastVisual.url && (
                  <img
                    src={lastVisual.url}
                    alt="地图视觉成图"
                    style={{
                      maxWidth: 260,
                      width: '100%',
                      border: '1px solid #e5e7eb',
                      borderRadius: 6,
                    }}
                  />
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    最近生成 · {lastVisual.provider || '—'} · {lastVisual.model || '—'} ·{' '}
                    {lastVisual.status}
                  </Text>
                  {lastVisual.node_id && (
                    <div>
                      <Text type="secondary" style={{ fontSize: 12 }} copyable={{ text: lastVisual.node_id }}>
                        素材库节点：{lastVisual.node_id}
                      </Text>
                    </div>
                  )}
                  <Paragraph style={{ fontSize: 12, whiteSpace: 'pre-wrap', marginBottom: 0 }}>
                    {lastVisual.prompt}
                  </Paragraph>
                  {lastVisual.url && (
                    <Button
                      size="small"
                      style={{ marginTop: 6 }}
                      onClick={() => onSetBaseMap(lastVisual.url as string)}
                      title="派生资产：仅作为参考层显示，不写入地图事实、不叠加标记"
                    >
                      设为底图（参考层）
                    </Button>
                  )}
                </div>
              </div>
            )}
          </Space>
        </Card>

        {historyVisuals.length > 0 && (
          <Card
            size="small"
            title={`视觉成图历史（${historyVisuals.length}）`}
            style={{ background: '#fafafa' }}
          >
            <Space wrap>
              {historyVisuals.map((visual, index) => (
                <div key={index} style={{ width: 168, textAlign: 'center' }}>
                  {visual.url && (
                    <img
                      src={visual.url}
                      alt={`成图 ${index + 1}`}
                      style={{
                        width: '100%',
                        aspectRatio: '1',
                        objectFit: 'cover',
                        border: '1px solid #e5e7eb',
                        borderRadius: 6,
                      }}
                    />
                  )}
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {visual.provider || 'unknown'} · {visual.model || '—'}
                    </Text>
                  </div>
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {visual.style ? `风格：${visual.style} ` : ''}
                      {visual.created_at ? new Date(visual.created_at).toLocaleDateString() : ''}
                    </Text>
                  </div>
                  {visual.node_id && (
                    <div>
                      <Text type="secondary" style={{ fontSize: 11 }} copyable={{ text: visual.node_id }}>
                        素材库
                      </Text>
                    </div>
                  )}
                  {visual.url && (
                    <Button
                      size="small"
                      style={{ marginTop: 4 }}
                      onClick={() => onSetBaseMap(visual.url as string)}
                      title="派生资产：仅作为参考层显示，不写入地图事实"
                    >
                      设为底图
                    </Button>
                  )}
                </div>
              ))}
            </Space>
          </Card>
        )}
      </Space>
    </Drawer>
  )
}
