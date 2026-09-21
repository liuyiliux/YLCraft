import type { PartNode } from '../../components/asset-hub/Model3DViewer'

/** 收集部位树的全部路径（用于把 `partVisibility` 铺满，未显式设过的按可见处理）。 */
export function collectPartPaths(parts: PartNode[]): string[] {
  const paths: string[] = []
  const walk = (nodes: PartNode[]) => {
    nodes.forEach(node => {
      paths.push(node.path)
      if (node.children?.length) walk(node.children)
    })
  }
  walk(parts)
  return paths
}

/**
 * 算出该回传给 antd Tree 的 `checkedKeys`：**只含"整块都可见"的节点**。
 *
 * 两条都是踩过坑的硬要求：
 *
 * 1. **不能把"半选"的父节点塞进来**。antd 的 `checkedKeys` 是受控的，收到父节点就会
 *    把它渲染成全选（并自动勾上所有后代），于是"取消一个子部位"在界面上看起来毫无变化。
 *    半选状态必须留给 antd 依据子节点自行推导。
 *
 * 2. **必须递归下探，不能只 filter 顶层**。部位树通常只有一个顶层节点（根骨骼），
 *    它一旦半选就会被整个丢掉；若就此返回空数组，antd 会认为"什么都没选中"，
 *    **整棵树的勾选态全乱**（用户实测："取消一个之后勾选就不对了"）。
 *    正确做法是：整块可见就上报这个父节点（让 antd 自动勾选其后代），
 *    否则把它下面**仍然整块可见**的子树报上去，父节点留给 antd 显示半选。
 *
 * @param parts 部位树（顶层节点）
 * @param visibility 路径 → 是否可见；缺省视为可见
 */
export function collectFullyCheckedPaths(
  parts: PartNode[],
  visibility?: Record<string, boolean>,
): string[] {
  const isFullyVisible = (node: PartNode): boolean => {
    // 没有显隐记录（首次打开）时一律视为可见，与 `partVisibility` 缺省即可见保持一致
    if (visibility?.[node.path] === false) return false
    return (node.children || []).every(isFullyVisible)
  }

  const collect = (nodes: PartNode[]): string[] => {
    const result: string[] = []
    nodes.forEach(node => {
      if (visibility?.[node.path] === false) return
      // 整块可见：只报这个父节点，后代交给 antd 联动。
      // 判定必须用布尔的"是否整块可见"，**不能拿下探结果的数组长度去比子节点个数**——
      // 一棵部分可见的子树会返回多个路径，长度恰好相等时就把它误判成"整块可见"，
      // 父节点被错误上报成全选（写测试时正是这样抓出来的）。
      if (isFullyVisible(node)) {
        result.push(node.path)
        return
      }
      result.push(...collect(node.children || []))
    })
    return result
  }

  return collect(parts)
}
