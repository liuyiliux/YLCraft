import type { AssistantContext } from './assistantSession'

/**
 * 对话栏的**纯逻辑**（tasks 1.5 / 1.6：把状态机与文案抽出来单测）。
 *
 * 为什么要抽出来：这段东西全是"输入 → 文字/判断"，最能测、也最容易悄悄写错——
 * 而它一旦写错，表现却是"用户看不懂的报错"或"助手拿不到场景事实"这类只在真机上出现的症状。
 * 留在组件里就只能靠点界面发现，抽成纯函数才能用测试钉住。
 */

export interface AssistantOutgoingInput {
  /** 用户这次说的话 */
  text: string
  /** 场景上下文快照（节点、机位、锁定项、选中项…） */
  context: AssistantContext
  /** 库里的动作标识（原样可用） */
  motionSlugs: string[]
}

/**
 * 组装真正发出去的消息。
 *
 * **场景事实必须写进正文**，而不是只塞进 `context`：实测后端不会把 `context` 呈现给模型，
 * 助手于是说"当前会话没有可用的画面场景"、反过来向用户要场景 ID。写进正文是唯一保证它读到的路径。
 */
export function buildAssistantMessage({ text, context, motionSlugs }: AssistantOutgoingInput): string {
  return [
    `【当前场景】id=${context.scene_id}（版本 ${context.scene_revision}；时长 ${context.duration_frames} 帧 @${context.fps}fps；活动机位「${context.active_camera_name}」id=${context.active_camera_id}）`,
    `【锁定不可改】节点：${context.locked_nodes.map(item => `${item.name}(${item.id})`).join('、') || '无'}；机位：${context.locked_cameras.map(item => item.name).join('、') || '无'}`,
    context.selected_node
      ? `【用户当前选中】${context.selected_node.name}（id=${context.selected_node.id}）`
      : '',
    // 可改对象清单：**必须带 id**。只给"人形 1 个、几何体 1 个"时，助手只能自己编 targetId——
    // 实测它编出 `node:desk`，于是每条操作都因目标不存在被拒，用户看到的是"助手一直说做不到"。
    (context.node_roster || []).length
      ? `【场景里可改的对象（targetId 必须是下面这些 id，原样使用，不要拼造）】${(context.node_roster || [])
          .map(item => `${item.name}(id=${item.id}, ${item.kind})`)
          .join('、')}`
      : '',
    // 机位清单同理：只给名字时助手会编一个 id（实测编出 `cam-main`，真实是 `camera-1`）
    (context.camera_roster || []).length
      ? `【场景里可改的机位（set_camera 的 targetId 必须是下面这些 id，原样使用，不要拼造）】${(context.camera_roster || [])
          .map(item => `${item.name}(id=${item.id})`)
          .join('、')}`
      : '',
    // 动作标识**原样列出**：实测模型会编造 `motion:motionwave`（正确是 `motion:wave`）。
    motionSlugs.length
      ? `【可用动作（assign_motion 的 motion 值必须是下面这些，原样使用，不要改动或拼造）】${motionSlugs.join('、')}`
      : '',
    '【姿势 vs 动作】库里有现成动作用 assign_motion（照抄上面的清单）；库里没有的动作（打斗、拥抱、拔刀等）不要编造动作标识，改用 pose 静态姿势 + 站位/朝向/间距表达，并明确说明这一版只能表达到哪一步（例如"只能到对峙，看不出打中"）。',
    '【库里没有的姿势：自己算角度】可以用 metadata.poseJoints 直接给关节角度，不必编造不存在的姿势名或动作名。字段：三元组 leftShoulder/rightShoulder/leftHip/rightHip/torso/head = [pitch, twist, spread]（torso/head 的第二个值是转身），单值 leftElbow/rightElbow/leftKnee/rightKnee/bodyOffsetY。正负：肢体 pitch 负值=向前抬、spread 正值=向体侧张开、**肘只能负值（前屈）、膝只能正值（后收）**、torso/head 的 pitch 正值=前倾低头（后仰用负值）。限位（超出会被收敛）：肩 pitch -160~70 / spread -45~170，肘 -150~0，膝 0~140，torso pitch -15~60 / 转身 ±60，head pitch -45~55。例：{"operations":[{"type":"add_node","payload":{"kind":"human_proxy","name":"出拳方","position":[-0.42,0,0],"metadata":{"height":1.72,"poseJoints":{"rightShoulder":[-95,0,12],"rightElbow":-6,"leftShoulder":[-62,0,22],"leftElbow":-108,"torso":[10,-22,0],"head":[4,-14,0],"leftHip":[-14,0,10],"rightHip":[18,0,10],"leftKnee":20,"rightKnee":14}}}}]}。',
    '【输出要求】若你给出改场景的方案，请把操作数组放进 ```json 代码块（形如 {"operations":[...]}），界面会拿它去校验并渲染半透明预览；没有方案时正常回答即可。',
    `【用户】${text}`,
  ]
    .filter(Boolean)
    .join('\n')
}

/** 校验结果翻译成一句人话 + 是否需要重新载入场景。 */
export interface RejectionNotice {
  notice: string
  /** 版本过期：这份方案整批作废，必须重新载入最新版本后再提一次。 */
  needsReload: boolean
}

/**
 * 把后端的拒绝原因翻译成**下一步该做什么**。
 *
 * 直接用后端原文的问题：它是给开发看的（"expected_revision 不匹配"），用户看不懂；
 * 而"助手引用了不存在的动作"这类又必须补上"可用的是这些"——否则用户只能重发一遍碰运气。
 */
export function rejectionNotice(reasons: string[], motionSlugs: string[] = []): RejectionNotice {
  const first = reasons.find(Boolean) || '未知原因'
  const count = reasons.length
  const head = `方案有 ${count} 条没通过校验，已不渲染预览`

  // 版本过期：整批作废 + 必须重新载入。放在最前面判断——它和别的原因不同，
  // 不是"改改方案就行"，而是"这份方案整体失效了"。
  if (reasons.some(item => /版本|revision|过期/.test(item))) {
    return {
      notice: `${head}：场景已经在别处被改过了，这份方案整批作废。已重新载入最新版本，请让助手基于新版本再提一次。`,
      needsReload: true,
    }
  }
  if (reasons.some(item => /锁定|locked/.test(item))) {
    return { notice: `${head}：${first}。先解锁该对象，再让助手重提。`, needsReload: false }
  }
  if (reasons.some(item => /动作/.test(item))) {
    const hint = motionSlugs.length ? `可用动作只有：${motionSlugs.join('、')}` : '库里暂时没有可用动作'
    return { notice: `${head}：${first}（${hint}）`, needsReload: false }
  }
  if (reasons.some(item => /资产|asset/.test(item))) {
    return {
      notice: `${head}：${first}。素材库里没有它，让助手从可摆清单里选，不要凭印象写 assetId。`,
      needsReload: false,
    }
  }
  if (reasons.some(item => /未知操作类型/.test(item))) {
    return {
      notice: `${head}：${first}。助手用了预演台不认识的操作类型，让它改用受支持的操作重提。`,
      needsReload: false,
    }
  }
  return { notice: `${head}：${first}`, needsReload: false }
}

/** 预览结果：通过就渲染幽灵态，不通过就给一句能行动的话。 */
export function previewOutcome(
  data: { valid?: boolean; rejected?: Array<{ reason?: string }> } | null | undefined,
  motionSlugs: string[] = [],
): { ok: boolean } & RejectionNotice {
  const rejected = (data?.rejected ?? []).map(item => item?.reason).filter(Boolean) as string[]
  if (data?.valid && !rejected.length) return { ok: true, notice: '', needsReload: false }
  return { ok: false, ...rejectionNotice(rejected.length ? rejected : ['未知原因'], motionSlugs) }
}
