# Tasks

调研已完成。以下为落地任务清单（按推荐路线 A 优先，分三阶段）。

## 阶段 1：后端（已落地，待测试验证）

- [x] 1. 调研腾讯云「查询绑骨蒙皮任务」接口（`DescribeAutoRiggingJob`，`Describe` 前缀，非 `Query`），确认与 `SubmitAutoRiggingJob` 的配对方式。
- [x] 2. 新增绑骨连接器 preset `examples/ai-connectors/tencent-hunyuan-rigging.json`（`capability: "rigging"`，`MotionType` 用 Jinja 条件渲染可选）。
- [x] 3. 数据模型：`Model3DGenerationTask` 加 `kind` 字段（迁移 `014_add_model3d_task_kind`），记录 `source_asset_id`/`source_url`/`motion_type`/`file_type`。
- [x] 4. 新增 `POST /model-3d/rig`：提交绑骨（仅绑骨 / 预设动作）+ 复用轮询 `GET /model-3d/tasks/{id}` + `/history?kind=rigging`；源模型经 `/model3d-files` 暴露公开 URL。
- [x] 5. `/model-3d/backends` 支持 `?capability=` 过滤（generation / rigging 分离）。
- [x] 6. 上传与回流统一提取骨骼/动画元数据，打 `rigged`/`animated` 标签（`assets.py` + `model3d_workspace.py`）。
- [x] 7. 新增绑骨相关单元测试（`test_model3d_workspace.py`）。
- [x] 8. 迁移与测试在目标环境跑通（`alembic upgrade head` + `pytest`）。

## 阶段 2：前端工作台（已完成）

- [x] 9. `/model-3d` 重构为「3D 创作工作台」：两步走（创建模型 → 让模型动起来）+ 素材库网格，替换现有「骨骼绑定方案」占位开关。
- [x] 10. 绑骨入口：Segmented 选择器切换「仅绑骨 / 预设动作（1-48 下拉）」+ 服务商选择器（读 `/backends?capability=rigging`）。
- [x] 11. `Model3DViewer` 增强 `useAnimations` 实际播放/切换骨骼动画（当前只检测不播放）。
- [x] 12. 素材库卡片徽标（静态/已绑骨/带动画）+ 筛选（基于 `metadata_json.has_bones/has_animations` + `rigged`/`animated` 标签）。

## 阶段 3：增强（待做）

- [ ] 13. 本地 UniRig 推理服务（Docker + torch + CUDA）接入工作台「本地 UniRig」入口（路线 B）。
- [ ] 14. TripoSR 纳入配置驱动连接器体系（当前 legacy 硬编码在 `Model3DService`，未走 AIConnector）。
- [ ] 15. 本地格式转换/预览生成（`generate_preview`/`convert_format` 现为 TODO 占位）。
- [ ] 16. 真实供应商验收：用已开通的腾讯云账号跑通「图生 3D → 绑骨蒙皮 → 带骨骼模型入库 → 查看器渲染」全链路，记录诊断与费用。
- [x] 17. 同步更新 `docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`、`docs/architecture/API_SURFACE.md` 与 `api_surface.json`（新增 `/model-3d/rig` 等）。
