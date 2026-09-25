/**
 * 预演助手会话的**纯逻辑**：上下文快照 + 消息状态。
 *
 * 为什么单独抽出来：这两件事都是"说错了会误导助手"的地方——上下文少给一个锁定对象，
 * 助手就会提出改锁定对象的方案；消息状态不设上限，长会话会把面板拖死。
 * 而它们都跟 React 无关，抽成纯函数就能单测（本项目的既有做法：安全相关的逻辑不留给人眼）。
 *
 * 渲染、请求发送、把方案接进幽灵预览都由 UI 层负责（见 `PrevisAssistantPanel.tsx`）。
 */

import type { PrevisCamera, PrevisNode } from './types'

/** 助手角色的标识。权限刻意收窄（见 `backend/app/services/agent/profile.py` 的 `previs-assistant`）。 */
export const ASSISTANT_PROFILE_ID = 'previs-assistant'

/** 消息上限：超出丢最旧的。长会话不该把面板拖死，历史本来就该去会话记录里看。 */
export const MAX_ASSISTANT_MESSAGES = 60

export interface AssistantMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  /** 毫秒时间戳；仅用于展示与排序。 */
  at: number
}

/**
 * 会话上下文。
 *
 * **面向"能改什么"而不是罗列节点**（沿用 `context_pack` 里 `_previs_scene_brief` 的取舍）：
 * 助手要判断的是"这个场景现在什么样、哪些东西不能动"，而不是"场景里每个节点叫什么"。
 */
export interface AssistantContext {
  scene_id: string
  scene_revision: number
  duration_frames: number
  fps: number
  active_camera_id: string
  active_camera_name: string
  /** 各类型节点的**数量**（不含明细）：明细对"提方案"没有帮助，反而挤掉上下文。 */
  node_counts: Record<string, number>
  /**
   * 场景里**可改对象的清单**（id + 名称 + 种类）。
   *
   * 为什么必须给：助手要写 `update_transform` / `set_human_proxy` 的 `targetId`，
   * 而正文里原先只有 `node_counts`（数量）。实测后果——助手说"场景上下文里没有给出
   * 桌子的真实节点 id，我编的 id 不在场景里"，于是**每一条操作都因 targetId 不存在被拒**，
   * 用户看到的是"助手一直说做不到"。数量够判断"有多少东西"，**不够定位"改哪一个"**。
   */
  node_roster: { id: string; name: string; kind: string }[]
  /**
   * 锁定对象**含 id 与名称**。
   *
   * 只给数量等于让助手再问一次"锁的是谁"，而它在一次对话里未必有机会问——
   * 这个取舍在 `context_pack` 里已经吃过一次教训（`locked_nodes` 当初只给了数量）。
   */
  locked_nodes: { id: string; name: string }[]
  locked_cameras: { id: string; name: string }[]
  /**
   * 场景里**可改机位的清单**（id + 名称）。
   *
   * 与 `node_roster` 同一个教训：`set_camera` 的 `targetId` 必须是机位 id，
   * 而正文原先只给了活动机位的**名字**。实测助手于是编出 `cam-main`，
   * 真实 id 是 `camera-1` —— 又一条"内容都对、引用是假的"被拒。
   */
  camera_roster: { id: string; name: string }[]
  /** 当前在左侧面板选中的节点：助手据此理解"这个/它"指谁。 */
  selected_node?: { id: string; name: string; kind: string }
}

export function buildAssistantContext(input: {
  /** 只用得上这几项，所以按结构声明，不依赖场景文档类型（前端侧那份类型与后端不同源）。 */
  scene: { id: string; revision: number; durationFrames?: number; fps?: number }
  nodes: PrevisNode[]
  cameras: PrevisCamera[]
  activeCameraId: string
  selectedNode?: PrevisNode | null
}): AssistantContext {
  const counts: Record<string, number> = {}
  for (const node of input.nodes) {
    counts[node.kind] = (counts[node.kind] || 0) + 1
  }
  const active = input.cameras.find(camera => camera.id === input.activeCameraId)
  return {
    scene_id: String(input.scene.id || ''),
    scene_revision: Number(input.scene.revision || 0),
    duration_frames: Number(input.scene.durationFrames || 0),
    fps: Number(input.scene.fps || 24),
    active_camera_id: String(input.activeCameraId || ''),
    // 起个可读的名字：助手在回复里引用机位时，"中景机位"比一串 UUID 有用得多
    active_camera_name: String(active?.name || '活动机位'),
    node_counts: counts,
    // 清单只列可改对象：锁定项另有一栏，重复列出只会让正文变长
    node_roster: input.nodes
      .filter(node => !node.locked)
      .map(node => ({ id: node.id, name: node.name, kind: node.kind })),
    locked_nodes: input.nodes
      .filter(node => node.locked)
      .map(node => ({ id: node.id, name: node.name })),
    locked_cameras: input.cameras
      .filter(camera => camera.locked)
      .map(camera => ({ id: camera.id, name: camera.name })),
    camera_roster: input.cameras
      .filter(camera => !camera.locked)
      .map(camera => ({ id: camera.id, name: camera.name })),
    ...(input.selectedNode
      ? {
          selected_node: {
            id: input.selectedNode.id,
            name: input.selectedNode.name,
            kind: input.selectedNode.kind,
          },
        }
      : {}),
  }
}

/** 追加一条消息（超出上限时丢最旧的）。返回新数组，不改原数组。 */
export function appendAssistantMessage(
  messages: AssistantMessage[],
  message: AssistantMessage,
): AssistantMessage[] {
  const next = [...messages, message]
  return next.length > MAX_ASSISTANT_MESSAGES ? next.slice(next.length - MAX_ASSISTANT_MESSAGES) : next
}

/** 生成一条消息（id 与时间由调用方传入，便于测试与"同一毫秒内两条"也能区分）。 */
export function makeAssistantMessage(
  role: AssistantMessage['role'],
  text: string,
  identity: { id: string; at: number },
): AssistantMessage {
  return { id: identity.id, role, text, at: identity.at }
}
