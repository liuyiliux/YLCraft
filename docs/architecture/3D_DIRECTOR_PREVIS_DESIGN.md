# 3D 导演预演台设计

## 1. 状态与目标

状态：Phase 1 静态导演台已落地（见 `openspec/changes/3d-director-previs/tasks.md` 任务 6-10）：`PrevisSceneDocument` 持久化（支持独立场景创建，无需项目）+ revision 并发保护、`/story` 分镜入口与顶级导航入口、可复用 3D 渲染原语、静态节点管理（Asset Hub 模型/可摆姿势的人形占位/几何体/全景背景/图层可见性/重命名/删除/锁定）、相机 CRUD（名称/位置/目标点/FOV/锁定）与导演/活动机位双视角、安全框/九宫格只读叠加。待相机拖拽回写、截图回流、关键帧与 Agent 导演助手（Phase 1 后续 / Phase 2-3）。

YLCraft 已有三块相邻能力：

- `/story`：项目正文、脚本、结构化分镜、分镜图与视频任务的业务事实来源。
- `/model-3d`：3D 模型生成、Asset Hub 入库、绑骨、动画播放、分层查看与部位显隐。
- `/canvas`：自由的创作工作流画布，用于编排素材、Prompt、生成和 Agent 操作，不承担项目分镜的唯一事实。

3D 导演预演台要补的是三者之间缺失的空间预演层：在生成分镜图或视频前，创作者把角色、道具、场景和机位摆进轻量 3D 空间，得到可复用的构图参考、镜头参数和后续动画预演。

它不是第二个 Story 页面、不是第二套素材库，也不是通用 3D DCC 软件。

## 2. 外部参考与采用边界

本设计只借鉴交互和数据建模思路，不复制外部源码。完整参考项目记录位于 `F:\PycharmProjects\YLCraft-refs\README.md`。

| 参考 | 借鉴点 | 不直接采用的原因 |
| --- | --- | --- |
| `jiguang132/storyai-3d-director-desk` | 导演/机位双视角、人物姿势占位、基础几何体、全景背景、安全框/九宫格、截图即分镜 | 先验证许可证后才可能参考实现；本项目只采用交互模型。 |
| `pengfeiqiao/kunpeng-director` | 稳定对象 ID、24fps、关键帧、人工锁定、可撤销操作、Agent 读取真实工程后操作 | 要和 YLCraft 的 Agent Run、确认和 ProjectContent 边界对齐，不能直接引入其工程模型。 |
| `awplanets/awplanet` | 骨骼姿势、电影化运镜、时间轴、虚拟拍摄 | PolyForm Noncommercial License，不可复制到商业用途代码；仅参考产品方向。 |
| `ddcat-ai/open-ai-canvas` | 角色资产、分镜、图片、视频、音频共同服务影视生产 | YLCraft 已有 Canvas 与 Story；只参考跨媒介工作流，不重复建设无限画布。 |
| `ganbo-gab/open-storyboard-canvas` | 导演台和分镜/生成结果共存的工作流 | 先确认许可、依赖和商业边界后才能复用任何代码。 |

## 3. 产品边界

### 3.1 要解决的问题

1. 把“谁站哪里、看向哪里、物体多大、镜头从哪里拍”的信息从自然语言 Prompt 前移为可见空间事实。
2. 从一个镜头的 3D 场景稳定产出构图参考图，作为现有分镜生图和图生视频的参考资产。
3. 让已绑骨或带动画的 Asset Hub 模型可用于轻量预演，而不是只在 `/model-3d` 单独查看。
4. 为后续关键帧、镜头运动和 Agent 可控预演留下稳定的数据契约。

### 3.2 明确不做

- 不替代 Blender、Unreal、Maya 等专业建模/动画工具。
- 不在 MVP 建地形雕刻、物理、复杂 IK、网格编辑或专业渲染器。
- 不复制 Story 的脚本、分镜文案、生成日志或项目关系图谱。
- 不让 Canvas 成为 3D 场景唯一状态；Canvas 只可引用或打开预演场景。
- 不让 Agent 直接覆盖人工锁定的位置、机位或关键帧。

## 4. 事实来源与数据边界

| 数据 | 唯一事实来源 | 预演台使用方式 |
| --- | --- | --- |
| 项目、章节、脚本、分镜面板 | `CreativeProject` / `ProjectContent` | 预演场景可绑定 `project_id`、`storyboard_content_id` 和 `panel_number`，也可为独立场景（三者全空，先摆思路无需项目）。 |
| 3D 模型、人物定妆、背景图、截图、视频 | Asset Hub | 场景节点仅保存 `asset_id` 和展示快照；不复制二进制。 |
| 绑骨/动画状态 | Asset 元数据与 `Model3DGenerationTask` | 仅作为可播放、可选动作和可视化能力，不重建任务账本。 |
| Prompt、图片/视频生成任务 | `ProjectGenerationLog` 和既有任务账本 | 截图被选择为参考时，使用既有 `ProjectAssetLink` 与生成 provenance。 |
| 自由工作流节点 | `CanvasDocument` | 可引用预演截图或通过入口打开预演台，不保存镜头空间状态。 |

### 4.1 新增的预演场景文档

进入实现时新增独立的持久化文档模型，例如 `PrevisSceneDocument`，而不是把整个场景 JSON 塞入 `ProjectContent.data`：

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
  transform: { position: [number, number, number]; rotation: [number, number, number, number]; scale: [number, number, number] }
  visible: boolean
  locked: boolean
  metadata: Record<string, unknown>
}

interface PrevisCamera {
  id: string
  name: string
  transform: { position: [number, number, number]; rotation: [number, number, number, number] }
  target?: [number, number, number]
  fov: number
  locked: boolean
}

interface PrevisKeyframe {
  id: string
  targetId: string
  frame: number
  property: 'position' | 'rotation' | 'scale' | 'camera_target' | 'camera_fov' | 'animation_clip'
  value: unknown
  interpolation: 'linear' | 'step' | 'slerp'
}
```

规则：

- `id` 生成后稳定不变，供 Agent、撤销记录、关键帧和 Asset Hub 血缘引用。
- 旋转存四元数，避免欧拉角插值翻转。
- `locked=true` 是业务数据，不是纯 UI 状态；后续 Agent 操作必须拒绝或要求显式人工解锁。
- 可撤销性在服务端操作层记录为 `PrevisOperation`，前端只做本地交互历史缓存，不能把浏览器历史当唯一事实。
- 场景本身不保存模型二进制、截图二进制或复制 Asset Hub 元数据。

### 4.2 截图回流契约

“截图即分镜”必须走现有资产和项目关联边界：

```text
PrevisSceneDocument + activeCamera
  -> canvas capture PNG/WebP
  -> Asset Hub image asset
  -> ProjectAssetLink(role=storyboard_reference)
  -> selected ProjectContent storyboard panel
  -> existing image/video generation reference fields
```

这样截图既能在分镜面板中选择、也能在素材库复用，同时保留 `previs_scene_id`、`camera_id`、`frame`、场景 revision 和源资产 ID 的 provenance。

## 5. 用户工作流

### 5.1 静态构图 MVP

1. 在 `/story` 的某个结构化分镜面板点击“3D 预演”。
2. 若该分镜还没有预演场景，创建并绑定一个场景文档；默认继承面板的景别、机位、角色和场景描述作为提示，不把文本自动变成空间事实。
3. 在预演台添加 Asset Hub 模型、人形姿势占位、基础几何体、全景背景和机位。
4. 在“导演视角”摆放，在“机位视角”检查画面；显示比例安全框和九宫格。
5. 截图并选择“设为本分镜参考图”。截图入 Asset Hub、关联当前面板，再打开既有的生图或图生视频动作。

### 5.2 动态预演

1. 对角色、道具或机位设置关键帧。
2. 在统一时间轴播放；对象使用位置/缩放线性插值，旋转使用四元数球面插值。
3. 对有动画的模型选择动画 clip；动作播放状态不能伪装成可编辑骨骼动画。
4. 先支持逐帧预览和参考帧截图；视频导出应在静态截图链路、帧稳定性和浏览器兼容验证后再做。

### 5.3 Agent 协作

Agent 的角色不是“凭文本臆造镜头”，而是先读取真实场景摘要和稳定 ID，再生成受限操作建议：

```ts
interface PrevisOperation {
  type: 'add_node' | 'update_transform' | 'set_camera' | 'add_keyframe' | 'remove_keyframe' | 'capture_reference'
  targetId?: string
  payload: Record<string, unknown>
  expectedRevision: number
}
```

- 写操作沿用 Agent 的确认和 trace 体系。
- 操作必须带 `expectedRevision`，防止过期 Agent 覆盖人工编辑。
- 被锁定的节点/相机只能读取，不能更新。
- Agent 生成的操作先在预演台显示差异预览，用户确认后才落库。

## 6. 复用现有模块

| 现有模块 | 预演台复用方式 | 不应承担的职责 |
| --- | --- | --- |
| `Model3DViewer` | GLB/FBX/OBJ 加载、场景图层、动画播放、部位显隐、灯光/网格/视角基础设施 | 不继续堆积 Story 业务、分镜保存逻辑或时间轴状态。 |
| `/model-3d` | 作为模型生成、绑骨、素材入场的资产工作台 | 不变成项目分镜编辑器。 |
| `/story` | 分镜面板入口、项目/章节上下文、参考图和视频生成回流 | 不维护独立 3D viewer 状态。 |
| Asset Hub | 模型、背景、截图、结果视频和来源血缘 | 不保存场景 JSON。 |
| `/canvas` | 将预演截图作为可复用图片节点；可添加“打开预演场景”引用节点 | 不保存对象变换/相机/关键帧真相。 |
| Agent Runtime | 提议并确认结构化预演操作、记录 trace | 不绕过锁定或直接写前端临时状态。 |

## 7. 分期实施

### Phase 0：设计与接口契约

- 明确 `PrevisSceneDocument`、节点、相机、关键帧和截图 provenance schema。
- 在 OpenSpec 中定义场景和截图回流 acceptance criteria。
- 确认所有参考项目许可证；任何代码搬运必须单独审查。

### Phase 1：静态导演台（最小价值版本）

- 在分镜面板增加“3D 预演”入口，按项目/分镜面板创建和打开预演场景。
- 新增导演视角 / 机位视角切换、相机预设、比例安全框/九宫格。
- 支持从 Asset Hub 添加模型、添加低成本人形姿势占位、基础几何体和全景背景。
- 支持移动/旋转/缩放、图层可见性与锁定。
- 支持截图入 Asset Hub 并关联到当前分镜面板；从该截图进入既有生图/视频链路。

Phase 1 完成标准：一个项目分镜面板可稳定产出可追溯参考图，参考图刷新后仍能在项目、素材库和后续生成请求中找到。

### Phase 2：受控动态预演

- 每场景只启用 24fps；支持时长、播放头、逐帧、关键帧增删。
- 支持对象 transform、相机 target/FOV、动画 clip 的基础关键帧。
- 提供场景级撤销/重做和 revision 冲突提示。
- 先完成参考帧截图；浏览器视频导出作为实验能力，不让它阻塞核心分镜生成工作流。

### Phase 3：Agent 导演助手

- 将预演场景摘要作为只读上下文提供给 Agent。
- 新增受限的场景操作 Tool schema、锁定校验、revision 校验和确认差异预览。
- 将已确认操作写入 Agent Run steps 与场景操作历史。

### Phase 4：供应商动作与高级输出

- 结合已验收的腾讯绑骨模型，映射动画 clip 和动作预设。
- 评估浏览器 `MediaRecorder`/WebCodecs 视频导出、FFmpeg 服务端导出和成本边界。
- 增加批量镜头参考帧和多机位 shot list，但不自动覆盖已有分镜文字或图片。

## 8. 需要提前避免的错误

1. 不要把“导演台”塞进现有 `/model-3d`，否则模型生成/绑骨和项目镜头编辑会互相挤压。
2. 不要以 `ProjectContent.data` 保存完整 3D scene JSON；分镜版本与空间编辑频率不同，会制造无意义的大版本和冲突。
3. 不要使用纯字符串名称作为 Agent 或关键帧目标；必须使用稳定 ID。
4. 不要让 Agent 的建议直接改变相机或角色位置；必须走 revision、locked 校验和确认。
5. 不要先做 MP4 导出；先证明静态构图截图能显著改善现有分镜图/视频生成的可控性。
6. 不要复制 awplanet 或任何许可证不兼容项目的代码；许可证与依赖必须在源码引入前审查。
7. 不要把预演视图与项目关系图谱、自由 Canvas 混成同一个页面或状态模型。

## 9. 验收指标

Phase 1 的人工验收至少覆盖：

- 新建项目分镜面板可创建、关闭、刷新和重新打开同一个预演场景。
- 3D 模型、基础占位物、相机变换和锁定在刷新后保持一致。
- 导演视角与机位视角呈现同一场景；安全框和九宫格不影响模型操作。
- 截图生成 Asset Hub 图片，并能成为当前分镜面板的参考图。
- 从该分镜发起的生图/视频请求能记录截图 Asset ID 与 `previs_scene_id` provenance。
- 不存在第二份项目分镜、角色、素材或任务事实。

后续 Phase 2/3 增加：关键帧插值稳定、锁定拒绝 Agent 修改、revision 冲突可见、所有 Agent 写入可回放。
