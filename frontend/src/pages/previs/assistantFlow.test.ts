import { describe, expect, it } from 'vitest'
import { buildAssistantMessage, previewOutcome, rejectionNotice } from './assistantFlow'
import { buildAssistantContext, type AssistantContext } from './assistantSession'

const hero = {
  id: 'hero',
  name: '主角',
  kind: 'human_proxy',
  locked: true,
  transform: { position: [0, 0, 0], rotation: [0, 0, 0, 1], scale: [1, 1, 1] },
  metadata: {},
  visible: true,
}

/** 未锁定：应出现在"可改对象清单"里（助手要拿它的 id 当 targetId）。 */
const table = {
  id: 'node-table',
  name: '桌子',
  kind: 'primitive',
  locked: false,
  transform: { position: [-1.4, 0.375, 0], rotation: [0, 0, 0, 1], scale: [1, 1, 1] },
  metadata: {},
  visible: true,
}

const context: AssistantContext = buildAssistantContext({
  scene: { id: 'scene-1', revision: 7, durationFrames: 96, fps: 24 },
  nodes: [hero, table] as any,
  cameras: [{ id: 'cam-1', name: '中景机位', locked: false }] as any,
  activeCameraId: 'cam-1',
  selectedNode: hero as any,
})

describe('对话栏：发给助手的消息（tasks 1.6）', () => {
  it('场景事实写进正文：id、版本、时长、活动机位都在——模型只能从正文读到', () => {
    const message = buildAssistantMessage({ text: '把桌子挪到人物右侧', context, motionSlugs: [] })
    expect(message).toContain('scene-1')
    expect(message).toContain('版本 7')
    expect(message).toContain('96 帧 @24fps')
  })

  it('锁定项与选中项都带上：助手才知道哪些不能改、用户在说哪个', () => {
    const message = buildAssistantMessage({ text: '挪一下', context, motionSlugs: [] })
    expect(message).toContain('主角')
    expect(message).toMatch(/锁定不可改/)
    expect(message).toMatch(/用户当前选中/)
  })

  it('可改对象清单带真实 id：助手写 targetId 才有依据，否则只能编', () => {
    const message = buildAssistantMessage({ text: '把桌子挪到人物右侧', context, motionSlugs: [] })
    // 实测教训：正文原先只有"人形 1 个、几何体 1 个"这类计数，助手于是编出 `node:desk`，
    // 每条操作都因目标不存在被拒，用户看到的是"助手一直说做不到"。
    expect(message).toContain('node-table')
    expect(message).toContain('桌子')
    expect(message).toMatch(/不要拼造/)
  })

  it('锁定对象不进可改清单：免得助手去改一个必然被拒的目标', () => {
    const message = buildAssistantMessage({ text: '挪一下', context, motionSlugs: [] })
    // 锁定的 hero 只应出现在「锁定不可改」，不该同时出现在可改清单里
    const roster = message.split('【场景里可改的对象')[1]?.split('\n')[0] || ''
    expect(roster).not.toContain('主角')
  })

  it('机位清单带真实 id：set_camera 的 targetId 才有依据（实测助手编出 cam-main）', () => {
    const message = buildAssistantMessage({ text: '机位推近一点', context, motionSlugs: [] })
    expect(message).toContain('cam-1')
    expect(message).toContain('中景机位')
    // 活动机位那行也要带 id，避免助手从名字拼一个
    expect(message).toContain('id=cam-1')
  })

  it('动作标识原样列出（模型会编造，只能把合法值摆在它眼前）', () => {
    const message = buildAssistantMessage({
      text: '挥手',
      context,
      motionSlugs: ['motion:wave', 'motion:nod'],
    })
    expect(message).toContain('motion:wave')
    expect(message).toContain('motion:nod')
  })

  it('用户的话在最后，且带上输出格式约定', () => {
    const message = buildAssistantMessage({ text: '机位推近一点', context, motionSlugs: [] })
    expect(message.trimEnd().endsWith('【用户】机位推近一点')).toBe(true)
    expect(message).toContain('```json')
  })
})

describe('对话与确认的边界用例（tasks 1.5）', () => {
  it('版本过期：整批作废 + 必须重新载入（不是"改改方案就行"）', () => {
    const outcome = previewOutcome(
      { valid: false, rejected: [{ reason: '场景中 revision 已变化，整批作废' }] },
      ['motion:wave'],
    )
    expect(outcome.ok).toBe(false)
    expect(outcome.needsReload).toBe(true)
    expect(outcome.notice).toContain('整批作废')
  })

  it('锁定对象被要求修改：提示先解锁', () => {
    const notice = rejectionNotice(['目标对象已锁定，不可修改'], [])
    expect(notice.notice).toContain('解锁')
    expect(notice.needsReload).toBe(false)
  })

  it('引用了不存在的动作：拒绝 + 附上可用动作清单（否则用户只能重发碰运气）', () => {
    const notice = rejectionNotice(['动作不存在：motion:motionwave'], ['motion:wave', 'motion:nod'])
    expect(notice.notice).toContain('motion:wave')
    expect(notice.notice).toContain('motion:nod')
  })

  it('引用了不存在的资产：提示从可摆清单里选，别凭印象写 assetId', () => {
    expect(rejectionNotice(['资产不存在：asset-123'], []).notice).toContain('素材库')
  })

  it('未知操作类型：说清是"操作类型不认识"，而不是丢一句后端原文', () => {
    expect(rejectionNotice(['未知操作类型：teleport'], []).notice).toContain('操作类型')
  })

  it('通过校验就是 ok，不给任何提示', () => {
    expect(previewOutcome({ valid: true, rejected: [] })).toEqual({
      ok: true,
      notice: '',
      needsReload: false,
    })
  })

  it('没有原因时也不炸：给出"未知原因"而不是空白提示', () => {
    expect(previewOutcome({ valid: false, rejected: [] }).notice).toContain('未知原因')
  })

  it('多条被拒时报条数，不是只说第一条', () => {
    expect(rejectionNotice(['a', 'b', 'c'], []).notice).toContain('3 条')
  })
})
