# Tasks

## Phase 1: Inventory and contract

- [x] 1. Inventory every TripoSR caller, environment variable, request field, poll field, and asset ingestion path in Model3DService.
  - _2026-09-25 盘点：唯一 caller 是 `backend/app/api/v1/model3d.py` 的旧 `/api/v1/3d/generate-from-image` 两个端点；旧服务读取 `TRIPOSR_API_BASE` / `TRIPOSR_API_KEY`，本地图片先 multipart 上传，再 POST `/task`，用 GET `/task/{task_id}` 轮询，结果字段是 `result.model_url`，错误字段是 `error`。前端工作台已走 `/api/v1/model-3d/*`，不经过这条 legacy 服务。_
- [x] 2. Confirm whether Model3DConnectorBackend can express upload plus submit plus poll plus download. Extend only the generic contract for gaps and add contract tests.
  - _2026-09-25 落地：通用 backend 原本缺少 multipart 上传；新增 `upload_endpoint` / `upload_field` / `upload_url_path` / `upload_headers` 契约，`submit` 在收到 data URI 且声明上传端点时先上传，再把返回 URL 渲染进 Request 模板。原有 submit/poll/download/诊断保持不变。_
- [x] 3. Add a TripoSR connector preset and response mapping, including error and progress fields.
  - _2026-09-25 落地：新增 `examples/ai-connectors/triposr-image-to-3d.json`，声明 `/upload`、`/task`、`/task/{task_id}`、`$.task_id`、`$.status`、`$.result.model_url`、`$.error`、progress 和终态映射；连接器标记 `legacy_image_to_3d=true`，旧路由只认这个标记，不做任意 3D 连接器回落。_

## Phase 2: Configuration migration

- [x] 4. Add an explicit migration tool: dry-run discovers TRIPOSR configuration and apply creates the connector. Never print the key and never write during application startup.
  - _2026-09-25 落地：新增 `backend/app/services/model3d/triposr_migration.py` 与 `backend/app/scripts/migrate_triposr_connector.py`。默认 dry-run，只有 `--apply` 才写；启动流程不接入；输出 `has_api_key=true/false` 与变更字段，不打印密钥；已有连接器只填空字段，不覆盖人工配置。_
- [x] 5. Add migration tests for missing configuration, base URL only, key present, repeated apply, and readable missing-field errors.
  - _2026-09-25 落地：`backend/tests/test_triposr_connector_migration.py` 覆盖默认 base、缺 key、dry-run 不写、key 存在时创建、重复 apply 幂等、已有手工字段不覆盖。_

## Phase 3: Cutover and legacy removal

- [x] 6. Switch image-to-3D routing to the configuration-driven backend while preserving existing HTTP endpoints and response semantics.
  - _2026-09-25 落地：`Model3DService.generate_3d_from_image` 改为连接器 facade，仍返回旧 `task_id/status/progress/result_url/error`，HTTP 路由与响应 schema 未改。状态 `done -> completed`、`error -> failed`。_
- [x] 7. Remove TripoSR direct HTTP, environment reads, and duplicate polling from Model3DService. Missing connector must return a readable error.
  - _2026-09-25 落地：删除 `_create_triposr_task` / `_get_triposr_task_status`、`httpx` 调用与 `TRIPOSR_*` 运行时读取；找不到标记连接器时返回中文可读错误并提示运行迁移脚本，不隐式回落。_
- [x] 8. Add regression tests for submit, poll, completed download, remote failure, timeout, missing connector, and asset ingestion.
  - _2026-09-25 落地：`backend/tests/test_model3d_workspace.py` 新增 data URI 上传、submit 参数、poll 映射、远程失败、ReadTimeout 诊断、结果下载、`_import_result` 入库 owner/metadata，以及缺连接器和旧服务无 `httpx` / `TRIPOSR` 环境读取的契约测试。_

## Phase 4: Verification and documentation

- [ ] 9. Run a real smoke test with an existing TripoSR configuration. If no provider is available, record it as unverified rather than using a mock as proof.
  - _2026-09-25 本地 dry-run：`action=create`、`base_url=https://api.tripo3d.ai/api/v1`、`has_api_key=false`。当前没有真实 TripoSR key，因此不能运行真实提交/轮询/下载；保持未勾选，不以 mock 冒充供应商验收。_
- [x] 10. Update architecture, API surface, and connector docs with the migration and rollback path.
  - _2026-09-25 落地：总架构 §4.4.2 改写旧 `/api/v1/3d/*` 的 TripoSR 说明；新增 `docs/guides/triposr-connector-migration.md`（dry-run/apply、旧接口语义、无连接器错误、回滚与真实验收边界）；quickstart 与 `examples/ai-connectors/README.md` 增加 preset 入口。HTTP 路由未增删，API surface 事实不变。_
- [x] 11. Run openspec validate triposr-connector-migration --strict.
  - _2026-09-25 验证：focused tests 55 passed；`openspec validate triposr-connector-migration --strict` 通过。_
  - _2026-09-25 全量回归：`pytest -q` 为 `1083 passed, 4 failed, 4 skipped`。4 个失败均在本 migration 未触碰的模块：3 个是 storybook/creative-project 对 `PACKAGE_PLAN_STAGES` 的旧断言与当前 `STORYBOOK_STAGES` 不一致，1 个是 `overlay_text` dry-run 仍断言“不落盘”而当前实现已明确改为一律生成 `_preview.png`。未在本 change 内修改这些无关行为；TripoSR 相关测试均通过。_
