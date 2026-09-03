import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'

const root = resolve(fileURLToPath(new URL('..', import.meta.url)))

const read = (path) => readFileSync(resolve(root, path), 'utf8')

const pages = [
  { route: '/agent', component: 'AgentPage', file: 'src/pages/agent/index.tsx' },
  { route: '/story', component: 'StoryPage', file: 'src/pages/story/index.tsx' },
  { route: '/characters', component: 'CharacterWorkspaceEntry', file: 'src/pages/character-detail/index.tsx' },
  { route: '/assets', component: 'AssetsPage', file: 'src/pages/assets/index.tsx' },
  { route: '/settings', component: 'SettingsPage', file: 'src/pages/settings/index.tsx' },
  { route: '/canvas', component: 'CanvasPage', file: 'src/pages/canvas/index.tsx' },
  { route: '/novel-world', component: 'NovelWorldPage', file: 'src/pages/novel-world/index.tsx' },
  { route: '/world-map', component: 'WorldMapPage', file: 'src/pages/world-map/index.tsx' },
]

const app = read('src/App.tsx')
const failures = []

for (const page of pages) {
  const source = read(page.file)
  if (!source.includes('export default function') && !source.includes('export default')) {
    failures.push(`${page.file} does not expose a default component`)
  }
  if (!app.includes(`path="${page.route.slice(1)}"`)) {
    failures.push(`App.tsx does not mount ${page.route}`)
  }
  if (!app.includes(page.component)) {
    failures.push(`App.tsx does not import/render ${page.component}`)
  }
}

const agent = read('src/pages/agent/index.tsx')
const agentNeedles = [
  '运行轨迹',
  '关联日志',
  '保存记忆',
  '委派子任务',
  '工具调用日志',
  '项目生成日志',
  '后台任务',
]
for (const needle of agentNeedles) {
  if (!agent.includes(needle)) {
    failures.push(`Agent page missing smoke marker: ${needle}`)
  }
}

const canvas = read('src/pages/canvas/index.tsx')
for (const needle of ['getImageTask', 'asyncTaskId', 'materializeGenerationResult', 'continueWorkflowAfterAsyncImage', 'resumeWorkflowRef', 'generationOutputImages', 'GenerationResultRail', 'CANVAS_STARTER_TEMPLATE_MENU', 'onRunWorkflow', '媒体选择节点需要先确认至少一项候选结果', "status: 'waiting'"]) {
  if (!canvas.includes(needle)) {
    failures.push('Canvas page missing async-generation marker: ' + needle)
  }
}
const agentApi = read('src/api/agent.ts')
for (const needle of ['getAgentRunLinkedLogs', 'memory-candidates/save', 'memory-candidates/discard']) {
  if (!agentApi.includes(needle)) {
    failures.push(`Agent API missing smoke marker: ${needle}`)
  }
}

const novelWorld = read('src/pages/novel-world/index.tsx')
for (const needle of ['小说世界提取', 'AI 判断模块', '提取所选模块', '检索原文证据']) {
  if (!novelWorld.includes(needle)) {
    failures.push(`Novel world page missing smoke marker: ${needle}`)
  }
}

const worldMap = read('src/pages/novel-world/components/WorldMapEditor.tsx')
for (const needle of [
  '世界地图工作台',
  'LayerPanel',
  'NodeDetailPanel',
  'VisualDrawer',
  'BatchDrawer',
  'ExportModal',
  'VersionModal',
  '导出 SVG / PNG / 点位 JSON',
]) {
  if (!worldMap.includes(needle)) {
    failures.push(`World map editor missing smoke marker: ${needle}`)
  }
}

const mapPanels = read('src/components/world/DataPanel.tsx')
for (const needle of ['批量管理（编辑）', '新增据点', '新增区域', '新增路线']) {
  if (!mapPanels.includes(needle)) {
    failures.push(`Map data panel missing smoke marker: ${needle}`)
  }
}

if (failures.length) {
  console.error('Page smoke failed:')
  for (const item of failures) console.error(`- ${item}`)
  process.exit(1)
}

console.log(`Page smoke passed: ${pages.map(page => page.route).join(', ')}`)
