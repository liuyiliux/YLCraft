# YLCraft API Surface

> Route facts are generated from `backend/app/main.py` and FastAPI router decorators.
> Update with: `python tools/generate_api_surface.py`, then manually review semantic/module impact.
> Do not hand-edit generated endpoint tables unless the generator cannot represent a route.

## Summary

- Router mounts: 52
- Endpoints: 624
- Public schema endpoints: 623
- Hidden compatibility endpoints: 1

## Router Mounts

| Prefix | Tags | Router | Source |
| --- | --- | --- | --- |
| `` | Novel Sources | `novel_sources` | `backend/app/api/v1/novel_sources.py` |
| `/api/v1` | Tags | `tags` | `backend/app/api/v1/tags.py` |
| `/api/v1` | Search | `search` | `backend/app/api/v1/search.py` |
| `/api/v1` | Lineage | `lineage` | `backend/app/api/v1/lineage.py` |
| `/api/v1` | Models | `models` | `backend/app/api/v1/models.py` |
| `/api/v1` | 3D Models | `model3d` | `backend/app/api/v1/model3d.py` |
| `/api/v1` | JianYing | `jianying` | `backend/app/api/v1/jianying.py` |
| `/api/v1` | Export | `export` | `backend/app/api/v1/export.py` |
| `/api/v1` | Cookie Acquisition | `cookie_acquisition` | `backend/app/api/v1/cookie_acquisition.py` |
| `/api/v1/agent` | Agent | `agent` | `backend/app/api/v1/agent.py` |
| `/api/v1/ai` | AI Capabilities | `ai_capabilities` | `backend/app/api/v1/ai_capabilities.py` |
| `/api/v1/ai/connectors` | AI Connectors | `ai_connectors` | `backend/app/api/v1/ai_connectors.py` |
| `/api/v1/asset-hub` | Asset Hub | `asset_hub` | `backend/app/api/v1/asset_hub.py` |
| `/api/v1/assets` | Assets | `assets` | `backend/app/api/v1/assets.py` |
| `/api/v1/bgm` | BGM | `bgm` | `backend/app/api/v1/bgm.py` |
| `/api/v1/bilibili` | Crawler — Bilibili | `bilibili` | `backend/app/services/platforms/bilibili/routes.py` |
| `/api/v1/book-sources` | Book Sources | `book_sources` | `backend/app/api/v1/book_sources.py` |
| `/api/v1/breaker` | Breaker | `breaker` | `backend/app/api/v1/breaker.py` |
| `/api/v1/canvas` | Creative Canvas | `canvas` | `backend/app/api/v1/canvas.py` |
| `/api/v1/characters` | Characters | `characters` | `backend/app/api/v1/characters.py` |
| `/api/v1/clip` | Clip — NarratoAI / MoE | `clip` | `backend/app/api/v1/clip.py` |
| `/api/v1/clip-ops` | Clip Operations | `clip_ops` | `backend/app/api/v1/clip_ops.py` |
| `/api/v1/clip/cutclaw` | Clip — CutClaw | `cutclaw` | `backend/app/api/v1/cutclaw.py` |
| `/api/v1/comfyui` | ComfyUI | `comfyui` | `backend/app/api/v1/comfyui.py` |
| `/api/v1/crawler` | Crawler | `crawler` | `backend/app/api/v1/crawler.py` |
| `/api/v1/creative-projects` | Creative Projects | `creative_projects` | `backend/app/api/v1/creative_projects.py` |
| `/api/v1/creative-projects` | Creative Projects — Fanqie | `creative_fanqie` | `backend/app/api/v1/creative_fanqie.py` |
| `/api/v1/download` | Download | `download` | `backend/app/api/v1/download.py` |
| `/api/v1/ebook` | Ebook | `ebook` | `backend/app/api/v1/ebook.py` |
| `/api/v1/external-api-keys` | External API Keys | `external_api_keys` | `backend/app/api/v1/external_api_keys.py` |
| `/api/v1/image-editor` | Image Editor | `image_editor` | `backend/app/api/v1/image_editor.py` |
| `/api/v1/image-prompts` | Image Prompt References | `image_prompts` | `backend/app/api/v1/image_prompts.py` |
| `/api/v1/images` | Images | `images` | `backend/app/api/v1/images.py` |
| `/api/v1/live2d` | Live2D Factory | `live2d` | `backend/app/api/v1/live2d.py` |
| `/api/v1/llm` | LLM | `llm` | `backend/app/api/v1/llm.py` |
| `/api/v1/logs` | Logs | `logs` | `backend/app/api/v1/logs.py` |
| `/api/v1/model-3d` | Image to 3D | `model3d_workspace` | `backend/app/api/v1/model3d_workspace.py` |
| `/api/v1/novels` | Novels | `novels` | `backend/app/api/v1/novels.py` |
| `/api/v1/platforms` | Platform Connections | `platforms` | `backend/app/api/v1/platforms.py` |
| `/api/v1/previs` | 3D Director Previs | `previs` | `backend/app/api/v1/previs.py` |
| `/api/v1/proxy` | Proxy | `proxy` | `backend/app/api/v1/proxy.py` |
| `/api/v1/reader` | Reader | `reader` | `backend/app/api/v1/reader.py` |
| `/api/v1/rule-assistant` | Rule Assistant | `rule_assistant` | `backend/app/api/v1/rule_assistant.py` |
| `/api/v1/settings` | Settings | `settings` | `backend/app/api/v1/settings.py` |
| `/api/v1/story` | Story Maker | `story` | `backend/app/api/v1/story.py` |
| `/api/v1/subtitles` | Subtitles | `subtitles` | `backend/app/api/v1/subtitles.py` |
| `/api/v1/tasks` | Tasks | `tasks` | `backend/app/api/v1/tasks.py` |
| `/api/v1/torrents` | Torrents | `torrents` | `backend/app/api/v1/torrents.py` |
| `/api/v1/tts` | TTS | `tts` | `backend/app/api/v1/tts.py` |
| `/api/v1/videos` | Videos | `videos` | `backend/app/api/v1/videos.py` |
| `/api/v1/wechat-mp` | Wechat MP | `wechat_mp` | `backend/app/api/v1/wechat_mp.py` |
| `/api/v1/ws` | WebSocket | `ws` | `backend/app/api/v1/ws.py` |

## Endpoints

### 3D Director Previs

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/previs/scenes` | List previs scenes | `list_previs_scenes` | `backend/app/api/v1/previs.py:81` |
| `POST` | `/api/v1/previs/scenes` | Create previs scene | `create_previs_scene` | `backend/app/api/v1/previs.py:99` |
| `GET` | `/api/v1/previs/scenes/{scene_id}` | Get previs scene | `get_previs_scene` | `backend/app/api/v1/previs.py:135` |
| `PUT` | `/api/v1/previs/scenes/{scene_id}` | Save previs scene with revision check | `save_previs_scene` | `backend/app/api/v1/previs.py:144` |
| `DELETE` | `/api/v1/previs/scenes/{scene_id}` | Delete previs scene | `delete_previs_scene` | `backend/app/api/v1/previs.py:181` |

### 3D Models

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/3d/convert` | - | `convert_3d_format` | `backend/app/api/v1/model3d.py:116` |
| `POST` | `/api/v1/3d/extract-metadata` | - | `extract_3d_metadata` | `backend/app/api/v1/model3d.py:66` |
| `POST` | `/api/v1/3d/generate-from-image` | - | `generate_3d_from_image` | `backend/app/api/v1/model3d.py:144` |
| `GET` | `/api/v1/3d/generate-from-image/{task_id}` | - | `get_3d_generation_status` | `backend/app/api/v1/model3d.py:168` |
| `POST` | `/api/v1/3d/generate-preview` | - | `generate_3d_preview` | `backend/app/api/v1/model3d.py:88` |
| `GET` | `/api/v1/3d/supported-formats` | - | `get_supported_formats` | `backend/app/api/v1/model3d.py:190` |

### AI Capabilities

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/ai/capabilities` | 获取 AI 能力列表 | `list_ai_capabilities` | `backend/app/api/v1/ai_capabilities.py:139` |

### AI Connectors

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/ai/connectors` | 列出所有 AI 连接 | `list_connectors` | `backend/app/api/v1/ai_connectors.py:153` |
| `POST` | `/api/v1/ai/connectors` | 创建 AI 连接 | `create_connector` | `backend/app/api/v1/ai_connectors.py:1070` |
| `GET` | `/api/v1/ai/connectors/discover-models` | 发现可用模型 | `discover_models` | `backend/app/api/v1/ai_connectors.py:930` |
| `GET` | `/api/v1/ai/connectors/export` | 导出所有 AI 连接为 JSON | `export_connectors` | `backend/app/api/v1/ai_connectors.py:202` |
| `POST` | `/api/v1/ai/connectors/import` | 从 JSON 导入 AI 连接 | `import_connectors` | `backend/app/api/v1/ai_connectors.py:277` |
| `GET` | `/api/v1/ai/connectors/provider-metadata` | 获取所有 Provider 元数据 | `list_providers` | `backend/app/api/v1/ai_connectors.py:449` |
| `POST` | `/api/v1/ai/connectors/provider-metadata` | 创建 Provider 元数据 | `create_provider` | `backend/app/api/v1/ai_connectors.py:496` |
| `POST` | `/api/v1/ai/connectors/provider-metadata/init` | 初始化默认 Provider 数据 | `init_default_providers` | `backend/app/api/v1/ai_connectors.py:715` |
| `GET` | `/api/v1/ai/connectors/provider-metadata/{provider_id}` | 获取单个 Provider 元数据 | `get_provider` | `backend/app/api/v1/ai_connectors.py:473` |
| `PUT` | `/api/v1/ai/connectors/provider-metadata/{provider_id}` | 更新 Provider 元数据 | `update_provider` | `backend/app/api/v1/ai_connectors.py:549` |
| `DELETE` | `/api/v1/ai/connectors/provider-metadata/{provider_id}` | 删除 Provider 元数据 | `delete_provider` | `backend/app/api/v1/ai_connectors.py:606` |
| `GET` | `/api/v1/ai/connectors/provider-metadata/{provider_id}/defaults/{provider_type}` | 获取指定类型的默认配置 | `get_provider_defaults` | `backend/app/api/v1/ai_connectors.py:635` |
| `POST` | `/api/v1/ai/connectors/reload` | 重新加载所有 AI 连接器配置，立即生效，无需重启 | `reload_connectors` | `backend/app/api/v1/ai_connectors.py:183` |
| `GET` | `/api/v1/ai/connectors/supported` | 获取支持的 AI 提供商 | `get_supported_ai_providers` | `backend/app/api/v1/ai_connectors.py:144` |
| `GET` | `/api/v1/ai/connectors/{conn_id}` | 获取连接详情 | `get_connector` | `backend/app/api/v1/ai_connectors.py:1055` |
| `PUT` | `/api/v1/ai/connectors/{conn_id}` | 更新 AI 连接 | `update_connector` | `backend/app/api/v1/ai_connectors.py:1090` |
| `DELETE` | `/api/v1/ai/connectors/{conn_id}` | 删除 AI 连接 | `delete_connector` | `backend/app/api/v1/ai_connectors.py:1110` |
| `POST` | `/api/v1/ai/connectors/{conn_id}/test` | 测试连接 | `test_connector` | `backend/app/api/v1/ai_connectors.py:1130` |
| `GET` | `/api/v1/ai/connectors/{conn_id}/usage` | 获取使用统计 | `get_usage_stats` | `backend/app/api/v1/ai_connectors.py:1147` |
| `POST` | `/api/v1/ai/connectors/{conn_id}/use` | 标记为已使用 | `mark_used` | `backend/app/api/v1/ai_connectors.py:1166` |

### Agent

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/agent/chat` | Agent 对话 | `chat` | `backend/app/api/v1/agent.py:154` |
| `GET` | `/api/v1/agent/memories` | 获取记忆 | `get_memories` | `backend/app/api/v1/agent.py:1462` |
| `POST` | `/api/v1/agent/memories` | 保存记忆 | `save_memory` | `backend/app/api/v1/agent.py:1496` |
| `GET` | `/api/v1/agent/memories/view` | 获取 Hermes 风格记忆视图 | `get_memory_view` | `backend/app/api/v1/agent.py:1488` |
| `DELETE` | `/api/v1/agent/memories/{key}` | 删除记忆 | `delete_memory` | `backend/app/api/v1/agent.py:1523` |
| `POST` | `/api/v1/agent/multi-agent/scene-simulation` | 多智能体场景推演 | `run_scene_simulation` | `backend/app/api/v1/agent.py:2020` |
| `GET` | `/api/v1/agent/profiles` | 智能体配置列表 | `list_profiles` | `backend/app/api/v1/agent.py:200` |
| `POST` | `/api/v1/agent/profiles` | 创建智能体配置 | `create_profile` | `backend/app/api/v1/agent.py:209` |
| `PUT` | `/api/v1/agent/profiles/{profile_id}` | 更新智能体配置 | `update_profile` | `backend/app/api/v1/agent.py:222` |
| `GET` | `/api/v1/agent/runs` | Agent 运行记录 | `list_runs` | `backend/app/api/v1/agent.py:716` |
| `GET` | `/api/v1/agent/runs/{run_id}` | Agent 运行详情 | `get_run_detail` | `backend/app/api/v1/agent.py:734` |
| `POST` | `/api/v1/agent/runs/{run_id}/cancel` | 取消 Agent 运行 | `cancel_run` | `backend/app/api/v1/agent.py:918` |
| `GET` | `/api/v1/agent/runs/{run_id}/context-snapshot` | 获取 Run 上下文快照 | `get_context_snapshot` | `backend/app/api/v1/agent.py:1038` |
| `POST` | `/api/v1/agent/runs/{run_id}/context-snapshot` | 重建 Run 上下文快照 | `reconstruct_context_snapshot` | `backend/app/api/v1/agent.py:949` |
| `POST` | `/api/v1/agent/runs/{run_id}/continue` | 继续 Agent 运行 | `continue_run` | `backend/app/api/v1/agent.py:1068` |
| `POST` | `/api/v1/agent/runs/{run_id}/delegate` | 委派 Agent 子任务 | `delegate_run` | `backend/app/api/v1/agent.py:1276` |
| `GET` | `/api/v1/agent/runs/{run_id}/delegations` | 获取 Agent Run 的子任务委派记录 | `get_run_delegations` | `backend/app/api/v1/agent.py:748` |
| `GET` | `/api/v1/agent/runs/{run_id}/export.md` | 导出 Agent Run Markdown | `export_run_markdown` | `backend/app/api/v1/agent.py:892` |
| `GET` | `/api/v1/agent/runs/{run_id}/linked-logs` | Agent Run 关联日志 | `get_run_linked_logs` | `backend/app/api/v1/agent.py:847` |
| `GET` | `/api/v1/agent/runs/{run_id}/memory-snapshot` | 获取 Agent Run 记忆快照 | `get_run_memory_snapshot` | `backend/app/api/v1/agent.py:861` |
| `POST` | `/api/v1/agent/runs/{run_id}/retry` | 重试 Agent 失败步骤 | `retry_run_step` | `backend/app/api/v1/agent.py:1094` |
| `GET` | `/api/v1/agent/runs/{run_id}/skill-candidate` | 分析 Run 是否适合沉淀为 Skill | `inspect_run_skill_candidate` | `backend/app/api/v1/agent.py:820` |
| `POST` | `/api/v1/agent/runs/{run_id}/skill-draft` | 从 Run 生成待审批 Skill 草稿 | `create_skill_draft_from_run` | `backend/app/api/v1/agent.py:831` |
| `POST` | `/api/v1/agent/runs/{run_id}/steps/{step_id}/confirm` | 确认并执行 pending 工具步骤 | `confirm_pending_step` | `backend/app/api/v1/agent.py:1174` |
| `POST` | `/api/v1/agent/runs/{run_id}/steps/{step_id}/memory-candidates/discard` | 丢弃待确认记忆 | `discard_memory_candidates` | `backend/app/api/v1/agent.py:1596` |
| `POST` | `/api/v1/agent/runs/{run_id}/steps/{step_id}/memory-candidates/save` | 保存待确认记忆 | `save_memory_candidates` | `backend/app/api/v1/agent.py:1531` |
| `GET` | `/api/v1/agent/runs/{run_id}/tree` | 获取 Agent Run 执行树 | `get_run_tree` | `backend/app/api/v1/agent.py:768` |
| `POST` | `/api/v1/agent/send` | 发送到 Agent | `send_to_agent` | `backend/app/api/v1/agent.py:1987` |
| `GET` | `/api/v1/agent/sessions` | 对话列表 | `list_sessions` | `backend/app/api/v1/agent.py:238` |
| `GET` | `/api/v1/agent/sessions/{session_id}` | 会话详情 | `get_session_detail` | `backend/app/api/v1/agent.py:1319` |
| `DELETE` | `/api/v1/agent/sessions/{session_id}` | 删除对话 | `delete_session` | `backend/app/api/v1/agent.py:1360` |
| `GET` | `/api/v1/agent/skills` | 技能列表 | `list_skills` | `backend/app/api/v1/agent.py:1623` |
| `POST` | `/api/v1/agent/skills` | 创建技能 | `create_skill` | `backend/app/api/v1/agent.py:1974` |
| `POST` | `/api/v1/agent/skills/bundles` | 创建用户 Skill Bundle | `create_skill_bundle` | `backend/app/api/v1/agent.py:1686` |
| `PUT` | `/api/v1/agent/skills/bundles/{bundle_name}` | 更新用户 Skill Bundle | `update_skill_bundle` | `backend/app/api/v1/agent.py:1691` |
| `DELETE` | `/api/v1/agent/skills/bundles/{bundle_name}` | 删除用户 Skill Bundle | `delete_skill_bundle` | `backend/app/api/v1/agent.py:1699` |
| `GET` | `/api/v1/agent/skills/drafts` | Skill 待审批草稿列表 | `list_skill_drafts` | `backend/app/api/v1/agent.py:1835` |
| `POST` | `/api/v1/agent/skills/drafts` | 创建 Skill 草稿 | `create_skill_draft` | `backend/app/api/v1/agent.py:1847` |
| `POST` | `/api/v1/agent/skills/drafts/import-url` | 从 URL 导入 Skill 草稿 | `import_skill_draft_url` | `backend/app/api/v1/agent.py:1868` |
| `GET` | `/api/v1/agent/skills/drafts/{draft_id}` | 读取 Skill 草稿 | `get_skill_draft` | `backend/app/api/v1/agent.py:1888` |
| `POST` | `/api/v1/agent/skills/drafts/{draft_id}/approve` | 批准并启用 Skill 草稿 | `approve_skill_draft` | `backend/app/api/v1/agent.py:1902` |
| `POST` | `/api/v1/agent/skills/drafts/{draft_id}/reject` | 拒绝 Skill 草稿 | `reject_skill_draft` | `backend/app/api/v1/agent.py:1917` |
| `GET` | `/api/v1/agent/skills/package-index` | 文件化 Skill 包索引 | `list_skill_package_index` | `backend/app/api/v1/agent.py:1645` |
| `GET` | `/api/v1/agent/skills/packages/{skill_name}/files` | Skill 包文件列表 | `list_skill_package_files` | `backend/app/api/v1/agent.py:1655` |
| `GET` | `/api/v1/agent/skills/packages/{skill_name}/files/content` | 读取 Skill 包文件 | `read_skill_package_file` | `backend/app/api/v1/agent.py:1669` |
| `POST` | `/api/v1/agent/skills/route-preview` | Skill 路由预览 | `preview_skill_route` | `backend/app/api/v1/agent.py:1933` |
| `GET` | `/api/v1/agent/threads` | Agent Thread 列表 | `list_threads` | `backend/app/api/v1/agent.py:255` |
| `GET` | `/api/v1/agent/threads/{thread_id}` | Agent Thread 详情 | `get_thread_detail` | `backend/app/api/v1/agent.py:1337` |
| `DELETE` | `/api/v1/agent/threads/{thread_id}` | 删除 Agent Thread | `delete_thread` | `backend/app/api/v1/agent.py:1370` |
| `GET` | `/api/v1/agent/tools` | 可用工具列表 | `list_tools` | `backend/app/api/v1/agent.py:1381` |
| `POST` | `/api/v1/agent/tools/test` | 测试 Agent 工具调用 | `run_tool_test` | `backend/app/api/v1/agent.py:1402` |

### Asset Hub

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/asset-hub/nodes` | 资产节点列表 | `list_nodes` | `backend/app/api/v1/asset_hub.py:237` |
| `POST` | `/api/v1/asset-hub/nodes` | 创建资产节点 | `create_node` | `backend/app/api/v1/asset_hub.py:281` |
| `GET` | `/api/v1/asset-hub/nodes/{node_id}` | 资产节点详情 | `get_node` | `backend/app/api/v1/asset_hub.py:305` |
| `PUT` | `/api/v1/asset-hub/nodes/{node_id}` | 更新资产节点 | `update_node` | `backend/app/api/v1/asset_hub.py:318` |
| `DELETE` | `/api/v1/asset-hub/nodes/{node_id}` | 删除资产节点 | `delete_node` | `backend/app/api/v1/asset_hub.py:340` |
| `GET` | `/api/v1/asset-hub/nodes/{node_id}/children` | 子节点列表 | `list_node_children` | `backend/app/api/v1/asset_hub.py:353` |
| `POST` | `/api/v1/asset-hub/nodes/{node_id}/tags` | 批量添加标签 | `add_node_tags` | `backend/app/api/v1/asset_hub.py:367` |
| `GET` | `/api/v1/asset-hub/nodes/{node_id}/versions` | 资产版本列表 | `list_versions` | `backend/app/api/v1/asset_hub.py:390` |
| `POST` | `/api/v1/asset-hub/nodes/{node_id}/versions` | 创建资产版本 | `create_version` | `backend/app/api/v1/asset_hub.py:414` |
| `DELETE` | `/api/v1/asset-hub/representations/{rep_id}` | 删除文件表示 | `delete_representation` | `backend/app/api/v1/asset_hub.py:522` |
| `POST` | `/api/v1/asset-hub/seed-tags` | 初始化默认标签树 | `seed_default_tags` | `backend/app/api/v1/asset_hub.py:578` |
| `GET` | `/api/v1/asset-hub/stats/type-counts` | 按类型统计 | `get_type_counts` | `backend/app/api/v1/asset_hub.py:537` |
| `GET` | `/api/v1/asset-hub/types` | 所有资产类型 | `list_asset_types` | `backend/app/api/v1/asset_hub.py:228` |
| `GET` | `/api/v1/asset-hub/versions/{version_id}` | 版本详情 | `get_version` | `backend/app/api/v1/asset_hub.py:439` |
| `DELETE` | `/api/v1/asset-hub/versions/{version_id}` | 删除版本 | `delete_version` | `backend/app/api/v1/asset_hub.py:454` |
| `GET` | `/api/v1/asset-hub/versions/{version_id}/representations` | 版本文件列表 | `list_representations` | `backend/app/api/v1/asset_hub.py:477` |
| `POST` | `/api/v1/asset-hub/versions/{version_id}/representations` | 创建文件表示 | `create_representation` | `backend/app/api/v1/asset_hub.py:494` |

### Assets

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/assets` | 素材资产列表 | `list_assets` | `backend/app/api/v1/assets.py:681` |
| `GET` | `/api/v1/assets/download` | 下载/预览本地文件 | `download_local_asset_file` | `backend/app/api/v1/assets.py:846` |
| `GET` | `/api/v1/assets/file` | 预览本地文件 | `download_local_asset_file` | `backend/app/api/v1/assets.py:846` |
| `GET` | `/api/v1/assets/tags` | 标签列表 | `list_tags` | `backend/app/api/v1/assets.py:1459` |
| `POST` | `/api/v1/assets/tags` | 创建标签 | `create_tag` | `backend/app/api/v1/assets.py:1468` |
| `POST` | `/api/v1/assets/upload` | 本地上传素材入库 | `upload_asset` | `backend/app/api/v1/assets.py:1205` |
| `POST` | `/api/v1/assets/upload-model3d` | 上传 3D 模型（ZIP 或单文件）入库 | `upload_model3d` | `backend/app/api/v1/assets.py:1161` |
| `DELETE` | `/api/v1/assets/versions/{version_id}` | 删除单个资产版本 | `delete_asset_version` | `backend/app/api/v1/assets.py:1669` |
| `GET` | `/api/v1/assets/{asset_id}` | 资产详情 | `get_asset` | `backend/app/api/v1/assets.py:1607` |
| `PUT` | `/api/v1/assets/{asset_id}` | 更新资产 | `update_asset` | `backend/app/api/v1/assets.py:1630` |
| `DELETE` | `/api/v1/assets/{asset_id}` | 删除资产 | `delete_asset` | `backend/app/api/v1/assets.py:1729` |
| `GET` | `/api/v1/assets/{asset_id}/course-episodes/{episode_index}/download` | 下载课程章节文件 | `download_course_episode_asset` | `backend/app/api/v1/assets.py:1425` |
| `GET` | `/api/v1/assets/{asset_id}/course-episodes/{episode_index}/sidecars/danmaku` | 读取课程章节弹幕 | `get_course_episode_danmaku` | `backend/app/api/v1/assets.py:1414` |
| `GET` | `/api/v1/assets/{asset_id}/course-episodes/{episode_index}/sidecars/subtitles/{subtitle_index}.vtt` | 读取课程章节字幕 | `get_course_episode_subtitle` | `backend/app/api/v1/assets.py:1402` |
| `GET` | `/api/v1/assets/{asset_id}/course-episodes/{episode_index}/stream` | 播放课程章节文件 | `stream_course_episode_asset` | `backend/app/api/v1/assets.py:1440` |
| `POST` | `/api/v1/assets/{asset_id}/deep-watermark-detect` | 只读检测合成水印痕迹（CtrlRegen/SynthID，不修改文件） | `detect_asset_deep_watermark` | `backend/app/api/v1/assets.py:978` |
| `GET` | `/api/v1/assets/{asset_id}/download` | 下载资产文件 | `download_asset` | `backend/app/api/v1/assets.py:863` |
| `GET` | `/api/v1/assets/{asset_id}/files/{filename:path}` | 下载/预览资产的配套文件 | `asset_sidecar_file` | `backend/app/api/v1/assets.py:880` |
| `POST` | `/api/v1/assets/{asset_id}/provenance-clean` | 审计或清理 AI 来源标记与文件元数据 | `clean_asset_provenance` | `backend/app/api/v1/assets.py:908` |
| `POST` | `/api/v1/assets/{asset_id}/restore` | 恢复软删除的资产 | `restore_asset` | `backend/app/api/v1/assets.py:1745` |
| `GET` | `/api/v1/assets/{asset_id}/sidecars/danmaku` | 读取资产弹幕 | `get_asset_danmaku` | `backend/app/api/v1/assets.py:1390` |
| `GET` | `/api/v1/assets/{asset_id}/sidecars/subtitles/{subtitle_index}.vtt` | 读取资产字幕 | `get_asset_subtitle` | `backend/app/api/v1/assets.py:1377` |
| `GET` | `/api/v1/assets/{asset_id}/stream` | 播放资产视频文件 | `stream_asset` | `backend/app/api/v1/assets.py:1249` |
| `GET` | `/api/v1/assets/{asset_id}/thumbnail` | 代理加载封面图 | `proxy_thumbnail` | `backend/app/api/v1/assets.py:1572` |
| `POST` | `/api/v1/assets/{asset_id}/thumbnail` | 设置资产缩略图 | `set_asset_thumbnail` | `backend/app/api/v1/assets.py:1549` |
| `POST` | `/api/v1/assets/{asset_id}/watermark-remove` | 去除显性可见水印并生成派生副本（图片/视频，不覆盖原文件） | `remove_asset_visual_watermark` | `backend/app/api/v1/assets.py:1015` |

### BGM

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/bgm/genres` | 风格分类列表 | `list_genres` | `backend/app/api/v1/bgm.py:181` |
| `GET` | `/api/v1/bgm/library` | BGM 曲目库列表 | `list_bgm_library` | `backend/app/api/v1/bgm.py:164` |
| `POST` | `/api/v1/bgm/mix` | 将 BGM 混音到视频 | `mix_bgm` | `backend/app/api/v1/bgm.py:240` |
| `GET` | `/api/v1/bgm/moods` | 情绪分类列表 | `list_moods` | `backend/app/api/v1/bgm.py:186` |
| `GET` | `/api/v1/bgm/tasks/{task_id}` | 查询混音任务状态 | `get_mix_task` | `backend/app/api/v1/bgm.py:191` |
| `POST` | `/api/v1/bgm/upload` | 上传自定义 BGM | `upload_bgm` | `backend/app/api/v1/bgm.py:199` |
| `GET` | `/api/v1/bgm/{track_id}` | 曲目详情 | `get_bgm_track` | `backend/app/api/v1/bgm.py:315` |
| `DELETE` | `/api/v1/bgm/{track_id}` | 删除自定义曲目 | `delete_bgm_track` | `backend/app/api/v1/bgm.py:324` |
| `PATCH` | `/api/v1/bgm/{track_id}/favorite` | 切换收藏状态 | `toggle_favorite` | `backend/app/api/v1/bgm.py:304` |
| `GET` | `/api/v1/bgm/{track_id}/file` | 获取 BGM 音频文件 | `get_bgm_file` | `backend/app/api/v1/bgm.py:283` |

### Book Sources

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` `hidden` | `/api/v1/book-sources` | - | `list_book_sources` | `backend/app/api/v1/book_sources.py:119` |
| `GET` | `/api/v1/book-sources` | - | `list_book_sources` | `backend/app/api/v1/book_sources.py:119` |
| `POST` | `/api/v1/book-sources/batch-delete` | - | `batch_delete_book_sources` | `backend/app/api/v1/book_sources.py:485` |
| `POST` | `/api/v1/book-sources/batch-toggle` | - | `batch_toggle_book_sources` | `backend/app/api/v1/book_sources.py:501` |
| `DELETE` | `/api/v1/book-sources/browser-sessions/{session_id}` | - | `close_book_source_browser_session` | `backend/app/api/v1/book_sources.py:439` |
| `POST` | `/api/v1/book-sources/browser-sessions/{session_id}/snapshot` | - | `snapshot_book_source_browser_session` | `backend/app/api/v1/book_sources.py:420` |
| `GET` | `/api/v1/book-sources/export` | - | `export_book_sources` | `backend/app/api/v1/book_sources.py:451` |
| `POST` | `/api/v1/book-sources/import` | - | `import_book_sources` | `backend/app/api/v1/book_sources.py:135` |
| `POST` | `/api/v1/book-sources/import-json` | - | `import_book_sources_json` | `backend/app/api/v1/book_sources.py:161` |
| `POST` | `/api/v1/book-sources/rules/convert` | - | `convert_book_source_rules` | `backend/app/api/v1/book_sources.py:253` |
| `GET` | `/api/v1/book-sources/search` | - | `search_books` | `backend/app/api/v1/book_sources.py:517` |
| `DELETE` | `/api/v1/book-sources/{source_id}` | - | `delete_book_source` | `backend/app/api/v1/book_sources.py:205` |
| `POST` | `/api/v1/book-sources/{source_id}/browser-session/start` | - | `start_book_source_browser_session` | `backend/app/api/v1/book_sources.py:394` |
| `GET` | `/api/v1/book-sources/{source_id}/cookies` | - | `list_book_source_cookies` | `backend/app/api/v1/book_sources.py:281` |
| `POST` | `/api/v1/book-sources/{source_id}/cookies` | - | `create_book_source_cookie` | `backend/app/api/v1/book_sources.py:292` |
| `PUT` | `/api/v1/book-sources/{source_id}/cookies/{cookie_id}` | - | `update_book_source_cookie` | `backend/app/api/v1/book_sources.py:309` |
| `DELETE` | `/api/v1/book-sources/{source_id}/cookies/{cookie_id}` | - | `delete_book_source_cookie` | `backend/app/api/v1/book_sources.py:324` |
| `PUT` | `/api/v1/book-sources/{source_id}/headers` | - | `update_book_source_headers` | `backend/app/api/v1/book_sources.py:265` |
| `GET` | `/api/v1/book-sources/{source_id}/rules` | - | `get_book_source_rules` | `backend/app/api/v1/book_sources.py:225` |
| `PUT` | `/api/v1/book-sources/{source_id}/rules` | - | `update_book_source_rules` | `backend/app/api/v1/book_sources.py:237` |
| `GET` | `/api/v1/book-sources/{source_id}/test` | - | `test_book_source` | `backend/app/api/v1/book_sources.py:337` |
| `POST` | `/api/v1/book-sources/{source_id}/test` | - | `test_book_source_with_rules` | `backend/app/api/v1/book_sources.py:366` |
| `PUT` | `/api/v1/book-sources/{source_id}/toggle` | - | `toggle_book_source` | `backend/app/api/v1/book_sources.py:183` |

### Breaker

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/breaker/analyze` | 创建拆解任务 | `analyze` | `backend/app/api/v1/breaker.py:46` |
| `POST` | `/api/v1/breaker/preview` | 预览小红书图文笔记 | `preview_xhs_note` | `backend/app/api/v1/breaker.py:135` |
| `GET` | `/api/v1/breaker/tasks/{task_id}` | 查询任务状态 | `get_task_status` | `backend/app/api/v1/breaker.py:72` |
| `GET` | `/api/v1/breaker/tasks/{task_id}/result` | 获取拆解结果 | `get_result` | `backend/app/api/v1/breaker.py:93` |

### Characters

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/characters` | 列出角色 | `list_characters` | `backend/app/api/v1/characters.py:235` |
| `POST` | `/api/v1/characters` | 创建角色 | `create_character` | `backend/app/api/v1/characters.py:279` |
| `GET` | `/api/v1/characters/duplicate-candidates` | 查询角色重复候选 | `get_duplicate_candidates` | `backend/app/api/v1/characters.py:382` |
| `GET` | `/api/v1/characters/meta/extract-origins` | 获取角色提取来源元数据 | `get_extract_origins` | `backend/app/api/v1/characters.py:368` |
| `GET` | `/api/v1/characters/meta/roles` | 获取角色定位元数据 | `get_roles` | `backend/app/api/v1/characters.py:343` |
| `GET` | `/api/v1/characters/meta/source-types` | 获取来源类型元数据 | `get_source_types` | `backend/app/api/v1/characters.py:331` |
| `GET` | `/api/v1/characters/meta/workflow-sources` | 获取角色流程来源元数据 | `get_workflow_sources` | `backend/app/api/v1/characters.py:357` |
| `GET` | `/api/v1/characters/relationships/graph` | 获取角色关系图谱 | `get_character_relationship_graph` | `backend/app/api/v1/characters.py:589` |
| `GET` | `/api/v1/characters/tags/all` | 获取所有自定义标签 | `get_all_character_tags` | `backend/app/api/v1/characters.py:322` |
| `GET` | `/api/v1/characters/{character_id}` | 获取角色详情 | `get_character` | `backend/app/api/v1/characters.py:736` |
| `PUT` | `/api/v1/characters/{character_id}` | 更新角色 | `update_character` | `backend/app/api/v1/characters.py:750` |
| `DELETE` | `/api/v1/characters/{character_id}` | 删除角色 | `delete_character` | `backend/app/api/v1/characters.py:797` |
| `POST` | `/api/v1/characters/{character_id}/enrich` | AI 补全角色信息 | `enrich_character` | `backend/app/api/v1/characters.py:1571` |
| `POST` | `/api/v1/characters/{character_id}/favorite` | 切换收藏状态 | `toggle_favorite` | `backend/app/api/v1/characters.py:423` |
| `POST` | `/api/v1/characters/{character_id}/link-story` | 关联到故事项目 | `link_story` | `backend/app/api/v1/characters.py:438` |
| `POST` | `/api/v1/characters/{character_id}/portrait/generate` | AI 生成角色立绘（资产中枢版） | `generate_character_portrait` | `backend/app/api/v1/characters.py:1731` |
| `POST` | `/api/v1/characters/{character_id}/portrait/prompt-preview` | 预览角色立绘提示词 | `preview_character_portrait_prompt` | `backend/app/api/v1/characters.py:941` |
| `GET` | `/api/v1/characters/{character_id}/portrait/slices` | 列出角色立绘九宫格切片子素材 | `list_character_portrait_slices` | `backend/app/api/v1/characters.py:1187` |
| `POST` | `/api/v1/characters/{character_id}/portrait/upgrade` | 将现有立绘升级到资产中枢 | `upgrade_portrait_to_asset_hub` | `backend/app/api/v1/characters.py:2055` |
| `GET` | `/api/v1/characters/{character_id}/portrait/versions` | 列出角色立绘版本 | `list_character_portrait_versions` | `backend/app/api/v1/characters.py:968` |
| `POST` | `/api/v1/characters/{character_id}/portrait/versions/{version_id}/set-main` | 设置角色主立绘版本 | `set_character_main_portrait_version` | `backend/app/api/v1/characters.py:1076` |
| `POST` | `/api/v1/characters/{character_id}/portrait/versions/{version_id}/slice-grid` | 将九宫格立绘版本切成可复用子素材 | `slice_character_portrait_grid` | `backend/app/api/v1/characters.py:1279` |
| `GET` | `/api/v1/characters/{character_id}/prompt-pack` | 生成角色 Prompt 资产包 | `get_character_prompt_pack` | `backend/app/api/v1/characters.py:726` |
| `GET` | `/api/v1/characters/{character_id}/relationships` | 列出角色关系 | `list_character_relationships` | `backend/app/api/v1/characters.py:632` |
| `POST` | `/api/v1/characters/{character_id}/relationships` | 创建角色关系 | `create_character_relationship` | `backend/app/api/v1/characters.py:693` |
| `PUT` | `/api/v1/characters/{character_id}/relationships/{relationship_id}` | 更新角色关系 | `update_character_relationship` | `backend/app/api/v1/characters.py:704` |
| `DELETE` | `/api/v1/characters/{character_id}/relationships/{relationship_id}` | 删除角色关系 | `delete_character_relationship` | `backend/app/api/v1/characters.py:717` |
| `GET` | `/api/v1/characters/{character_id}/state-timeline` | 获取角色在剧情中的状态变化轨迹 | `get_character_state_timeline` | `backend/app/api/v1/characters.py:506` |
| `POST` | `/api/v1/characters/{character_id}/tags` | 添加自定义标签 | `add_character_tag` | `backend/app/api/v1/characters.py:401` |
| `DELETE` | `/api/v1/characters/{character_id}/tags/{tag}` | 移除自定义标签 | `remove_character_tag` | `backend/app/api/v1/characters.py:412` |
| `GET` | `/api/v1/characters/{character_id}/world-usages` | 列出角色在不同世界/项目中的使用 | `list_character_world_usages` | `backend/app/api/v1/characters.py:466` |
| `PUT` | `/api/v1/characters/{character_id}/world-usages/{usage_id}` | 更新角色世界使用配置 | `update_character_world_usage` | `backend/app/api/v1/characters.py:476` |
| `DELETE` | `/api/v1/characters/{character_id}/world-usages/{usage_id}` | 移除角色世界使用关系 | `delete_character_world_usage` | `backend/app/api/v1/characters.py:493` |

### Clip Operations

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/clip-ops/audio` | 添加音频 | `add_audio` | `backend/app/api/v1/clip_ops.py:198` |
| `POST` | `/api/v1/clip-ops/concat` | 合并视频 | `concat_videos` | `backend/app/api/v1/clip_ops.py:135` |
| `POST` | `/api/v1/clip-ops/extract-audio` | 提取音频 | `extract_audio` | `backend/app/api/v1/clip_ops.py:293` |
| `GET` | `/api/v1/clip-ops/info/{video_path:path}` | 获取视频信息 | `get_video_info` | `backend/app/api/v1/clip_ops.py:83` |
| `POST` | `/api/v1/clip-ops/resize` | 调整分辨率 | `resize_video` | `backend/app/api/v1/clip_ops.py:262` |
| `POST` | `/api/v1/clip-ops/subtitle` | 添加字幕 | `add_subtitles` | `backend/app/api/v1/clip_ops.py:165` |
| `POST` | `/api/v1/clip-ops/thumbnail` | 生成缩略图 | `create_thumbnail` | `backend/app/api/v1/clip_ops.py:320` |
| `POST` | `/api/v1/clip-ops/trim` | 裁剪视频 | `trim_video` | `backend/app/api/v1/clip_ops.py:104` |
| `POST` | `/api/v1/clip-ops/upload` | 上传视频文件 | `upload_video` | `backend/app/api/v1/clip_ops.py:349` |
| `POST` | `/api/v1/clip-ops/watermark` | 添加水印 | `add_watermark` | `backend/app/api/v1/clip_ops.py:229` |

### Clip — CutClaw

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/clip/cutclaw` | CutClaw Agent 视频剪辑 | `cutclaw_clip` | `backend/app/api/v1/cutclaw.py:59` |
| `GET` | `/api/v1/clip/cutclaw/{task_id}` | 查询 CutClaw Agent 任务状态 | `get_cutclaw_task_status` | `backend/app/api/v1/cutclaw.py:99` |

### Clip — NarratoAI / MoE

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/clip/download` | 下载剪辑结果视频 | `download_clip_result` | `backend/app/api/v1/clip.py:172` |
| `POST` | `/api/v1/clip/moe` | MoE 多专家协作剪辑 | `moe_clip` | `backend/app/api/v1/clip.py:121` |
| `POST` | `/api/v1/clip/narrato` | NarratoAI Pipeline 剪辑 | `narrato_clip` | `backend/app/api/v1/clip.py:78` |
| `GET` | `/api/v1/clip/tasks/{task_id}` | 查询 Clip Lab 任务状态 | `get_clip_task_status` | `backend/app/api/v1/clip.py:156` |

### ComfyUI

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/comfyui/controlnets` | 获取可用 ControlNet 列表 | `get_controlnets` | `backend/app/api/v1/comfyui.py:268` |
| `POST` | `/api/v1/comfyui/generate` | 生成图像 | `generate_image` | `backend/app/api/v1/comfyui.py:854` |
| `POST` | `/api/v1/comfyui/interrupt` | 中断当前任务 | `interrupt` | `backend/app/api/v1/comfyui.py:345` |
| `GET` | `/api/v1/comfyui/loras` | 获取可用 LoRA 列表 | `get_loras` | `backend/app/api/v1/comfyui.py:243` |
| `GET` | `/api/v1/comfyui/models` | 获取可用模型列表 | `get_models` | `backend/app/api/v1/comfyui.py:218` |
| `GET` | `/api/v1/comfyui/nodes` | 列出节点 | `list_nodes` | `backend/app/api/v1/comfyui.py:774` |
| `POST` | `/api/v1/comfyui/nodes` | 添加节点 | `create_node` | `backend/app/api/v1/comfyui.py:781` |
| `DELETE` | `/api/v1/comfyui/nodes/{node_id}` | 删除节点 | `delete_node` | `backend/app/api/v1/comfyui.py:808` |
| `PUT` | `/api/v1/comfyui/nodes/{node_id}/default` | 设为默认节点 | `set_default_node` | `backend/app/api/v1/comfyui.py:799` |
| `GET` | `/api/v1/comfyui/presets` | 列出预设 | `list_presets` | `backend/app/api/v1/comfyui.py:639` |
| `POST` | `/api/v1/comfyui/presets` | 创建预设 | `create_preset` | `backend/app/api/v1/comfyui.py:658` |
| `GET` | `/api/v1/comfyui/presets/{preset_id}` | 获取预设 | `get_preset` | `backend/app/api/v1/comfyui.py:649` |
| `DELETE` | `/api/v1/comfyui/presets/{preset_id}` | 删除预设 | `delete_preset` | `backend/app/api/v1/comfyui.py:677` |
| `GET` | `/api/v1/comfyui/progress` | 获取当前进度 | `get_progress` | `backend/app/api/v1/comfyui.py:297` |
| `GET` | `/api/v1/comfyui/queue` | 获取队列状态 | `get_queue` | `backend/app/api/v1/comfyui.py:323` |
| `DELETE` | `/api/v1/comfyui/queue/{prompt_id}` | 从队列删除任务 | `delete_from_queue` | `backend/app/api/v1/comfyui.py:364` |
| `GET` | `/api/v1/comfyui/tasks` | 列出任务 | `list_tasks` | `backend/app/api/v1/comfyui.py:690` |
| `POST` | `/api/v1/comfyui/tasks` | 创建任务 | `create_task` | `backend/app/api/v1/comfyui.py:728` |
| `GET` | `/api/v1/comfyui/tasks/stats` | 获取统计 | `get_task_stats` | `backend/app/api/v1/comfyui.py:712` |
| `GET` | `/api/v1/comfyui/tasks/{prompt_id}` | 获取任务 | `get_task` | `backend/app/api/v1/comfyui.py:719` |
| `DELETE` | `/api/v1/comfyui/tasks/{prompt_id}` | 取消任务 | `cancel_task` | `backend/app/api/v1/comfyui.py:751` |
| `GET` | `/api/v1/comfyui/templates` | 列出模板 | `list_templates` | `backend/app/api/v1/comfyui.py:565` |
| `POST` | `/api/v1/comfyui/templates` | 创建模板 | `create_template` | `backend/app/api/v1/comfyui.py:594` |
| `GET` | `/api/v1/comfyui/templates/{template_id}` | 获取模板 | `get_template` | `backend/app/api/v1/comfyui.py:585` |
| `PUT` | `/api/v1/comfyui/templates/{template_id}` | 更新模板 | `update_template` | `backend/app/api/v1/comfyui.py:613` |
| `DELETE` | `/api/v1/comfyui/templates/{template_id}` | 删除模板 | `delete_template` | `backend/app/api/v1/comfyui.py:626` |
| `GET` | `/api/v1/comfyui/workflows` | 列出可用工作流 | `list_workflows` | `backend/app/api/v1/comfyui.py:105` |
| `POST` | `/api/v1/comfyui/workflows` | 保存工作流 | `save_workflow` | `backend/app/api/v1/comfyui.py:162` |
| `GET` | `/api/v1/comfyui/workflows/{name}` | 获取工作流 | `get_workflow` | `backend/app/api/v1/comfyui.py:138` |
| `DELETE` | `/api/v1/comfyui/workflows/{name}` | 删除工作流 | `delete_workflow` | `backend/app/api/v1/comfyui.py:184` |
| `WEBSOCKET` | `/api/v1/comfyui/ws/progress` | - | `websocket_progress` | `backend/app/api/v1/comfyui.py:446` |

### Cookie Acquisition

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/playwright/sessions` | 列出活跃的 Patchright 会话 | `playwright_list_sessions` | `backend/app/api/v1/cookie_acquisition.py:137` |
| `POST` | `/api/v1/playwright/start` | 启动浏览器获取 Cookie（使用 Patchright） | `playwright_start` | `backend/app/api/v1/cookie_acquisition.py:92` |
| `POST` | `/api/v1/playwright/{session_id}/cancel` | 取消 Patchright 会话 | `playwright_cancel` | `backend/app/api/v1/cookie_acquisition.py:159` |
| `WEBSOCKET` | `/api/v1/playwright/{session_id}/ws` | - | `playwright_ws` | `backend/app/api/v1/cookie_acquisition.py:169` |
| `POST` | `/api/v1/qrcode/generate` | 生成登录二维码 | `qrcode_generate` | `backend/app/api/v1/cookie_acquisition.py:229` |
| `POST` | `/api/v1/qrcode/{session_id}/refresh` | 刷新过期二维码 | `qrcode_refresh` | `backend/app/api/v1/cookie_acquisition.py:290` |
| `GET` | `/api/v1/qrcode/{session_id}/status` | 轮询扫码状态 | `qrcode_status` | `backend/app/api/v1/cookie_acquisition.py:271` |
| `WEBSOCKET` | `/api/v1/qrcode/{session_id}/ws` | - | `qrcode_ws` | `backend/app/api/v1/cookie_acquisition.py:306` |

### Crawler

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/crawler/fetch-no-watermark` | 批量获取无水印资源 | `fetch_no_watermark` | `backend/app/api/v1/crawler.py:365` |
| `POST` | `/api/v1/crawler/import` | 导入到素材库 | `import_to_assets` | `backend/app/api/v1/crawler.py:194` |
| `GET` | `/api/v1/crawler/note-detail` | 获取笔记详情（无水印） | `get_note_detail` | `backend/app/api/v1/crawler.py:292` |
| `GET` | `/api/v1/crawler/options` | 获取采集配置选项 | `get_options` | `backend/app/api/v1/crawler.py:155` |
| `GET` | `/api/v1/crawler/platforms` | 获取支持的平台列表 | `get_platforms` | `backend/app/api/v1/crawler.py:149` |
| `POST` | `/api/v1/crawler/search` | 搜索视频/图文素材 | `search_materials` | `backend/app/api/v1/crawler.py:164` |
| `POST` | `/api/v1/crawler/search-enhanced` | 增强搜索（支持笔记/用户） | `search_enhanced` | `backend/app/api/v1/crawler.py:238` |
| `GET` | `/api/v1/crawler/tasks/{task_id}` | 查询采集任务状态 | `get_task_status` | `backend/app/api/v1/crawler.py:223` |

### Crawler — Bilibili

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/bilibili/comment/send` | 发送B站评论 | `send_comment` | `backend/app/services/platforms/bilibili/routes.py:716` |
| `GET` | `/api/v1/bilibili/comments` | 获取B站评论 | `get_comments` | `backend/app/services/platforms/bilibili/routes.py:585` |
| `GET` | `/api/v1/bilibili/danmaku` | 获取B站弹幕 | `get_danmaku` | `backend/app/services/platforms/bilibili/routes.py:532` |
| `GET` | `/api/v1/bilibili/favorites` | 获取我的收藏夹列表 | `get_favorite_list` | `backend/app/services/platforms/bilibili/routes.py:949` |
| `GET` | `/api/v1/bilibili/favorites/{media_id}` | 获取收藏夹详情 | `get_favorite_detail` | `backend/app/services/platforms/bilibili/routes.py:1006` |
| `GET` | `/api/v1/bilibili/followings` | 获取关注列表 | `get_followings` | `backend/app/services/platforms/bilibili/routes.py:1191` |
| `GET` | `/api/v1/bilibili/history` | 获取历史观看记录（游标浏览） | `get_watch_history` | `backend/app/services/platforms/bilibili/routes.py:1099` |
| `GET` | `/api/v1/bilibili/history/search` | 搜索历史观看记录（时间筛选） | `search_watch_history` | `backend/app/services/platforms/bilibili/routes.py:1141` |
| `GET` | `/api/v1/bilibili/login-health` | B站登录态体检 | `check_login_health` | `backend/app/services/platforms/bilibili/routes.py:391` |
| `GET` | `/api/v1/bilibili/paid-course/detail` | 获取付费课程详情和章节列表 | `get_paid_course_detail` | `backend/app/services/platforms/bilibili/routes.py:1500` |
| `GET` | `/api/v1/bilibili/paid-course/download` | 下载付费课程章节 | `download_paid_course_episode` | `backend/app/services/platforms/bilibili/routes.py:1624` |
| `POST` | `/api/v1/bilibili/paid-course/download-task` | 创建付费课程章节下载任务 | `create_paid_course_download_task` | `backend/app/services/platforms/bilibili/routes.py:1573` |
| `GET` | `/api/v1/bilibili/paid-course/download-task/{task_id}` | 查询付费课程章节下载任务 | `get_paid_course_download_task` | `backend/app/services/platforms/bilibili/routes.py:1613` |
| `GET` | `/api/v1/bilibili/paid-course/playurl` | 获取付费课程视频播放地址 | `get_paid_course_playurl` | `backend/app/services/platforms/bilibili/routes.py:1539` |
| `GET` | `/api/v1/bilibili/paid-courses` | 获取付费课程列表 | `get_paid_courses` | `backend/app/services/platforms/bilibili/routes.py:1463` |
| `GET` | `/api/v1/bilibili/series/{series_id}` | 获取合集详情 | `get_series_detail` | `backend/app/services/platforms/bilibili/routes.py:1035` |
| `GET` | `/api/v1/bilibili/stats` | 获取B站作品数据 | `get_stats` | `backend/app/services/platforms/bilibili/routes.py:556` |
| `GET` | `/api/v1/bilibili/subtitle/download` | 下载B站字幕文件 | `download_subtitle` | `backend/app/services/platforms/bilibili/routes.py:641` |
| `GET` | `/api/v1/bilibili/subtitles` | 获取B站字幕 | `get_subtitles` | `backend/app/services/platforms/bilibili/routes.py:618` |
| `GET` | `/api/v1/bilibili/up/profile` | 获取UP主信息 | `get_up_profile` | `backend/app/services/platforms/bilibili/routes.py:758` |
| `GET` | `/api/v1/bilibili/up/ranking` | 获取UP主热门视频排行 | `get_up_ranking` | `backend/app/services/platforms/bilibili/routes.py:898` |
| `GET` | `/api/v1/bilibili/up/series` | 获取UP主合集列表 | `get_up_series` | `backend/app/services/platforms/bilibili/routes.py:871` |
| `GET` | `/api/v1/bilibili/up/videos` | 获取UP主视频列表 | `get_up_videos` | `backend/app/services/platforms/bilibili/routes.py:812` |
| `GET` | `/api/v1/bilibili/up/{uid}/favorites` | 获取UP主公开收藏夹列表 | `get_up_favorite_list` | `backend/app/services/platforms/bilibili/routes.py:980` |
| `GET` | `/api/v1/bilibili/video/info` | 获取B站视频信息 | `get_video_info` | `backend/app/services/platforms/bilibili/routes.py:693` |

### Creative Canvas

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/canvas/assets/image` | Save processed canvas image to Asset Hub | `save_canvas_image_asset` | `backend/app/api/v1/canvas.py:341` |
| `GET` | `/api/v1/canvas/documents` | List canvas documents | `list_canvas_documents` | `backend/app/api/v1/canvas.py:247` |
| `POST` | `/api/v1/canvas/documents` | Create canvas document | `create_canvas_document` | `backend/app/api/v1/canvas.py:263` |
| `GET` | `/api/v1/canvas/documents/{document_id}` | Get canvas document | `get_canvas_document` | `backend/app/api/v1/canvas.py:287` |
| `PUT` | `/api/v1/canvas/documents/{document_id}` | Save canvas document | `save_canvas_document` | `backend/app/api/v1/canvas.py:296` |
| `DELETE` | `/api/v1/canvas/documents/{document_id}` | Delete canvas document | `delete_canvas_document` | `backend/app/api/v1/canvas.py:331` |

### Creative Projects

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/creative-projects` | 列出创作项目 | `list_projects` | `backend/app/api/v1/creative_projects.py:604` |
| `POST` | `/api/v1/creative-projects` | 创建创作项目 | `create_project` | `backend/app/api/v1/creative_projects.py:627` |
| `POST` | `/api/v1/creative-projects/from-novel` | 从小说章节创建创作项目 | `create_from_novel` | `backend/app/api/v1/creative_projects.py:662` |
| `GET` | `/api/v1/creative-projects/logs/generation` | 跨项目查询生成日志 | `list_generation_logs_global` | `backend/app/api/v1/creative_projects.py:1467` |
| `GET` | `/api/v1/creative-projects/profiles` | 列出内容生产方案 | `list_production_profiles` | `backend/app/api/v1/creative_projects.py:646` |
| `GET` | `/api/v1/creative-projects/{project_id}` | 获取创作项目详情 | `get_project` | `backend/app/api/v1/creative_projects.py:706` |
| `PATCH` | `/api/v1/creative-projects/{project_id}` | 更新创作项目 | `update_project` | `backend/app/api/v1/creative_projects.py:984` |
| `DELETE` | `/api/v1/creative-projects/{project_id}` | 删除创作项目 | `delete_project` | `backend/app/api/v1/creative_projects.py:1000` |
| `GET` | `/api/v1/creative-projects/{project_id}/assets` | 列出项目素材关联 | `list_project_assets` | `backend/app/api/v1/creative_projects.py:1428` |
| `POST` | `/api/v1/creative-projects/{project_id}/assets` | 关联项目素材 | `link_project_asset` | `backend/app/api/v1/creative_projects.py:1502` |
| `GET` | `/api/v1/creative-projects/{project_id}/canvas` | 获取项目画布状态 | `get_canvas` | `backend/app/api/v1/creative_projects.py:1551` |
| `PUT` | `/api/v1/creative-projects/{project_id}/canvas` | 保存项目画布状态 | `save_canvas` | `backend/app/api/v1/creative_projects.py:1562` |
| `POST` | `/api/v1/creative-projects/{project_id}/chapters/{chapter_number}/check-continuity` | 跨章连续性检查（对比已锁定事实） | `check_continuity` | `backend/app/api/v1/creative_projects.py:1858` |
| `PUT` | `/api/v1/creative-projects/{project_id}/content-package` | 保存项目内容包版本 | `save_content_package` | `backend/app/api/v1/creative_projects.py:1364` |
| `POST` | `/api/v1/creative-projects/{project_id}/content-package/plan` | 一次生成项目内容包 | `plan_content_package` | `backend/app/api/v1/creative_projects.py:1381` |
| `GET` | `/api/v1/creative-projects/{project_id}/contents` | 列出项目阶段内容 | `list_contents` | `backend/app/api/v1/creative_projects.py:1313` |
| `PATCH` | `/api/v1/creative-projects/{project_id}/contents/{content_id}` | 保存项目阶段内容 | `update_content` | `backend/app/api/v1/creative_projects.py:1343` |
| `POST` | `/api/v1/creative-projects/{project_id}/contents/{content_id}/aftermath` | 从正式正文建立叙事后处理状态 | `run_narrative_aftermath` | `backend/app/api/v1/creative_projects.py:832` |
| `POST` | `/api/v1/creative-projects/{project_id}/contents/{content_id}/continuity-candidates/extract` | 从正文提取/入库结构化连续性候选 | `extract_continuity_candidates` | `backend/app/api/v1/creative_projects.py:1751` |
| `POST` | `/api/v1/creative-projects/{project_id}/contents/{content_id}/extract-continuity` | 从正文提取连续性候选卡 | `extract_continuity_candidates` | `backend/app/api/v1/creative_projects.py:1042` |
| `POST` | `/api/v1/creative-projects/{project_id}/contents/{content_id}/rewrite-paragraph` | 段落级非破坏性重写（生成候选版本） | `rewrite_paragraph` | `backend/app/api/v1/creative_projects.py:1879` |
| `POST` | `/api/v1/creative-projects/{project_id}/contents/{content_id}/save-as-asset` | 保存项目文本为素材 | `save_project_content_as_asset` | `backend/app/api/v1/creative_projects.py:1522` |
| `GET` | `/api/v1/creative-projects/{project_id}/continuity-candidates` | 列出连续性候选事实 | `list_continuity_candidates` | `backend/app/api/v1/creative_projects.py:1725` |
| `GET` | `/api/v1/creative-projects/{project_id}/continuity-candidates/context-summary` | 连续性事实上下文摘要（不进模型硬约束） | `continuity_context_summary` | `backend/app/api/v1/creative_projects.py:1840` |
| `POST` | `/api/v1/creative-projects/{project_id}/continuity-candidates/{candidate_id}/accept` | 确认候选事实，写入 locked project_bible / world_asset | `accept_continuity_candidate` | `backend/app/api/v1/creative_projects.py:1776` |
| `POST` | `/api/v1/creative-projects/{project_id}/continuity-candidates/{candidate_id}/ignore` | 忽略候选事实 | `ignore_continuity_candidate` | `backend/app/api/v1/creative_projects.py:1796` |
| `POST` | `/api/v1/creative-projects/{project_id}/continuity-candidates/{candidate_id}/merge` | 合并候选事实到已有 project_bible / world_asset | `merge_continuity_candidate` | `backend/app/api/v1/creative_projects.py:1816` |
| `GET` | `/api/v1/creative-projects/{project_id}/export` | 导出创作项目 ZIP | `export_project_zip` | `backend/app/api/v1/creative_projects.py:953` |
| `POST` | `/api/v1/creative-projects/{project_id}/extract-characters` | 两趟提取项目/小说角色 | `extract_project_characters` | `backend/app/api/v1/creative_projects.py:681` |
| `POST` | `/api/v1/creative-projects/{project_id}/fill-demo-data` | 为创作项目补充示例大纲、正文、脚本和分镜 | `fill_demo_data` | `backend/app/api/v1/creative_projects.py:1012` |
| `GET` | `/api/v1/creative-projects/{project_id}/foreshadowing` | 列出项目伏笔台账 | `list_foreshadowing` | `backend/app/api/v1/creative_projects.py:869` |
| `POST` | `/api/v1/creative-projects/{project_id}/foreshadowing/{item_id}/{action}` | 确认、推进、解决或忽略伏笔 | `decide_foreshadowing` | `backend/app/api/v1/creative_projects.py:887` |
| `POST` | `/api/v1/creative-projects/{project_id}/generate-chapter-outline` | 生成单话细纲 | `generate_chapter_outline` | `backend/app/api/v1/creative_projects.py:1135` |
| `POST` | `/api/v1/creative-projects/{project_id}/generate-chapter-plan` | 生成章节规划 | `generate_chapter_plan` | `backend/app/api/v1/creative_projects.py:1073` |
| `POST` | `/api/v1/creative-projects/{project_id}/generate-novel-body` | 生成章节正文 | `generate_novel_body` | `backend/app/api/v1/creative_projects.py:1153` |
| `POST` | `/api/v1/creative-projects/{project_id}/generate-outline` | 生成故事大纲 | `generate_outline` | `backend/app/api/v1/creative_projects.py:1055` |
| `POST` | `/api/v1/creative-projects/{project_id}/generate-script` | 生成短剧脚本 | `generate_script` | `backend/app/api/v1/creative_projects.py:1118` |
| `POST` | `/api/v1/creative-projects/{project_id}/generate-storyboard` | 生成分镜草稿 | `generate_storyboard` | `backend/app/api/v1/creative_projects.py:1276` |
| `GET` | `/api/v1/creative-projects/{project_id}/generation-logs` | 列出项目生成日志 | `list_generation_logs` | `backend/app/api/v1/creative_projects.py:1439` |
| `POST` | `/api/v1/creative-projects/{project_id}/match-reference-assets` | AI 匹配脚本/分镜参考卡 | `match_reference_assets` | `backend/app/api/v1/creative_projects.py:1295` |
| `GET` | `/api/v1/creative-projects/{project_id}/narrative-graph` | 查询项目叙事关系图谱 | `get_narrative_graph` | `backend/app/api/v1/creative_projects.py:910` |
| `PUT` | `/api/v1/creative-projects/{project_id}/narrative/autopilot` | 配置并启动受控叙事自动推进 | `configure_narrative_autopilot` | `backend/app/api/v1/creative_projects.py:515` |
| `GET` | `/api/v1/creative-projects/{project_id}/narrative/context-preview` | 预览下一章叙事上下文包 | `preview_narrative_context` | `backend/app/api/v1/creative_projects.py:760` |
| `GET` | `/api/v1/creative-projects/{project_id}/narrative/health` | 检查小说叙事数据健康状态 | `get_narrative_health` | `backend/app/api/v1/creative_projects.py:749` |
| `POST` | `/api/v1/creative-projects/{project_id}/narrative/rebuild` | 按正式章节顺序重建叙事状态 | `rebuild_narrative_state` | `backend/app/api/v1/creative_projects.py:851` |
| `GET` | `/api/v1/creative-projects/{project_id}/narrative/runs` | 列出项目叙事运行记录 | `list_narrative_runs` | `backend/app/api/v1/creative_projects.py:473` |
| `POST` | `/api/v1/creative-projects/{project_id}/narrative/runs` | 创建后台叙事批次运行 | `create_narrative_batch_run` | `backend/app/api/v1/creative_projects.py:490` |
| `POST` | `/api/v1/creative-projects/{project_id}/narrative/runs/{run_id}/{action}` | 控制叙事批次运行 | `control_narrative_run` | `backend/app/api/v1/creative_projects.py:547` |
| `GET` | `/api/v1/creative-projects/{project_id}/production-plan` | 读取创作导演生产计划 | `get_production_plan` | `backend/app/api/v1/creative_projects.py:717` |
| `PUT` | `/api/v1/creative-projects/{project_id}/production-plan` | 保存创作导演生产计划新版本 | `save_production_plan` | `backend/app/api/v1/creative_projects.py:732` |
| `POST` | `/api/v1/creative-projects/{project_id}/refine-novel-body` | 按中文要求微调章节正文 | `refine_novel_body` | `backend/app/api/v1/creative_projects.py:1171` |
| `POST` | `/api/v1/creative-projects/{project_id}/regenerate-chapter-outline-scenes` | 只重生成单话细纲场景 | `regenerate_chapter_outline_scenes` | `backend/app/api/v1/creative_projects.py:1409` |
| `POST` | `/api/v1/creative-projects/{project_id}/run-pipeline` | Run creative project production pipeline | `run_pipeline` | `backend/app/api/v1/creative_projects.py:1091` |
| `POST` | `/api/v1/creative-projects/{project_id}/split-comic-pages` | 拆分漫画页 | `split_comic_pages` | `backend/app/api/v1/creative_projects.py:1253` |
| `GET` | `/api/v1/creative-projects/{project_id}/state` | 查看项目动态状态当前值 | `get_project_state` | `backend/app/api/v1/creative_projects.py:775` |
| `GET` | `/api/v1/creative-projects/{project_id}/state/timeline` | 查看项目动态状态按章变化轨迹 | `get_project_state_timeline` | `backend/app/api/v1/creative_projects.py:787` |
| `POST` | `/api/v1/creative-projects/{project_id}/sync-characters` | 同步大纲角色到角色库 | `sync_project_characters` | `backend/app/api/v1/creative_projects.py:1534` |
| `POST` | `/api/v1/creative-projects/{project_id}/sync-project-bible` | 从故事大纲同步项目圣经和世界资产 | `sync_project_bible` | `backend/app/api/v1/creative_projects.py:1029` |
| `POST` | `/api/v1/creative-projects/{project_id}/writer-room/promote` | Promote writer-room prose to latest novel body | `promote_writer_room_content` | `backend/app/api/v1/creative_projects.py:1235` |
| `POST` | `/api/v1/creative-projects/{project_id}/writer-room/run` | Run selected novel writer-room steps | `run_writer_room` | `backend/app/api/v1/creative_projects.py:1206` |
| `POST` | `/api/v1/creative-projects/{project_id}/writer-room/step/{step}` | Run one novel writer-room step | `run_writer_room_step` | `backend/app/api/v1/creative_projects.py:1188` |
| `GET` | `/api/v1/creative-projects/{project_id}/writing-preflight` | 检查写作阶段前置条件 | `get_writing_preflight` | `backend/app/api/v1/creative_projects.py:815` |

### Creative Projects — Fanqie

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/creative-projects/{project_id}/fanqie/binding` | 读取项目番茄绑定 | `get_fanqie_binding` | `backend/app/api/v1/creative_fanqie.py:159` |
| `POST` | `/api/v1/creative-projects/{project_id}/fanqie/binding` | 设置项目番茄绑定 | `set_fanqie_binding` | `backend/app/api/v1/creative_fanqie.py:140` |
| `GET` | `/api/v1/creative-projects/{project_id}/fanqie/publish-preflight` | 预检番茄章节发布 | `preview_fanqie_publish` | `backend/app/api/v1/creative_fanqie.py:168` |
| `GET` | `/api/v1/creative-projects/{project_id}/fanqie/publish-status` | 查询番茄发布记录 | `get_fanqie_publish_status` | `backend/app/api/v1/creative_fanqie.py:196` |
| `POST` | `/api/v1/creative-projects/{project_id}/publish-to-fanqie` | 保存章节到番茄草稿 | `publish_to_fanqie` | `backend/app/api/v1/creative_fanqie.py:87` |

### Download

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/download/cover-proxy` | 封面图代理（弃用，请使用 /api/v1/proxy/image） | `cover_proxy` | `backend/app/api/v1/download.py:1343` |
| `POST` | `/api/v1/download/download` | 通过 yt-dlp 下载视频（返回文件流） | `download_video` | `backend/app/api/v1/download.py:825` |
| `POST` | `/api/v1/download/open-folder` | 打开文件夹并选中文件（Windows） | `open_folder` | `backend/app/api/v1/download.py:1332` |
| `POST` | `/api/v1/download/parse` | 解析视频链接 | `parse_download_url` | `backend/app/api/v1/download.py:451` |
| `POST` | `/api/v1/download/tasks` | 创建下载任务（后台，后台轮询） | `create_download_task` | `backend/app/api/v1/download.py:1284` |
| `GET` | `/api/v1/download/tasks/{task_id}` | 查询下载任务状态 | `get_download_task` | `backend/app/api/v1/download.py:1308` |

### Ebook

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/ebook/download/{task_id}` | 下载生成的 EPUB 文件 | `download_ebook` | `backend/app/api/v1/ebook.py:91` |
| `POST` | `/api/v1/ebook/generate` | 生成 EPUB 电子书 | `generate_ebook` | `backend/app/api/v1/ebook.py:53` |
| `GET` | `/api/v1/ebook/tasks` | 列出所有生成任务 | `list_ebook_tasks` | `backend/app/api/v1/ebook.py:84` |
| `GET` | `/api/v1/ebook/tasks/{task_id}` | 查询生成任务 | `get_ebook_task` | `backend/app/api/v1/ebook.py:74` |

### Export

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/export/dataset` | - | `export_dataset` | `backend/app/api/v1/export.py:68` |
| `POST` | `/api/v1/export/duplicates` | - | `find_duplicates` | `backend/app/api/v1/export.py:141` |
| `POST` | `/api/v1/export/merge` | - | `merge_duplicates` | `backend/app/api/v1/export.py:172` |
| `POST` | `/api/v1/export/quality` | - | `batch_calculate_quality` | `backend/app/api/v1/export.py:113` |
| `GET` | `/api/v1/export/quality/{asset_id}` | - | `calculate_quality_score` | `backend/app/api/v1/export.py:197` |
| `GET` | `/api/v1/export/stats` | - | `get_dataset_stats` | `backend/app/api/v1/export.py:97` |

### External API Keys

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/external-api-keys` | 列出外部 Agent API Key | `list_external_api_keys` | `backend/app/api/v1/external_api_keys.py:43` |
| `POST` | `/api/v1/external-api-keys` | 生成外部 Agent API Key | `create_external_api_key` | `backend/app/api/v1/external_api_keys.py:49` |
| `DELETE` | `/api/v1/external-api-keys/{key_id}` | 撤销外部 Agent API Key | `revoke_external_api_key` | `backend/app/api/v1/external_api_keys.py:68` |

### Image Editor

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/image-editor/watermark/image` | - | `add_image_watermark_api` | `backend/app/api/v1/image_editor.py:79` |
| `POST` | `/api/v1/image-editor/watermark/text` | - | `add_text_watermark_api` | `backend/app/api/v1/image_editor.py:16` |

### Image Prompt References

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/image-prompts/media/{source_id}/{item_id}/{filename}` | Read cached image prompt reference media | `read_image_prompt_reference_media` | `backend/app/api/v1/image_prompts.py:57` |
| `GET` | `/api/v1/image-prompts/references` | Search image prompt references | `search_image_prompt_references` | `backend/app/api/v1/image_prompts.py:71` |
| `POST` | `/api/v1/image-prompts/references` | Save a generated image prompt into the user prompt library | `create_user_image_prompt_reference` | `backend/app/api/v1/image_prompts.py:104` |
| `GET` | `/api/v1/image-prompts/references/{reference_id}` | Get image prompt reference detail | `get_image_prompt_reference` | `backend/app/api/v1/image_prompts.py:94` |
| `POST` | `/api/v1/image-prompts/references/{reference_id}/save-as-asset` | Save cached prompt reference image into Asset Hub | `save_image_prompt_reference_as_asset` | `backend/app/api/v1/image_prompts.py:115` |
| `GET` | `/api/v1/image-prompts/sources` | List image prompt reference sources | `list_image_prompt_sources` | `backend/app/api/v1/image_prompts.py:37` |
| `POST` | `/api/v1/image-prompts/sources/refresh` | Refresh image prompt reference sources | `refresh_image_prompt_sources` | `backend/app/api/v1/image_prompts.py:49` |

### Image to 3D

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/model-3d/backends` | Configured 3D connectors (generation / rigging) | `list_model3d_backends` | `backend/app/api/v1/model3d_workspace.py:253` |
| `POST` | `/api/v1/model-3d/generate` | Submit configured image-to-3D task | `generate_model3d` | `backend/app/api/v1/model3d_workspace.py:265` |
| `GET` | `/api/v1/model-3d/history` | Durable 3D workspace history | `model3d_history` | `backend/app/api/v1/model3d_workspace.py:381` |
| `POST` | `/api/v1/model-3d/rig` | Submit auto-rigging task (skeleton-only or preset motion) | `rig_model3d` | `backend/app/api/v1/model3d_workspace.py:455` |
| `GET` | `/api/v1/model-3d/tasks/{task_id}` | Poll image-to-3D task | `poll_model3d_task` | `backend/app/api/v1/model3d_workspace.py:337` |

### Images

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/images/backends` | 可用图像后端列表 | `list_backends` | `backend/app/api/v1/images.py:521` |
| `POST` | `/api/v1/images/generate` | 生成图片 | `generate_image` | `backend/app/api/v1/images.py:609` |
| `POST` | `/api/v1/images/generate-batch` | 批量生成多平台图片 | `batch_generate_endpoint` | `backend/app/api/v1/images.py:1608` |
| `POST` | `/api/v1/images/generate-batch/retry` | 单张图片重生成 | `batch_retry_endpoint` | `backend/app/api/v1/images.py:1543` |
| `POST` | `/api/v1/images/generate-batch/topics` | 多主题批量生成 | `batch_topics_generate_endpoint` | `backend/app/api/v1/images.py:1641` |
| `POST` | `/api/v1/images/generate-outline` | 多平台大纲生成 | `generate_outline_endpoint` | `backend/app/api/v1/images.py:1482` |
| `GET` | `/api/v1/images/platform-templates` | 可用平台/Prompt 模板列表 | `list_platform_templates` | `backend/app/api/v1/images.py:1360` |
| `POST` | `/api/v1/images/platform-templates` | 新增平台模板 | `create_platform_template` | `backend/app/api/v1/images.py:1391` |
| `PUT` | `/api/v1/images/platform-templates/{template_id}` | 更新平台模板 | `update_platform_template` | `backend/app/api/v1/images.py:1418` |
| `DELETE` | `/api/v1/images/platform-templates/{template_id}` | 删除平台模板 | `delete_platform_template` | `backend/app/api/v1/images.py:1455` |
| `GET` | `/api/v1/images/tasks/{task_id}` | 轮询图像生成任务 | `poll_image_task` | `backend/app/api/v1/images.py:903` |

### JianYing

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/jianying/export` | - | `export_jianying_draft` | `backend/app/api/v1/jianying.py:201` |
| `POST` | `/api/v1/jianying/extract` | - | `extract_jianying_materials` | `backend/app/api/v1/jianying.py:117` |
| `POST` | `/api/v1/jianying/import` | - | `import_jianying_draft` | `backend/app/api/v1/jianying.py:139` |
| `POST` | `/api/v1/jianying/import-upload` | - | `import_jianying_draft_upload` | `backend/app/api/v1/jianying.py:164` |
| `POST` | `/api/v1/jianying/parse` | - | `parse_jianying_draft` | `backend/app/api/v1/jianying.py:62` |
| `POST` | `/api/v1/jianying/parse-upload` | - | `parse_jianying_draft_upload` | `backend/app/api/v1/jianying.py:83` |
| `GET` | `/api/v1/jianying/supported-formats` | - | `get_supported_draft_formats` | `backend/app/api/v1/jianying.py:228` |

### LLM

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/llm/backends` | 获取可用的 LLM 后端列表 | `list_llm_backends` | `backend/app/api/v1/llm.py:93` |
| `POST` | `/api/v1/llm/chat` | LLM 对话 | `chat` | `backend/app/api/v1/llm.py:163` |

### Lineage

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/lineage/chain` | - | `create_prompt_model_output_chain` | `backend/app/api/v1/lineage.py:166` |
| `GET` | `/api/v1/lineage/common-ancestor` | - | `find_common_ancestor` | `backend/app/api/v1/lineage.py:203` |
| `POST` | `/api/v1/lineage/link` | - | `link_assets` | `backend/app/api/v1/lineage.py:127` |
| `DELETE` | `/api/v1/lineage/relation/{relation_id}` | - | `delete_relation` | `backend/app/api/v1/lineage.py:228` |
| `GET` | `/api/v1/lineage/{asset_id}` | - | `get_full_lineage` | `backend/app/api/v1/lineage.py:68` |
| `DELETE` | `/api/v1/lineage/{asset_id}` | - | `delete_all_relations` | `backend/app/api/v1/lineage.py:244` |
| `GET` | `/api/v1/lineage/{asset_id}/downstream` | - | `get_downstream_lineage` | `backend/app/api/v1/lineage.py:107` |
| `GET` | `/api/v1/lineage/{asset_id}/stats` | - | `get_lineage_stats` | `backend/app/api/v1/lineage.py:189` |
| `GET` | `/api/v1/lineage/{asset_id}/upstream` | - | `get_upstream_lineage` | `backend/app/api/v1/lineage.py:87` |

### Live2D Factory

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/live2d` | 列出 Live2D 模型 | `list_models` | `backend/app/api/v1/live2d.py:737` |
| `POST` | `/api/v1/live2d` | 创建 Live2D 模型（上传图片） | `create_model` | `backend/app/api/v1/live2d.py:631` |
| `GET` | `/api/v1/live2d/api-keys` | 列出 API 密钥 | `list_api_keys` | `backend/app/api/v1/live2d.py:323` |
| `POST` | `/api/v1/live2d/api-keys` | 创建 API 密钥 | `create_api_key` | `backend/app/api/v1/live2d.py:378` |
| `GET` | `/api/v1/live2d/api-keys/{key_id}` | 获取 API 密钥详情 | `get_api_key` | `backend/app/api/v1/live2d.py:430` |
| `PUT` | `/api/v1/live2d/api-keys/{key_id}` | 更新 API 密钥 | `update_api_key` | `backend/app/api/v1/live2d.py:456` |
| `DELETE` | `/api/v1/live2d/api-keys/{key_id}` | 删除 API 密钥 | `delete_api_key` | `backend/app/api/v1/live2d.py:504` |
| `GET` | `/api/v1/live2d/api-keys/{key_id}/test` | 测试 API 密钥 | `test_api_key` | `backend/app/api/v1/live2d.py:519` |
| `GET` | `/api/v1/live2d/batch` | 获取所有批量队列 | `list_batch_queues` | `backend/app/api/v1/live2d.py:2624` |
| `POST` | `/api/v1/live2d/batch` | 创建批量处理队列 | `create_batch_queue` | `backend/app/api/v1/live2d.py:2607` |
| `GET` | `/api/v1/live2d/batch/{queue_id}` | 获取队列详情 | `get_batch_queue` | `backend/app/api/v1/live2d.py:2636` |
| `DELETE` | `/api/v1/live2d/batch/{queue_id}` | 删除批量队列 | `delete_batch_queue` | `backend/app/api/v1/live2d.py:2782` |
| `POST` | `/api/v1/live2d/batch/{queue_id}/cancel` | 取消批量队列 | `cancel_batch_queue` | `backend/app/api/v1/live2d.py:2767` |
| `POST` | `/api/v1/live2d/batch/{queue_id}/start` | 启动批量队列处理 | `start_batch_queue` | `backend/app/api/v1/live2d.py:2660` |
| `GET` | `/api/v1/live2d/batch/{queue_id}/stats` | 获取队列统计 | `get_batch_queue_stats` | `backend/app/api/v1/live2d.py:2648` |
| `GET` | `/api/v1/live2d/characters` | 获取可选角色列表 | `get_characters_for_live2d` | `backend/app/api/v1/live2d.py:2308` |
| `GET` | `/api/v1/live2d/config/processing-modes` | 获取处理模式配置 | `get_processing_modes` | `backend/app/api/v1/live2d.py:253` |
| `PUT` | `/api/v1/live2d/config/processing-modes` | 更新处理模式配置 | `update_processing_modes` | `backend/app/api/v1/live2d.py:296` |
| `POST` | `/api/v1/live2d/from-asset` | 从素材库图片创建 Live2D 模型 | `create_from_asset` | `backend/app/api/v1/live2d.py:699` |
| `POST` | `/api/v1/live2d/from-character/{character_id}` | 从角色创建 Live2D 模型 | `create_from_character` | `backend/app/api/v1/live2d.py:2410` |
| `GET` | `/api/v1/live2d/options/status` | 获取状态选项 | `get_status_options` | `backend/app/api/v1/live2d.py:241` |
| `GET` | `/api/v1/live2d/options/style` | 获取风格模式选项 | `get_style_options` | `backend/app/api/v1/live2d.py:233` |
| `GET` | `/api/v1/live2d/presets/motions` | 获取动作预设列表 | `get_motion_presets` | `backend/app/api/v1/live2d.py:2194` |
| `GET` | `/api/v1/live2d/presets/motions/{preset_id}` | 获取指定动作预设 | `get_motion_preset` | `backend/app/api/v1/live2d.py:2234` |
| `GET` | `/api/v1/live2d/{model_id}` | 获取 Live2D 模型详情 | `get_model` | `backend/app/api/v1/live2d.py:794` |
| `PUT` | `/api/v1/live2d/{model_id}` | 更新 Live2D 模型 | `update_model` | `backend/app/api/v1/live2d.py:806` |
| `DELETE` | `/api/v1/live2d/{model_id}` | 删除 Live2D 模型 | `delete_model` | `backend/app/api/v1/live2d.py:839` |
| `GET` | `/api/v1/live2d/{model_id}/character` | 获取模型关联的角色 | `get_model_character` | `backend/app/api/v1/live2d.py:2345` |
| `GET` | `/api/v1/live2d/{model_id}/download` | 下载模型文件 | `download_model` | `backend/app/api/v1/live2d.py:1708` |
| `POST` | `/api/v1/live2d/{model_id}/export` | 导出 YLCraft 角色配置包 | `export_model` | `backend/app/api/v1/live2d.py:1628` |
| `POST` | `/api/v1/live2d/{model_id}/inpaint` | AI 遮挡补全 | `inpaint_model` | `backend/app/api/v1/live2d.py:1269` |
| `POST` | `/api/v1/live2d/{model_id}/link-character` | 关联角色到模型 | `link_character_to_model` | `backend/app/api/v1/live2d.py:2369` |
| `GET` | `/api/v1/live2d/{model_id}/lip-sync` | 获取口型动画 | `get_lip_sync` | `backend/app/api/v1/live2d.py:2166` |
| `POST` | `/api/v1/live2d/{model_id}/lip-sync` | 生成口型动画 | `generate_lip_sync` | `backend/app/api/v1/live2d.py:2088` |
| `POST` | `/api/v1/live2d/{model_id}/mesh` | 预留：自动生成网格（未实现） | `generate_mesh` | `backend/app/api/v1/live2d.py:1540` |
| `POST` | `/api/v1/live2d/{model_id}/motion` | 生成待机动作 | `generate_motion` | `backend/app/api/v1/live2d.py:1564` |
| `POST` | `/api/v1/live2d/{model_id}/physics` | 预留：配置物理模拟（未实现） | `configure_physics` | `backend/app/api/v1/live2d.py:1552` |
| `POST` | `/api/v1/live2d/{model_id}/pipeline` | 一键生成流水线 | `run_pipeline` | `backend/app/api/v1/live2d.py:1769` |
| `POST` | `/api/v1/live2d/{model_id}/presets/{preset_id}` | 应用动作预设到模型 | `apply_motion_preset` | `backend/app/api/v1/live2d.py:2263` |
| `POST` | `/api/v1/live2d/{model_id}/rembg` | AI 抠图（去除背景） | `rembg_model` | `backend/app/api/v1/live2d.py:860` |
| `POST` | `/api/v1/live2d/{model_id}/rig` | 自动骨骼绑定 | `rig_model` | `backend/app/api/v1/live2d.py:1282` |
| `PUT` | `/api/v1/live2d/{model_id}/rigging/expression` | 更新表情 | `update_expression` | `backend/app/api/v1/live2d.py:1456` |
| `PUT` | `/api/v1/live2d/{model_id}/rigging/eye-tracking` | 更新视线跟踪 | `update_eye_tracking` | `backend/app/api/v1/live2d.py:1502` |
| `GET` | `/api/v1/live2d/{model_id}/rigging/state` | 获取绑骨状态 | `get_rigging_state` | `backend/app/api/v1/live2d.py:1415` |
| `POST` | `/api/v1/live2d/{model_id}/segment` | AI 图像分割（自动分层） | `segment_model` | `backend/app/api/v1/live2d.py:1131` |
| `POST` | `/api/v1/live2d/{model_id}/style-transfer` | 风格转换（真人转二次元） | `style_transfer_model` | `backend/app/api/v1/live2d.py:995` |

### Logs

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/logs` | 事件日志列表 | `list_logs` | `backend/app/api/v1/logs.py:82` |
| `GET` | `/api/v1/logs/runtime` | 运行日志（文件 tail） | `list_runtime_logs` | `backend/app/api/v1/logs.py:113` |
| `GET` | `/api/v1/logs/{event_id}` | 事件日志详情 | `get_log` | `backend/app/api/v1/logs.py:143` |
| `GET` | `/api/v1/logs/{event_id}/generation` | 事件的 LLM 完整生成日志 | `get_log_generation` | `backend/app/api/v1/logs.py:156` |
| `POST` | `/api/v1/logs/{event_id}/retry` | 失败事件重发 | `retry_log` | `backend/app/api/v1/logs.py:191` |

### Models

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/downloads` | - | `list_downloads` | `backend/app/api/v1/models.py:367` |
| `POST` | `/api/v1/downloads/cleanup` | - | `cleanup_downloads` | `backend/app/api/v1/models.py:411` |
| `GET` | `/api/v1/downloads/{task_id}` | - | `get_download_progress` | `backend/app/api/v1/models.py:348` |
| `DELETE` | `/api/v1/downloads/{task_id}` | - | `cancel_download` | `backend/app/api/v1/models.py:397` |
| `GET` | `/api/v1/models` | - | `list_models` | `backend/app/api/v1/models.py:76` |
| `POST` | `/api/v1/models/civitai/download` | - | `download_civitai_model` | `backend/app/api/v1/models.py:271` |
| `GET` | `/api/v1/models/civitai/search` | - | `search_civitai` | `backend/app/api/v1/models.py:224` |
| `GET` | `/api/v1/models/civitai/{model_id}` | - | `get_civitai_model_info` | `backend/app/api/v1/models.py:250` |
| `POST` | `/api/v1/models/register` | - | `register_model` | `backend/app/api/v1/models.py:165` |
| `POST` | `/api/v1/models/scan` | - | `scan_local_models` | `backend/app/api/v1/models.py:144` |
| `GET` | `/api/v1/models/{model_id}` | - | `get_model` | `backend/app/api/v1/models.py:111` |
| `DELETE` | `/api/v1/models/{model_id}` | - | `delete_model` | `backend/app/api/v1/models.py:324` |
| `PUT` | `/api/v1/models/{model_id}/trigger-words` | - | `update_trigger_words` | `backend/app/api/v1/models.py:304` |

### Novel Sources

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/novel-sources` | 列出来源快照 | `list_snapshots` | `backend/app/api/v1/novel_sources.py:297` |
| `GET` | `/api/v1/novel-sources/domains` | 列出可检测的世界模块 | `list_domains` | `backend/app/api/v1/novel_sources.py:308` |
| `POST` | `/api/v1/novel-sources/import-bookshelf` | 导入书架章节为来源快照 | `import_bookshelf` | `backend/app/api/v1/novel_sources.py:277` |
| `POST` | `/api/v1/novel-sources/import-txt` | 导入本地 TXT 为来源快照 | `import_txt` | `backend/app/api/v1/novel_sources.py:240` |
| `GET` | `/api/v1/novel-sources/{snapshot_id}` | 获取来源快照详情 | `get_snapshot` | `backend/app/api/v1/novel_sources.py:323` |
| `GET` | `/api/v1/novel-sources/{snapshot_id}/chapters` | 列出快照章节 | `list_chapters` | `backend/app/api/v1/novel_sources.py:328` |
| `GET` | `/api/v1/novel-sources/{snapshot_id}/chunks` | 列出快照文本块 | `list_chunks` | `backend/app/api/v1/novel_sources.py:339` |
| `POST` | `/api/v1/novel-sources/{snapshot_id}/chunks/index` | 为小说文本块建立向量索引 | `index_chunks` | `backend/app/api/v1/novel_sources.py:355` |
| `POST` | `/api/v1/novel-sources/{snapshot_id}/chunks/search` | 混合检索小说文本块 | `search_chunks` | `backend/app/api/v1/novel_sources.py:383` |
| `POST` | `/api/v1/novel-sources/{snapshot_id}/derive` | 从完本来源创建派生项目 | `derive_project` | `backend/app/api/v1/novel_sources.py:450` |
| `POST` | `/api/v1/novel-sources/{snapshot_id}/extract` | 按模块提取世界候选 | `extract_world` | `backend/app/api/v1/novel_sources.py:424` |
| `POST` | `/api/v1/novel-sources/{snapshot_id}/plan` | 逐模块判断世界设定是否存在 | `plan_domains` | `backend/app/api/v1/novel_sources.py:401` |
| `POST` | `/api/v1/novel-sources/{snapshot_id}/sync` | 连载来源追加新章节 | `sync_chapters` | `backend/app/api/v1/novel_sources.py:474` |
| `GET` | `/api/v1/world-extraction-runs/{run_id}` | 获取提取运行状态 | `get_run` | `backend/app/api/v1/novel_sources.py:488` |
| `POST` | `/api/v1/world-extraction-runs/{run_id}/affected-facts` | 把合并/矛盾结论传播到已写事实 | `propagate_affected_facts` | `backend/app/api/v1/novel_sources.py:534` |
| `POST` | `/api/v1/world-extraction-runs/{run_id}/apply` | 确认候选并写入项目 | `apply_run` | `backend/app/api/v1/novel_sources.py:568` |
| `GET` | `/api/v1/world-extraction-runs/{run_id}/candidates` | 预览提取候选与证据 | `list_candidates` | `backend/app/api/v1/novel_sources.py:493` |
| `POST` | `/api/v1/world-extraction-runs/{run_id}/candidates/decide` | 标记候选为接受或忽略 | `decide_candidates` | `backend/app/api/v1/novel_sources.py:553` |
| `POST` | `/api/v1/world-extraction-runs/{run_id}/contradictions` | 判断重复候选是否同一实体或矛盾 | `detect_contradictions` | `backend/app/api/v1/novel_sources.py:517` |
| `GET` | `/api/v1/world-extraction-runs/{run_id}/reconcile` | 跨域调和候选提示 | `reconcile_run` | `backend/app/api/v1/novel_sources.py:507` |
| `GET` | `/api/v1/world-maps` | 列出世界地图文档 | `list_world_maps` | `backend/app/api/v1/novel_sources.py:590` |
| `POST` | `/api/v1/world-maps` | 创建世界地图文档 | `create_world_map` | `backend/app/api/v1/novel_sources.py:601` |
| `GET` | `/api/v1/world-maps/{map_id}` | 获取世界地图文档 | `get_world_map` | `backend/app/api/v1/novel_sources.py:612` |
| `PUT` | `/api/v1/world-maps/{map_id}` | 保存世界地图（revision CAS） | `update_world_map` | `backend/app/api/v1/novel_sources.py:620` |
| `DELETE` | `/api/v1/world-maps/{map_id}` | 删除世界地图文档 | `delete_world_map` | `backend/app/api/v1/novel_sources.py:648` |
| `GET` | `/api/v1/world-maps/{map_id}/render` | 渲染世界地图为 SVG | `render_world_map` | `backend/app/api/v1/novel_sources.py:636` |

### Novels

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/novels/add-to-bookshelf` | - | `add_to_bookshelf` | `backend/app/api/v1/novels.py:520` |
| `GET` | `/api/v1/novels/bookshelf-item/{asset_id}` | - | `get_bookshelf_item` | `backend/app/api/v1/novels.py:574` |
| `GET` | `/api/v1/novels/catalog` | - | `get_catalog` | `backend/app/api/v1/novels.py:478` |
| `GET` | `/api/v1/novels/chapter-content` | - | `get_chapter_content` | `backend/app/api/v1/novels.py:540` |
| `POST` | `/api/v1/novels/download-chapters` | - | `download_chapters` | `backend/app/api/v1/novels.py:595` |
| `GET` | `/api/v1/novels/search` | - | `search_novels` | `backend/app/api/v1/novels.py:455` |
| `GET` | `/api/v1/novels/source-catalog` | - | `get_source_catalog` | `backend/app/api/v1/novels.py:652` |
| `GET` | `/api/v1/novels/sources` | - | `get_sources` | `backend/app/api/v1/novels.py:635` |

### Platform Connections

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/platforms` | 列出所有平台连接 | `list_connections` | `backend/app/api/v1/platforms.py:117` |
| `POST` | `/api/v1/platforms` | 创建平台连接 | `create_connection` | `backend/app/api/v1/platforms.py:145` |
| `GET` | `/api/v1/platforms/supported` | 获取支持的平台列表 | `get_supported_platforms` | `backend/app/api/v1/platforms.py:92` |
| `GET` | `/api/v1/platforms/{conn_id}` | 获取连接详情 | `get_connection` | `backend/app/api/v1/platforms.py:130` |
| `PUT` | `/api/v1/platforms/{conn_id}` | 更新平台连接 | `update_connection` | `backend/app/api/v1/platforms.py:162` |
| `DELETE` | `/api/v1/platforms/{conn_id}` | 删除平台连接 | `delete_connection` | `backend/app/api/v1/platforms.py:179` |
| `GET` | `/api/v1/platforms/{conn_id}/cookie-content` | 获取 Netscape 格式 Cookie | `get_cookie_content` | `backend/app/api/v1/platforms.py:307` |
| `POST` | `/api/v1/platforms/{conn_id}/cookie-content` | 保存 Netscape 格式 Cookie | `save_cookie_content` | `backend/app/api/v1/platforms.py:333` |
| `POST` | `/api/v1/platforms/{conn_id}/publish` | 通过指定平台连接发布内容 | `publish_content` | `backend/app/api/v1/platforms.py:249` |
| `POST` | `/api/v1/platforms/{conn_id}/test` | 测试连接有效性 | `test_connection` | `backend/app/api/v1/platforms.py:194` |
| `POST` | `/api/v1/platforms/{conn_id}/use` | 标记为已使用 | `mark_used` | `backend/app/api/v1/platforms.py:208` |

### Proxy

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/proxy/image` | 通用图片代理（解决各平台 CDN 防盗链） | `proxy_image` | `backend/app/api/v1/proxy.py:122` |
| `GET` | `/api/v1/proxy/sniffer/cert` | 下载 CA 证书 | `download_ca_cert` | `backend/app/api/v1/proxy.py:205` |
| `GET` | `/api/v1/proxy/sniffer/health` | 检查代理状态 | `sniffer_health` | `backend/app/api/v1/proxy.py:195` |
| `POST` | `/api/v1/proxy/sniffer/start` | 启动抓包代理 | `start_sniffer` | `backend/app/api/v1/proxy.py:169` |
| `GET` | `/api/v1/proxy/sniffer/status/{session_id}` | 查询抓包状态 | `get_sniffer_status` | `backend/app/api/v1/proxy.py:179` |
| `POST` | `/api/v1/proxy/sniffer/stop/{session_id}` | 停止抓包 | `stop_sniffer` | `backend/app/api/v1/proxy.py:187` |

### Reader

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/reader/asset` | 读取本地文档图片资源 | `read_local_document_asset` | `backend/app/api/v1/reader.py:124` |
| `GET` | `/api/v1/reader/browse` | 浏览下载目录中的可阅读文件 | `browse_local_documents` | `backend/app/api/v1/reader.py:82` |
| `POST` | `/api/v1/reader/delete` | 删除下载目录内的本地文档或文件夹 | `delete_local_document` | `backend/app/api/v1/reader.py:115` |
| `GET` | `/api/v1/reader/file` | 读取本地下载文档用于预览 | `read_local_document` | `backend/app/api/v1/reader.py:94` |
| `POST` | `/api/v1/reader/files` | 读取多个本地下载文档用于合集预览 | `read_local_documents` | `backend/app/api/v1/reader.py:106` |

### Rule Assistant

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/rule-assistant/suggest` | - | `suggest_rule_patch` | `backend/app/api/v1/rule_assistant.py:30` |

### Search

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/embed/batch` | - | `batch_embed` | `backend/app/api/v1/search.py:312` |
| `POST` | `/api/v1/embed/image` | - | `embed_image` | `backend/app/api/v1/search.py:285` |
| `POST` | `/api/v1/embed/text` | - | `embed_text` | `backend/app/api/v1/search.py:258` |
| `GET` | `/api/v1/embed/{asset_id}` | - | `get_embedding_info` | `backend/app/api/v1/search.py:343` |
| `DELETE` | `/api/v1/embed/{asset_id}` | - | `delete_embedding` | `backend/app/api/v1/search.py:364` |
| `POST` | `/api/v1/search/by-embedding` | - | `search_by_embedding` | `backend/app/api/v1/search.py:177` |
| `POST` | `/api/v1/search/by-image` | - | `search_by_image` | `backend/app/api/v1/search.py:152` |
| `POST` | `/api/v1/search/by-text` | - | `search_by_text` | `backend/app/api/v1/search.py:127` |
| `POST` | `/api/v1/search/hybrid` | - | `hybrid_search` | `backend/app/api/v1/search.py:99` |
| `GET` | `/api/v1/search/similar/{asset_id}` | - | `get_similar_assets` | `backend/app/api/v1/search.py:205` |

### Settings

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/settings` | 获取系统设置 | `get_all_settings` | `backend/app/api/v1/settings.py:231` |
| `PUT` | `/api/v1/settings` | 批量更新设置 | `update_all_settings` | `backend/app/api/v1/settings.py:268` |
| `GET` | `/api/v1/settings/download-path` | 获取下载保存路径 | `get_download_path` | `backend/app/api/v1/settings.py:359` |
| `GET` | `/api/v1/settings/ffmpeg-path` | 获取 FFmpeg 路径 | `get_ffmpeg` | `backend/app/api/v1/settings.py:366` |
| `GET` | `/api/v1/settings/storage-paths` | 获取所有存储路径 | `get_all_storage_paths` | `backend/app/api/v1/settings.py:330` |

### Story Maker

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/story` | 列出故事列表 | `list_stories` | `backend/app/api/v1/story.py:307` |
| `POST` | `/api/v1/story/characters` | 保存角色到角色库 | `save_characters` | `backend/app/api/v1/story.py:136` |
| `POST` | `/api/v1/story/generate` | 生成故事结构 | `generate_story` | `backend/app/api/v1/story.py:83` |
| `POST` | `/api/v1/story/portrait` | 生成角色肖像 | `generate_portrait` | `backend/app/api/v1/story.py:193` |
| `GET` | `/api/v1/story/{story_id}` | 获取故事详情 | `get_story` | `backend/app/api/v1/story.py:261` |

### Subtitles

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/subtitles/burn` | 烧录字幕到视频 | `burn_subtitle` | `backend/app/api/v1/subtitles.py:162` |
| `POST` | `/api/v1/subtitles/extract` | 提交字幕提取任务 | `extract_subtitles` | `backend/app/api/v1/subtitles.py:101` |
| `GET` | `/api/v1/subtitles/styles` | 获取可用字幕样式列表 | `list_subtitle_styles` | `backend/app/api/v1/subtitles.py:95` |
| `GET` | `/api/v1/subtitles/tasks` | 列出所有字幕任务 | `list_subtitle_tasks` | `backend/app/api/v1/subtitles.py:136` |
| `GET` | `/api/v1/subtitles/tasks/{task_id}` | 查询提取任务状态 | `get_subtitle_task` | `backend/app/api/v1/subtitles.py:127` |
| `DELETE` | `/api/v1/subtitles/{subtitle_id}` | 删除字幕文件 | `delete_subtitle` | `backend/app/api/v1/subtitles.py:225` |
| `GET` | `/api/v1/subtitles/{subtitle_id}/download` | 下载字幕文件 | `download_subtitle` | `backend/app/api/v1/subtitles.py:143` |

### TTS

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/tts/files/{filename}` | 获取 TTS 音频文件 | `get_tts_file` | `backend/app/api/v1/tts.py:70` |
| `POST` | `/api/v1/tts/speak` | 文本转语音 | `tts_speak` | `backend/app/api/v1/tts.py:40` |

### Tags

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/assets/batch-auto-tag` | - | `auto_tag_batch_assets` | `backend/app/api/v1/tags.py:425` |
| `POST` | `/api/v1/assets/{asset_id}/auto-tag` | - | `auto_tag_asset` | `backend/app/api/v1/tags.py:398` |
| `GET` | `/api/v1/assets/{asset_id}/tags` | - | `get_asset_tags` | `backend/app/api/v1/tags.py:363` |
| `GET` | `/api/v1/tags` | - | `get_tag_tree` | `backend/app/api/v1/tags.py:152` |
| `POST` | `/api/v1/tags` | - | `create_tag` | `backend/app/api/v1/tags.py:188` |
| `POST` | `/api/v1/tags/batch` | - | `batch_tag_assets` | `backend/app/api/v1/tags.py:349` |
| `GET` | `/api/v1/tags/categories` | - | `get_tag_categories` | `backend/app/api/v1/tags.py:274` |
| `GET` | `/api/v1/tags/list` | - | `list_tags` | `backend/app/api/v1/tags.py:162` |
| `GET` | `/api/v1/tags/suggest/{asset_id}` | - | `suggest_tags` | `backend/app/api/v1/tags.py:376` |
| `POST` | `/api/v1/tags/sync-counts` | - | `sync_tag_counts` | `backend/app/api/v1/tags.py:455` |
| `GET` | `/api/v1/tags/{tag_id}` | - | `get_tag` | `backend/app/api/v1/tags.py:177` |
| `PUT` | `/api/v1/tags/{tag_id}` | - | `update_tag` | `backend/app/api/v1/tags.py:202` |
| `DELETE` | `/api/v1/tags/{tag_id}` | - | `delete_tag` | `backend/app/api/v1/tags.py:219` |
| `GET` | `/api/v1/tags/{tag_id}/ancestors` | - | `get_tag_ancestors` | `backend/app/api/v1/tags.py:261` |
| `GET` | `/api/v1/tags/{tag_id}/assets` | - | `get_tagged_assets` | `backend/app/api/v1/tags.py:286` |
| `POST` | `/api/v1/tags/{tag_id}/assets` | - | `tag_asset` | `backend/app/api/v1/tags.py:310` |
| `DELETE` | `/api/v1/tags/{tag_id}/assets` | - | `untag_asset` | `backend/app/api/v1/tags.py:337` |
| `GET` | `/api/v1/tags/{tag_id}/children` | - | `get_tag_children` | `backend/app/api/v1/tags.py:231` |
| `GET` | `/api/v1/tags/{tag_id}/descendants` | - | `get_tag_descendants` | `backend/app/api/v1/tags.py:248` |

### Tasks

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/tasks` | 任务列表 | `list_tasks` | `backend/app/api/v1/tasks.py:620` |
| `GET` | `/api/v1/tasks/stats` | 任务统计 | `get_task_stats` | `backend/app/api/v1/tasks.py:657` |
| `GET` | `/api/v1/tasks/{task_id}` | 任务详情 | `get_task_detail` | `backend/app/api/v1/tasks.py:732` |
| `DELETE` | `/api/v1/tasks/{task_id}` | 删除任务 | `delete_task` | `backend/app/api/v1/tasks.py:799` |
| `POST` | `/api/v1/tasks/{task_id}/cancel` | 取消任务 | `cancel_task` | `backend/app/api/v1/tasks.py:757` |

### Torrents

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/torrents` | List torrent downloads | `list_torrents` | `backend/app/api/v1/torrents.py:136` |
| `GET` | `/api/v1/torrents/engine` | Get torrent engine status | `get_engine_status` | `backend/app/api/v1/torrents.py:111` |
| `POST` | `/api/v1/torrents/magnet` | Add magnet link | `add_magnet` | `backend/app/api/v1/torrents.py:145` |
| `POST` | `/api/v1/torrents/upload` | Upload torrent file | `upload_torrent` | `backend/app/api/v1/torrents.py:154` |
| `GET` | `/api/v1/torrents/{download_id}` | Get torrent task | `get_torrent` | `backend/app/api/v1/torrents.py:189` |
| `DELETE` | `/api/v1/torrents/{download_id}` | Delete torrent task | `delete_torrent` | `backend/app/api/v1/torrents.py:296` |
| `POST` | `/api/v1/torrents/{download_id}/boost-trackers` | Add public trackers and reannounce torrent | `boost_torrent_trackers` | `backend/app/api/v1/torrents.py:285` |
| `GET` | `/api/v1/torrents/{download_id}/files` | List torrent files | `list_files` | `backend/app/api/v1/torrents.py:197` |
| `POST` | `/api/v1/torrents/{download_id}/files/{file_index}/prioritize-streaming` | Prioritize torrent file for streaming | `prioritize_torrent_streaming` | `backend/app/api/v1/torrents.py:236` |
| `GET` | `/api/v1/torrents/{download_id}/files/{file_index}/stream` | Stream torrent video file | `stream_file` | `backend/app/api/v1/torrents.py:324` |
| `GET` | `/api/v1/torrents/{download_id}/health` | Get torrent download health | `get_torrent_health` | `backend/app/api/v1/torrents.py:221` |
| `POST` | `/api/v1/torrents/{download_id}/import-assets` | Import completed files | `import_assets` | `backend/app/api/v1/torrents.py:312` |
| `POST` | `/api/v1/torrents/{download_id}/pause` | Pause torrent task | `pause_torrent` | `backend/app/api/v1/torrents.py:252` |
| `POST` | `/api/v1/torrents/{download_id}/refresh-metadata` | Retry torrent metadata discovery | `refresh_torrent_metadata` | `backend/app/api/v1/torrents.py:274` |
| `POST` | `/api/v1/torrents/{download_id}/resume` | Resume torrent task | `resume_torrent` | `backend/app/api/v1/torrents.py:263` |
| `POST` | `/api/v1/torrents/{download_id}/select-files` | Select files | `select_files` | `backend/app/api/v1/torrents.py:209` |

### Videos

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/videos/backends` | 可用视频后端列表 | `list_backends` | `backend/app/api/v1/videos.py:437` |
| `POST` | `/api/v1/videos/generate` | Generate video with optional project lineage | `generate_video` | `backend/app/api/v1/videos.py:478` |
| `GET` | `/api/v1/videos/history` | 视频生成历史与待处理任务 | `list_video_tasks` | `backend/app/api/v1/videos.py:776` |
| `GET` | `/api/v1/videos/tasks/{task_id}` | 查询任务状态 | `get_task_status` | `backend/app/api/v1/videos.py:686` |
| `GET` | `/api/v1/videos/tasks/{task_id}/file` | 播放已下载的视频任务文件 | `stream_task_file` | `backend/app/api/v1/videos.py:794` |

### WebSocket

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `WEBSOCKET` | `/api/v1/ws` | - | `websocket_endpoint` | `backend/app/api/v1/ws.py:22` |
| `GET` | `/api/v1/ws/status` | WebSocket 连接状态 | `ws_status` | `backend/app/api/v1/ws.py:84` |

### Wechat MP

| Method | Path | Summary | Handler | Source |
| --- | --- | --- | --- | --- |
| `GET` | `/api/v1/wechat-mp/articles` | 拉取文章列表 | `get_articles` | `backend/app/api/v1/wechat_mp.py:226` |
| `POST` | `/api/v1/wechat-mp/download-batch` | 批量下载文章 | `download_batch_articles` | `backend/app/api/v1/wechat_mp.py:277` |
| `POST` | `/api/v1/wechat-mp/download-single` | 下载单篇文章 | `download_single_article` | `backend/app/api/v1/wechat_mp.py:256` |
| `POST` | `/api/v1/wechat-mp/export-epub` | 多篇已下载文章合并导出 EPUB | `export_epub` | `backend/app/api/v1/wechat_mp.py:298` |
| `POST` | `/api/v1/wechat-mp/import-assets` | 将已下载文章导入素材库 | `import_articles_to_assets` | `backend/app/api/v1/wechat_mp.py:324` |
| `POST` | `/api/v1/wechat-mp/login/qrcode` | 生成登录二维码 | `start_qrcode_login` | `backend/app/api/v1/wechat_mp.py:171` |
| `GET` | `/api/v1/wechat-mp/login/status/{session_id}` | 轮询登录状态 | `check_login_status` | `backend/app/api/v1/wechat_mp.py:179` |
| `GET` | `/api/v1/wechat-mp/search-accounts` | 搜索公众号 | `search_accounts` | `backend/app/api/v1/wechat_mp.py:189` |

## Update Rules

- Add or remove API routes in code first.
- Run `python tools/generate_api_surface.py` after route changes, or make an equivalent explicit update when the generator cannot express the change.
- Commit this file and `docs/architecture/api_surface.json` together.
- Review the generated diff. The script records route facts only; the AI/developer must judge semantic changes.
- If route behavior changes materially, update `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`, the owning domain doc, or the relevant OpenSpec task too.
- Treat Agent tools and Skills as internal APIs: update their schema/spec docs and tests when inputs, outputs, risk level, authorization, or routing behavior changes.
