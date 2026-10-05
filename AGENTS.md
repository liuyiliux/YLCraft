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

## Reporting Rules

- **每次给用户的回复，结尾必须用大白话讲清两件事：「现在到哪了」和「下一步做什么」。**
  只列技术细节（改了哪个文件、跑了几个测试）**不算数** —— 用户看不懂"修好了"和"能用了吗"的区别。
- 说"修好了"之前，先说清**用户能看见的变化**是什么。例如："你点某个视频看评论，以前是空白，现在会告诉他该等还是该换网。"
- 没做完的事要写出来，并说清**为什么没做完**（缺什么、卡在哪、需要用户提供什么）。
- 不确定的事就说不确定。**测过**的才写"已验证"；没测的写"未验证"，不要含糊过去。
- 这条规则写在这里，是因为**对话上下文会被压缩、会丢**：2026-10-04 发生过一次
  用户明确要求过、但压缩后 AI 忘了，只能靠本文件留住。

