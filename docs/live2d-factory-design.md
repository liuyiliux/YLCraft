# Live 2D 工厂 — 参考项目与技术调研报告

> **版本**：v0.3.0
> **日期**：2026-05-04
> **更新**：Phase 2 AI 服务实现（抠图/风格转换/分层）
> **目的**：为 YLCraft Live 2D 工厂模块提供技术参考和实现方案

---

## 一、核心参考项目

### 1.1 技术基础库

| 项目 | Star | 技术栈 | 用途 |
|------|-------|--------|------|
| [EasyLive2D/live2d-py](https://github.com/EasyLive2D/live2d-py) | - | Python C扩展 | Live2D模型加载、唇形同步、基础面部绑骨 |
| [qinyonghang/Live2D-Python](https://github.com/qinyonghang/Live2D-Python) | - | Python | Cubism SDK Python封装，渲染和交互 |
| [Arkueid/live2d-py](https://github.com/Arkueid/live2d-py) | - | Python | 无需Web环境的Live2D SDK Python版 |
| [guansss/pixi-live2d-display](https://github.com/guansss/pixi-live2d-display) | 1.4k | TypeScript | PixiJS插件，支持展示各类Live2D模型 |

> ⚠️ 以上库均需要自行从 [Live2D官网](https://www.live2d.com/) 下载 Cubism SDK Core 模块

### 1.2 AI 自动生成参考项目

| 项目/资源 | 类型 | 核心能力 |
|-----------|------|----------|
| [Bilibili BV1j19oB4E8C](https://www.bilibili.com/video/BV1j19oB4E8C/) | 视频演示 | AI Agent全自动：扣图→分层→绑骨骼→生成可动模型 |
| Live2D Automation MCP Server | MCP服务 | 单张图像→面部特征提取→图层生成→骨骼绑定→物理模拟→动作配置，输出Cubism规范中间文件 |
| [alaster-t34.github.io](https://alaster-t34.github.io/) | 技术博客 | 训练AI模型(U-Net/DeepLab/Mask R-CNN)对原画立绘进行自动拆分 |
| SpineAI | 工具分享 | AI辅助快速生成Spine/Live2D动画资源 |

### 1.3 AI 驱动虚拟角色（参考架构）

| 项目 | Stars | 亮点 | 与YLCraft关联性 |
|------|-------|------|------------------|
| [moeru-ai/airi](https://github.com/moeru-ai/airi) | 38.9k | 最热门，AI伴侣+Live2D/VRM，支持实时语音 | 高 - 角色交互参考 |
| [Open-LLM-VTuber/Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) | 7.4k | 本地LLM+Live2D，支持语音打断 | 中 - 语音驱动参考 |
| [Ikaros-521/AI-Vtuber](https://github.com/Ikaros-521/AI-Vtuber) | 4.4k | 多LLM支持，多平台直播，TTS变声 | 中 - 直播集成参考 |
| [Voine/ChatWaifu_Mobile](https://github.com/Voine/ChatWaifu_Mobile) | 1.4k | 移动端，VITS+唇形同步+ChatGPT | 中 - 移动端参考 |

---

## 一.5 Coser 照片场景支持（v0.2.0 新增）

### 1.5.1 两种工作模式

| 模式 | 输入 | 输出风格 | 适用场景 |
|------|------|----------|----------|
| **动漫立绘模式** | 透明底PNG/PSD | 二次元Live2D | 游戏立绘、虚拟主播素材 |
| **Coser照片模式** | 真人Cos照片 | 真人Live2D / 二次元Live2D | Coser动态头像、直播互动 |

### 1.5.2 Coser 照片模式流程

```
Coser照片输入
    ↓
【步骤0】AI抠图（Remove.bg / RMBG-1.4）
  · 去除背景，保留人物主体
  · 可选：背景替换（纯色/自定义背景）
    ↓
【步骤0.5】风格转换（可选）
  · Real2Anime：真人转二次元风格
  · 保持真人：不做风格转换
    ↓
【步骤1】AI自动分层
  · 识别：头发、脸部、眼睛、嘴巴、身体、服装、配饰
  · Coser特殊：假发层次、妆面、道具
    ↓
【步骤2】AI遮挡补全
  · 补全头发遮挡的额头、眉毛区域
  · 补全衣物遮挡的身体部分
    ↓
【步骤3-6】自动绑骨 → 物理模拟 → 待机动画 → 导出
    ↓
输出：可动的 Live2D 角色
```

### 1.5.3 技术选型（Coser 专用）

| 能力 | 推荐工具/模型 | 说明 |
|------|-------------|------|
| **抠图** | RMBG-1.4 (BRIA AI) | 专门针对人像的分割模型 |
| **真人转二次元** | AnimeGANv3 / SDXL + ControlNet | 高质量风格转换 |
| **人像分割** | BiRefNet / U-2-Net | 精细的人像抠图+分层 |
| **遮挡补全** | SD Inpainting + LoRA | 保持原有特征的自然补全 |

---

## 二、Live 2D 自动生成技术流程

### 2.1 完整工作流

```
输入：角色立绘图片(PNG/PSD)
  ↓
【步骤1】AI自动分层（Image Segmentation）
  · 使用 U-Net / DeepLab / Mask R-CNN 进行部件分割
  · 输出各部件掩码（头发、眼睛、嘴巴、身体等）
  ↓
【步骤2】AI补全被遮挡区域（Inpainting）
  · 使用 Stable Diffusion Inpainting 或 PS Beta 生成式填充
  · 补全额头（前发遮挡）、牙齿（嘴巴闭合）等区域
  ↓
【步骤3】自动生成网格（Auto Mesh）
  · Live2D Cubism 5.0+ Auto Mesh Generator
  · 算法自动识别透明边缘，生成均匀三角面
  ↓
【步骤4】自动骨骼绑定（Auto Rigging）
  · 面部：Auto Standard Form（根据图层命名自动生成参数）
  · 身体：Spine Auto Weights（根据骨骼位置自动计算权重）
  ↓
【步骤5】物理模拟配置
  · 头发/衣摆：Pendulum（钟摆）参数配置
  · 输入：Head Input → 输出：Hair Physics
  ↓
【步骤6】自动生成待机动画
  · 自动眨眼（Auto Blink）
  · 呼吸循环（正弦波绑定到Param_Breath）
  ↓
输出：Live2D模型文件（.model3.json + 纹理 + 动作文件）
```

### 2.2 关键技术要点

| 技术点 | 实现方案 | 参考项目 |
|--------|----------|----------|
| **图像分割** | U-Net / DeepLab v3+ / Mask R-CNN | alaster-t34 博客 |
| **遮挡补全** | Stable Diffusion Inpainting / PS Generative Fill | Tahou.com 文章 |
| **网格生成** | Live2D Cubism 5.0+ Auto Mesh Generator | 官方SDK |
| **骨骼绑定** | 根据图层命名自动识别 + 权重计算算法 | Spine Auto Weights |
| **物理模拟** | 钟摆模型（Pendulum） | Live2D Physics |
| **呼吸动画** | 正弦波（Sine Wave）+ Ease In Out 曲线 | Live2D 官方教程 |

---

## 三、YLCraft Live 2D 工厂实现方案

### 3.1 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                   YLCraft Live 2D 工厂                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────┐ │
│  │   前端编辑器     │  │   后端 API      │  │  AI 服务  │ │
│  │  (React + Pixi) │  │  (FastAPI)      │  │  (Python) │ │
│  └────────┬────────┘  └────────┬────────┘  └────┬─────┘ │
│           │                      │                  │       │
│           └──────────────────────┼──────────────────┘       │
│                              ▼                               │
│              ┌──────────────────────────────┐                │
│              │     Live2D 模型生成引擎        │                │
│              │  · 图像分割                  │                │
│              │  · 遮挡补全                  │                │
│              │  · 自动绑骨                  │                │
│              │  · 动作生成                  │                │
│              └──────────────────────────────┘                │
│                              ▼                               │
│              ┌──────────────────────────────┐                │
│              │     输出：Cubism 模型         │                │
│              │  · .model3.json              │                │
│              │  · textures/                 │                │
│              │  · motions/                  │                │
│              └──────────────────────────────┘                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 目录结构规划

```
backend/app/
├── services/
│   ├── live2d/                    # 🆕 Live 2D 工厂服务
│   │   ├── __init__.py
│   │   ├── models.py            # Live2D模型数据模型
│   │   ├── segmentation.py      # AI图像分割服务
│   │   ├── inpainting.py       # 遮挡区域补全服务
│   │   ├── rigging.py          # 自动骨骼绑定服务
│   │   ├── mesh_generator.py   # 网格生成服务
│   │   ├── physics.py          # 物理模拟配置
│   │   ├── motion_generator.py # 动作生成服务
│   │   └── exporter.py         # Cubism模型导出
│   │
│   └── ...

frontend/src/
├── pages/
│   └── live2d/                  # 🆕 Live 2D 工厂页面
│       ├── index.tsx            # 主页面（上传+预览）
│       ├── editor.tsx           # 编辑器页面（绑骨+调整）
│       ├── preview.tsx          # 模型预览页面
│       └── components/
│           ├── ModelCanvas.tsx  # 模型画布（PixiJS）
│           ├── BoneEditor.tsx   # 骨骼编辑器
│           ├── MeshEditor.tsx   # 网格编辑器
│           └── MotionTimeline.tsx # 动作时间线
│
└── ...
```

### 3.3 数据模型设计

```python
# backend/app/services/live2d/models.py

from sqlmodel import SQLModel, Field
from enum import Enum
from typing import Optional, List, Dict
import uuid

class Live2DModelStatus(str, Enum):
    DRAFT = "draft"           # 草稿
    PROCESSING = "processing"   # 处理中
    RIGGED = "rigged"         # 已绑骨
    ANIMATED = "animated"      # 已生成动作
    COMPLETED = "completed"    # 已完成
    ERROR = "error"            # 错误

class Live2DModel(SQLModel, table=True):
    """Live2D 模型主表"""
    __tablename__ = "live2d_models"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    name: str                   # 模型名称
    description: str = ""       # 描述
    
    # 关联角色
    character_id: Optional[str] = None  # 关联角色ID
    
    # 原始图片
    source_image_path: str = ""  # 原始立绘路径
    source_image_url: str = ""   # 原始立绘URL
    
    # 分层结果
    layers: List[Dict] = Field(default=[], sa_type="JSON")  # 各部件图层信息
    
    # 模型文件
    model_file_path: str = ""   # .model3.json 路径
    textures_path: str = ""     # 纹理目录
    motions_path: str = ""      # 动作文件目录
    
    # 状态
    status: Live2DModelStatus = Live2DModelStatus.DRAFT
    
    # 元数据
    metadata: Dict = Field(default={})  # 附加元数据
    
    # 时间戳
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    # 使用统计
    use_count: int = 0
    last_used_at: Optional[datetime] = None

class Live2DBone(SQLModel, table=True):
    """骨骼数据表"""
    __tablename__ = "live2d_bones"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    model_id: str                # 关联模型ID
    
    name: str                   # 骨骼名称（如 "Head", "Body", "Hair_Front"）
    parent_id: Optional[str] = None  # 父骨骼ID
    
    # 位置信息
    position_x: float = 0.0
    position_y: float = 0.0
    rotation: float = 0.0
    
    # 绑定权重
    weights: Dict = Field(default={})  # 顶点权重数据
    
    created_at: datetime = Field(default_factory=datetime.now)

class Live2DMotion(SQLModel, table=True):
    """动作数据表"""
    __tablename__ = "live2d_motions"

    id: str = Field(primary_key=True, default_factory=lambda: uuid.uuid4().hex)
    model_id: str                # 关联模型ID
    
    name: str                   # 动作名称（如 "Idle", "Blink", "Talk"）
    motion_type: str = "idle"   # idle/blink/talk/custom
    
    # 动作文件
    file_path: str = ""         # .motion3.json 文件路径
    
    # 动作参数
    duration: float = 0.0       # 时长（秒）
    loop: bool = False          # 是否循环
    
    created_at: datetime = Field(default_factory=datetime.now)
```

### 3.4 API 设计

```
# Live2D 模型管理
POST   /api/v1/live2d/models              # 创建模型（上传图片）
GET    /api/v1/live2d/models              # 模型列表
GET    /api/v1/live2d/models/:id          # 模型详情
PUT    /api/v1/live2d/models/:id          # 更新模型
DELETE /api/v1/live2d/models/:id          # 删除模型

# AI 处理
POST   /api/v1/live2d/models/:id/segment  # AI图像分割（自动分层）
POST   /api/v1/live2d/models/:id/inpaint  # AI遮挡补全
POST   /api/v1/live2d/models/:id/rig      # 自动骨骼绑定
POST   /api/v1/live2d/models/:id/mesh     # 自动生成网格
POST   /api/v1/live2d/models/:id/physics  # 配置物理模拟
POST   /api/v1/live2d/models/:id/motion   # 生成待机动作

# 导出
POST   /api/v1/live2d/models/:id/export   # 导出Cubism模型
GET    /api/v1/live2d/models/:id/download # 下载模型文件

# 预览
GET    /api/v1/live2d/models/:id/preview  # 获取预览URL
WebSocket /api/v1/live2d/ws             # 实时预览（类似Story Maker）
```

---

## 四、分阶段实现计划

### Phase 1：基础框架（1-2周）⚡

| 任务 | 优先级 | 工作内容 |
|------|--------|----------|
| 数据模型 | 🔴 必须 | Live2DModel / Live2DBone / Live2DMotion 三个 Model |
| 图片上传 API | 🔴 必须 | 支持PNG/PSD上传，创建模型记录 |
| 模型列表 API | 🔴 必须 | GET /api/v1/live2d/models 分页/搜索 |
| 前端上传页面 | 🔴 必须 | 图片上传 + 模型列表展示 |
| Cubism SDK 集成 | 🔴 必须 | 下载并配置 Live2D Cubism SDK |

**交付物**：`backend/app/services/live2d/` 基础框架 + 前端上传页面

### Phase 2：AI 自动分层（2周）

| 任务 | 优先级 | 工作内容 |
|------|--------|----------|
| 图像分割模型 | 🔴 必须 | 集成 U-Net / DeepLab v3+ 预训练模型 |
| 部件识别 | 🔴 必须 | 识别头发、眼睛、嘴巴、身体等部件 |
| 遮挡补全 | 🟡 建议 | Stable Diffusion Inpainting 补全被遮挡区域 |
| 分层导出 | 🔴 必须 | 输出PSD格式（各部件独立图层） |

**交付物**：自动分层功能 + 补全功能

### Phase 3：自动绑骨（2周）

| 任务 | 优先级 | 工作内容 |
|------|--------|----------|
| 网格自动生成 | 🔴 必须 | 根据图层轮廓自动生成三角网格 |
| 骨骼创建 | 🔴 必须 | 根据标准模板自动创建骨骼 |
| 权重计算 | 🔴 必须 | 自动计算顶点-骨骼影响权重 |
| 参数绑定 | 🟡 建议 | 自动绑定常见参数（ParamAngleX/Y等） |

**交付物**：自动绑骨功能 + 基础可动模型

### Phase 4：动作生成（1-2周）

| 任务 | 优先级 | 工作内容 |
|------|--------|----------|
| 物理模拟 | 🟡 建议 | 头发/衣摆钟摆参数配置 |
| 自动眨眼 | 🟡 建议 | 随机间隔自动眨眼动作 |
| 呼吸循环 | 🟡 建议 | 正弦波呼吸动画 |
| 导出功能 | 🔴 必须 | 导出Cubism规范文件（.model3.json + motions/） |

**交付物**：完整可动Live2D模型导出

### Phase 5：前端编辑器（持续迭代）

| 任务 | 优先级 | 工作内容 |
|------|--------|----------|
| PixiJS 集成 | 🔴 必须 | 使用 pixi-live2d-display 展示模型 |
| 骨骼编辑器 | 🟡 建议 | 可视化调整骨骼位置和权重 |
| 网格编辑器 | 🟡 建议 | 手动调整网格密度和变形 |
| 动作时间线 | 🟡 可选 | 编辑自定义动作 |

---

## 五、技术决策建议

| 决策项 | 选项 | 建议 | 理由 |
|--------|------|------|------|
| **Live2D SDK版本** | Cubism 3.0 / 4.0 / 5.0 | **5.0+** | 支持Auto Mesh Generator，大幅提升效率 |
| **图片分层AI模型** | 自训练 / 调用API | **前期调用API** | 降低成本，快速验证流程 |
| **模型存储格式** | Cubism原生 / 自定义 | **Cubism原生** | 兼容官方Viewer和主流引擎 |
| **前端渲染** | PixiJS / Canvas / WebGL | **PixiJS** | 有成熟库(pixi-live2d-display)支持 |
| **图像分割模型** | U-Net / DeepLab / Mask R-CNN | **Mask R-CNN** | 实例分割精度高，适合复杂立绘 |
| **遮挡补全** | SD Inpainting / PS API / 自训练 | **SD Inpainting** | 开源，可本地部署，成本低 |

---

## 六、与YLCraft其他模块打通

```
Live 2D 工厂 ← → 角色库（Character Service）
  · 角色库中角色 → 一键生成Live2D模型
  · 生成的Live2D模型 → 保存回角色库

Live 2D 工厂 ← → Story Maker
  · Story Maker角色 → 自动生成Live2D模型
  · Live2D模型 → 用于分镜视频生成

Live 2D 工厂 ← → Clip Lab
  · Live2D模型 → 作为视频素材（可动角色）
  · 生成Live2D动画片段 → 剪辑入视频

Live 2D 工厂 ← → 资产库（Asset Library）
  · 生成的模型文件 → 入库到资产库
  · 支持模型文件的管理和复用
```

---

## 七、参考资源汇总

### 7.1 GitHub 项目

- [EasyLive2D/live2d-py](https://github.com/EasyLive2D/live2d-py) - Python Live2D库
- [guansss/pixi-live2d-display](https://github.com/guansss/pixi-live2d-display) - PixiJS Live2D插件
- [alaster-t34/ai-live2d](https://alaster-t34.github.io/) - AI自动拆分技术博客

### 7.2 技术文章

- [2D立绘活了：Live2D/Spine动作的AI辅助生成流](https://www.tahou.com/article/191930619786845189) - AI辅助工作流程
- [告别"拆图地狱"！SIGGRAPH 2026 惊艳开源项目 See...](https://zhuanlan.zhihu.com/p/2023503283017328213) - 自动拆图技术
- [關於·訓練ai讓其對原畫立繪進行拆分](https://alaster-t34.github.io/) - 训练AI进行图像分割

### 7.3 官方文档

- [Live2D Cubism SDK 教程](https://docs.live2d.com/zh-CHS/cubism-sdk-tutorials/top/) - 官方SDK文档
- [Live2D Viewer 使用说明](https://docs.live2d.com/) - 模型查看和测试

---

## 八、下一步行动

1. **确认技术方案** - 与团队确认SDK版本、AI模型选择
2. **下载Live2D Cubism SDK** - 从官网下载对应版本的SDK
3. **搭建基础框架** - 创建数据模型、API框架、前端页面
4. **集成图像分割模型** - 部署或调用图像分割API
5. **实现第一个Demo** - 完成从图片上传到自动分层的完整流程

---

## 九、实现状态（v0.3.0）

### 9.1 已完成功能

| 阶段 | 功能 | 状态 | 文件 |
|------|------|------|------|
| Phase 1 | 数据模型（Live2DModel/Bone/Motion） | ✅ 完成 | `backend/app/db/models/live2d.py` |
| Phase 1 | CRUD API（创建/列表/详情/更新/删除） | ✅ 完成 | `backend/app/api/v1/live2d.py` |
| Phase 1 | 前端上传页面 + 列表 | ✅ 完成 | `frontend/src/pages/live2d/index.tsx` |
| Phase 1 | 三种风格模式支持 | ✅ 完成 | `Live2DStyleMode` 枚举 |
| Phase 2 | AI 抠图服务（RMBG-1.4） | ✅ 完成 | `backend/app/services/live2d/rembg.py` |
| Phase 2 | 风格转换服务（SD+ControlNet） | ⚠️ 部分完成 | `backend/app/services/live2d/style_transfer.py` |
| Phase 2 | AI 分层服务（BiRefNet/U-2-Net） | ⚠️ 部分完成 | `backend/app/services/live2d/segmentation.py` |
| **新增** | **本地/API模式切换** | ✅ 完成 | 详见9.4节 |

### 9.2 待实现功能

| 阶段 | 功能 | 优先级 | 说明 |
|------|------|--------|------|
| Phase 2 | 遮挡补全（Inpainting） | 🟡 中 | SD Inpainting 补全遮挡区域 |
| Phase 2 | AnimeGAN 快速风格转换 | 🟡 中 | 可选替代 SD ControlNet |
| Phase 3 | 自动绑骨服务 | 🔴 高 | 自动生成骨骼和权重 |
| Phase 3 | 网格生成服务 | 🔴 高 | Auto Mesh Generator |
| Phase 4 | 物理模拟配置 | 🟢 低 | 头发/衣摆钟摆参数 |
| Phase 4 | 待机动作生成 | 🟢 低 | 眨眼+呼吸动画 |
| Phase 4 | Cubism 模型导出 | 🔴 高 | .model3.json 导出 |

### 9.3 本地/API模式切换功能（v0.4.0 新增）

#### 9.3.1 功能概述
为每个处理环节（抠图、风格转换、图像分割）提供**本地模型**和**云端API**两种处理方式，用户可灵活切换。

#### 9.3.2 支持的服务

| 环节 | 本地模式 | API模式 |
|------|----------|---------|
| 抠图（Rembg） | RMBG-1.4 模型 | Remove.bg API |
| 风格转换 | SD + ControlNet / AnimeGAN | Replicate API (SDXL) |
| 图像分割 | BiRefNet / U-2-Net | Hugging Face Inference API |

#### 9.3.3 配置文件
- 配置文件：`backend/config/live2d.json`
- 配置管理：`backend/app/core/config.py`

#### 9.3.4 API端点

| 端点 | 说明 |
|------|------|
| `GET /api/v1/live2d/config/processing-modes` | 获取当前处理模式配置 |
| `PUT /api/v1/live2d/config/processing-modes` | 更新处理模式配置 |
| `PUT /api/v1/live2d/models/{id}/processing-config` | 更新模型的个性化配置 |
| `POST /api/v1/live2d/models/{id}/rembg?mode=local|api` | 抠图（支持mode参数） |
| `POST /api/v1/live2d/models/{id}/style-transfer?mode=local|api` | 风格转换（支持mode参数） |
| `POST /api/v1/live2d/models/{id}/segment?mode=local|api` | 图像分割（支持mode参数） |

#### 9.3.5 配置优先级
1. **请求参数**（最高）：`?mode=api`
2. **模型级别配置**：`processing_config`字段
3. **全局配置**（最低）：`config/live2d.json`

#### 9.3.6 新增文件清单
- `backend/app/core/config.py` - ✅ 配置管理
- `backend/config/live2d.json` - ✅ 配置文件
- `backend/app/services/live2d/api_client.py` - ✅ API调用封装
- `docs/live2d-processing-mode-design.md` - ✅ 处理模式切换设计文档

### 9.3 依赖安装

```bash
# 核心依赖
pip install rembg onnxruntime

# 分割模型依赖
pip install transformers torch

# 风格转换依赖（可选）
pip install diffusers accelerate opencv-python
```

---

*本文档为Live 2D工厂模块的设计初稿，确认后可纳入 `DESIGN.md` 作为独立章节。*
