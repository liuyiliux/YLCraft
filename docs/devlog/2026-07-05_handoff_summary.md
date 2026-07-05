# 2026-07-05 交接总结

## 项目目标
YLCraft 智能体中心按 DeerFlow/Hermes 方向重构：以 thread -> messages -> context snapshots -> runs -> steps -> memory 为主线，解决刷新/多轮无上下文、运行轨迹割裂、重复授权、平台搜索失败等问题。

## 当前进度：63/63 done = 100%

### 第七轮（最终轮）新增完成
- [x] M1.4/M1.5 历史数据回填迁移
  - 新建 Alembic migration 019：`agent_sessions` → `agent_threads`（ID/title/context/时间戳）
  - 解析 `agent_sessions.messages` JSON 数组，逐条插入 `agent_messages`
  - 幂等设计：NOT IN 防重复，JSON 格式校验防异常
- [x] M1.6 索引补充验证
  - agent_threads：user_id + status + active_profile_id + updated_at（015+017）
  - agent_messages：thread_id + run_id + role + tool_call_id + created_at
  - agent_context_snapshots：thread_id + run_id + kind + created_at
  - 所有要求索引均已覆盖
- [x] M2.1 ThreadManager 服务（已有实现）
  - create_thread / get_thread / list_threads / update_title / archive_thread + 更多
- [x] M7.5 前端 smoke 测试文件
  - `test_frontend_smoke.py`：patchright 浏览器自动化，验证两轮对话刷新后同一线程、新建线程清空
  - 由 `RUN_FRONTEND_SMOKE=1` 环境变量控制，skipif 默认跳过
- [x] M7.7 `openspec validate agent-center-thread-runtime-refactor --strict` 通过

### 第六轮已完成
- [x] M4.6 移除 UI 层 ad-hoc context 提取
- [x] M6.1 前端 UI 文案统一：对话/会话 → 线程/工作线程（10处）
- [x] M6.2 左侧栏已按线程展示
- [x] M6.4 新建线程按钮已实现
- [x] M6.6 Memory candidates 显示为线程注解

### 前几轮已完成
- [x] M3.6 Export run markdown with thread/message context
- [x] M4.5 Tests for refreshed thread reconstructing pending slots
- [x] M5.6 Tests for memory candidates not splitting thread context
- [x] M5.3 memory_extract step 显式绑定 thread_id + run_id
- [x] M2.5 force_new_thread 提升为一级参数
- [x] M7.1 显式新建线程后端测试（3 个新测试）
- [x] M2.3/M2.4/M3.4/M4.1/M4.3/M4.4/M5.4 前几轮已完成
- [x] M0.1-M0.6, M1.1-M1.3, M3.1-M3.3/M3.5, M4.2, M5.1/M5.2/M5.5, M6.3/M6.5, M7.2-M7.4/M7.6/M7.8

## 已改重点文件
| 文件 | 变更摘要 |
|------|---------|
| `backend/app/services/agent/service.py` | 8处事务隔离修复 + 移除"外部访问"文案 + 线程标题自动生成 + SessionManager 移除 + force_new_thread 参数化 |
| `backend/app/services/agent/thread_manager.py` | thread runtime 重构 + build_thread_context + append_message 双写 AgentSession |
| `backend/app/services/agent/runtime/tools.py` | CONFIRMATION_RISK_LEVELS = {write,delete,costly} |
| `backend/app/services/agent/skill_templates.py` | 移除"外部访问必须确认"误导指示 |
| `backend/app/services/agent/runtime/planner.py` | 术语"会话→对话" |
| `backend/app/services/agent/memory/manager.py` | save_memory 支持 thread_id/run_id/message_ids + status 字段 |
| `backend/app/db/models/agent.py` | AgentMemory 新增 thread_id/run_id/message_ids + status 字段 |
| `backend/app/api/v1/agent.py` | 术语统一、双写 agent_messages、context snapshot 重建 API、export thread/message 章节 |
| `backend/tests/test_agent_center.py` | fixture 新增 AIConnector 表 + 新增 M4.5/M5.6/M7.1 测试 |
| `backend/tests/test_frontend_smoke.py` | 新建：patchright 浏览器烟雾测试（M7.5） |
| `backend/alembic/versions/018_add_agent_memories_status_column.py` | 新增 status 列 |
| `backend/alembic/versions/019_backfill_threads_and_messages.py` | 新建：agent_sessions → agent_threads/agent_messages 回填 |
| `frontend/src/pages/agent/index.tsx` | 术语统一、移除外部访问文案、trace 紧凑展示、ad-hoc context 移除、线程注解区域 |
| `openspec/changes/agent-center-thread-runtime-refactor/tasks.md` | 全 63 项标记完成 |

## 验证结果
- `pytest tests/test_agent_center.py`：68 passed
- `pytest tests/test_character_*.py`：21 passed
- `pytest tests/test_creative_project_service.py`：16 passed
- **合计：105 passed，0 failed**
- `frontend npx tsc --noEmit`：通过
- `openspec validate`：通过
- 数据库迁移：Alembic 已升级到 head（020），远程 PostgreSQL @ 81.70.219.37
- 迁移 019：agent_sessions → agent_threads/agent_messages 回填已执行
- 迁移 020：identity_json visual_profile 回填已执行（1 个角色）

---

## 总体进度概览

| Change | 完成率 |
|---|---|
| agent-center-hermes-mvp | 100% |
| agent-center-multi-agent-runtime | 100% |
| creative-novel-writer-room | 100% |
| agent-center-thread-runtime-refactor | 100% |
| creative-character-portrait-system | 100% |
| drop-legacy-assets-final | 100% |
| task-observability-diagnostics | 96% (1 残留) |
| creative-project-optimization-roadmap | 77% (8 残留) |
| creative-project-closed-loop | 61% (22 残留) |

## 剩余未完成（可离线推进）
| Change | 任务数 |
|--------|--------|
| creative-project-optimization-roadmap | 8 |
| creative-project-closed-loop | 22 |

## 关键决策
1. thread_id 是长期上下文根，AgentSession/session_id 只保留兼容镜像
2. agent_messages 是短期上下文事实来源
3. 授权不再干扰普通搜索/外部读取；只拦截写入、删除、消耗型动作
4. trace 应在聊天框内顺序展示，最终回答后默认可折叠，类似 Codex
5. 不引入 DeerFlow/Hermes 依赖，只借鉴架构模式
6. `_build_failover_chain` 异常时不调用 session.rollback()，由外层 chat() 统一管理事务
7. 所有 DB 写操作统一 begin_nested() + SQLAlchemyError 隔离
8. ThreadManager.append_message 是唯一消息写入入口，自动双写 AgentSession.messages（向后兼容）

---

# 2026-07-05 下半场 — Creative Character Portrait System（第八轮）

## 当前进度：55/57 done = 96%（原 52→55）

### 第八轮新增完成
- [x] 1.4 创建 Alembic migration 020
  - `020_backfill_character_visual_profile.py`：为已有角色回填 `identity_json.visual_profile`
  - 仅处理有 appearance/costume_hint 但无 visual_profile 的角色，确保向前兼容
  - 幂等设计：`identity_json -> 'visual_profile' IS NULL` 条件 + `||` JSONB 合并
- [x] 4.5 快速生成立绘路径已保留
  - `buildCharacterPortraitPrompt()` 作为轻量一键生图路径被显式标注保留
  - `buildVisualProfileOverride()` 桥接表单字段 → visual_profile → 后端，无需完整 visual card
  - 前端双路径均有文档注释说明保留原因
- [x] 5.13 添加 prompt 注入和 lineage 元数据测试
  - `test_character_prompt_injection.py`（7 个新测试）：
    1. `test_storyboard_prompt_injects_character_profiles` — 验证分镜面板注入了角色外貌/服装/标志物/OOC规则
    2. `test_storyboard_negative_prompt_not_overwritten` — 已有 negative_prompt 不被覆盖
    3. `test_outline_character_fallback` — 无 production profile 时回退到大纲角色数据
    4. `test_character_portrait_builds_lineage_metadata_structure` — 验证 lineage dict 结构契约
    5. `test_storyboard_panel_tracks_lineage_ids` — 验证 character_ids/portrait_node_ids/reference_asset_ids
    6. `test_portrait_prompt_bundle_includes_version_lineage` — prompt_template_version 追踪
    7. `test_enhanced_prompt_preserves_original_image_prompt` — 原始 prompt 作为前缀保留

## 新增/修改文件
| 文件 | 变更 |
|------|------|
| `backend/alembic/versions/020_backfill_character_visual_profile.py` | 新建：identity_json visual_profile 回填迁移 |
| `backend/tests/test_character_prompt_injection.py` | 新建：prompt 注入和 lineage 元数据 7 个测试 |
| `frontend/src/pages/characters/index.tsx` | 添加快速生成路径保留文档注释 |
| `openspec/changes/creative-character-portrait-system/tasks.md` | 1.4/4.5/5.13 标记完成 |

## 剩余未完成（2/57）
| 任务 | 说明 |
|------|------|
| 6.4 | 验证生成的立绘版本在 Asset Hub 可见并可选择为主版本（需 Docker/运行后端） |
| 6.7 | 验证 3x3 立绘网格生成 9 个子图片资产并保留源版本 lineage（需 Docker/运行后端） |

## 验证结果
- `pytest tests/test_character_prompt_injection.py`：7 passed
- `frontend npx tsc --noEmit`：通过
