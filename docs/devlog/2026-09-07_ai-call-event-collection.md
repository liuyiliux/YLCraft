# 2026-09-07 AI 调用事件日志统一收口交接

## 一、起因

用户反馈：世界地图 AI 生图在任务中心和事件日志里都没有记录。排查结论见
`research_report_task_event_logging_coverage.md`——根因不是"绕过公共模块"，而是
**事件日志只在端点手写，任何没手写的路径就完全不可观测**。

## 二、本轮做了什么

### 1. 事件记录下沉到 AIService 三个入口（核心）

`backend/app/services/ai/service.py`：

- 新增 `ai_call_context(...)` 上下文管理器（contextvars）：调用方注入 `project_id`、
  `ref_id`、`task_id`，可覆盖 `scene` / `task_type` / 标题，也可 `suppress_auto_event=True`
  抑制（端点自己写了业务事件时避免重复）。
- 新增 `_emit_call_event(...)`：统一写 `platform_event_logs`，带 scene、provider、model、
  耗时、成功/失败与错误、请求与响应摘要（各截断 2000 字符）。**best-effort：写失败只记
  debug 日志，绝不打断 AI 调用。**
- `chat` / `generate_image` / `generate_video` 三个入口全部接入：
  - `chat` 补了 try/except（原本异常直接抛出、连失败日志都没有），异常时先记失败事件再原样抛出
  - 无可用 backend 也记一条失败事件（此前直接返回失败结果，无任何痕迹）

一处改动覆盖所有服务侧 AI 调用：世界地图生图、区域形状推断、批量生图、agent 工具、
Live2D 等未手写记录的路径**立即进入事件日志**。

### 2. 地图链路补业务身份

`novel_sources.py` 三个端点用 `ai_call_context` 注入 `project_id` + `ref_id=map_id`，
并归入 `scene="world_map"`：

- `generate-visual`（`task_type="map_visual"`）
- `generate-visual/prompt-optimize`（`map_visual_prompt_optimize`）
- `regions/{id}/shape/generate`（`region_shape`，顺带取 document 拿 project_id）

`prompt-preview` 是本地拼提示词、不调模型，不记录。

### 3. 收敛两个真绕过点

这两个路径直连 provider、连 `AIService` 都不经过，自动收口覆盖不到：

- `services/embedding/service.py`：`embed_text_via_api` 的异常分支补失败事件。
  **成功不记**——逐条调用量太大，成功态由本地日志承载，只让失败可见。
- `services/breaker/service.py`：`transcribe_audio` 补成功/失败事件。
  此前 `except: pass` 把异常完全吞掉，转写失败无声无息。

### 4. 前端事件日志场景补全

`EventLogTab.tsx` 的 `SCENE_OPTIONS` 硬编码 5 个场景，而后端实际在用 11 个
（`world_extraction`、`world_generation`、`character_portrait`、`asset_provenance`
等全都筛不到）。补全选项 + 中文标签 + 配色，并给未知场景留兜底显示原值。

### 5. 架构文档

`YLCRAFT_SYSTEM_ARCHITECTURE.md` 新增「AI 调用与事件日志收口（可观测性）」小节，
写明必经入口、context 注入方式、绕过路径必须自补记录、任务与事件是两套系统。

## 三、测试

- 新增 `tests/test_ai_service_event_logging.py`（6 项）：成功事件带上下文、
  失败事件带 error、异常照抛但记事件、无 backend 记失败、图片/视频各自 scene、
  context 可覆盖 scene 与抑制。用 monkeypatch 截获 `record_event`，不依赖数据库。
- 后端 93 项通过（含 `test_novel_source_world` 78、`test_task_observability` 9）；
  前端 39 项通过。

## 四、必知坑

1. **过渡期会有双写**：`images` / `videos` / `model3d` 等端点本就手写 `record_event`，
   自动收口后会多出一条技术事件（task_type 相同）。计划随后删除端点层的重复记录，
   让 `record_event` 退化为"业务语义补充"。
2. **新场景要同步前端**：后端新增 scene 值必须同步 `EventLogTab.tsx` 的 `SCENE_OPTIONS`，
   否则用户筛选不到（已在该文件加注释警示）。
3. **AIService 拿不到 project_id**：只能靠调用方注入 context，没注入的事件 `project_id` 为空，
   不会出现在项目视图里。
4. **任务中心与事件日志仍是两套**：自动收口只解决事件日志；任务记录仍需端点显式
   `create_task`，且 task_type 要在 `PERSISTED_TASK_TYPES` 白名单内。

## 五、补记：任务中心兜底（同日第二轮）

事件日志收口只解决了"审计"那一半，任务中心那一半仍缺。本轮补上：

- 新增 `services/ai/tracking.py` 的 `ai_task(...)` async 上下文：一次完成
  「建任务 → 记开始 → 完成或失败 → 进度与诊断」，记账失败 best-effort 不打断业务。
  **不放到 AIService 自动收口**：任务需要业务粒度，chat 之类高频调用自动建任务会冲垮任务中心。
- `world_map_visual` 登记进 `PERSISTED_TASK_TYPES`，地图成图端点接入 `ai_task`，
  任务同时带上 `task_id`（事件日志与任务中心可互跳）。
- `should_persist` 不再静默返回 False：不落库时打日志说明原因（类型未登记 / 缺 project_id），
  此前表现为"任务凭空消失"且无从排查。
- 前端任务中心补全类型选项与中文标签（`world_map_visual`、`world_domain_expansion`）、
  配色与跳转路由（成图 → `/world-map`，域细化 → `/novel-world`）。
- 新增 `tests/test_ai_task_tracking.py`（4 项）：成功置 done 且带 result、
  失败置 failed 且异常原样抛出、带 project_id 才落库、白名单规则。

## 六、后续候选

- 清理端点层重复 `record_event`（约 43 处）
- 视频/3D 的自有 Task 表接入任务中心聚合（`tasks.py:_all_task_infos`）
- Live2D 与 agent 工具补任务记录（事件已由收口覆盖）
- 嵌入调用的成功态做汇总指标（现在是逐条静默）
