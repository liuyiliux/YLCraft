import { describe, expect, it } from 'vitest'

import {
  MAX_ASSISTANT_MESSAGES,
  appendAssistantMessage,
  buildAssistantContext,
  makeAssistantMessage,
} from './assistantSession'
import type { PrevisCamera, PrevisNode } from './types'

const node = (over: Partial<PrevisNode>): PrevisNode =>
  ({
    id: 'n1',
    kind: 'human_proxy',
    name: '人形占位 1',
    visible: true,
    locked: false,
    transform: { position: [0, 0, 0], rotation: [0, 0, 0, 1], scale: [1, 1, 1] },
    metadata: {},
    ...over,
  }) as PrevisNode

const camera = (over: Partial<PrevisCamera>): PrevisCamera =>
  ({
    id: 'c1',
    name: '中景机位',
    transform: { position: [0, 1.6, 4], rotation: [0, 0, 0, 1], scale: [1, 1, 1] },
    target: [0, 0, 0],
    fov: 50,
    locked: false,
    ...over,
  }) as PrevisCamera

describe('预演助手会话：上下文快照', () => {
  const scene = { id: 'scene-1', revision: 7, durationFrames: 96, fps: 24 }

  it('给出场景事实与活动机位（机位用可读名字，不用 UUID）', () => {
    const ctx = buildAssistantContext({
      scene,
      nodes: [node({})],
      cameras: [camera({})],
      activeCameraId: 'c1',
    })
    expect(ctx.scene_id).toBe('scene-1')
    expect(ctx.scene_revision).toBe(7)
    expect(ctx.duration_frames).toBe(96)
    expect(ctx.active_camera_name).toBe('中景机位')
  })

  it('节点数量照旧给：判断"有多少东西"够用，不占太多正文', () => {
    const ctx = buildAssistantContext({
      scene,
      nodes: [node({}), node({ id: 'n2' }), node({ id: 'p1', kind: 'primitive' })],
      cameras: [camera({})],
      activeCameraId: 'c1',
    })
    expect(ctx.node_counts).toEqual({ human_proxy: 2, primitive: 1 })
  })

  it('可改对象清单带 id：数量不够定位"改哪一个"（实测助手会编 targetId 导致每条被拒）', () => {
    const ctx = buildAssistantContext({
      scene,
      nodes: [node({}), node({ id: 'n2' }), node({ id: 'p1', kind: 'primitive' })],
      cameras: [camera({})],
      activeCameraId: 'c1',
    })
    expect(ctx.node_roster).toEqual([
      { id: 'n1', name: '人形占位 1', kind: 'human_proxy' },
      { id: 'n2', name: '人形占位 1', kind: 'human_proxy' },
      { id: 'p1', name: '人形占位 1', kind: 'primitive' },
    ])
  })

  it('锁定对象不进可改清单：给了就是让助手去改一个必然被拒的目标', () => {
    const ctx = buildAssistantContext({
      scene,
      nodes: [node({ locked: true }), node({ id: 'n2' })],
      cameras: [camera({})],
      activeCameraId: 'c1',
    })
    expect(ctx.node_roster.map(item => item.id)).toEqual(['n2'])
  })

  it('锁定对象必须带 id 与名称：只给数量等于让助手再问一次，而它未必有机会问', () => {
    const ctx = buildAssistantContext({
      scene,
      nodes: [node({ locked: true }), node({ id: 'n2', name: '自由的' })],
      cameras: [camera({ id: 'c2', name: '固定机位', locked: true })],
      activeCameraId: 'c1',
    })
    expect(ctx.locked_nodes).toEqual([{ id: 'n1', name: '人形占位 1' }])
    expect(ctx.locked_cameras).toEqual([{ id: 'c2', name: '固定机位' }])
  })

  it('选中节点会带进上下文（助手据此理解「这个」指谁）；没选就不带这个键', () => {
    const picked = buildAssistantContext({
      scene,
      nodes: [node({})],
      cameras: [camera({})],
      activeCameraId: 'c1',
      selectedNode: node({}),
    })
    expect(picked.selected_node).toEqual({ id: 'n1', name: '人形占位 1', kind: 'human_proxy' })

    const none = buildAssistantContext({ scene, nodes: [], cameras: [], activeCameraId: '' })
    expect('selected_node' in none).toBe(false)
    // 没有活动机位时给兜底名字，而不是空串（助手回复里引用机位才不会出现空白）
    expect(none.active_camera_name).toBe('活动机位')
  })
})

describe('预演助手会话：消息状态', () => {
  const message = (id: string) => makeAssistantMessage('user', `第 ${id} 句`, { id, at: Number(id) })

  it('追加不改原数组（React 状态更新要求）', () => {
    const before = [message('1')]
    const after = appendAssistantMessage(before, message('2'))
    expect(before).toHaveLength(1)
    expect(after.map(item => item.id)).toEqual(['1', '2'])
  })

  it('超出上限丢最旧的，而不是无限增长把面板拖死', () => {
    let list = [] as ReturnType<typeof message>[]
    for (let index = 0; index < MAX_ASSISTANT_MESSAGES + 5; index += 1) {
      list = appendAssistantMessage(list, makeAssistantMessage('user', `m${index}`, { id: String(index), at: index }))
    }
    expect(list).toHaveLength(MAX_ASSISTANT_MESSAGES)
    expect(list[0].id).toBe('5')
    expect(list[list.length - 1].id).toBe(String(MAX_ASSISTANT_MESSAGES + 4))
  })

  it('同一毫秒内的两条消息靠 id 区分（不靠时间戳排序去重）', () => {
    const a = makeAssistantMessage('user', 'a', { id: 'a', at: 1000 })
    const b = makeAssistantMessage('assistant', 'b', { id: 'b', at: 1000 })
    expect(appendAssistantMessage([a], b)).toHaveLength(2)
  })
})
