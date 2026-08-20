# 2026-08-20 预演台 Phase 1 落地交接

## 项目目标

YLCraft 3D 导演预演台：分镜生成前在轻量 3D 空间里确定人物站位、机位与构图，截图作为参考进入生图/视频链路，降低抽卡成本。参考项目：storyai-3d-director-desk / kunpeng-director / Wasserman Filmmaker Suite 等（见 `docs/reference/REF_PROJECTS.md`）。

## 已改文件（本提交）

- 后端：`backend/app/db/models/previs.py`（三字段可空）、`backend/app/api/v1/previs.py`（独立场景创建）、`backend/alembic/versions/018_allow_standalone_previs_scenes.py`（新增）、`backend/tests/test_previs_scenes.py`（+2 独立场景用例）
- 前端：`frontend/src/pages/previs/index.tsx`（独立场景列表工作台 + 新建场景 + 相机面板 + 姿势下拉）、`SceneViewport.tsx`（相机 rig / 双视角 / 安全框九宫格 / 胶囊人渲染）、`frontend/src/components/three/humanProxy.tsx`（新增，程序化姿势人形）、`frontend/src/components/layout/AppLayout.tsx`（顶级导航「3D 预演」+ 导航去重）、`frontend/src/api/index.ts`（PrevisScene 类型/创建参数放宽）
- 文档：`docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`、`docs/architecture/3D_DIRECTOR_PREVIS_DESIGN.md`、`docs/README.md`、`docs/reference/REF_PROJECTS.md`、`openspec/changes/3d-director-previs/tasks.md`（任务 10 勾选）

## 当前进度

Phase 1 静态导演台全部代码落地：

- `PrevisSceneDocument` 持久化 + revision CAS；独立场景（不绑定项目分镜）与绑定分镜场景并存
- `/story` 分镜卡片入口 + 顶级导航入口（无场景时显示独立场景列表工作台，可新建场景）
- 节点管理：Asset Hub 模型 / 可摆姿势程序化人形（6 姿势预设）/ 几何体 / 全景背景 / 显隐 / 重命名 / 删除 / 锁定
- 相机 CRUD（名称/位置/目标点/FOV/锁定）+ 导演/活动机位双视角 + 安全框/九宫格只读叠加

## 验证结果

- 后端：`backend\tests\test_previs_scenes.py` 8 passed
- 前端：`npm run build`（含 tsc --noEmit）通过 ×多次
- `git diff --check` 干净
- 远程 PostgreSQL 已 `alembic upgrade head` 到 018（017 事件日志 + 018 独立场景可空列已落库）

## 待办任务

1. 任务 11：活动机位截图 PNG/WebP → Asset Hub 图片 → `ProjectAssetLink` → 分镜面板参考字段
2. 任务 12：截图进入既有生图/视频请求链路（保留 `previs_scene_id`/`camera_id`/revision provenance）
3. 任务 13：桌面/窄屏实机验证 + focused 前端测试
4. 活动机位拖拽回写 transform（目前活动机位模式禁用 OrbitControls）
5. 独立场景标题编辑（保存接口已支持 title，前端未接）
6. Phase 2：24fps 播放头、关键帧、相机/变换插值
7. Phase 3：Agent 导演助手（只读场景摘要 + 受控 `PrevisOperation` Tool）

## 关键决策

- 独立场景：`project_id`/`storyboard_content_id`/`panel_number` 全空即独立场景；绑定场景才做去重检查（409）
- 人形占位改为程序化胶囊人（参照 storyai ProceduralMannequin 的 MIT 思路自写），无外部模型、无版权风险；awplanet（Noncommercial）与 costage（无 LICENSE）素材禁用
- 入口对齐参考项目主流：顶级导航 + 场景列表工作台，分镜卡片入口保留为快捷路径

## 报错细节

- PowerShell 会把 python stderr 的 alembic INFO 日志误报为 RemoteException/exit 1；以 `alembic current` 为准（已在 018 head）
- 远程库迁移之前因网络超时失败；本次 VPN 连通后成功

## 下一步建议

先做任务 11 截图回流（需浏览器实机验证活动机位视角），或先补活动机位拖拽回写。提交前跑 `backend\tests\test_previs_scenes.py` 与 `frontend npm run build`。
