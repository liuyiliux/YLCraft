## ADDED Requirements

### Requirement: 系统必须支持把章节正文保存到番茄作家后台草稿

系统 SHALL 提供草稿保存能力，使用登录态 cookie 通过番茄作家后台 Web API 将章节正文（HTML 片段）存为草稿。正式发布不在当前能力范围。

#### Scenario: 存草稿成功
- **WHEN** 调用 `FanqieClient.save_draft(book_id, item_id, title, content_html, volume_name, volume_id)`
- **THEN** 系统用 `httpx` 携带 cookie POST `cover_article/v0/`
- **AND** 返回 `200` 且 `code==0` 时报告成功并携带 `latest_version`

#### Scenario: cookie 过期明确报错
- **WHEN** 番茄返回非 0 错误且消息指向登录态失效，或 HTTP 跳转登录页
- **THEN** 系统抛出可识别的 `CookieExpiredError`
- **AND** 提示用户重新抓取登录态，不静默重试

#### Scenario: 错误被分类
- **WHEN** 发布遇到参数错误、风控拦截或网络异常
- **THEN** 系统区分 `ParamError` / `RiskControlError` / 网络异常并给出可操作提示

### Requirement: 系统必须支持从创作项目将章节正文保存到番茄草稿（核心场景）

系统 SHALL 把番茄发布作为「创作项目」(`/story`) 的发布出口：读取 `ProjectContent(content_type="novel_body")` 的 `text_content`，转换为番茄 HTML 片段后发布，并将回执写入发布记录。

#### Scenario: 从创作项目逐章发布
- **WHEN** 用户在创作项目某章 `novel_body` 触发「保存到番茄草稿」，并提供了番茄 `book_id` / `volume_id` / 章节 `item_id`
- **THEN** 系统调用 `FanqiePublishService.publish_chapter()` 读取该章正文、转 HTML、调 `FanqieClient.save_draft`
- **AND** 在 `ProjectPublishRecord` 写入 `{content_id, book_id, item_id, chapter_number, action, remote_version, status}`

#### Scenario: 发布状态可查
- **WHEN** 用户查看某章发布状态
- **THEN** 系统从 `ProjectPublishRecord` 返回「未保存 / 草稿 + 远程版本号」，避免重复覆盖

#### Scenario: 项目级番茄绑定
- **WHEN** 用户在创作项目设置里绑定番茄
- **THEN** 系统将 `{conn_id, book_id, volume_id, volume_name}` 存于 `CreativeProject.settings_json.fanqie`（或 `ProjectPublishBinding` 表）
- **AND** 发布时默认可从此绑定读取，无需每次重填

#### Scenario: 批量发布
- **WHEN** 用户选中多章并发起发布
- **THEN** 系统逐章调用 `publish_chapters_bulk()`，每章独立回执，单章失败不影响其余章节，且绝不静默重试

### Requirement: 系统必须支持查看番茄作家后台「我的数据」

系统 SHALL 提供对标 B站 `pages/my-data` 的查看能力，通过番茄作家后台 Web API 拉取「我的书 / 章节 / 阅读与收益」等创作数据，在 YLCraft 内统一展示。

#### Scenario: 拉取我的书籍列表
- **WHEN** 用户在「我的数据」页选择已绑定的番茄账号
- **THEN** 系统调用 `FanqieClient.get_my_books(page, size)`（凭证 cookie 即标识作家，无需 writer_id 参数）返回书籍列表（书名 / book_id / 字数等）
- **AND** 数据实时来自番茄作家后台（未启用落库快照；`NovelBookStat`/`NovelEarning` 为可选后续）

#### Scenario: 拉取单书阅读与统计
- **WHEN** 用户选中某本书查看详情
- **THEN** 系统调用 `get_book_stats(book_id, stats_type)`（已落地，真实接口 `book_common_v1/v0`）返回阅读量、追读、投票、评分等
- **AND** 前端按 `stats_type` 切换数据中心子 Tab（基础/质量/流量），未推荐书数据多为 0

#### Scenario: 拉取收益（待抓包）
- **WHEN** 用户查看某书收益/分成
- **THEN** 系统调用 `get_earnings(period)`（**E 组待抓**，任务 25 待用户在已登录浏览器抓 cURL 回填）
- **AND** 当前 `routes.py` 的 `/earnings` 返回 `not_captured` 占位，不展示假数据

#### Scenario: 作家信息（凭证提取）
- **WHEN** 系统绑定番茄凭证并测试连接时
- **THEN** `extract_account_info_from_cookie()` 从 cookie 解析 `writer_id` 写回 `PlatformConnection.account_id` / `account_url`，并用只读 `get_my_books` 探活确认 cookie 存活
- **AND** 作家昵称/头像暂未提取（待 E 组抓包，任务 21）；后续「我的数据」以 `account_id`（writer_id）为查询主键（对齐 B站用 `account_id` 当 uid）

### Requirement: 系统必须支持拉取番茄热门故事灵感

系统 SHALL 提供公域灵感接口，通过 `GET douyin_hot_list/v0/` 拉取热门故事列表辅助创作选题。

#### Scenario: 热榜返回
- **WHEN** 调用 `FanqieClient.get_hot_list(type=0)`
- **THEN** 系统用 `httpx` 携带 cookie GET `douyin_hot_list/v0/`
- **AND** 返回 `200` 且 `code==0` 时解析 `item_list`（书名 / 作者 / 标签 / 摘要 / 字数 / 链接）

### Requirement: 番茄登录态必须复用平台凭证模型

系统 SHALL 将番茄登录态 cookie 存储于 `PlatformConnection.cookie_content`，复用 `AuthType.COOKIE`，无需新增模型字段。

#### Scenario: 平台登记
- **WHEN** 在平台管理中登记番茄
- **THEN** 系统将其加入受支持平台列表，标注凭证类型为 COOKIE、支持查看与发布
- **AND** 现有 cookie 读写逻辑可直接用于番茄

#### Scenario: cookie 解析
- **WHEN** 从 `PlatformConnection` 读取 Netscape 格式 cookie
- **THEN** 系统将其解析为 dict 供 `httpx` 使用

### Requirement: 自动化测试不得触碰用户线上内容

系统 SHALL 在执行任何番茄接口探针或测试时，仅使用独立测试章节（标题含 `[TEST]` 前缀、独立 `item_id`）与独立 cookie，绝不复用用户正在写作的章节。

#### Scenario: 测试章隔离
- **WHEN** 运行客户端验证或测试脚本
- **THEN** 系统针对专用测试章节 / 独立 cookie 操作
- **AND** 不修改用户线上任何书的正式章节内容

#### Scenario: 凭证不入库
- **WHEN** 运行探针脚本
- **THEN** 系统不将真实 cookie 持久化到代码仓库或数据库
