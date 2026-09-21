import { describe, expect, it } from 'vitest'
import type { PrevisDraft } from '../../api'
import { draftBlockedReason, draftNodeIds } from './draftView'

function draft(overrides: Partial<PrevisDraft> = {}): PrevisDraft {
  return {
    success: true,
    scene_id: 'scene-1',
    panel_number: 3,
    read_only: true,
    scene_revision: 2,
    proposed_scene: {},
    operations: [],
    defaults: [],
    warnings: [],
    rejected: [],
    summary: {},
    ...overrides,
  }
}

describe('草案里被改动的节点', () => {
  it('新建节点按它自带的 id 标出', () => {
    const ids = draftNodeIds(
      draft({
        operations: [
          { type: 'add_node', payload: { node: { id: 'draft-p3-hero-1', kind: 'human_proxy' } } },
          { type: 'add_node', payload: { node: { id: 'draft-p3-hero-2', kind: 'human_proxy' } } },
        ],
      }),
    )
    expect(ids).toEqual(['draft-p3-hero-1', 'draft-p3-hero-2'])
  })

  it('改动已有节点也算', () => {
    const ids = draftNodeIds(
      draft({
        operations: [
          { type: 'set_human_proxy', targetId: 'hero-old', payload: { height: 1.8 } },
          { type: 'assign_motion', targetId: 'hero-old', payload: { motion: 'motion:walk' } },
          { type: 'update_transform', targetId: 'prop-1', payload: { position: [1, 0, 0] } },
        ],
      }),
    )
    // 去重：同一个人被改了两次也只标一个
    expect(ids).toEqual(['hero-old', 'prop-1'])
  })

  it('机位与场景级操作不产生节点标记', () => {
    const ids = draftNodeIds(
      draft({
        operations: [
          { type: 'add_camera', payload: { name: '中景机位' } },
          { type: 'set_camera', targetId: 'cam-1', payload: { fov: 40 } },
          { type: 'set_duration', payload: { frames: 96 } },
          { type: 'add_keyframe', targetId: 'hero-1', payload: { property: 'position' } },
        ],
      }),
    )
    expect(ids).toEqual([])
  })

  it('没有草案时返回空', () => {
    expect(draftNodeIds(null)).toEqual([])
  })
})

describe('幽灵态能否确认', () => {
  it('版本一致且没有未保存改动 → 可以确认', () => {
    expect(draftBlockedReason(draft(), { dirty: false, sceneRevision: 2 })).toBe('')
  })

  it('本地有未保存改动 → 拦住并说明会被覆盖', () => {
    const reason = draftBlockedReason(draft(), { dirty: true, sceneRevision: 2 })
    expect(reason).toContain('未保存')
    expect(reason).toContain('覆盖')
  })

  it('版本不一致 → 拦住并说明要重新载入', () => {
    const reason = draftBlockedReason(draft(), { dirty: false, sceneRevision: 5 })
    expect(reason).toContain('revision 2')
    expect(reason).toContain('重新载入')
  })

  it('未保存改动的提示优先于版本提示（两条都成立时先修更危险的那条）', () => {
    expect(draftBlockedReason(draft(), { dirty: true, sceneRevision: 9 })).toContain('未保存')
  })

  it('没有草案时不需要拦', () => {
    expect(draftBlockedReason(null, { dirty: true, sceneRevision: 1 })).toBe('')
  })
})
