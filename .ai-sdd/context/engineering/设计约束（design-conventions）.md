# 设计约束（AI 调用 / 任务 / 观测）

来源：`platform-event-logging`、`task-observability-diagnostics` 实现与踩坑。最后更新：2026-09-11。

## 1. AI 调用必须走 `AIService` 三个入口

`chat` / `generate_image` / `generate_video`（`backend/app/services/ai/service.py`）是唯一收口点：
自动落平台事件（scene/provider/model/耗时/成功失败/错误），且 `BackendRouter` 内部多次降级只算一次调用。

- 业务身份用 `ai_call_context(...)` 注入：`project_id`、`ref_id`、`scene`、`task_type`、`label`、`task_id`、`retry_payload`。
- 端点自己已写业务事件时用 `suppress_auto_event=True` 抑制自动记账，避免同一次操作落两条。
- 写日志是 best-effort：失败不打断 AI 调用本身。
- **不要回到端点手写"调用成功/失败"事件的旧模式**；那会与收口双写。
- 直连 provider 的旁路（`services/embedding` 的 httpx 直连、breaker 的 STT、model3d 的 httpx）必须自行补记事件，否则该路径不可观测。

## 2. 任务记录不能自动收口

任务需要**业务粒度**（一次"地图成图"一条），高频 `chat` 若自动建任务会冲垮任务中心。
做法：长耗时操作显式用 `ai_task(...)`（`services/ai/tracking.py`）包住
「建任务 → 记开始 → 完成或失败 → 进度与诊断」，记账失败不影响业务。

## 3. 重试/重发必须复用业务端点

- 任务重试：从账本 `request_json` 重建请求对象后，**直接 `await` 生成端点函数**（如 `await generate_video(req, external_key=None)`），
  从而复用资产入库、项目关联、事件与新任务记录的全部行为；不要另写 provider 直连逻辑。
- 事件重发：沿用 `api/v1/logs.py` 的 `retry_log` 分支结构（image/video/llm）。
- **函数直调注意**：FastAPI 端点的 `external_key: Optional[ExternalApiKey] = Depends(...)` 在直接调用时不会被解析，
  必须显式传 `external_key=None`，否则会把 `Depends(...)` 默认对象带进业务逻辑。

## 4. 前端与后端枚举必须同步

- 任务类型：后端白名单 ↔ 前端 `TASK_TYPE_OPTIONS` + `TYPE_COLOR_MAP`（缺项＝用户筛不到任务）。
- 事件场景：后端 `scene` ↔ 前端 `EventLogTab` 的 `SCENE_OPTIONS` + `SCENE_LABEL_MAP`。

## 5. 列表接口与详情接口的字段长度差异

列表/搜索接口常用 `preview=True` 截断长文本（如提示词截到 360 字），**展示全文或插入正文前必须取详情**，
否则会把残缺内容写进业务（曾导致生图提示词残缺）。

## 6. 文档同步协议

- 新增/改语义 API → 跑 `backend/venv_win/Scripts/python.exe tools/generate_api_surface.py` 重新生成
  `docs/architecture/API_SURFACE.md` 与 `api_surface.json`（勿手改）。
- 模块边界变化 → 更新 `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` 第 5 节；
  数据模型变化 → 第 4 节；阶段性交接 → `docs/devlog/YYYY-MM-DD_topic.md`。
