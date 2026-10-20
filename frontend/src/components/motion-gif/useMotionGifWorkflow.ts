/**
 * 动图工作流的**状态与行为**收口（切帧 + 合成 + 入库）。
 *
 * **为什么抽这个 hook**：这套逻辑原本散在 `image-gen/index.tsx`（2874 行）
 * 的 14 个互不相邻的代码块里，合计约 535 行。后果很具体：
 *
 * - 改一个动图交互，要在 2800 行里跳 14 次；
 * - 状态与操作它的函数离得远，`useCallback` **漏依赖**这类 bug 特别容易犯
 *   （本模块就踩过两次：漏 `motionGifOn` 导致回调永远读到旧值、
 *   `refreshMotionFramePreview` 写回自己依赖的 state 造成无限刷新）。
 *
 * 收进来之后：页面只拿一个对象用；新页面（`/motion`）直接复用同一份逻辑，
 * **不需要复制粘贴**。
 *
 * ## 边界（刻意划清）
 *
 * **本 hook 只管"已经有一张多格图之后"的事**：
 * 切帧、手动切格、每帧微调、合成、入库。
 *
 * **不管生成**：多格图的产出（提示词、动效类型、调用生图模型）留在生图页。
 * 原因是实测确认的 —— `slice-preview` / `compose` **都不需要动效类型**，
 * 四类动效只差提示词里的一个段落（其余块四类完全相同）。
 * 也就是说：**动效类型属于"生成"，不属于"切图"**。
 * 所以独立页完全不需要知道用户当初选的是环绕还是表情包。
 *
 * ## 跨页存活
 *
 * 状态经 `motionDraft`（sessionStorage）持久化。跳去图片编辑器再回来、
 * 或从生图页跳到独立页，都靠它把用户的切法/分割线/调色带回来。
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { message } from 'antd'
import {
  composeMotionGif,
  previewMotionGifSlice,
  saveMotionGif,
  uploadMotionGifFrame,
} from './api'
import { restoreAutoSlice } from './motionGifConfig'
import { clearMotionDraft, loadMotionDraft, saveMotionDraft } from './motionDraft'
import { useMotionGifOptions } from './useMotionGifOptions'
import { consumeImageEditorResults, launchImageEditor } from '../canvas/bridge'
import type {
  FrameAdjust,
  GridLayoutKey,
  LoopMode,
  MotionGifComposeOutput,
  SheetGridEdges,
  SliceRef,
} from './motionGifConfig'

/**
 * 合成输出长边（px）。
 *
 * 取 480 是实测过的：1024x1024 切 8 格（单格 256x512）时，480px 成品尚可接受。
 * 要撑 640px 成品就需要 2048 生成（单格 512px）—— **但那组组合我没实测过**，
 * 所以默认留在验证过的 480。
 */
export const MOTION_OUTPUT_SIZE = 480

/**
 * 排布兜底表。
 *
 * 事实来源是后端 `/motion-gif/options`（见 `useMotionGifOptions`）。
 * 这里只用于**选项还没拉到**的那一小段时间，否则"换排布"会因为查不到格数而算错。
 */
const GRID_FALLBACK: Record<GridLayoutKey, { rows: number; cols: number; cells: number }> = {
  '4x4': { rows: 4, cols: 4, cells: 16 },
  '2x4': { rows: 2, cols: 4, cells: 8 },
  '1x4': { rows: 1, cols: 4, cells: 4 },
}

export interface UseMotionGifWorkflowOptions {
  /** 是否启用（独立页恒 true；生图页跟随开关）。禁用时所有请求不发。 */
  enabled?: boolean
  /** 生成的题目，用于资产命名。独立页可为空。 */
  prompt?: string
  /** 创作项目血缘 —— 入库时带上，拆页后必须由调用方继续传，否则会断关联。 */
  projectId?: string
  contentId?: string
  /** 跳到图片编辑器时的返回路径（独立页是 `/motion`，生图页是 `/image-gen`）。 */
  returnTo?: string
}

export function useMotionGifWorkflow(options: UseMotionGifWorkflowOptions = {}) {
  const { enabled = true, prompt = '', projectId = '', contentId = '', returnTo = '/motion' } = options
  const navigate = useNavigate()
  const location = useLocation()

  /** 页面加载时先读草稿，用它当各 state 的初始值（只读一次）。 */
  const draft = useMemo(() => loadMotionDraft(), [])

  const [sheetPath, setSheetPath] = useState(draft?.motionSheetPath ?? '')
  const [sheetPreview, setSheetPreview] = useState(draft?.motionSheetPreview ?? '')
  const [layout, setLayout] = useState<GridLayoutKey>(draft?.motionGifLayout ?? '2x4')
  const [customShape, setCustomShape] = useState<{ rows: number; cols: number } | null>(
    draft?.customMotionShape ?? null,
  )
  const [order, setOrder] = useState<SliceRef[]>(draft?.motionOrder ?? [])
  const [loop, setLoop] = useState<LoopMode>(draft?.motionLoop ?? 'pingpong')
  const [alignSubject, setAlignSubject] = useState(draft?.motionAlignSubject ?? true)
  const [trim, setTrim] = useState(draft?.motionTrim ?? false)
  const [gridEdges, setGridEdges] = useState<SheetGridEdges | null>(draft?.motionGridEdges ?? null)
  const [frameUrls, setFrameUrls] = useState<string[]>([])
  const [output, setOutput] = useState<MotionGifComposeOutput | null>(null)
  const [composing, setComposing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [nodeId, setNodeId] = useState(draft?.motionNodeId ?? '')
  const [versionNumber, setVersionNumber] = useState(draft?.motionVersionNumber ?? 0)

  const { shapeOf, loops: loopOptions, grids: gridLayouts } = useMotionGifOptions(true)

  /** 某个排布的行列格数：优先用后端值，拉不到才退回兜底表。 */
  const shape = useCallback(
    (key: GridLayoutKey) => shapeOf(key) || GRID_FALLBACK[key],
    [shapeOf],
  )

  /** 实际用于切帧的行列（自定义优先，其次当前排布）。 */
  const activeShape = customShape || shape(layout)

  // -- 跨页持久化 ----------------------------------------------------------

  useEffect(() => {
    if (!sheetPath) {
      // 全新状态、什么都没做 —— 不要用空状态覆盖已有草稿
      return
    }
    saveMotionDraft({
      motionGifOn: true,
      motionGifKind: draft?.motionGifKind ?? 'orbit',
      motionGifLayout: layout,
      motionGifLang: draft?.motionGifLang ?? 'en',
      motionGifSubject: draft?.motionGifSubject ?? '',
      motionGifDisabledBlocks: draft?.motionGifDisabledBlocks ?? [],
      motionGifOptimized: draft?.motionGifOptimized ?? false,
      motionSheetPath: sheetPath,
      motionSheetPreview: sheetPreview,
      customMotionShape: customShape,
      motionPickedIndex: draft?.motionPickedIndex ?? 0,
      motionOrder: order,
      motionLoop: loop,
      motionAlignSubject: alignSubject,
      motionTrim: trim,
      motionGridEdges: gridEdges,
      motionNodeId: nodeId,
      motionVersionNumber: versionNumber,
    })
  }, [
    sheetPath, sheetPreview, layout, customShape, order, loop,
    alignSubject, trim, gridEdges, nodeId, versionNumber, draft,
  ])

  // -- 图源 ----------------------------------------------------------------

  /** 选定待切分的多格图。会重置帧顺序与分割线（换了图它们就没意义了）。 */
  const chooseSheet = useCallback(
    (path: string, previewUrl?: string) => {
      setSheetPath(path)
      setSheetPreview(previewUrl || '')
      setOrder(restoreAutoSlice(activeShape.rows * activeShape.cols, []))
      setGridEdges(null)
      setOutput(null)
    },
    [activeShape.rows, activeShape.cols],
  )

  const reset = useCallback(() => {
    setSheetPath('')
    setSheetPreview('')
    setOrder([])
    setGridEdges(null)
    setFrameUrls([])
    setOutput(null)
    setNodeId('')
    setVersionNumber(0)
    clearMotionDraft()
  }, [])

  /**
   * 自愈：**有图但没帧**时自动补上默认切法。
   *
   * 为什么需要：图源可以从多个入口进来 —— 点候选、跳转前写草稿、
   * 刷新页面从 sessionStorage 恢复。`chooseSheet` 会顺手填帧顺序，
   * 但**走草稿恢复这条路时它不会被调用**，于是出现"图已就绪、却没有可切的帧"
   * 的矛盾状态（实测复现过：草稿里有图、`motionOrder` 为空，
   * 面板显示"还没有可切的图"，用户无从下手）。
   *
   * 放在 effect 里而不是初始化里：`activeShape` 依赖后端拉的排布表，
   * 首帧可能还没拿到，初始化时算出的格数会是兜底值。
   */
  useEffect(() => {
    if (!enabled || !sheetPath) return
    if (order.length > 0) return
    setOrder(restoreAutoSlice(activeShape.rows * activeShape.cols, []))
  }, [enabled, sheetPath, order.length, activeShape.rows, activeShape.cols])

  // -- 排布 ----------------------------------------------------------------

  const changeLayout = useCallback(
    (next: GridLayoutKey) => {
      setLayout(next)
      setCustomShape(null)
      // 换排布后旧的帧顺序引用了不存在的格号，重置回自动切分。
      // 上传图保留（用户特意传的，多半是补模型画不好那一格），
      // 但必须按序号去重 —— restoreAutoSlice 会被多次调用，否则会反复累加。
      setOrder(prev => restoreAutoSlice(shape(next).cells, prev))
      // 拖过的分割线对不上新行列数（边界个数不匹配），直接清掉。
      setGridEdges(null)
    },
    [shape],
  )

  const changeShape = useCallback(
    (rows: number, cols: number) => {
      // 用后端给的排布表反查，而不是前端自己那份
      const known = gridLayouts.find(g => g.rows === rows && g.cols === cols)?.key
      if (known) {
        changeLayout(known)
      } else {
        setOrder(restoreAutoSlice(rows * cols, []))
        setOutput(null)
        setCustomShape({ rows, cols })
      }
    },
    [changeLayout, gridLayouts],
  )

  // -- 每帧微调 ------------------------------------------------------------

  const setAdjust = useCallback((index: number, adjust: FrameAdjust | null) => {
    setOrder(prev => {
      if (index < 0 || index >= prev.length) return prev
      const next = [...prev]
      next[index] = adjust ? { ...next[index], adjust } : { ...next[index], adjust: null }
      return next
    })
  }, [])

  // -- 切帧预览（本地像素处理，不花钱）--------------------------------------

  const refreshPreview = useCallback(async () => {
    if (!enabled || !sheetPath || order.length === 0) {
      setFrameUrls([])
      return
    }
    try {
      const res: any = await previewMotionGifSlice({
        sheet_path: sheetPath,
        rows: activeShape.rows,
        cols: activeShape.cols,
        order,
        align_subject: alignSubject,
        trim,
        grid_edges: gridEdges ?? undefined,
      })
      const data = res?.data ?? res
      if (data?.success) {
        setFrameUrls(data.frame_urls || [])
        // 后端回传它实际用的边界（做过夹紧/补齐），用它校正本地值，
        // 否则用户拖到越界时面板显示位置与真正切出来的会不一致。
        //
        // ⚠️ 必须**比较后再写**：本函数依赖 gridEdges，写新对象会再次触发本函数
        // —— 不比较就是无限刷新循环（肉眼表现为面板一直转圈）。
        const echoed: SheetGridEdges | undefined = data.grid_edges
        if (echoed) {
          setGridEdges(prev =>
            prev &&
            prev.xs.length === echoed.xs.length &&
            prev.ys.length === echoed.ys.length &&
            prev.xs.every((v, i) => Math.abs(v - echoed.xs[i]) < 1e-6) &&
            prev.ys.every((v, i) => Math.abs(v - echoed.ys[i]) < 1e-6)
              ? prev
              : echoed,
          )
        }
      } else {
        setFrameUrls([])
      }
    } catch (e: any) {
      setFrameUrls([])
      // 预览失败不该打断主流程：用户仍可直接合成
      message.warning(`切帧预览失败：${e?.message || e}`)
    }
  }, [enabled, sheetPath, order, activeShape.rows, activeShape.cols, alignSubject, trim, gridEdges])

  useEffect(() => {
    refreshPreview()
  }, [refreshPreview])

  // -- 送进图片编辑器 / 接收结果 -------------------------------------------

  const openFrameInEditor = useCallback(
    (index: number) => {
      const url = frameUrls[index]
      if (!url) {
        message.warning('这一帧还没有预览图 —— 等切帧预览生成完再试')
        return
      }
      launchImageEditor({
        imageUrl: url,
        returnTo,
        sourceTitle: `第 ${index + 1} 帧`,
        payload: { frameIndex: index },
        createdAt: new Date().toISOString(),
      })
      navigate('/image-editor')
    },
    [frameUrls, navigate, returnTo],
  )

  /**
   * 接收编辑器送回的结果，替换对应那一帧。
   *
   * 替换方式是**换成新的上传帧**而不是原地改像素 —— 帧顺序存的是"来源标识"
   * （SliceRef），像素在后端。新图必须先经 `upload-frame` 落盘拿到序号。
   * 直接塞 data URL 是**已知会失败**的（`resolve_asset_file` 对 `data:` 返回 None）。
   */
  const acceptFrameEdits = useCallback(async () => {
    const results = consumeImageEditorResults()
    if (results.length === 0) return
    const claimed = results
      .map(r => ({ r, index: Number((r.payload as any)?.frameIndex) }))
      .filter(x => Number.isInteger(x.index) && x.index >= 0)
    if (claimed.length === 0) return

    setComposing(true)
    try {
      let next = [...order]
      let replaced = 0
      let outOfRange = 0
      for (const { r, index } of claimed) {
        if (index >= next.length) {
          // 以前是**静默跳过**，于是"已替换 1 帧"的提示照发、画面却没变 ——
          // 用户看到的是"提示说替换了，其实什么都没发生"。现在如实报出来。
          outOfRange += 1
          continue
        }
        const blob = await (await fetch(r.imageDataUrl)).blob()
        const ext = (r.imageDataUrl.match(/data:image\/(\w+)/)?.[1] || 'png').replace('jpeg', 'jpg')
        const uploaded = await uploadMotionGifFrame(
          new File([blob], `edited_${index + 1}.${ext}`, { type: blob.type || 'image/png' }),
        )
        if (!uploaded?.success) continue
        // 新上传帧没有 adjust（像素已经变了），旧的调色必须丢掉
        next[index] = { kind: 'upload', index: uploaded.index }
        replaced += 1
      }
      setOrder(next)
      if (replaced > 0) message.success(`已替换 ${replaced} 帧 —— 点「合成动图」出新版`)
      if (outOfRange > 0) {
        message.warning(
          `有 ${outOfRange} 帧没换上：切帧列表里没有这个位置了（可能换过图或删过格）。` +
            '请重新选一帧再编辑。',
        )
      }
      if (replaced === 0 && outOfRange === 0) {
        message.warning('编辑结果没能用上：上传没成功，请重试')
      }
    } catch (e: any) {
      message.error(`接收编辑结果失败：${e?.message || e}`)
    } finally {
      setComposing(false)
    }
  }, [order])

  // 回到本页时接收（编辑器那边点是"送回"）
  useEffect(() => {
    acceptFrameEdits()
  }, [acceptFrameEdits, location.pathname])

  // -- 合成 / 入库 ---------------------------------------------------------

  const compose = useCallback(async () => {
    if (!sheetPath) {
      message.warning('还没有待切分的图片 —— 先选一张')
      return
    }
    setComposing(true)
    try {
      const res: any = await composeMotionGif({
        sheet_path: sheetPath,
        rows: activeShape.rows,
        cols: activeShape.cols,
        order,
        loop,
        size: MOTION_OUTPUT_SIZE,
        align_subject: alignSubject,
        trim,
        grid_edges: gridEdges ?? undefined,
        save_frames: true,
        write_webp: true,
        write_mp4: false,
      })
      const data = res?.data ?? res
      if (data?.success) {
        setOutput(data.output)
        // 合成时后端也存了每帧小图，直接复用（省一次预览请求）
        if (data.output?.frame_paths?.length) setFrameUrls(data.output.frame_paths)
        message.success('合成完成（未调用模型，不产生费用）')
      } else {
        message.error(data?.error || '合成失败')
      }
    } catch (e: any) {
      message.error(`合成失败：${e?.message || e}`)
    } finally {
      setComposing(false)
    }
  }, [sheetPath, activeShape.rows, activeShape.cols, order, loop, alignSubject, trim, gridEdges])

  const save = useCallback(async () => {
    if (!sheetPath) {
      message.warning('还没有待切分的图片')
      return
    }
    setSaving(true)
    try {
      const res: any = await saveMotionGif({
        sheet_path: sheetPath,
        rows: activeShape.rows,
        cols: activeShape.cols,
        order,
        loop,
        size: MOTION_OUTPUT_SIZE,
        write_webp: true,
        write_mp4: false,
        name: prompt.trim().slice(0, 40) || '动图',
        prompt,
        provider: '',
        model: '',
        motion_kind: draft?.motionGifKind || '',
        // ⚠️ 存库是**自己再合成一次**，所以合成参数必须与 compose 完全一致。
        // 少传 align_subject/trim 会让入库的成品与用户刚看到的不一样。
        align_subject: alignSubject,
        trim,
        grid_edges: gridEdges ?? undefined,
        node_id: nodeId || undefined,
        project_id: projectId || undefined,
        content_id: contentId || undefined,
      })
      const data = res?.data ?? res
      if (data?.success) {
        setNodeId(data.node_id)
        setVersionNumber(data.version_number || 1)
        setOutput(data.output)
        message.success(nodeId ? `已追加为 v${data.version_number}（同一个动图节点）` : '已存入素材库')
      } else {
        message.error(data?.error || '保存失败')
      }
    } catch (e: any) {
      message.error(`保存失败：${e?.message || e}`)
    } finally {
      setSaving(false)
    }
  }, [
    sheetPath, activeShape.rows, activeShape.cols, order, loop, alignSubject,
    trim, gridEdges, nodeId, prompt, projectId, contentId, draft?.motionGifKind,
  ])

  return {
    // 图源
    sheetPath, sheetPreview, chooseSheet, reset,
    // 排布
    layout, activeShape, layoutOptions: gridLayouts, changeLayout, changeShape,
    // 切帧
    order, setOrder, frameUrls, gridEdges, setGridEdges,
    alignSubject, setAlignSubject, trim, setTrim,
    // 循环
    loop, setLoop, loopOptions,
    // 每帧微调
    setAdjust,
    // 图片编辑器
    openFrameInEditor,
    // 合成 / 入库
    output, composing, saving, versionNumber, nodeId,
    compose, save,
  }
}

export type MotionGifWorkflow = ReturnType<typeof useMotionGifWorkflow>
