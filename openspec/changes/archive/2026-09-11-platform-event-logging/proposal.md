# Proposal: 任务中心统一观测（任务 / 事件日志 / 运行日志）

## What

把分散的执行记录收敛到**任务中心**一个页面，通过三个 Tab 提供完整观测能力：

1. **任务**（现有）- 可续跑/可取消/有进度的异步任务（爆款拆解、下载、图像/视频/3D 生成、剪辑），含事件时间线详情。
2. **事件日志**（新增）- 结构化的跨场景成败事件：AI 生成（图片/视频/3D/文本）与关键系统事件，含 provider/model、状态、错误、耗时、请求/响应摘要，持久化到统一表 `platform_event_logs`，只读可查。
3. **运行日志**（新增）- 后端应用运行日志（目前只打 stdout、无落盘文件）。为后端增加滚动文件日志，并提供查看入口：读最近 N 行、按级别/关键词过滤、按时间翻页。

4. **失败重发**（新增）- 事件日志详情对失败的 AI 生成（图片/视频/3D/文本）提供「重发」能力：基于脱敏后的完整可重放参数 `retry_payload_json` 按场景重新提交，形成失败→重发→结果 的追溯链。

同时修复**图片生成失败不落账**的缺陷：当前 `POST /api/v1/images/generate` 只在成功时持久化，失败与异常分支直接把错误返回前端、完全无痕，导致上游超时（如 `aaccx.pw` 透传的 `Socket timeout, timeout: 60000ms`）或 503 这类失败在 UI 里看不到，无法追溯。

## Why

- 失败无痕：图片生成失败只返回当次请求，UI「历史」是纯内存态、刷新即丢，也无 `/images/history`；视频/3D 有独立账本表，图片没有，跨场景也无统一视图。
- 上游中转（如 `api.aaccx.pw`）常返回 503 `No available compatible accounts` 或内部 60s socket 超时，这些错误目前完全不可见。
- 后端日志只打 stdout：进程一重启历史就没了，用户想看「像 .log 文件那样」的全部输出根本没有载体。
- 任务与日志本质都是「跨场景执行记录 + 详情」，放一起（同一页）比新增独立导航项更符合用户心智。已落地的 `task-observability-diagnostics` design.md 也预留了「后续新增 task_events 表」的方向。

## What changes

| 层 | 新增 | 修改 |
|---|---|---|
| DB | Alembic 迁移 `017_add_platform_event_logs`，新建 `platform_event_logs` 表 | - |
| Backend | `db/models/` 新增 `PlatformEventLog` 模型 | - |
| Backend | `services/platform_log/service.py`：事件写入 + 查询 + 脱敏/截断 | 复用 `task_queue._sanitize_event_value` |
| Backend | 运行日志：`main.py` 增加 RotatingFileHandler 落盘；`api/v1/logs.py` 增加运行日志读取 | `main.py` 日志配置 |
| Backend | `api/v1/logs.py`：`GET /api/v1/logs`（事件筛选/分页）、`GET /api/v1/logs/{id}`、`GET /api/v1/logs/runtime`（运行日志行）、`POST /api/v1/logs/{id}/retry`（失败重发） | `main.py` 注册路由 |
| Backend | 图片/视频/3D/文本生成统一写平台事件，失败记录存 `retry_payload_json` | `images.py` 失败/异常分支补落账 |
| Frontend | 任务中心页加「事件日志」「运行日志」两个 Tab，事件详情加「重发」按钮 | `pages/tasks/index.tsx` 由单列表改为 Tabs 容器 |

## Non-goals

- 不把 stdout 全量行塞数据库：`platform_event_logs` 只存结构化事件；运行日志走文件 + 按需读取，不整文件入库或整文件塞表格。
- 不替代后端 logger 的 stdout 输出（仍保留，文件日志是新增的并行 sink）。
- 不做 ELK / OpenTelemetry 等系统级观测平台，不做日志远程上报。
- 不采集完整请求体、API Key、Authorization、完整图片 base64 或二进制内容。
- 不回填历史事件；不重构现有任务中心后端聚合逻辑（`/api/v1/tasks` 保持不变）。
- 图片生成 UI 独立「我的历史」账本（仿 `/videos/history`）不在本变更内；本变更只保证失败事件进统一事件日志可查。

## User flow

1. 用户在任务中心页切换三个 Tab：任务 / 事件日志 / 运行日志。
2. 一次图片/视频/3D/文本生成在成功与失败路径都写入一条 `platform_event_logs`，失败必带 error 与响应摘要。
3. 用户在「事件日志」Tab 按场景、级别、状态、时间、关键词筛选，点开查看 provider/model、错误、请求/响应摘要、耗时。
4. 用户在「运行日志」Tab 查看后端运行输出（最近 N 行），按级别/关键词过滤，定位 stdout 级别的细节（如某次 HTTP 请求、重试）。
5. 对上游超时/503，用户既能在「事件日志」看到结构化失败原因，也能在「运行日志」看到对应原始输出。
6. 用户在事件日志详情点击「重发」，系统按场景重放原请求，成功后生成新记录并通过追溯链关联原失败记录。
