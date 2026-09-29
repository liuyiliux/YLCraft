/**
 * 创作者中心数据面板（抖音 / 小红书）
 *
 * ## 为什么单独做这个
 *
 * 「我的数据」页原有的内容来自普通站接口（`/users/me`），
 * 那只是**公开数据** —— 粉丝数、获赞数，别人也看得到。
 *
 * **创作者中心**（`creator.douyin.com` / `creator.xiaohongshu.com`）
 * 才有**只有号主能看**的运营数据：
 *
 *     曝光数 / 观看量 / 主页访问 / 完播率 / 2 秒跳出
 *     平均观看时长 / 净增粉丝 / 取关 / 搜索来源 …
 *
 * ## 实测（2026-09-29，与创作者后台页面完全一致）
 *
 *     小红书  曝光 759（+96%）观看 157（+503%）封面点击率 4.4%
 *             完播率 3.4% 主页访客 9（-40%）净涨粉 1
 *     抖音    播放 16（+8）主页访问 1（+1）点赞 1（+1）粉丝 854
 *
 * ## ⚠️ 登录态要求
 *
 * 两个平台的创作者中心都**复用主站登录态**，不需要单独登录。
 * 但**过期的 session 依然存在** —— 若报 401，需要重新扫码：
 *   小红书 → 会出现"电脑设备登录超限，请重新登录"
 *   抖音   → 会出现"登录已过期"
 */
import { useState, useEffect, useCallback } from 'react'
import {
  Card, Row, Col, Statistic, Table, Tag, Space, Typography, Empty,
  Spin, Button, Segmented, Tooltip, Alert, message,
} from 'antd'
import {
  RiseOutlined, FallOutlined, ReloadOutlined, BarChartOutlined,
  EyeOutlined, TeamOutlined, ThunderboltOutlined,
} from '@ant-design/icons'
import {
  getDouyinCreatorOverview, getDouyinCreatorWorks,
  getXhsCreatorOverview, getXhsCreatorFans,
} from '../../api'
import { useTheme } from '../../constants/theme'

const { Text } = Typography

/** 一个指标卡片（数值 + 环比 + 可选单位） */
interface MetricCard {
  key: string
  label: string
  value: number
  /** 是否比率（前端加 %） */
  isRate?: boolean
  /** 环比（%） */
  rate?: number | null
}

function formatNum(v: number | null | undefined): string {
  const n = Number(v || 0)
  if (Math.abs(n) >= 100000000) return `${(n / 100000000).toFixed(2)}亿`
  if (Math.abs(n) >= 10000) return `${(n / 10000).toFixed(1)}万`
  return String(n)
}

/**
 * 环比标签。
 *
 * ⚠️ **环比为 0 或缺失时不显示** —— 显示"+0%"没有信息量，
 * 还会让人以为"数据没变"（实际是"没有对比数据"）。
 */
function RateTag({ rate, theme }: { rate?: number | null; theme: any }) {
  if (rate === null || rate === undefined) return null
  const n = Number(rate)
  if (!Number.isFinite(n) || n === 0) return null
  const up = n > 0
  return (
    <Text style={{ fontSize: 12, color: up ? '#22c55e' : '#ef4444', marginLeft: 6 }}>
      {up ? <RiseOutlined /> : <FallOutlined />} {up ? '+' : ''}{n.toFixed(0)}%
    </Text>
  )
}

export default function CreatorCenterPanel({ platform }: { platform: string }) {
  const { theme: THEME } = useTheme()
  const isXhs = platform === 'xiaohongshu'

  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')
  const [period, setPeriod] = useState<'seven' | 'thirty'>('seven')
  const [days, setDays] = useState<7 | 15 | 30>(7)
  const [metrics, setMetrics] = useState<MetricCard[]>([])
  const [summary, setSummary] = useState('')
  const [fans, setFans] = useState<any>(null)
  const [works, setWorks] = useState<any[]>([])

  const load = useCallback(async () => {
    setLoading(true); setErr(''); setMetrics([]); setSummary(''); setFans(null); setWorks([])
    try {
      if (isXhs) {
        const [ov, f] = await Promise.all([
          getXhsCreatorOverview(period),
          getXhsCreatorFans(period),
        ])
        const m = (ov as any)?.data?.metrics || {}
        // 只展示有意义的指标（按截图上的顺序）
        const order = [
          'impl_count', 'view_count', 'cover_click_rate', 'video_full_view_rate',
          'like_count', 'collect_count', 'comment_count', 'share_count',
          'net_rise_fans_count', 'rise_fans_count', 'loss_fans_count',
          'home_view_count', 'avg_view_time', 'danmaku_count',
        ]
        const cards: MetricCard[] = []
        for (const k of order) {
          const v = m[k]
          if (!v) continue
          cards.push({
            key: k, label: v.label, value: v.value,
            isRate: v.is_rate, rate: v.rate,
          })
        }
        setMetrics(cards)
        setSummary(String((ov as any)?.data?.summary || ''))
        setFans((f as any)?.data || null)
      } else {
        const ov = await getDouyinCreatorOverview(days)
        const m = (ov as any)?.data?.metrics || {}
        const order = [
          'play', 'profile', 'digg', 'comment', 'share',
          'new_fans', 'cancel_fans', 'fans',
          'account_search', 'post_search',
        ]
        const cards: MetricCard[] = []
        for (const k of order) {
          const v = m[k]
          if (!v) continue
          cards.push({
            key: k, label: v.label, value: v.total,
            rate: v.period_incr,
          })
        }
        setMetrics(cards)

        // 作品列表（含完播率等深度指标）
        try {
          const w = await getDouyinCreatorWorks(10, 0)
          setWorks(((w as any)?.data?.works || []))
        } catch {
          // 作品列表失败不影响总览展示
        }
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || '加载失败'
      setErr(String(detail))
    } finally {
      setLoading(false)
    }
  }, [platform, period, days, isXhs])

  useEffect(() => { load() }, [load])

  const workColumns = [
    {
      title: '作品', dataIndex: 'title', key: 'title', ellipsis: true,
      render: (t: string, r: any) => (
        <Space size={8}>
          {r.cover && (
            <img
              src={`/api/v1/proxy/image?url=${encodeURIComponent(r.cover)}`}
              alt="" style={{ width: 36, height: 48, objectFit: 'cover', borderRadius: 4 }}
            />
          )}
          <Text style={{ fontSize: 13 }}>{t || '(无标题)'}</Text>
        </Space>
      ),
    },
    { title: '播放', dataIndex: 'play_count', key: 'play_count', width: 80,
      render: (v: number) => formatNum(v) },
    { title: '点赞', dataIndex: 'like_count', key: 'like_count', width: 70,
      render: (v: number) => formatNum(v) },
    {
      // 完播率是创作者中心独有的指标（普通站拿不到）
      title: (
        <Tooltip title="创作者中心独有指标 —— 普通站接口拿不到">
          完播率
        </Tooltip>
      ),
      dataIndex: 'completion_rate', key: 'completion_rate', width: 90,
      render: (v: number) => (v ? `${(Number(v) * 100).toFixed(1)}%` : '-'),
    },
    { title: '均看', dataIndex: 'avg_view_second', key: 'avg_view_second', width: 80,
      render: (v: number) => (v ? `${Number(v).toFixed(1)}s` : '-') },
    { title: '净涨粉', dataIndex: 'subscribe_count', key: 'subscribe_count', width: 80,
      render: (v: number) => formatNum(v) },
  ]

  return (
    <Card
      style={{ background: THEME.bgCard, border: `1px solid ${THEME.border}`, marginTop: 16 }}
      title={
        <Space>
          <BarChartOutlined style={{ color: '#f59e0b' }} />
          <Text strong>创作者中心</Text>
          <Tag color="orange">仅号主可见</Tag>
        </Space>
      }
      extra={
        <Space>
          {isXhs ? (
            <Segmented
              size="small"
              value={period}
              onChange={(v) => setPeriod(v as any)}
              options={[{ label: '近7天', value: 'seven' }, { label: '近30天', value: 'thirty' }]}
            />
          ) : (
            <Segmented
              size="small"
              value={days}
              onChange={(v) => setDays(v as any)}
              options={[{ label: '近7天', value: 7 }, { label: '近15天', value: 15 }, { label: '近30天', value: 30 }]}
            />
          )}
          <Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={load}>
            刷新
          </Button>
        </Space>
      }
    >
      <Spin spinning={loading}>
        {err && (
          <Alert
            type="warning" showIcon style={{ marginBottom: 12 }}
            message="创作者中心数据获取失败"
            description={
              <span style={{ fontSize: 12 }}>
                {err}
                <br />
                提示：创作者中心复用主站登录态。若提示未登录，请到「账号中心」
                重新扫码（过期的登录态在 cookie 里依然存在，所以看起来"已登录"）。
              </span>
            }
          />
        )}

        {!err && metrics.length === 0 && !loading && (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
                没有拿到创作者中心数据
              </Text>
            }
          />
        )}

        {metrics.length > 0 && (
          <>
            {summary && (
              <Alert
                type="info" showIcon style={{ marginBottom: 14 }}
                message={<span style={{ fontSize: 13 }}>{summary}</span>}
              />
            )}

            <Row gutter={[12, 12]}>
              {metrics.map((m) => (
                <Col key={m.key} xs={12} sm={8} md={6} lg={4}>
                  <div style={{
                    padding: '10px 12px',
                    background: THEME.bgElevated || THEME.bgCard,
                    border: `1px solid ${THEME.border}`,
                    borderRadius: 8,
                  }}>
                    <div style={{ fontSize: 12, color: THEME.textSecondary, marginBottom: 4 }}>
                      {m.label}
                    </div>
                    <Space size={0} align="baseline">
                      <Text strong style={{ fontSize: 20 }}>
                        {m.isRate ? Number(m.value).toFixed(1) : formatNum(m.value)}
                      </Text>
                      {m.isRate && (
                        <Text style={{ fontSize: 13, color: THEME.textSecondary }}>%</Text>
                      )}
                      <RateTag rate={m.rate} theme={THEME} />
                    </Space>
                  </div>
                </Col>
              ))}
            </Row>
          </>
        )}

        {/* 小红书：粉丝明细 */}
        {isXhs && fans && (
          <Row gutter={12} style={{ marginTop: 16 }}>
            <Col span={8}>
              <Statistic
                title="新增关注" value={fans.rise_fans_count}
                prefix={<RiseOutlined style={{ color: '#22c55e' }} />}
                valueStyle={{ fontSize: 20 }}
              />
            </Col>
            <Col span={8}>
              <Statistic
                title="取消关注" value={fans.leave_fans_count}
                prefix={<FallOutlined style={{ color: '#ef4444' }} />}
                valueStyle={{ fontSize: 20 }}
              />
            </Col>
            <Col span={8}>
              <Statistic
                title="粉丝总数" value={fans.fans_count}
                prefix={<TeamOutlined />} valueStyle={{ fontSize: 20 }}
              />
            </Col>
          </Row>
        )}

        {/* 抖音：作品表（含完播率等深度指标） */}
        {!isXhs && works.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <Space style={{ marginBottom: 8 }}>
              <ThunderboltOutlined style={{ color: '#f59e0b' }} />
              <Text strong style={{ fontSize: 13 }}>作品深度数据</Text>
              <Text style={{ fontSize: 12, color: THEME.textSecondary }}>
                （完播率 / 平均观看时长只有创作者中心有）
              </Text>
            </Space>
            <Table
              size="small"
              rowKey="id"
              columns={workColumns as any}
              dataSource={works}
              pagination={false}
              scroll={{ x: 640 }}
            />
          </div>
        )}
      </Spin>
    </Card>
  )
}
