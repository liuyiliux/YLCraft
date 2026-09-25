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
  getFanqieBookChapters,
  getFanqieBookDrafts,
  createFanqieDraft,
  fanqieWebUrls,
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

/**
 * 番茄草稿或章节。
 *
 * 两者来自不同接口、字段略有差异：章节用 `item_list`（`index` 是章序），
 * 草稿用 `draft_list`（`index` 恒为 -1）。用 `__isDraft` 标记来源，
 * 便于在下拉里区分展示。
 */
interface FanqieChapter {
  item_id: string
  volume_id?: string
  index: number
  title: string
  word_number?: number
  /** 前端标记：true 表示来自草稿箱（GET /fanqie/book/{id}/drafts） */
  __isDraft?: boolean
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
  const [chapters, setChapters] = useState<FanqieChapter[]>([])
  const [loadingChapters, setLoadingChapters] = useState(false)
  const [creatingDraft, setCreatingDraft] = useState(false)
  const [checking, setChecking] = useState(false)
  const [preflight, setPreflight] = useState<any | null>(null)
  const [statuses, setStatuses] = useState<any[]>([])
  // 当前填写的发布目标 item_id，用于「在番茄打开本章」按钮的可用性判断
  const [itemId, setItemId] = useState<string>('')
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

  /**
   * 从番茄拉取该书已有章节（真实端点，2026-09-25 抓包确认），
   * 供发布时自动填入 item_id / volume_id，替代手动抄 ID。
   * 纯只读，不改动线上任何数据。
   *
   * 同时拉取**草稿箱**：番茄的草稿与章节是同一份数据的两个阶段，
   * 未发布的草稿不会出现在章节列表里。只拉章节会让「往草稿里写字」找不到目标。
   */
  const loadChapters = async () => {
    const connId = form.getFieldValue('conn_id')
    const bookId = form.getFieldValue('book_id')
    if (!connId || !bookId) {
      message.warning('请先选择番茄连接并填写书籍 ID')
      return
    }
    setLoadingChapters(true)
    try {
      const [chapRes, draftRes]: any[] = await Promise.all([
        getFanqieBookChapters(connId, bookId, { size: 100 }),
        getFanqieBookDrafts(connId, bookId, { size: 100 }).catch(() => null),
      ])
      const chapList: FanqieChapter[] = chapRes?.data?.item_list || []
      // ⚠️ 草稿箱字段是 draft_list，不是 item_list
      const draftList: FanqieChapter[] = draftRes?.data?.draft_list || []

      setChapters([
        ...draftList.map((d) => ({ ...d, __isDraft: true })),
        ...chapList.map((c) => ({ ...c, __isDraft: false })),
      ])

      if (chapList.length === 0 && draftList.length === 0) {
        message.info('番茄未返回章节或草稿；可先点下方「打开番茄建章」')
      } else {
        message.success(
          `已拉取 ${draftList.length} 个草稿、${chapList.length} 个章节，可从下拉直接选`,
        )
      }
    } catch (e: any) {
      message.error(e?.message || '拉取章节/草稿列表失败')
    } finally {
      setLoadingChapters(false)
    }
  }

  /** 在番茄网页端打开当前书（新建章节/草稿仍须在那边操作，YLCraft 不越权建章）。 */
  const openFanqie = (target: 'book' | 'chapter' | 'editor', itemId?: string) => {
    const bookId = form.getFieldValue('book_id')
    const bookTitle = form.getFieldValue('book_title') || ''
    if (target !== 'book' && !bookId) {
      message.warning('请先填写书籍 ID')
      return
    }
    const url =
      target === 'book'
        ? fanqieWebUrls.bookManage()
        : target === 'chapter'
          ? fanqieWebUrls.chapterManage(String(bookId), String(bookTitle))
          : fanqieWebUrls.editor(String(bookId), String(itemId || ''), 'modifydraft')
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  /**
   * 让 YLCraft 直接在番茄建一个空草稿并填入 item_id（写入操作，不幂等）。
   *
   * 这是"不用手动建章"的关键：真实端点 POST /api/author/article/new_article/v0/
   * 会返回新分配的 item_id。因为每次调用都会在草稿箱新增一条，所以先二次确认，
   * 且失败不自动重试（避免生成多条草稿）。
   */
  const createDraftOnFanqie = () => {
    const connId = form.getFieldValue('conn_id')
    const bookId = form.getFieldValue('book_id')
    if (!connId || !bookId) {
      message.warning('请先选择番茄连接并填写书籍 ID')
      return
    }
    Modal.confirm({
      title: '在番茄新建一个空草稿？',
      content:
        '这会在你的番茄账号草稿箱里真实新增一条草稿，并自动填入本面板。' +
        '正文不会写入，需要你再点「保存到番茄草稿」。',
      okText: '新建草稿',
      cancelText: '取消',
      onOk: async () => {
        setCreatingDraft(true)
        try {
          const res: any = await createFanqieDraft(connId, bookId)
          const data = res?.data || {}
          if (!data.item_id) throw new Error('番茄未返回 item_id')
          form.setFieldsValue({
            item_id: data.item_id,
            ...(data.volume_id ? { volume_id: data.volume_id } : {}),
          })
          setItemId(data.item_id)
          setPreflight(null)
          message.success(`已在番茄新建草稿：${data.item_id}`)
        } catch (e: any) {
          message.error(e?.message || '新建草稿失败')
        } finally {
          setCreatingDraft(false)
        }
      },
    })
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
      destroyOnHidden
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
            label={`本章番茄发布目标 item_id（第 ${chapterNumber ?? '?'} 章）`}
            name="item_id"
            rules={[{ required: true, message: '必填：选择一个番茄草稿或章节' }]}
            extra="番茄的草稿与章节是同一份数据的两个阶段：草稿只在草稿箱，发布后才进章节列表。点「拉取草稿与章节」可自动填入，无需手抄 ID。"
          >
            <Input
              placeholder="选择下方列表自动填入，或手动粘贴番茄 item_id"
              onChange={(e) => {
                setItemId(e.target.value)
                setPreflight(null)
              }}
            />
          </Form.Item>
          <Space style={{ marginBottom: 12 }} wrap>
            <Button
              size="small"
              type="primary"
              loading={creatingDraft}
              onClick={createDraftOnFanqie}
            >
              让 YLCraft 新建番茄草稿
            </Button>
            <Button size="small" loading={loadingChapters} onClick={() => void loadChapters()}>
              拉取草稿与章节
            </Button>
            <Button size="small" onClick={() => openFanqie('chapter')}>
              打开番茄建章
            </Button>
            <Button
              size="small"
              disabled={!itemId}
              onClick={() => openFanqie('editor', itemId)}
            >
              在番茄打开本章
            </Button>
            {chapters.length > 0 && (
              <Select
                size="small"
                style={{ minWidth: 300 }}
                placeholder="选择番茄草稿或章节（自动填 item_id 与卷）"
                value={undefined}
                options={chapters.map((c: any) => ({
                  label: c.__isDraft
                    ? `【草稿】${c.title || '未命名草稿'}（${c.word_number}字）`
                    : `第${c.index}章 ${c.title}（${c.word_number}字）`,
                  value: c.item_id,
                }))}
                onChange={(pickedId) => {
                  const picked: any = chapters.find((c: any) => c.item_id === pickedId)
                  if (!picked) return
                  form.setFieldsValue({
                    item_id: picked.item_id,
                    ...(picked.volume_id ? { volume_id: picked.volume_id } : {}),
                  })
                  setItemId(picked.item_id)
                  setPreflight(null)
                  message.success(
                    picked.__isDraft
                      ? `已填入草稿：${picked.title || '未命名草稿'}（保存后可在番茄点「下一步」发布）`
                      : `已填入第${picked.index}章：${picked.title}`,
                  )
                }}
              />
            )}
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
