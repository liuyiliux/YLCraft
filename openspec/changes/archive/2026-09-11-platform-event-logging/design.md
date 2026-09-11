# Design: 任务中心统一观测（任务 / 事件日志 / 运行日志）

## Architecture

```text
业务服务 / API 层
  -> services/platform_log/service.record_event(...)   # 结构化事件收口
    -> 脱敏/截断 (复用 task_queue._sanitize_event_value)
    -> PlatformEventLog -> platform_event_logs 表
      -> GET /api/v1/logs (筛选/分页) / GET /api/v1/logs/{id}

后端 logging
  -> main.py RotatingFileHandler -> backend/storage/logs/app.log (滚动)
    -> GET /api/v1/logs/runtime (读最近 N 行 + 级别/关键词过滤)

任务中心前端 (pages/tasks/index.tsx 改为 Tabs)
  ├─ Tab 任务       -> 现有 /api/v1/tasks 聚合 (不变)
  ├─ Tab 事件日志   -> /api/v1/logs
  └─ Tab 运行日志   -> /api/v1/logs/runtime
```

三类记录职责分离：

- **任务**：可操作（取消/删除/重试）、有进度、可续跑的异步工作。后端 `/api/v1/tasks` 聚合逻辑保持不变。
- **事件日志**：只读、结构化的成败事件流水，入库。
- **运行日志**：只读、stdout 级别的原始应用输出，走文件不落库，按需读取。

## PlatformEventLog 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | str (pk) | `log_{uuid4().hex}` |
| `scene` | str (index) | 场景：`image` / `video` / `model3d` / `llm` / `system` / `agent` 等 |
| `task_type` | str (index) | 细分类，如 `image_generation`、`text_to_video` |
| `task_id` | str? (index) | 关联任务 ID（video/model3d/agent 账本 task_id，可空） |
| `level` | str (index) | `info` / `warning` / `error` |
| `status` | str (index) | `success` / `failed` / `pending` |
| `provider` | str | 供应商名 |
| `model` | str | 模型名 |
| `message` | str | 人读摘要 |
| `error` | str? | 错误详情（上游超时、503 原文摘要） |
| `request_summary` | str | 请求摘要（脱敏截断） |
| `response_summary` | str | 响应摘要（脱敏截断） |
| `duration_ms` | int | 耗时毫秒 |
| `project_id` | str? (index) | 关联创作项目（可空） |
| `retry_payload_json` | str | 脱敏后的完整可重放参数（默认 `"{}"`） |
| `retry_of` | str? | 指向被重发的失败事件 id（本次为重发结果时） |
| `retried_by` | str? | 指向重发后的结果事件 id（本次为被重发的失败事件时） |
| `created_at` | float (index) | 记录时间戳 |

约束：

- `request_summary` / `response_summary` 默认截断到 1000 字符，仅用于展示。
- `retry_payload_json` 是**脱敏后的完整可重放参数**（保留完整 prompt/messages/项目字段等，移除 Authorization/api_key/token/base64 图片/二进制），用于「重发」精确还原请求；不截断、不压缩业务字段。
- 不落 `Authorization` / `api_key` / `token` 原始值，不落完整 base64 图片或二进制。
- `scene` 用稳定枚举字符串，新增场景需同步文档。

## 事件日志写入点

统一收口 `services/platform_log/service.py` 的 `async def record_event(...)`，内部做脱敏/截断与入库。

1. **图片生成** `api/v1/images.py:generate_image`
   - 同步成功 → `info/success`；异步 pending（已建任务）→ `pending`，task_id 关联队列任务。
   - **`else` 失败分支（现 L673）**：补 `record_event(error=result.error)` —— 修复无痕核心。
   - **`except` 异常分支（现 L680）**：补 `record_event(error=str(e))`。
   - 素材定稿失败（现 L646 status=error）补一条。
2. **视频** `videos.py:generate_video` —— 已写账本，追加一条事件（复用 result.success/error）。
3. **3D** `model3d_workspace.py` —— 同上。
4. **文本/LLM** `llm.py` —— 复用现有 `_write_project_generation_log` 触发点，追加 `scene=llm`。
5. **系统级**（可选）：启动、迁移完成写 `scene=system`。

## 运行日志（文件）

- `main.py` 在现有 `logging.basicConfig` 基础上**追加** `RotatingFileHandler`，写到 `backend/storage/logs/app.log`（按大小滚动，保留若干备份），stdout 输出保持不变。
- 读取接口只**倒序读最近 N 行**（tail 方式），支持 `level` / `q`（关键词）/ `before`（翻页游标）过滤；不整文件返回，不解析进数据库。
- 路径、滚动大小、保留份数做成常量，便于调整。

## 查询 API

```text
GET /api/v1/logs
  query: scene, level, status, task_type, project_id, q, since, until, page, page_size
  -> 分页摘要列表（默认 created_at 倒序）

GET /api/v1/logs/{id}
  -> 单条完整详情（message/error/request/response_summary/duration_ms/task_id）

GET /api/v1/logs/runtime
  query: level, q, limit, before
  -> 运行日志行（时间/级别/logger/消息），倒序

POST /api/v1/logs/{id}/retry
  -> 按 scene 重放失败请求，返回新生成结果（新事件 id / 新 task_id）
```

## 失败重发（通用重放）

### 目标

对 `status=failed` 的 AI 生成事件，允许用户一键重发原请求。跨 image/video/model3d/llm 四类场景统一走 `POST /api/v1/logs/{id}/retry`。

### retry_payload_json（各场景内容）

| scene | retry_payload 字段 | 重发时调用的入口 |
| --- | --- | --- |
| `image` | prompt / negative_prompt / size / provider / model / seed / steps / cfg_scale / sampler / lora / controlnet / 项目字段（project_id/content_id/source_type/source_index/source_title/chapter_number 等） | 复用 `POST /images/generate` 的参数与逻辑 |
| `video` | prompt / duration / resolution / aspect_ratio / provider / model / seed / start_image / reference_asset_ids / generate_audio / music_hint / 项目字段 | 复用 `POST /videos/generate` 的参数与逻辑 |
| `model3d` | prompt / provider / model / source_asset_id / source_image / options | 复用 `POST /model-3d/generate` 的参数与逻辑 |
| `llm` | messages / model / temperature / max_tokens / provider | 复用 `POST /llm/chat` 的参数与逻辑 |

写入时**必须保留项目/血缘字段**（project_id/content_id/source_type 等），否则重发后产物无法回写 Asset Hub 与项目关联，血缘断裂。

### 重发流程

1. `POST /logs/{id}/retry` 读取事件，校验 `status == failed` 且 `retry_payload_json` 非空（否则 409/400）。
2. 按 `scene` 分发到对应生成函数（复用现有 service 调用，而非重新写一套提交逻辑）。
3. 重发成功 → 写一条新事件（`status=success` 或 `pending`，`retry_of=原事件 id`），并把原事件的 `retried_by` 更新为新事件 id。
4. 重发失败 → 写一条新 `failed` 事件（`retry_of=原事件 id`），保留新错误。
5. 原失败事件不覆盖、不删除；通过 `retry_of` / `retried_by` 形成「失败 → 重发 → 结果」链，前端可据此串联展示。

### 边界

- 仅 `failed` 状态开放重发；`pending` / `success` 不开放。
- 非法请求（模型不存在、prompt 被拒）重发仍会失败：前端在详情展示 error 原因让用户判断，按钮始终可用但给出提示。
- 重发不自动携带 API Key（provider 配置从连接器实时读取，不落库）。
- 异步场景重发后是新的 task_id，与旧任务独立。

## 前端：任务中心改 Tabs

`pages/tasks/index.tsx` 由单列表改为 Tabs 容器：

- **Tab 任务**：保留现有全部逻辑（Table + Drawer + Timeline + 取消/删除），不改动数据源。
- **Tab 事件日志**：Table（时间/场景/级别 Tag/状态/provider/model/message/耗时）+ 筛选（scene/level/status/时间/关键词）+ 详情抽屉（完整 message/error、request/response_summary 可折叠可复制、duration_ms、关联 task_id）。复用现有 Table/Drawer 模式。
- **Tab 运行日志**：列表（时间/级别/logger/消息）+ level/关键词过滤 + 加载更多（before 游标）。

导航仍只有「任务中心」一项，不新增 `/logs` 独立路由。

## 修复图片失败无痕（与事件日志同步落地）

- 补 `images.py` 三个失败分支的 `record_event`，失败信息随事件入库。
- 异步生图轮询失败已由 `image_generation` 任务 `append_event("failed")` 覆盖（images.py L934-955），本变更只补**提交即失败**与**同步失败**空白。
- 平台事件与 `project_task_records` 账本不冲突：账本面向「可续跑任务」，事件日志面向「跨场景统一可查的成败事件」。

## Rollout plan

1. DB 迁移 + 模型 + 平台日志服务（脱敏）。
2. 运行日志：RotatingFileHandler + 读取接口。
3. 日志查询 API（事件 + runtime）+ 注册路由。
4. 图片生成失败分支落账（修复无痕）。
5. 视频/3D/LLM 追加平台事件。
6. 任务中心前端改三 Tab。
7. 验证（单测 + build + 手动造上游失败确认事件/运行日志均可见）。
