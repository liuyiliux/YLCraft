# YLCraft 上下文库

本目录是项目通用上下文库（SDD 上下文），由 `context-bootstrap` / `context-harvest` / `context-update` 维护。

## 加载规则

1. 入口是 `context-index.yaml`：先按 `stage` + `scope` 筛选，再按 `load_policy` 最小加载。
2. 目录型条目（以 `/` 结尾）先读该目录的 `README.md`，再按证据需要读取具体文件。
3. `.ai-sdd/context/changes/{change-name}/` 为 change 专属上下文，仅在处理该 change 时读取。

## 文件清单

| 分类 | 文件 | 内容 |
|---|---|---|
| 业务 | `business/领域术语与业务对象（domain-glossary）.md` | 任务/观测领域术语 |
| 业务 | `business/业务规则与核验体系（business-rules）.md` | 任务落库、重启对账、重试边界、事件约束 |
| 数据 | `data/核心数据模型（data-model）/` | 三套任务账本 + 两套日志表的分工与字段 |
| 数据 | `data/枚举值字典（enum-dictionary）.md` | scene 取值、任务白名单、状态枚举 |
| 工程 | `engineering/设计约束（design-conventions）.md` | 观测模式、任务粒度、重试实现约束 |
| 工程 | `engineering/接口设计规范（api-style-guide）.md` | API 落点与文档同步流程 |
| 系统 | `system/系统交互关系与调用链（integration-map）.md` | AI 调用/任务/事件/重试的调用链 |

## 与其它权威文档的关系

- **架构总纲**：`docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md`（模块边界、数据模型、文档更新协议）
- **API 目录**：`docs/architecture/API_SURFACE.md` + `api_surface.json`（由 `tools/generate_api_surface.py` 生成，勿手改）
- 本库只保存**可复用的规则与约定**，不重复架构文档的叙述性内容；冲突时以架构文档与源码为准。

## 证据要求

写入本库的事实必须可追溯：带 `文件:行号` 或 change/artifact 来源。命名推断、未验证的类比不写入正式条目。
