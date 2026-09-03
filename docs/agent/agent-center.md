# Agent Center 使用说明

Agent Center 是 YLCraft 的项目智能体工作台。默认界面只保留最近对话、消息时间线和输入框，让普通用户直接描述目标；智能体设定、模型、工具授权、长期记忆、默认项目、默认 Skill 和完整运行轨迹按需展开。

执行过程不是独立的管理报表。计划、工具调用、观察、委派和确认按发生顺序出现在对话中，最终回答完成后默认折叠；需要排错或沉淀 Skill 时再打开完整轨迹。工具、记忆、连接器或执行树加载失败只影响对应辅助区域，不应清空当前对话。

## 创建或复制智能体

1. 打开前端 `/agent`。
2. 在左侧智能体列表选择一个现有智能体。
3. 点击右上角设置按钮，打开“智能体设定”抽屉。
4. 点击“复制新建”可以从当前智能体复制一份。
5. 在 `Profile` 页签里改名称、头像标识、角色和定位说明。

只有承担总控职责的 Profile 才应打开 `Supervisor：允许委派子智能体`。该能力开启后，运行时才会向模型暴露 `delegate_agent_tasks`；普通 Writer/Reviewer Worker 即使工具授权选择 `*`，也看不到且无法调用委派工具，避免递归失控。

建议按职责拆智能体，而不是让一个智能体包办所有事：

- 总控导演：拆任务、验收、委派子智能体。
- 小说作者：章节正文、续写、人味改写。
- 角色设定师：角色卡、视觉卡、立绘提示词。
- 分镜导演：脚本、镜头、漫画页、生图提示词。
- 素材管家：检索素材、匹配参考图、补标签。
- 质检编辑：连续性、设定一致性、缺口检查。

## 选择文本模型

在 `Model` 页签里选择文本供应商和文本模型。这里读取的是“设置 -> 模型配置”里的 LLM 供应商。

如果供应商或模型留空，会使用系统默认文本模型。若列表为空，先去模型配置里新增或启用 LLM 类型连接器。

## 授权工具

在 `Tools` 页签里选择允许该智能体调用的工具。

- 选择 `*` 表示允许全部工具。
- 不选 `*` 时，只会把已勾选工具发给模型。
- 未授权工具不会进入模型候选列表，模型即使想调用也会被后端拦截。
- `write`、`delete`、`costly` 风险工具会先生成待确认步骤，用户确认后才执行；普通外部读取不重复弹授权。

工具卡片里会显示输入说明、输出说明、风险等级和成本提示。可以先用“测试工具”验证参数格式。

### 素材库工具

素材库作为 `asset` 分类工具接入智能体，是参考图、剪辑、字幕和 BGM 流程的入口：

- `search_assets`：搜索图片、视频、音频、文本等资产；默认只返回 `status=READY` 的素材，避免误用已删除资产。
- `get_asset_detail`：读取单个素材的文件路径、缩略图、标签、元数据、版本和媒体属性。
- `download_asset`：返回本地可访问文件引用，不会真正复制或下载文件。
- `add_asset_tag`：给素材补标签，风险等级为 `write`。
- `delete_asset`：把素材标记为 `DELETED`，风险等级为 `delete`，不会直接删除磁盘文件。

推荐流程是：先用 `search_assets` 找素材，再用 `get_asset_detail` 或 `download_asset` 拿到文件路径；如果素材要进入某个创作项目，继续调用 `link_creative_project_asset` 绑定为项目参考卡。

### 创作项目工具

创作项目已经作为 `creative_project` 分类工具接入智能体，推荐按“先读上下文，再读完整内容，再写回或运行流水线”的顺序使用：

- `list_creative_projects`：列出项目，拿到 `project_id`。
- `inspect_creative_project`：查看项目阶段、内容数量、最近生成日志和项目圣经摘要。
- `build_creative_project_context_pack`：构建紧凑上下文包，适合智能体理解某个项目或某一章当前状态。
- `get_creative_production_plan`：读取当前导演生产计划或历史版本；上下文包也会携带当前方案、计划版本、节点依赖和待确认节点的轻量摘要。
- `save_creative_production_plan`：把用户确认或修改后的可见生产计划追加为新版本，风险等级为 `write`；保存计划不启动生成，但其中的确认点必须在调用生图、生视频、3D、下载或发布前遵守。
- `list_creative_project_contents`：列出正文、脚本、分镜、项目圣经等内容摘要，拿到 `content_id`。
- `get_creative_project_content`：读取单条内容的完整结构化 JSON 和正文文本，用于续写、改写、拆分镜或质检。
- `update_creative_project_content`：把智能体改写后的标题、正文、结构化 JSON 或锁定状态写回项目，风险等级为 `write`，需要确认。
- `list_creative_project_asset_links`：查看项目或某条内容已经挂载了哪些素材/参考卡。
- `link_creative_project_asset`：把素材库资产挂到项目或某条内容上，作为角色、背景、风格、世界观或输出产物参考。
- `match_creative_project_reference_assets`：为脚本、分镜或漫画页匹配项目参考卡，并把 `reference_asset_ids` / `reference_notes` 写回内容 JSON。
- `list_creative_project_generation_logs`：查询项目或跨项目 AI 生成日志摘要，快速定位失败阶段、模型和校验错误。
- `get_creative_project_generation_log`：读取单条生成日志详情，包含完整 prompt、request、raw_response、normalized 和 validation_error。
- `sync_creative_project_bible`：从故事大纲同步项目圣经和世界资产卡。
- `run_creative_project_pipeline`：运行项目流水线，生成细纲、正文、脚本、分镜、参考卡或漫画页。
- `run_creative_writer_room`：运行小说写作室多步骤流程，适合单章正文生成、润色和评审。
- Canvas tools use the `canvas` category. Free-form `/canvas` document tools are `list_creative_canvas_documents`, `get_creative_canvas_document`, and `apply_creative_canvas_operations`. Project relationship-graph tools are `get_project_canvas`, `save_project_canvas`, `add_project_canvas_node`, `connect_project_canvas_nodes`, and `apply_project_canvas_operations`. Write tools have `write` risk and require confirmation.

如果只是检查或规划，用前三类只读工具即可；如果要保存修改或生成新内容，会进入确认步骤。

参考图推荐流程是：先用素材库工具找到角色/背景/风格图，再用 `link_creative_project_asset` 挂到项目参考卡集合；生成脚本或分镜后，调用 `match_creative_project_reference_assets` 给每个场景/镜头补上参考图 ID，后续生图工具就能带着这些参考图继续生成。

排错推荐流程是：先用 `list_creative_project_generation_logs` 过滤 `status=failed` 或指定 `stage`，再用 `get_creative_project_generation_log` 查看完整原始响应和校验错误，让智能体据此判断是 prompt、模型输出、JSON 结构还是字段约束问题。

### AI 生图工具

图片生成已经作为 `image` 分类工具接入智能体：

- `list_image_backends`：查看当前可用生图后端、模型、尺寸和是否支持参考图。
- `preview_image_generation_request`：预览标准化生图请求，不调用模型、不花钱，适合先确认 prompt、参考图和 lineage。
- `generate_image_asset`：真正调用图片模型，风险等级为 `costly`，会进入待确认步骤；成功后尽量保存到素材库 / Asset Hub。
- `poll_image_generation_task`：查询异步生图任务，完成时会把图片入库并返回素材节点 ID。

推荐流程是：先让智能体预览请求，再确认执行生图；如果返回 `status=pending`，继续让智能体轮询 `task_id`。

### AI 视频工具

视频生成已经作为 `video` 分类工具接入智能体：

- `list_video_backends`：查看当前可用视频生成后端、模型和能力。
- `preview_video_generation_request`：预览标准化视频请求，不调用模型、不花钱；适合先确认 prompt、首帧图、时长、比例和分辨率。
- `generate_video_asset`：真正调用视频模型，风险等级为 `costly`，会进入待确认步骤；同步完成时会尽量保存到素材库 / Asset Hub。
- `poll_video_generation_task`：查询异步视频生成任务，完成后返回视频链接、本地路径或错误信息。

推荐流程是：先预览视频请求，确认参数和成本风险后再执行生成；如果返回 `status=pending`，继续轮询 `task_id`，直到完成或失败。

### Prompt 模板工具

Prompt 模板已经作为 `prompt_template` 分类工具接入智能体：

- `list_prompt_templates`：按用途和阶段列出平台图文/创作项目模板，只返回摘要、变量和长度。
- `get_prompt_template`：读取单个模板的完整 system、正文、图片和视频模板。
- `preview_prompt_template_render`：用示例变量预览渲染结果，不调用模型、不写库，适合检查最终会发给模型的内容。
- `update_prompt_template`：更新模板字段，风险等级为 `write`，默认需要用户确认后才会执行。

推荐流程是：先 `list_prompt_templates` 找到阶段模板，再 `get_prompt_template` 查看完整内容；修改前用 `preview_prompt_template_render` 检查变量覆盖和缺失项，确认无误后再执行 `update_prompt_template`。

### AI 配置工具

AI 连接器和供应商规范已经作为 `ai_config` 分类工具接入智能体：

- `list_ai_connectors`：按 `llm/image/video/tts/stt/embedding` 列出当前启用的模型配置、默认模型、可用模型、能力和使用统计。
- `get_ai_connector`：读取单个连接器的非敏感详情，包括 SDK/HTTP 模式、请求模板、响应解析、默认参数、尺寸和参考图能力。
- `list_provider_metadata` / `get_provider_metadata`：读取已注册供应商规范，用于复用请求模板、响应解析、尺寸和参考图配置。
- `upsert_provider_metadata`：根据用户提供的供应商文档或示例请求创建/更新供应商规范，风险等级为 `write`，属于 AI 配置助手的低风险可逆写入，会直接执行并在 Trace 中展示。
- `create_ai_connector` / `update_ai_connector`：根据用户提供的模型、base_url、endpoint、模板和能力字段创建或修改连接器，风险等级为 `write`，属于 AI 配置助手的低风险可逆写入，会直接执行并在 Trace 中展示。图片连接器必须显式设置 `default_params.image_capabilities`：文生图为 `["text_to_image"]`，图生图/改图为 `["image_to_image"]`，同接口双能力则两者都写；endpoint 名称只作为旧数据兜底。
- `test_ai_connector`：测试连接器连通性，读取配置并发起测试请求。
- `discover_connector_models`：从供应商接口发现可用模型列表。

这些读取工具不会返回 API Key。推荐配置流程是：先读取或写入 provider metadata，再创建/更新 connector，最后用 `test_ai_connector` 或 `discover_connector_models` 验证。删除连接器、真实生图、视频生成等仍按 `delete` / `costly` 规则进入确认。

模型配置智能体应按“先检查、再拆规范、再写入、最后验证”的顺序工作：

- 配置前先调用 `list_provider_metadata` / `list_ai_connectors`；修改已有连接器前先调用 `get_ai_connector`，只改必要字段，空 `api_key` 表示保留已有密钥。
- 从 API 文档或 curl 中拆出 `base_url`、`api_endpoint`、`provider_type`、`api_format`、`default_model`、`request_template`、`response_config`、`supported_sizes`、`default_params` 和参考图字段。不要把某个供应商的临时错误当成通用规则写死。
- URL 必须能拼出完整请求端点，不要只停在 `https://host/v1`。OpenAI-compatible 生图通常为 `/v1/images/generations`，图片编辑/图生图通常为 `/v1/images/edits`。
- `request_template` 是 Jinja2 JSON 模板；字符串字段优先使用 `{{ prompt_json }}`，避免多行 prompt 造成 JSON 控制字符错误。常用变量包括 `model`、`prompt`、`prompt_json`、`size`、`n`、`seed`、`response_format`、`reference_image_url`、`reference_image_base64`、`reference_image_urls`、`images`、`images_json`。
- 参考图传递方式必须互斥：JSON 数组模式使用 `images: [{"image_url": "{{ reference_image_url }}"}]`，只设置 `reference_image_array_field=images`、清空 `reference_image_field`；multipart 本地上传模式在 `default_params` 中设置 `{"request_content_type":"multipart","multipart_image_field":"image"}`，只设置 `reference_image_field=image`、清空 `reference_image_array_field`。只有供应商文档明确要求时才使用 `images[].image`。
- `support_reference_image` 只表示参考图如何传入，不再决定连接器属于文生图还是图生图；Agent 创建或修正图片模型时必须同时检查/写入 `image_capabilities`。
- OpenAI-compatible base64 图片响应通常配置 `{"response_format":"base64","base64_images_path":"$.data[*].b64_json","error_path":"$.error.message"}`；返回 URL 的接口使用 `images_path`。

### 任务中心工具

任务中心已经作为 `task` 分类工具接入智能体：

- `list_project_tasks`：查看下载、生图、视频、创作、字幕、剪辑等异步任务摘要，可按状态、类型和关键词过滤。
- `get_project_task`：读取单个任务详情，包含 payload、result、diagnostics、events 和错误信息。
- `cancel_project_task`：取消尚未完成的任务，风险等级为 `write`，默认需要确认。
- `delete_project_task`：从任务中心视图删除任务记录，风险等级为 `delete`，默认需要确认；不会删除素材库资产文件。

推荐排错流程是：先 `list_project_tasks(status="failed")` 找失败任务，再 `get_project_task` 读取完整事件和错误；如果任务仍在运行且需要停止，再确认执行 `cancel_project_task`。

### 小说库工具

小说和书源已经作为 `novel` 分类工具接入智能体：

- `list_novel_sources`：列出本地书源配置和规则能力，不访问外部网站。
- `list_novel_bookshelf`：列出 Asset Hub 中的小说书架/下载记录，可作为创作项目上游素材。
- `search_novel_sources`：跨启用书源搜索小说，风险等级为 `external`，会访问外部书源站点。
- `get_novel_catalog`：读取指定书源的小说目录，风险等级为 `external`。
- `preview_novel_chapter`：读取章节正文截断预览，风险等级为 `external`，默认不把整章塞进上下文。

推荐流程是：先 `list_novel_bookshelf` 查本地已有小说；没有合适素材时，经确认后 `search_novel_sources`，再 `get_novel_catalog` 和 `preview_novel_chapter` 判断是否适合拆成短剧/漫画项目。

小说来源 → 世界提取作为 `novel_source` 分类工具接入，与真人 `/novel-world` 页面走同一套预览-确认契约：

- `list_novel_source_snapshots`：列出已导入的来源快照（TXT/书架），只读本地。
- `inspect_novel_source_snapshot`：查看快照章节与可提取/可检测的世界模块。
- `plan_novel_source_domains`：AI 逐模块判断存在性（detected/not_detected/uncertain），风险 `costly`，只检测不提取。
- `extract_novel_source_world`：按选定模块提取候选（角色/地点/势力/历史事件），风险 `costly`，只预览不写项目事实；未指定 `domains` 且没有检测结果时回落到基础层（角色/地点/势力/历史事件），扩展模块需先 `plan_novel_source_domains` 检测后显式启用；`mode=delta` 时从上次游标只处理新文本块并把新证据并回既有候选。
- `expand_world_entity_attributes`：AI 按模块属性契约补充一个世界实体的字段，风险 `costly`，只补勾选字段、不覆盖已有内容；产出 `origin=ai_draft` 候选（无原文证据、**不伪造**），需确认后由 `apply` 写入正典。契约外的字段与新增模块只作为 `suggested_fields`/`suggested_domains` 返回，默认不启用，需用户确认后才参与提取。
- `expand_world_domain`：按层次策略 AI 细化**整个模块**，风险 `costly`，**异步提交**并返回 `task_id`；轮询复用既有 `get_project_task(task_id)`（任务中心统一管理、可在任务中心页与 `cancel_project_task` 查看/取消）。完成后 `result` 含 `run_id` 与候选数，仍需到 `/novel-world` 审阅确认才写入正典。
- `list_world_building_suggestions`：列出 AI 提出但**尚未确认**的结构建议（新模块与新字段），风险 `read`，不调用模型；未确认的建议不参与任何提取与生成。
- `resolve_world_field_suggestion`：确认或忽略一个建议字段，风险 `write`；确认后写入该模块的属性契约（只追加、内置字段不动），忽略后不再重复提示。
- `resolve_world_domain_suggestion`：确认或忽略一个建议模块，风险 `write`；确认后启用并参与提取，忽略后移除该建议。
- `manage_world_building_template`：管理世界构建模板（层次策略 + 每档提示词），风险 `write`；`action=list` 只读；`save` 保存模板（内置模板只读，save 更新内置会被拒绝；`template_id` 留空即新建项目私有模板）；`delete` 删除项目私有模板；`action=draft` 让 AI 按项目已启用模块与补充要求起草一份 `{name,layers,prompts,note}` 草案（会调用一次模型、消耗配额），**草案不落库**，需再显式 `save` 才保存——与真人「AI 起草 → 确认后保存」是同一纪律。

> 结构变更必须过闸：智能体可以**查看与转达**建议，但确认与否应由用户决定——智能体不得自行批准自己提出的建议。
- `sync_novel_source_chapters`：为连载快照追加新章节和新文本块，风险 `write`，只追加不重建。
- `list_world_extraction_candidates`：预览候选与逐字证据（同时覆盖本次运行产生或更新的条目）。
- `decide_world_extraction_candidates`：接受/忽略/合并候选，风险 `write`，只改候选状态；`merge` 用 `merge_into` 把重复候选的证据与设定并入目标，源候选进入 `merged` 终态。
- `apply_world_extraction_run`：唯一写入点，把已接受候选写入角色库和锁定的 `world_asset` 事实卡，风险 `write`。
- `index_novel_source_chunks`：为快照文本块建立可选向量索引，风险 `costly`，失败块保留为 `failed`，来源仍可走精确检索。
- `search_novel_source_chunks`：按查询词做精确/向量混合召回，只读，返回文本块、字符偏移与原文，用于证据复核或提取前定位上下文。
- `reconcile_world_extraction_run`：确定性检查候选的跨模块重名、别名交叉、证据重叠与时序问题，只读提示，不自动合并；向用户汇报冲突时应逐条说明并请其决策。
- `detect_world_extraction_contradictions`：对重复组做语义判断（同一实体一致 / 同一实体矛盾 / 不同实体），风险 `costly`，会调用一次模型；只给建议（merge / resolve / keep_separate），不自动合并。
- `propagate_affected_world_facts`：把合并与冲突结论传播到已写入的 `world_asset`，只打 `review_required` 标记并附原因，风险 `write`，不改写事实内容；可传入上一步的 verdicts 附带矛盾原因。
- `derive_project_from_novel_source`：从完本来源创建改编/续写/同人派生项目，风险 `write`；原作正典（已确认世界事实与角色关联）复制进新项目并标记只读参考层。连载来源不支持，应引导用户用增量同步。

推荐流程：`list_novel_source_snapshots` → `inspect_novel_source_snapshot` → 可选 `index_novel_source_chunks`（长篇来源建议先建索引）→ `plan_novel_source_domains`（向用户说明每域判断与成本）→ `extract_novel_source_world` → `reconcile_world_extraction_run`（复核冲突）→ `list_world_extraction_candidates`（预览证据）；审阅中可用 `search_novel_source_chunks` 复核原文。连载更新时先 `sync_novel_source_chapters`，再用 `mode=delta` 增量提取，避免重建整套世界；完本来源要开新篇时，经用户确认后用 `derive_project_from_novel_source` 创建改编/续写/同人项目。提取默认不写项目，`apply` 前必须先经用户确认。

### 世界地图工具

地图工具与真人 `/world-map` 工作台共用同一 service 层，因此规则完全一致：结构化 `map_json`（区域/据点/路线/空间层）是正典，成图与提示词润色都是**派生**动作。

- `list_world_maps`：列出地图文档（可按项目或来源快照过滤），返回版本号与各要素计数，读取到的 `revision` 是后续写操作必填的 CAS 依据，风险 `read`。
- `get_world_map`：读取单张地图的完整结构化内容与版本号，风险 `read`。
- `create_world_map`：新建地图（可传初始 `map_json`，或 `clone_project_places=true` 从项目地点实体克隆），风险 `write`；初版为 v1 并落 v1 历史快照。
- `save_world_map`：按 `expected_revision` 做 CAS 保存，版本不一致时返回当前版本并拒绝，风险 `write`；成功后落一条 append-only 历史快照。
- `render_world_map_svg`：确定性渲染 SVG，不调用模型、不消耗配额，风险 `read`；超长时截断并标记 `truncated`。
- `export_world_map_points`：导出结构化点位 JSON（含 `entity_id` 与原文证据），不是图片，风险 `read`。
- `resolve_world_map_entities`：解析据点关联的地点实体与证据，并给出 `orphan_node_ids`；游离标记（无 `entity_id` 或实体已不存在）不是正典，应提示关联实体而不是当作事实，风险 `read`。
- `build_world_map_visual_prompt`：从结构化数据确定性生成生图提示词（含坐标与方位约定），不消耗配额，风险 `read`。
- `optimize_world_map_visual_prompt`：用 LLM 润色提示词，保留全部地名、坐标约束与方位，只改写表达，风险 `read`；**不落库、不生成图**，只消耗一次文本配额。
- `generate_world_map_visual`：按提示词生成视觉成图并入素材中枢，风险 `write`；成图只以引用形式记回 `map_json.visuals`，不自动铺为底图、不叠加标记、不改空间关系，并发冲突时放弃回写而不回滚成图。
- `list_world_map_revisions`：列出历史版本（倒序），传 `revision` 时返回该版完整内容，风险 `read`。
- `rollback_world_map`：回滚到历史版本，风险 `write`；以旧快照为内容产生**新**版本，历史链不被改写，需先校验 `expected_revision` 与当前版本一致。

推荐流程：`list_world_maps` → `get_world_map` → `build_world_map_visual_prompt`（先看提示词是否表达准确）→ 需要润色时 `optimize_world_map_visual_prompt` → 经用户确认后 `generate_world_map_visual` → 用 `save_world_map` 保存结构化改动。成图与底图是派生资产，不得据此断言地理事实；要断言事实应读 `map_json` 或 `resolve_world_map_entities` 的实体证据。

### 下载解析工具

下载入口已经作为 `download` 分类工具接入智能体：

- `parse_download_link`：解析视频、文章或媒体链接，返回标题、作者、平台、封面、时长、清晰度摘要和可关联的解析素材 ID；该工具会访问外部链接，风险等级为 `external`。
- `create_download_task`：确认后创建后台下载任务，会访问外部站点、消耗带宽并写入本地文件/素材库，风险等级为 `external`。
- `poll_download_task`：读取下载任务当前进度、错误和完成后的文件/素材 ID，风险等级为 `read`。

推荐流程是：先让智能体调用 `parse_download_link` 判断链接是否可用和有哪些清晰度；用户确认后再调用 `create_download_task`；随后用 `poll_download_task` 或任务中心的 `get_project_task` 排查进度和错误。

### 公众号工具

微信公众号采集入口已经作为 `wechat_mp` 分类工具接入智能体：

- `list_wechat_mp_connections`：列出已配置的公众号平台连接，只返回连接状态、账号摘要和是否配置凭证，不返回 Cookie 或 Token。
- `search_wechat_mp_accounts`：通过已登录连接搜索公众号，返回 fake_id、昵称、头像、简介等摘要；风险等级为 `external`。
- `list_wechat_mp_articles`：按 fake_id 拉取公众号文章列表；风险等级为 `external`。
- `download_wechat_mp_article`：确认后下载单篇文章为 Markdown/HTML/EPUB/PDF，本地写文件；风险等级为 `external`。

推荐流程是：先 `list_wechat_mp_connections` 找可用连接，再 `search_wechat_mp_accounts` 定位公众号 fake_id，接着 `list_wechat_mp_articles` 选择文章，最后经确认调用 `download_wechat_mp_article`。下载后的文件可继续通过素材库导入/关联到创作项目。

### TTS 语音合成工具

语音合成已经作为 `tts` 分类工具接入智能体：

- `preview_tts_request`：预览文本转语音请求，不写文件、不调用供应商。
- `generate_tts_audio`：确认后把文本生成音频文件，返回 `file_path` 和 `audio_url`；风险等级为 `costly`。当前后端仍可能是占位音频，后续接入真实 TTS Provider 后会消耗额度。

推荐流程是：先用 `preview_tts_request` 检查旁白/台词、语速、声音和供应商，再确认调用 `generate_tts_audio`。生成结果可继续交给素材库、剪辑或 BGM/字幕后处理工具。

### 电子书工具

EPUB 生成已经作为 `ebook` 分类工具接入智能体：

- `create_ebook_from_folder`：从包含 Markdown/HTML 的本地文件夹生成 EPUB，风险等级为 `write`。
- `get_ebook_task`：读取单个 EPUB 任务状态和输出路径。
- `list_ebook_tasks`：列出最近 EPUB 生成任务。

推荐流程是：公众号/小说/正文内容先下载或导出成本地 Markdown/HTML 文件夹，再用 `create_ebook_from_folder` 生成 EPUB；如果任务未完成或失败，用 `get_ebook_task` 和 `list_ebook_tasks` 排查。

### 语义检索工具

语义素材检索已经作为 `semantic_search` 分类工具接入智能体：

- `semantic_search_assets`：用文本语义、全文和标签权重混合搜索素材库；风险等级为 `costly`，因为可能调用 embedding 模型。
- `find_similar_assets`：基于已有素材 embedding 查找相似素材，适合找同风格参考图或一致性素材。
- `get_asset_embedding_info`：检查素材是否已有 embedding 记录，不返回原始向量。

推荐流程是：普通关键词先用 `search_assets`；需要“风格/语义相近”时用 `semantic_search_assets`；已有参考图想找同类素材时用 `find_similar_assets`。

### 素材血缘工具

素材血缘已经作为 `lineage` 分类工具接入智能体：

- `get_asset_lineage_graph`：读取完整上游/下游血缘图。
- `get_asset_upstream_lineage`：查看素材来源，例如 prompt、模型、参考图、源文章。
- `get_asset_downstream_lineage`：查看素材派生物，例如变体图、分镜图、导出文件。
- `get_asset_lineage_stats`：查看上下游数量、关系类型分布等统计。
- `link_asset_lineage`：确认后创建两个素材间的血缘关系，风险等级为 `write`。
- `find_asset_common_ancestor`：判断两个素材是否同源。

推荐流程是：生成图片、漫画分镜、角色立绘或导出文件后，用 `link_asset_lineage` 把参考图、prompt、输出物串起来；排查“为什么工作台不显示/这张图从哪里来”时，先查 upstream/downstream。

### 本地阅读工具

本地文档阅读已经作为 `reader` 分类工具接入智能体：

- `browse_reader_documents`：浏览下载目录或指定根目录下的可阅读文件。
- `read_reader_document`：读取单个 Markdown/HTML/文本/EPUB 类文档，默认返回截断预览，避免一次塞入过大正文。
- `read_reader_document_collection`：把多个本地文档作为合集预览，适合电子书生成前检查顺序和内容。
- `delete_reader_document`：确认后删除下载目录内的本地文档或文件夹，风险等级为 `delete`。

推荐流程是：先 `browse_reader_documents` 找文件，再 `read_reader_document` 或 `read_reader_document_collection` 预览；确认内容正确后可交给 `create_ebook_from_folder`、创作项目导入或素材库关联。

### 导出质检工具

素材库导出、质量评分和查重已经作为 `export` 分类工具接入智能体：

- `get_export_dataset_stats`：读取素材库数据集统计。
- `export_asset_dataset`：确认后把符合条件的素材和元数据导出为 ZIP，风险等级为 `write`。
- `calculate_asset_quality`：计算单素材质量分，风险等级为 `costly`。
- `batch_calculate_asset_quality`：批量计算素材质量分，风险等级为 `costly`。
- `find_duplicate_assets`：按向量相似度查找重复素材，风险等级为 `costly`。
- `merge_duplicate_assets`：确认后把重复素材合并到主素材，风险等级为 `write`。

推荐流程是：导出前先 `get_export_dataset_stats` 和 `find_duplicate_assets` 做体检；清理重复素材时先人工确认，再调用 `merge_duplicate_assets`；正式交付或备份时用 `export_asset_dataset`。

### 平台采集工具

平台采集已经作为 `platform_source` 分类工具接入智能体：

- `list_platform_source_options`：读取支持的平台和采集类型。
- `list_platform_connections`：列出已配置的平台连接摘要，不返回 Cookie、Token 或凭证内容。
- `search_platform_sources`：按关键词搜索平台内容，风险等级为 `external`。
- `search_platform_sources_enhanced`：增强搜索，支持搜索类型、排序、分页和过滤条件，风险等级为 `external`。
- `get_platform_note_detail`：获取单条内容详情和无水印资源信息，风险等级为 `external`。
- `fetch_platform_no_watermark`：批量获取无水印媒体资源，风险等级为 `external`。
- `import_platform_results_to_assets`：确认后把采集结果导入素材库，风险等级为 `write`。

推荐流程是：先 `list_platform_connections` 确认账号/Cookie 状态，再 `search_platform_sources_enhanced` 找内容；需要媒体资源时调用 `get_platform_note_detail` 或 `fetch_platform_no_watermark`；确认可用后再 `import_platform_results_to_assets` 入库，后续可接 `parse_download_link`、素材血缘和创作项目引用。

## 绑定默认项目和 Skill

在 `Default Context` 页签里配置：

- 默认创作项目 ID：未指定项目时，智能体会自动读取这个项目的上下文包。
- 默认工作流：给智能体一个稳定的工作方向，例如 `character_visual_card`。
- 默认 Skill IDs：选择内置或自定义 Skill，例如 `novel_completion`、`reference_match`。
- 默认上下文 JSON：补充章节号、目标参数等结构化上下文。

默认 Skill 会在每次运行时注入到系统提示里。它不是单纯标签，而是会告诉模型采用哪套工作方法。

## 记忆和 Skill 模板

`Memory` 页签包含两类内容：

- 长期记忆：用户偏好、项目规则、事实片段。
- Skill 模板：可复用工作方法，例如小说补全、角色视觉卡、分镜生成、参考图匹配、漫画生图提示词。

内置 Skill 会自动补齐到数据库。自定义 Skill 可以后续通过 API 或页面扩展创建。

## 查看运行轨迹

每次对话都会创建一个 Agent Run，并记录步骤：

- intake：收到用户请求。
- context_pack：合并默认上下文、项目上下文和记忆。
- llm_response：模型首次判断和工具调用意图。
- tool_call：工具调用结果或待确认状态。
- observe：模型读取工具结果后的继续推理。
- final：最终回复。

在页面中可以查看 Run Timeline、工具结果摘要、原始 JSON、关联项目/素材/任务对象。Run 也可以导出 Markdown，方便复盘和排错。

## 运行时架构优化

### 当前多智能体边界

Agent Center 已有统一 Supervisor/Worker 主链。带 `can_delegate=true` 的 Profile 可以调用 `delegate_agent_tasks`，一次创建最多 6 个子任务；无依赖任务按并发上限运行，带 `depends_on` 的任务按拓扑批次运行。每个子 Agent 使用独立 Thread、独立 `AsyncSession` 和独立 `AgentService`，结果汇合为父 Run 的工具 observation，随后父 `RunLoop` 会继续规划或给出最终答复。运行数据通过 `AgentRun.root_run_id/parent_run_id` 和 `AgentDelegation` 持久化，可由 `/runs/{run_id}/tree` 与 `/runs/{run_id}/delegations` 检查。

运行轨迹中的“委派并续跑”是人工触发的同构入口：它仍通过 `SubagentOrchestrator` 创建子 Run，但汇合成功后会把 observation 送回原父 Run，并在同一条执行树中继续规划。API 调用方可通过 `POST /runs/{run_id}/delegate` 的 `resume_parent` 控制是否立即续跑；旧调用默认仅委派，保持兼容。

边界仍需如实说明：Writer Room 当前的“角色演绎”仍是单模型结构化推演，整条链路是确定性的分阶段写作流水线；专用 `MultiAgentCoordinator` 也尚未迁移到统一运行时。子 Agent 的等待确认、确认结果和取消状态已经能向父级委派步骤传播；等待确认后的自动续跑仍由用户在轨迹中触发，避免确认接口暗中启动新一轮成本型执行。因此这些功能不能提前标成完整团队版 Writer Room。

Agent Center 的运行时核心借鉴了 DeerFlow 2.0（字节跳动 Super Agent Harness 框架）和 Hermes Agent（Nous Research 自演化智能体）的成熟设计模式，在以下方面增强了可靠性和效率：

**上下文压缩**。当对话历史接近模型 token 上限时（默认 12000 token 阈值），系统会自动压缩旧消息为摘要，保留最近 8 条消息完整不变。压缩后的摘要作为系统消息注入，确保模型不会因上下文溢出而丢失关键信息。每次 LLM 调用前都会执行快速令牌预算检查（sentinel 模式），只在必要时触发压缩。

**循环检测**。智能体在工具调用阶段会同时检测两种循环模式：基于 SHA-256 哈希的滑动窗口循环检测（最近 10 轮内同一工具+参数重复 3 次即告警），以及连续同工具计数器（同一工具连续调用 4 次触发警告）。检测到循环后会自动注入提示，引导模型尝试不同策略或给出最终答案。

**记忆置信度评分**。中期记忆增加了 DeerFlow 风格的置信度评分（0.0-1.0），低于 0.7 的记忆不会注入上下文。当同一条记忆被再次确认时，置信度会自动提升 0.1。记忆上下文注入有 2000 token 预算上限，按置信度降序排列，超出部分截断。

**Provider 故障转移**。LLM 调用增加了 Hermes 风格的供应商故障转移链：首选智能体配置的供应商和模型，失败后自动尝试同类型激活的 AI 连接器，最后降级到系统默认模型。确保单个供应商不可用时不会中断工作流。

**多智能体并行执行**。角色演员（role-actor）在场景推演时使用 asyncio.gather 并行执行，默认并发上限为 3。每个演员创建独立会话，状态不共享。异常会被单独捕获，不会因为一个角色失败而中断其他角色的推理。

**渐进式工具加载**。工具注册表支持 `description_short` 字段，可在 `summary_mode` 下先加载一行摘要而非完整描述。当工具数量多时有效降低 token 开销（200 个工具的 token 开销可达 40 个），参考 Hermes 的渐进式 Skill 披露机制。

## 常见问题

### 为什么提示“工具未授权”？

当前智能体的 `Tools` 页签没有勾选该工具。给智能体授权，或切换到拥有该工具权限的智能体。

### 为什么像是只回答一次，没有自动做事？

常见原因是模型没有返回工具调用，或者工具没有授权。检查：

- 该智能体是否有合适的系统设定。
- 是否绑定了默认 Skill。
- 工具是否授权。
- 迭代预算是否大于 1（至少留一轮工具调用空间）。
- Run Timeline 里有没有 `tool_call` 步骤。

### Skill 和工具有什么区别？

工具是真正执行项目操作的函数，比如读取项目、生成正文、匹配素材。Skill 是指导模型如何使用这些工具和组织输出的工作方法。

### 什么时候用默认项目？

当一个智能体长期服务某个创作项目时，可以绑定默认项目。这样你说“继续完善第二章分镜”时，它能自动带上项目上下文，少填参数。

## 字幕和 BGM 后处理工具

字幕作为 `subtitle` 分类工具接入智能体：

- `extract_subtitle`：从本地视频提取字幕或语音转文字，生成 SRT/ASS 文件，风险等级为 `costly`。
- `get_subtitle_styles`：查看可用字幕样式，供提取或烧录字幕时选择。
- `burn_subtitle`：把字幕硬烧录到视频中，生成新视频文件。

BGM 作为 `bgm` 分类工具接入智能体：

- `list_bgm_tracks`：按风格、情绪或关键词搜索曲库。
- `add_bgm_to_video`：把 BGM 混入本地视频，支持音量、淡入淡出和循环控制。
- `upload_bgm`：把本地音频复制到 `data/bgm` 并登记为可检索曲目。

推荐后处理流程是：先用素材库或视频生成工具拿到 `video_path`，再按需要 `extract_subtitle`、`burn_subtitle`、`list_bgm_tracks`、`add_bgm_to_video`，每一步都会返回新的文件路径给后续工具继续使用。

## 剪辑和爆款拆解工具

剪辑作为 `clip` 分类工具接入智能体：

- `start_cutclaw_clip`：按自然语言目标启动 CutClaw 智能剪辑任务。
- `start_narrato_clip`：启动 NarratoAI 自动剪辑流程，按目标时长和候选片段数生成结果。
- `start_moe_clip`：启动 MoE 多专家并行剪辑任务。
- `get_clip_task_status`：轮询剪辑任务状态和输出路径。

爆款拆解作为 `breaker` 分类工具接入智能体：

- `analyze_viral_content`：分析外部视频或内容链接，风险等级为 `external`，会创建异步任务。
- `get_breaker_task_status`：查询爆款分析任务，读取钩子、结构、情绪曲线、角色、分镜和仿写提示。
- `generate_script`：基于主题和可选爆款分析结果生成短视频仿写脚本，风险等级为 `costly`。

推荐流程是：外部链接先 `analyze_viral_content`，再轮询 `get_breaker_task_status`；本地视频剪辑先选择 CutClaw/Narrato/MoE 之一启动任务，再用 `get_clip_task_status` 轮询结果。`generate_script` 只生成文本脚本，不会自动写入创作项目。
