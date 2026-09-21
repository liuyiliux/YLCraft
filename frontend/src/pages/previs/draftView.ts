/**
 * 幽灵态（待确认草案）的两条纯逻辑。
 *
 * 抽出来的理由很实际：这两条判断都是**安全相关**的——"哪些节点该标成草案"错了会让用户看不出
 * 改了哪；"能不能确认"错了会让用户把别人的改动或自己未保存的改动**悄悄覆盖掉**。放在组件里
 * 只能靠人眼验证，抽出来就能单测（与 `timeline.ts` / `cameraMoves.ts` 同一处理方式）。
 */

import type { PrevisDraft } from '../../api'

/**
 * 草案里**被新增或改动**的节点 id：视口据此把"这次新加的/改过的"标成半透明 + 线框盒。
 *
 * 只关心节点：`set_camera` / `add_camera` / `set_duration` 改的是机位与场景级字段，
 * 它们在视口里没有"某个节点"可标，改由确认条的摘要说明。
 */
export function draftNodeIds(draft: PrevisDraft | null): string[] {
  if (!draft) return []
  const ids = new Set<string>()
  for (const operation of draft.operations || []) {
    if (operation.type === 'add_node') {
      // 初稿会给新建节点显式 id（否则后续操作引用不到它），这里直接取
      const nodeId = operation.payload?.node?.id
      if (typeof nodeId === 'string' && nodeId) ids.add(nodeId)
      continue
    }
    if (['set_human_proxy', 'assign_motion', 'update_transform'].includes(operation.type) && operation.targetId) {
      ids.add(operation.targetId)
    }
  }
  return [...ids]
}

/**
 * 幽灵态能否确认；返回空串表示可以，否则返回**可执行的原因**。
 *
 * 两条必须拦住的情况：
 * 1. **本地有未保存改动**——草案是服务端基于已保存的场景算的，直接确认会把用户刚做的改动
 *    悄悄丢掉（这是最危险的一种：用户会以为"我只是应用了初稿"）；
 * 2. **版本不一致**——场景已被他人改动，草案的前提过期了。
 *
 * 刻意返回原因而不是布尔值：按钮置灰却不说明为什么，用户只会反复点击。
 */
export function draftBlockedReason(
  draft: PrevisDraft | null,
  context: { dirty: boolean; sceneRevision: number | null | undefined },
): string {
  if (!draft) return ''
  if (context.dirty) {
    return '本地有未保存的改动：先保存（或撤销）再确认初稿，否则这些改动会被草案覆盖'
  }
  if (Number(context.sceneRevision ?? 0) !== Number(draft.scene_revision ?? 0)) {
    return `场景版本已变化（草案基于 revision ${draft.scene_revision}，本地是 ${
      context.sceneRevision ?? '未知'
    }）：请重新载入场景后再生成初稿`
  }
  return ''
}
