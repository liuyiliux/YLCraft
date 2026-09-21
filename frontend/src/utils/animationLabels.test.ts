import { describe, expect, it } from 'vitest'
import {
  animationDisplay,
  animationLabel,
  animationNameOptions,
  animationOptions,
  isPoseDuration,
} from './animationLabels'

describe('animationLabel', () => {
  it('常见动作直译', () => {
    expect(animationLabel('idle')).toBe('待机')
    expect(animationLabel('Walk')).toBe('走路')
    expect(animationLabel('run')).toBe('跑步')
  })

  it('带导出前缀与分隔符的变体也认得出', () => {
    // Blender / Mixamo 导出的 clip 名常见这些形态，归一化要能吃掉它们
    expect(animationLabel('Armature|walk')).toBe('走路')
    expect(animationLabel('mixamo.com|Idle')).toBe('待机')
    expect(animationLabel('idle_01')).toBe('待机')
  })

  it('认不出就返回空字符串，交给调用方回退原名（不硬翻）', () => {
    expect(animationLabel('myCustomClip')).toBe('')
    expect(animationLabel('')).toBe('')
  })

  it('已入库模型的动画名都有中文', () => {
    // Xbot(7 段) + CesiumMan 的 Survey，这些是真实在用的名字
    for (const name of ['agree', 'headShake', 'idle', 'run', 'sad_pose', 'sneak_pose', 'walk', 'Survey']) {
      expect(animationLabel(name), name).not.toBe('')
    }
  })
})

describe('animationDisplay', () => {
  it('有中文时「中文 · 原名」，没有时保留原名', () => {
    expect(animationDisplay('walk')).toBe('走路 · walk')
    expect(animationDisplay('myCustomClip')).toBe('myCustomClip')
  })
})

describe('animationOptions', () => {
  it('value 必须保持原始下标——它会被拿去索引模型的 clips 数组', () => {
    expect(animationOptions(['idle', 'walk'])).toEqual([
      { label: '待机 · idle', value: 0 },
      { label: '走路 · walk', value: 1 },
    ])
  })
})

/**
 * 定格姿态的识别（用户实测反馈：选「沮丧」「潜行」时角色一闪一闪）。
 *
 * 根因是 Xbot 的 `sad_pose` / `sneak_pose` 时长只有 0.033 秒（1 帧），
 * 它们是"摆一个姿势"而不是"播放一段动画"；按循环播放就会在两个关键帧之间
 * 每秒来回几十次。判断必须基于**真实时长**，而不是猜 clip 名字里有没有 "pose"
 * （叫不叫那个名字取决于导出方，而"只有 1 帧"是文件里的事实）。
 */
describe('isPoseDuration', () => {
  it('1~2 帧的 clip 判为定格姿态', () => {
    expect(isPoseDuration(0.0333)).toBe(true)   // Xbot sad_pose 实测值
    expect(isPoseDuration(0.0667)).toBe(true)
    expect(isPoseDuration(0.2)).toBe(true)
  })

  it('正常动画不算姿态', () => {
    expect(isPoseDuration(0.7)).toBe(false)     // run
    expect(isPoseDuration(2.5)).toBe(false)     // idle
  })

  it('时长未知或为 0 时不误判', () => {
    expect(isPoseDuration(undefined)).toBe(false)
    expect(isPoseDuration(0)).toBe(false)
  })
})

/**
 * 两种 options 的区别必须钉住——混用会让后端收到数字而不是动作名。
 * 实测踩过：套用动作库时传了下标，后端 422。
 */
describe('animationNameOptions（value 是动作名）', () => {
  it('value 是原始动作名，不是下标', () => {
    expect(animationNameOptions(['walk', 'run'])).toEqual([
      { label: '走路 · walk', value: 'walk' },
      { label: '跑步 · run', value: 'run' },
    ])
  })

  it('与 animationOptions 的差别只在 value 的类型', () => {
    expect(animationOptions(['walk'])[0].value).toBe(0)
    expect(animationNameOptions(['walk'])[0].value).toBe('walk')
    // label 必须一致，避免两处显示不同步
    expect(animationOptions(['walk'])[0].label).toBe(animationNameOptions(['walk'])[0].label)
  })
})

describe('animationOptions 的定格姿态标注', () => {
  it('按时长加标注', () => {
    const options = animationOptions(['idle', 'sad_pose'], [2.5, 0.0333])
    expect(options[0].label).toBe('待机 · idle')
    expect(options[1].label).toBe('沮丧 · sad_pose（定格姿态）')
  })

  it('没给时长就不标注（宁可不说，也不要瞎标）', () => {
    expect(animationOptions(['sad_pose'])[0].label).toBe('沮丧 · sad_pose')
  })
})
