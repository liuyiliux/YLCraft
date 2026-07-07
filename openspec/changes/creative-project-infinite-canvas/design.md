# Design

## Concept Split

YLCraft has two visual surfaces:

| Surface | Role | Source of truth |
| --- | --- | --- |
| 项目关系图谱 | Visualizes existing project facts and lineage. | `CreativeProject`, `ProjectContent`, `ProjectAssetLink`, asset metadata. |
| 创作画布 / 自由画布 | Free-form composition, planning and AI-assisted workspace. | Canvas document state and operation log. |

The relationship graph should stay deterministic and regenerable. The infinite canvas should be user-authored and editable.

## MVP Data Shape

```ts
type CanvasViewport = {
  x: number
  y: number
  k: number
}

type CanvasNode = {
  id: string
  type: 'text' | 'image' | 'asset' | 'prompt' | 'content' | 'note' | 'group' | 'agent_output'
  title: string
  position: { x: number; y: number }
  width: number
  height: number
  metadata?: Record<string, unknown>
}

type CanvasConnection = {
  id: string
  fromNodeId: string
  toNodeId: string
  type?: string
  label?: string
  metadata?: Record<string, unknown>
}

type CanvasOperation =
  | { op: 'add_node'; node: CanvasNode }
  | { op: 'update_node'; nodeId: string; patch: Partial<CanvasNode> }
  | { op: 'delete_node'; nodeId: string }
  | { op: 'connect_nodes'; connection: CanvasConnection }
  | { op: 'disconnect_nodes'; connectionId: string }
  | { op: 'select_nodes'; nodeIds: string[] }
  | { op: 'set_viewport'; viewport: CanvasViewport }
  | { op: 'run_generation'; nodeId: string; generationType: string; metadata?: Record<string, unknown> }
```

## Interaction Notes

- All visible nodes live inside a world layer transformed with `translate(x, y) scale(k)`.
- Wheel zoom should preserve the world coordinate under the pointer.
- Grid should be computed from the viewport transform rather than fixed screen pixels.
- Node metadata should link to YLCraft project ids, content ids, asset ids, prompt text and generation logs, but the canvas should not duplicate full project records.

## Agent Notes

Agent tools should emit operations, not mutate React state directly. Write-like operations require review if they create project content, generate paid media or delete nodes. Read-only operations such as listing canvas nodes should not require confirmation.
