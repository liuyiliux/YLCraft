/**
 * 世界地图工作台 · 独立入口（与 /novel-world 平级）。
 * 从 URL 读取 project_id / snapshot_id，让 WorldMapEditor 直接定位。
 * 与 /novel-world 共享同一 WorldMapEditor 实现（结构化数据为正典，AI 成图仅派生）。
 *
 * 页面层负责三件与主题/作用域有关的全局事项：
 * 1) 挂载 .worldmap-scope（样式令牌作用域，见 docs/design/world-map-workbench-style.md §3）；
 * 2) 用 ConfigProvider 把 antd 的主色/语义色/圆角对齐同一套令牌，避免组件各自写死 hex；
 * 3) 提供项目选择器：URL 未带 project_id 时（如从侧边栏直接进入）也能就地选定项目，
 *    选择写回 URL（replace），刷新/分享不丢上下文。
 */
import { useEffect, useState } from 'react'
import { ConfigProvider, Select, theme as antdTheme } from 'antd'
import { useSearchParams } from 'react-router-dom'
import WorldMapEditor from '../novel-world/components/WorldMapEditor'
import { listCreativeProjects } from '../../api'
import '../../components/world/worldmap.css'

const THEME_KEY = 'worldmap-theme'

interface ProjectOption {
  id: string
  title: string
}

/** 工作台类页面默认提供深浅主题，偏好记忆到 localStorage。 */
function useWorkbenchTheme(): [string, (next: string) => void] {
  const [theme, setTheme] = useState<string>(() => localStorage.getItem(THEME_KEY) || 'light')
  useEffect(() => {
    localStorage.setItem(THEME_KEY, theme)
  }, [theme])
  return [theme, setTheme]
}

export default function WorldMapPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const projectId = searchParams.get('project_id')
  const snapshotId = searchParams.get('snapshot_id')
  const [theme, setTheme] = useWorkbenchTheme()
  const dark = theme === 'dark'
  const [projects, setProjects] = useState<ProjectOption[]>([])

  useEffect(() => {
    let cancelled = false
    listCreativeProjects({ limit: 80 })
      .then((response) => {
        if (cancelled) return
        const data = (response as { data?: ProjectOption[] } | null)?.data || []
        setProjects(data)
      })
      .catch(() => {
        // 列表加载失败不阻塞工作台：编辑器内仍有「需要先有项目」的引导。
      })
    return () => {
      cancelled = true
    }
  }, [])

  const handleProjectChange = (next: string) => {
    const params = new URLSearchParams(searchParams)
    params.set('project_id', next)
    // 切换项目后旧项目的快照深链必然失效，一并清掉避免错位恢复。
    params.delete('snapshot_id')
    setSearchParams(params, { replace: true })
  }

  return (
    <ConfigProvider
      theme={{
        algorithm: dark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: {
          colorPrimary: dark ? '#3c8cff' : '#1677ff',
          colorError: dark ? '#ff7a7c' : '#ff4d4f',
          colorSuccess: dark ? '#6bd04d' : '#52c41a',
          colorWarning: dark ? '#ffa940' : '#fa8c16',
          borderRadius: 6,
          fontSize: 13,
          controlHeight: 32,
        },
      }}
    >
      <div className="worldmap-scope" data-theme={theme} style={{ padding: 24, minHeight: '100%' }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 12,
            marginBottom: 8,
          }}
        >
          <Select
            showSearch
            optionFilterProp="label"
            style={{ minWidth: 280 }}
            placeholder="选择创作项目（确认写入世界设定后才有地点实体）"
            value={projectId ?? undefined}
            onChange={handleProjectChange}
            options={projects.map((p) => ({ value: p.id, label: p.title || p.id }))}
          />
          <button
            type="button"
            onClick={() => setTheme(dark ? 'light' : 'dark')}
            title={dark ? '切换到浅色' : '切换到深色'}
            style={{
              height: 28,
              padding: '0 10px',
              fontSize: 12,
              cursor: 'pointer',
              color: 'var(--p-fg)',
              background: 'var(--p-surface)',
              border: '1px solid var(--p-border)',
              borderRadius: 6,
            }}
          >
            {dark ? '浅色' : '深色'}
          </button>
        </div>
        <WorldMapEditor projectId={projectId} snapshotId={snapshotId} />
      </div>
    </ConfigProvider>
  )
}
