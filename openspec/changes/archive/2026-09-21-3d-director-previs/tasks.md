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
- [x] 16. Evaluate frame capture and MP4/WebM export only after static capture is stable; document browser and cost constraints.
  - _2026-09-14 完成（评估 + 记录约束），完整报告见 `docs/research/research_report_previs_export_feasibility.md`。结论与实测数据摘要：_
  - _**真正的瓶颈不是浏览器支持，而是视口帧率。** 能力层面全部就绪（`captureStream` / `MediaRecorder` / `VideoEncoder` 均可用，连 `video/mp4;codecs=avc1` 都支持）。但在有真实负载的场景（Vanguard 骨骼模型 + 阴影 + 聚光 + 位移动画）上，**播放时 17% 的帧超出 24fps 预算**（p95 66.5ms vs 预算 41.7ms），并行编码时 **35% 超预算**、平均只剩 25.7fps。_
  - _**因此 MediaRecorder 实时录制不作为主路径**：它按**墙上时钟**打时间戳，视口稳定不了 24fps 就会录出一条时长漂移、节奏不匀的视频——等于把 #14/#15 辛苦建立的"同一帧永远是同一姿态"这个性质丢掉。改成 `captureStream(0)` + `track.requestFrame()` 手动喂帧能控制"抓哪一帧"，但 **MediaRecorder 的时间戳仍按墙钟**，快速批量喂帧会得到时长错误的视频。_
  - _应走**确定性离线导出**（逐帧渲染→逐帧取图→服务端按固定帧率合成）：离线可以慢，但每帧都来自指定帧号，输出必然是准确 24fps。实测 96 帧（4 秒 @24fps）约 **3.6 秒 / 9.4 MB**（JPEG 方案）。_
  - _**格式要分开**：单帧截图保持 PNG（单张、要当生图结构参考，无损有价值，71ms/1.4MB 不是问题；JPEG 的有损压缩反而可能给下游 AI 引入它自己会放大的伪影）；**批量导出才用 JPEG**——96 帧 PNG 是 132MB/6.8s，JPEG(q0.92) 只有 9.4MB/1.6s。另测出一个反直觉点：**WebP 编码比 JPEG 慢 9 倍**（154ms vs 17ms），体积只小一半，批量导出不划算。_
  - _**测量方法上的一个坑（我差点据此下错结论）**：首轮在 headless 下量到 19fps 并准备写进报告，核查渲染器后发现 headless 走 **SwiftShader 软件渲染**，带界面才是真实 GPU（Intel UHD），**两者差 2.6 倍**。报告因此把两种情况都列出，结论建立在真实 GPU 那一栏。_
  - _**成本结论：这条链路零 API 额度**——客户端编码是本地算力，服务端合成用仓内已有的本地 ffmpeg，不调用任何收费接口。_
  - _需新增的唯一能力：`core/ffmpeg.py` 的 `FFmpegService` 现有 9 个方法（get_video_info/concat_videos/trim_video/add_subtitles/add_audio/add_watermark/resize_video/extract_audio/create_thumbnail），**独缺"图片序列 → 视频"**，全仓也没有按 `-framerate` 读序列的先例。_
- [x] 26. Export a batch of reference frames as a ZIP of JPEGs, reusing the existing offline frame-render path (`services/export` already does ZIP with volume splitting) — no encoder needed.
  - _2026-09-15 完成。_
  - _契约：`POST /api/v1/previs/scenes/{scene_id}/export-frames`，multipart 收浏览器**离线逐帧渲染**的 JPEG，按上传顺序重命名为连续编号（`frames/frame_0001.jpg`…）后打包 ZIP，内含 `manifest.json`。_
  - _**文件名与帧号必须分开表达**：ffmpeg 的 image2 demuxer 按编号连续性读序列，而 `step > 1` 时真实帧号是 0、2、4…（不连续）。所以文件名只保证顺序，「这张图是第几帧」记在 manifest 的 `frames[].frame` 与 `time` 里。靠文件名猜帧号，会得到一条错位的剪辑素材——而且肉眼很难当场发现。_
  - _只收 JPEG：同一份 4 秒预演的 PNG 序列是 132MB / 6.8s，JPEG(q0.92) 只有 9.4MB / 1.6s；批量帧是**过程产物**，不像单帧截图那样需要无损。单帧「截图回流」仍走 PNG 并入库关联分镜，两条路语义分开。_
  - _**不入库**是刻意的：96 帧都塞进素材库，一次导出就把素材库灌满，反而找不到东西。ZIP 直接下载，manifest 里带场景 id/revision/机位/帧范围，需要单张进参考时仍走截图回流那条路。_
  - _上限 600 帧（同时约束单次 multipart 体积，约 60MB）；帧数/时长由响应头 `X-Previs-Frame-Count`/`X-Previs-Duration-Seconds` 返回，前端不必解压就能提示。_
- [x] 27. Add server-side sequence compositing: a new `FFmpegService.images_to_video` (`-framerate 24`) driven through the existing task center, so exported video is guaranteed to be true 24fps regardless of client rendering speed.
  - _2026-09-15 完成。_
  - _`core/ffmpeg.py` 补上第 10 个方法 `images_to_video`（此前 9 个方法里独缺「图片序列 → 视频」，全仓也没有按 `-framerate` 读序列的先例）。`-framerate` 必须在 `-i` 之前，否则会被当成输出选项、序列按默认帧率读；另加两条「写错了也能跑、但产出没人能放」的约束：`-pix_fmt yuv420p` 与 `scale=trunc(iw/2)*2:trunc(ih/2)*2`（canvas 视口尺寸可能是奇数，4:2:0 的色度下采样会直接报错）。_
  - _端点 `POST /scenes/{scene_id}/export-video` 复用与 #26 相同的落盘，创建 `task_type=previs_export_video` 任务后台合成，完成后视频进 Asset Hub（`source=previs_frame_export`）。走任务中心而不是同步返回：合成虽只要数秒，但上传 600 帧本身就不该让请求一直挂着。_
  - _**合成失败与入库失败分开报告**：视频确实产出时任务就是成功的（`result.download_url` 可用），入库失败只作为 `asset_error` 如实标注——否则用户会以为白跑一趟。合成成功即删掉帧序列这一中间产物，失败则保留现场（`frames/` 原样留着）供排查。_
  - _一处如实标注的实测细节：输入是 JPEG 时 ffprobe 读出的 pix_fmt 是 `yuvj420p`（full range 的 4:2:0），仍是 4:2:0、现代播放器与剪辑软件都能读；`-pix_fmt yuv420p` 要防的是 yuv444p 那类不通用采样。测试断言因此接受两者，而不是假装它就是 limited-range。_
  - _前端：`SceneCaptureFn` 扩展为可指定 `mime`/`quality`/`background`（JPEG 没有 alpha，透明画布直接编码会变黑底，所以由用户选深色/白色底色而不是默默给黑）；采集按帧号逐帧挪播放头，**每帧等两次 rAF** 再取图——我们自己的 rAF 与 R3F 渲染循环的 rAF 谁先执行并无保证，只等一帧可能取到上一帧的画面，整段序列就会错位一帧。导出仅允许在「活动机位」视图触发（导演视角的视锥辅助线不该进画面），前端 `planExportFrames` 与后端 manifest 用同一套换算预演帧数。_
  - _验证：`pytest tests/test_previs_scenes.py tests/test_ffmpeg_service.py` → **29 passed**（新增 9 例导出契约 + 5 例 ffmpeg 命令参数）；`vitest run` → **108 passed（8 文件）**（`timeline.test.ts` 新增 6 例帧计划）；`npm run build` 通过。**真实后端 + 真实 ffmpeg 端到端**：12 帧 step=2 导出 ZIP（manifest 帧号 `[0,2,4,…,22]`、`span_frames=23`）；24 帧提交合成 → 任务 `running 10 → 70 → done 100` → `asset_id` 已入库 → ffprobe 实测 **`r_frame_rate=24/1`、`nb_frames=24`**，帧率断言通过。_
  - _**真实浏览器端到端**（CDP 驱动本机 Chrome 152，预演台页面）：导演视角下「导出」按钮 `disabled=true` → 切「活动机位」后 `disabled=false`（闸门生效）→ 打开弹窗设 0/8/步长 2 → 摘要回显「共 0–8 帧、步长 2、共 5 帧、覆盖约 0.4 秒」→ 下载到 443KB 的 ZIP（5 帧 + manifest，`frame_count=5`、`step=2`、`camera_id=cam-1`）→ **帧 0 与第 3 帧字节数不同（94788 / 94886），证明逐帧采集真的换了位姿**；再切视频模式 → 按钮变为「提交合成任务」→ 提交后弹窗给出任务回执 → 该批帧在服务端合成出 **`1098×636`、`r_frame_rate=24/1`、`nb_frames=5`** 的 MP4（尺寸等于浏览器视口）。全程 **0 个 >=400、0 条新增 console 错误**。_
  - _**端到端抓到一个真 bug（单测没覆盖）**：后台合成传给 `images_to_video` 的是导出根目录而不是 `frames/` 子目录，任务报「帧序列为空」并把帧留在原地——是"真跑一次"才暴露出来的，已修并加了目录层级的断言。_
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

- [x] 17. Add a read-only previs scene summary to Agent context with stable IDs and lock state, phrased so it can answer **coverage** questions ("which storyboard panels have no previs scene yet", "which cameras/nodes are locked") rather than only listing nodes.
  - _调研依据：Storyflow 的差异点是「AI 读整块板而非单帧」——能跨序列回答「哪些镜头还没预演」。只罗列节点，等于把单帧能力包装成整板能力，Agent 仍然回答不了覆盖度问题。_
  - _2026-09-14 完成。_
  - _**挂在既有的 pack 上而不是新造通道**：`build_creative_project_context_pack` 新增 `previs` 键。该 pack 由 `AgentService._augment_context`（`service.py:1380`）在**每次带 `project_id` 的运行中自动注入**，所以 Agent 不需要主动调工具就能看到——这是本条要的「进入上下文」而不是「提供一个工具」。_
  - _**面向覆盖度而非罗列节点**（本条的核心要求）：给出 `storyboard_panels_total` / `panels_with_scene` / `panels_without_scene` **精确计数**与 `uncovered_panels` **显式清单**（含 `storyboard_content_id` + `panel_number`）。分镜可以按章有多份，面板号只在各自分镜内唯一，所以键必须带上 content_id。_
  - _**稳定 ID 与锁定状态**：每个场景给 `scene_id`、`revision`、`node_count`/`camera_count`/`keyframe_count`、`active_camera_id`，以及 `locked_nodes`/`locked_cameras`——**含 ID 与名称**。只给数量等于让 Agent 再问一次，而它没有「再问」的能力。_
  - _**缺口并入 `known_gaps`**：`_known_gaps` 加了可选参数，覆盖度缺口进同一份列表。理由是那不是"新增一块信息"，而是"同一类判断"——导演正是按 `known_gaps` 决定下一步做什么。_
  - _三个刻意的取舍：① 覆盖度按**整个项目**统计并显式声明 `scope: "project"`（不随 `chapter_number` 收窄），否则调用方会把「某一章的缺口」误读成全项目；② 明细有截断上限（`PREVIS_UNCOVERED_LIMIT=24` / `PREVIS_SCENE_LIMIT=12`）但**计数始终精确、截断显式标记**（`uncovered_panels_truncated`）——否则 Agent 会把「只看到前 24 个」当成「总共只有 24 个」，据此排产会漏掉大批镜头；③ **读取失败时报 `error` 并把 `panels_without_scene` 置 `None`（不是 0）**。_
  - _另外报出两种真实会出现的引用不一致：`scenes_without_panel`（有场景但没绑面板）与 `scenes_referencing_missing_panel`（场景指向已被删除的面板）。_
  - _**实现中发现并处理的一个隐患**：测试 fixture 的建表列表里没有 `PrevisSceneDocument`，而 `_previs_brief` 现在会被每次调用——表不存在就会抛错，**把既有上下文测试一起打挂**。但更重要的是生产语义：**预演表读不出来不该让整份上下文崩掉**（导演还需要项目其它部分才能工作）。因此把查询包成「可见地降级」——报 `error`、计数置 `None`，并**同时把该表加进测试 fixture**，让正常路径也能被真实测到。_
  - _顺手修掉一处自己造的浪费：初次接线时 `_previs_brief` 在返回体与 `known_gaps` 里各调一次，等于两次 DB 查询；改为算一次复用。_
  - _测试：`test_creative_project_workflow_api.py` 新增 **4 例**——覆盖度计数与缺口清单（含 locked 状态与孤儿场景）、明细截断但计数精确、无分镜时不产生噪音缺口、读取失败时报错并置 None（而非 0）。fixture 补 `PrevisSceneDocument` 建表。_
  - _验证：新用例 **6 passed**（4 新增 + 2 既有上下文用例，确认未破坏既有行为）；回归 `pytest -k "agent or creative_project or context_pack or previs or content_package or profile"` → **381 passed / 2 skipped**；lints 干净。_
- [x] 18. Add a reviewed `PrevisOperation` Tool contract with expected revision, lock validation, confirmation diff, Agent Run trace, and focused authorization tests.
  - _2026-09-14 完成。_
  - _**拆成两个工具，而不是一个**（本条最关键的决定）：`previs_preview_operations`（read，只校验+出差异）与 `previs_apply_operations`（write，再校验一次后 CAS 落库）。合成一个工具就等于让 Agent 自己决定"要不要落库"，design 要求的**人工确认会被绕过**。_
  - _**落库前重新校验一次**：预览通过不代表落库时仍然通过——两次之间场景可能已被人工改动。校验很廉价，而一次错误覆盖会把人工调整冲掉。_
  - _**`expected_revision` 不匹配时整批作废**，不是逐条挑能用的执行。理由是：场景已经动过，Agent 的前提整体过期了；挑几条去执行只会拼出一个谁都没预料的中间态——比全部拒绝危险得多。_
  - _纯逻辑收在 `backend/app/services/previs/operations.py`（输入场景 dict、输出新场景 dict，**不碰数据库**，可完整单测）；工具层在 `services/agent/tools/previs_tools.py`。_
  - _四条硬规则：① 类型必须在白名单内；② **锁定对象只能读不能写**（`update_transform`/`set_camera`/关键帧操作全部检查）；③ 目标必须存在（按稳定 ID 找 node 或 camera）；④ **`capture_reference` 明确拒绝并说明原因**——截图需要浏览器渲染与上传，工具做不到；静默接受一个做不到的事比拒绝更糟。_
  - _一处容易漏的一致性：**改 `fov` 时同步重算 `focalLength`**。否则前端 `normalizeCamera` 在载入时按旧焦距把 fov 重算回去，这次改动**等于白做**（差异预览里也会一并显示焦距将如何变化）。_
  - _授权只给 `creative-director` 与 `storyboard-director`（预演是分镜的空间层，分镜导演需要它）；`quality-reviewer`、`character-designer` 等拿不到写操作。注册了但未授权等于不可用，因此**授权测试是硬断言**。_
  - _**一处如实标注的未完成**：`Agent Run steps` **没有显式写入**。工具由 `ToolRegistry.execute_tool(name, args)` 调用、**拿不到 run_id**，无法自行写 `AgentRunStep`；目前 trace 走 `AgentService._log_tool_call`（`service.py:1789`）对每次工具调用的**自动记录**——含完整参数与返回值，但 **result 截断 2000 字符**。因此工具返回值刻意精简（只放计数、ID 与摘要），**完整细节写进随场景持久化的操作历史**（预演台「操作历史」可看）。若要显式写 steps，需要先给工具执行链路传上下文——那超出本条范围。_
  - _测试：`backend/tests/test_previs_operations.py` 新增 **15 例**，分五层——纯校验（revision 过期整批作废、锁定不可改、目标不存在、未知类型、capture_reference 带原因拒绝）、落库（只动被点名的节点、fov↔焦距自洽、关键帧增删与缺省插值、不就地修改入参）、差异预览（只给被改字段、含推导出的焦距）、工具层（预览只读、CAS 递增 revision 并写历史、过期批零副作用、落库再校验）、授权。_
  - _验证：新增 **15 passed**；回归 `test_agent_center.py` + 三个预演/创作测试文件 → **178 passed / 1 failed → 修好后 16 passed**（见下）。两工具均注册成功，风险等级 `read` / `write`，必填参数含 `expected_revision`，`output_type` 遵循 creative_project 分类的 `creative_` 前缀约定。未新增 HTTP 端点。_
  - _**回归抓到一个我自己破坏的既有约定**：`test_agent_tool_registry_exposes_creative_project_tools` 断言该分类下所有工具的 `output_type` 必须以 `creative_` 开头，而我初版写的是 `previs_operation_*`。**改的是我的代码而不是放宽测试**——遵守既有约定比新造一种命名更省事也更一致。_
  - _另修一个循环导入：初版 `previs_tools.py` 用 `from . import register_tool`，而其余 29 个工具模块都用 `from app.services.agent.registry import register_tool`；前者会在包初始化时炸掉。_

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
