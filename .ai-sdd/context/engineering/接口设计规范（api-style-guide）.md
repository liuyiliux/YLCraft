# 接口设计规范（YLCraft）

来源：本项目现有路由与文档同步流程；§6 写作风格档案接口来自 `creative-writing-style-profiles`。最后更新：2026-09-11。

## 1. 落点与命名

| 约定 | 说明 |
|---|---|
| 前缀 | 统一 `/api/v1/<domain>`（如 `/api/v1/images`、`/api/v1/tasks`、`/api/v1/novels`） |
| 路由文件 | `backend/app/api/v1/<domain>.py`；业务逻辑放 `backend/app/services/<domain>/`，端点保持薄 |
| 前端调用 | 统一在 `frontend/src/api/index.ts` 导出（该文件较大，新增按领域就近放置，不做无关重构） |
| 请求/响应模型 | Pydantic `BaseModel`；响应统一带 `success` 字段，业务失败用 `success=false + error`（HTTP 层只用于输入/权限/不存在/冲突类错误） |
| 错误语义 | 参数/输入问题 → 400；不存在 → 404；状态冲突（如"只有失败事件可重发"）→ 409；服务未初始化 → 503 |

## 2. 任务与长耗时接口

- 长耗时生成类接口在**异步路径**返回 `task_id`，由前端轮询；同步路径直接返回结果。
- 任务相关接口在 `/api/v1/tasks`：列表（轻量）、详情（含 `diagnostics` + `events`）、`cancel`、`retry`、`delete`。
- 任务化必须配合任务账本与持久化白名单，见 `.ai-sdd/context/data/枚举值字典（enum-dictionary）.md`。

## 3. 事件与日志接口

| 接口 | 用途 |
|---|---|
| `GET /api/v1/logs` | 事件流筛选分页（scene / task_type / status / level / project_id / ref_id） |
| `GET /api/v1/logs/{id}` | 事件详情（含 request/response 摘要与 retry_payload） |
| `POST /api/v1/logs/{id}/retry` | 失败事件重发（仅 failed 且带 retry_payload） |
| `GET /api/v1/logs/{id}/generation` | 按事件取完整 LLM 生成日志 |
| `GET /api/v1/logs/runtime` | 读取滚动文件日志（支持 level/关键词/before 游标） |

**响应结构差异（易踩）**：`GET /logs` 列表项字段在**顶层**（`id`/`scene`/`task_type`/`provider`/`model`/`message`/`error`/`duration_ms`/`retry_of`/`retried_by`/`created_at`）；
而 `GET /logs/{id}` 是 `{"success": true, "item": {...}}` —— 详情的 `request_summary`/`response_summary`/`retry_payload` 都嵌在 `item` 里，不要按 `data` 取。

**重发边界**：`POST /logs/{id}/retry` 只支持 `image` / `video` / `llm` 三类 scene；非 `failed` 返回 409，缺 `retry_payload` 返回 400；重发成功或失败都会写一条新事件并用 `retry_of` 指回原事件，原事件 `retried_by` 指向新事件。

## 4. 文档同步（强制）

新增/修改/删除接口后必须执行：

```bash
cd F:/PycharmProjects/YLCraft
backend/venv_win/Scripts/python.exe tools/generate_api_surface.py
```

它会重写 `docs/architecture/API_SURFACE.md` 与 `docs/architecture/api_surface.json`（含全部端点与行号）。
手改这两个文件会在下次生成时被覆盖。

## 5. 鉴权与外部调用

- 外部 Agent 走 `/api/v1/ai/capabilities` 发现能力，凭证仅由平台侧连接器管理，不接受调用方传入 Key。
- `optional_external_api_key` 用于外部 API Key 可选的端点；内部直接函数调用时须显式传 `None`（见设计约束 §3）。

## 6. 写作风格档案接口

<!-- 来源：openspec/changes/creative-writing-style-profiles，导入日期：2026-09-11 -->

| 接口 | 用途 |
|---|---|
| `POST /api/v1/writing-styles/{profile_id}/restore` | 取消归档（恢复为草稿）；成功返回 `{success: true, data: <档案>}`，非法状态抛 `ValueError` → 400 |
| `GET /api/v1/writing-styles/{id}/export` | 导出为 Markdown Skill 草稿（互操作格式：frontmatter + 维度 + 新造示例 + 约束） |
| `POST /api/v1/writing-styles/import` | 由 Markdown Skill 导入；**恒产 `draft`**，同样跑材料检查（导入不是免检通道） |
| `POST /api/v1/writing-styles/review-deviation` | 生成后偏差审阅；取项目**已绑定且 active** 档案，未绑定则跳过而不报错 |

- 前端调用统一在 `frontend/src/api/index.ts` 导出（如 `restoreWritingStyleProfile(id)`），路径与后端逐字一致。
- Agent 侧同名能力在 `backend/app/services/agent/tools/writing_style_tools.py`（共 **13** 个工具：5 只读 / 8 写入），与 HTTP **共用同一服务层** `WritingStyleService`，确认边界必须一致。

## 7. Agent 运行与确认接口

<!-- 来源：openspec/changes/agent-workbench-ui-redesign，导入日期：2026-09-12 -->

| 接口 | 关键约定 |
|---|---|
| `POST /agent/runs/{run_id}/steps/{step_id}/confirm` | 确认并执行 pending 工具步骤；前端 `confirmAgentRunStep(runId, stepId)` |
| `POST /agent/runs/{run_id}/steps/{step_id}/memory-candidates/save` 与 `/discard` | 记忆候选的保存与丢弃——**这一对是完整的确认/拒绝** |
| `POST /agent/runs/{run_id}/cancel` | 取消整个运行；当前被「拒绝工具确认」复用（后端无 step 级 reject） |
| `GET /agent/threads` | 返回 `id / thread_id / session_id / title / status / active_profile_id / created_at / updated_at`。**`status` 与 `active_profile_id` 此前前端未声明而被丢弃** |
| `updateAgentProfile(profileId, patch)` | 前端可直接改 `model` / `default_workflow` 并持久化；顶部控制栏依赖它 |

注意：`/agent/threads` 的 `status` 取值域实际仅 `active` / `archived`（`archived` 已被列表过滤），见枚举字典。


## 8. 世界构建接口

<!-- 来源：openspec/changes/ai-progressive-world-building，导入日期：2026-09-12 -->

| 接口 | 关键约定 |
|---|---|
| `GET/PUT/DELETE /api/v1/projects/{project_id}/world-domains[/{domain_key}]` | 列出域契约 / 覆盖内置域或新增自定义域 / 重置内置默认或移除自定义域 |
| `POST /api/v1/projects/{project_id}/world-generation/expand-entity/preview` | **不调用模型**，只返回提示词（降低试错成本） |
| `POST /api/v1/projects/{project_id}/world-generation/expand-entity` | 按域 schema 补实体字段，产出 `ai_draft` 候选 |
| `POST /api/v1/projects/{project_id}/world-generation/expand-domain` | 按模板层次策略细化整个域 |
| Agent 工具 | `expand_world_entity_attributes`、`expand_world_domain`（异步，复用任务工具轮询）、`resolve_world_domain_suggestion` |

**失败约定**：一律抛 `ValueError` → API 转 400，且**运行落 `failed` + `diagnostics_json.error`，不产生脏候选**；前端弹窗内 `message.error` 展示。


## 9. 写作前置检查接口

<!-- 来源：openspec/changes/creative-project-writing-guardrails，导入日期：2026-09-12 -->

| 接口 | 关键约定 |
|---|---|
| `GET /api/v1/creative-projects/{project_id}/writing-preflight?chapter=&stage=&source=` | 只读，无副作用；返回 `{success, data}`，data 含 `stage`/`chapter_number`/`checks`/`ready`/`blockers`/`next_action`/source id/`methods`。前端封装 `getCreativeProjectWritingPreflight`（`src/api/index.ts:1984`） |

**同一契约两用**：真人 UI 在按钮启用前调用以禁用或标注被阻塞动作；Agent 用同一份契约解释并修复被阻塞的工作流。不要让前端另写一套"能不能点"的判断，否则两侧对阻塞原因的解释会不一致。


## 7. 创作项目叙事运行时接口

<!-- 来源：openspec/changes/creative-project-narrative-runtime，导入日期：2026-09-12 -->

| 接口 | 用途 |
|---|---|
| `GET /creative-projects/{id}/narrative/health` | 检查小说叙事数据健康状态 |
| `POST /creative-projects/{id}/contents/{content_id}/aftermath` | 由**一个正式 `novel_body` 版本**创建派生状态，按源内容/版本指纹幂等 |
| `GET /creative-projects/{id}/narrative/snapshots` | 列出快照 |
| `GET /creative-projects/{id}/narrative/context-preview` | 预览下一章叙事上下文包 |
| `GET /creative-projects/{id}/foreshadowing`（+ `/{id}/accept\|ignore\|resolve`） | 伏笔台账与处置 |
| `GET /creative-projects/{id}/narrative-graph` | 叙事图谱（**只读** `ProjectStoryEvent`、已确认事实、已确认台账行） |
| `GET\|POST /creative-projects/{id}/narrative/runs`（+ `/{run_id}/{action}`） | 叙事运行创建、列表与 pause/resume/cancel |

- **新增路由必须同步**：API surface 重新生成、前端客户端类型、架构文档与聚焦测试。
