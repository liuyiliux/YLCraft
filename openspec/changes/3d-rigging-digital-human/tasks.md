# Tasks

调研已完成。以下为落地任务清单（按推荐路线 A 优先，分三阶段）。

## 阶段 1：后端（已落地，待测试验证）

- [x] 1. 调研腾讯云「查询绑骨蒙皮任务」接口（`DescribeAutoRiggingJob`，`Describe` 前缀，非 `Query`），确认与 `SubmitAutoRiggingJob` 的配对方式。
- [x] 2. 新增绑骨连接器 preset `examples/ai-connectors/tencent-hunyuan-rigging.json`（`capability: "rigging"`，`MotionType` 用 Jinja 条件渲染可选）。
- [x] 3. 数据模型：`Model3DGenerationTask` 加 `kind` 字段（迁移 `014_add_model3d_task_kind`），记录 `source_asset_id`/`source_url`/`motion_type`/`file_type`。
- [x] 4. 新增 `POST /model-3d/rig`：提交绑骨（仅绑骨 / 预设动作）+ 复用轮询 `GET /model-3d/tasks/{id}` + `/history?kind=rigging`；源模型经 `/model3d-files` 暴露公开 URL。
- [x] 5. `/model-3d/backends` 支持 `?capability=` 过滤（generation / rigging 分离）。
- [x] 6. 上传与回流统一提取骨骼/动画元数据，打 `rigged`/`animated` 标签（`assets.py` + `model3d_workspace.py`）。
- [x] 7. 新增绑骨相关单元测试（`test_model3d_workspace.py`）。
- [x] 8. 迁移与测试在目标环境跑通（`alembic upgrade head` + `pytest`）。

## 阶段 2：前端工作台（已完成）

- [x] 9. `/model-3d` 重构为「3D 创作工作台」：两步走（创建模型 → 让模型动起来）+ 素材库网格，替换现有「骨骼绑定方案」占位开关。
- [x] 10. 绑骨入口：Segmented 选择器切换「仅绑骨 / 预设动作（1-48 下拉）」+ 服务商选择器（读 `/backends?capability=rigging`）。
- [x] 11. `Model3DViewer` 增强 `useAnimations` 实际播放/切换骨骼动画（当前只检测不播放）。
- [x] 12. 素材库卡片徽标（静态/已绑骨/带动画）+ 筛选（基于 `metadata_json.has_bones/has_animations` + `rigged`/`animated` 标签）。

## 阶段 3：增强（待做）

- [ ] 13. 本地 UniRig 推理服务（Docker + torch + CUDA）接入工作台「本地 UniRig」入口（路线 B）。
  - _结论（2026-09-24 收口复核）：**未开始，也不建议在当前 change 里硬塞**。这是独立的基础设施切片——需要 Docker + NVIDIA CUDA + torch 权重（体量按 GB 计）、一个常驻推理进程，以及工作台里的排队/进度/失败可见性；与既有"配置驱动连接器"是两套运行模型。按仓库硬规矩（不写两套并存的半成品），应先立**独立 change**，把「权重从哪来 / 显存门槛 / 任务队列与超时 / 失败怎么报」四项定清楚，再在 3D 工作台加入口。触发条件：用户明确要离线绑骨，或供应商额度成为长期瓶颈。_
  - _追踪指针（2026-09-25）：本 change 不实现该项，已拆到独立 change `unirig-local-rigging-service`；本项保持未勾选，直到独立 change 完成。_
  - _进展（2026-09-25）：独立 change 已完成 upstream revision/license/checkpoint checksum、sidecar contract 与 AIConnector field mapping（tasks 1-3）。当前机器 6GB VRAM 低于 upstream 8GB minimum，真实 GPU service/acceptance（tasks 4-6、11）仍未完成，因此本项继续未勾选。_
- [ ] 14. TripoSR 纳入配置驱动连接器体系（当前 legacy 硬编码在 `Model3DService`，未走 AIConnector）。
  - _结论（2026-09-24，与交接说明一致）：**必须另立独立 change，不能在本 change 收尾阶段顺带改**。现状是"图生 3D 有多条后端：配置驱动的 AIConnector + TripoSR legacy 硬编码"两套并存；把它迁到连接器会同时动请求构造、轮询协议、结果回流与后端列表接口，属于跨模块行为变更。独立 change 的最小切片：只把 TripoSR 包成 `AIConnector` 实现（入参/出参/轮询对齐现有连接器契约），保持 HTTP 路由与前端不变，再删 legacy 分支——**迁移完成前不删旧路径**，避免出现"配置里没有、路由还指着"的空窗。_
  - _追踪指针（2026-09-25）：本 change 不实现该项，已拆到独立 change `triposr-connector-migration`；本项保持未勾选，直到独立 change 完成。_
- [x] 15. 本地格式转换/预览生成（`generate_preview`/`convert_format` 现为 TODO 占位）。
  - _2026-09-16 完成：按 `core/ffmpeg.py` 的同一范式新增 `core/blender.py`（`BlenderService`），把 Blender 无头命令行包装成服务；脚本在 `services/model3d/blender_scripts/`（`convert.py` 格式转换 / 剥骨 / 减面，`preview.py` 渲染预览图）。`Model3DService` 的两个 TODO 方法改为调用它。Blender 由 winget 安装（LTS 4.5.10），`discover_blender()` 会按环境变量 → 常见安装位置 → PATH 的顺序找，找不到时功能显式降级而不是假装成功。_
  - _三条刻意的取舍：① **`generate_preview` 失败返回 None，`convert_format` 失败抛错**——预览是锦上添花（没有它模型照样能用，不该拖垮入库），而转换失败必须让调用方知道，否则会拿到"说转成了 FBX、实际还是 GLB"的文件；② 预览相机由**包围盒**算出而非写死距离——图生 3D 的产物被归一化过，手工模型却有 1.9 米高，写死不是拍太远就是穿模；③ 预览用透明背景 PNG，方便叠在深浅卡片上。_
  - _**减面是绑骨的必要前置**：`--ratio` 参数用于把 50 万面的图生 3D 高模压到能过 60MB 上限（实测素材库里就有 75MB 撞线的）。**剥骨（`--strip-armature`）同理**：删骨架前先把当前姿势烘焙成 rest pose，否则删完网格会弹回绑定姿势、T-Pose 白摆。实测：把 CC0 的 T-Pose 模型从 91KB / 56 根骨骼 → 51KB / 0 根骨骼，尺寸与姿势分毫未动。_
- [ ] 16. 真实供应商验收：用已开通的腾讯云账号跑通「图生 3D → 绑骨蒙皮 → 带骨骼模型入库 → 查看器渲染」全链路，记录诊断与费用。
  - **结论（2026-09-21，`previs-agent-scene-composition` 收口时追加；用户已确认表述）**：这条链路**因产品定位搁置，不是配额或费用问题**——AI 生成不依赖原始模型的外观，人形在预演台里改用**通用占位**（程序化胶囊人，由参数型动作驱动），因此"图生 3D → 绑骨蒙皮 → 入库 → 渲染"在本产品里**没有承接方**：腾讯云配额与费用不再是阻塞点。**后续若要接回，最小切片是"外部动作数据 → 参数通道映射"**（把免许可障碍的 BVH 映射到我们自己的 23 个关节通道，见 `previs-agent-scene-composition` tasks 1.11），而不是绑骨重定向——本项目当初选择参数型载体，换来的正是"不需要绑骨、不存在两套骨架朝向不一致"。
  - _2026-09-15 进展：**先做完了不调用供应商也能做的那一半**——按**文件事实**核对（Tripo 那篇验收文章的思路：网页能预览动作 ≠ 导出文件里有动画，必须打开导出文件数清楚）。新增只读工具 `tools/inspect_model3d.py`（不联网、不调模型，解析 glTF JSON 逐项统计）。_
  - _**实测对照**（本机现有模型）：`vanguard.glb` 2 网格 / 7434 顶点 / 11376 面 / **2 套骨架、49 根骨骼 / 4 段动画**（Idle·Run·TPose·Walk，各 156 通道，起止 0–1.97s / 0–0.7s / 0–0.03s / 0–1.03s）；`ue-mannequin.glb` **67 根骨骼、0 段动画**；用户真实图生 3D 的两个模型（28MB / 27MB）**50 万三角面、0 骨骼、0 动画**——正是要送去绑骨的那种静态高模。_
  - _**核对抓到一个真缺陷**：`Model3DService.extract_metadata` 把 `len(skins)`（皮肤**套数**）当成骨骼数，vanguard 会落成「2 根骨骼」而实际 49 根。徽标只做布尔判定所以一直没露馅，但落库数字是错的——一旦界面显示「骨骼 N 根」，就会让人得出"这个绑定只有 2 根骨"的相反结论。已改为按骨架 **joints 并集**计（`bones`），另存 `skins` 套数、`animation_count`、`animation_details`（名称/通道/起止秒）；GLB 与 `.gltf` 共用 `_summarize_gltf` 同一口径（此前 `.gltf` 分支不提骨骼，GLTF 模型永远打不上「已绑骨」标签）。判定仍为 `has_bones = bool(bones)`、`has_animations = bool(animations)`，静态模型两者皆假。_
  - _测试：新增 `tests/test_model3d_metadata.py` **5 例**（手造最小 glTF/GLB，固定"joints 并集而非 skins 套数"、动画明细、两种格式同口径、静态模型为 0、网格计数）；`tests/test_model3d_workspace.py` **27 例**回归通过。架构文档 §4.4.2 已记录该口径修正。_
  - _**仍未完成（会产生费用，不擅自发起）**：真正调用腾讯云 `SubmitAutoRiggingJob` 那一步。发起前需确认三件事：① `tencent-hunyuan-rigging` 连接器已配真实密钥；② 源模型是 A-Pose / T-Pose 且不带武器、翅膀等外部组件（腾讯的约束）；③ 源模型可经 `/model3d-files` 暴露为公开 URL。_
  - _「查看器渲染」这一环已被 `3d-director-previs` #15 的浏览器实测覆盖（切到 Vanguard 后动作列表上报 4 条 clip、选 Walk 后第 0 帧与中段截图字节不同），不重复验证。_
  - _2026-09-16 前置检查（不花钱的部分已全部做完）：_
  - _**公网可达性 OK**：COS 已完整配置（bucket / 地域 / 密钥齐全），绑骨走 COS 上传 + 24h 签名 URL，**不依赖本机公网 IP**。这是这条链路最容易踩的坑——`_resolve_rig_source` 只在没有 COS 时才回退到 `BASE_URL + /model3d-files`，那时腾讯云根本下载不到源文件。_
  - _**源模型这一关卡住了**：腾讯绑骨只接受人形 A/T-Pose，而素材库 4 个静态模型量过尺寸——`probe_e2e` 0.72×0.72×0.72、`6af5c651…` 0.88×0.67×0.82（宽还大于高）、`5896a329…` 0.80×0.88×0.82（**且 75MB 超 60MB 上限**）、`b8ff9ed0…` 0.83×0.83×0.83（就是那个木桌）。人形应"高 >> 宽≈深"，四个全是接近等比的团块——**腾讯图生 3D 会把输出归一化进单位立方体，默认产物不满足绑骨的人形前提**。体检工具已补"包围盒尺寸"输出，正是为这一判断服务。_
  - _顺手堵了一个会让钱白花的洞：`_resolve_rig_source` 提交前**不检查 60MB**，75MB 那个模型要提交+轮询一轮才从远端得知失败。已加 `_assert_rig_source_size`（纯函数、可单测；上限与报错文案都由 `_RIG_SOURCE_MAX_BYTES` 常量驱动，不写死），新增 2 例；`test_model3d_workspace.py` + `test_model3d_metadata.py` 共 **34 例通过**。_
  - _**源模型已解决（CC0）**：改用公开模型而不是生图——下载 `Godot-Male-Base-Mesh`（CC0 / 公有领域，GitHub 可直连下载），它是 T-Pose 男性基础网格但**自带 56 根骨骼**；用新装的 Blender 4.5 剥骨后得到**无骨骼 T-Pose 人形低模**（1804 面、0.28×1.95×1.17、宽高比 1:7）——这才是绑骨要的输入。已入库（`953af3c9…`）。_
  - _2026-09-16 **真实调用已发出**：链路代码完全正确，**卡在账号配额，不是代码问题**。_
  - _请求证据：`X-TC-Action: SubmitAutoRiggingJob` / `X-TC-Version: 2025-05-13` / `X-TC-Region: ap-guangzhou`，body `{"File3D":{"Url":"https://ylcraft-1255992870.cos.ap-beijing.myqcloud.com/model3d/rig/<asset_id>.glb?<24h 签名>","Type":"GLB"}}`。设计里的每一步都对上了：源模型走 COS 签名 URL（公网可达），**没有**掉进本机 `BASE_URL` 那条死路。_
  - _腾讯返回：`ResourceInsufficient` ——「资源不足，请前往控制台 https://console.cloud.tencent.com/ai3d 开通付费或资源包」。即**该账号未开通 3D 绑骨的付费资源**。开通后直接重跑 `tools/verify_rigging_live.py` 即可（轮询阶段返回的 `FailedOperation.JobNotExist` 是任务压根没创建成功的连带现象，不是新问题）。_
  - _**真实调用抓出三个真缺陷（都已修）**——这正是"必须真跑一次"的价值：_
  - _① **绑骨端点的错误处理引用了不存在的字段**：`except` 分支访问 `req.prompt` / `req.model` / `req.source_image` / `req.options`，而这四个 `Model3DRigRequest` 全都没有（从 `/generate` 照抄时带过来的）。后果极隐蔽：绑骨一出错，**错误处理自己先抛 AttributeError**，真实失败原因被吞掉，用户只看到一个没有任何信息的 500，平台事件日志也记不上去（排查时日志里干干净净）。已抽出 `_rig_retry_payload(req)`，并补上 `logger.exception` 与该文件此前缺失的 `logger`。_
  - _② **源模型路径没按项目根解析**：库里存的是相对路径，绑骨却直接 `Path(row).is_file()`——解析的是服务进程工作目录，实测就报「该素材没有可用的本地模型文件」。已改用项目既有的 `resolve_storage_path`（图生 3D 那条路同样的写法一并修了，它此前只是碰巧能跑）。_
  - _③ 60MB 上限提交前不校验（见上一条）。_
  - _2026-09-16 补充（素材库侧的两个缺陷，均已修）：_
  - _① **上传的 3D 模型在素材库显示为「加载失败」**：因为上传这条路**从不生成缩略图**——图生 3D 那条路由远端提供 preview，上传没有，而素材库卡片靠缩略图渲染。已让 `_import_uploaded_model` 用 `Model3DService.generate_preview`（即 #15 的 Blender 渲染）补上，Blender 不可用时留空而不是让整次上传失败。实测重新上传后 `thumbnail_url` 有值、预览图可下载（73KB PNG）。_
  - _② **标签的写入侧与读取侧用的不是同一份数据**：写入落在 `AssetTagLink` 关联表，而卡片视图与标签筛选读的是 `AssetNode.tags_json`（创建时恒为空数组）。后果是素材库按 `rigged` / `animated` 筛选**一条都查不到**（标签其实早就写进库了，80 个标签里就有它们），卡片上也显示不全。已加 `AssetNodeService.get_tags_map`（按 node_ids 一次查完，避免 N+1），列表与详情两条路径都合并真实标签。修复后实测：`tags=animated` 5 条、`tags=rigged` 5 条、卡片标签 `['upload','3d_model','rigged','animated']`；`k -k "asset or node"` 回归 **106 passed**（2 个失败是 PDF/PPTX 依赖缺失，与本次无关）。_
  - _顺带入库 5 个**开源带骨骼/动画模型**，供预演台与 3D 工作台直接摆用：Xbot（67 骨 / 7 段动画）、CesiumMan（19 骨 / 走路）、RiggedFigure（19 骨）、Fox（24 骨 / 3 段动画）、BrainStem（18 骨 / 长动画），来源为 three.js 与 Khronos glTF-Sample-Assets 示例库，许可以各模型原页为准（多为 CC-BY / CC0）。**在"让预演台有能动的角色"这件事上，下成品模型比自己绑骨划算得多**：零成本、零等待、质量更好；绑骨留作"把自己生成的角色变可动"时再用。_
  - _③ **全屏查看 3D 模型白屏**（用户报告，实测确认是**全局**问题而非模型问题）：`Model3DViewer` 用 drei 的 `<Environment preset="studio" />`，它会在运行时**去 CDN 下载 HDR 环境贴图**；本机取不到（`ERR_CONNECTION_RESET`），错误一路冒到 `Model3DErrorBoundary`，于是画布整个变成「3D 模型加载失败，文件可能不完整或格式不支持」——**把网络问题报成了模型损坏**，且所有 3D 查看入口（素材库详情、全屏查看器、3D 工作台）一起白屏。诊断方式：CDP 打开两个模型（新下载的 Xbot 与原先"能用"的木凳）对比，两者报**同一个错**且页面 `canvas` 都不存在，据此排除"模型/后端"方向。修法：HDR 下到 `frontend/public/hdr/` 改走**本地文件**，并新增 `EnvironmentBoundary`——环境贴图失败只降级为普通灯光。修复后实测：canvas 出现、`选择动画` 与面数信息正常、HDR 报错消失。_
  - _教训（已写进架构文档约定）：**查看器不得依赖远端资源**——环境贴图这类辅助资源一律本地化，否则离线或 CDN 抖动会让整个功能"看起来是坏的"，且错误提示会指向完全错误的方向。_
  - _2026-09-17 修正（用户实测反馈「套动作生成的模型是躺着的」，且「导入时原始模型并不是躺着的」）：_
  - _**根因是重定向只统一了骨骼名、没统一骨骼朝向**。Action 存的是**骨骼局部坐标系**下的旋转，两套骨架名字对齐 ≠ 局部轴对齐；直接复制局部旋转会让模型扭曲甚至躺倒。改为「`COPY_ROTATION` 约束 + **世界空间**（`target_space = owner_space = "WORLD"`）+ `nla.bake(visual_keying=True)`」——对齐的是"骨骼在世界里朝哪"，不是"它在自己坐标系里转了多少度"。_
  - _实测对比：修正后 BrainStem 套 Xbot 的 7 段动作**全部站立**（`run` 高/横截 = 1.33、`walk` = 1.20），静止姿势 2.415×2.834 正常。判定用的是**骨骼驱动后**的包围盒（evaluated mesh），**不是** glTF 的 POSITION 绑定姿势坐标——上一次正是栽在后者上，读着"静止就躺着"的数值却得出了相反结论。_
  - _顺带修掉两处产物污染：① **一次 bake 会新建不止一个 action**（Blender 4.4+ 的 slot 机制），改用「bake 前后 action 集合的差集」认定产物后，孤儿动画 `Action.001`…`Action.007` 不再出现；② **源模型带进来的原始 action 未删除**，既与烘焙结果重名成 `walk.001`，又可能被误选——而选中它们恰恰会重现"躺倒"的老毛病。收尾时一并删除后，动画从 9 段收敛为干净的 8 段（7 段套用 + 1 段模型自带）。_
  - _重名还导致改名失效：源 action 在场时改名会被 Blender 自动加 `.001`，改为「先挂临时名 → 收尾删掉源 action → 再改回正式名」。_
  - _另修**部位勾选框点了没反应**：受控 `checkedKeys` 里混进了"半选"的父节点（antd 会把它渲染成全选），于是取消一个子部位后界面看起来毫无变化；现只回传"整块都可见"的节点，半选交由 antd 依据子节点自行推导。_
  - _文档：README「环境要求」补上 **Blender 4.5+**，含四个脚本的职责、未安装时的降级行为、三平台安装方式与 `BLENDER_PATH`（程序按环境变量 → 常见安装位置 → PATH 自动查找，已覆盖 Linux 的 `/usr/bin`、`/usr/local/bin`、`/snap/bin`）。Blender 官方支持 Linux，`--background` 模式不依赖图形界面。_
  - _新增素材 `b2b3160a`（BrainStem + Xbot 动作库·重定向修正版），与旧的 `a9940683`（9 段、含躺倒隐患）并存，便于对比验证。_
  - _**进一步定位（同日，用户复验后）**：上面那条「世界空间」的结论**不是根因**——用户导入修正版后模型**仍然是躺着的**。重新核对时才发现自己此前量错了轴：**Blender 导入 glTF 后场景是 Z-up，身高在 Z 轴**，我却按「glTF 是 Y-up」去读 Y，把"前后厚度"当成了"身高"，于是把躺着的模型判成了"站立"，白绕一大圈。教训：**验证姿势必须用"骨骼驱动后"的包围盒 + 正确的轴，并在真实浏览器里看一眼**。_
  - _**真因：BrainStem 的绑定姿势（rest pose）本身就是躺着的**——rest 高度 2.00 < 水平跨度 2.83，它靠自带动画 `Anim_0` 把自己扶起来（动画中高度 2.78）。所以查看器里默认播动画、看着是站着的；一旦套上别人的动作，骨骼按新动作摆位、网格却被拽回那个躺着的骨架 → 当场躺平。**正因为"它自己会站起来"，这个缺陷一直没暴露。**_
  - _修复：新增 `blender_scripts/upright.py`，把"它自己站起来的那个姿势"固化成新的 rest。判据「rest 身高 < 动画中身高的 92%」→ **需要才动手**（实测 BrainStem `ratio=0.719` 被扶正；CesiumMan `ratio=1.020` 原样不动，正常站姿的模型不会被误伤）。数学是标准重新绑定 `v_new = Σ w_j · (M_pose_old_j · M_rest_old_j⁻¹) · v_old`：先父后子重写 `edit_bone.matrix`，再逐顶点按权重重算。_
  - _**`bpy.ops.pose.armature_apply()` 是个会静默失败的坑**：它在无头环境下返回 `{'FINISHED'}`、模型却分毫未动（实测两次，连网格一起选中也没用），所以改为手写 rebind 而不是调它。_
  - _已接进正式流程：`_run_retarget` 在「检查目标骨架命名」**之前**插入「检查绑定姿势」（进度 14），扶正结果写进任务 `result.upright` 留痕，便于日后遇到"套上就躺着"直接定性。_
  - _**端到端实测**（原始 BrainStem `f31c7217` + Xbot `553f032c`）：任务 8 → 14 → 30 → 55 → 78 → done，`upright=need=1 ratio=0.719 rest=2.000 anim=2.781`，入库素材 `7a34d95f`；**真实浏览器截图确认模型站得笔直**（修复前沿同一条链路是横躺的）。模型相关测试 39 passed。_
  - _**第二轮修正（同日，用户复验后）**：扶正解决了"躺着"，但**一播动作腿就反向折叠、脚翻到上面**（上半身正常）。量化后立刻定性：BrainStem 的**腿骨是"往上长"的**——Hips 0.91 → 大腿 0.87 → 膝 **1.22** → 脚 **1.61**（越往末端越高）；对照 CesiumMan 是 0.00 → 0.07 → 0.05 → 0.02（一路向下）。**这个模型的骨骼布局天生与人形语义相反**，只因网格靠蒙皮权重显示正常，肉眼完全看不出来。_
  - _于是「让目标骨骼的**绝对世界朝向**等于源的」这条路暴露了致命前提：它要求两套骨架的骨骼朝向**语义一致**。Xbot 的大腿朝下、BrainStem 的大腿朝上，硬对齐 → 朝上的腿被**翻转 180°** → "腿对折、脚朝上"。这也解释了为什么它此前只在腿部暴露：上半身的骨骼朝向恰好差异不大。_
  - _**改为"增量法"**：`M_target_now = M_target_rest · (M_source_rest⁻¹ · M_source_now)`——只搬运"源骨骼相对它自己 rest 动了多少"，左乘到目标自己的 rest 上，目标骨架的骨骼朝向/骨长/层级关系原样保留。实现要点：① 先**全量采集**源骨架每帧的世界矩阵、再逐帧写目标（边读边写不行：写入要往目标 action 插关键帧，而 `frame_set()` 会把已插的关键帧应用回目标，两个骨架互相污染）；② 写入顺序**父先子后**，父一变就 `update()`，否则子骨骼拿到过期基准；③ 写 `pose_bone.matrix` 必须处在 **POSE 模式**（OBJECT 模式下赋值直接抛异常），且切模式前骨架要处于选中态；④ 写完把 `location` 清零只留旋转——`matrix` 带来的位移会让骨骼脱离父级、角色飘走。_
  - _验证：同一条链路上腿骨 Z 从 `0.91 → 0.87 → 1.22 → 1.61`（向上折）变为 `0.91 → 0.87 → 0.56 → 0.21`（一路向下），7 段动作逐帧检查**全部 ok**；**真实浏览器截图确认站立行走、双腿正常**。完整流程（原始躺着模型 → 自动扶正 → 改名 → 增量重定向）：任务 8 → 14 → 30 → 55 → 78 → done，入库素材 `82bee249`；模型相关测试 39 passed。_
  - _素材对照（确认无误后可删）：`7a34d95f`（只修了躺倒、腿部仍反向）、`c7ae9f50`（本地增量法验证）、`82bee249`（增量法首版，手臂/躯干仍有问题）。_
  - _**第三轮（同日）：手臂扭转 / 身体歪 / 部位勾选框**。用户复验反馈"手臂好像扭过去了、身体是歪的"以及"左边的勾选还是有点问题"。_
  - _手臂问题的根因是**上一版公式的数学错误**：`T_now = T_rest · (S_rest⁻¹ · S_now)` 中，`S_rest⁻¹·S_now` 是**世界空间**增量、**已经把父骨骼带来的旋转算进去了**；再逐根骨骼应用时父级旋转被**重复叠加**，**越靠末端的骨骼转得越离谱**（手臂在最末端所以最明显、躯干次之）。_
  - _改为**在骨骼自己的空间里算增量**：`Δ_world = S_rest · S_basis · S_rest⁻¹`（`S_basis` 取源骨骼的 `matrix_basis`，即"相对它自己 rest 动了多少"，不含父级影响），再 `basis_target = T_rest⁻¹ · Δ_world · T_rest` 转进目标骨骼空间。前后两次 `rest` 夹持即**轴系桥接**，父级连锁影响交给 Blender 层级自动传导。顺带不再需要 `pose_bone.matrix` + 逐骨骼 `update()`，直接写 `rotation_quaternion`，既快又简单。_
  - _验证：左右小臂 X 坐标**符号相反**（分居身体两侧）、脊柱 X 偏移 <0.05（不歪）、脚 Z 全程低于髋 Z；浏览器截图确认站立行走正常。入库素材 `535b8f2d`（**当前正确版本**）。_
  - _**部位勾选框的真 bug**：`checkedPartKeys` 只对**顶层**节点做 filter，而部位树只有一个顶层节点（Hips）——它一旦半选（取消任意一个子部位）就会被整个丢掉、返回空数组，antd 于是认定"什么都没选中"，**整棵树的勾选态全乱**（这正是用户说的"还是有点问题"）。改为**递归下探**：整块可见就上报该父节点（antd 会自动勾选其后代），否则上报下面"仍然整块可见"的子树，父节点留给 antd 显示半选。_
  - _**排查中的两个教训（已记下）**：① 前端验证最初跑在 `5173`，而 `vite.config.ts` 里配置的端口是 **3000**、用户访问的也是 3000——**拿错端口做验证**，看到的可能是另一个实例，这类"验证环境与用户环境不一致"必须先确认；② 素材库列表是**虚拟滚动**，按名字找卡片经常找不到，UI 自动化要么按顺序点、要么先筛选。_
  - _**把勾选推导抽成纯函数并加测试**（`pages/model-3d/parts.ts` + `parts.test.ts`，7 例）：这个缺陷反复出现过两次，值得钉住。**写测试时当场抓出实现里又一处错误**——原先用「下探结果的数组长度 === 子节点个数」判断"整块可见"，但一棵**部分可见**的子树会返回多个路径，长度恰好相等时父节点就被误判成全选；改用布尔的 `isFullyVisible` 判定后才正确。_
  - _验证：`vitest run` → **128 passed（10 文件）**；`tsc --noEmit` 通过。素材 `535b8f2d` 为当前正确版本。_
  - _2026-09-16 **通用动作库**（把非 Mixamo 谱系的模型接进统一动作库，三步能力均落地）：_
  - _前提事实：动作 clip 是"某根骨头在某时刻的旋转"，程序**按骨骼名**对号入座——实测五个模型五套命名（Xbot 的 `mixamorig:Hips`、CesiumMan 的 `Skeleton_torso_joint_1`、BrainStem 的 `node3`），所以不加处理时动作**无法跨模型复用**。_
  - _① **骨骼分析 + 自动推断对应关系**（`blender_scripts/skeleton_report.py`）：导出骨骼树（名字/父级/世界坐标/高度/左右），并按人形骨架的固定结构推断 Mixamo 对应——根骨分叉出"往上的脊柱"与"往下的两条腿"，脊柱顶端再分出脖子与双臂。名字可以是任何语言，但**谁是谁的孩子、谁更高不会骗人**。实测 RiggedFigure 的 19 根**全部推断正确**（Hips/Spine/Spine2/Neck/Head/LeftArm…LeftUpLeg…LeftToeBase）；左右手性与 Xbot 的 Mixamo 标准名一致（LeftArm 均在 +x，已用脚本校验，因为错了会变成顺拐）。_
  - _② **按映射改名**（`convert.py --bone-map`）：两个不写清楚就会**静默出错**的地方——**两阶段改名**（直接 A→B 时若 B 仍被占用，Blender 会悄悄生成 `B.001`，映射失效）与**同步顶点组名**（蒙皮权重按顶点组名找骨骼，只改骨骼名会让权重整体失配、模型僵住且不报任何错）。实测 19 根全改成功、蒙皮属性完好、原有动画的 57 个通道也一起改名（没留断链）。_
  - _③ **动作重定向烘焙**（`retarget_bake.py`）：Blender 的 Action 曲线路径是 `pose.bones["mixamorig:LeftArm"]`——**按骨骼名寻址**，所以两边名字统一后，直接把源 action 挂到目标骨架上即可驱动。两个取舍：只保留**旋转**通道（丢掉位移/缩放，否则目标角色会飘走或沉下去，动作改为"原地做"——位置本来由导演在预演台摆）；目标缺的部位（锁骨/手指）曲线自然无效，导出时被忽略。_
  - _**实测踩到并修掉的一个坑**：Blender 导出 GLTF 会把 `bpy.data.actions` 里的**所有** action 一起导出——源模型带进来的动作会"顺带"全被套上，而我起初只过滤了点名的那一个，其余带着 Xbot 的位移（`run` 高达 **-12 米**）一起导出，套上后角色会直接飞出去。改成过滤全部新增 action 后，所有动作的位移通道归零、旋转保留（1876 条）。_
  - _成果：一次操作把 **Xbot 的 7 段动作全部套到 RiggedFigure 上**（agree/headShake/idle/run/sad_pose/sneak_pose/walk + 原有 Anim_0 = **8 段**，覆盖 19 根骨骼），已入库（`fabc22d9…`，自动带预览图）。服务层已包装为 `BlenderService.skeleton_report` / `retarget_bake`。_
  - _④ **UI 入口已落地**（原计划里的"未完成"）：`POST /api/v1/model-3d/retarget`（`_run_retarget` 后台任务，自动判断目标骨架是否需要先统一命名）+ 3D 工作台左栏「套用别人的动作」按钮与弹窗（选动作来源 → 选动作 → 提交）。BlenderService 补 `skeleton_report` / `retarget_bake` 与 `convert_format(bone_map=...)`（映射表走临时文件，避免 Windows 命令行长度限制截断）。新增 9 例测试。**端到端验证**：先用接口真实跑通（CesiumMan 套 Xbot，22.7 秒，产出 8 段动画并入库），再**从界面点通**（用户实测 + 新素材 `dad3c761` 带 `retarget`/`animated` 标签）。_
  - _**UI 联调抓到的两个真 bug（都已修）**：① **下拉的 value 类型混用**——套用动作库时复用了为"本地按索引播放"设计的 `animationOptions`（它的 value 是**下标**），于是后端收到数字而不是动作名，直接 422；已拆出 `animationNameOptions`（value 是动作名），并在两个函数的注释与测试里写明区别。② **422 的报错信息不可读**——FastAPI 的 `detail` 是数组，`new Error(detail)` 显示成 `[object Object]`，等于把"哪个参数不对"藏起来；现在会拼成可读文本。_
- [x] 17. 同步更新 `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`、`docs/architecture/API_SURFACE.md` 与 `api_surface.json`（新增 `/model-3d/rig` 等）。
  - _2026-09-17 task: upright baseline frame fixed; asset dfede07b_
  - _2026-09-17 conclusion: upright baseline fixed (scan most-vertical frame). Arm issue is BrainStem-specific (no shoulder bone, mechanical-arm bone orientation) - verified with CesiumMan control test where arms swing normally._
  - _2026-09-17: tried flipping reversed bones + rebind - render showed worse (leaning body, crossing arms), NOT adopted. BrainStem arm issue stays model-specific (mechanical arms, no shoulder bone). Latest good asset: dfede07b._
  - _2026-09-17 **付费资源状态已确认：仍未开通，这就是唯一的阻塞点**。连接器侧全部就绪——`Tencent Hunyuan Auto Rigging (示例)` `is_active=true`、`has_api_key=true`（密钥与 TC3 签名都通过：返回的是业务码 `ResourceInsufficient`，不是 `AuthFailure`）、COS 已配置（源模型走 24h 签名 URL）、源模型仍是已剥骨的 CC0 T-Pose 人形 `953af3c9`。真提交 `SubmitAutoRiggingJob` 被账号额度拦住：`{"Code":"ResourceInsufficient","Message":"资源包积分已用尽，请至控制台(https://console.cloud.tencent.com/ai3d)开通后付费或购买资源包。"}`（RequestId `11acfb42-4db7-4d1b-a92d-f1bc8e2500fc`）。**不是代码问题，无需再改链路。**_
  - _官方计费事实（已核对文档，用于估成本）：绑骨蒙皮 **10 积分/次**；后付费 **0.12 元/积分 ≈ 1.2 元/次**；预付费 1000 积分 = 100 元（1 年有效）；首次开通后可到 `/ai3d/packages` 领取**一次性 100 积分**（1 年有效、需手动领，免费额度覆盖清单里没有绑骨）；**任务失败不计费**，所以本次试探一分钱没花。_
  - _这次文案是「**积分已用尽**」而不是上次的「未开通」——很可能免费积分包已领过、被此前的图生 3D 调用耗光了（专业版 Normal 20 积分/次，100 积分撑不过几次）。后付费**默认不开通**，这正是 `ResourceInsufficient` 的直接原因（官方明说：免费包耗尽后不会自动转后付费，而是报"计费异常"）。_
  - _解封动作（用户侧控制台操作，代码侧无事可做）：① 领免费额度 https://console.cloud.tencent.com/ai3d/packages ；② 买资源包 https://buy.cloud.tencent.com/ai3d ；③ 控制台设置里开通后付费 https://console.cloud.tencent.com/ai3d/settings 。拿到积分后直接重跑 `python tools/verify_rigging_live.py --asset-id 953af3c9…`。_
  - _⚠️ 迁移提示（官方文档「注意」原文）：混元相关功能正逐步迁往 **TokenHub**（https://console.cloud.tencent.com/tokenhub），迁移后原平台**停止支持新购模型服务**（存量服务不受影响）。若 ai3d 控制台已经买不到包/开不了后付费，改走 TokenHub；这条会成为后续换供应商的触发条件。_
  - _工具修正（本次唯一改动）：`tools/verify_rigging_live.py` 新增 `--preflight-only`（只查前置条件、不提交、不花钱），并把 `ResourceInsufficient` 的提示从笼统的"未开通付费资源"换成"积分已用尽/未购 + 后付费未开通"＋三个控制台入口＋单价与"失败不计费"。原因是这次排查暴露一个认知缺口：**腾讯 ai3d 的 19 个接口全是提交/查询任务类，没有查询开通状态或资源余量的接口**，这一条前置条件注定无法离线自查，只能真提交一次——把这个事实写进脚本 docstring，避免下次又绕一圈。_
