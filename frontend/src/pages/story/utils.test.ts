/**
 * 分镜参考素材选择的聚焦测试。
 *
 * 背景（3d-director-previs 验收项 #23）：3D 预演截图回流时使用
 * `role="storyboard_reference"`，而参考选择用的是 role 白名单。若白名单漏了它，
 * 截图会「关联成功却选不到」——用户在分镜里根本看不到自己刚截的图。
 * 这里把白名单行为固定住，避免以后再加 role 时又漏。
 */
import { describe, expect, it } from 'vitest'
import { REFERENCE_LINK_ROLES, selectReferenceAssetsForPrompt } from './utils'

function link(assetId: string, role: string, metadata: Record<string, any> = {}) {
  return { asset_id: assetId, role, metadata } as any
}

describe('selectReferenceAssetsForPrompt', () => {
  it('把预演截图（storyboard_reference）纳入候选', () => {
    const assets = [link('capture-1', 'storyboard_reference')]
    const selected = selectReferenceAssetsForPrompt(assets, '第 1 镜：人物走进房间')
    expect(selected.map((item) => item.asset_id)).toEqual(['capture-1'])
  })

  it('排除不作为生成参考的 role（如 output）', () => {
    const assets = [link('output-1', 'output'), link('capture-1', 'storyboard_reference')]
    expect(selectReferenceAssetsForPrompt(assets, '').map((item) => item.asset_id)).toEqual(['capture-1'])
  })

  it('提示词点名的素材优先于预演截图', () => {
    const assets = [
      link('capture-1', 'storyboard_reference'),
      link('char-1', 'character', { character_name: '林默' }),
    ]
    const selected = selectReferenceAssetsForPrompt(assets, '林默推开门，逆光')
    // 角色一致性高于构图参考：点名角色应排在预演截图之前
    expect(selected[0].asset_id).toBe('char-1')
  })

  it('预演截图的优先级高于通用参考，但低于背景/画风之外的默认序', () => {
    const assets = [
      link('ref-1', 'reference'),
      link('capture-1', 'storyboard_reference'),
    ]
    const selected = selectReferenceAssetsForPrompt(assets, '一个空旷的街道')
    expect(selected[0].asset_id).toBe('capture-1')
  })

  it('白名单包含所有可作为生成参考的 role', () => {
    expect([...REFERENCE_LINK_ROLES].sort()).toEqual(
      ['background', 'character', 'reference', 'storyboard_reference', 'style', 'world'].sort(),
    )
  })
})
