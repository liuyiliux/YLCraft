/**
 * Telegram 账号登录（MTProto）
 *
 * ## 为什么单独一页（而不是塞进账号中心）
 *
 * 其它平台是"抓一次 cookie"（一次性动作），而 Telegram 是
 * **多步状态机**：
 *
 *     api_id/api_hash → 手机号 → 发验证码 → 提交验证码
 *                                      ↘ 开了两步验证 → 再提交密码
 *
 * 塞进账号中心的 cookie 流程会把那套 UI 搞乱（要按钮变来变去）。
 * 单独一页可以把每一步讲清楚。
 *
 * ## ⚠️ 先说清楚：这一步**不是必需的**
 *
 * Telegram 的**公开频道不需要登录**（`t.me/s`，含频道内关键词搜索）——
 * 在「采集」页选 Telegram 就能直接用。
 *
 * 登录后**额外**获得：
 *   · 在**你已加入的**频道/群组里搜关键词
 *   · 列出你加入的频道
 *   · 读取**私有频道**
 *
 * ⚠️ **注意**：它**不是**"全网搜索" —— Telegram 的
 * `messages.SearchGlobal` 只覆盖你已加入的会话。
 * 真正搜所有公开频道要 Premium 且按 Stars 计费，本项目不做。
 */
import { useEffect, useState } from 'react'
import {
  Card, Form, Input, Button, Steps, Alert, Space, Typography, Tag,
  Descriptions, Result, message, Divider,
} from 'antd'
import {
  SendOutlined, CheckCircleOutlined, SafetyCertificateOutlined,
  ReloadOutlined, LogoutOutlined,
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import {
  getTelegramStatus, telegramSendCode, telegramSignIn, telegramLogout,
  type TelegramStatusResponse,
} from '../../api'

const { Title, Paragraph, Text, Link } = Typography

export default function TelegramLoginPage() {
  const navigate = useNavigate()
  const [status, setStatus] = useState<TelegramStatusResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [step, setStep] = useState(0)          // 0=填凭证 1=填验证码 2=完成
  const [needsPassword, setNeedsPassword] = useState(false)
  const [phone, setPhone] = useState('')
  const [form] = Form.useForm()

  const refresh = async () => {
    try {
      const st = await getTelegramStatus()
      setStatus(st)
      if (st.logged_in) setStep(2)
      setNeedsPassword(Boolean(st.needs_password))
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '查询状态失败')
    }
  }

  useEffect(() => { refresh() }, [])

  /** 第一步：发验证码 */
  const handleSendCode = async (values: any) => {
    setLoading(true)
    try {
      await telegramSendCode({
        api_id: String(values.api_id || '').trim(),
        api_hash: String(values.api_hash || '').trim(),
        phone: String(values.phone || '').trim(),
      })
      setPhone(String(values.phone || '').trim())
      setStep(1)
      setNeedsPassword(false)
      message.success('验证码已发送 —— 请查看你已登录的 Telegram 客户端')
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '发送失败')
    } finally {
      setLoading(false)
    }
  }

  /** 第二步：提交验证码（必要时带两步验证密码） */
  const handleSignIn = async (values: any) => {
    setLoading(true)
    try {
      const res = await telegramSignIn({
        code: String(values.code || '').trim(),
        password: String(values.password || ''),
      })
      if (res?.needs_password) {
        // 账号开了两步验证 —— 让用户补密码
        setNeedsPassword(true)
        message.warning('该账号开启了两步验证，请填写密码后再次提交')
      } else {
        message.success(`登录成功${res?.username ? `：@${res.username}` : ''}`)
        setStep(2)
        await refresh()
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = async () => {
    setLoading(true)
    try {
      await telegramLogout()
      message.success('已退出 Telegram')
      setStep(0)
      setNeedsPassword(false)
      form.resetFields()
      await refresh()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '退出失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ maxWidth: 860, margin: '0 auto', padding: 24 }}>
      <Title level={3}>
        <SendOutlined style={{ color: '#0088cc', marginRight: 8 }} />
        Telegram 账号登录
      </Title>

      {/* ⚠️ 最重要的一段：先说清楚"不登录也能用"，避免用户白折腾 */}
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="这一步是可选的 —— 公开频道不需要登录"
        description={
          <div>
            <Paragraph style={{ marginBottom: 6 }}>
              在「采集」页选 Telegram 就能直接抓<Text strong>公开频道</Text>
              （含<Text strong>频道内关键词搜索</Text>），<Text strong>不需要登录</Text>。
            </Paragraph>
            <Paragraph style={{ marginBottom: 6 }}>登录后额外获得：</Paragraph>
            <ul style={{ marginBottom: 6, paddingLeft: 20 }}>
              <li>在<Text strong>你已加入的</Text>频道/群组里搜关键词</li>
              <li>列出你加入的频道（一键采集）</li>
              <li>读取<Text strong>私有频道</Text></li>
            </ul>
            <Text type="warning">
              ⚠️ 注意：这<Text strong>不是「全网搜索」</Text> —— Telegram 的关键词搜索
              只覆盖你已加入的会话。真正搜所有公开频道需要 Premium 且按 Stars 计费，
              本项目不做。
            </Text>
          </div>
        }
      />

      <Steps
        current={step}
        size="small"
        style={{ marginBottom: 20 }}
        items={[
          { title: 'API 凭证' },
          { title: '手机号验证' },
          { title: '完成' },
        ]}
      />

      {/* ===== 已登录 ===== */}
      {status?.logged_in && step === 2 ? (
        <Card>
          <Result
            status="success"
            icon={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
            title="已登录 Telegram"
            subTitle={
              <Descriptions column={1} size="small" style={{ maxWidth: 420, margin: '0 auto' }}>
                <Descriptions.Item label="账号">
                  {status.display_name || '-'}
                  {status.username ? <Tag color="blue" style={{ marginLeft: 8 }}>@{status.username}</Tag> : null}
                </Descriptions.Item>
                <Descriptions.Item label="User ID">{status.user_id || '-'}</Descriptions.Item>
                <Descriptions.Item label="api_id">{status.api_id || '-'}</Descriptions.Item>
              </Descriptions>
            }
            extra={[
              <Button key="crawler" type="primary" onClick={() => navigate('/crawler?platform=telegram')}>
                去采集
              </Button>,
              <Button key="logout" danger icon={<LogoutOutlined />} loading={loading} onClick={handleLogout}>
                退出登录
              </Button>,
            ]}
          />
        </Card>
      ) : step === 0 ? (
        /* ===== 第一步：API 凭证 + 手机号 ===== */
        <Card>
          <Alert
            type="warning"
            showIcon
            style={{ marginBottom: 16 }}
            message="先申请 API 凭证（免费，2 分钟）"
            description={
              <div>
                <Paragraph style={{ marginBottom: 6 }}>
                  1. 打开 <Link href="https://my.telegram.org" target="_blank" rel="noreferrer">my.telegram.org</Link>
                  ，用你的 Telegram 手机号登录
                </Paragraph>
                <Paragraph style={{ marginBottom: 6 }}>
                  2. 进「API development tools」→ 随便填个 App 名字 → 创建
                </Paragraph>
                <Paragraph style={{ marginBottom: 0 }}>
                  3. 把 <Text code>App api_id</Text> 和 <Text code>App api_hash</Text> 填到下面
                </Paragraph>
              </div>
            }
          />

          <Form form={form} layout="vertical" onFinish={handleSendCode}>
            <Form.Item
              name="api_id"
              label="api_id"
              rules={[{ required: true, message: '请填写 api_id（一串数字）' }]}
            >
              <Input placeholder="例如 12345678" autoComplete="off" />
            </Form.Item>

            <Form.Item
              name="api_hash"
              label="api_hash"
              rules={[{ required: true, message: '请填写 api_hash（32 位字符串）' }]}
              extra="⚠️ api_hash 属于敏感凭证，只保存在本机（backend/data/telegram/），不会上传也不会入库 git"
            >
              <Input.Password placeholder="32 位哈希字符串" autoComplete="off" />
            </Form.Item>

            <Form.Item
              name="phone"
              label="手机号"
              rules={[{ required: true, message: '请填写手机号' }]}
              extra="必须带国家码的国际格式，例如 +8613800138000"
            >
              <Input placeholder="+8613800138000" autoComplete="off" />
            </Form.Item>

            <Space>
              <Button type="primary" htmlType="submit" loading={loading} icon={<SendOutlined />}>
                发送验证码
              </Button>
              <Button onClick={refresh} icon={<ReloadOutlined />}>刷新状态</Button>
            </Space>
          </Form>
        </Card>
      ) : (
        /* ===== 第二步：验证码（+可选两步验证密码） ===== */
        <Card>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message={`验证码已发送到 ${phone || '你的 Telegram'}`}
            description="验证码会出现在**你已登录的 Telegram 客户端**里（不是短信，除非你没装 App）。在 Telegram 的对话列表里找「Telegram」官方账号。"
          />

          <Form layout="vertical" onFinish={handleSignIn}>
            <Form.Item
              name="code"
              label="验证码"
              rules={[{ required: true, message: '请填写验证码' }]}
            >
              <Input placeholder="例如 12345" autoComplete="off" />
            </Form.Item>

            <Form.Item
              name="password"
              label={<span><SafetyCertificateOutlined /> 两步验证密码{needsPassword ? '' : '（未开启则留空）'}</span>}
              extra={needsPassword
                ? '该账号开启了两步验证，必须填写密码'
                : '只有账号开启了两步验证时才需要填'}
            >
              <Input.Password placeholder="两步验证密码" autoComplete="off" />
            </Form.Item>

            <Space>
              <Button type="primary" htmlType="submit" loading={loading}>
                完成登录
              </Button>
              <Button onClick={() => setStep(0)}>返回上一步</Button>
            </Space>
          </Form>
        </Card>
      )}

      <Divider />

      <Card size="small" title="常见问题">
        <Paragraph>
          <Text strong>验证码收不到？</Text>
          <br />
          验证码发到 **Telegram App 里**（官方账号发的消息），不是短信。
          手机上打开 Telegram 就能看到。若仍收不到，返回上一步重新发送。
        </Paragraph>
        <Paragraph style={{ marginBottom: 0 }}>
          <Text strong>有封号风险吗？</Text>
          <br />
          用官方 API 正常使用是安全的。但 Telegram 官方对所有第三方客户端账号会
          「自动置于观察之下」，请<Text strong>不要高频批量操作</Text>
          （程序里已对限流做了可读提示）。
        </Paragraph>
      </Card>
    </div>
  )
}
