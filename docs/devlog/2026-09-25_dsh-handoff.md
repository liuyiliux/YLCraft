# 2026-09-25 从 Codex 换到 DSH 的接手说明

## 适用场景

- 同一台 Windows 电脑，仓库路径保持 `F:\PycharmProjects\YLCraft`。
- 不换机器、不换数据库、不换工作区，不需要重新 clone、复制目录或迁移 PostgreSQL 数据。
- Codex 退出后，DSH 直接读取同一个工作目录。当前所有未提交和未跟踪改动仍在这里。

## 项目目标

继续推进 YLCraft。当前工作区不是干净仓库，包含前几轮完成的认证、归属、TripoSR 迁移、UniRig 规划文档和大量尚未提交的前后端改动。DSH 接手时不要再开一份 clone，也不要从远端拉一个“干净版本”覆盖当前目录。

## DSH 接手第一步

在中文字符可能被终端错误解码的前提下，优先运行只读命令并先确认状态：

```powershell
cd F:\PycharmProjects\YLCraft
git status --short --branch
git log --oneline -8
```

然后按顺序阅读：

1. `AGENTS.md`
2. `docs/README.md`
3. `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`
4. `docs/architecture/API_SURFACE.md`
5. `docs/AI_HANDOFF_PROTOCOL.md`
6. `openspec/changes/*/tasks.md` 中仍在进行或暂缓的 change

工作区里的修改和未跟踪文件默认是用户或上一轮 Agent 的工作。禁止执行 `git reset --hard`、`git checkout --` 或全局清理；只顺着现状修改。

## 当前进度

### 已完成

- 历史数据已归到本地 `root` 账号。涉及 `creative_projects`、`asset_nodes`、`project_task_records`、`video_generation_tasks`、`model3d_generation_tasks`。最后一次只读复核五张表均为 `null_before=0 updated=0 remaining=0`。
- `user-authentication` 已归档，包含服务端会话、HttpOnly Cookie、外部 Agent Key 与人类会话任一通过、登录失败限流、归属校验和前端登录页。
- TripoSR 已从 `Model3DService` 的硬编码 HTTP 调用迁到配置驱动连接器。相关 focused tests 55 例通过。
- UniRig 本地绑骨只完成 Phase 1：上游版本、MIT 许可、权重文件与 SHA-256、sidecar 接口契约、错误码、共享目录和 AIConnector 字段映射已经写入 `openspec/changes/unirig-local-rigging-service/design.md`。

### 暂缓

- UniRig Phase 2 及以后暂缓。当前机器是 RTX 3060 Laptop 6GB，官方最低要求 8GB，用户暂时不购买支持设备。
- 不下载多 GB 权重，不创建半成品 Docker 服务，不提前做“本地 UniRig”前端入口。重新启动条件是有 8GB 或更高显存的 NVIDIA 机器，并且 Docker Linux 引擎可用。
- TripoSR 真实供应商 smoke 未完成，因为当前没有可用 key。代码迁移已完成，但不能把 mock/本地契约测试说成真实供应商验收。

### 仍然脏的工作区

`git status --short --branch` 显示 `main...github/main [ahead 71]`，同时有大量已修改和未跟踪文件。这些是上一轮和本轮累计的工作。新 AI 只能顺着改，不能执行 `git reset`、`git checkout` 或全局清理。

## 如果以后真的换电脑

当前不执行这一节。它只保留给未来换机器时使用；如果只是从 Codex 换成 DSH，直接跳过。

### 方案 A：最稳，整目录复制

复制整个 `F:\PycharmProjects\YLCraft`，包含隐藏文件和未提交改动。不要把 `backend\venv_win` 和 `frontend\node_modules` 当成可移植依赖；新机器建议重新创建。

必须一起检查的本地内容：

- `backend\.env`：不在 Git 中，包含本机配置和可能的供应商配置。不要把内容贴进交接文档或提交。
- PostgreSQL 数据：本地数据库不随 Git 走。需要迁移时用 `pg_dump`/`pg_restore` 或备份 Docker volume。
- `backend\storage`：素材、缩略图、生成结果和临时文件的本地存储。
- `frontend\public\login`：未跟踪的登录页背景资源。
- `local`、`CUDA`、`HTTP`、`YLCraft` 等当前未跟踪文件：先确认归属，不要顺手删除。

### 方案 B：走 Git

只有在明确决定提交时才使用 Git。远程 `origin` 是 CNB，当前交接说明记录其推送正常；`github` 推送不稳定，不要浪费时间。不要直接 push 到 `github`。

如果走 Git，提交前必须按改动范围跑对应测试，只暂存自己确认的文件，并把未提交但不该入库的本地文件排除。当前任务没有替用户提交或推送，所以新环境不能只依赖 `git pull`。

## 当前环境与启动命令

同一台电脑通常不需要重新安装项目。只有 DSH 发现依赖缺失、虚拟环境损坏或换了 Python/Node 运行时，才重新创建依赖环境。

当前已验证的本机版本：

- Python 3.10.6，使用 `backend\venv_win`。
- Node.js 24.15.0，npm 11.12.1。项目要求 Node 18+，推荐 20 LTS。
- Git 2.55.0.windows.3。
- OpenSpec CLI 1.3.1。

从仓库根目录执行：

```powershell
cd backend
python -m venv venv_win
.\venv_win\Scripts\python.exe -m pip install -r requirements.txt
.\venv_win\Scripts\python.exe -m alembic upgrade head
cd ..\frontend
npm install
```

后端和前端分别启动时按仓库实际脚本执行。启动后确认：

- 前端：http://localhost:3000
- 后端：http://localhost:8000
- API 文档：http://localhost:8000/docs

## 验证结果

本轮已执行：

```text
openspec validate --all --strict --no-interactive
36 passed, 0 failed

backend pytest -q
1083 passed, 4 failed, 4 skipped  →  DSH 接手轮修复后：1087 passed, 0 failed, 4 skipped

backfill_owner_user_id dry-run
five tables: null_before=0, updated=0, remaining=0

git diff --check
no whitespace errors
```

全量后端测试当时有 4 个失败（**已于 2026-09-25 DSH 接手轮修复，现为 1087 passed / 0 failed**）：

- 3 个是 storybook/creative-project 对 `PACKAGE_PLAN_STAGES` 的旧断言与当前 `STORYBOOK_STAGES` 不一致。
- 1 个是 `overlay_text` dry-run 仍断言“不落盘”，而当前实现已明确改为一律生成 `_preview.png`。

修复口径（重要，不是简单改数字）：

- `STORYBOOK_STAGES` 是**有意**的专用词表（通用内容包词表缺「故事→分镜」这一步，会让页数只能硬填），故把测试从「必须等于通用词表」改为「词表身份 + 族别 + 不混叙事**章节编排**阶段」。
- `NARRATIVE_STAGES` 收窄为 `outline/chapter_plan/chapter_outline/novel_body/review`：`script`/`storyboard`/`comic_pages` 是**跨族共用**的产物阶段（前端 `pipelineStageOptions` 里与大纲、正文并列），算作叙事专属属于把「名字重合」误判成「族别串味」。
- `overlay_text` 测试改为按**真实调用契约**（端点不传 `output`）断言 dry_run 落 `_preview.png`、不写正式产物；同步修正了实现里过时的 docstring 与 CLI 帮助文本。

本轮没有重新跑前端 `vitest`、TypeScript 检查和生产构建。前端最后记录的完整通过结果在 `docs/devlog/2026-09-23_user_authentication_handoff.md`，换环境后不能直接把它当成当前工作区的最终证明。

**已补验（2026-09-25 DSH 接手轮）**：前端侧已在本工作区重跑，全部通过——

```text
cd frontend
npx vitest run   →  Test Files 20 passed (20) / Tests 338 passed (338)
npm run build    →  tsc --noEmit（两份 tsconfig）+ vite build 通过（退出 0）
```

因此当前工作区是「后端 `1087 passed, 0 failed, 4 skipped` + 前端 `338 passed`」双绿状态，可直接作为后续接手的基线；上面那句"未重跑"仅保留作历史。

## 活动任务的阻塞盘点（2026-09-25 逐条核实）

目标「把活动的任务全部开发完」在代码侧已无可推进项：4 条活动 change 的 **20 个未勾选任务，没有一项是"代码没写"**，全部卡在外部条件。逐条核实结果：

| change | 未勾 | 阻塞性质 | 解封条件（均在用户侧） |
| --- | --- | --- | --- |
| `fanqie-publisher` | 7 / 31 / 32 | 需真实账号写路径 | 提供有效 Cookie + 自建 `[TEST]` 测试章，跑 `tools/test_fanqie_client.py --live` |
| `fanqie-publisher` | 21 / 23 / 25 | E 组端点未抓包 | 登录态抓包取得真实 path 与签名参数，回填 `design.md` 端点表后替换 `routes.py` 的 `not_captured` 占位 |
| `unirig-local-rigging-service` | 4-13 | 硬件不足 | 8GB+ 显存 NVIDIA 机器且 Docker Linux 引擎可用 |
| `3d-rigging-digital-human` | 16 | 付费额度 + 产品已搁置 | 开通腾讯云 3D 绑骨付费资源，**且**重新决定恢复该能力 |
| `3d-rigging-digital-human` | 13 / 14 | 追踪指针 | 不在此 change 实施，已拆到上面两个独立 change |
| `triposr-connector-migration` | 9 | 无真实 key | 在受管连接器配置真实 TripoSR key 后跑真实 smoke |

**禁止的"推进"方式（会违反仓库硬规矩）**：不得为 E 组端点猜写路径（运行时必 404）、不得以 mock 冒充 TripoSR 供应商验收、不得把 6GB 显存下的失败包装成"本地绑骨可用"。

**验证过的基线（可直接信任）**：后端 `1087 passed / 0 failed / 4 skipped`；前端 `vitest 338 passed`；`openspec validate --all --strict` 36 passed；`alembic current` = `heads` = `046`；工作区除 6 个已知垃圾文件外干净，`origin` 与 `github` 均已同步。

## 关键决策

- `root` 历史归属是本地数据库运维动作，不写进 Alembic 自动迁移。`root` 密码、Cookie、Token 和供应商密钥不得进入仓库。
- 新资源必须由服务端写入 owner；历史 `NULL` 仍按遗留数据可访问，不能因为迁移把历史内容全部锁死。
- UniRig 只保留已调研的契约和版本结论，暂不实现服务。没有支持显存前，不把 6GB 失败包装成“本地绑骨可用”。
- 本地 UniRig 失败时不得静默切到腾讯云。这个边界写在 `openspec/changes/unirig-local-rigging-service/specs/unirig-local-rigging-service/spec.md`。

## 下一步建议

1. 不需要搬迁：DSH 直接使用 `F:\PycharmProjects\YLCraft` 当前目录。
2. 先跑 `git status --short --branch`，确认脏文件仍在，再按 `docs/AI_HANDOFF_PROTOCOL.md` 重建上下文。
3. UniRig 保持暂停；除非以后有至少 8GB 显存的 NVIDIA GPU 且用户明确恢复该任务，不要开始 Phase 2。
4. TripoSR 若要做真实验收，需要用户在受管连接器里配置真实 key；不要把 key 写进源码、文档、测试或交接文件。
5. DSH 完成任务后继续更新对应 OpenSpec，并运行 `openspec validate --all --strict --no-interactive` 和 `git diff --check`。

## 可直接给 DSH 的启动话术

```text
请在 F:\PycharmProjects\YLCraft 同一工作区接手 YLCraft。先读 AGENTS.md、docs/README.md、docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md、docs/architecture/API_SURFACE.md、docs/AI_HANDOFF_PROTOCOL.md，以及 docs/devlog/2026-09-25_dsh-handoff.md。先跑 git status --short --branch，保护现有未提交和未跟踪改动，不要 reset、checkout 或清理。历史数据已归本地 root；TripoSR 代码迁移已完成但真实供应商 smoke 未做；UniRig 因当前 6GB 显存低于官方 8GB 最低要求而暂缓。当前 Python 使用 backend\venv_win\Scripts\python.exe。
```

## 主要文件入口

- 总规则：`AGENTS.md`
- 文档地图：`docs/README.md`
- 交接协议：`docs/AI_HANDOFF_PROTOCOL.md`
- 历史归属运维：`docs/guides/owner-backfill.md`
- TripoSR 迁移：`docs/guides/triposr-connector-migration.md`
- UniRig 调研与契约：`openspec/changes/unirig-local-rigging-service/design.md`
- UniRig 任务状态：`openspec/changes/unirig-local-rigging-service/tasks.md`
- TripoSR 任务状态：`openspec/changes/triposr-connector-migration/tasks.md`
