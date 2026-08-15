# 2026-08-15 分支收敛交接

## 项目目标

把仓库从多分支（`main` / `develop` / `master`）收敛为单一 `main`，并清理两个远程（`github`、`origin`=cnb.cool）与本地所有冗余分支和临时备份引用。

## 背景与分支分析

- `develop`（`685e6ffa`）最新最完整 → 作为唯一 `main`。
- 旧 `main`（`96b38a17`）是早期快照，含泄露文件（`backend/.env`、`backend/app/data/settings.json`）与旧架构代码。
- `master`（本地 `444fbcb0`，远程 cnb.cool `da798d0b`）有 232 个旧提交，但**无独有文件**（全部内容已在 `main` 中）。

## 已执行操作

1. 本地 `main` 强推到 `develop` 顶点 `685e6ffa`。
2. 三笔提交落在该顶点：`9ba17d36`（backend）、`be2d3365`（frontend）、`685e6ffa`（docs）。
3. 删除本地 `master`、`develop`，以及临时备份 tag `backup/main-old`、`backup/master-old`、`backup/develop-now` 和本地分支 `local/pre-public-history-working-copy`。
4. 删除远程分支：github `develop`；cnb.cool `develop`、`master`。

## 当前状态

- github：仅 `main`（`685e6ffa`）。
- cnb.cool：仅 `main`（`685e6ffa`），默认分支已改为 `main`。
- 本地：仅 `main`，工作区干净，`main` 跟踪 `github/main`。

## 关键决策

- **删前已核查无有用代码丢失**：`master` 无独有文件；旧 `main` 唯一的“真独有”功能是豆包 Doubao 后端（`services/llm/doubao.py`，硬编码 OpenAI 兼容封装），已被当前 `GenericLLMBackend`（配置驱动、支持任意 OpenAI 兼容 API）覆盖，豆包可直接加 DB 配置使用。
- 旧 `main` 的其余独有文件均为泄露密钥/日志/构建产物或旧架构同功能代码，未保留。

## 报错细节

- cnb.cool 的 `master` 是**默认分支**，`git push --delete` 被拒：`remote rejected master (deletion of the current branch prohibited)`。需先在网页把默认分支改为 `main`，再删除成功。
- 其公开 OpenAPI（`api.cnb.cool/swagger.json`）的仓库 PATCH 接口仅支持 description/license/site/topics，无「改默认分支」接口，只能网页操作。

## 下一步建议（另一台机器）

1. `git fetch --prune` 同步远端分支消失。
2. 若本地还 checkout 着旧 `master`/`develop`：先 `git checkout main`，再 `git branch -D master develop`。
3. 本地残留旧提交仍可通过 `git fsck --unreachable` 在 gc 前找回；如需长期兜底可打归档 tag（指向 `685e6ffa`）。
