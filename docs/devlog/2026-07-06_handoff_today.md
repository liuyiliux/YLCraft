# 2026-07-06 交接总结

## 项目目标

围绕 YLCraft Agent Skill Runtime 和创作项目闭环做收尾：

- Skill 侧参考 DeerFlow / Hermes 思路，完成文件化 `SKILL.md`、Bundle、草稿审批、运行轨迹、上下文回放和匹配测试。
- 创作项目侧只做了少量闭环治理，不应继续跑偏，除非用户明确要求。

## 当前结论

Agent Skill 这块按 OpenSpec `agent-skill-package-runtime` 已完成。

证据：

- `openspec/changes/agent-skill-package-runtime/tasks.md` 中 M0-M10 全部 `[x]`。
- 已有 workflow replay 测试覆盖：多轮上下文 -> Skill trace -> Run 转 Skill -> 审批启用 -> 再次路由命中。
- 当前工作区干净，并已推送到 `origin/master`。

## 今日主要提交

按从早到晚：

- `102c104d feat(agent): add file-backed skill package workflow`
- `3687269b feat(skill): 添加用户自定义 Bundle 创建及 GitHub 仓库 URL 自动解析`
- `72a9d8c9 docs(devlog): 添加Agent Skill文件化运行时交接文档`
- `feb3f524 feat(agent): improve skill runtime observability`
- `fc924aba feat(agent): improve skill draft review`
- `c7f540bd feat(agent): enhance skill bundle management`
- `eee61060 fix(agent): confirm skill bundle deletion`
- `1838af0a docs(agent): add skill runtime guide`
- `861e423a test(agent): add skill workflow replay coverage`
- `f40787e8 feat(creative): clarify project loop navigation`
- `d88de4ce fix(story): add legacy migration hints`
- `079d27ff fix(agent): generate route test examples per skill`

## 已改文件/目录

Agent Skill Runtime：

- `backend/app/services/agent/skill_loader.py`
- `backend/app/services/agent/skill_drafts.py`
- `backend/app/services/agent/runtime/skills.py`
- `backend/app/services/agent/runtime/context.py`
- `backend/app/services/agent/tools/skill_tools.py`
- `backend/app/services/agent/service.py`
- `backend/app/api/v1/agent.py`
- `backend/app/db/models/agent.py`
- `backend/app/skills/**/SKILL.md`
- `backend/app/skills/bundles/*.yaml`
- `frontend/src/components/agent/SkillManagementPanel.tsx`
- `frontend/src/pages/agent/index.tsx`
- `frontend/src/api/agent.ts`
- `frontend/src/api/index.ts`
- `backend/tests/test_agent_center.py`
- `docs/agent-skill-runtime.md`
- `docs/devlog/2026-07-06_agent_skill_runtime_gap_plan.md`
- `openspec/changes/agent-skill-package-runtime/`

创作项目闭环治理：

- `frontend/src/components/layout/AppLayout.tsx`
- `backend/app/api/v1/story.py`
- `backend/tests/test_story_legacy_compat.py`
- `docs/creative-project-loop.md`
- `openspec/changes/creative-project-closed-loop/tasks.md`

## 当前进度

### Agent Skill Runtime

已完成：

- 文件化 Skill 包加载：`backend/app/skills/**/SKILL.md`
- YAML frontmatter 解析、校验、checksum、package index
- 内置 Skill 迁移
- metadata 驱动路由：keywords / context_keys / tools
- 渐进式上下文加载：先 Skill index，命中后再注入完整 Skill
- slash 激活：`/skill_name`
- Bundle YAML：内置和用户 Bundle
- Bundle 创建、编辑、删除 API 和 UI
- 外部 Skill / 手动粘贴 Skill 进入草稿审批
- Run 转 Skill 草稿
- 草稿 diff、批准、拒绝、拒绝后回填编辑器
- 路由规则编辑生成草稿，不直接覆盖 active Skill
- target-skill 反向诊断：缺关键词、缺上下文、缺工具
- Run 记录 selected Skill、route reasons、Bundle
- Skill usage/success 统计
- Agent 页面显示本轮 Skill 并可跳转管理页
- 文档：`docs/agent-skill-runtime.md`
- 回放测试：`test_agent_workflow_replay_context_skill_trace_and_approved_skill_routing`

最近用户反馈并已修：

- “匹配测试不要写固定一个，目前已有的技能都应该有自己的”
- 已改为：匹配测试根据当前 Skill 的 `triggers.keywords`、`context_keys`、`tools` 自动生成 message/context/tools。
- 目标 Skill 下拉切换时自动换成该 Skill 自己的测试样例。
- Bundle 测试也根据 Bundle 内 Skill 生成测试输入，不再复用上一次输入。

### 页面样式说明

用户问“是不是把页面样式改了”：

- 是，今天改过全局侧边栏导航结构和标签。
- 文件：`frontend/src/components/layout/AppLayout.tsx`
- 改动：主导航提升为 `创作项目 / 素材库 / 下载 / 小说 / AI 图片`。
- 非主线模块加了 `实验` / `辅助` 标签。
- 这会影响截图里的左侧导航视觉。
- Skill 管理页本体本轮主要改的是“匹配测试”行为，不是大改视觉。

### 创作项目闭环

只做了基础治理，不是当前主线：

- 新增 `docs/creative-project-loop.md`
- OpenSpec `creative-project-closed-loop` 勾掉 Phase 0 和 #27、#52
- 旧 `/api/v1/story` 接口增加 `migration_hint`，指向 `/api/v1/creative-projects`
- 注意：之前一度准备继续做“从小说章节创建项目”的前端入口，但用户打断并要求回到 Skill。不要继续这个方向，除非用户明确要求。

## 验证记录

已通过：

```powershell
backend\venv_win\Scripts\python.exe -m pytest backend\tests\test_agent_center.py -q
```

结果：`97 passed`

```powershell
openspec validate agent-skill-package-runtime --strict
```

结果：通过

```powershell
npm.cmd run build
```

结果：通过

```powershell
backend\venv_win\Scripts\python.exe -m pytest backend\tests\test_creative_project_service.py backend\tests\test_creative_project_writer_room_api.py backend\tests\test_story_legacy_compat.py -q
```

结果：`22 passed`

```powershell
openspec validate creative-project-closed-loop --strict
```

结果：通过

## 关键决策

- 不引入 DeerFlow / Hermes 依赖，只借鉴：
  - DeerFlow：文件化 Skill、渐进加载、slash activation
  - Hermes：程序性记忆、成功 workflow 沉淀为 Skill
- 外部 Skill 不自动启用，必须草稿审批。
- 路由规则编辑不直接改 active Skill，只生成待审批 `SKILL.md` 草稿。
- 普通读类工具不重复授权；授权主要用于 write/delete/costly。
- Skill 是过程能力，不存项目内容、用户隐私或一次性对话事实。
- `thread_id` 是长期上下文主线，run/step/snapshot 负责回放和证据。

## 报错和处理细节

### 1. PostgreSQL 事务异常

现象：

```text
InFailedSQLTransactionError: current transaction is aborted
```

处理：

- `_build_failover_chain()` 不再在 except 里直接 `session.rollback()`
- 多个 DB 写操作用 `begin_nested()` 隔离
- `chat()` 分阶段 commit / rollback guard
- 测试 fixture 补 `AIConnector` 表

### 2. MissingGreenlet

原因：

- SQLite 测试里缺表后触发 rollback，破坏 async greenlet 上下文。

处理：

- 去掉 failover 内部 rollback
- fixture 补表

### 3. B 站搜索失败

日志：

```text
'CrawlerService' object has no attribute 'use_mediacrawler'
```

处理：

- 修过 CrawlerService 兼容路径。
- `Unknown search_type 'note'` 只是 B 站 fallback 到 video search，不是致命错误。

### 4. 重复授权

处理：

- 授权等级收敛为 `write/delete/costly`
- 普通外部读取和搜索不再反复要求授权。

### 5. 匹配测试固定示例

处理：

- `SkillManagementPanel.tsx` 新增 `buildSkillRouteExample()`
- 根据每个 Skill 的 triggers 自动生成测试输入。

## 待办任务

Skill 计划内功能：无阻塞，OpenSpec 已全勾。

Skill 后续可优化项：

- 继续美化 Skill 管理页，但别只改颜色，要改信息层级和交互密度。
- 增加 Skill 质量检查：过宽关键词、缺失 required_tools、重复 Skill 名。
- UI 手测：切换每个 Skill，确认匹配测试样例是否合理。
- 可增加一个前端单元测试或 Playwright/Patchright 测试覆盖 Skill 示例填充。

创作项目剩余 OpenSpec：

- `creative-project-closed-loop`：19 项未完成
- `creative-project-optimization-roadmap`：11 项未完成
- `task-observability-diagnostics`：1 项未完成

不要把这些误认为 Skill 未完成。

## 下一步建议

如果用户继续问 Skill：

1. 先确认 `settings?tab=agent-skills` 页面中匹配测试是否每个 Skill 都自动切换样例。
2. 如还丑，重点改 Skill 管理页右侧结构，不要再动全局导航。
3. 若要功能增强，优先做 Skill 质量检查和示例测试覆盖。

如果用户说继续做剩余任务：

1. 先问清是继续 Skill 优化，还是切到创作项目闭环。
2. 不要默认继续小说章节转项目，刚才已经被用户纠偏。

## 当前仓库状态

- 分支：`master`
- 远端：`origin/master`
- 最新提交：`079d27ff fix(agent): generate route test examples per skill`
- 当前工作区：干净
