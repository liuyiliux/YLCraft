# YLCraft 文档地图

本文是项目文档入口。新 AI 接手时先读这里，再按任务进入对应目录，避免反复全仓考古。

## 必读入口

| 文档 | 用途 |
| --- | --- |
| `AGENTS.md` | 仓库级 AI 入口规则，短规则优先级最高。 |
| `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` | 总架构入口：产品主线、模块边界、核心模型、接口维护规则。 |
| `docs/architecture/API_SURFACE.md` | 后端接口清单，接口变更后必须同步。 |
| `docs/DESIGN.md` | 产品定位、总体架构、模块状态的单一事实来源。 |
| `docs/AI_HANDOFF_PROTOCOL.md` | 多 AI / 多电脑协作协议：接手、开发、交接、提交前检查。 |
| `openspec/changes/*/tasks.md` | 正在推进的规格任务和完成状态。 |

## 文档目录职责

| 目录 | 放什么 | 规则 |
| --- | --- | --- |
| `docs/agent/` | Agent 工作台、Skill Runtime、工具调用、记忆、上下文。 | Agent 相关实现变化必须更新这里或对应 OpenSpec。 |
| `docs/architecture/` | 子系统架构设计，如资产中枢、AI 服务层、播放器、规则助手。 | 讲长期设计，不写当天流水账。 |
| `docs/guides/` | 可执行工作流说明，如创作项目闭环。 | 面向“怎么用/怎么串起来”。 |
| `docs/platform/` | B 站、多平台采集/发布等外部平台能力。 | 平台兼容、登录、限流、接口差异放这里。 |
| `docs/rules/` | 后端、前端、数据库、代码风格等工程规范。 | 规则类文档要短、可执行。 |
| `docs/refactor/` | 重构、迁移、清理计划。 | 计划完成后把长期结论回写到架构或领域文档。 |
| `docs/devlog/` | 必要的阶段性交接。 | 只在跨电脑/长任务切换时写，文件名用 `YYYY-MM-DD_topic.md`。 |
| `docs/reference/` | 外部参考资料、客户素材、二进制样例。 | 不作为当前实现事实来源。 |

## 当前主线状态

| 主线 | 状态 | 事实来源 |
| --- | --- | --- |
| Agent Skill Runtime | 已完成并归档 | `openspec/changes/archive/agent-skill-package-runtime/tasks.md` |
| Agent 多智能体/上下文运行时 | 已完成并归档 | `openspec/changes/archive/agent-center-multi-agent-runtime/tasks.md` |
| 创作项目闭环 | 仍有未完成项 | `openspec/changes/creative-project-closed-loop/tasks.md` |
| 创作项目优化路线 | 仍有未完成项 | `openspec/changes/creative-project-optimization-roadmap/tasks.md` |
| 任务观测诊断 | 仍有少量未完成项 | `openspec/changes/task-observability-diagnostics/tasks.md` |

## 每次开发后必须更新什么

| 改动类型 | 必须同步 |
| --- | --- |
| 新增/修改 HTTP API | `docs/architecture/API_SURFACE.md` 和 `docs/architecture/api_surface.json`；如影响模块职责或工作流，再更新 `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`、领域文档或 OpenSpec。 |
| 新增/修改 Agent Tool / Skill | 工具 schema、risk level、测试、`docs/agent/agent-skill-runtime.md`；如改变运行时边界，再更新总架构。 |
| 新增/修改数据库字段 | Alembic 迁移、模型说明；如需人工执行，在 final 或必要 devlog 里写清命令。 |
| Agent 工具/Skill 变化 | `docs/agent/agent-skill-runtime.md` 和相关测试。 |
| UI 结构或交互变化 | 对应页面文档或必要 devlog 截短说明，不把视觉想法散写到聊天里。 |
| 阶段性完成 | 优先更新架构/领域文档；只有跨电脑/长任务交接才写 `docs/devlog/YYYY-MM-DD_topic.md`。 |

`tools/generate_api_surface.py` 只能同步路由事实，不能替代架构判断。跑完脚本后仍要检查：接口语义是否变了、前端调用是否受影响、Agent 工具是否要同步、OpenSpec 任务是否要勾选。

## 文档清理原则

- 不再新增根目录散文档，除非是 `README.md`、`AGENTS.md` 这类入口文件。
- 过期方案能删就删；需要规格追溯的归入 `openspec/changes/archive/`；外部参考放 `docs/reference/`。
- 同一主题只保留一个当前事实来源，历史细节依靠 git 历史或必要 devlog。
- 参考资料和实现文档分开：`docs/reference/` 不是实现状态。
- `docs/devlog/` 是历史推进记录，不是新 AI 默认必读入口；当前事实要沉淀回架构、接口或专题文档。
