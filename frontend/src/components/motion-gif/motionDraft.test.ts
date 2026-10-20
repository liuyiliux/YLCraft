/**
 * 跨页传递「待切分的图片」（回归保护）。
 *
 * 起因（用户反馈"素材库还是没有新入的动图"）：
 * 拆 hook 时，生图页**残留了一份页面本地的 `motionSheetPath` state**，
 * 点候选缩略图写的是它 —— 而它已经没人读了。真正的图源归 `/motion` 页，
 * 只能经 sessionStorage 草稿传递。
 *
 * 后果是**静默的**：页面看不出异常（缩略图高亮正常），
 * 跳到 `/motion` 却是空的图源 → 切不了帧 → 合成没产出 → 素材库里当然什么都没有。
 * 用户只能看到"存了但没有"，中间每一步都不报错。
 *
 * 这里把"选图必须落进草稿"钉住。
 */

import { beforeEach, describe, expect, it } from 'vitest'

import {
  MOTION_DRAFT_STORAGE_KEY,
  clearMotionDraft,
  loadMotionDraft,
  rememberMotionSheet,
  saveMotionDraft,
} from './motionDraft'

/** 最小 sessionStorage 替身（vitest 默认是 node 环境，没有它）。 */
function installSessionStorage() {
  const store = new Map<string, string>()
  ;(globalThis as any).sessionStorage = {
    getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
    setItem: (k: string, v: string) => void store.set(k, String(v)),
    removeItem: (k: string) => void store.delete(k),
    clear: () => store.clear(),
  }
}

const BASE_DRAFT = {
  motionGifOn: true,
  motionGifKind: 'expression' as const,
  motionGifLayout: '2x4' as const,
  motionGifLang: 'zh' as const,
  motionGifSubject: '',
  motionGifDisabledBlocks: [],
  motionGifOptimized: false,
  motionSheetPath: '/old/sheet.png',
  motionSheetPreview: '/api/old',
  customMotionShape: null,
  motionPickedIndex: 0,
  motionOrder: [],
  motionLoop: 'cycle' as const,
  motionAlignSubject: true,
  motionTrim: false,
  motionGridEdges: null,
  motionNodeId: '',
  motionVersionNumber: 0,
}

describe('跨页传递待切分图', () => {
  beforeEach(() => {
    installSessionStorage()
    clearMotionDraft()
  })

  it('选图后草稿里必须有它 —— 否则 /motion 打开是空的', () => {
    rememberMotionSheet('/new/sheet.png', '/api/new')
    const draft = loadMotionDraft()
    expect(draft).not.toBeNull()
    expect(draft!.motionSheetPath).toBe('/new/sheet.png')
    expect(draft!.motionSheetPreview).toBe('/api/new')
  })

  it('只改图源，不覆盖用户在 /motion 调好的切法', () => {
    // 用户已在 /motion 里调过：分割线 + 帧顺序 + 调色
    saveMotionDraft({
      ...BASE_DRAFT,
      motionOrder: [
        { kind: 'origin', index: 3, adjust: { brightness: 0.6 } },
        { kind: 'upload', index: 1 },
      ],
      motionGridEdges: { xs: [0, 0.3, 0.5, 0.75, 1], ys: [0, 0.5, 1] },
    })

    // 生图页选了另一张候选
    rememberMotionSheet('/another/sheet.png', '/api/another')

    const draft = loadMotionDraft()!
    expect(draft.motionSheetPath).toBe('/another/sheet.png')
    // 循环方式、对齐等**用户偏好**要留着
    expect(draft.motionLoop).toBe('cycle')
    expect(draft.motionAlignSubject).toBe(true)
  })

  it('换图必须清掉分割线 —— 那是上一张图的坐标', () => {
    saveMotionDraft({
      ...BASE_DRAFT,
      motionGridEdges: { xs: [0, 0.3, 0.5, 0.75, 1], ys: [0, 0.5, 1] },
    })
    rememberMotionSheet('/brand/new.png', '/api/new')
    // 留着旧边界会让新图一切出来就是错位的，且**不会报错**
    expect(loadMotionDraft()!.motionGridEdges).toBeNull()
  })

  it('没有草稿时也能单独工作（首次进入就选图）', () => {
    expect(loadMotionDraft()).toBeNull()
    rememberMotionSheet('/first/sheet.png', '/api/first')
    expect(loadMotionDraft()!.motionSheetPath).toBe('/first/sheet.png')
  })

  it('没有图源的草稿一律当作没有（避免恢复出空面板）', () => {
    saveMotionDraft({ ...BASE_DRAFT, motionSheetPath: '' })
    expect(loadMotionDraft()).toBeNull()
  })

  it('草稿写坏（非法 JSON）时不抛错，当作没有', () => {
    ;(globalThis as any).sessionStorage.setItem(MOTION_DRAFT_STORAGE_KEY, '{坏掉的')
    expect(loadMotionDraft()).toBeNull()
  })
})
