# 核实：文章转述 vs 仓库事实（2026-10-16）

> **起因**：所有者追问「纯文章提到的项目，你实际链接看项目了吗」——
> 答案是**没有**，这是个疏漏。本文件是补做的核实。
> 方法：GitHub API + 浏览器打开仓库实读。

---

## 〇、核实结果一览

| 项目 | 文章说的 | **仓库实际** | 判定 |
| --- | --- | --- | --- |
| **BeefTV** | 「桌面软件，不是网站」「Go 后端 + React 前端，**Wails 打包**」「约 200MB 安装包」 | **Docker 部署的 Web 服务**（`Dockerfile` / `docker-compose*.yml` / `nginx.conf` / `render.yaml`），无 Wails 打包 | ❌ **不实** |
| **Infinite Canvas** | 未提许可 | **AGPL-3.0** | 🔴 **文章漏了关键信息** |
| **Infinite Canvas** | 未提 Agent 接入方式 | 有 **`canvas-agent/`** + `skills-lock.json` + `.agents/` | ⚠️ **不完整** |

---

## 一、BeefTV

### 1.1 真实仓库

| 项 | 值 |
| --- | --- |
| 仓库 | **`glanderness/BeefTV`**（🔴 **文章没给地址**） |
| Star / Fork | **1444 / 276**（文章说"超一千 star"✅ 吻合） |
| 许可 | **MIT** ✅ 与文章一致 |
| 定位 | 「High-performance · Lightweight · AI Native Video workspace」 |

> ⚠️ 搜索时发现**至少 6 个 fork**（`liangkunnhello`、`hejianlan`、`juanxincai23` 等），
> 说明它在中文圈有人二次分发 —— 这本身是"有人在用"的信号。

### 1.2 🔴 文章最不可靠的一处：形态说错了

**文章说**：
> 「BeefTV 是个**桌面软件**，不是网站，得下安装包装在电脑上用。
> Mac 和 Windows 都有安装包，Linux 有个 DEB 包。
> 技术上是 Go 写的后端加 React 前端，拿 **Wails** 打的包，安装包大概 200 MB。」

**仓库实际根目录**：
```
go.mod  go.sum  main.go  handler/  router/  service/  model/  middleware/
Dockerfile  docker-compose.yml  docker-compose.dev.yml
docker-compose.local.yml  docker-compose.build.yml
nginx.conf  render.yaml
web/            ← 前端
backend/  agent-host/  plugin-packages/  tools/  scripts/
docs/  fixtures/  assets/  build/
```

**判定**：这是**标准 Go Web 服务 + Docker 部署**，
有 `nginx.conf` 和 `render.yaml`（Render 平台的 PaaS 部署配置）。
**没有 Electron/Tauri/Wails 桌面打包**，**也没有 200MB 安装包的证据**。

> 💡 **这条差异很重要**：
> 我之前基于文章写了"桌面软件，需下载安装"到文档里 —— **那是错的**。
> 实际它跟我们的形态更接近（Web 服务 + 画布），**部署方式可参考**。

### 1.3 文章没提但值得注意的

| 文件 | 含义 |
| --- | --- |
| `AGENTS.md` | 🔴 **它也有 `AGENTS.md`** —— 和我们仓库的约定一样 |
| `THIRD_PARTY_NOTICES.md` | 第三方声明齐全（合规意识） |
| `SECURITY.md` / `CODE_OF_CONDUCT.md` / `CONTRIBUTING.md` | 社区文件完整 |
| `plugin-packages/` | 🔴 **有插件包机制**（文章只说"内置 BeefAPI 渠道"） |
| `agent-host/` | Agent 宿主是独立目录 |
| `fixtures/` | 有测试夹具 |

---

## 二、Infinite Canvas

### 2.1 真实仓库

| 项 | 值 |
| --- | --- |
| 仓库 | `tigerowo/infinite-canvas` ✅（文章给了） |
| Star / Fork | **1207 / 265** |
| 定位 | 「开源 AI 创作工作台，集成无限画布、Agent、**导演台**、全景图、AI 生图、图片编辑、视频生成、画布编排等」 |
| 技术栈 | Go 后端（`go.mod` / `main.go` / `handler` / `router` / `service` / `model` / `middleware`）+ `web/` |

### 2.2 🔴🔴 最重要的发现：**AGPL-3.0**

```
LICENSE: AGPL-3.0
```

**文章一个字都没提许可。**

> 🚨 **这是实质风险**：
> AGPL-3.0 是强传染许可，**若把它的代码并入 YLCraft，
> 可能要求整个 YLCraft 开源**。
>
> - **可以**：学设计思路（思路不受版权保护）
> - **不可以**：直接抄代码
> - **要接**：必须单独做法务判断
>
> **这条必须补进我们的调研结论**，之前那篇文章没提，等于误导。

### 2.3 文章没提的目录

| 目录 | 含义 |
| --- | --- |
| **`canvas-agent/`** | 🔴 Agent 接入层（文章只说"Codex 可通过本机 Canvas Agent 服务接入"） |
| **`skills-lock.json`** | 🔴 **有 skill 锁文件** —— 说明它也有 skill 体系 |
| **`.agents/`** | 🔴 **用了 `.agents/` 目录约定** —— 和我们一样 |
| `skills-lock.json` + `.agents/` 并存 | 说明 skill 是可锁定依赖，不是散装文件 |

---

## 三、三方对照更新（加上许可维度）

| 项目 | 许可 | 形态 | 我看过界面吗 |
| --- | --- | --- | --- |
| **OhMyGame** | Apache 2.0 | **Electron 桌面应用**（217.7MB） | ✅ **看了**（2026-10-16 实装） |
| **BeefTV** | MIT | **Docker Web 服务**（文章误写为桌面） | ❌ |
| **Infinite Canvas** | 🔴 **AGPL-3.0** | Docker Web 服务（18080 端口） | ❌ |

> 💡 **许可维度是这个表最重要的一列** ——
> 三家里两家允许商用集成（MIT / Apache-2.0），
> **一家（AGPL-3.0）不能**。

---

## 四、我自己的失误记录

这一轮暴露了三个问题，记下来：

| # | 失误 | 教训 |
| --- | --- | --- |
| 1 | **BeefTV 文章没给仓库地址，我没去找就写了** | 只给文章链接时，**必须去核实真实来源** |
| 2 | **把"桌面软件/需安装"写进了文档** | 转述的形态描述**必须核实** |
| 3 | **没注意 Infinite Canvas 的 AGPL** | 🔴 **许可信息永远要单独核实**，这是接入的前提 |

> ✅ 已在 `2026-10-16_handraw_ohmygame_infinitecanvas.md` 顶部标注"仅文章来源"，
> 本文件补上核实结果。**后续文档引用这两个项目时，必须带上许可列。**

---

## 五、待核实

| 项 | 状态 |
| --- | --- |
| BeefTV 的真实界面 | `未看` —— 但现在知道它是 Docker Web 服务，**可以本地起** |
| BeefTV 的 `plugin-packages/` 有什么插件 | `未看` |
| Infinite Canvas 的 `skills-lock.json` 内容 | `未看` |
| Infinite Canvas 的 `canvas-agent/` 实现方式 | `未看` |
| 两者的 AGPL/MIT 具体条款 | MIT 已确认；**AGPL 影响范围需法务判断** |
| OhMyGame 有内容时的画布 | `待模型 Key` |