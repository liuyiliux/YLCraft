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

- [ ] 14. Add scene duration, 24fps playhead, transform and camera keyframes, slerp rotation interpolation, and persisted scene operation history.
- [ ] 15. Reuse existing rigged-model animation clips as scene playback selections without claiming editable skeletal animation.
- [ ] 16. Evaluate frame capture and MP4/WebM export only after static capture is stable; document browser and cost constraints.

## Phase 3: Agent director assistant

- [ ] 17. Add a read-only previs scene summary to Agent context with stable IDs and lock state.
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
