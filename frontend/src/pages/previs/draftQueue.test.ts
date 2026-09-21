import { describe, expect, it } from 'vitest'

import {
  DRAFT_QUEUE_MAX,
  draftQueueLabel,
  draftQueueNextParams,
  draftQueuePosition,
  nextInDraftQueue,
  parseDraftQueue,
  serializeDraftQueue,
} from './draftQueue'

describe('批量初稿队列：解析', () => {
  it('空值 / 空串 / 只有逗号 → 空队列（不能解析出空项）', () => {
    expect(parseDraftQueue(null)).toEqual([])
    expect(parseDraftQueue(undefined)).toEqual([])
    expect(parseDraftQueue('')).toEqual([])
    expect(parseDraftQueue(',,')).toEqual([])
  })

  it('去空白、丢空项，保留顺序', () => {
    expect(parseDraftQueue(' a , b ,,c ')).toEqual(['a', 'b', 'c'])
  })

  it('去重且保留首次出现的位置（顺序就是执行顺序，不能因为去重而乱）', () => {
    expect(parseDraftQueue('a,b,a,c,b')).toEqual(['a', 'b', 'c'])
  })

  it('超过上限时截断（上限的存在理由是 URL 长度，不是性能）', () => {
    const many = Array.from({ length: DRAFT_QUEUE_MAX + 20 }, (_, index) => `s${index}`)
    expect(parseDraftQueue(many.join(','))).toHaveLength(DRAFT_QUEUE_MAX)
    // 截断保留的是**前面**那些：顺序即执行顺序，丢掉队尾才不会打乱已确认的部分
    expect(parseDraftQueue(many.join(','))[0]).toBe('s0')
  })

  it('序列化会顺手规整脏数据，避免把重复项写回 URL', () => {
    expect(serializeDraftQueue(['a', ' a ', '', 'b'])).toBe('a,b')
  })
})

describe('批量初稿队列：定位与推进', () => {
  const queue = ['s1', 's2', 's3']

  it('进度按 1 基给出', () => {
    expect(draftQueuePosition(queue, 's1')).toEqual({ index: 1, total: 3 })
    expect(draftQueuePosition(queue, 's3')).toEqual({ index: 3, total: 3 })
  })

  it('当前场景不在队列里 → null（视为不是批量进来的，UI 整块不显示）', () => {
    expect(draftQueuePosition(queue, 'other')).toBeNull()
    expect(draftQueuePosition([], 's1')).toBeNull()
  })

  it('下一格：中间格有、末格与大独格都没有', () => {
    expect(nextInDraftQueue(queue, 's1')).toBe('s2')
    expect(nextInDraftQueue(queue, 's3')).toBe('')
    expect(nextInDraftQueue(['only'], 'only')).toBe('')
    expect(nextInDraftQueue(queue, 'other')).toBe('')
  })

  it('推进参数：带上下一格、保留整条队列、并要求自动出草案', () => {
    const params = draftQueueNextParams(queue, 's2')
    expect(params?.get('scene_id')).toBe('s3')
    expect(params?.get('queue')).toBe('s1,s2,s3')
    // `draft=1` 让下一格进去就进幽灵态，与单格入口同一条路
    expect(params?.get('draft')).toBe('1')
  })

  it('末格没有推进参数（调用方据此收尾并摘掉队列）', () => {
    expect(draftQueueNextParams(queue, 's3')).toBeNull()
    expect(draftQueueNextParams(['only'], 'only')).toBeNull()
    expect(draftQueueNextParams(queue, 'other')).toBeNull()
  })
})

describe('批量初稿队列：文案', () => {
  it('中间格说明"确认或放弃后进入下一格"', () => {
    expect(draftQueueLabel({ index: 2, total: 5 })).toBe('批量初稿：第 2 / 5 格，确认或放弃后进入下一格')
  })

  it('末格必须点明"最后一格"：用户要知道按完还有没有下一格', () => {
    expect(draftQueueLabel({ index: 5, total: 5 })).toContain('最后一格')
    // 只有一格时同样要说清，否则与"后面还有很多"在界面上长得一样
    expect(draftQueueLabel({ index: 1, total: 1 })).toContain('最后一格')
  })

  it('不在批量里时没有文案', () => {
    expect(draftQueueLabel(null)).toBe('')
  })
})
