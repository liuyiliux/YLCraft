/**
 * 图生图「编辑台」（EditHere 式布局）
 *
 * 参考 EditHere 的空间组织：**上方工具条 → 中央画布 → 右侧批注侧栏**。
 * 这三者的顺序不是审美偏好，是功能要求：
 * - 工具条在上 = 模型/尺寸这些「全局设置」不用低头找，也不会把画布挤小；
 * - 画布居中且占满 = 圈选精度直接决定改图质量，画布必须大；
 * - 批注在右 = 眼睛从「图」移到「字」再移回「图」，编号能一一对上。
 *
 * 与原来单栏表单的差别：批注不再是「参考图下面又一块折叠区」，而是工作台的主体。
 */

import { useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Select,
  Space,
  Tag,
  Tooltip,
  Typography,
  Upload,
  message,
} from 'antd'
import {
  AppstoreOutlined,
  ClearOutlined,
  EyeOutlined,
  InboxOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import type { UploadFile } from 'antd/es/upload/interface'
import AnnotationCanvas, {
  toAnnotationPayload,
  type ImageAnnotation,
} from './AnnotationCanvas'
import AnnotationSidebar from './AnnotationSidebar'
import ImagePromptPreviewModal from './ImagePromptPreviewModal'
import { renderAnnotatedImage } from './renderAnnotatedImage'

const { Text } = Typography
const { Dragger } = Upload

interface Props {
  imageUrl: string
  annotations: ImageAnnotation[]
  onAnnotationsChange: (next: ImageAnnotation[]) => void
  activeId: string | null
  onActiveChange: (id: string | null) => void

  referenceImages: UploadFile[]
  onReferenceImagesChange: (files: UploadFile[]) => void
  onPickFromLibrary: () => void
  referenceUrl: string
  onReferenceUrlChange: (value: string) => void
  onAddReferenceUrl: () => void
  libraryPicker: React.ReactNode

  provider?: string
  providerOptions: { label: string; value: string }[]
  onProviderChange: (value: string) => void
  selectedModel?: string
  modelOptions: { label: string; value: string }[]
  onModelChange: (value: string) => void
  size?: string
  sizeOptions: { label: string; value: string }[]
  onSizeChange: (value: string) => void
  batchCount: number
  onBatchCountChange: (value: number) => void

  loading: boolean
  onGenerate: () => void
  onSwitchToClassic: () => void
  hintMode: 'marked' | 'text'
  onHintModeChange: (mode: 'marked' | 'text') => void
  /** 提示词预览弹窗。默认只读，这里只负责触发。 */
  prompt: string
  hintText: string | undefined
  onHintTextChange: (value: string | undefined) => void
  onPromptChange: (value: string) => void
  negativePrompt: string
  onNegativePromptChange: (value: string) => void
}

export default function ImageEditorWorkspace(props: Props) {
  const {
    imageUrl,
    annotations,
    onAnnotationsChange,
    activeId,
    onActiveChange,
    referenceImages,
    onReferenceImagesChange,
    onPickFromLibrary,
    referenceUrl,
    onReferenceUrlChange,
    onAddReferenceUrl,
    libraryPicker,
    provider,
    providerOptions,
    onProviderChange,
    selectedModel,
    modelOptions,
    onModelChange,
    size,
    sizeOptions,
    onSizeChange,
    batchCount,
    onBatchCountChange,
    loading,
    onGenerate,
    onSwitchToClassic,
    hintMode,
    onHintModeChange,
    prompt,
    hintText,
    onHintTextChange,
    onPromptChange,
    negativePrompt,
    onNegativePromptChange,
  } = props

  const [showSettings, setShowSettings] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [markedPreview, setMarkedPreview] = useState('')
  const written = toAnnotationPayload(annotations).length
  const writtenPayload = toAnnotationPayload(annotations)

  // 预览弹窗要展示「实际发出去的那张带框图」。渲染较贵（canvas + toDataURL），
  // 所以只在**打开弹窗时**算一次并缓存，批注变动时用已缓存的旧图会误导用户。
  useEffect(() => {
    if (!previewOpen) {
      setMarkedPreview('')
      return
    }
    let cancelled = false
    if (hintMode !== 'marked' || !imageUrl || writtenPayload.length === 0) {
      setMarkedPreview('')
      return
    }
    renderAnnotatedImage(imageUrl, writtenPayload)
      .then((url) => {
        if (!cancelled) setMarkedPreview(url)
      })
      .catch(() => {
        if (!cancelled) setMarkedPreview('')
      })
    return () => {
      cancelled = true
    }
  }, [previewOpen, hintMode, imageUrl, writtenPayload])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* ===== 顶部工具条 ===== */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '10px 14px',
          background: '#1a1a2e',
          border: '1px solid #333',
          borderRadius: 8,
          marginBottom: 12,
          flexWrap: 'wrap',
        }}
      >
        <Space size={8} wrap>
          <ThunderboltOutlined style={{ color: '#7c3aed' }} />
          <Text strong style={{ color: '#e2e8f0' }}>
            改图工作台
          </Text>
          <Tag color="cyan" style={{ margin: 0 }}>
            图生图
          </Tag>
        </Space>

        {/* 模型选择置顶：改图效果几乎完全由模型决定，这是最需要一眼看到、手边就能换的东西 */}
        <Select
          value={provider}
          onChange={onProviderChange}
          style={{ width: 150 }}
          size="small"
          placeholder="厂商"
          options={providerOptions}
        />
        <Select
          value={selectedModel}
          onChange={onModelChange}
          style={{ width: 210 }}
          size="small"
          placeholder="模型"
          options={modelOptions}
          showSearch
          optionFilterProp="label"
        />

        <Select
          value={size}
          onChange={onSizeChange}
          style={{ width: 140 }}
          size="small"
          placeholder="尺寸"
          options={sizeOptions}
        />

        <Space size={4} wrap>
          {[1, 2, 3, 4].map((n) => (
            <Button
              key={n}
              size="small"
              type={batchCount === n ? 'primary' : 'default'}
              onClick={() => onBatchCountChange(n)}
            >
              {n}
            </Button>
          ))}
        </Space>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          <Tooltip title="参数提示词与反向提示词">
            <Button
              size="small"
              type={showSettings ? 'primary' : 'default'}
              onClick={() => setShowSettings((v) => !v)}
              icon={<AppstoreOutlined />}
            >
              提示词
            </Button>
          </Tooltip>
          <Tooltip title="查看模型最终收到的完整提示词（含系统自动拼接部分）">
            <Button
              size="small"
              type="primary"
              ghost
              onClick={() => setPreviewOpen(true)}
              icon={<EyeOutlined />}
            >
              预览提示词
            </Button>
          </Tooltip>
          <Button size="small" onClick={onSwitchToClassic}>
            返回表单模式
          </Button>
        </div>
      </div>

      {/* 提示词区：默认收起。改图时批注才是主提示词，复述画面反而容易把模型带偏。 */}
      {showSettings && (
        <div
          style={{
            padding: 12,
            background: '#1a1a2e',
            border: '1px solid #333',
            borderRadius: 8,
            marginBottom: 12,
          }}
        >
          <Text style={{ color: '#8b8ba8', fontSize: 12, display: 'block', marginBottom: 6 }}>
            提示词（可留空：批注本身就是完整的修改指令）
          </Text>
          <textarea
            value={prompt}
            onChange={(e) => onPromptChange(e.target.value)}
            placeholder="描述你想要的画面…"
            style={{
              width: '100%',
              minHeight: 70,
              background: '#1e1e2e',
              border: '1px solid #333',
              borderRadius: 6,
              color: '#e2e8f0',
              padding: 8,
              fontFamily: 'inherit',
              marginBottom: 8,
            }}
          />
          <Text style={{ color: '#8b8ba8', fontSize: 12, display: 'block', marginBottom: 6 }}>
            反向提示词（可选）
          </Text>
          <textarea
            value={negativePrompt}
            onChange={(e) => onNegativePromptChange(e.target.value)}
            placeholder="不想出现的内容…"
            style={{
              width: '100%',
              minHeight: 54,
              background: '#1e1e2e',
              border: '1px solid #333',
              borderRadius: 6,
              color: '#e2e8f0',
              padding: 8,
              fontFamily: 'inherit',
            }}
          />
        </div>
      )}

      {/* ===== 主体：中央画布 + 右侧批注侧栏 ===== */}
      <div style={{ display: 'flex', gap: 12, flex: 1, minHeight: 0, flexWrap: 'wrap' }}>
        <div style={{ flex: '1 1 520px', minWidth: 0, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          {imageUrl ? (
            <AnnotationCanvas
              imageUrl={imageUrl}
              annotations={annotations}
              onChange={onAnnotationsChange}
              activeId={activeId}
              onActiveChange={onActiveChange}
              hideList
              disabled={loading}
              height={520}
            />
          ) : (
            <div
              style={{
                height: 520,
                background: '#0f0f1a',
                border: '1px dashed #3a3a5e',
                borderRadius: 8,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 12,
                padding: 24,
              }}
            >
              <InboxOutlined style={{ fontSize: 40, color: '#7c3aed' }} />
              <Text style={{ color: '#e2e8f0', fontSize: 14 }}>先放一张要改的图</Text>
              <Text style={{ color: '#8b8ba8', fontSize: 12, textAlign: 'center', maxWidth: 420 }}>
                上传、粘贴链接，或从素材库选一张。放好之后就能在图上圈出想改的位置。
              </Text>
              <Space wrap>
                <Button type="primary" onClick={onPickFromLibrary} disabled={loading}>
                  从素材库选择
                </Button>
              </Space>
              <Space.Compact style={{ width: '100%', maxWidth: 460 }}>
                <input
                  value={referenceUrl}
                  onChange={(e) => onReferenceUrlChange(e.target.value)}
                  placeholder="或粘贴图片 URL"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') onAddReferenceUrl()
                  }}
                  style={{
                    flex: 1,
                    background: '#1e1e2e',
                    border: '1px solid #333',
                    borderRadius: '6px 0 0 6px',
                    color: '#e2e8f0',
                    padding: '6px 10px',
                  }}
                />
                <Button onClick={onAddReferenceUrl}>添加</Button>
              </Space.Compact>
              <Dragger
                multiple
                maxCount={3}
                fileList={referenceImages}
                showUploadList={false}
                onChange={({ fileList }) => onReferenceImagesChange(fileList)}
                beforeUpload={() => false}
                style={{ background: '#1e1e2e', border: '1px dashed #444', maxWidth: 460 }}
              >
                <p style={{ color: '#8b8ba8', margin: 0 }}>或把图片拖到这里（最多 3 张）</p>
              </Dragger>
              {libraryPicker}
            </div>
          )}

          {/* 已有图时提供替换入口 */}
          {imageUrl && (
            <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <Text style={{ color: '#6b6b8a', fontSize: 12 }}>
                当前 {referenceImages.length} 张参考图（标注第 1 张）
              </Text>
              <Button
                size="small"
                icon={<ClearOutlined />}
                disabled={loading}
                onClick={() => {
                  onReferenceImagesChange([])
                  onAnnotationsChange([])
                  onActiveChange(null)
                }}
              >
                移除
              </Button>
              <Button size="small" onClick={onPickFromLibrary} disabled={loading}>
                换一张
              </Button>
            </div>
          )}
        </div>

        {/* 右侧批注侧栏 */}
        <div
          style={{
            flex: '0 0 320px',
            minWidth: 280,
            background: '#1a1a2e',
            border: '1px solid #333',
            borderRadius: 8,
            padding: 12,
            display: 'flex',
            flexDirection: 'column',
            maxHeight: 520,
          }}
        >
          <AnnotationSidebar
            annotations={annotations}
            onChange={onAnnotationsChange}
            activeId={activeId}
            onActiveChange={onActiveChange}
            disabled={loading}
            hintMode={hintMode}
            onHintModeChange={onHintModeChange}
          />
        </div>
      </div>

      {/* ===== 底部操作条 ===== */}
      <div
        style={{
          marginTop: 12,
          padding: '12px 14px',
          background: '#1a1a2e',
          border: '1px solid #333',
          borderRadius: 8,
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        {written > 0 ? (
          <Tag color="cyan" style={{ margin: 0 }}>
            {written} 条批注会随这次生成提交
          </Tag>
        ) : (
          <Text style={{ color: '#8b8ba8', fontSize: 12 }}>
            批注可以替代提示词：圈住要改的地方写清要求，直接点右边「开始生成」即可
          </Text>
        )}
        <Button
          type="primary"
          size="large"
          icon={<ThunderboltOutlined />}
          loading={loading}
          onClick={onGenerate}
          style={{ marginLeft: 'auto', minWidth: 160 }}
        >
          开始生成
        </Button>
      </div>

      <ImagePromptPreviewModal
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        prompt={prompt}
        annotations={writtenPayload}
        markedReference={hintMode === 'marked' && writtenPayload.length > 0}
        markedImagePreview={markedPreview}
        referenceCount={hintMode === 'marked' && writtenPayload.length > 0 ? 2 : referenceImages.length}
        hintText={hintText}
        onApplyHintText={onHintTextChange}
        showHintEditor={hintMode === 'marked' && writtenPayload.length > 0}
      />
    </div>
  )
}