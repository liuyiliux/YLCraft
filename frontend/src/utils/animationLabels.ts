/**
 * 动画名中文化（展示层）。
 *
 * 三条刻意的原则：
 * 1. **不改数据**：GLB 里的 clip 名是文件事实——对接、排查、跨模型复用都要用原文，
 *    中文化只发生在渲染这一层；
 * 2. **认不出就显示原名**：宁可看到 `myCustomClip`，也不硬翻成一个可能错的中文。
 *    否则用户会以为那是模型自带的名字，排查时对不上文件；
 * 3. 展示成「待机 · idle」：中文在前好读，原名在后可核对。
 */

/** 精确匹配表（键为归一化后的名字）。 */
const EXACT: Record<string, string> = {
  idle: '待机',
  idle01: '待机',
  idle02: '待机',
  walk: '走路',
  walk01: '走路',
  run: '跑步',
  running: '跑步',
  jog: '慢跑',
  sprint: '冲刺',
  jump: '跳跃',
  agree: '点头同意',
  headshake: '摇头',
  tpose: 'T 形站姿',
  apose: 'A 形站姿',
  survey: '张望',
  death: '倒地',
  dying: '倒下',
  talk: '说话',
  wave: '挥手',
  dance: '跳舞',
  sit: '坐下',
  punch: '出拳',
  kick: '踢腿',
  bow: '鞠躬',
  clap: '鼓掌',
  attack: '攻击',
  hit: '受击',
  victory: '胜利',
  cheer: '欢呼',
  salute: '敬礼',
  standup: '起身',
  sneak: '潜行',
  crouch: '蹲下',
  crawl: '爬行',
  swim: '游泳',
  fly: '飞行',
}

/** 关键词规则（归一化后按顺序匹配，用于 `Idle_01`、`Armature|walk` 这类变体）。 */
const RULES: Array<[RegExp, string]> = [
  [/^(idle|breath|standing)/, '待机'],
  [/^(walk|stroll)/, '走路'],
  [/^(run|sprint|jog)/, '跑步'],
  [/^jump/, '跳跃'],
  [/shake.*head|headshake/, '摇头'],
  [/agree|nod/, '点头同意'],
  [/sad/, '沮丧'],
  [/sneak/, '潜行'],
  [/happy|joy/, '高兴'],
  [/angry|rage/, '愤怒'],
  [/death|die|dying/, '倒地'],
  [/hit|damage|hurt/, '受击'],
  [/attack|punch|kick/, '攻击'],
  [/talk|speak|say/, '说话'],
  [/wave/, '挥手'],
  [/dance/, '跳舞'],
  [/sit/, '坐下'],
  [/survey|look.?around/, '张望'],
]

/** 归一化：去掉 `Armature|`、`mixamo.com|` 这类前缀与多余分隔符。 */
function normalize(name: string): string {
  const tail = String(name || '').split('|').pop() || ''
  return tail.trim().toLowerCase().replace(/[\s_\-.:]+/g, '')
}

/** 取中文名；认不出时返回空字符串（调用方决定怎么回退）。 */
export function animationLabel(name: string): string {
  const key = normalize(name)
  if (!key) return ''
  if (EXACT[key]) return EXACT[key]
  for (const [pattern, label] of RULES) {
    if (pattern.test(key)) return label
  }
  return ''
}

/** 下拉/标签用的一行文案：有中文则「中文 · 原名」，否则就是原名。 */
export function animationDisplay(name: string): string {
  const label = animationLabel(name)
  return label ? `${label} · ${name}` : name
}

/**
 * 判定为「定格姿态」的时长上限（秒）。
 *
 * 为什么需要：有些 clip 根本不是动画而是**一个姿势**——实测 Xbot 的
 * `sad_pose` / `sneak_pose` 时长只有 0.033 秒（1 帧）。这类 clip 若按循环播放，
 * 就会在 1~2 个关键帧之间每秒来回几十次，看起来是"一闪一闪"（用户实测反馈）。
 * 正确语义是**播一次然后停住**（LoopOnce + clampWhenFinished）。
 */
export const POSE_DURATION_SECONDS = 0.2

/** 该时长是否属于「定格姿态」。 */
export function isPoseDuration(seconds?: number): boolean {
  return typeof seconds === 'number' && seconds > 0 && seconds <= POSE_DURATION_SECONDS
}

/**
 * 把 clip 名列表转成 antd Select 的 options，**value 是索引**。
 *
 * 用途：本地播放——选中的索引要拿去索引模型自己的 clips/actions 数组。
 * `durations` 传进来时会给定格姿态加上标注（用真实时长判断，而不是猜名字：
 * 叫不叫 `_pose` 取决于导出方，而"只有 1 帧"是文件里的事实）。
 *
 * ⚠️ 如果是要**把动作名发给后端**（例如套用动作库），请用 `animationNameOptions`
 * ——两者混用会让后端收到数字而不是动作名，表现为 422。
 */
export function animationOptions(
  names: string[],
  durations?: number[],
): Array<{ label: string; value: number }> {
  return names.map((name, index) => {
    const label = animationDisplay(name)
    return {
      label: isPoseDuration(durations?.[index]) ? `${label}（定格姿态）` : label,
      value: index,
    }
  })
}

/**
 * 把 clip 名列表转成 options，**value 是动作名本身**。
 *
 * 与 `animationOptions` 的区别只在这里：这个用于"把动作名传出去"的场景
 * （后端接口、跨模型套用），那个用于"本地按索引播放"。
 */
export function animationNameOptions(names: string[]): Array<{ label: string; value: string }> {
  return names.map(name => ({ label: animationDisplay(name), value: name }))
}
