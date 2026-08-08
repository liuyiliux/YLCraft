/**
 * YLCraft — 创作项目 → 番茄小说 发布面板
 *
 * 在 /story 工作台「正文」区弹出，把当前章节 novel_body 正文推送到番茄作家后台。
 * 约定：番茄的建书/建卷/建章节仍在 Web 端完成；此处只推正文到对应 item_id（存草稿）。
 */
import React, { useEffect, useState } from 'react'
import {
  Modal,
  Form,
  Select,
  Input,
  Button,
  message,
  Tag,
  Spin,
  Alert,
  Space,
  Typography,
  List,
} from 'antd'
import {
  listPlatformConnections,
  getFanqieBinding,
  setFanqieBinding,
  previewFanqiePublish,
  publishChapterToFanqie,
  getFanqiePublishStatus,
} from '../../api'

interface Props {
  projectId: string
  contentId: string
  chapterNumber?: number
  chapterTitle?: string
  visible: boolean
  onClose: () => void
}

interface ConnOption {
  id: string
  name: string
}

export default function FanqiePublishPanel({
  projectId,
  contentId,
  chapterNumber,
  chapterTitle,
  visible,
  onClose,
}: Props) {
  const [connections, setConnections] = useState<ConnOption[]>([])
  const [binding, setBinding] = useState<Record<string, any>>({})
  const [loadingBinding, setLoadingBinding] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [checking, setChecking] = useState(false)
  const [preflight, setPreflight] = useState<any | null>(null)
  const [statuses, setStatuses] = useState<any[]>([])
  const [form] = Form.useForm()

  const loadConnections = async () => {
    try {
      const res: any = await listPlatformConnections()
      const conns = (res?.data?.connections || res?.connections || []) as any[]
      setConnections(
        conns
          .filter((c) => (c.platform || '').toLowerCase() === 'fanqie')
          .map((c) => ({ id: c.id, name: c.name || c.account_name || c.id })),
      )
    } catch {
      /* 忽略：连接列表不影响表单 */
    }
  }

  const loadBinding = async () => {
    setLoadingBinding(true)
    try {
      const res: any = await getFanqieBinding(projectId)
      const b = res?.data || {}
      setBinding(b)
      form.setFieldsValue({
        conn_id: b.conn_id,
        book_id: b.book_id,
        volume_id: b.volume_id,
        volume_name: b.volume_name,
      })
    } finally {
      setLoadingBinding(false)
    }
  }

  const loadStatus = async () => {
    try {
      const res: any = await getFanqiePublishStatus(projectId, chapterNumber)
      setStatuses(res?.data || [])
    } catch {
      /* 忽略 */
    }
  }

  useEffect(() => {
    if (visible) {
      loadConnections()
      loadBinding()
      loadStatus()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, projectId, chapterNumber])

  const onSaveBinding = async () => {
    try {
      const v = await form.validateFields(['conn_id', 'book_id', 'volume_id', 'volume_name'])
      await setFanqieBinding(projectId, v)
      setBinding(v)
      message.success('番茄绑定已保存')
    } catch (e: any) {
      if (e?.message) message.error(e.message)
    }
  }

  const runPreflight = async (values?: any) => {
    let v = values
    if (!v) {
      try {
        v = await form.validateFields()
      } catch {
        return null
      }
    }
    setChecking(true)
    try {
      const res: any = await previewFanqiePublish(projectId, {
        content_id: contentId,
        item_id: v.item_id,
        conn_id: v.conn_id,
        book_id: v.book_id,
        volume_id: v.volume_id,
        volume_name: v.volume_name,
      })
      const next = res?.data || null
      setPreflight(next)
      if (next?.ready) message.success('发布条件已通过本地预检')
      else message.warning(`发布条件未满足：${(next?.missing || []).join('、') || '请检查目标信息'}`)
      return next
    } catch (e: any) {
      message.error(e?.message || '发布预检失败')
      return null
    } finally {
      setChecking(false)
    }
  }

  const onSaveDraft = async () => {
    let v: any
    try {
      v = await form.validateFields()
    } catch {
      return
    }
    const preview = await runPreflight(v)
    if (!preview?.ready) return
    setPublishing(true)
    try {
      const res: any = await publishChapterToFanqie(projectId, {
        conn_id: v.conn_id,
        book_id: v.book_id,
        volume_id: v.volume_id,
        volume_name: v.volume_name,
        chapters: [
          {
            content_id: contentId,
            item_id: v.item_id,
            chapter_number: chapterNumber,
            title: chapterTitle,
          },
        ],
      })
      const d = res?.data || {}
      if (d.failed > 0) message.warning(`草稿保存完成：${d.success} 成功 / ${d.failed} 失败`)
      else message.success(`已将 ${d.success} 章保存到番茄草稿`)
      loadStatus()
    } catch (e: any) {
      message.error(e?.message || '发布失败')
    } finally {
      setPublishing(false)
    }
  }

  return (
    <Modal
      title="保存到番茄草稿"
      open={visible}
      onCancel={onClose}
      onOk={onSaveDraft}
      okText="保存草稿"
      confirmLoading={publishing}
      width={580}
      destroyOnClose
    >
      <Spin spinning={loadingBinding}>
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="番茄的建书 / 建卷 / 建章节请在 Web 端完成；此处仅把 YLCraft 正文推送到对应章节（存草稿）。"
        />
        <Form form={form} layout="vertical" onValuesChange={() => setPreflight(null)}>
          <Form.Item
            label="番茄连接（cookie 凭证）"
            name="conn_id"
            rules={[{ required: true, message: '请选择番茄连接' }]}
          >
            <Select
              placeholder="选择 fanqie 连接（在平台管理里添加 cookie）"
              options={connections.map((c) => ({ label: c.name, value: c.id }))}
              notFoundContent="未找到 fanqie 连接，请先在「平台管理」添加"
            />
          </Form.Item>
          <Form.Item label="书籍 ID (book_id)" name="book_id" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="番茄 Web 端书籍 ID" />
          </Form.Item>
          <Form.Item label="卷 ID (volume_id)" name="volume_id" rules={[{ required: true, message: '必填' }]}>
            <Input placeholder="番茄卷 ID" />
          </Form.Item>
          <Form.Item label="卷名 (volume_name)" name="volume_name">
            <Input placeholder="如：第一卷" />
          </Form.Item>
          <Form.Item
            label={`本章番茄章节 item_id（第 ${chapterNumber ?? '?'} 章）`}
            name="item_id"
            rules={[{ required: true, message: '必填：Web 端已建好的章节 ID' }]}
          >
            <Input placeholder="仅填写已在番茄 Web 手动创建的独立 [TEST] 章节 item_id" onChange={() => setPreflight(null)} />
          </Form.Item>
          <Space>
            <Button onClick={onSaveBinding}>保存绑定</Button>
            <Button loading={checking} onClick={() => void runPreflight()}>
              检查发布条件
            </Button>
            {binding && binding.conn_id && <Tag color="green">已绑定</Tag>}
          </Space>
        </Form>

        {preflight && (
          <Alert
            style={{ marginTop: 12 }}
            type={preflight.ready ? 'success' : 'warning'}
            showIcon
            message={preflight.ready ? '本地预检通过，可保存到指定草稿章节' : '本地预检未通过'}
            description={
              preflight.ready
                ? `目标：书籍 ${preflight.resolved_target?.book_id} / 卷 ${preflight.resolved_target?.volume_id} / item ${preflight.resolved_target?.item_id}`
                : `缺少或不匹配：${(preflight.missing || []).join('、')}`
            }
          />
        )}

        <Typography.Title level={5} style={{ marginTop: 16 }}>
          发布记录
        </Typography.Title>
        <List
          size="small"
          dataSource={statuses}
          locale={{ emptyText: '暂无发布记录' }}
          renderItem={(s: any) => (
            <List.Item>
              <Space>
                <Tag color={s.status === 'success' ? 'green' : s.status === 'failed' ? 'red' : 'default'}>
                  {s.status}
                </Tag>
                <span>
                  第 {s.chapter_number} 章 → item {s.item_id}
                </span>
                {s.remote_version != null && <Tag color="blue">v{s.remote_version}</Tag>}
                {s.error_message && <span style={{ color: '#cf1322' }}>{s.error_message}</span>}
              </Space>
            </List.Item>
          )}
        />
      </Spin>
    </Modal>
  )
}
