import { sanitizeHumanProxyPose, type HumanProxyPose } from '../../components/three/humanProxy'

/**
 * 用户自己存下来的姿势（**区别于代码里的预设**）。
 *
 * 为什么存的是**关节角**而不是一个预设名：预设名要走前后端两处枚举同步（新增 punch/hit 时
 * 就踩过这个坑——前端加了后端没加，助手一用就被拒）。存关节角走的是既有的 `poseJoints`
 * 通道，后端逐字段校验 + 限位收敛都现成，不需要改任何枚举。
 *
 * 存在 localStorage 而不是后端表：这是**本机的个人习惯件**（跟"我常用的几个造型"一个性质），
 * 不进场景数据、不影响别人、也不必为此引一张表和一个接口。
 */
export interface CustomPose {
  id: string
  name: string
  joints: HumanProxyPose
}

const STORAGE_KEY = 'ylcraft.previs.customPoses'

/** 上限 24：再多就变成"找姿势"而不是"用姿势"了。 */
export const MAX_CUSTOM_POSES = 24

function store(): Storage | null {
  try {
    return typeof localStorage !== 'undefined' ? localStorage : null
  } catch {
    // 隐私模式下访问 localStorage 会抛：存不下就当没有，功能降级但页面不能崩
    return null
  }
}

function newId(): string {
  return `cp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

/** 读本机存过的姿势。**坏数据逐条跳过**而不是整份丢弃：一条脏数据不该让用户丢掉全部积累。 */
export function loadCustomPoses(): CustomPose[] {
  const raw = store()?.getItem(STORAGE_KEY)
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed
      .map((item: any) => {
        const joints = sanitizeHumanProxyPose(item?.joints)
        if (!joints) return null
        return { id: String(item?.id || newId()), name: String(item?.name || '未命名姿势'), joints }
      })
      .filter((item: CustomPose | null): item is CustomPose => item !== null)
  } catch {
    return []
  }
}

export function persistCustomPoses(list: CustomPose[]): void {
  try {
    store()?.setItem(STORAGE_KEY, JSON.stringify(list))
  } catch {
    // 配额满等情况：存不下就算了，不该因为"没存住"打断正在摆姿势的人
  }
}

/**
 * 存一个新姿势。**同名覆盖**（重名的新增等于改，用户不会困惑于两个同名条目）。
 * 返回新列表与一句提示（满了 / 覆盖了 / 空姿势）。
 */
export function saveCustomPose(
  list: CustomPose[],
  name: string,
  joints: HumanProxyPose,
): { list: CustomPose[]; notice: string } {
  const cleanName = name.trim()
  const clean = sanitizeHumanProxyPose(joints)
  if (!cleanName) return { list, notice: '请先给这个姿势起个名字' }
  if (!clean) return { list, notice: '当前没有可保存的关节角度' }
  const withoutSameName = list.filter(item => item.name !== cleanName)
  const notice =
    withoutSameName.length !== list.length
      ? `已更新「${cleanName}」`
      : list.length >= MAX_CUSTOM_POSES
        ? `最多存 ${MAX_CUSTOM_POSES} 个姿势，请先删掉几个`
        : `已存为「${cleanName}」`
  if (withoutSameName.length !== list.length) {
    return { list: [...withoutSameName, { id: list.find(i => i.name === cleanName)!.id, name: cleanName, joints: clean }], notice }
  }
  if (list.length >= MAX_CUSTOM_POSES) return { list, notice }
  return { list: [...list, { id: newId(), name: cleanName, joints: clean }], notice }
}

export function removeCustomPose(list: CustomPose[], id: string): CustomPose[] {
  return list.filter(item => item.id !== id)
}

export function findCustomPose(list: CustomPose[], id: string): CustomPose | undefined {
  return list.find(item => item.id === id)
}
