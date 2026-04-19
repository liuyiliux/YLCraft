# YLCraft — 开发进度

> 最后更新：2026-04-19
> 设计文档：`DESIGN.md`

---

## 当前状态总览

```
[████████████████████████████████████████████████]  ~95%
```

| 模块 | 状态 | 说明 |
:|------|------|------|
| 需求分析 | ✅ 完成 | 5 个开源项目源码分析 |
| 系统设计 | ✅ 完成 | 完整架构设计文档 |
| BackendManager | ✅ 完成 | Protocol + Registry + YAML + Manager |
| Backend 实现 | ✅ 完成 | 7 个 Backend |
| API 层 | ✅ 完成 | Provider/LLM/Images/TTS/Breaker/Story 端点 |
| CutClaw 模式 | ✅ 完成 | Agent 工具调用 + FFmpeg 渲染 |
| NarratoAI 模式 | ✅ 完成 | Pipeline 流水线（纪录片/短剧）|
| MoE 多专家 | ✅ 完成 | 三专家 + ControlPlane 编排器 |
| 爆款拆解 | ✅ 完成 | Breaker API + 内置视频解析（yt-dlp）|
| Story Maker | ✅ 完成 | 角色库 + 分镜 Agent + 一致性检查 + 9 个 API 端点 |
| OpenClaw Skill | ✅ 完成 | 10 个 Skill 脚本（breaker/clip/story/llm/image/tts）|
| 前端 Phase 1 | ✅ 完成 | 6 个页面 + 路由 + API Client |
| 前端 Phase 2（素材库） | ✅ 完成 | 素材库 Grid + 搜索 + 标签 + 详情抽屉 + 引用机制 |
| 前端 Phase 3（后台下载） | ✅ 完成 | 后台任务队列 + 轮询进度，解决大文件 XHR 超时 |
| 前端 Phase 4（角色管理） | ✅ 完成 | 角色 CRUD + 来源标签 + 定位 + 收藏/冻结 |

---

## 已完成 ✅

### 需求分析
- [x] **ArcReel 源码分析** — Protocol + Dataclass + Registry 架构
- [x] **Jellyfish 源码分析** — Provider 注册表 + LangChain Agent
- [x] **MoneyPrinterTurbo 分析** — YAML 配置 + if-else 分发
- [x] **CutClaw 源码分析** — LLM Agent Tool Calling 剪辑
- [x] **NarratoAI 源码分析** — Pipeline 流水线 + Provider 双模式
- [x] **montage-ai 源码分析** — MoE 多专家协作架构

### 系统设计
- [x] **DESIGN.md 完成** — 完整设计文档，涵盖：
  - 系统架构（BackendManager / Agent / Provider）
  - BackendManager 核心实现（Protocol + Registry + YAML）
  - Clip Lab 三大模式（CutClaw / NarratoAI / MoE）
  - 爆款拆解服务设计
  - OpenClaw Skill 设计
  - 技术选型

---

## 决策记录 📋

### 决策 1：模型抽象层方案
**问题**：如何设计可替换的模型调用层？
**选择**：融合 ArcReel（Protocol + Dataclass）+ Jellyfish（Provider 注册表）+ MoneyPrinterTurbo（YAML 配置）
**原因**：ArcReel 最完整，但 Jellyfish 的注册表有别名解析和线程安全优势，MoneyPrinterTurbo 的 YAML 配置最简单易用
**日期**：2026-04-15

### 决策 2：剪辑工具架构
**问题**：Clip Lab 采用哪种 AI 剪辑方案？
**选择**：三种模式并存：CutClaw（Agent 驱动）+ NarratoAI（Pipeline）+ MoE（多专家）
**原因**：不同场景适合不同方案，CutClaw 适合智能判断，NarratoAI 适合固定流程，MoE 适合精细控制
**日期**：2026-04-15

### 决策 3：OpenClaw 集成方式
**问题**：如何让 AI Agent 调用平台能力？
**选择**：Skill 封装 REST API，Skill 脚本通过 HTTP 调用后端
**原因**：Skill 是 OpenClaw 的标准扩展方式，且不侵入后端代码
**日期**：2026-04-15

### 决策 4：资产库（素材库）架构
**问题**：资产管理的层次结构如何设计？
**选择**：
- 底层：统一资产库（Asset Library），支持多种资产类型（视频/图片/音频/角色/商品/场景/道具）
- 角色作为资产的一种类型（CHARACTER），与视频/图片并列
- 素材库页面 → 资产库（改名）
- 角色管理页面暂时保留，未来可整合进资产库的"角色" Tab
**原因**：
  - 角色是 Story Maker 的核心，但也是其他场景（电商/摄影）共用的元素
  - 统一资产库避免数据分散，引用机制更简单
  - 电商/摄影/短剧的区别在于"场景"和"用途"，不在于资产本身
**日期**：2026-04-19

### 决策 5：功能维度 vs 用户场景维度
**问题**：功能模块按什么维度组织？
**选择**：以功能模块为维度组织，用户场景（电商/摄影/短剧）作为标签/分类属性
**原因**：
  - 爆款拆解 → 电商/摄影/短剧 都用
  - 视频剪辑 → 电商/摄影/短剧 都用
  - AI 生成 → 所有场景共用
  - 素材库 → 所有场景共用
**日期**：2026-04-19

---

## 技术债务 🏚️

- [ ] FFmpeg 环境依赖未验证（Windows 兼容性）
- [ ] Madmom 在 Windows 上的安装问题
- [ ] CogVideoX 本地部署指南缺失
- [ ] Provider API Key 安全存储（目前明文/环境变量）
- [x] 后台下载任务 ✅ 已实现（BackgroundTasks + 内存任务表 + 轮询）

---

## 下一步行动 →

**当前状态**：Phase 1-3 前后端核心功能全部完成

### 已完成 ✅
1. [x] Story Maker（角色立绘 + 分镜脚本 + 分镜图 + 9 API 端点）
2. [x] 视频解析内置集成（抖音/快手/B站/小红书/微博 + yt-dlp 兜底）
3. [x] yt-dlp 去水印下载（yt-dlp + httpx 双策略）
4. [x] Story Maker Agent 实现（CharacterLibrary + FilmShotlist + ConsistencyChecker）
5. [x] 资产库前端（Grid + 搜索 + 标签 + 详情抽屉 + 引用机制）— 原"素材库"
6. [x] 后台下载任务（BackgroundTasks + 内存任务表 + 轮询，解决大文件 XHR 超时）
7. [x] 角色管理模块（角色 CRUD + 来源标签 + 定位 + 收藏/冻结）— Phase 4

### 待完成 ⏳
- 任务管理页面（展示所有后台任务）
- 资产库：扩展支持角色类型（CHARACTER）作为资产类型之一
- [x] ~~前端开发~~ ✅ 完成（React + Vite + Ant Design）
  - [x] Dashboard 概览页
  - [x] Breaker 爆款拆解页
  - [x] Clip Lab 页面
  - [x] Story Maker 页面
  - [x] Tasks 任务管理页 ← 新增
  - [x] Settings 设置页 ← 新增
- [x] ~~Whisper 字幕提取集成~~ ✅ 完成
- [x] ~~Redis 任务队列~~ ✅ 完成
- [x] ~~视频生成后端~~ ✅ 完成（Seedance + CogVideoX）
- [x] ~~FFmpeg 硬件加速验证~~ ✅ 完成（Windows 兼容性已验证）

---
