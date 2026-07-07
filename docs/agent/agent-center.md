# Agent Center 使用说明

Agent Center 是 YLCraft 的项目智能体工作台。它不是单次问答页，而是把“智能体设定、模型、工具授权、长期记忆、默认项目、默认 Skill、运行轨迹”放在一起，方便后续把创作项目、素材库、角色库、分镜和生图流程串起来。

## 创建或复制智能体

1. 打开前端 `/agent`。
2. 在左侧智能体列表选择一个现有智能体。
3. 点击右上角设置按钮，打开“智能体设定”抽屉。
4. 点击“复制新建”可以从当前智能体复制一份。
5. 在 `Profile` 页签里改名称、头像标识、角色和定位说明。

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
- `write`、`delete`、`external`、`costly` 风险工具会先生成待确认步骤，用户确认后才执行。

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

AI 连接器已经作为 `ai_config` 分类只读工具接入智能体：

- `list_ai_connectors`：按 `llm/image/video/tts/stt/embedding` 列出当前启用的模型配置、默认模型、可用模型、能力和使用统计。
- `get_ai_connector`：读取单个连接器的非敏感详情，包括 SDK/HTTP 模式、请求模板、响应解析、默认参数、尺寸和参考图能力。

这些工具不会返回 API Key，也不会触发连接测试或模型调用。推荐流程是：智能体需要选模型时先查 `list_ai_connectors`，遇到配置疑问再用 `get_ai_connector` 看非敏感详情。

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
