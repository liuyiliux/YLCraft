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
