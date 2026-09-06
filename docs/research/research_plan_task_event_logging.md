# 研究计划：任务/事件记录缺失全面梳理

## 背景与问题

用户反馈：生成地图（world map AI 生图）在「任务中心」的任务列表和「事件日志」里都没有记录。据此提出四个问题：

1. 调用 AI 这类操作是否应统一走公共生成模块？
2. 为什么有的任务写入了记录、有的没有？
3. 当前是否真的经过公共生成逻辑，还是存在绕过公共模块的路径？
4. 还有哪些场景存在类似的「任务/事件未记录」？

## 已知锚点

- `backend/app/services/task_persistence.py`（任务持久化）
- `backend/app/core/task_queue.py`（任务队列，含 push_task_created 等事件推送）
- `backend/app/services/platform_log/service.py`（`record_event`，写 `platform_event_logs`）
- OpenSpec：`openspec/changes/task-observability-diagnostics/`、`openspec/changes/platform-event-logging/`
- 测试：`backend/tests/test_task_observability.py`
- 已接入事件日志的端点：images / videos / llm / model3d / live2d / creative_projects / novel_sources(部分)
- 疑似未接入：`/api/v1/world-maps/{map_id}/generate-visual`、`prompt-preview`、`prompt-optimize`

## 调研分工（并行 code-explorer 子代理）

| 子代理 | 主题 | 产出 |
|---|---|---|
| A | 公共任务/事件记录基建（task_persistence / task_queue / platform_log / tasks.py / logs.py / 两个 OpenSpec change / 测试） | 公共模块职责、设计要求、落库表、任务中心数据来源 |
| B | AI/生成类端点接入覆盖盘点 | 端点清单 × 是否事件日志 × 是否任务记录 × 走哪个模块 |
| C | world map 生图链路专项 | 三端点链路逐步定位缺失点，与角色立绘对比 |
| D | AI 调用封装与绕过点 | 统一封装清单 + 绕过直连清单 + 是否应统一 |

## 输出要求

综合四份结果，产出 `research_report_task_event_logging_coverage.md`：

- 结论先行：现状判定、根因分类
- 覆盖矩阵（端点 × 记录情况）
- 根因分析（为什么有的有、有的没有）
- 绕过公共模块的路径清单
- 其它未记录场景清单
- 修复建议（分层：立即/短期/架构），含统一的接入方式建议
