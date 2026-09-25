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
| `docs/research/` | 专题调研产出：排查计划与结论报告（如任务/事件记录覆盖梳理）。 | 结论要回写到架构或领域文档，这里保留完整推导过程。 |

平台接入入口：`docs/platform/BILIBILI_GUIDE.md`、`docs/platform/FANQIE_GUIDE.md`；其余跨平台对比资料仍在 `docs/platform/MULTI_PLATFORM_REFERENCE.md`。本地历史归属维护见 `docs/guides/owner-backfill.md`。

## 当前主线状态

> **2026-09-25 update:** `triposr-connector-migration` is no longer planning-only: its connector migration and focused tests are complete, while the real-provider smoke remains unverified because no key is available. `unirig-local-rigging-service` has completed tasks 1-3 (pinned revision/license/checkpoints, sidecar contract, connector mapping); Phase 2+ is deferred because the current machine has 6GB VRAM, below the upstream 8GB minimum, and the user is not buying a supported GPU now.

最近更新：2026-09-25。本轮归档五条线：`user-authentication` 18/18（服务端会话 + HttpOnly Cookie、外部 Agent `ylk_` Key 任一通过、`owner_user_id` 可空的平滑迁移；认证/归属后端测试重跑 14 例通过）、`asset-library-list-performance` 16/16、`task-detail-diagnostics-normalization` 25/25、`previs-ai-copilot` 13/14（3.2 / 3.3 真浏览器验收已完成；2.5「程序化模型本期不做」明确保留未勾）、`legacy-owner-backfill` 7/7（五张历史归属表已复核归到本地 `root`，并新增默认 dry-run、显式 `--apply`、幂等测试的运维入口）。归档目录为 `openspec/changes/archive/2026-09-25-*`。`3d-rigging-digital-human` 的任务 13 / 14 已拆到独立 change `unirig-local-rigging-service` 与 `triposr-connector-migration`。`triposr-connector-migration` 已切到配置驱动连接器，focused tests 通过，真实供应商 smoke 因当前没有可用 key 仍未验证；`unirig-local-rigging-service` 已完成任务 1-3（上游 revision、MIT 许可、权重校验值、sidecar 契约、连接器字段映射），Phase 2+ 因当前机器 6GB 显存低于官方 8GB 最低要求、用户暂不购买设备而暂缓。

上一轮（2026-09-14）：内容包链路**已成链并归档**（`content-package-workspaces` 20/21，落地 capability 6 条需求），三条线：

**① 内容包链路成形并归档**（`content-package-workspaces` 20/21）。内容包六种类型有了集中式契约 schema（`article_package` / `social_carousel` / `shot_list` / `single_media` 标记为 API-only，本期不建 UI；校验分「结构性硬错误」与「内容质量软提示」两档，避免 LLM 抖动直接变成保存失败）；五个平台适配器落地并接入 `outputs[]`（公众号 / 小红书 / 短视频 / PDF / 素材包，**按产出形态命名而非平台**，不调外部平台、不写回源包、带 `source_package_id`/`source_package_version`/`source_item_ids` 溯源，单个适配器失败可独立重建，产出集合由方案声明的 `output_adapters` 决定）；条目级重试与 `stale` 语义（只重跑一条，其余原样保留，依赖它的输出按依赖判定过期）。规划逻辑从 `outline_service.py` 提取为可复用 `ContentPackagePlanner`，原 `generate_outline` 变 39 行兼容委托。

**② Agent 运行时收口并归档**。`agent-team-composition` 归档（21/23，两项前置不存在已如实标注），落地 capability 8 条需求。归档前**按事实收窄了 delta spec 三处过度声明**（审批路由、plan/batch 模式下的目录稳定性、persona/plan-mode 实例化），避免主 spec 长期宣称不存在的能力。`AgentScope.enter_scope()` 接缝与 `AgentService` per-session 状态接线完成 —— 价值是把隔离从"约定"升级为"结构保证"（复核发现原描述的"角色共享可变实例"缺陷当时并不存在）；压缩请求开始携带显式 `system_prompt_ref`/`tool_schema_ref`。

**③ 平台 Cookie 规范化收进公共基类**（修线上故障）。B站搜索返回空的根因是 `_build_headers` 把 Netscape 文件原文塞进 HTTP `Cookie` 头（含换行/制表符）被 httpx 拒绝，请求根本没发出去；账号检测当时能用只是因为那条路径已先规范化。**同一凭证、多条路径、只有部分做了规范化** —— 本项目已踩第 4 次（`to_storage_path` 读写不对称、`_get_conn_cookie` vs 公众号路径、bili vs 小红书 vs 番茄、浏览器路径静默失败）。现统一收在 `BasePlatformClient.header_cookie()` 并在 `_init_http_client` 强制覆盖注入，**单个平台客户端即便写错也会被纠正**（有"故意写错"的子类测试固定这一点）。

另：内容搜索页列宽可拖拽（含 localStorage 持久化）、封面按 16:9 占满列宽随列宽缩放；提示词参考选择器补缩略图、弹窗定高左右独立滚动、列表分页。

上一轮（2026-09-07）：可观测性收口 —— 事件日志从「各端点手写」下沉到 `AIService` 三个入口统一记录（`ai_call_context` 注入业务身份），补齐地图生图、批量生图、agent 工具、Live2D 与两个直连绕过点（embedding / STT）；任务侧新增 `ai_task` 封装与持久化白名单不静默丢弃，世界地图成图进任务中心（完整排查见 `docs/research/research_report_task_event_logging_coverage.md`）。世界地图据点链路打通：`from-places` 按地点实体 `region` 属性自动建区域并归类、已有据点重跑补齐归属、初稿版本快照修正、工作台独立页加项目选择器与「生成全部形状」；提取侧 `region` 无同名地点时补建 `region` 实体并连 `part_of`。

上一轮（2026-09-05）：世界地图区域几何重构完成并归档（openspec/changes/archive/region-geometry-rework）：区域为独立形状（语义参数 + seed 前端确定性展开，20 种据点 kind + 图标），据点/Agent 工具/清库收尾；小说提取保留原文证据，真人和 Agent 均先预览后确认，确认不重复调用模型；角色库筛选、项目增量合并和正文角色上下文已完成。小说来源世界项目可选向量索引与混合检索、提取域扩展到八域（世界规则/力量体系/经济/物种）同走一条证据校验与写入通道；AI 渐进式世界构建已完成：expand_entity / expand_domain 生成链路与提取语义隔离（ai_draft 候选无证据、结构建议默认不启用需确认）、世界构建模板项目级自定义与 AI 起草、`/platform-templates`「世界构建」统一管理入口。

| 主线 | 状态 | 事实来源 |
| --- | --- | --- |
| Agent Skill Runtime | 已完成并归档 | `openspec/changes/archive/agent-skill-package-runtime/tasks.md` |
| Agent 上下文/父子 Run 基础运行时 | 已完成并归档；普通聊天仍以单 Agent 工具循环为主 | `openspec/changes/archive/agent-center-multi-agent-runtime/tasks.md` |
| Agent Supervisor/子智能体运行时 | 已完成（30/30）：独立子 Session、并行/依赖委派、父续跑（`resume_from_delegation_observation`）、子确认/取消向父汇合传播、层级/预算/并发诊断、执行树与委派 API、"委派并续跑"动作、Writer Room `team` 模式（每角色一子 Agent + editor 汇合）；前端构建与 Agent Center/Story 外部浏览器 smoke 通过 | `openspec/changes/agent-supervisor-subagent-runtime/tasks.md` |
| Agent 对话工作台 | 进行中：已收敛为对话优先双栏、内联轨迹、局部失败恢复和页面错误边界；待接入真实后端后的多轮对话人工验收 | `openspec/changes/agent-center-conversation-workbench-redesign/tasks.md` |
| Agent 工作台 UI 改造 | 已落地：markdown 表格/加粗渲染、总控助手提示词禁 emoji、确认显眼化、顶部控制栏（智能体/模型/默认工作流/会话日志/关键动作，模型与工作流直接写回智能体配置）、待确认横幅移入顶栏且可定位、底部遥测条（等宽，缺失显示 `--`）、左栏会话状态点、消息时间戳、卡片收敛为分隔线与留白、窄屏过滤区改 flex 换行；待真实视口目视验收，以及后端为 threads 列表补「最近一次 run 状态」以使全部会话都有准确状态点 | `openspec/changes/agent-workbench-ui-redesign/tasks.md` |
| Agent 声明式团队组合 | 已归档（21/23，落地 capability 8 条需求）：`AgentScope` 平面隔离（含 `enter_scope()` 接缝与 `AgentService` per-session 状态接线，隔离从"约定"升级为"结构保证"）、团队模板 schema/loader/validator、`TeamComposer`、`spawn/fork/continuable` 三原语、缓存稳定工具目录 + `CostMeter` + 压缩溯源（含显式 `system_prompt_ref`/`tool_schema_ref`）、per-role 授权溯源随子 Run 落库、Writer Room `team` 模式；旧 `MultiAgentCoordinator` 硬编码逻辑已去重。两项未勾且前置不存在：plan/batch 模式、能力变更走草稿审批（模板是仓库内 YAML，无运行时写入端点） | `openspec/changes/archive/2026-09-13-agent-team-composition/tasks.md` |
| 内容包工作台 | **已归档（20/21，落地 capability 6 条需求）**：六种 `package_type` 契约 schema（四种 API-only）、五个平台适配器 + 输出端点（按方案 `output_adapters` 出、带溯源三元组、不复制 items）、条目级重试与 `stale` 语义、`ContentPackagePlanner` 提取、**导演计划按族使用各自阶段词表**（内容包族用 `PACKAGE_PLAN_STAGES`）、6 个 Agent 工具、绘本页序可调、共享展示组件（`GeneratedMediaThumb`/`PackageOutputList`）、**批量生图端到端实测通过**（免费后端 Agnes：事件日志 3 条 success、Asset Hub 3 个素材、逐条溯源、独立重生成只影响目标条目）。未勾 1 项：`#16` 的"独立草稿绑定项目"无实现对象（`content_package_drafts` 全仓 0 命中） | `openspec/changes/archive/2026-09-14-content-package-workspaces/tasks.md` |
| 创作项目闭环 | 角色提取、角色库同步、项目回流、正文上下文注入和真人/Agent 双入口已完成；仅留真实生图后端人工验收 | `openspec/changes/creative-project-closed-loop/tasks.md` |
| AI 渐进世界构建（梯子原则） | 已完成：可扩展底座（`world_domain_definitions` + 域定义 CRUD，宗教/语言/文化/生态四域）、三档生成动作（`draft_world` 因既有「大纲→提取→审阅」链路承担而关闭，落地 `expand_domain`（异步接入任务中心）与 `expand_entity`）、世界构建模板（内置种子只读 + 项目私有可改可删可设默认；真人 `/story` 细化弹窗内嵌编辑与 `/platform-templates`「世界构建」Tab 统一入口；AI 起草草案不落库、确认后保存）、`prompt-preview` 不调模型、生成候选 `origin=ai_draft` 无证据且结构与字段建议（`ai_suggested` 默认不启用）经用户确认后才生效、上下文打包区分 AI 创作/大纲/原作正典。Agent 工具：`expand_world_entity_attributes` / `expand_world_domain` / `manage_world_building_template`（含 draft）/ `list_world_building_suggestions` 等 7 个 | `openspec/changes/ai-progressive-world-building/tasks.md` |
| 小说源资产世界项目 | 最小闭环与增量链路已落地，多来源共用同一套逐域提取/证据/候选/写入管线：TXT 上传、书架章节导入、创作项目大纲（`/story` 圣经/世界 →「生成世界设定候选」）、来源快照直接建项目（`from-novel-source`）、小说书架每本「提取世界」；十一个域（角色/地点/势力/历史事件/世界规则/力量体系/经济/物种/物品/术语表/剧情时间线）提取、证据预览与确认写入项目，连载同步（含追加章节 UI）+ 按游标增量提取（新证据并回既有候选，不重建世界，增量变更区分展示）；可选向量索引与混合检索（PostgreSQL 下走 pgvector 数据库级近邻、其它回退 JSON 向量混合，含邻域扩展）、跨域调和与语义矛盾检测、受影响事实传播、候选 merge、完本来源派生项目（改编/续写/同人，原作正典 `source_canon` 只读分层，Context Pack T0 已分层注入）已完成，类型化独立实体与关系（`world_entities`/`world_entity_relations`，含派生复制）也已落地，真人 `/novel-world` 与 14 个 Agent 工具共用同一服务层。世界地图工作台基于 Leaflet（CRS.Simple）实现拖拽/缩放/平移/底图上传/区域独立形状与不限层嵌套（区域几何语义见架构文档「区域几何」），保留 SVG 导出，并可用生图链路生成视觉成图（对齐角色立绘接入：选 provider/model/size、`prompt-preview` 先看提示词、成图入资产中枢，成图只是派生视觉资产，`map_json` 空间关系才是正典）。剩余：真实浏览器/Agent E2E 验收 | `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` §4.2.1、`docs/agent/agent-center.md`、`openspec/changes/novel-source-world-project/specs/novel-world-project/tasks.md` |
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
| 写作风格档案 | 进行中：`WritingStyleProfile` / `ProjectWritingStyleLink` 与草稿→审核→激活→项目绑定生命周期已落地（迁移 `043` 已执行），输入侧支持从来源快照测量聚合 + 有界抽象分析提取草稿、Markdown Skill 导入导出，来源材料泄漏检查作为审核闸门，生成后可做风格偏差审阅；真人入口 `/writing-styles`（世界观 → 写作风格），Agent 有 11 个工具共用同一服务层。剩余：人工与 Agent 的 E2E 验收 | `openspec/changes/creative-writing-style-profiles/tasks.md` |
| 任务观测诊断 | 已完成，事件时间线和异步生图诊断已验证；另补 AI 操作统一任务记账 `ai_task(...)`（`services/ai/tracking.py`）与持久化白名单不静默丢弃（不落库打日志说明原因），世界地图成图（`world_map_visual`）已登记白名单并进任务中心 | `openspec/changes/task-observability-diagnostics/tasks.md` |
| 全平台事件日志 | 三 Tab（任务/事件日志/运行日志）、`platform_event_logs` 表与 `/api/v1/logs`、滚动文件日志、失败重发均已落地；**事件记录已下沉到 `AIService` 三个入口统一收口**（`chat`/`generate_image`/`generate_video`，`ai_call_context` 注入 `project_id`/`ref_id`，支持 `suppress_auto_event`），此前只靠端点手写导致地图生图、批量生图、agent 工具、Live2D 完全不可观测；直连绕过点（embedding、breaker STT）已自补事件；前端场景选项补全到后端在用的全部 scene。剩余：端点层约 43 处重复 `record_event` 待清理、视频/3D 自有 Task 表待接入任务中心 | `openspec/changes/platform-event-logging/tasks.md`、`docs/research/research_report_task_event_logging_coverage.md` |
| 数据库迁移收敛 | Alembic 迁移链当前到 `035_add_world_map_documents`；启动和 Agent 请求路径不再隐式改 schema，角色提取证据、视频/图转 3D/动态状态/平台事件日志、小说来源世界提取、块级向量召回和结构化世界地图均通过显式迁移落库。`023` 会移除历史素材 AI 参数中并非供应商实际返回的采样步数与采样器默认值。 | `backend/alembic/versions/`、`openspec/changes/database-migration-convergence/tasks.md` |
| 独立视频工作台 | 文生/图生视频、视频提示词模板、素材库首帧、持久任务恢复、任务中心聚合和 Asset Hub 回流已落地；模式 tab 驱动供应商/模型过滤、`video_capabilities` 能力约束、视频首帧缩略图已补齐；仍待真实供应商全链路验收 | `openspec/changes/ai-video-workspace/tasks.md` |
| 图转 3D 工作台 | 配置驱动提交/轮询/下载、Asset Hub 入库、GLB 优先与 ZIP 解包、PreviewImageUrl 缩略图、独立页面已落地；仍待真实供应商生成 GLB 验收 | `openspec/changes/image-to-3d-workspace/tasks.md` |
| 3D 骨骼绑定与数字人 | 后端已落地：绑骨连接器（`SubmitAutoRiggingJob`/`DescribeAutoRiggingJob`）、`POST /model-3d/rig`、源模型经 COS 临时签名 URL 或 `/model3d-files` 暴露、部位树显隐与动画播放；仍待真实绑骨供应商端到端验收（需 ≤60MB 人形 GLB/FBX） | `openspec/changes/3d-rigging-digital-human/tasks.md` |
| 3D 导演预演台 | Phase 1 已落地：`PrevisSceneDocument` 持久化（可建独立场景，无需项目）+ revision 并发保护、`/story` 分镜入口与顶级导航入口（可新建独立场景或浏览场景列表）、可复用 3D 渲染原语（`scenePrimitives`）、静态导演台节点管理（Asset Hub 模型/人形占位单载体：可摆姿势胶囊人（真人比例，已下线 UE 白模与 Vanguard）/几何体/全景背景/图层可见性/重命名/删除/锁定）、相机 CRUD（名称/位置/目标点/FOV/锁定）与导演/活动机位双视角、安全框/九宫格叠加；待相机拖拽回写、截图回流、关键帧与 Agent 阶段 | `docs/architecture/3D_DIRECTOR_PREVIS_DESIGN.md`、`openspec/changes/3d-director-previs/tasks.md` |
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
