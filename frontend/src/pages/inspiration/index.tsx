/**
 * InspirationPage — 番茄热榜灵感 → 转创作项目选题
 *
 * 链路：
 *   选番茄连接（PlatformConnection, cookie）→ GET /fanqie/hot-list（只读灵感列表）
 *     → 每张卡片「转为创作选题」→ POST /creative-projects（source_type=fanqie_hot）
 *       → 跳转到 /story 创作项目工作台。
 *
 * 安全：全程只读拉取热榜，绝不改动用户线上数据；cookie 仅走现有 PlatformConnection。
 */
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd'
import {
  BulbOutlined,
  FireOutlined,
  LinkOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { createCreativeProject, getFanqieHotList, listPlatformConnections } from '../../api'

const { Title, Paragraph, Text } = Typography

type Conn = {
  id: string
  name: string
  platform: string
  account_name?: string
}

type HotItem = {
  book_id?: string
  book_name?: string
  title?: string
  name?: string
  author?: string
  category?: string[]
  content?: string
  desc?: string
  summary?: string
  word_number?: number | string
  thumb_url?: string
  cover_url?: string
  video_url?: string
}

function bestTitle(item: HotItem): string {
  return (item.book_name || item.title || item.name || '未命名灵感').trim()
}

function bestIdea(item: HotItem): string {
  return (item.content || item.desc || item.summary || '').toString().trim()
}

export default function InspirationPage() {
  const navigate = useNavigate()
  const [conns, setConns] = useState<Conn[]>([])
  const [connId, setConnId] = useState<string>()
  const [loadingConns, setLoadingConns] = useState(false)
  const [items, setItems] = useState<HotItem[]>([])
  const [loaded, setLoaded] = useState(false)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState<string>()
  const [convertItem, setConvertItem] = useState<HotItem | null>(null)
  const [converting, setConverting] = useState(false)
  const [form] = Form.useForm()

  useEffect(() => {
    setLoadingConns(true)
    listPlatformConnections()
      .then((res: any) => {
        const list: Conn[] = (res?.data || []).filter(
          (c: Conn) => c.platform === 'fanqie',
        )
        setConns(list)
        if (list.length && !connId) setConnId(list[0].id)
      })
      .catch(() => setConns([]))
      .finally(() => setLoadingConns(false))
  }, [])

  const loadHot = useCallback(async () => {
    if (!connId) {
      setErr('请先在「账号中心」创建一个番茄小说连接（保存你的作家后台 cookie）。')
      return
    }
    setLoading(true)
    setErr(undefined)
    try {
      const res: any = await getFanqieHotList(connId, 0)
      const data = res?.data || {}
      const list: HotItem[] = data.item_list || []
      setItems(list)
      setLoaded(true)
      if (!list.length) {
        setErr('热榜返回为空（可能 cookie 已失效，或当前榜单暂无数据）。')
      }
    } catch (e: any) {
      setErr(e?.message || '加载热榜失败')
    } finally {
      setLoading(false)
    }
  }, [connId])

  const openConvert = (item: HotItem) => {
    form.setFieldsValue({
      title: bestTitle(item),
      project_type: 'novel',
    })
    setConvertItem(item)
  }

  const doConvert = async () => {
    if (!convertItem) return
    const v = await form.validateFields()
    setConverting(true)
    try {
      const res: any = await createCreativeProject({
        title: v.title,
        idea: bestIdea(convertItem),
        project_type: v.project_type,
        source_type: 'fanqie_hot',
        source_ref: {
          book_id: convertItem.book_id || '',
          book_name: bestTitle(convertItem),
          author: convertItem.author || '',
          category: convertItem.category || [],
          thumb_url: convertItem.thumb_url || convertItem.cover_url || '',
        },
      })
      message.success('已创建创作选题，前往「创作项目」开始写作')
      setConvertItem(null)
      navigate('/story')
    } catch (e: any) {
      message.error(e?.message || '创建选题失败')
    } finally {
      setConverting(false)
    }
  }

  const renderCard = (item: HotItem, idx: number) => {
    const title = bestTitle(item)
    const idea = bestIdea(item)
    const cover = item.thumb_url || item.cover_url
    const category = item.category || []
    return (
      <Col key={item.book_id || idx} xs={24} sm={12} lg={8} xxl={6}>
        <Card
          hoverable
          cover={
            cover ? (
              <div
                style={{
                  height: 168,
                  background: '#f0f2f5 center/cover no-repeat',
                  backgroundImage: `url(${cover})`,
                }}
              />
            ) : (
              <div
                style={{
                  height: 168,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: 'linear-gradient(135deg,#fff7e6,#fff1f0)',
                  color: '#fa8c16',
                  fontSize: 40,
                }}
              >
                <FireOutlined />
              </div>
            )
          }
          actions={[
            <Button
              key="convert"
              type="link"
              icon={<BulbOutlined />}
              onClick={() => openConvert(item)}
              disabled={!connId}
            >
              转为创作选题
            </Button>,
          ]}
        >
          <Card.Meta
            title={
              <Text ellipsis={{ tooltip: title }} style={{ width: '100%' }}>
                {title}
              </Text>
            }
            description={
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                {item.author ? <Text type="secondary">作者：{item.author}</Text> : null}
                <Space size={[4, 4]} wrap>
                  {category.slice(0, 4).map((c, i) => (
                    <Tag key={i} color="orange">
                      {c}
                    </Tag>
                  ))}
                </Space>
                {item.word_number ? (
                  <Text type="secondary">约 {item.word_number} 字</Text>
                ) : null}
                <Paragraph
                  type="secondary"
                  ellipsis={{ rows: 3, tooltip: idea }}
                  style={{ marginBottom: 0, fontSize: 13 }}
                >
                  {idea || '（暂无摘要）'}
                </Paragraph>
              </Space>
            }
          />
        </Card>
      </Col>
    )
  }

  return (
    <div style={{ padding: 24, maxWidth: 1400, margin: '0 auto' }}>
      <Space align="center" size={10}>
        <FireOutlined style={{ fontSize: 26, color: '#fa541c' }} />
        <Title level={3} style={{ margin: 0 }}>
          番茄热榜灵感
        </Title>
      </Space>
      <Paragraph type="secondary" style={{ marginTop: 8 }}>
        从番茄作家后台的热门故事中挖掘开书灵感，一键把它变成 YLCraft 的创作项目选题，
        继而用工作台的大纲 / 正文 / 发布番茄流水线完成创作。
      </Paragraph>

      <Space wrap style={{ marginBottom: 16 }}>
        <Select
          style={{ width: 280 }}
          placeholder="选择番茄小说连接"
          loading={loadingConns}
          value={connId}
          onChange={setConnId}
          options={conns.map((c) => ({
            value: c.id,
            label: `${c.name}${c.account_name ? `（${c.account_name}）` : ''}`,
          }))}
          notFoundContent="未找到番茄连接"
        />
        <Button
          type="primary"
          icon={<ReloadOutlined />}
          loading={loading}
          onClick={loadHot}
          disabled={!connId}
        >
          加载热榜
        </Button>
        <Button icon={<LinkOutlined />} onClick={() => navigate('/accounts')}>
          去账号中心建连接
        </Button>
      </Space>

      {!conns.length && !loadingConns ? (
        <Alert
          type="info"
          showIcon
          message="尚未配置番茄小说连接"
          description="番茄热榜需要你的作家后台 cookie。请点击「去账号中心建连接」创建一个 platform=fanqie、auth_type=cookie 的连接并保存 cookie，再回来加载热榜。"
          action={
            <Button size="small" type="primary" onClick={() => navigate('/accounts')}>
              前往
            </Button>
          }
        />
      ) : null}

      {err ? (
        <Alert type="warning" showIcon message="未能加载热榜" description={err} style={{ marginBottom: 16 }} />
      ) : null}

      {loading ? (
        <div style={{ textAlign: 'center', padding: 64 }}>
          <Spin tip="正在拉取热门故事…" />
        </div>
      ) : loaded && !items.length && !err ? (
        <Empty description="该连接暂无热榜数据" />
      ) : items.length ? (
        <Row gutter={[16, 16]}>
          {items.map((item, idx) => renderCard(item, idx))}
        </Row>
      ) : null}

      <Modal
        title="转为创作选题"
        open={!!convertItem}
        onCancel={() => setConvertItem(null)}
        onOk={doConvert}
        confirmLoading={converting}
        okText="创建并前往创作"
        cancelText="取消"
        destroyOnClose
      >
        {convertItem ? (
          <Form form={form} layout="vertical">
            <Form.Item label="灵感来源">
              <Text type="secondary">{bestTitle(convertItem)}</Text>
            </Form.Item>
            <Form.Item
              label="选题标题"
              name="title"
              rules={[{ required: true, message: '请填写选题标题' }]}
            >
              <Input placeholder="创作项目标题" maxLength={120} />
            </Form.Item>
            <Form.Item label="项目类型" name="project_type" initialValue="novel">
              <Select
                options={[
                  { value: 'novel', label: '小说' },
                  { value: 'short_drama', label: '短剧' },
                ]}
              />
            </Form.Item>
            <Form.Item label="灵感摘要（将写入项目 idea）">
              <Input.TextArea
                value={bestIdea(convertItem)}
                autoSize={{ minRows: 3, maxRows: 6 }}
                readOnly
              />
            </Form.Item>
            <Alert
              type="info"
              showIcon
              message="创建后将在「创作项目」生成新项目，来源标记为番茄热榜，可继续写大纲与正文，并一键保存到番茄草稿。"
            />
          </Form>
        ) : null}
      </Modal>
    </div>
  )
}
