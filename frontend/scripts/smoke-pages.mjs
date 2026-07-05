import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'

const root = resolve(fileURLToPath(new URL('..', import.meta.url)))

const read = (path) => readFileSync(resolve(root, path), 'utf8')

const pages = [
  { route: '/agent', component: 'AgentPage', file: 'src/pages/agent/index.tsx' },
  { route: '/story', component: 'StoryPage', file: 'src/pages/story/index.tsx' },
  { route: '/characters', component: 'CharactersPage', file: 'src/pages/characters/index.tsx' },
  { route: '/assets', component: 'AssetsPage', file: 'src/pages/assets/index.tsx' },
  { route: '/settings', component: 'SettingsPage', file: 'src/pages/settings/index.tsx' },
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

const agentApi = read('src/api/agent.ts')
for (const needle of ['getAgentRunLinkedLogs', 'memory-candidates/save', 'memory-candidates/discard']) {
  if (!agentApi.includes(needle)) {
    failures.push(`Agent API missing smoke marker: ${needle}`)
  }
}

if (failures.length) {
  console.error('Page smoke failed:')
  for (const item of failures) console.error(`- ${item}`)
  process.exit(1)
}

console.log(`Page smoke passed: ${pages.map(page => page.route).join(', ')}`)
