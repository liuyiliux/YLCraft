/**
 * 生图提示词预览
 *
 * 回答一个具体问题：**模型最后到底收到了什么？**
 * 图生图下系统会追加标注图说明与批注意见清单，用户只填了主提示词，看不到全貌；
 * 而各家模型对默认文案反应差别很大，必须**可见、可改、可关**。
 *
 * 预览走 `POST /images/prompt-preview`，与真正生成共用后端 `build_effective_prompt`，
 * 所以这里显示的就是会发出去的原文，不存在「预览一套、实际另一套」。
 */

import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Input, Modal, Space, Spin, Tag, Typography, message } from 'antd'
import { ReloadOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { previewImagePrompt, type ImagePromptPreview } from '../../api'

const { Text } = Typography
const { TextArea } = Input

interface Props {
  open: boolean
  onClose: () => void
  prompt: string
  annotations: { comment: string; rectangle: { x1: number; y1: number; x2: number; y2: number } }[]
  markedReference: boolean
  /** 当前生效的标注图说明：undefined = 用默认，'' = 已关闭 */
  hintText: string | undefined
  /**
   * 渲染好的「带框标注图」（data URL），用于在预览里直接展示用户实际会发出去的东西。
   * 为空串表示这一步没做成（纯文字模式 / 渲染失败），预览里会如实说明。
   */
  markedImagePreview: string
  /** 本次实际会发送的参考图张数（用于确认原图与标注图都在） */
  referenceCount: number
  /** 用户在弹窗里改完后回写（保存才生效） */
  onApplyHintText: (value: string | undefined) => void
  /** 是否展示「标注图说明」编辑区——只有真的发了标注图才有意义 */
  showHintEditor: boolean
}

export default function ImagePromptPreviewModal({
  open,
  onClose,
  prompt,
  annotations,
  markedReference,
  hintText,
  markedImagePreview,
  referenceCount,
  onApplyHintText,
  showHintEditor,
}: Props) {
  const [data, setData] = useState<ImagePromptPreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [draftHint, setDraftHint] = useState<string>('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = (await previewImagePrompt({
        prompt,
        annotations,
        annotation_marked_reference: markedReference,
        // undefined → 后端用默认；'' → 明确关闭。其余按用户草稿走。
        annotation_hint_text: draftHint,
      })) as any
      const payload = res?.data ?? res
      setData(payload)
    } catch (e: any) {
      message.error(`预览失败：${e?.message || e}`)
    } finally {
      setLoading(false)
    }
  }, [prompt, annotations, markedReference, draftHint])

  // 打开时按当前生效值初始化草稿；关闭时清掉，避免下次带着上次的残留打开。
  useEffect(() => {
    if (!open) {
      setData(null)
      return
    }
    setDraftHint(hintText ?? '')
  }, [open, hintText])

  useEffect(() => {
    if (open) void load()
    // 草稿变化不自动重拉：用户正在打字，每次按键都打接口没意义。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const hintEnabled = draftHint.trim().length > 0
  const systemKeys = new Set(data?.system_added || [])

  return (
    <Modal
      title={
        <span>
          <ThunderboltOutlined style={{ marginRight: 8, color: '#a855f7' }} />
          提示词预览
        </span>
      }
      open={open}
      onCancel={onClose}
      width={820}
      footer={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => void load()}>
            重新预览
          </Button>
          <Button type="primary" onClick={onClose}>
            关闭
          </Button>
        </Space>
      }
    >
      <Spin spinning={loading}>
        <Alert
          type="info"
          showIcon
          message="下面是模型最终收到的完整提示词"
          description={
            <span style={{ fontSize: 12 }}>
              带 <Tag color="orange" style={{ marginInlineEnd: 4 }}>系统自动添加</Tag>{' '}
              标记的是系统替你加的内容（标注图说明、批注意见清单），不是你自己写的。
            </span>
          }
          style={{ marginBottom: 12 }}
        />

        {/* 实际发送的参考图：让用户直接看见「带框图长什么样、原图在不在」 */}
        {markedReference && (
          <div style={{ marginBottom: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <Text strong style={{ color: '#e2e8f0', fontSize: 13 }}>
                带框标注图（实际发给模型的第 2 张）
              </Text>
              <Tag color="cyan" style={{ margin: 0 }}>
                本次共 {referenceCount} 张参考图
              </Tag>
            </div>
            {markedImagePreview ? (
              <img
                src={markedImagePreview}
                alt="带框标注图预览"
                style={{
                  maxWidth: '100%',
                  maxHeight: 320,
                  objectFit: 'contain',
                  border: '1px solid #333',
                  borderRadius: 6,
                  background: '#0f0f1a',
                }}
              />
            ) : (
              <Alert
                type="warning"
                showIcon
                message="带框图还没有生成"
                description="点右下角「重新预览」会重新渲染；仍然失败通常是因为参考图来自外站（跨域无法导出）。"
              />
            )}
            <Text style={{ color: '#6b6b8a', fontSize: 11, display: 'block', marginTop: 4 }}>
              这就是模型会看到的第二张图：与原图内容一致，只多了青框与编号，仅用于定位。
            </Text>
          </div>
        )}

        {/* 分块展示：让用户一眼看出哪段是自己写的、哪段是系统加的 */}
        {data?.blocks?.length ? (
          <div style={{ marginBottom: 14 }}>
            {data.blocks.map((block) => {
              const isSystem = systemKeys.has(block.key)
              return (
                <div
                  key={block.key}
                  style={{
                    marginBottom: 10,
                    padding: '8px 10px',
                    borderRadius: 6,
                    border: `1px solid ${isSystem ? '#7c3aed' : '#333'}`,
                    background: isSystem ? 'rgba(124,58,237,0.06)' : '#1a1a2e',
                  }}
                >
                  <Space size={6} style={{ marginBottom: 4 }}>
                    <Text strong style={{ color: '#e2e8f0', fontSize: 12 }}>
                      {block.label}
                    </Text>
                    {isSystem && (
                      <Tag color="orange" style={{ margin: 0, fontSize: 10 }}>
                        系统自动添加
                      </Tag>
                    )}
                  </Space>
                  <div style={{ color: '#cbd5e1', fontSize: 12, whiteSpace: 'pre-wrap' }}>
                    {block.content}
                  </div>
                </div>
              )
            })}
          </div>
        ) : null}

        {/* 最终全文：便于整体复制出去对照 */}
        <Text style={{ color: '#8b8ba8', fontSize: 12 }}>
          最终发送的完整内容：
        </Text>
        <TextArea
          readOnly
          value={data?.prompt || ''}
          autoSize={{ minRows: 6, maxRows: 14 }}
          style={{ marginTop: 6, fontFamily: 'monospace', fontSize: 12 }}
        />

        {/* 标注图说明可编辑：不同模型对这句话反应差别很大，必须让用户能改、能关 */}
        {showHintEditor && (
          <div style={{ marginTop: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <Text strong style={{ color: '#e2e8f0', fontSize: 13 }}>
                标注图说明（默认拼接的那段）
              </Text>
              <Tag color={hintEnabled ? 'cyan' : 'default'} style={{ margin: 0 }}>
                {hintEnabled ? '已启用' : '已关闭'}
              </Tag>
              <Button
                size="small"
                type="text"
                style={{ color: '#8b8ba8' }}
                onClick={() => {
                  setDraftHint(data?.default_hint_text || '')
                  message.info('已填回默认文案，保存后生效')
                }}
              >
                恢复默认
              </Button>
            </div>
            <TextArea
              value={draftHint}
              onChange={(e) => setDraftHint(e.target.value)}
              autoSize={{ minRows: 3, maxRows: 8 }}
              placeholder="留空表示不要这段说明"
              style={{ fontSize: 12 }}
            />
            <Text style={{ color: '#6b6b8a', fontSize: 11, display: 'block', marginTop: 4 }}>
              例如「只改框选的地方，其他部分保持不变」「不要把框线画进结果」。
              留空即完全不加这句。
            </Text>
            <div style={{ marginTop: 10 }}>
              <Button
                type="primary"
                size="small"
                onClick={() => {
                  // 空串是「明确关闭」，undefined 是「用默认」——两者语义不同，不能混。
                  onApplyHintText(draftHint.trim() ? draftHint : undefined)
                  onClose()
                }}
              >
                保存并应用
              </Button>
            </div>
          </div>
        )}
      </Spin>
    </Modal>
  )
}