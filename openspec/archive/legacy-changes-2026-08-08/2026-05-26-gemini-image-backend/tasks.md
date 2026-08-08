## 1. 依赖安装

- [x] 1.1 `requirements.txt` 新增 `google-genai>=1.0.0`

## 2. GeminiImageBackend 实现

- [x] 2.1 创建 `backend/app/services/image/gemini_image_backend.py`
- [x] 2.2 实现 `__init__()`：创建 `genai.Client(api_key, http_options={"base_url": ...})`
- [x] 2.3 实现 `generate()`：构建 `contents`（支持纯文本和图生图多模态）
- [x] 2.4 实现图片提取：遍历 `parts` 提取 `inline_data`，保存到本地
- [x] 2.5 实现 `health_check()` 和 `close()`

## 3. Manager 路由

- [x] 3.1 `manager.py` `_init_image_backend()` 新增 `gemini` provider 路由分支
- [x] 3.2 Gemini Backend 初始化失败时降级到 GenericImageBackend

## 4. 前端预设

- [x] 4.1 `PROVIDER_PRESETS.gemini.image` 配置默认值
- [x] 4.2 预设包含 `default_model: "gemini-2.5-flash-image"`、`base_url`、`supported_sizes`

## 5. 导出/导入

- [x] 5.1 `ai_connectors.py` 导出函数确认 `provider: "gemini"` 可正常导出

## 6. 验证

- [ ] 6.1 测试文生图：prompt → Gemini → 图片保存本地
- [ ] 6.2 测试图生图：prompt + 参考图 → Gemini → 图片保存本地
