# YLCraft AI 接手协议

目标：让任意 AI 在两台电脑、多条开发线之间快速接手，先知道“当前事实来源在哪里”，再动代码。

## 1. 接手前 10 分钟

按顺序执行，不要跳过：

```powershell
git status --short --branch
git log --oneline -8
rg --files docs openspec .agents README.md AGENTS.md 2>$null | Sort-Object
```

然后阅读：

1. `AGENTS.md`
2. `docs/README.md`
3. `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`
4. 当前任务相关的 OpenSpec：`openspec/changes/<change-id>/tasks.md`
5. 当前任务涉及的代码入口和测试
6. 如涉及接口，读取并更新 `docs/architecture/API_SURFACE.md`

如果工作区有未提交改动，默认是用户或另一个 AI 的工作。只能读取、顺着改，不能回滚。

## 2. 判断当前任务属于哪条线

| 任务 | 先看 |
| --- | --- |
| Agent 对话、上下文、工具、Skill | `docs/agent/`、`openspec/changes/agent-*` |
| 创作项目、小说、分镜、角色、参考图 | `docs/guides/creative-project-loop.md`、`openspec/changes/creative-*` |
| 素材、下载、平台采集 | `docs/platform/`、`backend/app/services/crawler*`、`backend/app/api/v1/crawler.py` |
| AI 模型配置、供应商、连接器 | `backend/app/services/ai/`、`backend/app/services/agent/tools/ai_config_tools.py` |
| 前端体验/页面重做 | `docs/rules/03-前端开发规范.md`、相关页面组件 |
| 数据库/迁移 | `docs/rules/06-数据库设计规则.md`、`backend/alembic/versions/` |

不确定时先用 `rg` 找代码事实，不要从旧 devlog 推断。

## 3. 开发中记录规则

- 每完成一个 OpenSpec 子任务，就勾选对应 `tasks.md`。
- 新增接口、工具、Skill、数据库字段时，在同一轮补总架构、接口清单或对应专题文档。
- 修 bug 时记录：现象、根因、修复点、验证命令。
- UI 改动要记录结构变化，不只写“优化样式”。
- 不要把一次性聊天结论当文档，结论要落到 `docs/` 或 OpenSpec。

## 4. 接口和架构同步规则

这不是自动更新要求，而是每个 AI 的收尾纪律。改完接口以后，不能只提交代码。

HTTP API 变更完成标准：

1. 路由、schema、服务实现和测试已更新。
2. 运行或等价更新 `python tools/generate_api_surface.py`，提交 `docs/architecture/API_SURFACE.md` 和 `docs/architecture/api_surface.json`。
3. 人工检查生成结果：新增/删除/改语义的接口是否能从 summary、handler、source 看懂。
4. 如果接口改变模块边界、数据流、前端工作流或 Agent 可调用能力，同步更新 `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`、对应领域文档或 OpenSpec。
5. 在 final/devlog 中说明验证命令和未验证风险。

Agent Tool / Skill 也按“内部接口”处理：

- 输入参数、输出结构、risk level、授权策略、匹配规则、工具名称变化，都必须更新工具 schema、测试和 `docs/agent/agent-skill-runtime.md`。
- 不要只为某个平台写特例；通用能力要沉淀成通用工具或 Skill，再由平台适配层实现差异。
- Skill 文件是过程能力，不存一次性用户事实；上下文和记忆仍以 Agent thread/message/memory 为事实来源。

## 5. 交接文档模板

只有阶段性长任务、跨电脑切换或用户明确要求交接时，才新建或更新：

```text
docs/devlog/YYYY-MM-DD_topic.md
```

推荐结构：

```markdown
# YYYY-MM-DD 交接总结

## 项目目标

## 已改文件

## 当前进度

## 验证结果

## 待办任务

## 关键决策

## 报错细节

## 下一步建议
```

保持短而准。不要复制完整日志，只写能让下一位 AI 继续推进的信息。`docs/devlog/` 是历史记录，不是默认必读事实来源；当前事实优先更新 `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` 和相关专题文档。

## 6. 提交与推送规则

提交前：

```powershell
git diff --check
git status --short
```

按改动范围运行验证：

| 改动 | 最低验证 |
| --- | --- |
| 纯文档/Skill 文档 | `git diff --check` |
| API 清单 | 运行或等价更新 `python tools/generate_api_surface.py`，并人工确认语义和架构影响 |
| Agent 后端 | `backend\venv_win\Scripts\python.exe -m pytest backend\tests\test_agent_center.py -q` |
| 创作项目后端 | 相关 `backend/tests/test_creative_project*.py` |
| 前端 TypeScript/UI | `cd frontend; npm run build` |
| OpenSpec | `openspec validate <change-id> --strict` |

如果工作区有别人的改动，只 stage 自己改的文件。提交信息用简短范围：

```text
docs: add AI handoff protocol
feat(agent): ...
fix(story): ...
```

## 7. 不能做的事

- 不能为了“清爽”删除历史参考资料。
- 不能把旧 devlog、git 历史或已归档 OpenSpec 当当前实现依据。
- 不能无说明改远程数据库结构。
- 不能把授权、上下文、记忆这类基础能力做成单平台特例。
- 不能只改 UI 颜色就声称完成重设计。
- 不能把“跑了接口生成脚本”当成架构更新；脚本只负责路由事实，AI 负责语义判断。

## 8. 项目专用 Skill

后续接手时可显式要求：

```text
使用 ylcraft-ai-handoff 接手这个任务
```

Skill 位置：

```text
.agents/skills/ylcraft-ai-handoff/SKILL.md
```

它会强制 AI 按本文流程读取入口、检查 OpenSpec、保护脏改、最后写交接。
