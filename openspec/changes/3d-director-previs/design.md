# Design

## 能力定位

3D 导演预演台是项目分镜的空间预演层：它读取既有项目、分镜和 Asset Hub 事实，生成独立的 `PrevisSceneDocument`，再把当前机位截图作为有 provenance 的图片资产回流到分镜。

它不属于模型生成/绑骨任务账本，也不属于自由 Canvas 文档。

## 页面与入口

- 入口位于 `/story` 当前分镜面板，动作名为“3D 预演”。
- 打开时按 `project_id + storyboard_content_id + panel_number` 查找场景；不存在则创建一个空场景。
- 预演场景可以复用 `/model-3d` 已有的模型加载、动画、灯光、网格和部位显隐基础设施，但不把分镜业务状态加入 `Model3DViewer`。
- `/canvas` 后续只增加“引用预演截图/打开预演场景”的桥接，不保存空间状态。

## 场景数据契约

```ts
interface PrevisSceneDocument {
  id: string
  projectId: string
  storyboardContentId?: string
  panelNumber?: number
  title: string
  fps: 24
  durationFrames: number
  activeCameraId: string
  nodes: PrevisNode[]
  cameras: PrevisCamera[]
  keyframes: PrevisKeyframe[]
  settings: PrevisSettings
  revision: number
  createdAt: string
  updatedAt: string
}

interface PrevisNode {
  id: string
  kind: 'asset_model' | 'human_proxy' | 'primitive' | 'panorama' | 'light'
  name: string
  assetId?: string
  transform: {
    position: [number, number, number]
    rotation: [number, number, number, number]
    scale: [number, number, number]
  }
  visible: boolean
  locked: boolean
  metadata: Record<string, unknown>
}

interface PrevisCamera {
  id: string
  name: string
  transform: {
    position: [number, number, number]
    rotation: [number, number, number, number]
  }
  target?: [number, number, number]
  fov: number
  locked: boolean
}
```

约束：

- 节点和相机 ID 创建后稳定；名称不可作为操作目标。
- 旋转使用四元数存储。
- 场景只保存 Asset Hub 的 `asset_id` 和必要展示快照，不复制二进制。
- `locked` 是业务字段；任何未来 Agent 写操作都必须尊重它。
- `revision` 用于并发保护，写入请求必须携带 `expected_revision`。
- Phase 1 的 `keyframes` 可以为空，但字段保留给后续 24fps 时间轴。

## Phase 1 静态场景能力

### 节点

- 从 Asset Hub 添加 GLB/GLTF/OBJ/FBX 模型。
- 添加轻量人物占位和基础几何体，供人物站位和物品比例预演。
- 添加全景背景或背景图引用。
- 图层列表支持选中、显示/隐藏、锁定、删除和重命名。

### 相机

- 至少提供导演视角和当前机位视角。
- 支持新增、选中、重命名和删除机位。
- 支持位置、朝向、目标点、FOV 的基础调整。
- 支持安全框与九宫格叠加；辅助线只影响视图，不写入模型或项目事实。

### 截图回流

截图流程必须保持以下顺序：

```text
PrevisSceneDocument + activeCamera
  -> browser capture PNG/WebP
  -> Asset Hub image asset
  -> ProjectAssetLink(role=storyboard_reference)
  -> selected storyboard panel
  -> existing image/video generation reference
```

截图元数据至少包括：

```json
{
  "source": "previs_capture",
  "previs_scene_id": "...",
  "camera_id": "...",
  "frame": 0,
  "scene_revision": 3,
  "source_asset_ids": ["..."]
}
```

截图失败不得修改当前分镜或创建半成品关联；上传成功但关联失败时要保留可诊断错误和可重试入口。

## 后续阶段预留

- Phase 2：24fps 时间轴、位置/缩放/相机 FOV/目标点关键帧，旋转使用 slerp，动画 clip 只引用已有 Asset Hub 动画。
- Phase 3：Agent 只读场景摘要、受限 `PrevisOperation`、人工确认、锁定校验、revision 校验和 Agent Run trace。
- Phase 4：参考帧批量导出、浏览器 MediaRecorder/WebCodecs 或服务端 FFmpeg 评估。

这些能力不属于本 Phase 1 的完成标准。
