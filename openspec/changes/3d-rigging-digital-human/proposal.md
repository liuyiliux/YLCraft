# 3D 骨骼绑定与数字人

## 背景

现有 `/model-3d` 图生 3D 工作台（`provider_type: "3d"`，配置驱动连接器，走腾讯混元 TC3 签名）产出的是**静态网格**（GLB/OBJ/FBX），无骨骼、无蒙皮、无动画。产品希望在「图生 3D」之后继续延伸「骨骼绑定 → 数字人」能力，让生成的角色能「动起来」。

本文记录调研结论、三条候选路线，以及截至 2026-08-18 的实现进度，供后续 AI 接手时避免重复调研。

## 关键事实（已确认）

1. **腾讯混元生 3D 已原生提供「绑骨蒙皮」接口**：`SubmitAutoRiggingJob`（域名 `ai3d.tencentcloudapi.com`，Version `2025-05-13`，与现有 `SubmitHunyuanTo3DProJob` 完全同域名同版本同 TC3 签名）。
   - 输入 `File3D.Url`（FBX/GLB，≤60MB）+ `File3D.Type`，可选 `MotionType`（48 种预设动作：待机/走路/奔跑/街舞/回旋踢等，int 1-48）。
   - 输出 `JobId`（有效期 24h），经「查询绑骨蒙皮任务」接口（**`DescribeAutoRiggingJob`**，注意是 `Describe` 前缀，与图生 3D 的 `Query` 前缀不同）轮询得到带骨骼模型，`Status` 取 `WAIT/RUN/FAIL/DONE`。
   - 约束：人形需 A-Pose/T-Pose，不带武器/坐骑/翅膀等外部组件。
   - 参考文档：https://cloud.tencent.com/document/product/1804/131618
2. 混元生 3D 还提供「文生动作」「3D 人物生成」「智能拓扑」「纹理生成」「UV 展开」「组件生成」「格式转换」等下游能力（产品概述：https://cloud.tencent.com/document/product/1804/120696）。
3. 项目当前**无本地重模型推理基础设施**：`backend/requirements.txt` 无 `torch`，无 GPU 假设；后端是「轻后端 + 配置驱动调外部 API」模式。
4. 现有 Live2D 的「绑骨（`rigging.py`）/口型（`lip_sync.py`）」是**纯代码占位**（固定比例估算、RMS 近似），`mesh`/`physics` 接口返回 501，不是可依赖的真实能力。

## 三条候选路线

| 路线 | 做法 | 与现有架构贴合度 | 成本/风险 |
| --- | --- | --- | --- |
| A. 接 API | 复用现有 `Model3DConnectorBackend` 配置驱动模式，新增绑骨蒙皮/文生动作能力 | 最高，架构零改动、纯加配置 | 低（需腾讯云开通对应接口） |
| B. 本地跑 UniRig | 开源 MIT（清华+Tripo），本地部署 `torch + CUDA GPU ≥ 8GB` | 低，需引入全新本地推理基础设施 | 高（需 GPU 服务器） |
| C. 混元云端 Studio 手动 rig | 用户在混元 3D Studio 手动绑骨再导出回传素材库 | 中，无需后端能力，仅依赖上传 + 骨骼识别 | 无自动能力 |

- 开源参考：UniRig（https://github.com/VAST-AI-Research/UniRig ，MIT，输入 GLB/OBJ/FBX/VRM → 输出骨架+蒙皮 rigged 模型）。
- 2D 数字人口型驱动（独立方向，非本 change 主目标）：SadTalker / MuseTalk / EchoMimic / LiveTalking 等，均属「本地 GPU 重推理」，若要落地需单独立项并确认硬件。

## 推荐与实现决策

- **优先落地路线 A（接混元绑骨蒙皮 API）**：与现有图生 3D 实现模式完全同构，可复用连接器/TC3 签名/任务账本/Asset Hub 回流的既有代码。
- **绑骨蒙皮拆成两种独立调用**（同一入口，用选择器切换）：
  - **纯绑骨蒙皮**：`SubmitAutoRiggingJob` 只传 `File3D`，**不传 `MotionType`** → 输出仅带骨骼、无动作的模型，可在 Blender/Unity 中二次操控。
  - **绑骨蒙皮 + 预设动作**：额外传 `MotionType`（1-48）→ 直接套一个预设动作。
- **服务商统一抽象**：绑骨走 `provider_type="3d"` 的配置驱动连接器，通过 `response_config.capability` 区分 `generation`（图生/文生 3D）与 `rigging`（绑骨蒙皮），UI 上服务商选择器天然支持非混元 API 与未来本地 UniRig。
- **素材库区分骨骼模型**：上传/生成入库时统一用 `Model3DService.extract_metadata` 提取 `bones`/`animations`，写入 `metadata_json` 的 `has_bones`/`has_animations` 并打 `rigged`/`animated` 标签，供素材库徽标展示与筛选（同时覆盖路线 C：混元 Studio 绑完骨上传回来自动识别为「已绑骨」）。

## 当前状态（2026-08-18 后端已落地，前端待做）

### 已完成（阶段 1 后端）

- 迁移 `014_add_model3d_task_kind.py`：给 `model3d_generation_tasks` 加 `kind` 列（`generation` / `rigging`），生成与绑骨历史可分列。
- `Model3DGenerationTask.kind` 字段（默认 `generation`）。
- 新增绑骨连接器 preset `examples/ai-connectors/tencent-hunyuan-rigging.json`（`SubmitAutoRiggingJob` / `DescribeAutoRiggingJob`，`request_template` 用 Jinja 条件渲染 `MotionType`，`response_config.capability: "rigging"`）。
- `model3d_workspace.py` 新增 `POST /model-3d/rig`（`Model3DRigRequest`：`source_asset_id`/`source_url` + 可选 `motion_type` 1-48 + `file_type`）；源模型本地文件复制到 `storage/model3d/public` 并经 `/model3d-files` 静态挂载暴露为公开 URL（腾讯绑骨接口仅接受公开 URL）。
- `/model-3d/backends` 支持 `?capability=` 过滤；`/model-3d/history` 支持 `?kind=` 过滤；`_task_dict` 输出 `kind`。
- `assets.py` 上传 3D 模型时提取骨骼/动画元数据并打 `rigged`/`animated` 标签。
- `main.py` 挂载 `/model3d-files` 静态目录。
- 新增绑骨相关测试（`test_model3d_workspace.py`）。

### 待做（阶段 2 前端）

- `/model-3d` 重构为「3D 创作工作台」（两步：创建模型 → 让模型动起来），替换现有「骨骼绑定方案」占位开关。
- 绑骨入口用选择器切换「仅绑骨 / 预设动作」+ 服务商选择器。
- `Model3DViewer` 增强：`useAnimations` 实际播放骨骼动画（当前只检测 `hasAnimation` 显示「支持」，不播放）。
- 素材库卡片徽标（静态/已绑骨/带动画）+ 筛选。

### 待做（阶段 3 增强）

- 本地 UniRig 推理服务（Docker + torch + CUDA）接入工作台「本地 UniRig」入口。
- TripoSR 纳入配置驱动连接器体系（当前 legacy 硬编码在 `Model3DService`，未走 AIConnector）。
- 本地格式转换/预览生成（`generate_preview`/`convert_format` 现为 TODO 占位）。
