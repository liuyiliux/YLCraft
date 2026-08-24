/**
 * YLCraft — 运行日志 Tab
 *
 * 后端应用运行日志（文件 tail）：时间、级别、logger、消息；支持级别/关键词过滤与加载更多。
 */

import {
  Button,
  Card,
  Input,
  Select,
  Space,
  Tag,
  message,
} from 'antd'
import { ReloadOutlined, ConsoleSqlOutlined } from '@ant-design/icons'
import { useState, useCallback, useEffect } from 'react'
import { listRuntimeLogs } from '../../api'
import { useTheme } from '../../constants/theme'

const LEVEL_OPTIONS = [
  { label: '全部级别', value: '' },
  { label: 'DEBUG', value: 'debug' },
  { label: 'INFO', value: 'info' },
  { label: 'WARNING', value: 'warning' },
  { label: 'ERROR', value: 'error' },
  { label: 'CRITICAL', value: 'critical' },
]

const LEVEL_COLOR_MAP: Record<string, string> = {
  debug: 'default',
  info: 'blue',
  warning: 'orange',
  error: 'red',
  critical: 'magenta',
}

interface RuntimeLine {
  timestamp: string
  level: string
  module: string
  module_key: string
  name: string
  message: string
}

const MODULE_CATALOG = [
  ['creative_project_outline', '创作项目-大纲'],
  ['creative_project_detail_outline', '创作项目-细纲'],
  ['creative_project_body', '创作项目-正文'],
  ['creative_project_script', '创作项目-剧本'],
  ['creative_project_storyboard', '创作项目-分镜'],
  ['ai_text', 'AI文本'], ['ai_image', 'AI生图'], ['ai_video', 'AI生视频'],
  ['ai_3d', 'AI生3D'], ['ai_tts', 'AI语音'], ['ai_stt', 'AI语音识别'],
  ['model_config', '模型配置'], ['comfyui', 'ComfyUI工作流'],
  ['asset_hub', '素材库-资产中枢'], ['asset_lineage', '素材库-资产血缘'], ['prompt_library', '提示词库'],
  ['download', '下载中心'], ['crawler', '素材采集'], ['bilibili', '哔哩哔哩'], ['fanqie', '番茄创作'],
  ['wechat', '微信内容'], ['creator_data', '创作者数据中心'], ['novel', '小说阅读与书源'],
  ['live2d', 'Live2D工厂'], ['clip', 'AI剪辑'], ['subtitle', '字幕工具'], ['bgm', 'BGM音乐'],
  ['breaker', '爆款拆解'], ['canvas', '创作画布'], ['previs', '3D预演'], ['agent', 'Agent智能体'],
  ['export', '导出中心'], ['account', '账号与登录'], ['task', '任务中心'], ['logs', '日志中心'],
  ['settings', '系统设置'], ['http', '外部接口'], ['ylcraft', '系统服务'], ['system', '系统'],
] as const

export default function RuntimeLogTab() {
  const { theme: THEME } = useTheme()
  const [lines, setLines] = useState<RuntimeLine[]>([])
  const [level, setLevel] = useState('')
  const [module, setModule] = useState('')
  const [q, setQ] = useState('')
  const [before, setBefore] = useState('')
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)

  const load = useCallback(async (params: { level?: string; module?: string; q?: string; before?: string; append?: boolean }) => {
    if (params.append) setLoadingMore(true)
    else setLoading(true)
    try {
      const res = await listRuntimeLogs({
        level: params.level,
        module: params.module,
        q: params.q,
        limit: 200,
        before: params.before || undefined,
      })
      if (res.success) {
        const newLines = res.lines || []
        if (params.append) {
          setLines((prev) => [...newLines, ...prev])
        } else {
          setLines(newLines)
        }
        setHasMore(!!res.has_more)
        setBefore(res.before || '')
      }
    } catch (err) {
      message.error('加载运行日志失败')
      console.error(err)
    } finally {
      setLoading(false)
      setLoadingMore(false)
    }
  }, [])

  useEffect(() => {
    load({ level, module, q })
  }, [load])

  const handleSearch = () => {
    setBefore('')
    load({ level, module, q })
  }

  const handleModuleChange = (value: string) => {
    setModule(value)
    setBefore('')
    load({ level, module: value, q })
  }

  const handleLoadMore = () => {
    if (before) load({ level, module, q, before, append: true })
  }

  const observedModules = new Map(lines.filter((line) => line.module_key).map((line) => [line.module_key, line.module]))
  const moduleOptions = Array.from(new Map([
    ...MODULE_CATALOG,
    ...Array.from(observedModules.entries()),
  ]).entries())
    .map(([value, label]) => ({ label, value }))

  return (
    <div>
      <Card
        title={
          <span>
            <ConsoleSqlOutlined style={{ marginRight: 8 }} />
            运行日志
          </span>
        }
        extra={
          <Space wrap>
            <Select
              placeholder="级别"
              value={level}
              onChange={setLevel}
              options={LEVEL_OPTIONS}
              style={{ width: 120 }}
              allowClear
            />
            <Select
              placeholder="模块"
              value={module}
              onChange={handleModuleChange}
              options={[{ label: '全部模块', value: '' }, ...moduleOptions]}
              style={{ width: 140 }}
              allowClear
              showSearch
              optionFilterProp="label"
              filterOption={(input, option) => String(option?.label || '').toLowerCase().includes(input.toLowerCase())}
            />
            <Input.Search
              placeholder="搜索关键词"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              style={{ width: 220 }}
              allowClear
              onSearch={handleSearch}
            />
            <Button icon={<ReloadOutlined />} onClick={handleSearch} loading={loading}>刷新</Button>
          </Space>
        }
      >
        <div
          style={{
            maxHeight: 640,
            overflow: 'auto',
            background: THEME.bgElevated,
            border: `1px solid ${THEME.border}`,
            borderRadius: 6,
            padding: 12,
            fontFamily: 'monospace',
            fontSize: 12,
            lineHeight: 1.7,
          }}
        >
          {hasMore && (
            <div style={{ marginBottom: 12, textAlign: 'center' }}>
              <Button size="small" loading={loadingMore} onClick={handleLoadMore}>加载更早</Button>
            </div>
          )}
          {loading && lines.length === 0 ? (
            <div style={{ color: THEME.textSecondary }}>加载中...</div>
          ) : lines.length === 0 ? (
            <div style={{ color: THEME.textSecondary }}>暂无运行日志</div>
          ) : (
            lines.map((line, idx) => (
              <div key={`${line.timestamp}-${idx}`} style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                <span style={{ color: THEME.textSecondary, whiteSpace: 'nowrap' }}>{line.timestamp}</span>
                <Tag color={LEVEL_COLOR_MAP[line.level.toLowerCase()] || 'default'} style={{ marginRight: 0, fontSize: 11, lineHeight: '16px' }}>
                  {line.level}
                </Tag>
                <Tag color="geekblue" style={{ marginRight: 0, fontSize: 11, lineHeight: '16px' }}>
                  {line.module || '系统'}
                </Tag>
                <span style={{ color: THEME.textPrimary, wordBreak: 'break-all' }}>
                  <span style={{ color: THEME.textSecondary }}>{line.name}: </span>
                  {line.message}
                </span>
              </div>
            ))
          )}
        </div>
      </Card>
    </div>
  )
}
