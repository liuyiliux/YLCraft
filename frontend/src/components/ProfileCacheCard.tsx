/**
 * 采集浏览器 profile 缓存管理卡片（2026-10-03）
 *
 * ## 为什么需要这个
 *
 * `backend/data/browser_profiles/<平台>/` 是**持久化 profile**，每次采集都
 * 复用同一份磁盘目录，只增不减，也没有任何东西会回收它。实测 9 个平台合计
 * **724MB**，其中约 **94% 是可丢弃的加速副本**（真实登录态只有几十 KB）。
 *
 * 原始体积构成（xhs 419MB 实测）：
 *   Default/Cache        377.5MB  ← 241MB WebP 封面 + 8MB JPEG + 4.5MB gzip JS
 *   Default/Code Cache    26.9MB  ← V8 编译后的 JS 字节码
 *   Default/Network/Cookies 20KB  ← **这才是登录态**
 *
 * ## 关键安全约束（不能碰的东西）
 *
 * `Service Worker` 目录**不在清理范围内** —— `crawler/service.py` 里明确
 * 记录微博采集**必须**有 SW 上下文（由它代理请求并注入 httpx 复现不了的
 * 上下文，实测直连一律 `ok=-100`）。删了等于让微博采集直接失效。
 * `Network`(Cookies/HSTS)、`Local Storage`、`IndexedDB`、`Sessions` 同理。
 *
 * ## 失败必须显示
 *
 * 浏览器占用 profile 时 Windows 会锁文件，删不掉。后端把失败的目录连同原因
 * 放在 `skipped` 里返回 —— 这里**原样展示**，不吞掉、不假装清完了。
 */
import { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Card, Collapse, Popconfirm, Progress, Space, Spin, Tag, Tooltip, Typography, message } from 'antd'
import {
  ClearOutlined,
  DeleteOutlined,
  InfoCircleOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
// ⚠️ 本文件在 `src/components/`（**不是** components 的子目录），
//    所以是 `../` 一级，写成 `../../` 会找不到模块（tsc TS2307）。
import {
  BrowserProfileCacheList,
  clearAllBrowserProfileCaches,
  clearBrowserProfileCache,
  getBrowserProfileCaches,
} from '../api'
import { useTheme } from '../constants/theme'

const { Text, Paragraph } = Typography

/** 把未知异常转成可读字符串。`catch (e: any)` 里的 e 实际是 unknown。 */
function errText(e: unknown): string {
  const anyE = e as { response?: { data?: { detail?: string } }; message?: string }
  return anyE?.response?.data?.detail || anyE?.message || '未知错误'
}

function fmtBytes(n: number): string {
  if (!n) return '0 KB'
  if (n < 1024) return `${n} B`
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1048576).toFixed(1)} MB`
}

export default function ProfileCacheCard() {
  const { theme } = useTheme()
  const [data, setData] = useState<BrowserProfileCacheList | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string>('')
  const [error, setError] = useState('')
  const [skipped, setSkipped] = useState<Record<string, string>>({})

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      setData(await getBrowserProfileCaches())
    } catch (e: unknown) {
      // 读不到就是读不到 —— 显示原因，不显示成"0 MB，一切正常"
      setError(errText(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const run = async (platform: string, all: boolean) => {
    setBusy(platform || '*')
    setError('')
    setSkipped({})
    try {
      const r = all ? await clearAllBrowserProfileCaches() : await clearBrowserProfileCache(platform)
      // 汇总被跳过的目录（删除失败 / 浏览器占用）——必须显示
      const merged: Record<string, string> = {}
      for (const item of r.results) {
        for (const [dir, why] of Object.entries(item.skipped || {})) {
          merged[`${item.platform} / ${dir}`] = why
        }
      }
      setSkipped(merged)
      if (r.total_freed_mb > 0) {
        message.success(`已释放 ${r.total_freed_mb} MB${merged && Object.keys(merged).length ? '（部分目录未清，详见下方提示）' : ''}`)
      } else if (Object.keys(merged).length) {
        message.warning('没有释放空间：相关目录被占用，未能清理')
      } else {
        message.info('没有可清理的缓存')
      }
      await load()
    } catch (e: unknown) {
      const detail = errText(e)
      setError(detail)
      message.error(`清理失败：${detail}`)
    } finally {
      setBusy('')
    }
  }

  const total = data?.total_disk_mb || 0
  const cacheMb = data?.total_cache_mb || 0
  const ratio = total > 0 ? Math.round((cacheMb / total) * 100) : 0
  // cookie 总体积很小，单独算出来给用户看"清这些不会掉登录"
  const cookieBytes = (data?.platforms || []).reduce((s, p) => s + (p.cookie_bytes || 0), 0)

  return (
    <Card
      title={
        <Space size={8}>
          <ThunderboltOutlined />
          <span>采集浏览器缓存</span>
          {data && cacheMb > 0 && (
            <Tag color="orange" style={{ marginInlineEnd: 0 }}>{cacheMb.toFixed(0)} MB 可清理</Tag>
          )}
        </Space>
      }
      extra={
        <Space>
          <Tooltip title="重新统计">
            <Button size="small" icon={<ReloadOutlined />} onClick={load} loading={loading} />
          </Tooltip>
          <Popconfirm
            title="清理所有平台的采集缓存"
            description={`将释放约 ${cacheMb.toFixed(0)} MB。登录态与 Service Worker 不受影响。`}
            okText="确认清理"
            cancelText="取消"
            onConfirm={() => run('', true)}
            disabled={cacheMb <= 0}
          >
            <Button size="small" icon={<ClearOutlined />} disabled={cacheMb <= 0} loading={busy === '*'}>
              全部清理
            </Button>
          </Popconfirm>
        </Space>
      }
      style={{ background: theme.bgCard, border: `1px solid ${theme.border}`, borderRadius: 12 }}
      styles={{ body: { padding: 16 } }}
    >
      {error && <Alert type="error" showIcon message="操作失败" description={error} style={{ marginBottom: 12 }} />}

      {Object.keys(skipped).length > 0 && (
        <Alert
          type="warning"
          showIcon
          message="部分目录未能清理（已如实列出，未假装成功）"
          description={
            <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
              {Object.entries(skipped).map(([k, v]) => (
                <li key={k} style={{ fontSize: 12 }}>
                  <Text code style={{ fontSize: 11 }}>{k}</Text> — {v}
                </li>
              ))}
            </ul>
          }
          style={{ marginBottom: 12 }}
        />
      )}

      {loading && !data ? (
        <div style={{ textAlign: 'center', padding: 24 }}><Spin /></div>
      ) : !data || (data.platforms || []).length === 0 ? (
        <Paragraph type="secondary" style={{ marginBottom: 0, fontSize: 13 }}>
          还没有采集浏览器 profile。首次扫码或采集后会自动生成。
        </Paragraph>
      ) : (
        <>
          <div style={{ marginBottom: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 }}>
              <Text type="secondary">
                可清理 {cacheMb.toFixed(1)} MB / 总占用 {total.toFixed(1)} MB
              </Text>
              <Text type="secondary" style={{ fontSize: 11 }}>
                <InfoCircleOutlined /> 登录态仅 {fmtBytes(cookieBytes)}，清理不会掉登录
              </Text>
            </div>
            <Progress
              percent={ratio}
              size="small"
              strokeColor={ratio > 50 ? '#faad14' : '#52c41a'}
              format={p => `${p}%`}
            />
          </div>

          <Collapse
            size="small"
            ghost
            items={[{
              key: 'per-platform',
              label: <Text style={{ fontSize: 13 }}>按平台查看（{data.platforms.length}）</Text>,
              children: (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {data.platforms
                    .filter(p => p.total_mb > 0)
                    .sort((a, b) => b.cache_mb - a.cache_mb)
                    .map(p => (
                      <div
                        key={p.platform}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 8,
                          padding: '6px 8px', borderRadius: 6,
                          background: theme.bgElevated || theme.bgPage,
                        }}
                      >
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <Text style={{ fontSize: 13 }}>{p.platform}</Text>
                          <div style={{ fontSize: 11, color: theme.textSecondary }}>
                            {p.cache_mb > 0
                              ? `可清 ${p.cache_mb.toFixed(1)} MB`
                              : <span style={{ color: theme.textDisabled }}>无缓存</span>}
                            {' · '}
                            总 {p.total_mb.toFixed(1)} MB
                            {' · cookie '}
                            {fmtBytes(p.cookie_bytes)}
                          </div>
                        </div>
                        <Popconfirm
                          title={`清理 ${p.platform} 的缓存`}
                          description={`将释放约 ${p.cache_mb.toFixed(1)} MB。登录态与 Service Worker 不受影响。`}
                          okText="确认清理"
                          cancelText="取消"
                          onConfirm={() => run(p.platform, false)}
                          disabled={p.cache_mb <= 0}
                        >
                          <Button
                            size="small"
                            icon={<DeleteOutlined />}
                            disabled={p.cache_mb <= 0}
                            loading={busy === p.platform}
                          />
                        </Popconfirm>
                      </div>
                    ))}
                </div>
              ),
            }]}
          />

          <Alert
            type="info"
            style={{ marginTop: 12 }}
            message={<Text style={{ fontSize: 12 }}>清理的是什么，不动的是什么</Text>}
            description={
              <div style={{ fontSize: 11.5, lineHeight: 1.7 }}>
                <div>
                  <Text strong>会删（加速副本）</Text>：
                  HTTP 响应缓存（封面图 / JS / CSS）、V8 Code Cache、GPU 与着色器缓存、扩展包缓存
                </div>
                <div>
                  <Text strong>不会动（身份与功能）</Text>：{data.preserved}
                </div>
                <div style={{ marginTop: 4, color: theme.textSecondary }}>
                  <InfoCircleOutlined /> 删掉后首次采集会变慢（要重新下载资源），但结果与登录态不受影响。
                  平台被浏览器占用时部分目录会删不掉，上面会列出具体原因。
                </div>
              </div>
            }
          />
        </>
      )}
    </Card>
  )
}
