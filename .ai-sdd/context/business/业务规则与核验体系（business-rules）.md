# 业务规则与核验体系

来源：`task-observability-diagnostics` 实现与其代码；§6 写作风格档案规则来自 `creative-writing-style-profiles`。最后更新：2026-09-11。

## 1. 任务持久化规则

| 规则 | 内容 | 证据 |
|---|---|---|
| 双条件落库 | 任务写入 `project_task_records` 需**同时**满足：`task_type` 命中 `PERSISTED_TASK_TYPES` **且** payload 带 `project_id` | `backend/app/services/task_persistence.py`（`should_persist`） |
| 白名单 | `image_generation`、`creative_writing`、`world_domain_expansion`、`world_map_visual` | 同上 |
| 不挂项目任务放行 | `novel_download`、`live2d_processing` 经 `PERSISTED_STANDALONE_TASK_TYPES` 豁免 `project_id` | 同上 |
| 不落库须说明原因 | `should_persist` 返回 False 时必须打日志，否则表现为"任务凭空消失"无从排查 | tasks #29 |

## 2. 重启对账

进程重启后首次恢复持久化任务时，把残留的 `pending`/`running` 收尾为失败并置 `progress_message = "服务重启，任务中断"`。
目的：避免任务中心出现永远转圈、进度不动的僵尸任务。证据：`backend/app/core/task_queue.py`（`restore_persisted_tasks` → `_mark_interrupted`）。

## 3. 重试 / 重发边界

| 场景 | 允许条件 | 行为 |
|---|---|---|
| 事件重发 | `status=failed` 且带 `retry_payload`；否则 409 / 400 | 支持 `image` / `video` / `llm` 三类 scene；重发产生新事件并写 `retry_of` 追溯链 | 
| 任务重试 | 仅失败/取消的 `video_generation`、`model3d_generation` | 读账本 `request_json` 重建参数 → 复用生成端点重提交（产生新任务，原任务保留） |
| 绑骨任务（3D `kind=rigging`） | 不允许一键重试 | 指引回工作台重新发起 |
| 图片任务 | 不在任务中心重试 | 指引到事件日志 Tab 重发（那里有完整可重放参数） |

证据：`api/v1/logs.py:190`、`api/v1/tasks.py`（`retry_task`）。

## 4. 事件内容约束

| 约束 | 内容 | 证据 |
|---|---|---|
| 敏感字段屏蔽 | 事件 `data` 与响应摘要按 `SENSITIVE_KEYS` 替换为 `***`（api_key / authorization 等） | `core/task_queue.py:24`、`:61` |
| 长度截断 | 摘要超过 `MAX_SUMMARY_LENGTH`（20000）时截断并追加 `...(truncated)` | `services/platform_log/service.py` |
| 事件条数上限 | 每个任务最多保留 `MAX_TASK_EVENTS`（100）条 | `core/task_queue.py:22` |
| 不采集 | 完整请求体、API Key、完整图片 base64、完整第三方响应 | proposal `Non-goals` |

## 5. 常见误用与防呆

- **前端任务类型下拉必须与后端白名单同步**：`TASK_TYPE_OPTIONS` 缺项会让用户筛不到任务（曾出现 `novel_download` / `world_map_visual` 漏配）。
- **`GET /api/v1/tasks` 是轻量接口**：默认不返回 `payload/result/diagnostics`；传 `project_id` 时会隐式启用 detail 以完成过滤，但**不会**把 payload 返回给调用方（除非显式 `include_detail=true`）。
- **列表接口的 prompt 可能是预览值**：提示词类列表用 `preview=True` 截断（如 360 字），需要全文必须取详情（曾导致插入生图框的提示词残缺）。

## 6. 写作风格档案规则

<!-- 来源：openspec/changes/creative-writing-style-profiles，导入日期：2026-09-11 -->

| 规则 | 内容 | 证据 |
|---|---|---|
| 生命周期 | `draft → reviewed → active → archived`；`restore` 使 `archived → draft`，**绝不直接跳到 reviewed/active**（材料闸门必须重跑） | design.md「Lifecycle」、`api/v1/writing_styles.py` |
| 归档 ≠ 删除 | 归档后不再进入运行时选择，但 `project_writing_style_links` 记录保留；取消归档后也不自动生效，需重新 review + activate | 测试用例（归档→恢复→重走闸门） |
| 提取恒为草稿 | 提取**绝不自动激活**；激活与绑定是分离步骤，且 `activate` 只接受 `reviewed` | tasks #6 |
| 材料闸门位置 | 泄漏/合规闸门放在 `review` 与 `activate`；**违规档案可留在草稿里查看与修正，但进不了生效链路**；编辑草稿后闸门自动重算 | tasks #11 |
| 泄漏判定阈值 | ① 来源专名/禁用词污染；② 与来源样本**连续 12 字重合**（复述原文）→ 判违规；③ 新造示例与样本 **8-gram 重合率 ≥ 0.12** → 仅告警 | tasks #11 |
| 导入不是免检通道 | Markdown Skill 导入同样产出 `draft` 并跑同一套材料检查 | tasks #10 |
| 强度决定注入量 | `subtle` / `balanced` / `strong` 分别注入最多 **8 / 16 / 24** 条规则与 **1 / 2 / 4** 个新造示例，注入块标题标注两字标签（参考 / 贴合 / 严格） | `INTENSITY_POLICY`、本轮实现 |
| 风格审阅只报告 | `review_prose_deviation` 比对实测与基线，severity 阈值 warn 0.35 / off 0.75；**绝不改写正文或档案**（风格是软约束，偏离多少由人决定） | tasks #12 |

## 7. Agent 工作台规则

<!-- 来源：openspec/changes/agent-workbench-ui-redesign，导入日期：2026-09-12 -->

| 规则 | 内容 | 证据 |
|---|---|---|
| 顶栏模型/工作流写回配置 | 顶栏的「模型」与「默认工作流」**直接写回当前智能体配置**（`updateAgentProfile`），不是本次请求的临时参数——run 载荷不含 model/mode 字段，而这两项决定运行时行为。UI 须给出「已保存到智能体配置」反馈 | `applyProfileSetting` |
| 拒绝工具确认 = 取消整个运行 | 后端**无 step 级 reject 端点**，「拒绝」复用 `cancelAgentRun`；必须用二次确认写明后果（"后端暂不支持只跳过这一步，拒绝会取消当前整个运行"） | `handleRejectRunStep` + `Popconfirm` |
| 会话状态点「有数据才显示」 | 只在状态可知时渲染状态点；无数据**不渲染**，不用默认值或推测值冒充 | 左栏会话列表 |
| 遥测缺失显示 `--` | 缺失显示 ASCII 双连字符 `--`（不是中文破折号 `—`）；无 run 时「步骤」「工具」也显示 `--` 而非 0 | 底部遥测条 |
| 卡片收敛的四类例外 | 优先用 `borderTop` 分隔线 + 留白替代带边框卡片；**保留边框**：① 页面外壳 ② Markdown 表格单元格 ③ 选中态（左栏 section / 工具授权 / 会话激活）④ 错误与待确认隔离。虚线占位区亦保留 | design §4 |
| 窄屏折叠按类名不按序号 | ≤820px 折叠次要控件用 `.agent-rail-optional` 类名，**不要**用 `:nth-child(n)` | `index.css` |
| 缓存区 opt-in | cache 命中率 / 首 token 均值依赖 provider usage 数据，数据不可用时**整个区块不渲染**（代码中不存在即为正确状态） | design §3.4 / §5 |


## 8. 世界构建规则

<!-- 来源：openspec/changes/ai-progressive-world-building，导入日期：2026-09-12 -->

| 规则 | 内容 | 证据 |
|---|---|---|
| 结构变更必须过闸 | 模型输出分 `items`（内容）与 `suggested_fields`/`suggested_domains`（结构建议）；建议落 `world_domain_definitions` 且 `source=ai_suggested`、`is_enabled=False`，**不自动生效** | `_persist_suggested_domains` |
| 生成内容不得伪造证据 | `origin=ai_draft` 的候选 `evidence_json="[]"`；审阅页与导出均带来源标注 | D2 / R6 |
| 写入唯一通道是 `apply` | 生成只产候选，正典写入只能经 `POST /world-extraction-runs/{id}/apply` | D5 |
| 内置域字段只可追加不可删除 | 保证历史 `attributes_json` 始终可解析 | `resolve_specs` |
| 契约外字段转建议而非丢弃 | 服务层只接受「已勾选且在属性契约内」的值，其余转为 `suggested_fields` | `expand_entity` |
| 幂等去重 | 候选 `fingerprint = gen:{project_id}:{entity.id}` | `world_generation.py` |


## 9. 写作前置检查规则

<!-- 来源：openspec/changes/creative-project-writing-guardrails，导入日期：2026-09-12 -->

| 规则 | 内容 |
|---|---|
| preflight 必须只读 | 不创建 `ProjectNarrativeContextSnapshot`、不调用模型，仅投影既有状态 |
| 返回值契约固定 | 归一化 `stage` 与 `chapter_number`、有序 `checks`（`pass`/`block`）、`ready`、`blockers`、可执行的 `next_action`、可用章节大纲 source id、兼容方法与 checksum |
| 生成方法仍是权威 | preflight 只做前置判断，不替代生成逻辑；未就绪时应解释并修复而非强行生成 |
| opt-in 方法包默认不生效 | `auto_apply=false`，须在项目设置中被选中才写入 T6 |
| 禁止性变更保留既有边界 | 方法包只贡献"怎么写"的方法指导，不突破候选/正典边界 |


## 10. 制作台规则

<!-- 来源：openspec/changes/story-production-desk，导入日期：2026-09-12 -->

| 规则 | 内容 |
|---|---|
| **不持久化独立阶段状态** | 制作台不存"当前阶段是否完成"的字段；完成度在渲染时由 `/story` 已加载的项目资源算出 |
| **六条完成度定义** | 故事蓝图＝非空大纲；项目设定＝至少一条 project-bible 或 world-asset 记录；章节计划＝非空章节计划；分集生产＝（最新章节大纲＋已批准正文＋脚本＋分镜记录数）÷（计划章节数×4）；写作审阅＝有 `prose_review` 候选的章节 ÷ 有已批准正文的章节；关系与交付＝至少一条项目关联资产 |
| **计数只是状态指示** | 计数**从不**提升候选、从不标记生产运行成功、也**不隐含**供应商成本 |
| **批量生产非破坏性收纳** | 收进紧凑折叠，但保留依赖顺序、skip-existing 行为与失败重试语义 |

**通用原则**：派生状态优先"渲染时计算"，不要为一个可由既有权威记录推出的结论新增持久化字段——那会产生第二份真相。


## 11. 数据库迁移与 DDL 安全规则

<!-- 来源：openspec/changes/database-migration-convergence，导入日期：2026-09-12 -->

| 规则 | 内容 |
|---|---|
| **升级是运维动作，不是请求路径动作** | `alembic upgrade head` 只能由运维/部署显式执行；应用**永不**自动升级远程库 |
| **每条运行时 DDL 必须有归宿** | 三选一：被某个 revision 表示 / 作为记录在案的临时兼容例外保留 / 其迁移验证通过后移除 |
| **升级前必须备份并记录 `alembic current`** | 远程库升级前先备份并留存当前 revision |
| **迁移测试只用一次性数据库** | 迁移测试**不得**连接或改动配置中的远程库 |
| **部署完成判据三合一** | `alembic current` 到位 + 针对性 API 检查 + 启动日志确认 head 且未触发兼容 DDL |


## 12. 创作项目动态状态规则

<!-- 来源：openspec/changes/creative-project-dynamic-state，导入日期：2026-09-12 -->

| 规则 | 内容 |
|---|---|
| **内容不设 schema，信封必设 schema** | `value_json` 自由 JSON（标量/列表/对象），但 `project_id`/`scope`/`key`/`op`/`chapter_number`/溯源字段都有约束 |
| **append-only + fingerprint 去重** | `fingerprint = sha256(project:scope:key:op:value:chapter:source)`；已存在则跳过，重批也不产生重复 |
| **折叠语义** | `set` → 覆盖；`add` → 数值 `+`、列表 `union`（去重）；`remove` → 数值 `-`、列表 `差集`、标量删键 |
| **折叠顺序确定** | 按 `(chapter_number, created_at)` 折叠，保证同章多次重批结果稳定 |
| **章节重批用 supersede** | 先删该章旧条目再落新条目 |
| **隔离原则** | 静态设定（`Character` 性别/外貌/性格/能力、`CharacterStoryLink` 项目覆盖）**不碰**；锁定事实（`project_bible`/`world_asset` 且 `is_locked`）**不碰**，继续只读注入；动态状态**只**进 `ProjectStateEntry` |


## 13. 创作项目叙事运行时规则

<!-- 来源：openspec/changes/creative-project-narrative-runtime，导入日期：2026-09-12 -->

| 规则 | 内容 |
|---|---|
| **正典 vs 提案分界（核心）** | 只有 `novel_body`（人工 promote）与**锁定**的 `project_bible`/`world_asset` 可作**硬约束**进入生成；快照是有界状态（仅能由**源版本重放**改变）；事件/伏笔是软状态（仅显式动作或确定性重放可改状态）；**判定候选永不自动接受**；Writer Room 候选、Canvas/资产/Agent 线程数据默认**不进**上下文 |
| **派生状态必须可溯源** | 快照/事件/台账行**始终**带 `project_id` / `source_content_id` / `source_version` / `chapter_number` / 源指纹 / 抽取与运行溯源 |
| **源版本替换用 supersede 而非销毁** | 新版已批准正文**取代**旧版派生的状态，旧状态仍保留可查 |
| **Aftermath 幂等** | 幂等键 = `source_content_id + source_fingerprint + pipeline_version`；仅在 `novel_body` 创建或**显式重放**后调度 |
| **失败隔离** | 富化失败**不影响已批准正文的有效性**；运行标记 `partial` 并列出可重试的失败阶段 |
| **重放必须用同一源版本** | 绝不"因为有同号章节就顺手用最新章" |
| **待决候选不得泄漏** | 待决候选、未批准台账行、agent 记忆、游离 canvas 数据**永不进入 T0–T5**；当前候选可作为"重写来源"显式提供，但**必须标注为候选而非正典** |


## 14. Agent 工作台信息架构规则

<!-- 来源：openspec/changes/agent-center-conversation-workbench-redesign，导入日期：2026-09-12 -->

| 规则 | 内容 |
|---|---|
| **主任务优先** | 管理信息不得淹没主任务；高级能力（工具测试、Profile 编辑、运行树）**不删除、只降低默认层级** |
| **辅助能力失败不阻塞聊天** | 线程、Profile、工具、记忆、模型、运行详情各有**局部** loading / error / retry；**不因辅助接口失败而整页报错** |
| **恢复失败必须显式** | 线程恢复失败要明确告知，且**不得创建重复会话** |
| **保留部分产出** | 请求失败时保留**已流式产出的部分输出**与重试入口，不清空 |


## 15. 小说来源与世界提取规则

<!-- 来源：openspec/changes/novel-source-world-project，导入日期：2026-09-12 -->

| 规则 | 内容 |
|---|---|
| **证据必须逐字命中** | 抽取值必须**逐字**落在某个文本块/偏移上，否则该条目**直接丢弃**（不是降级保留） |
| **候选先于正典** | 模型抽取的设定**绝不自动成为正典**；必须先人工/Agent 确认 |
| **`apply` 是唯一写入点** | `POST /world-extraction-runs/{run_id}/apply` 是写入项目的**唯一**通道；未提供项目时自动创建世界项目 |
| **角色复用既有 Character** | 角色写入既有 `Character` + `CharacterStoryLink`，**不建平行的"小说世界角色"实体** |
| **复杂域物化为独立实体** | 势力/地点/物种/历史事件/战力/物品等物化为 `WorldEntity` + `WorldEntityRelation`，与 `world_asset` 事实卡**并存**（事实卡仍是锁定正典的权威载体） |
| **只有完本来源可派生** | 派生项目（`adaptation`/`continuation`/`fan_work`）**仅对完本来源开放**；来源快照**始终只读** |
| **连载走增量同步** | `sync` 只追加新章节与新块，**既有章节偏移与证据锚点保持稳定**；增量提取从 checkpoint 起只喂新块 |
| **向量失败不阻断** | 未配置或向量失败时，证据校验**稳定降级**为精确/顺序检索 |


## 16. 创作项目闭环规则

<!-- 来源：openspec/changes/creative-project-closed-loop，导入日期：2026-09-12 -->

| 规则 | 内容 |
|---|---|
| **阶段感知生成（核心）** | ① 大纲只用创意或小说摘要；② 章节计划必须用**已保存**的大纲；③ 单话细纲用大纲 + 章节计划；④ 正文/脚本用细纲 + **锁定的**角色/世界观数据；⑤ 分镜用脚本场景 + 视觉风格 + 角色外观 |
| **JSON-first + 校验 + 一次修复** | 系统提示词定义角色/输出 schema/禁 Markdown；后端 Pydantic 校验；失败则带校验错误**修复一次**；原始请求响应、模板元数据与归一化结果都进生成日志 |
| **生成单元必须独立存储** | 阶段产出不可全藏在单个大 JSON 里——分开存才能重生成/版本化/关联/检索/复用 |
| **每个生成资产必须记录谱系** | 必须记录 project id、content id、prompt、model、provider 与来源关系 |
| **实验模块不得阻断主流程** | 历史半成品应标注并在主导航收拢，不得打断用户 |
| **资产双轨先用兼容层** | 普通素材表与资产中枢并行时先做兼容层，再逐步统一，不一次性大迁移 |
| **画布状态先存项目 metadata** | 必要时再提升为独立表，避免过早引入新表 |


## 17. 提示词参考库规则

<!-- 来源：openspec/changes/image-prompt-reference-library，导入日期：2026-09-12 -->

| 规则 | 内容 |
|---|---|
| **提示词引用不自动入素材库** | 选中/插入提示词引用**不会**自动成为 Asset Hub 条目；只有**生成的图片**才入资产中枢并带谱系 |
| **生成物仍须带谱系** | 经提示词库生图时，生成图照常写入 Asset Hub 并记录来源关系 |
| **同步本地优先** | 来源刷新**默认本地优先**；远端抓取需显式 `force_remote` 或 UI 的"远端更新"模式 |
| **按来源 + 外部 id 去重** | 同一来源内重复条目按 external id 去重，重复同步不产生重复行 |
| **分面选项彼此独立** | 模型/来源/标签三组分面互不影响：选一个分面只改结果集，**不改其他分面的可选项** |


## 19. 图转 3D 与绑骨规则

<!-- 来源：openspec/changes/image-to-3d-workspace，导入日期：2026-09-13 -->

| 规则 | 内容 |
|---|---|
| **输入守卫（默认 image）** | 默认 `image` 模式；未提供参考图/素材时点提交会被 `message.warning` **静默 return**，不发请求 |
| **结果必须入资产中枢并带谱系** | 完成的 3D 结果写入 Asset Hub，`source_type=image_to_3d` |
| **供应商任务 id 与本地账本 id 分离** | 供应商 id 可能是"不透明编码载荷"；本地用 `model3d_<hex>` 短 id，原始 id 另存供轮询 |
| **绑骨需要源模型公网可达** | 腾讯云绑骨只接受**公网可达**的 GLB/FBX；优先 COS 上传 + 24h 签名 URL，否则回退 `BASE_URL + /model3d-files/public/`（本地 `127.0.0.1` 必然失败） |


## 20. 角色册与角色流程规则

<!-- 来源：openspec/changes/character-management-redesign，导入日期：2026-09-13 -->

| 规则 | 内容 |
|---|---|
| **两类角色流程门禁不同** | `extract`（从小说/正文提取）与 `character-first`（角色先行再演绎）**不共享**强制正文/大纲门禁；角色先行可直接进入设定、参考图、关系与 Prompt 资产包，再选择性回流 Story/生产线 |
| **字段来源分层** | `field_sources`：外来文本 → `original`、原创大纲 → `ai_inferred`、用户手填 → `user_edited`；**同步流程只补空缺，不覆盖已有来源** |
| **角色册完善度只用列表字段** | 完善度与摘要必须由**列表接口已返回**的字段计算，不得逐项请求详情——窄栏里为每个角色各发一次详情请求会明显拖慢列表 |
| **完善度阈值要按真实填充率设计** | 实测 20 个角色：`background` 20/20、`personality` 18/20、`identity` 15/20、`appearance`/`age_range`/`arc` 各 11/20、`ability`/`behavior`/`motivation`/`speech` 各 3/20、`voice` **0/20**。阈值不按此分布设，会全员"完善"或全员"未完善" |


## 21. 视频生成规则

<!-- 来源：openspec/changes/ai-video-workspace，导入日期：2026-09-13 -->

| 规则 | 内容 |
|---|---|
| **提交不阻塞** | `/videos/generate` 立即返回 provider 任务 id，不等待完成 |
| **终态轮询只入库一次** | 终态时把本地视频导入 Asset Hub **且仅一次**，并保留项目谱系 |
| **项目谱系用 `role=output`** | 与生图路径的 `role=generated` **不同名**——按 `generated` 断言会误判"没有谱系" |
| **能力约束由后端声明** | 前端不得自行假定支持哪些时长/分辨率/比例，必须以 `/videos/backends` 的 `constraints` 为准 |
| **图生视频需公网首帧** | Agnes 的 `image_requires_public_url=true`：首帧必须公网可达，本地 `127.0.0.1` 不行（与 3D 绑骨同理）；**文生视频无此约束** |


## 22. Supervisor 与子代理运行时规则

<!-- 来源：openspec/changes/agent-supervisor-subagent-runtime，导入日期：2026-09-13 -->

| 规则 | 内容 |
|---|---|
| **子结果汇合后重进父规划** | 汇合结果作为 observation 写回原父 Run（`resume_from_delegation_observation`，metadata `phase=delegation_join_observation`），并**继续同一个 `RunLoop`** |
| **失败不得降级成文本** | 子失败必须是失败状态，不能变成父级看到的"成功输出" |
| **子确认/取消向父传播** | 汇合时若有子处于 `waiting_confirmation`，join status 即 `waiting_confirmation`，父 Run 状态同步置为该值，并在 summary 计数 |
| **确认后的自动续跑必须由用户触发** | 避免确认接口静默启动新一轮成本型执行 |
| **文案必须匹配真实执行模型** | 确定性顺序服务阶段**必须**表述为 staged workflow；只有**含持久子 Run** 的才可称多智能体，**且须同时暴露 responsible profiles 与执行树作为证据** |
| **域内 agent 循环保持独立** | CutClaw 等域自有 LLM 工具循环通过 Agent 工具（如 `start_cutclaw_clip`）与日志接入即可，**不强行纳入 Supervisor 语义** |


## 23. 声明式团队组合规则

<!-- 来源：openspec/changes/agent-team-composition，导入日期：2026-09-13 -->

| 规则 | 内容 |
|---|---|
| **模板校验失败绝不 fallback** | 依赖环、缺 join、未知 profile ⇒ **结构化错误**，在任何子代理启动前拒绝；**绝不回退到已删除的硬编码执行路径**（避免静默回归） |
| **失败不得降级为普通文本** | 校验失败、运行时缺失、预算超限都以结构化失败呈现 |
| **模式切换不增删工具** | 变更类工具保留在目录里，用**追加的指令文本**覆盖行为；隐藏工具会破坏从首个变动 schema token 起的缓存复用 |
| **压缩是有损状态迁移，不是效率优化** | 压缩产物必须携带源 span 引用 + 摘要版本 + 确定性展开路径 + prompt/schema 引用，否则等于制造"无版本的记忆替身" |
| **能力挂载即授权变更** | 角色能力是权限授予；能力变更应先产出 diff 再走审批，而非静默生效（审批路由当前**未实现**，见缺口） |
| **归档前必须核对 delta spec 是否描述了未实现的行为** | 本次归档前发现该 change 的 delta spec 有 **3 处**描述尚未实现（plan/batch 模式下的目录稳定性、能力变更的审批路由、persona/plan-mode 实例化），已按事实收窄后再归档。**原样归档会让主 spec 长期宣称不存在的能力** |


## 24. 内容包与平台适配规则

| 规则 | 说明 |
| --- | --- |
| **校验分两档，结构性问题才硬拒** | 硬错误仅限不可安全落库者（未知包类型、items 非数组、`status` 越界、条数超上限）；内容质量类（条数偏低、缺推荐字段、整包无媒体提示词）只收 `warnings`。"先存标题、再补提示词"是内容包增量编辑的正常中间态，硬拒会让调用方存不了半成品。 |
| **schema 是条数的唯一权威** | 生成数量按 `package_type` 的上限夹取（`single_media` 上限 1）。若放任（按默认 12 条生成），保存时会被按类型拒绝，表现为"生成成功但保存失败"。 |
| **适配器三条边界** | 不调外部平台、不写回源包、不保存第二份事实源。平台产物含正文文字是必然的（那是产物本身），禁止的是把 `items` 再存一份当可编辑事实源。单个适配器失败不影响其它（该条记 `failed`，可独立重建）。 |
| **产出哪些适配器由方案声明决定** | `profiles.py` 的 `output_adapters` 是运行时依据：不传 `adapters` 时按方案全出（绘本→PDF+素材包；科普/平台图文→公众号+小红书+素材包；单镜头→素材包）。 |
| **过期按依赖判定** | 只有 `source_item_ids` 命中变更条目的输出被标 `stale`。当前五个适配器都产出**整包级**产物，故改任一条都会让全部输出过期——这是依赖判定的正确结论，不是无差别作废。 |
| **单条重跑不重规划整包** | 省 token，且不会冲掉用户已手改的条目。 |
| **导演计划按族使用各自阶段词表** | 内容包族用 `PACKAGE_PLAN_STAGES`，叙事族保持既有阶段。词表是**路由输入（指导）而非校验器**：计划节点的 `stage` 仍是自由字符串，未知值不被拒绝。 |
| **归档前必须核对 delta spec 是否描述了未实现的行为** | 本次归档前发现 **5 处**过度声明（素材规划未消费、文章包/轮播包的包级字段未生成、批量"逐条勾选"未实现、任务中心只对异步供应商成立、"共享服务"范围被夸大），已按事实收窄后再归档。 |
| **`content_package` 目前只有项目内一条路径** | 无"独立草稿"（`content_package_drafts` 全仓 0 命中），因此没有"把独立包绑定到项目"的对象。 |
