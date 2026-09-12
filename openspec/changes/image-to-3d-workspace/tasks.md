# Tasks

- [x] Add explicit `3d` AI connector type and database migration path.
- [x] Add durable image-to-3D task ledger.
- [x] Add configuration-driven submit/poll/download adapter.
- [x] Add independent image-to-3D APIs and Asset Hub import with source lineage.
- [x] Add independent `/model-3d` page and navigation entry.
- [x] Add focused contract tests and update architecture/API documentation.
- [x] Add a credential-free Tencent Hunyuan 3D Pro connector preset authenticated with TC3-HMAC-SHA256 (`api_format=tencent_tc3`, `SecretId:SecretKey`), including the TC3 signing path and POST polling template support in the adapter.
- [x] Run a real configured provider from the page and verify a downloaded GLB opens in the asset viewer.
  - _2026-09-12 完成，过程中发现并修复了一个阻断性 bug：_
    - _真实执行（从页面、非 mock）：真实浏览器打开 `/model-3d` → 点「创建模型」展开面板 → 切「文生 3D」→ 填描述 → 点「生成 3D 模型」；Provider `Tencent Hunyuan 3D Pro (示例)` model `3.0`，供应商回执 `ResultCreditConsumed: 20`（**真实消耗 20 点**）。任务 `model3d_b8ff9ed07bc747e3971687be4a61793c` `status=done`，产出 28.46 MB GLB，资产 `986a044a-51d2-415a-875a-a4715c9e3db5`。_
    - _**阻断性 bug（已修）**：生成物在磁盘上且已注册进 Asset Hub，但 `/api/v1/assets/{id}/download` 返回 404「文件不存在」，查看器因此打不开模型。根因是 **`to_storage_path` 被重复调用**——`facade.create_generated_image` 先转一次得 `backend/app/storage/...`，`AssetRepresentationService.create` 又转一次；而该函数用 `Path(path).resolve()` **按进程 CWD 解析相对路径**（uvicorn 的 CWD 是 `backend\`），于是拼成 `backend/backend/app/storage/...`。同一文件内 `resolve_storage_path`（读）按**项目根**解析，两者**不对称**。_
    - _代码修复：`backend/app/services/asset_file_resolver.py::to_storage_path` 改为相对路径按项目根解析（与读取端对称），使函数**幂等**——一次修好全部双重调用点（facade L106/L297、characters L1460/L1488、assets L907）。已验证连续调用三次结果一致。_
    - _数据修复：全库 796 个文本列扫描确认**只有** `asset_representations.file_path` 命中 `backend/backend/`，共 **26 行**（2026-09-01 〜 09-12，含图片/3D/视频）。已备份原文后更新，残留 0 行，**26/26 均可还原到真实文件**。回滚备份：`tmp/backup_doubled_paths.json`。_
    - _修复后终验（真实浏览器，只读不耗额度）：`/api/v1/assets/986a044a.../download` 返回 **206 + `glTF` 魔数**；`/model3d-viewer/{assetId}` 渲染 **WebGL 900×1000 canvas**、无「加载失败」、**全程零 >=400 响应、零控制台 error**（修复前为 1 条 404）。_
    - _回归验证：`pytest -k "asset or resolver or novel_source or model3d or model_3d or creative_project"` → **305 passed / 2 skipped**。_
    - _待办（未做，需环境操作）：后端 uvicorn 以**非 `--reload`** 方式运行，代码修复需**重启后端**才对后续新生成生效（存量数据已修好，当前读写已正常）。_
