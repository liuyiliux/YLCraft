# YLCraft 参考项目文档

> 来源：联网搜索 + 本地代码分析，2026-05-03

---

## ArcReel — AI Agent 视频工作台
**GitHub**: https://github.com/ArcReel/ArcReel  
**技术栈**: React 19 + FastAPI + Claude Agent SDK + Claude/Gemini/Seedream + FFmpeg + SQLite/PostgreSQL

### 核心能力
- **完整流水线**：上传小说 → AI 拆分剧本 → 生成人物设计图 → 生成分镜图 → 生成视频片段 → FFmpeg 合成成片
- **多智能体协作**：基于 Claude Agent SDK，编排 Skill + 聚焦 Subagent，自动 dispatch 专职 Agent（角色提取/剧本生成/资产生成）
- **多供应商可切换**：图片支持 Gemini / Seedream / Grok，视频支持 Veo 3.1 / Seedance / Grok，不锁定单一供应商
- **角色一致性**：先生成人物设计图，后续所有分镜和视频均参考该设计，跨镜头保持角色外观统一
- **剪映草稿导出**：按集导出为剪映 ZIP，桌面版里二次编辑
- **异步任务队列**：RPM 速率限制 + Image/Video 独立并发通道，lease-based 调度，支持断点续传

### YLCraft 可借鉴
- Backend Provider 架构（Protocol + Registry）
- 多供应商切换机制
- 角色一致性保证策略
- 异步任务 + SSE 进度推送

---

## CutClaw — 音乐驱动 AI 长视频剪辑
**GitHub**: https://github.com/GVCLab/CutClaw  
**技术栈**: 多智能体 + 多模态模型

### 核心能力
- **音乐驱动剪辑**：先分析音乐节拍/重拍/能量曲线，把视觉叙事严格对应到听觉骨架上
- **一键素材解构**：原始视频和音频提取镜头、场景、动作、情感等层级信息
- **指令驱动剪辑风格**：文字指令自动理解并执行剪辑决策
- **智能自动裁剪**：内容感知裁剪，适配 9:16/16:9 等各平台比例
- **多智能体协作**：编剧（理解叙事）+ 剪辑师（选择时间戳）+ 审片（质量验证）
- **多模型支持**：可接入主流多模态模型

### YLCraft 可借鉴
- 多智能体 Pipeline 模式
- 音乐驱动的自动剪辑策略
- 素材解构与重组逻辑

---

## LocalMiniDrama — 本地 AI 短剧漫剧生成工具
**GitHub**: https://github.com/xuanyustudio/LocalMiniDrama  
**技术栈**: Node.js + Seedance2 生图

### 核心能力
- **本地 AI 短剧生成**：从故事到成片一站式，数据不出本机
- **角色生成**：输入 outline → LLM 提取角色 → 返回角色数组（name/role/description/personality/appearance/voice_style）
- **角色肖像生成**：character.appearance + drama style → imageClient.generateImage()
- **短剧工作流管理**：剧本 → 角色 → 分镜 → 生图 → 生视频 → 剪辑

### YLCraft 可借鉴
- **角色生成流程**（最直接可复用的参考）：outline → LLM → 角色数组
- **角色肖像生成**：appearance 字段作为 prompt 生成图片
- 短剧全链路设计思路

---

## huobao-drama（火宝短剧）
**GitHub**: https://github.com/chatfire-AI/huobao-drama  
**技术栈**: Go + Vue3 + SQLite

### 核心能力
- **全栈 AI 短剧自动化生产平台**：剧本解析 → 角色/分镜生成 → 视频合成
- **角色管理**：AI 生成角色形象，批量生成，图片上传与管理
- **分镜制作**：自动生成分镜脚本，场景描述与镜头设计，分镜图片生成（文生图）
- **本地存储 + SQLite**：适合自建的 AI 素材/分镜/视频任务管理后台

### YLCraft 可借鉴
- 角色批量管理功能设计
- 分镜脚本自动生成逻辑
- 本地存储方案

---

## NarratoAI — AI 脚本 + TTS 流水线
**参考目录**: `F:\PycharmProjects\YLCraft-refs\NarratoAI`
**技术栈**: Python + MoviePy + LLM + TTS

### 核心能力
- **Pipeline 模式**：多步骤流水线，视频素材搜索 → LLM 旁白生成 → TTS 配音 → 视频合成
- **脚本生成**：从视频分析生成纪录片风格脚本
- **TTS 集成**：文本转语音，多音色支持
- **Prompt 模板**：预设各类脚本 prompt 模板

### YLCraft 可借鉴
- Pipeline 模式设计
- TTS 集成方式
- Prompt 模板化

---

## jellyfish — 视频处理 API
**参考目录**: `F:\PycharmProjects\YLCraft-refs\jellyfish`
**用途**: 视频处理 API 规范设计参考

### YLCraft 可借鉴
- 视频 API 接口设计
- 任务状态管理

---

## yiliu（逸流）— 多平台图文生成器
**GitHub**: https://github.com/liuyiliux/CrossGen
**技术栈**: Python 3.11+ + FastAPI + Redis + Vue 3 + TypeScript + Element Plus

### 核心能力
- **一键生成**：一句话输入，自动生成多平台图文内容（小红书/抖音/公众号/头条号）
- **灵感获取**：搜索小红书热门内容，支持链接解析，导入参考图片
- **AI 驱动**：集成 GPT/Claude 等 LLM + Stable Diffusion 图像生成
- **批量处理**：支持批量主题并行生成
- **模板化**：平台模板配置，灵活响应平台规则变化
- **结构化内容**：总标题 + 总文案 + 多张图片的内容结构

### YLCraft 可借鉴
- **图文分离的数据结构**：Outline (title + copywriting) + Page (image_prompt)，适合 YLCraft 的 story outline 设计
- **平台模板系统**：不同平台有不同模板（platform_templates.yaml），YLCraft 场景标签（电商/摄影/短剧/COSER）可参考
- **参考图导入**：小红书笔记图片直接导入作为 AI 绘图参考，精准还原风格

---

## 其他参考项目

| 项目 | GitHub | 核心特点 |
|------|--------|----------|
| **Toonflow** | HBAI-Ltd/Toonflow-app | AI 短剧工厂，小说秒变剧集，无限画布工作台 |
| **BigBanana AI Director** | — | 关键帧驱动，Script-to-Asset-to-Keyframe 工业化工作流 |
| **Micro-Drama-Skills** | zhaihao118/Micro-Drama-Skills | Claude Skills 驱动，AI 短剧全流程自动化 |
| **MoneyPrinterTurbo** | — | AI 视频配音/文案 |
| **CineGen-AI** | Will-Water/CineGen-AI | 开源 AI 漫剧/动漫/短剧生成 |
| **Yihen-Drama** | CszYihen/Yihen-Drama | 前端+后端+Docker 一键部署，支持角色场景 |

---

## 参考项目能力矩阵

| 功能 | ArcReel | CutClaw | LocalMiniDrama | huobao-drama | NarratoAI |
|------|---------|---------|---------------|--------------|-----------|
| 小说→短视频 | ✅ | ❌ | ✅ | ❌ | ❌ |
| 音乐驱动剪辑 | ❌ | ✅ | ❌ | ❌ | ❌ |
| 角色生成/生图 | ✅ | ❌ | ✅ | ✅ | ❌ |
| 分镜生成 | ✅ | ❌ | ✅ | ✅ | ❌ |
| 视频合成 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 多智能体 | ✅ | ✅ | ❌ | ❌ | ❌ |
| 多供应商切换 | ✅ | ❌ | ❌ | ❌ | ❌ |
| TTS | ✅ | ❌ | ❌ | ❌ | ✅ |
| 剪映导出 | ✅ | ❌ | ❌ | ❌ | ❌ |
| 本地部署 | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## YLCraft 下一步可复用功能优先级

1. **[高] 角色生成服务**：参考 LocalMiniDrama 的 `characterGenerationService.js`，从剧本描述用 LLM 提取角色信息
2. **[高] 角色肖像生成**：参考 LocalMiniDrama 的 `characterLibraryService.js`，从 appearance 生成图片
3. **[高] 多供应商 Backend**：参考 ArcReel 的 Provider 架构，完善 BackendManager
4. **[中] 角色一致性策略**：参考 ArcReel，锁定角色设计图保证跨镜头一致
5. **[中] 音乐驱动剪辑**：参考 CutClaw，实现 Beat-based 自动剪辑
6. **[低] 剪映草稿导出**：参考 ArcReel，按集导出剪映 ZIP
