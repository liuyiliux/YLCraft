/**
 * 图生图「画面批注」侧栏
 *
 * 从 `AnnotationCanvas` 里拆出来的**列表部分**：画布留在左栏原位，侧栏只管
 * 「编号 ↔ 意见」这一列对应关系。拆开的原因是编辑工作台需要把侧栏放到屏幕右侧——
 * 画布在中间、批注在右边，眼睛才能在「图」和「文字」之间来回对。
 *
 * 与画布共享同一份 `annotations` 状态，两边任一处修改都会同步。
 */

import { useMemo } from 'react'
import { Button, Empty, Input, Radio, Space, Tag, Tooltip, Typography, message } from 'antd'
import { ClearOutlined, DeleteOutlined } from '@ant-design/icons'
import type { ImageAnnotation } from './AnnotationCanvas'

const { Text } = Typography
const { TextArea } = Input

const MAX_COMMENT_LEN = 1000

const SAMPLES = [
  '这只手多了一根手指',
  '角色外套换成红色风衣',
  '这个气泡不要压住脸',
  '背景的电线去掉',
  '这里再亮一些',
]

interface Props {
  annotations: ImageAnnotation[]
  onChange: (next: ImageAnnotation[]) => void
  activeId?: string | null
  onActiveChange?: (id: string | null) => void
  disabled?: boolean
  /** 定位方式：带框标注图（默认）/ 纯文字坐标。 */
  hintMode?: 'marked' | 'text'
  onHintModeChange?: (mode: 'marked' | 'text') => void
}

export default function AnnotationSidebar({
  annotations,
  onChange,
  activeId,
  onActiveChange,
  disabled = false,
  hintMode = 'marked',
  onHintModeChange,
}: Props) {
  const writtenCount = annotations.filter((item) => item.comment.trim()).length

  // 与画布角标、提示词编号共用同一套：空意见不占号，否则三处会错位。
  const numbering = useMemo(() => {
    const map = new Map<string, number>()
    annotations.forEach((item) => {
      if (item.comment.trim() && !map.has(item.id)) map.set(item.id, map.size + 1)
    })
    return map
  }, [annotations])

  const updateComment = (id: string, comment: string) => {
    onChange(annotations.map((item) => (item.id === id ? { ...item, comment } : item)))
  }

  const removeAnnotation = (id: string) => {
    onChange(annotations.filter((item) => item.id !== id))
    if (activeId === id) onActiveChange?.(null)
  }

  const focusComment = (id: string) => {
    document.querySelector<HTMLTextAreaElement>(`[data-annotation-input="${id}"]`)?.focus()
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          paddingBottom: 8,
          borderBottom: '1px solid #2a2a3e',
          marginBottom: 10,
        }}
      >
        <Text strong style={{ color: '#e2e8f0', fontSize: 13 }}>
          批注意见
        </Text>
        <Tag color={annotations.length ? 'cyan' : 'default'} style={{ margin: 0 }}>
          已标 {writtenCount} / {annotations.length}
        </Tag>
        {annotations.length > 0 && (
          <Button
            size="small"
            type="text"
            icon={<ClearOutlined />}
            disabled={disabled}
            onClick={() => {
              onChange([])
              onActiveChange?.(null)
            }}
            style={{ color: '#8b8ba8', marginLeft: 'auto' }}
          >
            清空
          </Button>
        )}
      </div>

      {/* 定位方式：说清两种做法各自解决什么问题，别让用户盲选 */}
      {annotations.length > 0 && onHintModeChange && (
        <div style={{ marginBottom: 10, flex: '0 0 auto' }}>
          <Radio.Group
            size="small"
            value={hintMode}
            onChange={(e) => onHintModeChange(e.target.value)}
            style={{ marginBottom: 6 }}
          >
            <Radio.Button value="marked">带框图定位</Radio.Button>
            <Radio.Button value="text">只用文字</Radio.Button>
          </Radio.Group>
          <div style={{ color: '#6b6b8a', fontSize: 11, lineHeight: 1.6 }}>
            {hintMode === 'marked'
              ? '把框画到图上，模型直接「看见」位置，比读坐标更准（推荐）。'
              : '只发原图，用文字描述位置。框线可能干扰画质时用这个。'}
          </div>
        </div>
      )}

      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
        {annotations.length === 0 ? (
          <div style={{ paddingTop: 24, textAlign: 'center' }}>
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                <Text style={{ color: '#6b6b8a', fontSize: 12 }}>
                  还没有批注。
                  <br />
                  在左侧图上拖一个框就能添加。
                </Text>
              }
            />
          </div>
        ) : (
          <Space direction="vertical" style={{ width: '100%' }} size={8}>
            {annotations.map((item, index) => {
              const isActive = activeId === item.id
              const isEmpty = !item.comment.trim()
              return (
                <div
                  key={item.id}
                  onClick={() => {
                    onActiveChange?.(item.id)
                    focusComment(item.id)
                  }}
                  style={{
                    padding: 8,
                    borderRadius: 6,
                    cursor: 'pointer',
                    background: isActive ? '#1e1e2e' : 'transparent',
                    border: `1px solid ${
                      isEmpty ? '#f59e0b' : isActive ? '#7c3aed' : '#2a2a3e'
                    }`,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                    <Tag color={isEmpty ? 'orange' : 'cyan'} style={{ margin: 0, fontSize: 11 }}>
                      {isEmpty ? '—' : numbering.get(item.id)}
                    </Tag>
                    <Text style={{ color: '#6b6b8a', fontSize: 11, flex: 1 }}>
                      x {Math.round(item.rectangle.x1 * 100)}~{Math.round(item.rectangle.x2 * 100)}% · y{' '}
                      {Math.round(item.rectangle.y1 * 100)}~{Math.round(item.rectangle.y2 * 100)}%
                    </Text>
                    {isEmpty && (
                      <Tag color="warning" style={{ margin: 0, fontSize: 10 }}>
                        待填写
                      </Tag>
                    )}
                    <Tooltip title="删除">
                      <Button
                        size="small"
                        type="text"
                        disabled={disabled}
                        onClick={(e) => {
                          e.stopPropagation()
                          removeAnnotation(item.id)
                        }}
                        icon={<DeleteOutlined />}
                        style={{ color: '#f87171' }}
                      />
                    </Tooltip>
                  </div>
                  <TextArea
                    data-annotation-input={item.id}
                    value={item.comment}
                    disabled={disabled}
                    maxLength={MAX_COMMENT_LEN}
                    autoSize={{ minRows: 2, maxRows: 6 }}
                    placeholder={isEmpty ? '写下想改什么' : `第 ${numbering.get(item.id)} 处想改成什么？`}
                    onChange={(e) => updateComment(item.id, e.target.value)}
                    onFocus={() => onActiveChange?.(item.id)}
                  />
                </div>
              )
            })}
          </Space>
        )}
      </div>

      {annotations.length > 0 && writtenCount < annotations.length && (
        <div
          style={{
            marginTop: 10,
            padding: '10px 12px',
            borderRadius: 8,
            background: '#14142a',
            border: '1px solid #2a2a4e',
            flex: '0 0 auto',
          }}
        >
          <Text style={{ color: '#8b8ba8', fontSize: 11, display: 'block', marginBottom: 6 }}>
            点一个示例，填进选中的批注：
          </Text>
          <Space wrap size={[6, 6]}>
            {SAMPLES.map((sample) => (
              <Tag
                key={sample}
                color="purple"
                style={{ cursor: 'pointer', margin: 0 }}
                onClick={() => {
                  const target =
                    annotations.find((a) => a.id === activeId && !a.comment.trim()) ||
                    annotations.find((a) => !a.comment.trim())
                  if (!target) return
                  updateComment(target.id, sample)
                  onActiveChange?.(target.id)
                }}
              >
                {sample}
              </Tag>
            ))}
          </Space>
        </div>
      )}

      {annotations.length - writtenCount > 0 && (
        <Text style={{ color: '#fbbf24', fontSize: 11, marginTop: 6, flex: '0 0 auto' }}>
          还有 {annotations.length - writtenCount} 条没写意见，只圈不写的不会生效。
        </Text>
      )}
    </div>
  )
}