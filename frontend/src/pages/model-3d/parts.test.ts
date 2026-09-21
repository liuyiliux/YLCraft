import { describe, expect, it } from 'vitest'

import type { PartNode } from '../../components/asset-hub/Model3DViewer'
import { collectFullyCheckedPaths, collectPartPaths } from './parts'

/**
 * 部位树的形状取自真实模型（根骨骼 → 脊柱 → 四肢），只保留与勾选推导相关的字段。
 */
const tree: PartNode[] = [
  {
    name: 'Hips',
    path: 'Hips',
    childCount: 3,
    children: [
      {
        name: 'Spine',
        path: 'Hips/Spine',
        childCount: 2,
        children: [
          { name: 'Arm', path: 'Hips/Spine/Arm', childCount: 1 },
          { name: 'Head', path: 'Hips/Spine/Head', childCount: 1 },
        ],
      },
      { name: 'Leg', path: 'Hips/Leg', childCount: 1 },
    ],
  },
]

describe('collectFullyCheckedPaths', () => {
  it('没有显隐记录时视为全部可见，只在顶层报一个节点', () => {
    expect(collectFullyCheckedPaths(tree)).toEqual(['Hips'])
  })

  it('全部可见时同样只报顶层——后代交给 antd 自己联动，报多了反而会覆盖半选态', () => {
    expect(collectFullyCheckedPaths(tree, {})).toEqual(['Hips'])
  })

  it('取消一个叶子后：半选的父节点退场，但其余"整块可见"的子树必须照旧上报', () => {
    // 这条是真实 bug 的回归测试：曾经的实现只 filter 顶层节点，
    // 顶层一旦半选就返回空数组，antd 便认为"什么都没选中"，整棵树的勾选态全乱。
    const result = collectFullyCheckedPaths(tree, { 'Hips/Spine/Head': false })
    expect(result).not.toEqual([])
    expect(result).toContain('Hips/Leg')
    expect(result).not.toContain('Hips')
    expect(result).not.toContain('Hips/Spine')
  })

  it('子树整块被取消时，该子树一个节点都不上报', () => {
    expect(collectFullyCheckedPaths(tree, { 'Hips/Spine': false })).toEqual(['Hips/Leg'])
  })

  it('兄弟子树全被取消时返回空数组——此时确实不该有任何勾选，不能硬凑一个父节点', () => {
    const result = collectFullyCheckedPaths(tree, {
      'Hips/Spine': false,
      'Hips/Leg': false,
    })
    expect(result).toEqual([])
  })

  it('空树返回空数组，不抛异常', () => {
    expect(collectFullyCheckedPaths([], {})).toEqual([])
  })
})

describe('collectPartPaths', () => {
  it('铺满所有路径（含中间节点），供 partVisibility 初始化使用', () => {
    expect(collectPartPaths(tree)).toEqual([
      'Hips',
      'Hips/Spine',
      'Hips/Spine/Arm',
      'Hips/Spine/Head',
      'Hips/Leg',
    ])
  })
})
