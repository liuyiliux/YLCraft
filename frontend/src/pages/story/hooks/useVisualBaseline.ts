/**
 * 项目视觉基准的读取 / 设置 / 清除 + 选择器状态。
 *
 * 基准是**项目级**的一张图（`project_asset_links` 里 `role="visual_baseline"`，
 * 一个项目只保留一张），生图时由服务端自动注入为参考图——所以前端只负责「挑哪张」，
 * 不需要在每次生图时自己带上它。
 *
 * 抽成 hook 而不是写在页面里：`novel-world` 已有一份同样的逻辑，故事页再抄一遍
 * 必然会漂移（改了一处忘了另一处）。
 */
import { useCallback, useEffect, useState } from 'react'
import { message } from 'antd'

import { clearVisualBaseline, getVisualBaseline, listAssets, setVisualBaseline } from '../../../api'
import type { BaselineCandidate } from '../../../components/world/BaselinePickerModal'

export function useVisualBaseline(projectId?: string) {
  const [assetId, setAssetId] = useState<string | null>(null)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [candidates, setCandidates] = useState<BaselineCandidate[]>([])
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')

  // 基准是项目级设置：随项目变化重新读取，未绑定项目时置空。
  // 带 cancelled 标记：项目切换够快时，先发的请求可能后到，会把新项目的基准覆盖掉。
  useEffect(() => {
    if (!projectId) {
      setAssetId(null)
      return
    }
    let cancelled = false
    getVisualBaseline(projectId)
      .then((res: any) => {
        if (!cancelled) setAssetId(res?.data?.asset_id ?? null)
      })
      .catch(() => {
        if (!cancelled) setAssetId(null)
      })
    return () => {
      cancelled = true
    }
  }, [projectId])

  const loadCandidates = useCallback(async (keyword = '') => {
    setLoading(true)
    try {
      const res: any = await listAssets({
        asset_type: 'image',
        page: 1,
        page_size: 48,
        ...(keyword.trim() ? { search: keyword.trim() } : {}),
      })
      setCandidates(res?.data ?? res?.items ?? [])
    } catch {
      setCandidates([])
    } finally {
      setLoading(false)
    }
  }, [])

  const openPicker = useCallback(async () => {
    setPickerOpen(true)
    await loadCandidates(search)
  }, [loadCandidates, search])

  const pick = useCallback(
    async (asset: BaselineCandidate) => {
      if (!projectId) {
        message.warning('视觉基准按项目保存：请先选择或绑定一个创作项目')
        return
      }
      try {
        await setVisualBaseline(projectId, asset.id)
        setAssetId(asset.id)
        setPickerOpen(false)
        message.success('已设为项目视觉基准（生图时自动作为参考图注入）')
      } catch (error) {
        message.error((error as Error).message)
      }
    },
    [projectId],
  )

  const clear = useCallback(async () => {
    if (!projectId) return
    try {
      await clearVisualBaseline(projectId)
      setAssetId(null)
      message.success('已清除项目视觉基准')
    } catch (error) {
      message.error((error as Error).message)
    }
  }, [projectId])

  return {
    assetId,
    hasBaseline: Boolean(assetId),
    pickerOpen,
    setPickerOpen,
    candidates,
    loading,
    search,
    setSearch,
    openPicker,
    loadCandidates,
    pick,
    clear,
  }
}
