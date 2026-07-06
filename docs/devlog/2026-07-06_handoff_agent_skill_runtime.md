# 2026-07-06 交接总结：Agent Skill 文件化运行时

## 项目目标

围绕 YLCraft 的 Agent Skill 架构继续推进：参考 Hermes Agent / DeerFlow 思路，把 Skill 从写死规则升级为文件化 `SKILL.md` 包；支持外部 Skill URL 导入但必须先进入草稿审批；支持成功 Agent Run 沉淀为 Skill 草稿；增加设置页的 Skill 管理 UI；优化 Agent 技能页视觉；修复 URL 导入、Bundle 固定等问题。

## 已提交代码

### `102c104 feat(agent): add file-backed skill package workflow`

- 新增文件化 Skill Loader：`backend/app/services/agent/skill_loader.py`
  - 加载 `backend/app/skills/**/SKILL.md`
  - 解析 YAML frontmatter
  - 支持 `references/`、`templates/`
  - 支持 Bundle YAML
- 新增 Skill 草稿审批服务：`backend/app/services/agent/skill_drafts.py`
  - 支持手动粘贴 `SKILL.md`
  - 支持 URL 导入
  - 支持批准写入 `backend/app/skills/user/.../SKILL.md`
  - 禁止覆盖内置 Skill
  - 阻止 localhost / 私网 URL
- 新增 Agent 工具：
  - `import_agent_skill_from_url`
  - `create_agent_skill_draft`
  - `list_agent_skill_drafts`
  - `list_agent_skill_packages`
  - `inspect_agent_run_skill_candidate`
  - `create_agent_skill_draft_from_run`
- 新增设置页 `Agent 技能` Tab：`frontend/src/components/agent/SkillManagementPanel.tsx`
- Agent Run 页面新增“分析 Skill”“生成 Skill 草稿”和跳转审批页。
- 新增内置 Skill 包：AI 模型配置、素材检索/打标、角色视觉卡、角色立绘提示词、漫画生图提示词、连续性检查、小说补全/润色/审校、导出、下载、视频、字幕、TTS 等。
- 新增 OpenSpec：`openspec/changes/agent-skill-package-runtime/`

### `3687269 feat(skill): 添加用户自定义 Bundle 创建及 GitHub 仓库 URL 自动解析`

- GitHub 仓库首页导入支持：
  - 输入 `https://github.com/owner/repo`
  - 自动尝试：
    - `https://raw.githubusercontent.com/owner/repo/main/SKILL.md`
    - `https://raw.githubusercontent.com/owner/repo/main/skills/<repo>/SKILL.md`
    - `master` 分支同样尝试
- URL 导入失败时返回 diagnostics，前端显示更有用的原因。
- Bundle 不再只能是内置固定 YAML：
  - 新增 `POST /api/v1/agent/skills/bundles`
  - 用户创建后写入 `backend/app/skills/user/bundles/*.yaml`
  - Loader 同时加载内置和用户 Bundle
- 前端新增 Bundle 创建 UI：名称、描述、多选 Skill。
- “路由预览”改名为“匹配测试”，说明它只是模拟用户消息会命中哪些 Skill，不会真正执行。

## Codex 技能安装

用户要求安装 [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill)。

已安装到 Codex 用户技能目录，不在项目里：

`C:\Users\AI\.codex\skills\taste-skill\SKILL.md`

该 `SKILL.md` 内声明的技能名：

`design-taste-frontend`

注意：需要重启 Codex 才能在新会话自动拾取这个新安装技能。

## 设计优化

使用 `taste-skill` 思路优化了 Agent 技能页：

`frontend/src/components/agent/SkillManagementPanel.tsx`

方向：

- 这是后台产品工具页，不是 landing page。
- 沿用 Ant Design 和现有主题 token。
- 视觉语言：克制、可扫描、偏企业工具台。
- 设计拨盘：Variance 4 / Motion 2 / Density 7。

改动：

- 顶部工作台头部：Skill 包、待审批、Bundle、调用记录。
- 表格增加选中态、hover 态、统一表头层级。
- 当前 Skill、匹配测试、草稿审批、Bundle 统一面板系统。
- 增加响应式规则，避免窄屏挤爆。

## 当前功能说明

### 文件化 Skill

默认从 `backend/app/skills/**/SKILL.md` 加载。

用户批准的外部 Skill 写到 `backend/app/skills/user/<skill-name>/SKILL.md`。

### 外部 Skill 导入

支持：

- raw `SKILL.md`
- GitHub blob URL
- GitHub 仓库首页
- GitHub tree 目录 URL

导入不会自动启用，先进入草稿审批。

### 草稿审批

设置页入口：`/settings?tab=agent-skills`

流程：

1. 输入 URL 或粘贴完整 `SKILL.md`
2. 创建待审批草稿
3. 审查内容和 diff
4. 批准后写入用户 Skill 目录
5. Loader 重新加载后进入 Agent 路由

### 匹配测试

原“路由预览”。

作用：

- 输入一条用户消息
- 可选输入 context JSON
- 查看会命中哪些 Skill
- 不执行工具
- 不真正启动 Agent

### Bundle

Bundle 是多个 Skill 的组合。

内置 Bundle：`backend/app/skills/bundles/*.yaml`

用户 Bundle：`backend/app/skills/user/bundles/*.yaml`

前端现在可以创建用户 Bundle。

## 验证记录

后端：

```powershell
.\venv_win\Scripts\python.exe -m pytest tests\test_agent_center.py -q -k "skill_draft or skill_package or skill_route or skill_tools or run_skill or skill_bundle"
```

结果：`23 passed`

前端：

```powershell
npm.cmd run build
npm.cmd run smoke:pages
```

结果：

- build 通过
- `Page smoke passed: /agent, /story, /characters, /assets, /settings`

OpenSpec：

```powershell
openspec validate agent-skill-package-runtime --strict
```

结果：通过。

其他：

```powershell
git diff --check
```

结果：通过。

## 重要问题和处理

### GitHub 仓库 URL 导入失败

用户输入：`https://github.com/Leonxlnx/taste-skill`

页面报：`Fetch skill URL failed: All connection attempts failed`

原因：后端环境连接 `github.com` 失败，但可连接 `raw.githubusercontent.com`。

处理：自动把仓库首页展开成 raw 候选地址。对 `Leonxlnx/taste-skill` 会尝试：

- `https://raw.githubusercontent.com/Leonxlnx/taste-skill/main/SKILL.md`
- `https://raw.githubusercontent.com/Leonxlnx/taste-skill/main/skills/taste-skill/SKILL.md`

### 私网 URL 安全漏洞

发现：`SkillDraftError` 继承 `ValueError`，导致 `_validate_url()` 里的私网 IP 报错被 `except ValueError` 吞掉。

处理：

- 只捕获 IP 解析失败。
- 真实私网 / loopback / link-local / reserved / unspecified IP 全部拒绝。
- 重定向每一跳都重新校验。

### Bundle 固定

原状态：只加载内置 `backend/app/skills/bundles/*.yaml`。

处理：

- 新增用户 Bundle 写入目录：`backend/app/skills/user/bundles/*.yaml`
- Loader 同时加载内置和用户 Bundle。
- 前端提供创建入口。

## 关键文件

后端：

- `backend/app/services/agent/skill_loader.py`
- `backend/app/services/agent/skill_drafts.py`
- `backend/app/services/agent/tools/skill_tools.py`
- `backend/app/services/agent/runtime/skills.py`
- `backend/app/services/agent/runtime/context.py`
- `backend/app/services/agent/service.py`
- `backend/app/api/v1/agent.py`
- `backend/app/db/models/agent.py`
- `backend/tests/test_agent_center.py`

前端：

- `frontend/src/components/agent/SkillManagementPanel.tsx`
- `frontend/src/pages/settings/index.tsx`
- `frontend/src/pages/agent/index.tsx`
- `frontend/src/api/agent.ts`
- `frontend/src/api/index.ts`

OpenSpec：

- `openspec/changes/agent-skill-package-runtime/`

## 后续建议

1. Skill 可观测性
   - 每次 Agent Run 记录命中了哪些 Skill
   - 命中原因、分数、来源 package/slash/bundle
   - UI 展示“本次使用 Skill”
2. Skill 编辑器
   - 草稿批准前可在线编辑
   - frontmatter 校验
   - required_tools 是否存在校验
   - triggers 预览
3. Bundle 管理增强
   - 删除 Bundle
   - 编辑 Bundle
   - 显示 Bundle 来源：builtin/user
   - 显示包含 Skill 是否缺失
4. Run 转 Skill 增强
   - 目前是确定性生成
   - 后续可加 AI 润色，但必须继续走草稿审批
5. 文档补充
   - 写一页“如何写 YLCraft Skill”
   - 给用户一个最小 `SKILL.md` 模板
   - 给 Bundle 一个 YAML 示例

