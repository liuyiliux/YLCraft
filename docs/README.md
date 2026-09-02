# YLCraft 文档地图

本文是项目文档入口。新 AI 接手时先读这里，再按任务进入对应目录，避免反复全仓考古。

## 仓库地址

- GitHub：https://github.com/liuyiliux/YLCraft
- CNB：https://cnb.cool/yiliu/YLCraft

## 必读入口

| 文档 | 用途 |
| --- | --- |
| `AGENTS.md` | 仓库级 AI 入口规则，短规则优先级最高。 |
| `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` | 总架构入口：产品主线、模块边界、核心模型、接口维护规则。 |
| `docs/architecture/API_SURFACE.md` | 后端接口清单，接口变更后必须同步。 |
| `docs/DESIGN.md` | 产品定位、总体架构、模块状态的单一事实来源。 |
| `docs/AI_HANDOFF_PROTOCOL.md` | 多 AI / 多电脑协作协议：接手、开发、交接、提交前检查。 |
| `openspec/changes/*/tasks.md` | 正在推进的规格任务和完成状态。 |

## 文档目录职责

| 目录 | 放什么 | 规则 |
| --- | --- | --- |
| `docs/agent/` | Agent 工作台、Skill Runtime、工具调用、记忆、上下文。 | Agent 相关实现变化必须更新这里或对应 OpenSpec。 |
| `docs/architecture/` | 子系统架构设计，如资产中枢、AI 服务层、播放器、规则助手。 | 讲长期设计，不写当天流水账。 |
| `docs/guides/` | 可执行工作流说明，如创作项目闭环。 | 面向“怎么用/怎么串起来”。 |
| `docs/guides/quickstart.md` | 面向 fork 开发者的快速上手指南：启动、配模型密钥、首次使用路径。 | 新人开箱必读。 |
| `docs/platform/` | B 站、多平台采集/发布等外部平台能力。 | 平台兼容、登录、限流、接口差异放这里。 |
| `docs/rules/` | 后端、前端、数据库、代码风格等工程规范。 | 规则类文档要短、可执行。 |
| `docs/refactor/` | 重构、迁移、清理计划。 | 计划完成后把长期结论回写到架构或领域文档。 |
| `docs/devlog/` | 必要的阶段性交接。 | 只在跨电脑/长任务切换时写，文件名用 `YYYY-MM-DD_topic.md`。 |
| `docs/reference/` | 外部参考资料、客户素材、二进制样例。 | 不作为当前实现事实来源。 |

平台接入入口：`docs/platform/BILIBILI_GUIDE.md`、`docs/platform/FANQIE_GUIDE.md`；其余跨平台对比资料仍在 `docs/platform/MULTI_PLATFORM_REFERENCE.md`。

## 当前主线状态

最近更新：2026-09-01。角色主线已从“能同步”推进到“可审阅、可追溯、可回流”：小说提取保留原文证据，真人和 Agent 均先预览后确认，确认不重复调用模型；角色库筛选、项目增量合并和正文角色上下文已完成。小说来源世界项目本轮补齐了可选向量索引与混合检索的真人/Agent 入口，并把提取域从四域扩展到八域（新增世界规则、力量/科技体系、经济/金融、物种），扩展域复用与基础域同一条证据校验与写入通道。

| 主线 | 状态 | 事实来源 |
| --- | --- | --- |
| Agent Skill Runtime | 已完成并归档 | `openspec/changes/archive/agent-skill-package-runtime/tasks.md` |
| Agent 上下文/父子 Run 基础运行时 | 已完成并归档；普通聊天仍以单 Agent 工具循环为主 | `openspec/changes/archive/agent-center-multi-agent-runtime/tasks.md` |
| Agent Supervisor/子智能体运行时 | Phase 0-2 与执行树 UI 已完成：独立子 Session、并行/依赖委派、父续跑、确认传播、层级/预算诊断；待“委派并续跑”动作和 Writer Room team 模式 | `openspec/changes/agent-supervisor-subagent-runtime/tasks.md` |
| Agent 对话工作台 | 进行中：已收敛为对话优先双栏、内联轨迹、局部失败恢复和页面错误边界；待接入真实后端后的多轮对话人工验收 | `openspec/changes/agent-center-conversation-workbench-redesign/tasks.md` |
| Agent 工作台 UI 改造 | 已落地：markdown 表格/加粗渲染、总控助手提示词禁 emoji、确认显眼化（顶部待确认卡片+横幅）、底部运行状态栏、空态引导；待左栏会话状态点/顶栏精简与真实对话验收 | `openspec/changes/agent-workbench-ui-redesign/tasks.md` |
| Agent 声明式团队组合 | 运行时已完整落地：`AgentScope` 平面隔离、团队模板 schema/loader/validator、`TeamComposer`、`spawn/fork/continuable` 三原语、缓存稳定工具目录 + `CostMeter` + 压缩溯源、内置模板、Writer Room `team` 模式（opt-in `rehearsal_mode=team`）；旧 `MultiAgentCoordinator` 硬编码逻辑已去重，`scene-sim` 团队路径已用真实 DeepSeek 端到端验收（5/5 子任务完成）；仍待 `AgentService` per-session 状态迁移与 writer-room team 真实项目验收 | `openspec/changes/agent-team-composition/tasks.md` |
| 创作项目闭环 | 角色提取、角色库同步、项目回流、正文上下文注入和真人/Agent 双入口已完成；仅留真实生图后端人工验收 | `openspec/changes/creative-project-closed-loop/tasks.md` |
| AI 渐进世界构建（梯子原则） | 已完成：可扩展底座（`world_domain_definitions` + 域定义 CRUD，宗教/语言/文化/生态四域）、三档生成动作（`draft_world` 因既有「大纲→提取→审阅」链路承担而关闭，落地 `expand_domain`（异步接入任务中心）与 `expand_entity`）、世界构建模板（内置种子只读 + 项目私有可改可删可设默认；真人 `/story` 细化弹窗内嵌编辑与 `/platform-templates`「世界构建」Tab 统一入口；AI 起草草案不落库、确认后保存）、`prompt-preview` 不调模型、生成候选 `origin=ai_draft` 无证据且结构与字段建议（`ai_suggested` 默认不启用）经用户确认后才生效、上下文打包区分 AI 创作/大纲/原作正典。Agent 工具：`expand_world_entity_attributes` / `expand_world_domain` / `manage_world_building_template`（含 draft）/ `list_world_building_suggestions` 等 7 个 | `openspec/changes/ai-progressive-world-building/tasks.md` |
| 小说源资产世界项目 | 最小闭环与增量链路已落地，多来源共用同一套逐域提取/证据/候选/写入管线：TXT 上传、书架章节导入、创作项目大纲（`/story` 圣经/世界 →「生成世界设定候选」）、来源快照直接建项目（`from-novel-source`）、小说书架每本「提取世界」；十一个域（角色/地点/势力/历史事件/世界规则/力量体系/经济/物种/物品/术语表/剧情时间线）提取、证据预览与确认写入项目，连载同步（含追加章节 UI）+ 按游标增量提取（新证据并回既有候选，不重建世界，增量变更区分展示）；可选向量索引与混合检索（PostgreSQL 下走 pgvector 数据库级近邻、其它回退 JSON 向量混合，含邻域扩展）、跨域调和与语义矛盾检测、受影响事实传播、候选 merge、完本来源派生项目（改编/续写/同人，原作正典 `source_canon` 只读分层，Context Pack T0 已分层注入）已完成，类型化独立实体与关系（`world_entities`/`world_entity_relations`，含派生复制）也已落地，真人 `/novel-world` 与 14 个 Agent 工具共用同一服务层。世界地图工作台基于 Leaflet（CRS.Simple）实现拖拽/缩放/平移/底图上传/势力范围多边形，保留 SVG 导出，并可用生图链路生成视觉成图（对齐角色立绘接入：选 provider/model/size、`prompt-preview` 先看提示词、成图入资产中枢，成图只是派生视觉资产，`map_json` 空间关系才是正典）。剩余：真实浏览器/Agent E2E 验收 | `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` §4.2.1、`docs/agent/agent-center.md`、`openspec/changes/novel-source-world-project/specs/novel-world-project/tasks.md` |
| 创作项目动态状态 | append-only 台账 `ProjectStateEntry`（scope 区分角色/世界、自由 JSON 键值、set/add/remove、按章溯源 + 去重）、`StateLedger` 折叠/回滚、叙事运行时抽取 `state_changes`、context pack 注入「动态状态」层；静态设定与锁定事实隔离 | `openspec/changes/creative-project-dynamic-state/tasks.md` |
| 创作项目优化路线 | 已完成并归档 | `openspec/changes/archive/creative-project-optimization-roadmap/tasks.md` |
| 小说连续性事实闭环 | 已完成并归档 | `openspec/changes/archive/creative-project-continuity-facts/tasks.md` |
| 创作画布 | 已完成并归档 | `openspec/changes/archive/creative-project-infinite-canvas/tasks.md` |
| 小说叙事运行时 | Phase 0-7 已完成：Context Pack、伏笔台账、叙事图谱、Story Cockpit、Skill 路由、受控运行和跨模态血缘均已落地 | `openspec/changes/creative-project-narrative-runtime/tasks.md` |
| 小说写作门禁与方法包 | 代码和 focused 验证完成；仅剩外部 Chrome/Patchright 视觉验收 | `openspec/changes/creative-project-writing-guardrails/tasks.md` |
| 番茄小说发布 | Cookie、书籍、热榜、统计、项目绑定、本地发布预检、草稿发布和 Agent 工具已落地；仅剩真实测试章、登录态抓包接口与端到端联调 | `openspec/changes/fanqie-publisher/tasks.md` |
| 提示词参考库 | 本地优先同步、双语/多图、图片缓存、筛选、画布和生图集成完成；仅剩完整人工验收 | `openspec/changes/image-prompt-reference-library/tasks.md` |
| Story 生产台 | 已完成，已验证桌面/移动布局 | `openspec/changes/story-production-desk/tasks.md` |
| 视频分镜生产 | 代码和项目回流完成；仅剩真实视频供应商验收 | `openspec/changes/story-video-shot-production/tasks.md` |
| 任务观测诊断 | 已完成，事件时间线和异步生图诊断已验证 | `openspec/changes/task-observability-diagnostics/tasks.md` |
| 全平台事件日志 | 进行中：任务中心改三 Tab（任务/事件日志/运行日志）；新建 `platform_event_logs` 表 + `/api/v1/logs`（含 `/runtime`）查询；后端补滚动文件日志；同步修复图片生成失败不落账 | `openspec/changes/platform-event-logging/tasks.md` |
| 数据库迁移收敛 | Alembic 迁移链当前到 `035_add_world_map_documents`；启动和 Agent 请求路径不再隐式改 schema，角色提取证据、视频/图转 3D/动态状态/平台事件日志、小说来源世界提取、块级向量召回和结构化世界地图均通过显式迁移落库。`023` 会移除历史素材 AI 参数中并非供应商实际返回的采样步数与采样器默认值。 | `backend/alembic/versions/`、`openspec/changes/database-migration-convergence/tasks.md` |
| 独立视频工作台 | 文生/图生视频、视频提示词模板、素材库首帧、持久任务恢复、任务中心聚合和 Asset Hub 回流已落地；模式 tab 驱动供应商/模型过滤、`video_capabilities` 能力约束、视频首帧缩略图已补齐；仍待真实供应商全链路验收 | `openspec/changes/ai-video-workspace/tasks.md` |
| 图转 3D 工作台 | 配置驱动提交/轮询/下载、Asset Hub 入库、GLB 优先与 ZIP 解包、PreviewImageUrl 缩略图、独立页面已落地；仍待真实供应商生成 GLB 验收 | `openspec/changes/image-to-3d-workspace/tasks.md` |
| 3D 骨骼绑定与数字人 | 后端已落地：绑骨连接器（`SubmitAutoRiggingJob`/`DescribeAutoRiggingJob`）、`POST /model-3d/rig`、源模型经 COS 临时签名 URL 或 `/model3d-files` 暴露、部位树显隐与动画播放；仍待真实绑骨供应商端到端验收（需 ≤60MB 人形 GLB/FBX） | `openspec/changes/3d-rigging-digital-human/tasks.md` |
| 3D 导演预演台 | Phase 1 已落地：`PrevisSceneDocument` 持久化（可建独立场景，无需项目）+ revision 并发保护、`/story` 分镜入口与顶级导航入口（可新建独立场景或浏览场景列表）、可复用 3D 渲染原语（`scenePrimitives`）、静态导演台节点管理（Asset Hub 模型/人形三样式：可摆姿势胶囊人·内置 UE 白模·Vanguard/几何体/全景背景/图层可见性/重命名/删除/锁定）、相机 CRUD（名称/位置/目标点/FOV/锁定）与导演/活动机位双视角、安全框/九宫格叠加；待相机拖拽回写、截图回流、关键帧与 Agent 阶段 | `docs/architecture/3D_DIRECTOR_PREVIS_DESIGN.md`、`openspec/changes/3d-director-previs/tasks.md` |
| 内容生产方案与导演 Agent 编排 | Phase 1-3 已落地；Phase 4 已锁定外部 `watermarks-remover`（MIT/v0.5.0）本地适配边界，并落地内部适配器：素材审计、文本/图片/视频/音频元数据清理副本（ffmpeg 去容器元数据）、`authorized_source` 授权来源字段、Asset Hub `derived_from` 血缘和事件日志；前端入口（素材库详情「清理元数据」+ 独立页 `/provenance-clean`）。已复刻 Layer A 文本隐形 Unicode（零宽/bidi/标签/非字符/空间同形字，保留 emoji 胶水与合法 ZWJ/ZWNJ）与多格式覆盖（图片加 gif、文档扩至 docx/xlsx/pptx/odt/epub）；写作室新增可选 `prose_watermark_clean`（Layer B 统计水印最大努力改写扰动）；新增只读合成水印检测（CtrlRegen 纯 CPU 内置检测器 + SynthID 可选适配器，`POST /api/v1/assets/{asset_id}/deep-watermark-detect`，视频载体抽帧检测）；新增显性可见水印去除（`POST /api/v1/assets/{asset_id}/watermark-remove`，delogo/blur/crop，图片/视频，生成派生副本不覆盖原文件），审计去水印页扩展为「素材审计与去水印」。轻量内容包现已统一覆盖绘本/漫画、科普、平台图文和单镜头：从主题或素材开始，不强制正文、大纲、圣经；完整叙事方案继续保留短剧/小说的细纲、演绎和正文链路。剩余：任务 16 平台/编辑器边界区分、任务 19 浏览器 smoke、任务 25 外部 Agent API 鉴权 | `openspec/changes/content-production-orchestration/` |
| 外部 Agent API | 已有能力发现、素材上传、生图/生视频/3D、任务、事件日志和素材详情接口；外部 Agent 仅通过平台 API 使用页面已配置的连接器，不接触供应商密钥。已落地平台级 `ExternalApiKey` 鉴权（`/api/v1/external-api-keys` 生成/列出/撤销，Bearer 校验 + read/write/generate 作用域 + 每 key 限流 + `generate` scope 消耗配额），覆盖生图/生视频/文本/3D/素材上传与素材详情/日志/能力查询，支持强制开关 `YLCRAFT_EXTERNAL_API_REQUIRE_KEY=1`；待任务详情等剩余读接口与公开示例 | `docs/guides/external-agent-api.md`、`openspec/changes/content-production-orchestration/tasks.md` |
| 3D 模型查看器 | 独立全屏页、GLB/GLTF/OBJ 渲染、渲染模式（纹理/白模/线框/反照率/法线）、灯光面板、视角对齐、包围盒、拓扑角标、键盘平移已完成 | `frontend/src/components/asset-hub/Model3DViewer.tsx`、`frontend/src/pages/model3d-viewer/` |
| 素材库上传与缩略图 | 通用本地上传（图片/视频/音频/文本/3D）、3D 模型前端渲染截图缩略图、视频第一帧缩略图、删除容错已完成 | `backend/app/api/v1/assets.py` |
| 远程对象存储（COS） | 手写签名上传、密钥入库 `system_settings`、设置页「密钥配置」Tab、Agnes 图生视频公网 URL 已落地 | `backend/app/services/cos_storage.py` |

## 每次开发后必须更新什么

| 改动类型 | 必须同步 |
| --- | --- |
| 新增/修改 HTTP API | `docs/architecture/API_SURFACE.md` 和 `docs/architecture/api_surface.json`；如影响模块职责或工作流，再更新 `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`、领域文档或 OpenSpec。 |
| 新增平台功能或 HTTP API | 同步检查并更新受影响的 API-facing Skill（`SKILL.md`、流程参考、调用脚本及测试）；外部 Agent 只使用平台 API 和能力发现结果，不配置或持有供应商密钥。 |
| 新增/修改 Agent Tool / Skill | 工具 schema、risk level、测试、`docs/agent/agent-skill-runtime.md`；如改变运行时边界，再更新总架构。 |
| 新增/修改数据库字段 | Alembic 迁移、模型说明；如需人工执行，在 final 或必要 devlog 里写清命令。 |
| Agent 工具/Skill 变化 | `docs/agent/agent-skill-runtime.md` 和相关测试。 |
| UI 结构或交互变化 | 对应页面文档或必要 devlog 截短说明，不把视觉想法散写到聊天里。 |
| 阶段性完成 | 优先更新架构/领域文档；只有跨电脑/长任务交接才写 `docs/devlog/YYYY-MM-DD_topic.md`。 |

`tools/generate_api_surface.py` 只能同步路由事实，不能替代架构判断。跑完脚本后仍要检查：接口语义是否变了、前端调用是否受影响、Agent 工具是否要同步、OpenSpec 任务是否要勾选。

`creative-project-narrative-runtime` is complete and remains the source of truth for the audited Story runtime, guarded narrative runs, cross-modal provenance, and real-provider image closure until it is archived.

## 文档清理原则

- 不再新增根目录散文档，除非是 `README.md`、`AGENTS.md` 这类入口文件。
- 过期方案能删就删；当前格式的已完成变更归入 `openspec/changes/archive/`；旧格式规格归入 `openspec/archive/`；外部参考放 `docs/reference/`。
- 同一主题只保留一个当前事实来源，历史细节依靠 git 历史或必要 devlog。
- 参考资料和实现文档分开：`docs/reference/` 不是实现状态。
- `docs/devlog/` 是历史推进记录，不是新 AI 默认必读入口；当前事实要沉淀回架构、接口或专题文档。
