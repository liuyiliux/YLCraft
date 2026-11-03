# YLCraft AI Entry Rules

This repository is developed by multiple AI agents across multiple machines. Before changing code, every agent must rebuild project context from source files instead of relying on chat history.

## Required First Reads

1. Read `docs/README.md` for the current documentation map.
2. Read `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` for the current system architecture and module boundaries.
3. Read `docs/architecture/API_SURFACE.md` when changing or calling backend APIs.
4. Read `docs/AI_HANDOFF_PROTOCOL.md` for the takeover and handoff workflow.
5. Check active OpenSpec tasks under `openspec/changes/*/tasks.md`.
6. Run `git status --short --branch` and treat existing changes as user or another agent's work.

## Work Rules

- Do not revert or overwrite unrelated dirty files.
- Prefer small, verifiable changes with focused tests.
- **Test scope must match the change（2026-10-04 加）** ——
  run the tests for what you touched, not the whole suite.
  The full suite (`backend/tests`, ~2600 tests, ~10 分钟) is for a **batch** of
  changes before merge, **not** after every edit.
  2026-10-04 an agent ran it 6 次 in one day and burned an hour of pure waiting
  —— 时间花在等上，不是在做事上。

  | 改了什么 | 跑什么 |
  | --- | --- |
  | 一个函数 / 一个 helper | 那个测试文件（秒级） |
  | 某个平台客户端 | 那个平台的测试 |
  | 共用层（`comments.py` / `users.py` / `meta.py`） | 挑一个受影响的平台做冒烟 |
  | 一批改动收尾 | 跑**一次**全量 |

- When changing APIs, database schema, agent tools, or UI workflows, update the architecture/API docs or OpenSpec tasks in the same turn.
- API work is not done until `docs/architecture/API_SURFACE.md` and `docs/architecture/api_surface.json` match the routes, and any semantic/module impact is reflected in `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` or the owning domain doc.
- Agent tools and Skills are treated as internal APIs: update their schema/spec docs and tests when inputs, outputs, risk level, or routing behavior changes.
- Use `docs/devlog/` for historical handoff notes only; it is not the default source of truth.
- For YLCraft-specific takeover or handoff work, use the `.agents/skills/ylcraft-ai-handoff` skill.

## Context Budget Rules（2026-10-26 加）

> 来源：调研一个外部「AI 工作台」项目（luanyujia-workbench）的记忆机制。
> 它把「上下文预算」当工程问题管，而不是靠感觉。我们吃过亏：某份文档涨到没人读。

**三条体量红线。写文档前先看这张表，超了就拆。**

| 对象 | 红线 | 到线动作 |
| --- | --- | --- |
| 接手必读文档（`docs/README.md`、架构、本文件） | **≤ 25 KB** | 拆「主文件（索引+规则）+ reference 子文件（明细）」 |
| 交接记录（`docs/devlog/`、`AI_HANDOFF_PROTOCOL` 的进度段） | **≤ 4 KB** | 只留最新一份，**覆盖写不追加** |
| 单篇 skill / 单篇领域文档 | **≤ 12 KB** | 拆主文件 + reference |

**reference 子文件的例外**：如果它是**被 grep 的查询表**（如工具目录、接口清单），
可以超 12 KB —— 但要显式标注「这是查询表，按需 grep，不要整篇读」。

**已经拆过的**（不要拆回去）：
- `docs/agent/agent-center.md`（24.7 K → 7.9 K），工具明细移到 `docs/agent/TOOL_CATALOG.md`
- `docs/prototypes/PHOTO_REFERENCE_LIBRARY_REQUIREMENTS.md` 仍在 113 K 以上，**待拆**，别当范例

**拆分必须可证明**（只搬不丢）：
1. 先 `git show HEAD:<file>` 留一份拆分前快照
2. 拆
3. 跑核对：对比拆分前后的**关键词/标识符集合**，必须完全一致
4. 把对比结果写进提交说明

## 验证规则：判据只能是画面（2026-10-26 加）

> 外部调研里最值得抄的一条纪律。我们踩过两次：
> 改 `?openEdit=1` 以为写进去就行（修图页没打开）；CSS 插进 JS 字符串里（`node --check` 过了但白屏）。

- **凡是「我改了配置、指望别的层去读」的地方，都必须找到画面上的落点。**
- ❌ 不要拿「我写进去的那个值」当成功证据 —— 那只能证明你写了，不能证明界面读了。
- ✅ 验收标准必须是**用户能看见的东西**：DOM 里有这个元素 / 页面显示这个字 / 截图对得上。
- 原型改完必须用 bsk 打开实测，并加 `?nc=<随机>` 防缓存假阴性。
- 🔴 **`?nc` 只管 HTML，管不到子资源** —— 改了 `js/` 或 `css/` 必须同时 bump
  `index.html` 里那些标签的 `?v=<日期时间>`（全部一起换）。
  2026-11-03 踩过：CSS 链接当时**没有** `?v`，用户浏览器一直用旧 CSS，
  新加的 `.gnode.hasimg{height:208}` 不生效，缩略图高度塌成 0 ——
  我这边测试全是干净浏览器，看不出问题，用户那边就是"怎么没变化"。

## Reporting Rules

- **每次给用户的回复，结尾必须用大白话讲清两件事：「现在到哪了」和「下一步做什么」。**
  只列技术细节（改了哪个文件、跑了几个测试）**不算数** —— 用户看不懂"修好了"和"能用了吗"的区别。
- 说"修好了"之前，先说清**用户能看见的变化**是什么。例如："你点某个视频看评论，以前是空白，现在会告诉他该等还是该换网。"
- 没做完的事要写出来，并说清**为什么没做完**（缺什么、卡在哪、需要用户提供什么）。
- 不确定的事就说不确定。**测过**的才写"已验证"；没测的写"未验证"，不要含糊过去。
- 这条规则写在这里，是因为**对话上下文会被压缩、会丢**：2026-10-04 发生过一次
  用户明确要求过、但压缩后 AI 忘了，只能靠本文件留住。

