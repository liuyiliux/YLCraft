/**
 * 「工作台选中的模型」必须真的传到生成接口（回归保护）。
 *
 * 起因：内容包的两个**文本生成**调用（一次生成 / 单条重跑）漏传了 `provider` / `model`，
 * 而后端在两者为空时会静默回落到**默认连接器**。后果是：
 * 界面上选的是 A，实际跑的是 B；不报错，日志里只出现 B——
 * 用户只能靠"感觉输出不对"才发现，而那时额度已经花了。
 *
 * 这条缺陷属于「能力有、调用方漏了」：API 客户端与后端**都支持**这两个参数，
 * 只有调用方没传。所以这里把「传了没有」固定住，而不是去测生成结果。
 *
 * 同类对照：`useChapterContentActions`（大纲/细纲/正文/脚本/分镜）与
 * `useWorktreePreferenceActions`（流水线）一直是传的——内容包是新功能，漏了这条约定。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const planMock = vi.fn()
const retryMock = vi.fn()

vi.mock('../../../api', () => ({
  planCreativeProjectContentPackage: (...args: unknown[]) => planMock(...args),
  retryCreativeProjectContentPackageItem: (...args: unknown[]) => retryMock(...args),
  // hook 里 import 的其余符号给空实现，避免解析失败
  buildCreativeProjectContentPackageOutputs: vi.fn(),
  createCreativeProject: vi.fn(),
  createCreativeProjectFromNovel: vi.fn(),
  deleteCreativeProject: vi.fn(),
  extractCreativeProjectCharacters: vi.fn(),
  linkCreativeProjectAsset: vi.fn(),
  saveCreativeProjectContentPackage: vi.fn(),
  syncCreativeProjectBible: vi.fn(),
  syncCreativeProjectCharacters: vi.fn(),
  updateCreativeProject: vi.fn(),
  updateCreativeProjectContent: vi.fn(),
}))

vi.mock('../../../api/novelSource', () => ({ startProjectWorldExtraction: vi.fn() }))

vi.mock('antd', () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

import { useProjectContentActions } from './useProjectContentActions'

/** 测试用的模型选择：故意与"默认连接器"不同，才能验出有没有真的传过去。 */
const SELECTED_LLM = '若海-qwen3.8-27b'
const SELECTED_MODEL = 'qwen3.8-27b'

function buildDeps(overrides: Record<string, unknown> = {}) {
  const contentPackageForm = {
    getFieldsValue: () => ({ topic: '山里的怪同学', brief: '一个安静的转学生', item_count: 12, prompt_only: false }),
    getFieldValue: (key: string) => (key === 'brief' ? '一个安静的转学生' : false),
    setFieldsValue: vi.fn(),
  }
  return {
    selectedProject: { id: 'project-1', title: '山里的怪同学' },
    isContentPackageProject: true,
    contentPackageForm,
    contentPackageData: {},
    contentPackageContent: null,
    selectedLlm: SELECTED_LLM,
    selectedModel: SELECTED_MODEL,
    setLoadingAction: vi.fn(),
    loadContents: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  } as unknown as Record<string, unknown>
}

async function invokePlan(deps: Record<string, unknown>) {
  // 这个 hook 的入参/返回值都是宽类型（`Record<string, any>`），测试里按需松转换即可
  const actions = useProjectContentActions(deps as never) as unknown as Record<string, (...args: any[]) => any>
  planMock.mockResolvedValue({ data: { data: {} } })
  await actions.handlePlanContentPackage()
  return planMock.mock.calls[0]
}

async function invokeRetry(deps: Record<string, unknown>) {
  const actions = useProjectContentActions(deps as never) as unknown as Record<string, (...args: any[]) => any>
  retryMock.mockResolvedValue({ data: { data: {} } })
  await actions.handleRetryContentPackageItem('item-1')
  return retryMock.mock.calls[0]
}

beforeEach(() => {
  planMock.mockReset()
  retryMock.mockReset()
})

describe('内容包生成必须带上工作台选中的文本模型', () => {
  it('一次生成内容包：把 provider 与 model 一起发出', async () => {
    const [projectId, payload] = (await invokePlan(buildDeps())) as [string, Record<string, unknown>]

    expect(projectId).toBe('project-1')
    expect(payload.provider).toBe(SELECTED_LLM)
    expect(payload.model).toBe(SELECTED_MODEL)
    // 其余参数不能被这次修复带丢
    expect(payload.topic).toBe('山里的怪同学')
    expect(payload.item_count).toBe(12)
  })

  it('单条重跑：同样带上 provider 与 model', async () => {
    const [projectId, itemId, payload] = (await invokeRetry(buildDeps())) as [
      string,
      string,
      Record<string, unknown>,
    ]

    expect(projectId).toBe('project-1')
    expect(itemId).toBe('item-1')
    expect(payload.provider).toBe(SELECTED_LLM)
    expect(payload.model).toBe(SELECTED_MODEL)
  })

  it('未选模型时传 undefined（而不是空串）', async () => {
    // 空串会被后端当作"提供了但为空"，与"没提供"不是一回事；
    // 未选时应当交给后端回落，而不是塞一个无效值进去。
    const [, payload] = (await invokePlan(buildDeps({ selectedLlm: '', selectedModel: '' }))) as [
      string,
      Record<string, unknown>,
    ]

    expect(payload.provider).toBeUndefined()
    expect(payload.model).toBeUndefined()
  })
})
