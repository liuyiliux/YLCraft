# Proposal: 任务详情诊断字段归一化

## Why

独立视频与图生 3D 任务使用各自的持久化账本，供应商原始诊断保存在
`result.diagnostics`（提交阶段为 `operation` / `method` / `endpoint` /
`http_status` / `response_excerpt`），而任务中心详情读取的是图片任务风格的稳定字段
（`external_task_id` / `provider` / `model` / `last_remote_status` /
`last_response_excerpt`）。

这两种契约在真实视频任务 `video_95471d0af2c04b1495a47916b7aeef60` 上直接冲突：
接口能查到完整任务，但详情诊断卡中的外部任务 ID、服务商、模型、远端状态和响应摘要
全部显示为空。问题不在数据库查询，而在读取契约没有把供应商原始诊断转换为任务中心
稳定字段。

## What Changes

- 在任务 API 的持久化媒体任务详情路径中，把视频与图生 3D 的供应商诊断归一到任务中心
  稳定字段。
- 保留供应商原始诊断，不覆盖既有标准字段；归一化只补缺，不改变存储结构或历史记录。
- 任务中心详情展示归一化后的关键字段，并补充已在后端返回的 `operation`、
  `endpoint`、`http_status` 诊断项。
- 用后端单元测试固定“保留原始诊断 + 生成稳定字段 + 已有字段优先”三条契约。
- 用真实浏览器重新打开一条视频任务详情，确认页面可见供应商、模型和响应摘要。
- 停止终态任务的重复供应商查询：失败轮询写入 `completed_at` 并标记 `terminal=true`，
  本地已是终态时直接返回已存结果；旧失败记录缺少结束时间时耗时显示为未知。
- 终态时间优先使用供应商报告的 `completed_at` / `output.end_time`，只在供应商未提供时
  回退本地观测时间；视频历史与轮询响应统一返回 `completed_at`。
- 视频工作台的 `failed` / `cancelled` 不再回落到“排队中”；修正真实任务
  `video_b0d9b219cfcf4b12aa1badd63164c373` 的本地结束时间为供应商时间，耗时从
  2096.29s 纠正为约 74.5s。
- 任务中心「任务管理」增加状态过滤：等待中、运行中、已完成、失败、已取消；过滤在已加载的
  任务列表本地执行，并把 `completed` / `succeeded` / `processing` 等历史状态别名归一到
  可理解的状态分组。

## Non-goals

- 不修改 `video_generation_tasks` / `model3d_generation_tasks` 的表结构。
- 不批量回填历史任务；只修正已确认拥有供应商完成时间的目标记录。
- 不把供应商请求体、完整响应、密钥或 token 暴露到任务详情。
- 不改变任务列表接口的轻量返回策略。
- 不为状态过滤新增服务端查询参数；当前列表由任务中心一次加载，沿用既有前端类型过滤边界。

## Impact

- Backend：`backend/app/api/v1/tasks.py`、`backend/app/api/v1/videos.py`、
  `backend/app/services/ai/types.py`、`backend/app/services/ai/backends/video/generic.py`
- Backend tests：`backend/tests/test_task_observability.py`、
  `backend/tests/test_video_project_context.py`、`backend/tests/test_generic_video_connector.py`
- Frontend：`frontend/src/pages/tasks/index.tsx`、`frontend/src/pages/video-gen/index.tsx`
- Docs/OpenSpec：本 change 与 `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`
