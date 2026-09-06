# YLCraft 任务与事件记录缺失：全面梳理报告

> 触发问题：世界地图的 AI 生图（`POST /api/v1/world-maps/{map_id}/generate-visual`）在「任务中心」和「事件日志」里都没有记录。
> 排查范围：后端全部 API 路由、服务层、agent 工具、后台任务；前端任务中心三个 Tab；两个相关 OpenSpec change 与既有测试。

---

## 一、结论先行

**1）没有"公共生成模块"承载 AI 操作，记录全靠端点手写。**
`AIService`（`backend/app/services/ai/service.py:69`）只是 provider 编排与路由层（`chat()` `:137`、`generate_image()` `:179`、`generate_video()` `:193`），它**既不建任务也不写事件日志**。设计文档把它定位为"横切关注点（初始化、健康检查、对外接口统一）"层（`docs/architecture/YLCraft-AI服务层架构设计.md:94-97`），模块 docstring 也自述负责"日志、用量统计等横切关注点"（`service.py:4`）——**但这两项职责声明了、从未实现**（方法体内只有 `logger.info`，`chat()` 甚至没有 try/except，`service.py:170-173`）。

**2）"任务"和"事件日志"是两套系统，各自的落点与消费方都不同。**

| | 任务中心 | 事件日志 |
|---|---|---|
| 数据 | `InMemoryTaskQueue`（进程内存）+ `project_task_records` 表 + 各媒体自有表（如 `VideoGenerationTask`） | `platform_event_logs` 表 |
| 写入 | `queue.create_task()`（`core/task_queue.py:90`）→ `_persist()`（`:269`）→ `task_persistence.upsert_task()` | 端点手写 `platform_log.record_event()`（`services/platform_log/service.py:44`） |
| 前端 | `frontend/src/pages/tasks/index.tsx:201` 调 `listTasks()` → `GET /api/v1/tasks` | `EventLogTab.tsx`，字段含场景/状态/provider/模型/耗时/任务 ID（`EventLogTab.tsx:402-409`） |

**3）为什么有的任务有记录、有的没有——因为"是否被记录"取决于开发者在该端点手写了没有。**
`record_event` 在 `backend/app/` 下**只被 10 个文件调用**（其中 1 个是它自己），**服务层零调用**。要让一次 AI 操作可观测，必须手写三件事，且三步都没有编译期或框架级约束：

1. `queue.create_task(task_type=..., payload={"project_id": ...})`——且 task_type 必须命中白名单 `PERSISTED_TASK_TYPES = {"image_generation", "creative_writing", "world_domain_expansion"}`（`services/task_persistence.py:34`）且 `project_id` 非空（`should_persist()` `:37`），否则进程重启即丢；
2. `queue.append_event` / `update_progress` / `update_diagnostics` 写时间线；
3. `platform_log.record_event(...)` **成功与失败各一次**。

**4）世界地图生图并没有"绕过公共模块"——它走的是正规 AI 链路，缺的是记录本身。**
`novel_sources.py:1929` → `world_map_visual.py:140` `manager.generate_image(...)`，而 `world_map_visual.py:128` 的 `manager` 就是 `get_ai_service()`，即完整经过 `AIService → BackendRouter → Backend`。同一个 `novel_sources.py` 文件里，`expand_domain` 规规矩矩写了 7 处 `record_event`（`:1335/1354/1430/1463/1555/1574/1593`）并建了任务（`:1508`），而生图端点一处都没有——**同一文件两种写法，正是"靠自觉"的最好证据**。

---

## 二、覆盖矩阵：谁记了、谁没记

`record_event` 实际调用分布（全仓统计）：

| 文件 | 次数 | 说明 |
|---|---|---|
| `api/v1/novel_sources.py` | 12 | 集中在世界提取/生成，地图生图 0 |
| `api/v1/characters.py` | 6 | 角色立绘等 |
| `api/v1/model3d_workspace.py` | 6 | 3D 生成 |
| `api/v1/images.py` | 5 | 仅 `/generate`；批量与大纲生成 0 |
| `api/v1/logs.py` | 5 | 重放/查询侧 |
| `api/v1/videos.py` | 3 | 视频生成（任务走自有表） |
| `api/v1/creative_projects.py` | 3 | 写作类 scene="writing" |
| `api/v1/assets.py` | 3 | 资产侧 |
| `api/v1/llm.py` | 1 | 通用 LLM 聊天 |
| `services/platform_log/service.py` | 2 | 自身 |

### 世界地图相关（本次问题核心）

| 端点 | 位置 | 是否调模型 | 事件日志 | 任务记录 |
|---|---|---|---|---|
| `POST /world-maps/{id}/generate-visual` | `novel_sources.py:1929` | 生图 | **无** | **无** |
| `POST /world-maps/{id}/generate-visual/prompt-optimize` | `:1891` | LLM | **无** | **无** |
| `POST /world-maps/{id}/generate-visual/prompt-preview` | `:1872` | 否（本地拼提示词） | 无需 | 无需 |
| `POST /world-maps/{id}/regions/{rid}/shape/generate` | `:1787` | LLM | **无** | **无** |
| `POST /novel-sources/{id}/chunks/index` | `:610` | Embedding | **无** | **无** |
| `POST /novel-sources/{id}/extract` | `:715` | LLM | **无** | **无** |
| `POST /world-extraction-runs/{id}/contradictions` | `:808` | LLM | **无** | **无** |
| `POST /projects/{pid}/world-generation/expand-domain` | `:1484` | LLM | 有（`world_generation` / `expand_domain`） | 有（`world_domain_expansion`，`:1508`） |

### 其它业务域

| 端点/模块 | 事件日志 | 任务记录 | 备注 |
|---|---|---|---|
| `POST /api/v1/images/generate`（`images.py:510`） | 有（5 处，含 pending/成功/失败/异常） | 仅当返回 `task_id` 且 `status=="pending"` 时建（`:567`）；同步出图的供应商不建任务 | 覆盖最完整的一处 |
| `/images/generate-outline`、`/generate-batch`（+`/retry`、`/topics`） | **无** | **无** | 直连 `manager.generate_image`（`:1463`）与 `batch_generate_images` |
| `POST /api/v1/videos/generate`（`videos.py:477`） | 有（3 处） | 写**自有表** `VideoGenerationTask`（`:576-594`），不走 core 队列 | 因此视频任务不会出现在任务中心 |
| `model-3d` 生成（`model3d_workspace.py:264`） | 有（6 处） | 自有表 `Model3DGenerationTask` | 同上 |
| `live2d.py` | **无**（全仓无 `record_event`） | 仅有 WS 进度推送 `push_task_progress`，task_id 是拼接字符串（`:63`），不进内存队列 | 任务中心与事件日志都看不到 |
| **全部 agent 工具**（`services/agent/tools/`） | **无**（`record_event` 全目录 0 命中） | 部分有 `create_task`/任务队列引用 | agent 触发的 AI 调用整体不可审计 |
| `creative_projects.py` 写作类 | 有（scene="writing"） | — | |

---

## 三、是否存在绕过公共模块的路径

**AI 调用主链路是收敛的**（`AIService → BackendRouter → Backend → httpx/openai SDK`），但存在 5 处真绕过——它们连 `AIService` 都不经过，因此未来即便在 `AIService` 层统一收口也覆盖不到：

| 绕过点 | 位置 | 说明 |
|---|---|---|
| Embedding | `services/embedding/service.py:236/259/280` | 自己读 `AIConnector` 的 base_url/api_key（`:76-88`、`:108-119`），`httpx.post` 直连 `/embeddings`（`:258`），另有 qwen/huggingface 分支（`:220-229`） |
| STT 语音转写 | `services/breaker/service.py:200-216` | 硬编码 `https://api.siliconflow.cn/v1/audio/transcriptions`，api_key 取 `os.environ`（`:202`），完全不查 AIConnector |
| 模型连通性测试 | `services/ai_connector/service.py:878/893/951` | 自建 `build_url("/chat/completions")` 等探测请求（诊断用，非业务） |
| 模型列表测试 | `api/v1/ai_connectors.py:948-950` | `import openai; openai.OpenAI(...)` 直接建客户端 |
| ComfyUI | `services/comfyui/` | 通过 `AIService.get_backend()`（`service.py:219`）直取实例，架构上明确不合并（`YLCraft-AI服务层架构设计.md:395`） |

**另有分叉点需注意**：`AIService.get_backend()` / `get_default()`（`service.py:219/233`，注释明写"供 comfyui 等直接访问"）允许调用方绕过 Router 直接拿 Backend；Router 内部对一次请求可能串行降级调用 N 个 backend（`router.py:179-202`、`:256-275`），若把记录插在 Router 层会产生 N 条重复事件。

**死代码一处**：`ai_connector/service.py:1144` 的 `log_usage()`（写 `AIUsageLog` 表，`models/ai_connector.py:454`）**全仓无调用点**；实际只有 `image/generic.py:1148` 的 `_update_usage()` 更新了 `usage_count/total_cost`，两者都**不记录耗时、不写事件日志**。

---

## 四、还有哪些场景存在"任务/事件未记录"

按用户可感知的后果排序：

1. **世界地图 AI 生图**（`generate-visual`、`prompt-optimize`）：无事件、无任务、无耗时、失败只抛 5xx（`novel_sources.py:1959-1961`）→ 用户看不到在跑、失败查不到、无法重放。
2. **区域形状 AI 推断**（`regions/{id}/shape/generate`）：同上，且它只产参数与 seed，出问题最难定位。
3. **图片批量生成链路**（`/images/generate-batch`、`/retry`、`/topics`、`/generate-outline`）：批量任务比单张更需要进度与失败明细，却完全无记录。
4. **世界提取主流程**（`/novel-sources/{id}/extract`、`/world-extraction-runs/{id}/contradictions`、`/chunks/index` 的 embedding）：提取是最长、最容易失败的链路，目前只有 `plan_domains` 与项目世界提取有日志。
5. **Agent 工具触发的 AI**：全部无事件日志。用户在 agent 会话里发起的生图/写作/世界生成，只在会话里可见，任务中心与事件日志里不存在。
6. **Live2D 全链路**：只有 WebSocket 进度，没有落库记录，刷新即失。
7. **视频与 3D 生成**：有事件日志，但任务写在自有表，不进任务中心 → 任务中心"看不到"，重试入口也不统一（`logs.py:268` 的 `model3d` 重放直接返回 400）。
8. **后台/异步任务路径**：`_run_domain_expansion_task` 等后台函数内的 AI 调用，记录依赖函数内手写，端点层只覆盖了入口那一次。

---

## 五、修复建议（分层）

### 立即（本次问题止血）
给地图生图链路补记录，照抄同文件 `expand_domain` 的写法（成功/失败各一次、带 `duration_ms` 与 `retry_payload`）：
- `POST /world-maps/{id}/generate-visual`（`novel_sources.py:1929`）
- `POST /world-maps/{id}/generate-visual/prompt-optimize`（`:1891`）
- `POST /world-maps/{id}/regions/{rid}/shape/generate`（`:1787`）
- `prompt-preview` 不调模型，无需记录。

### 短期（补齐明显缺口）
- 图片批量链路（`/generate-batch`、`/retry`、`/topics`、`/generate-outline`）
- 世界提取主流程（`/extract`、`/contradictions`、`/chunks/index`）
- Live2D：至少补一次 `record_event`（WS 推送不能替代审计）
- Agent 工具：在工具基类或注册处统一补事件日志（否则 agent 侧永远不可观测）
- 视频/3D：把自有 Task 表接入任务中心聚合（`_all_task_infos`，`tasks.py:322`），或反向写入 core 队列

### 架构（根治"靠自觉"）
**在 `AIService` 三个入口方法做统一收口**（`service.py:137 chat` / `:179 generate_image` / `:193 generate_video`）：

- 理由：这是唯一语义完备的必经点——能同时拿到 scene（llm/image/video）、provider、model、请求与响应、耗时与错误；只需 3 处改动；能天然覆盖世界地图生图等所有服务侧调用；与架构文档声明的"横切关注点"职责对齐；且天然去重（Router 内部 N 次降级只算 1 次）。
- 落地：内部加 `_tracked()` 包装，`time.perf_counter()` 计时，`finally` 调 `platform_log.record_event(...)`（已支持 `scene/provider/model/duration_ms/error/retry_payload`，自带脱敏与 1000 字截断，best-effort 不抛错）。`project_id` / `task_id` 用 `contextvars` 由端点注入；`chat()` 补 try/except；`AIService` 当前无 DB session（`__init__` 只收 registry/router，`service.py:77`），需按 platform_log 现有模式自建异步会话。
- 收敛绕过点：embedding 注册为新的 MediaType 走 `AIService`；breaker 的 STT 至少补 `record_event`（更彻底的是改为查 AIConnector）。
- 收口完成后，**可删除端点层约 43 处重复 `record_event`**，`record_event` 退化为"业务语义补充"而非必需。
- 任务记录建议：`PERSISTED_TASK_TYPES` 白名单改为"端点显式声明"或扩白名单，否则新增类型永远落不了库；`task_type` 不在白名单时至少有告警日志（当前 `should_persist` 静默返回 False）。

---

## 六、局限性

- 统计基于静态代码检索（`record_event` 调用点计数），未做运行时抓包验证；个别端点可能经由工具函数间接记录而未在计数中体现。
- 两个 OpenSpec change 中，`platform-event-logging` 31 项里 30 项已勾选，唯一未勾的是"手动验证触发一次生图失败"，其 `tasks.md:29` 亦自承曾"勾选但未真实通过"——说明清单完成度与真实可用性存在偏差，本次梳理以代码事实为准。
- 未覆盖前端埋点与浏览器侧错误上报（超出本次范围）。

---

## 参考（代码位置）

1. `backend/app/services/platform_log/service.py:44` — `record_event` 唯一事件入口
2. `backend/app/db/models/platform_log.py:11,20` — `platform_event_logs` 表
3. `backend/app/core/task_queue.py:90,269` — 内存任务队列与条件落库
4. `backend/app/services/task_persistence.py:34,37,42` — 白名单、判定、写入
5. `backend/app/services/ai/service.py:69,137,179,193` — AIService 三个必经入口
6. `backend/app/services/ai/backends/router.py:49,158,246` — 选路与降级
7. `backend/app/api/v1/novel_sources.py:1929,1872,1891,1787` — 地图生图与形状推断端点
8. `backend/app/api/v1/tasks.py:322,619` — 任务中心聚合逻辑
9. `backend/app/api/v1/logs.py:211-268` — 重放分派（仅 image/video/llm 可重放）
10. `openspec/changes/platform-event-logging/design.md:58-70` — 接入点设计清单（不含地图）
11. `openspec/changes/task-observability-diagnostics/design.md:17` — 第一阶段不引表
12. `docs/architecture/YLCraft-AI服务层架构设计.md:94-97` — AIService 为横切关注点层
