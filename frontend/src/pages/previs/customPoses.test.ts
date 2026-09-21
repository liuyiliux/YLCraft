import { beforeEach, describe, expect, it } from 'vitest'
import {
  MAX_CUSTOM_POSES,
  loadCustomPoses,
  persistCustomPoses,
  removeCustomPose,
  saveCustomPose,
} from './customPoses'

/** 内存版 localStorage：隐私模式与"存不下"也要能测。 */
function installStorage(): void {
  const data = new Map<string, string>()
  const stub = {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    removeItem: (key: string) => void data.delete(key),
    clear: () => data.clear(),
    key: () => null,
    length: 0,
  }
  Object.defineProperty(globalThis, 'localStorage', { value: stub, configurable: true, writable: true })
}

const punch = { rightShoulder: [-95, 0, 12] as [number, number, number], rightElbow: -6 }

describe('本机姿势预设（把助手算出来的姿势存下来复用）', () => {
  beforeEach(() => installStorage())

  it('存了之后能读回来，且关节角原样保留', () => {
    const { list } = saveCustomPose([], '出拳', punch)
    persistCustomPoses(list)
    const loaded = loadCustomPoses()
    expect(loaded).toHaveLength(1)
    expect(loaded[0].name).toBe('出拳')
    expect(loaded[0].joints.rightElbow).toBe(-6)
  })

  it('同名是更新而不是新增：不会攒出一堆重名条目', () => {
    const first = saveCustomPose([], '出拳', punch).list
    const second = saveCustomPose(first, '出拳', { ...punch, rightElbow: -30 }).list
    expect(second).toHaveLength(1)
    expect(second[0].joints.rightElbow).toBe(-30)
  })

  it('空名字与空姿势都拒绝，并给出可读提示', () => {
    expect(saveCustomPose([], '  ', punch).notice).toContain('名字')
    expect(saveCustomPose([], '出拳', {}).notice).toContain('没有可保存')
  })

  it('超过上限不再新增（而不是无限膨胀）', () => {
    let list: ReturnType<typeof loadCustomPoses> = []
    for (let i = 0; i < MAX_CUSTOM_POSES; i++) list = saveCustomPose(list, `姿势${i}`, punch).list
    const overflow = saveCustomPose(list, '第 25 个', punch)
    expect(overflow.list).toHaveLength(MAX_CUSTOM_POSES)
    expect(overflow.notice).toContain('最多')
  })

  it('删除只删指定的那条', () => {
    const list = saveCustomPose(saveCustomPose([], 'a', punch).list, 'b', punch).list
    expect(removeCustomPose(list, list[0].id)).toHaveLength(1)
  })

  it('坏数据逐条跳过，不会因为一条脏数据丢掉全部积累', () => {
    localStorage.setItem(
      'ylcraft.previs.customPoses',
      JSON.stringify([{ id: 'x', name: '好的', joints: punch }, { id: 'y', name: '坏的', joints: '这不是姿势' }]),
    )
    expect(loadCustomPoses().map(item => item.name)).toEqual(['好的'])
  })
})
