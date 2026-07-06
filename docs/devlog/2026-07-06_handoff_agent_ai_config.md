# 2026-07-06 交接总结：模型配置智能体

## 项目目标

完善 YLCraft 的通用 AI 模型配置智能体：用户提供任意供应商规范、curl 示例或 API 文档后，智能体可创建/更新供应商规范和模型连接器，并能测试普通生图与图片编辑模型。aaccx 的 `gpt-image-2 /v1/images/edits` 仅作为测试样例，不作为默认内置模型。

## 已改文件

| 文件 | 变更 |
| --- | --- |
| `backend/app/services/agent/profile.py` | 新增通用内置智能体 `ai-config-specialist`；修复内置 profile 同步时覆盖用户 provider/model 的问题；同步默认上下文 |
| `backend/app/services/agent/tools/ai_config_tools.py` | JSON 参数解析失败时返回明确错误；`test_ai_connector` 支持 `image_url/image_path/image_mode/request_content_type/response_format` |
| `backend/app/services/ai_connector/service.py` | 连接器测试支持图片编辑 `/images/edits`；公网图片走 JSON，本地文件走 multipart；测试模板支持 `*_json` 安全变量 |
| `backend/app/services/ai/backends/image/generic.py` | 正式图片生成链路支持 multipart、本地 Windows 绝对路径、`images_json`、编辑模型默认 `b64_json` |
| `backend/alembic/versions/001_initial_schema.py` | 修复 squash 迁移缺少 `import sqlmodel` 的问题 |
| `backend/tests/test_agent_center.py` | 增加迁移 import 与 JSON 参数错误测试；保持 profile 模型偏好测试通过 |
| `backend/tests/test_ai_image_async.py` | 增加 aaccx JSON 编辑、multipart 编辑、正式后端 multipart 发送测试 |

## 当前进度

- 通用内置智能体已写入远程数据库：
  - `ai-config-specialist | AI 模型配置专家 | builtin=True`
- 数据库确认是远程库：
  - `backend/.env` 指向 `81.70.219.37:5432/ylcraft`
- aaccx 没有被硬塞为默认连接器；它只保留在测试中验证通用能力。
- 图片编辑链路已支持：
  - JSON：`images: [{ "image_url": "https://..." }]`
  - multipart：`image=@本地文件`

## 验证结果

- `backend\venv_win\Scripts\python.exe -m pytest backend/tests/test_ai_image_async.py -q`：9 passed
- `backend\venv_win\Scripts\python.exe -m pytest backend/tests/test_agent_center.py -q`：70 passed
- `compileall`：通过
- 远程库查询已确认能看到 `AI 模型配置专家`

## 关键决策

- 模型配置智能体必须是通用智能体，不绑定 aaccx。
- aaccx 只作为 OpenAI-compatible 图片编辑接口的测试样例。
- 维护脚本/一次性脚本必须显式加载 `backend/.env`，否则会退回默认 localhost 数据库。
- 内置 profile 同步不能覆盖用户已经设置过的 `provider/model`。

## 待办任务

- 设置页接入“用智能体配置模型”的入口，让用户在模型配置页直接把供应商规范发给 `AI 模型配置专家`。
- 在 UI 中清晰展示 `test_ai_connector` 的请求摘要、响应摘要和错误诊断。
- 后续可补一个“从 curl 自动解析 provider/connector 草稿”的预览工具，写入前让用户确认。

## 报错细节

- 页面看不到新智能体：原因是第一次脚本未加载 `.env`，误连默认 localhost；后续加载 `backend/.env` 后已同步到远程库。
- 页面看不到新模型：原因是未创建具体连接器；这是正确状态，因为 aaccx 不应作为默认硬编码模型。
- `test_agent_chat_uses_selected_profile_model_preferences` 失败：内置 profile 同步覆盖了测试/用户设置的 `provider/model`，已改为只在默认值非空且当前为空时填充。
- 通用图片后端原先不支持 Windows 绝对路径和 multipart，已修复。
