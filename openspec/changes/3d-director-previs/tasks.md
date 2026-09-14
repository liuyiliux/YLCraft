# Tasks

## Phase 0: Design and research

- [x] 1. Survey 3D director/previs references and record license boundaries in `F:\PycharmProjects\YLCraft-refs\README.md`.
- [x] 2. Define the product boundary: previs is a project-storyboard spatial layer, not a second Story page, Asset Hub, Canvas document, or DCC tool.
- [x] 3. Define `PrevisSceneDocument`, stable node/camera IDs, transforms, locks, revision, and future keyframe contract.
- [x] 4. Define the screenshot return path: active camera capture -> Asset Hub -> `ProjectAssetLink` -> storyboard panel -> existing image/video reference fields.
- [x] 5. Write design, requirements, acceptance criteria, and Phase 1 scope.

## Phase 1: Static director desk

- [x] 6. Add `PrevisSceneDocument` persistence, Alembic migration, API schemas, CRUD endpoints, focused backend tests, and API surface documentation.
- [x] 7. Add a 3D previs entry from `/story` storyboard panels; find or create scenes by project/content/panel identity.
- [x] 8. Extract or extend reusable 3D scene primitives from `Model3DViewer` without moving Story business state into the generic viewer.
- [x] 9. Implement Asset Hub model insertion, lightweight human proxies, primitives, panoramic/background references, layer visibility, rename, delete, and lock.
- [x] 10. Implement director view, active camera view, camera CRUD, transform/FOV controls, safe frame, and rule-of-thirds overlays.
- [x] 11. Capture the active camera to PNG/WebP, import it into Asset Hub with previs provenance, and link it to the originating storyboard panel as a selectable reference.
  - _2026-09-14 完成（后端 + 前端）：_
    - _新增 `POST /api/v1/previs/scenes/{scene_id}/capture`（multipart）：顺序固定为「场景 + 活动机位 → 浏览器截图 → Asset Hub 图片 → `ProjectAssetLink(role=storyboard_reference)` → 分镜面板」。_
    - _**溯源由服务端从场景派生**（`scene_revision` 取行上的 revision、`source_asset_ids` 取场景节点的 `assetId`、`camera_id` 校验必须在场景机位表内），不采信客户端——否则「这张图出自哪一版场景」不可信。_
    - _**失败语义分离、不制造半成品关联**：上传失败则既不产生资产也不产生关联（503）；上传成功但关联失败返回 `linked=false` + `link_error` + 可重试字段（`asset_id`/`content_id`/`role`/`relation`/`provenance`），可用既有 `POST /creative-projects/{id}/assets` 以同一 metadata 重试。独立场景（未绑定分镜）直接 400 拒绝，而不是建悬空关联。_
    - _**前端截图能力**：`SceneViewport` 新增 `onCaptureReady`，用 `onCreated` 把截图函数交给上层；实现**先同步渲染一帧再 `toDataURL`**（默认 `preserveDrawingBuffer=false`，异步读取会得到空白画布）。安全框/九宫格是 HTML 叠加层，天然不进 canvas，符合「辅助线只写视图不写事实」。_
    - _预演台顶栏新增「截图回流」按钮：**仅「活动机位」视图可用**（截的就是该机位画面），导演视角与未绑定分镜的场景下禁用并给出原因提示。_
    - _**「as a selectable reference」这半句原本不成立**：截图用的 role `storyboard_reference` 不在参考选择的白名单里，导致「关联成功却选不到」。已把该白名单从 5 处重复定义收敛为每侧一份常量（后端 `REFERENCE_LINK_ROLES`、前端同名常量），并把 `storyboard_reference` 纳入；自动选择里给 +12 分（高于通用参考 +4，低于提示词点名 +20/+30，避免压过角色一致性）。_
    - _验证：`pytest tests/test_previs_scenes.py` **15 passed**（新增 7 例：独立场景 400 / 未知机位 400 / 非法格式 400 / 顺利路径的服务端溯源与文件落盘 / 部分失败不伪造成功 / 上传失败不留痕 / 场景不存在 404）；前端 `utils.test.ts` 5 例固定白名单行为；**浏览器端到端**：导演视角按钮禁用 → 切活动机位后可用 → 点击得到「截图已入库并关联到当前分镜」，`POST …/capture` 返回 `linked=True`，0 个 >=400、0 条 console error。_
- [x] 12. Verify captured references enter the existing storyboard image/video generation request path without duplicate content, assets, or task records.
  - _2026-09-14 核实满足：_
    - _截图以 `role=storyboard_reference` 进入分镜参考通道（见 #11 的白名单收敛），`selectReferenceAssetsForPrompt` 与手动选择器都取它；后端 `_project_reference_assets` 的 4 处调用（正文/脚本/分镜/漫画页的生成参考清单）同样纳入。_
    - _**不产生重复 content / asset / 任务记录**：一次截图只建 1 个 Asset Hub 资产 + 1 条 `ProjectAssetLink`，不写 `ProjectContent`（Asset Hub 素材与原项目内容分属不同表）；端点全程不触碰任务账本（无 `queue.create_task`），因为这是本地上传而非生成任务。_
    - _实测证据：`GET /creative-projects/{id}/assets` 中该资产只有 **1 条**关联（role=storyboard_reference、relation=derived_from、content_id 指向分镜），重复调用会各自新增一条独立记录（每次截图是新资产，不去重也不覆盖）。_
- [x] 13. Add desktop and narrow-screen UI validation, focused backend/frontend tests, and document the module/API changes.
  - _2026-09-14 完成：_
    - _**后端聚焦测试**：`tests/test_previs_scenes.py` 8 → **15 例**（新增 7 例覆盖截图端点的全部分支，见 #11）。_
    - _**前端聚焦测试**：新增 `frontend/src/pages/story/utils.test.ts` **5 例**，固定「预演截图必须可被选为参考」这一行为（含优先级：点名角色 > 预演截图 > 通用参考，以及 `output` 必须被排除）。`npm test`（vitest）5 文件 **44 例通过**。_
    - _**UI 验证（桌面 + 窄屏）**：1440×900 与 900×800 下均 canvas 渲染、截图入口可见、**无横向溢出**（scrollWidth == innerWidth）；0 个 >=400、0 条 console error。_
    - _**文档同步**：`tools/generate_api_surface.py` 重新生成 `API_SURFACE.md` + `api_surface.json`（**679** 端点，+1 即 capture，已入清单）；架构 §4.4.5 补「截图回流已落地」的完整说明（含两处设计选择与 role 白名单收敛）。_
    - _`npm run build` 通过（3824 模块）；lints 干净。_

## Phase 2: Dynamic previs

- [x] 14. Add scene duration, 24fps playhead, transform and camera keyframes, slerp rotation interpolation, and persisted scene operation history.
  - _2026-09-14 完成。_
  - _**过程中发现一个前置缺口（本条之前不存在）**：节点变换在 UI 里**根本改不了**——没有拖拽手柄、也没有位置/旋转/缩放输入框，只有相机的有。也就是说「给角色/道具打关键帧」当时没有输入路径（所有节点永远停在默认位置）。已一并补上：图层面板可选中节点，选中后有变换面板（位置/旋转°/缩放）+ 3D `TransformControls` 手柄（移动/旋转/缩放三模式）；旋转在数据里存四元数（design 要求，避免欧拉角插值翻转），但**编辑用角度**，转换只发生在输入输出边界。_
  - _契约按 design §4.1 实现**逐通道**关键帧（`property` = position/rotation/scale/camera_target/camera_fov/animation_clip，`interpolation` = linear/step/slerp），而不是整帧快照——只动位置时不该连带把缩放钉死。`animation_clip` 取值先保留，实现在 #15。_
  - _求值收在纯函数模块 `frontend/src/pages/previs/timeline.ts`（无 React / three 依赖，可单测）。三条约定：① **插值方式取自前一个关键帧**（区间由它起始），与主流动画工具的 F-curve 一致；② 边界不做循环——首帧前保持首帧、末帧后保持末帧，避免场景外出现意料之外的运动；③ **坏数据只丢当前通道**（退回前一个值），不抛错也不产出 NaN。_
  - _`slerpQuaternion` 处理三个必错的点：**取最短路径**（`dot < 0` 取反，否则 350°→10° 会绕远路 340°、画面上表现为镜头原地翻半圈）、**近平行退化为线性**（`dot → ±1` 时分母趋于 0，直接除得 NaN）、**结果归一化**（浮点误差累积会让模型缓慢缩放/倾斜）。_
  - _**打点/自动打点的规则**：按**通道**判断而不是按目标——该通道已有关键帧则在当前帧打点/更新，否则改静态值。这样有两个好处：① 给位置打点不会顺带把缩放也钉死；② 拖动一定有反馈，不会出现「拖了却被时间轴顶回去」这种让人以为工具坏了的情况。_
  - _**面板显示求值后的值**：节点与机位的变换面板都读当前帧的求值结果。若显示静态值而画面用插值结果，打了点后就会出现「面板写 0、画面在 5」。机位另有取舍：**FOV 一旦有关键帧（即变焦），焦距输入被禁用**——镜头由 FOV 驱动，两处可改会互相打架。_
  - _**性能取舍**：位姿由 `SceneViewport` 的 `useFrame` 逐帧求值，`playheadRef` 才是渲染的事实来源；React 侧只按约 10Hz 同步一次读数。若播放时每帧 setState，图层面板与机位面板（几十个 antd 控件）会跟着每秒重渲染二十多次。_
  - _操作历史按 design §5.3 的 `PrevisOperation` 词表实现并**随场景 JSON 持久化**（design §4.1 要求可撤销性不能只存在浏览器里），上限 200 条防无界增长。**偏离一处并已标注**：词表补了 `remove_node`/`add_camera`/`remove_camera`/`set_duration` 四个 design 未列的操作——那份是面向 Agent 的写操作，而本地编辑确实会产生删节点/增删机位/改时长；**不为迁就词表而漏记删除**（一份漏掉删除的记录会让人误以为"这个节点一直在"）。删节点/机位时会一并清掉它的关键帧，不留指向已删目标的孤儿数据。_
  - _`durationFrames` 的兼容处理：既有场景从未写过这个字段（一律 0），0 视为「未设置」补默认 96 帧（4 秒 @24fps）——否则时间轴长度为 0，播放头无处可放。_
  - _测试：新增 `frontend/src/pages/previs/timeline.test.ts` **26 例**——slerp 两端取值/90° 中点 45°/**350°→10° 中点必须是 0° 而非 180°**/结果归一化/近平行不产 NaN；通道按目标与属性双重过滤、同帧后写生效；取样端点保持、区间线性、step 保持、旋转 slerp、数值通道线性、坏数据退回前值；逐通道独立（给位置打点不影响缩放）；机位位置/目标点/FOV 可动画；帧秒换算与 clamp；归一化丢非法关键帧、旋转缺省插值为 slerp、操作历史过滤非法类型。_
  - _验证：`npx vitest run` → **87 passed（7 文件）**（原 61 例 + 新增 26 例）；`npm run build`（`tsc --noEmit` 两个 tsconfig + vite）**通过**，3826 模块；lints 干净。_
  - _**浏览器端到端 18/18**（真实 Chromium）：加几何体后自动选中并可读变换面板 → 第 0 帧设 X=4 并打点 → 播放头移到中段改 X=10（**自动打点**）→ 保存后落库确为 `[(0,[4,0.5,0]), (48,[10,0.5,0])]` 两条 → **回到第 24 帧读到 X=7**（4 与 10 的中点，精确吻合，证明「自动打点 → 逐帧求值 → 线性插值 → 面板回显」整条链路打通）→ 播放使播放头从 24 前进到 54 → 操作历史含 add_node/add_keyframe 且已落库 2 条 → 重载后关键帧仍为 2 条。全程 **0 个 >=400、0 条 console error**。_
  - _tsc 抓到我自己的 4 个错误（vitest 不做类型检查，测试没暴露）：其中一个是**真 bug**——`recordOperation` 定义在 `addCamera`/`deleteCamera` 之后，而 `useCallback` 的依赖数组是渲染时立即求值的，会在初始化前访问它并**直接抛错导致页面白屏**；已把它的定义移到所有使用者之前并注明原因。另一个是四元数线性插值误用 `lerpVec3` 的非法类型转换，改为通用的逐分量插值。_
- [x] 15. Reuse existing rigged-model animation clips as scene playback selections without claiming editable skeletal animation.
  - _2026-09-14 完成。_
  - _**按帧同步，而不是自由播放**——这是本条最重要的取舍。现有 `Model3DViewer` 用的是 `action.reset().fadeIn().play()`（自己按墙上时钟推进），但预演台必须把播放头折算成秒喂给 `mixer.setTime()`：自由播放会让"同一帧"在不同时刻呈现不同姿态，多角色动作也无法对齐，预演就失去参考价值；而 `setTime` 每次都从 0 重新推进到 t，因此**同一帧永远是同一姿态**。这一点由端到端测试固定（见下）。_
  - _只**引用**模型自带的 `AnimationClip`（GLTF 提供），不创建也不修改任何动画数据；存的是 clip 名字。UI 明确写出「预演台只做选择与按帧播放，**不编辑骨骼动画**」，与 design「动作播放状态不能伪装成可编辑骨骼动画」一致。_
  - _契约复用 #14 已保留的 `animation_clip` 通道，缺省插值为 **`step`**（换动作是离散事件，走→跑不该"渐变"；且字符串值本来也只能按 step 解释）。因此**可以按帧切换动作**：打过点就按关键帧走，否则用 `node.metadata.animationClip` 静态选择——与其它通道同一套"按通道判断"规则。_
  - _实现细节两处：① clip 关键帧用 `useMemo` 预排序一次、配 `sampleFromKeys` 逐帧解析（新抽出的函数，避免每帧重新过滤 + 排序 + 建 Map）；② `activeRef` 只在 clip **变化时**才 stop/play，避免每帧重置混合。另修复 `AssetModelMesh` 里既有的**条件调用 hook**（`if (!modelUrl) return null` 后才 `useGLTF`）——判断上移到父组件，hook 顺序始终稳定。_
  - _测试：`timeline.test.ts` 新增 11 例——`animation_clip` 缺省插值为 step、字符串通道两帧之间保持前值切帧才换、未打点回落静态选择、**倒序写入（先 48 后 0）仍正确**、动画通道不干扰同节点的变换通道、`sampleFromKeys` 与 `sampleChannel` 结果一致、`currentChannelValue` 的动画分支（含一条专门固定下述缺陷的用例）。_
  - _验证：`npx vitest run` → **98 passed（7 文件）**；`npm run build` 通过（3826 模块）；lints 干净。_
  - _**浏览器端到端 14/14**（真实 Chromium + 内置 `vanguard.glb`，它自带 Idle/Run/TPose/Walk 四条 156 通道动画）：切到 Vanguard 后「动作」行出现并上报 4 条 clip（`ue-mannequin.glb` 有骨骼但无动画，正确不出现）→ 选 Walk → **第 0 帧截图 183874 B，中段 183262 B（姿态确实在变），再拖回第 0 帧仍是 183874 B 且逐字节相同** → 第 0 帧给动作打点、中段改选 Run 后落库为 `[(0,'Walk','step'), (48,'Run','step')]` → 重载后重新选中节点仍能拿到动作列表且回显 `Walk`。全程 0 个 >=400、0 条 console error。_
  - _**端到端测试抓到一个真缺陷（单测没覆盖到）**：`currentChannelValue` 起初只处理 `position`/`rotation`/`scale` 与机位通道，动作通道落到末尾返回 `undefined`，而 `addKeyframe` 拿到 `undefined` 就直接不写——表现为**「按了钥匙什么都没发生」且没有任何提示**。已补上动画分支并加了一条专门固定它的单测（断言返回空串而非 `undefined`，并把成因写在注释里）。_
  - _另：端到端脚本首轮还报「重载后动作列表消失」，核查后确认是**产品正常行为**——选中状态是会话内局部状态、不入库，所以重载后要重新点一下图层行面板才出现；已改测试步骤而非改产品。_
- [ ] 16. Evaluate frame capture and MP4/WebM export only after static capture is stable; document browser and cost constraints.
- [x] 24. Upgrade `PrevisCamera` from FOV-only to real optics: focal length, sensor format, and computed depth of field, so a framing reference means the same thing to a DP as it does to the tool.
  - _调研依据：FrameForge 与 Previs Pro 唯一重合的核心卖点就是「镜头光学是一等数据」（真实镜头型号、传感器尺寸、景深）。而 `PrevisCamera` 原来只有 `fov`——**同一个 fov 在 Super 16 和 Alexa LF 上是完全不同的取景**，所以那时的"机位参考"给不出可直接执行的信息。_
  - _范围：数据契约 + 机位面板 + 视口口径一致。景深只做**计算与读数**（近界/远界/超焦距），不做景深模糊渲染（design 非目标：不做专业渲染器）。_
  - _向后兼容：既有场景只有 `fov`。载入时按默认画幅从 `fov` 反推出等效焦距——给定画幅下 `fov ↔ 焦距` 是双射，这是**同一取景的等价重述**，不是编造数据。_
  - _2026-09-14 完成：_
    - _新增纯函数模块 `frontend/src/pages/previs/optics.ts`（无 React / three 依赖，可单测）：7 种画幅表（全画幅、Super 35、Alexa LF、APS-C、M4/3、Super 16、2x 变形宽银幕，变形按 `width × squeeze` 展开横向有效宽度）、`fov ↔ 焦距` 双向换算、弥散圆（对角线/1500）、景深（近界/远界/超焦距）。_
    - _**`focalLength` + `sensorFormat` 是事实，`fov` 由它们推出**；反向改 `fov` 时回算焦距。三者若不一致，就会出现「面板写 85mm、视口却是 24mm 口径」的参考图——而口径错等于参考没有意义。为此拆出 `updateCameraOptics`（由光学推 fov）与 `updateCameraFov`（由 fov 回算焦距）两个入口。_
    - _面板：画幅下拉、焦距输入（含 14/18/24/28/35/50/85/135 预设 Tag，当前值高亮）、T 光圈、对焦距离，以及一行读数「水平视角 X° · 景深 N – M（超焦距 H）」。导演视角额外显示活动机位的**视锥线框**（`CameraHelper`），让焦距变化在机外可见——它只作视图参考，不进场景保存、也不参与截图。_
    - _**一个如实标注的精度边界**：换算结果收敛到 1 位小数（fov 到 0.1°、焦距到 0.1mm），以便面板与落库 JSON 可读。代价是往返有极小损失（135mm → 15.2° → 134.9mm）。0.1mm 对真实镜头无意义（镜头本身也不按 0.1mm 标注），且实测**反复换算不累积漂移**（改光圈/对焦都会走一次换算，fov 读数保持稳定）；测试断言的是「显示精度内互逆」，不是数学严格互逆。_
    - _改焦距 → 水平视角随之变化的端到端实测：35mm 全画幅得 **54.4°**（2·atan(36/70)），85mm 得 **23.9°**（2·atan(36/170)），与公式吻合。**超焦距比值 89.5/15.20 = 5.89 与 (85/35)² = 5.90 一致**（超焦距正比于焦距平方），长焦景深 2.91–3.10m 明显浅于 35mm 的 2.51–3.73m——整条光学链路自洽，不是把数字摆上去而已。_
    - _测试：新增 `frontend/src/pages/previs/optics.test.ts` **17 例**（画幅与弥散圆含全画幅 0.029mm 教科书值、变形宽银幕宽度展开、换算与教科书值吻合、同 fov 不同画幅对应不同焦距、显示精度内互逆、反复换算不漂移、景深已知算例 2.74–3.32m、光圈/焦距对景深的影响、越过超焦距远界为 ∞ 并格式化为 ∞、无解返回 null、`normalizeCamera` 向后兼容不改既有取景且冲突时以光学为准）。_
    - _验证：`npx vitest run` → **61 passed（6 文件）**（原 44 例 + 新增 17 例）；`npm run build`（两个 tsconfig 的 `tsc --noEmit` + vite）**通过**，3825 模块；lints 干净。_
- [x] 25. Implement the `light` node kind already declared in the contract but silently ignored.
  - _现状（本项属 Phase 1 补漏）：`PrevisNodeKind` 与 design 都声明了 `'light'`，`NODE_KIND_LABEL` 也有「灯光」，但 `SceneViewport` 的 `NodeMesh` 没有 light 分支、编辑器也没有创建入口——**节点建了不生效、且不报错**。_
  - _调研依据：Cine Tracer 证明「灯光预演」是分镜工具普遍忽略、却真实存在的独立缺口（DP 想在装车前看到大致光效）。_
  - _2026-09-14 完成：_
    - _`NodeMesh` 新增 light 分支，支持**点光 / 聚光 / 平行光**（颜色、强度、衰减距离；聚光另有锥角与半影）。平行光在 three 里由「灯位 → 原点」决定方向，所以用节点位置当灯位，与"在场景里摆一盏灯"的直觉一致。三种灯都投影——不投影的灯在本工具里等于没有效果，预演要的就是看光。_
    - _`readLightConfig` 统一补齐缺失字段（渲染与面板共用同一份读取，避免"面板显示 12、画面用的是别的值"）。_
    - _编辑器侧新增「灯光」下拉入口；配置控件（类型/颜色/强度）抽成 `LightNodeControls` 放在图层行**下方**而非行内——图层面板只有 280px，塞进去会把名称输入框压到不可用。_
    - _**顺带补上真实阴影**（此前全仓 `castShadow` 为 0、Canvas 未开 `shadows`，画面发平，灯不投影则等于没用）：Canvas 开 `shadows="soft"`，默认平行光与灯光节点均投影，几何体/平面/载入模型（含 GLB，逐 mesh 打开）设 `castShadow`/`receiveShadow`。同时移除 `ContactShadows`——它本来是在没有真阴影时代替地面接纳影的，如今真阴影与它会叠出双层影子。_
    - _端到端实测（浏览器）：从「灯光」下拉添加点光后图层出现该节点、颜色选择器与强度滑块就位；保存后重载，灯光节点仍在。全程 0 个 >=400、0 条 console error。_

## Phase 3: Agent director assistant

- [ ] 17. Add a read-only previs scene summary to Agent context with stable IDs and lock state, phrased so it can answer **coverage** questions ("which storyboard panels have no previs scene yet", "which cameras/nodes are locked") rather than only listing nodes.
  - _调研依据：Storyflow 的差异点是「AI 读整块板而非单帧」——能跨序列回答「哪些镜头还没预演」。只罗列节点，等于把单帧能力包装成整板能力，Agent 仍然回答不了覆盖度问题。_
- [ ] 18. Add a reviewed `PrevisOperation` Tool contract with expected revision, lock validation, confirmation diff, Agent Run trace, and focused authorization tests.

## Acceptance criteria for Phase 1

- [x] 19. A storyboard panel can create, close, reload, and reopen the same previs scene.
  - _2026-09-14 实测通过：同一 scene_id 关闭（导航离开）后重新打开，仍加载同一场景——标题正确、相机面板值一致。_
- [x] 20. A scene restores asset references, object/camera transforms, visibility, locks, and active camera after refresh.
  - _2026-09-14 实测通过（浏览器，非只看代码）：新建场景写入 position `[4,2.5,5]` / target `[0,0.8,0]` / fov `45`、2 个节点；刷新重开后相机面板实测值为 `["4","2.5","5","0","0.8","0","45"]`——**逐值吻合**；图层里两个节点（`立方体`/`人物`）均在。_
    - _一处方法学提醒（我这次先踩了）：节点名与相机数值都在**输入框**里，用 `inner_text` 读会得到「0 个节点」的假失败；必须读控件 `value`。_
- [x] 21. Director and active-camera views show the same scene; safe frame and rule-of-thirds overlays remain view-only.
  - _2026-09-14 实测通过：导演视角与活动机位下各渲染 1 个 3D canvas（同一场景）；安全框/九宫格以 `position:absolute` + `pointer-events:none` 的 HTML 叠加层实现，实测存在且**只读**（不参与场景保存，也不进 canvas 截图）。_
- [x] 22. A camera capture creates an Asset Hub image with `previs_scene_id`, camera, revision, and source-asset provenance, then links it to the originating storyboard panel.
  - _2026-09-14 实测通过：截图落库后 `GET /assets/{id}` 显示资产文件位于 `storage/uploads/previs/<uuid>/previs-capture.png`；`GET /creative-projects/{id}/assets` 中该资产的关联 metadata 实测为 `{"source":"previs_capture","previs_scene_id":"10f1ba5b…","camera_id":"cam-1","scene_revision":1,"source_asset_ids":[]}`，`role=storyboard_reference`、`relation=derived_from`、`content_id` 指向来源分镜。`scene_revision` 由服务端派生（测试里先保存一次把 revision 推到 2，断言得到 2）。_
- [x] 23. The linked capture can be selected by existing storyboard image/video generation flows without creating duplicate project content or task ledgers.
  - _2026-09-14 核实并修好一个真实缺口：截图虽已关联，但参考选择按 role 白名单过滤，而 `storyboard_reference` **不在白名单内**（该白名单在 5 处各写一份），因此**关联成功却选不到**。已收敛为每侧一份常量并纳入该 role；前端 5 例单测固定该行为。**不产生重复 project content 或任务账本**：一次截图 = 1 资产 + 1 关联，不写 `ProjectContent`、不建任务。_
