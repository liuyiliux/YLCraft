# YLCraft 集成 ComfyUI 和数字人功能 — 全面可行性分析

> **分析日期**：2026-05-06
> **分析人**：WorkBuddy AI
> **项目状态**：Live2D 工厂已完成约 98%，YLCraft 整体架构成熟

---

## 一、现有架构评估

### 1.1 项目当前结构

```
YLCraft/
├── backend/
│   ├── app/
│   │   ├── api/v1/           # 15+ API 模块（已完成）
│   │   │   ├── videos.py     # ✅ 视频生成 API
│   │   │   ├── images.py      # ✅ 图像生成 API
│   │   │   ├── tts.py        # ✅ TTS API（占位）
│   │   │   ├── live2d.py      # ✅ Live2D 工厂 API
│   │   │   └── ...
│   │   ├── connectors/       # ✅ 连接器架构（已完成）
│   │   │   ├── ai/           # AI Provider 连接器
│   │   │   └── social/       # 社交媒体连接器（9个）
│   │   ├── services/        # ✅ 服务层架构（已完成）
│   │   │   ├── video_gen/     # 视频生成服务
│   │   │   │   ├── base.py   # BaseVideoBackend 抽象基类
│   │   │   │   └── minimax.py # Minimax 实现
│   │   │   ├── image/        # 图像生成服务
│   │   │   ├── llm/          # LLM 调度器
│   │   │   └── live2d/       # Live2D 工厂
│   │   └── core/
│   │       └── contracts/    # ✅ 数据契约（dataclass）
│   └── requirements.txt
└── frontend/
    └── src/pages/
        ├── video-gen/        # ✅ 视频生成页面
        ├── image-gen/        # ✅ 图像生成页面
        └── live2d/           # ✅ Live2D 工厂页面
```

### 1.2 现有能力矩阵

| 能力域 | 当前状态 | 实现方式 |
|--------|---------|---------|
| **LLM 调度** | ✅ 完整 | BackendManager + Registry |
| **图像生成** | ✅ 基础 | BaseImageBackend + Minimax |
| **视频生成** | ✅ 基础 | BaseVideoBackend + Minimax |
| **TTS 语音** | ⚠️ 占位 | 预留接口，待接入 |
| **Live2D** | ✅ ~98% | 独立流水线（Cosplay照片→VTS） |
| **资产库** | ✅ 基础 | 统一素材管理 |
| **WebSocket** | ✅ 完整 | 任务进度实时推送 |

### 1.3 核心架构优势

YLCraft 已具备**极适合集成新能力**的架构特征：

```
✅ 模块化 Backend 架构
   ├── BaseVideoBackend (视频生成基类)
   ├── BaseImageBackend (图像生成基类)
   └── BackendManager (统一调度器)

✅ Provider 注册表模式
   └── 通过 YAML 配置即可注册新 Provider

✅ 异步任务 + WebSocket 进度推送
   └── poll_with_retry 机制

✅ 统一的请求/响应契约
   └── dataclass 数据模型
```

---

## 二、ComfyUI 集成方案

### 2.1 ComfyUI 简介

**ComfyUI** 是一个基于节点工作流的 AI 图像/视频生成平台：

| 特性 | 说明 |
|------|------|
| **工作流** | 节点图可视化编排 |
| **模型支持** | Stable Diffusion、FLUX、WAN 2.1 等 |
| **图像能力** | 文生图、图生图、ControlNet、IP-Adapter |
| **视频能力** | 图生视频、视频合成 |
| **部署方式** | 本地运行 + API Server |
| **扩展性** | 丰富的自定义节点生态 |

### 2.2 集成价值

| 维度 | 价值 |
|------|------|
| **图像质量** | 接入 SD/FLUX 等顶级开源模型 |
| **视频生成** | 接入视频生成模型（如 WAN 2.1） |
| **可控性** | 工作流定制能力强 |
| **成本** | 本地运行，零 API 费用 |
| **差异化** | 与现有云服务形成互补 |

### 2.3 技术方案

#### 方案 A：ComfyUI 即服务（推荐）

```
┌─────────────────────────────────────────────────────────────────┐
│                        YLCraft 后端                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ ComfyUI API  │  │  图像生成     │  │  视频生成     │          │
│  │  Client      │  │  Backend     │  │  Backend     │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                 │                   │
│         └─────────────────┼─────────────────┘                   │
│                           ▼                                     │
│              ┌────────────────────────┐                         │
│              │    BackendManager      │                         │
│              │  (统一调度，与现有架构) │                         │
│              └────────────────────────┘                         │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼ ComfyUI REST API / WebSocket
┌─────────────────────────────────────────────────────────────────┐
│                     ComfyUI Server                                │
│  (独立进程，可本地部署或远程 GPU 服务器)                           │
│  ├── 模型管理                                                     │
│  ├── 工作流执行                                                   │
│  └── WebSocket 进度推送                                          │
└─────────────────────────────────────────────────────────────────┘
```

#### 方案 B：ComfyUI 嵌入式

将 ComfyUI 作为 YLCraft 子模块集成，适合完全离线场景。

### 2.4 实现细节

#### 2.4.1 目录结构

```
backend/app/services/
├── comfyui/                      # 🆕 ComfyUI 服务
│   ├── __init__.py
│   ├── client.py                # ComfyUI API 客户端
│   ├── image_backend.py         # ComfyUI 图像 Backend
│   ├── video_backend.py         # ComfyUI 视频 Backend
│   ├── workflows/               # 预定义工作流
│   │   ├── txt2img.json         # 文生图工作流
│   │   ├── img2img.json         # 图生图工作流
│   │   ├── img2video.json       # 图生视频工作流
│   │   └── wan21_video.json     # WAN 2.1 视频工作流
│   └── models.py                # 模型管理
└── ...
```

#### 2.4.2 ComfyUI API Client

```python
# backend/app/services/comfyui/client.py

import httpx
import asyncio
import json
import logging
from typing import Optional, AsyncIterator
from pathlib import Path

logger = logging.getLogger("ylcraft.comfyui")

class ComfyUIClient:
    """
    ComfyUI API 客户端

    功能：
    - 图像生成（文生图、图生图）
    - 视频生成（图生视频）
    - 工作流执行
    - 任务状态轮询
    """

    def __init__(self, server_url: str, workflow_dir: str = None):
        self.server_url = server_url.rstrip("/")
        self.workflow_dir = Path(workflow_dir) if workflow_dir else None
        self._client = httpx.AsyncClient(timeout=300.0)

    async def get_system_stats(self) -> dict:
        """获取系统状态（显存、模型列表）"""
        resp = await self._client.get(f"{self.server_url}/system_stats")
        resp.raise_for_status()
        return resp.json()

    async def get_models(self) -> dict:
        """获取可用模型列表"""
        resp = await self._client.get(f"{self.server_url}/api/model_list")
        resp.raise_for_status()
        return resp.json()

    async def queue_prompt(self, workflow: dict) -> dict:
        """
        提交工作流任务

        Args:
            workflow: 工作流节点配置字典

        Returns:
            {"prompt_id": "xxx", "number": 1, ...}
        """
        resp = await self._client.post(
            f"{self.server_url}/api/prompt",
            json={"prompt": workflow}
        )
        resp.raise_for_status()
        return resp.json()

    async def get_history(self, prompt_id: str) -> dict:
        """获取任务历史（含输出）"""
        resp = await self._client.get(f"{self.server_url}/api/history/{prompt_id}")
        resp.raise_for_status()
        return resp.json()

    async def get_progress(self) -> dict:
        """获取当前执行进度"""
        resp = await self._client.get(f"{self.server_url}/api/progress")
        resp.raise_for_status()
        return resp.json()

    async def upload_image(self, image_path: str, name: str = None) -> dict:
        """上传图片到 ComfyUI"""
        with open(image_path, "rb") as f:
            files = {"image": (name or Path(image_path).name, f.read())}
            resp = await self._client.post(
                f"{self.server_url}/api/upload/image",
                files=files
            )
        resp.raise_for_status()
        return resp.json()

    async def poll_until_complete(
        self,
        prompt_id: str,
        poll_interval: float = 1.0,
        max_wait: float = 600.0
    ) -> dict:
        """轮询直到任务完成"""
        import time
        elapsed = 0.0

        while elapsed < max_wait:
            history = await self.get_history(prompt_id)

            if prompt_id in history:
                status = history[prompt_id].get("status", {})
                if status.get("completed", False):
                    return history[prompt_id]
                elif status.get("error"):
                    raise RuntimeError(f"ComfyUI task error: {status['error']}")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            logger.debug(f"Waiting for ComfyUI task {prompt_id}, {int(elapsed)}s elapsed")

        raise TimeoutError(f"ComfyUI task {prompt_id} timeout after {max_wait}s")

    async def execute_workflow(
        self,
        workflow: dict,
        poll_interval: float = 1.0,
        max_wait: float = 600.0
    ) -> dict:
        """
        执行工作流并等待完成

        Returns:
            包含所有输出节点结果的字典
        """
        # 1. 提交任务
        result = await self.queue_prompt(workflow)
        prompt_id = result["prompt_id"]
        logger.info(f"ComfyUI task submitted: {prompt_id}")

        # 2. 等待完成
        history = await self.poll_until_complete(prompt_id, poll_interval, max_wait)

        # 3. 提取输出
        outputs = {}
        for node_id, node_data in history.get("outputs", {}).items():
            if "images" in node_data:
                outputs[node_id] = node_data["images"]
            elif "video" in node_data:
                outputs[node_id] = node_data["video"]

        return {"prompt_id": prompt_id, "outputs": outputs}

    def load_workflow(self, name: str) -> dict:
        """从文件加载工作流 JSON"""
        if not self.workflow_dir:
            raise ValueError("workflow_dir not configured")
        path = self.workflow_dir / f"{name}.json"
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
```

#### 2.4.3 ComfyUI Image Backend

```python
# backend/app/services/comfyui/image_backend.py

from __future__ import annotations
import logging
import time
from dataclasses import dataclass
from typing import Optional

from app.services.image.base import BaseImageBackend, ImageCapabilities
from app.core.contracts.types import ImageGenerationRequest, ImageGenerationResult

logger = logging.getLogger("ylcraft.comfyui.image")

@dataclass
class ComfyUIImageConfig:
    """ComfyUI 图像配置"""
    server_url: str = "http://127.0.0.1:8188"
    workflow_name: str = "txt2img"  # txt2img / img2img
    model: str = "sd15"
    output_dir: str = "storage/comfyui/outputs"
    timeout: int = 300

class ComfyUIImageBackend(BaseImageBackend):
    """
    ComfyUI 图像生成后端

    支持：
    - 文生图 (txt2img)
    - 图生图 (img2img)
    - ControlNet 控制
    """

    PROVIDER_ID = "comfyui"
    PROVIDER_NAME = "ComfyUI"

    def __init__(self, config: ComfyUIImageConfig):
        self._config = config
        self._client = None

    @property
    def name(self) -> str:
        return f"comfyui-{self._config.model}"

    @property
    def model(self) -> str:
        return self._config.model

    @property
    def capabilities(self) -> set:
        from app.core.contracts.types import ImageCapability
        return {
            ImageCapability.TEXT_TO_IMAGE,
            ImageCapability.IMAGE_TO_IMAGE,
            ImageCapability.STYLE_CONTROL,
        }

    @property
    def image_capabilities(self) -> ImageCapabilities:
        return ImageCapabilities(
            max_resolution=2048,
            supports_controlnet=True,
            supports_lora=True,
        )

    async def initialize(self) -> bool:
        """初始化 ComfyUI 客户端"""
        try:
            from .client import ComfyUIClient
            self._client = ComfyUIClient(self._config.server_url)
            stats = await self._client.get_system_stats()
            logger.info(f"ComfyUI connected: {stats.get('devices', 'unknown')}")
            return True
        except Exception as e:
            logger.error(f"ComfyUI init failed: {e}")
            return False

    async def _generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        """执行图像生成"""
        start = time.perf_counter()

        try:
            # 1. 加载工作流模板
            workflow = self._client.load_workflow(
                self._config.workflow_name
            )

            # 2. 替换工作流参数
            # 具体节点 ID 需根据工作流 JSON 确定
            workflow["3"]["inputs"]["text"] = req.prompt  # KSampler prompt
            if req.negative_prompt:
                workflow["4"]["inputs"]["text"] = req.negative_prompt  # Negative prompt

            # 3. 设置尺寸
            if req.size:
                width, height = map(int, req.size.split("x"))
                workflow["5"]["inputs"]["width"] = width   # Empty Latent Image
                workflow["5"]["inputs"]["height"] = height

            # 4. 执行
            result = await self._client.execute_workflow(workflow)

            # 5. 提取输出
            outputs = result["outputs"]
            images = []
            for node_id, node_output in outputs.items():
                if isinstance(node_output, list):
                    for img in node_output:
                        if "filename" in img:
                            images.append({
                                "url": f"{self._config.server_url}/view?filename={img['filename']}",
                                "filename": img["filename"]
                            })

            return ImageGenerationResult(
                success=True,
                url=images[0]["url"] if images else None,
                local_path=self._output_path(images[0]["filename"]) if images else None,
                model=self._config.model,
                cost=0.0,  # 本地无 API 费用
                latency_ms=(time.perf_counter() - start) * 1000,
            )

        except Exception as e:
            logger.error(f"ComfyUI image generation failed: {e}")
            return ImageGenerationResult(
                success=False,
                error=str(e),
                latency_ms=(time.perf_counter() - start) * 1000,
            )

    def _output_path(self, filename: str) -> str:
        import os
        path = os.path.join(self._config.output_dir, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path
```

#### 2.4.4 注册到 BackendManager

```python
# backend/app/services/comfyui/__init__.py

from .client import ComfyUIClient
from .image_backend import ComfyUIImageBackend, ComfyUIImageConfig
from .video_backend import ComfyUIVideoBackend, ComfyUIVideoConfig

__all__ = [
    "ComfyUIClient",
    "ComfyUIImageBackend",
    "ComfyUIImageConfig",
    "ComfyUIVideoBackend",
    "ComfyUIVideoConfig",
]
```

```python
# backend/app/services/llm/manager.py 新增

def _load_comfyui_backends():
    from app.services.comfyui import ComfyUIImageBackend, ComfyUIVideoBackend, ComfyUIImageConfig, ComfyUIVideoConfig
    return {
        "comfyui-image": ComfyUIImageBackend,
        "comfyui-video": ComfyUIVideoBackend,
    }
```

### 2.5 ComfyUI 配置

```yaml
# backend/config/providers.yaml

providers:
  # ========== 现有 Provider ==========
  minimax-image:
    type: image
    api_key: ${MINIMAX_API_KEY}
    api_base: https://api.minimax.chat
    model: image-01

  minimax-video:
    type: video
    api_key: ${MINIMAX_API_KEY}
    api_base: https://api.minimax.chat
    model: video-01

  doubao-llm:
    type: llm
    api_key: ${DOUBAO_API_KEY}
    api_base: https://ark.cn-beijing.volces.com/api/v3
    model: doubao-pro

  # ========== 🆕 ComfyUI Provider ==========
  comfyui-local:
    type: image,video
    server_url: http://127.0.0.1:8188
    workflow_dir: backend/app/services/comfyui/workflows
    output_dir: storage/comfyui/outputs
    models:
      image: sd15,flux
      video: wan21

defaults:
  image: minimax-image
  video: minimax-video
  llm: doubao-llm
```

---

## 三、数字人功能集成方案

### 3.1 数字人能力分类

| 类型 | 说明 | 技术实现 |
|------|------|---------|
| **2D 数字人** | 真人视频驱动 | Wav2Lip、Sadtalker、DINOX |
| **2.5D 数字人** | 单图驱动说话 | Live2D（已有）、Audio-driven |
| **3D 数字人** | 3D 模型驱动 | MetaHuman、Unity/UE5 |
| **AI 数字主播** | 语音驱动口型 | CosyVoice + 唇形同步 |

### 3.2 与 Live2D 的关系

```
┌─────────────────────────────────────────────────────────────────┐
│                        数字人能力总览                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────────────┐    ┌─────────────────────┐            │
│   │    Live2D 工厂       │    │   🆕 数字人工厂      │            │
│   │    (已实现 ~98%)     │    │   (本次集成目标)     │            │
│   └──────────┬──────────┘    └──────────┬──────────┘            │
│              │                          │                       │
│              ▼                          ▼                       │
│   ┌─────────────────────┐    ┌─────────────────────┐            │
│   │  Cosplay 照片        │    │  真人照片/视频       │            │
│   │  ↓ 抠图+立绘        │    │  ↓                  │            │
│   │  ↓ Live2D 绑定      │    │  ↓ 驱动生成         │            │
│   │  ↓ VTS 导出         │    │  ↓ 数字人视频        │            │
│   │  → Live2D 动画      │    │  → AI 主播视频      │            │
│   └─────────────────────┘    └─────────────────────┘            │
│                                                                 │
│   特点：静态立绘 → 动态立绘      特点：真人感 / 播报感            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 推荐的数字人方案

#### 方案 A：音频驱动数字人（推荐）

适合 **AI 主播 / 新闻播报 / 课程讲解** 场景：

| 组件 | 技术选型 | 说明 |
|------|---------|------|
| **TTS 语音** | CosyVoice 2.0 | 阿里开源，支持声音克隆 |
| **唇形同步** | Wav2Lip / DINOX | 音频驱动口型 |
| **背景处理** | SadTalker | 从单张照片生成说话头肩视频 |
| **视频合成** | SadTalker + GFPGAN | 保持面部质量 |

#### 方案 B：视频驱动数字人

适合 **真人模仿 / 舞蹈 / 动作迁移** 场景：

| 组件 | 技术选型 | 说明 |
|------|---------|------|
| **动作迁移** | LoRA-X | 参考视频驱动目标人物 |
| **图像驱动** | LivePortrait | 单图驱动面部表情 |
| **视频融合** | 高质量视频合成 |

### 3.4 技术方案（独立模块）

#### 3.4.1 目录结构

```
backend/app/services/
├── digital_human/                # 🆕 数字人工厂
│   ├── __init__.py
│   ├── config.py                 # 配置管理
│   ├── service.py                # 主服务类
│   ├── backends/                 # 后端实现
│   │   ├── __init__.py
│   │   ├── base.py               # 抽象基类
│   │   ├── sadtalker.py          # SadTalker 实现
│   │   ├── wav2lip.py            # Wav2Lip 实现
│   │   └── liveportrait.py       # LivePortrait 实现
│   ├── tts/                      # TTS 引擎
│   │   ├── __init__.py
│   │   ├── cosyvoice.py          # CosyVoice 2.0
│   │   └── edge_tts.py           # Edge-TTS 备选
│   └── assets/                   # 资源管理
│       ├── models.py             # 模型下载/管理
│       └── faces.py              # 人脸检测/处理
└── ...
```

#### 3.4.2 数字人主服务

```python
# backend/app/services/digital_human/service.py

"""
YLCraft — 数字人工厂主服务

功能：
- 从单张照片 + 音频生成说话视频
- 支持多种后端（SadTalker / Wav2Lip / LivePortrait）
- 内置 TTS 语音合成（CosyVoice / Edge-TTS）
- 异步任务 + WebSocket 进度推送
"""

from __future__ import annotations

import asyncio
import logging
import uuid
import os
from pathlib import Path
from typing import Optional, Literal
from dataclasses import dataclass, field
from enum import Enum

from app.core.contracts.types import (
    poll_with_retry,
    MediaType,
)
from app.core.config import ensure_download_path

logger = logging.getLogger("ylcraft.digital_human")


class DigitalHumanBackend(str, Enum):
    """数字人后端类型"""
    SADTALKER = "sadtalker"      # 单图 + 音频 → 说话视频
    WAV2LIP = "wav2lip"          # 音频 + 人脸区域 → 唇形同步
    LIVE_PORTRAIT = "liveportrait"  # 单图驱动表情/头动


class TTSType(str, Enum):
    """TTS 类型"""
    COSYVOICE = "cosyvoice"      # 阿里 CosyVoice 2.0
    EDGE_TTS = "edge_tts"        # Microsoft Edge-TTS
    OPENAI_TTS = "openai_tts"    # OpenAI TTS


@dataclass
class DigitalHumanRequest:
    """数字人生成请求"""
    # 输入
    source_image: str = ""           # 源图片路径/URL
    audio_path: Optional[str] = None # 音频文件路径
    script: Optional[str] = None     # 文本脚本（将转为语音）

    # 配置
    backend: DigitalHumanBackend = DigitalHumanBackend.SADTALKER
    tts_type: TTSType = TTSType.EDGE_TTS
    voice: str = "zh-CN-XiaoxiaoNeural"  # Edge-TTS 音色

    # 参数
    duration: int = 10           # 最大时长（秒）
    enhancement: bool = True     # 面部增强
    background: str = "source"   # 背景模式: source / remove / blur

    # 输出
    output_dir: Optional[str] = None


@dataclass
class DigitalHumanResult:
    """数字人生成结果"""
    success: bool
    task_id: str = ""
    video_path: Optional[str] = None
    video_url: Optional[str] = None
    thumbnail_path: Optional[str] = None
    duration: float = 0.0
    backend: str = ""
    cost: float = 0.0
    latency_ms: float = 0.0
    error: Optional[str] = None


class DigitalHumanService:
    """
    数字人工厂主服务

    使用示例：
    ```python
    service = DigitalHumanService()

    # 方式 1：文本脚本 → TTS → 数字人视频
    result = await service.generate(
        request=DigitalHumanRequest(
            source_image="input/avatar.png",
            script="欢迎来到 YLCraft，这里是您的 AI 创作助手。",
            backend=DigitalHumanBackend.SADTALKER,
        )
    )

    # 方式 2：已有音频
    result = await service.generate(
        request=DigitalHumanRequest(
            source_image="input/avatar.png",
            audio_path="input/voice.mp3",
            backend=DigitalHumanBackend.WAV2LIP,
        )
    )
    ```
    """

    def __init__(self, config: dict = None):
        self._config = config or {}
        self._backends: dict[DigitalHumanBackend, Any] = {}
        self._tts_engines: dict[TTSType, Any] = {}
        self._initialized = False

    async def initialize(self):
        """初始化所有后端"""
        if self._initialized:
            return

        # 初始化数字人后端
        from .backends.sadtalker import SadTalkerBackend
        from .backends.wav2lip import Wav2LipBackend
        from .backends.liveportrait import LivePortraitBackend

        self._backends[DigitalHumanBackend.SADTALKER] = SadTalkerBackend(
            model_path=self._config.get("sadtalker_model_path"),
            device=self._config.get("device", "cuda"),
        )
        self._backends[DigitalHumanBackend.WAV2LIP] = Wav2LipBackend(
            model_path=self._config.get("wav2lip_model_path"),
            device=self._config.get("device", "cuda"),
        )
        self._backends[DigitalHumanBackend.LIVE_PORTRAIT] = LivePortraitBackend(
            model_path=self._config.get("liveportrait_model_path"),
            device=self._config.get("device", "cuda"),
        )

        # 初始化 TTS 引擎
        from .tts.cosyvoice import CosyVoiceEngine
        from .tts.edge_tts import EdgeTTSEngine

        self._tts_engines[TTSType.COSYVOICE] = CosyVoiceEngine(
            model_path=self._config.get("cosyvoice_model_path"),
        )
        self._tts_engines[TTSType.EDGE_TTS] = EdgeTTSEngine()

        # 预热后端
        for backend in self._backends.values():
            if hasattr(backend, "warmup"):
                await backend.warmup()

        self._initialized = True
        logger.info(f"DigitalHumanService initialized with {len(self._backends)} backends")

    async def generate(
        self,
        request: DigitalHumanRequest,
        on_progress: callable = None,
    ) -> DigitalHumanResult:
        """
        生成数字人视频

        Args:
            request: 生成请求
            on_progress: 进度回调 (progress: int, message: str)

        Returns:
            DigitalHumanResult
        """
        import time
        start = time.perf_counter()

        task_id = f"dh_{uuid.uuid4().hex[:8]}"

        try:
            # 1. 检查输入
            if not request.source_image:
                return DigitalHumanResult(
                    success=False,
                    task_id=task_id,
                    error="source_image is required",
                )

            # 2. 如果没有音频，调用 TTS 生成
            audio_path = request.audio_path
            if not audio_path and request.script:
                logger.info(f"[{task_id}] Generating TTS for script: {request.script[:50]}...")
                tts_engine = self._tts_engines.get(request.tts_type)
                if not tts_engine:
                    return DigitalHumanResult(
                        success=False,
                        task_id=task_id,
                        error=f"TTS engine not available: {request.tts_type}",
                    )

                tts_result = await tts_engine.generate(
                    text=request.script,
                    voice=request.voice,
                    output_dir=request.output_dir,
                )
                if not tts_result.success:
                    return DigitalHumanResult(
                        success=False,
                        task_id=task_id,
                        error=f"TTS failed: {tts_result.error}",
                    )
                audio_path = tts_result.audio_path
                logger.info(f"[{task_id}] TTS generated: {audio_path}")

            if not audio_path:
                return DigitalHumanResult(
                    success=False,
                    task_id=task_id,
                    error="Either audio_path or script is required",
                )

            # 3. 获取后端
            backend = self._backends.get(request.backend)
            if not backend:
                return DigitalHumanResult(
                    success=False,
                    task_id=task_id,
                    error=f"Backend not available: {request.backend}",
                )

            # 4. 生成数字人视频
            logger.info(f"[{task_id}] Generating digital human with {request.backend}...")
            if on_progress:
                on_progress(30, "正在生成数字人视频...")

            result = await backend.generate(
                source_image=request.source_image,
                audio_path=audio_path,
                output_dir=request.output_dir or str(ensure_download_path() / "digital_human"),
                duration=request.duration,
                enhancement=request.enhancement,
            )

            latency_ms = (time.perf_counter() - start) * 1000

            if result.success:
                return DigitalHumanResult(
                    success=True,
                    task_id=task_id,
                    video_path=result.video_path,
                    video_url=f"/api/v1/digital_human/video/{task_id}",
                    duration=result.duration,
                    backend=request.backend.value,
                    latency_ms=latency_ms,
                )
            else:
                return DigitalHumanResult(
                    success=False,
                    task_id=task_id,
                    error=result.error,
                    latency_ms=latency_ms,
                )

        except Exception as e:
            logger.error(f"[{task_id}] Digital human generation failed: {e}")
            return DigitalHumanResult(
                success=False,
                task_id=task_id,
                error=str(e),
                latency_ms=(time.perf_counter() - start) * 1000,
            )
```

#### 3.4.3 SadTalker 后端实现

```python
# backend/app/services/digital_human/backends/sadtalker.py

"""
SadTalker 后端实现

SadTalker: 从单张照片 + 音频生成高质量说话视频
论文: https://arxiv.org/abs/2212.04363
开源: https://github.com/OpenTalker/SadTalker
"""

from __future__ import annotations

import os
import logging
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("ylcraft.digital_human.sadtalker")

@dataclass
class SadTalkerConfig:
    """SadTalker 配置"""
    model_path: str = "models/SadTalker"
    checkpoint_dir: str = "models/SadTalker/checkpoints"
    device: str = "cuda"  # cuda / cpu
    ffmpeg_path: str = "ffmpeg"  # 确保已安装


class SadTalkerBackend:
    """
    SadTalker 数字人后端

    输入：人脸图片 + 音频
    输出：说话头肩视频
    """

    def __init__(self, config: SadTalkerConfig = None):
        self._config = config or SadTalkerConfig()

    async def generate(
        self,
        source_image: str,
        audio_path: str,
        output_dir: str,
        duration: int = 10,
        enhancement: bool = True,
        **kwargs,
    ) -> dict:
        """
        生成说话视频

        Args:
            source_image: 源图片路径
            audio_path: 音频文件路径
            output_dir: 输出目录
            duration: 最大时长
            enhancement: 是否使用增强

        Returns:
            {"success": bool, "video_path": str, "duration": float, "error": str}
        """
        try:
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"sadtalker_{Path(source_image).stem}.mp4")

            # 构建 SadTalker 命令
            cmd = [
                "python", "-m", "sadtalker",
                "--driven_audio", audio_path,
                "--source_image", source_image,
                "--result_dir", output_dir,
                "--enhance", str(enhancement).lower(),
                "--device", self._config.device,
            ]

            logger.info(f"Running SadTalker: {' '.join(cmd)}")

            # 执行（同步转异步）
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                error_msg = stderr.decode() if stderr else "SadTalker failed"
                logger.error(f"SadTalker error: {error_msg}")
                return {"success": False, "error": error_msg}

            # 查找输出文件
            # SadTalker 默认输出在 result_dir/<filename>/ 目录
            expected_dir = os.path.join(output_dir, Path(source_image).stem)
            if os.path.exists(expected_dir):
                # 查找生成的视频
                for f in os.listdir(expected_dir):
                    if f.endswith(".mp4"):
                        video_path = os.path.join(expected_dir, f)
                        # 获取视频时长
                        duration = await self._get_video_duration(video_path)
                        return {
                            "success": True,
                            "video_path": video_path,
                            "duration": duration,
                        }

            return {"success": False, "error": "Output video not found"}

        except Exception as e:
            logger.error(f"SadTalker generation failed: {e}")
            return {"success": False, "error": str(e)}

    async def _get_video_duration(self, video_path: str) -> float:
        """获取视频时长"""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        try:
            return float(stdout.decode().strip())
        except:
            return 0.0

    async def warmup(self):
        """预热模型"""
        logger.info("Warming up SadTalker...")
        # 可以做一些轻量预热
        await asyncio.sleep(0.1)
```

#### 3.4.4 CosyVoice TTS 实现

```python
# backend/app/services/digital_human/tts/cosyvoice.py

"""
CosyVoice 2.0 TTS 引擎

阿里开源的高质量语音合成，支持声音克隆
GitHub: https://github.com/Silicon-Identifier/CosyVoice
"""

from __future__ import annotations

import os
import logging
import asyncio
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("ylcraft.digital_human.cosyvoice")

@dataclass
class CosyVoiceResult:
    """TTS 生成结果"""
    success: bool
    audio_path: Optional[str] = None
    duration: float = 0.0
    error: Optional[str] = None


class CosyVoiceEngine:
    """
    CosyVoice 2.0 TTS 引擎

    支持：
    - 文本转语音
    - 声音克隆（需要参考音频）
    - 情感控制
    """

    def __init__(self, model_path: str = None, device: str = "cuda"):
        self._model_path = model_path or "models/CosyVoice"
        self._device = device
        self._model = None

    async def initialize(self):
        """加载模型"""
        if self._model is not None:
            return

        try:
            # 方式 1: 使用 cosyvoice Python SDK
            # from cosyvoice import CosyVoice
            # self._model = CosyVoice(self._model_path, device=self._device)

            # 方式 2: 使用 API 服务（推荐生产环境）
            # 如果有 CosyVoice 服务运行
            self._api_url = os.environ.get("COSYVOICE_API_URL", "http://127.0.0.1:5000")

            logger.info(f"CosyVoice initialized with API: {self._api_url}")

        except Exception as e:
            logger.warning(f"CosyVoice init failed, falling back to Edge-TTS: {e}")
            self._model = None

    async def generate(
        self,
        text: str,
        voice: str = "中文女声",
        output_dir: str = None,
        reference_audio: str = None,
        speed: float = 1.0,
    ) -> CosyVoiceResult:
        """
        生成语音

        Args:
            text: 待合成文本
            voice: 音色名称
            output_dir: 输出目录
            reference_audio: 参考音频（用于声音克隆）
            speed: 语速

        Returns:
            CosyVoiceResult
        """
        try:
            output_dir = output_dir or "storage/tts"
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"cosyvoice_{os.getpid()}.wav")

            if self._model:
                # 本地模式
                result = self._model.inference(
                    text=text,
                    stream=False,
                    speed=speed,
                )
                # 保存音频
                with open(output_path, "wb") as f:
                    f.write(result["audio"])
            else:
                # API 模式
                import httpx
                async with httpx.AsyncClient(timeout=60.0) as client:
                    response = await client.post(
                        f"{self._api_url}/tts",
                        json={
                            "text": text,
                            "voice": voice,
                            "speed": speed,
                            "reference_audio": reference_audio,
                        }
                    )
                    response.raise_for_status()
                    with open(output_path, "wb") as f:
                        f.write(response.content)

            duration = await self._get_audio_duration(output_path)
            return CosyVoiceResult(
                success=True,
                audio_path=output_path,
                duration=duration,
            )

        except Exception as e:
            logger.error(f"CosyVoice generation failed: {e}")
            return CosyVoiceResult(success=False, error=str(e))

    async def _get_audio_duration(self, audio_path: str) -> float:
        """获取音频时长"""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        try:
            return float(stdout.decode().strip())
        except:
            return 0.0
```

### 3.5 数字人 API

```python
# backend/app/api/v1/digital_human.py

"""
YLCraft — 数字人工厂 API

POST /api/v1/digital_human/generate    — 生成数字人视频
GET  /api/v1/digital_human/backends    — 列出可用后端
GET  /api/v1/digital_human/voices      — 列出可用音色
GET  /api/v1/digital_human/video/:id  — 获取生成的视频
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services.digital_human.service import (
    DigitalHumanService,
    DigitalHumanRequest,
    DigitalHumanBackend,
    TTSType,
)

router = APIRouter()
logger = logging.getLogger("ylcraft.digital_human")

# 服务实例
_service: Optional[DigitalHumanService] = None

def get_service() -> DigitalHumanService:
    global _service
    if _service is None:
        _service = DigitalHumanService()
        import asyncio
        asyncio.create_task(_service.initialize())
    return _service


# =============================================================================
# 请求/响应模型
# =============================================================================

class DigitalHumanGenerateRequest(BaseModel):
    """数字人生成请求"""
    # 输入
    source_image_url: Optional[str] = Field(None, description="源图片 URL")
    script: Optional[str] = Field(None, description="文本脚本（将转为语音）")
    audio_url: Optional[str] = Field(None, description="已有音频 URL")

    # 配置
    backend: str = Field("sadtalker", description="后端类型: sadtalker / wav2lip / liveportrait")
    tts_type: str = Field("edge_tts", description="TTS 类型: cosyvoice / edge_tts")
    voice: str = Field("zh-CN-XiaoxiaoNeural", description="TTS 音色")

    # 参数
    duration: int = Field(10, ge=3, le=60, description="最大时长")
    enhancement: bool = Field(True, description="面部增强")
    background_mode: str = Field("source", description="背景模式")


class DigitalHumanResponse(BaseModel):
    """数字人生成响应"""
    success: bool
    task_id: Optional[str] = None
    video_url: Optional[str] = None
    video_path: Optional[str] = None
    status: str = "pending"
    progress: int = 0
    error: Optional[str] = None


class BackendInfo(BaseModel):
    name: str
    description: str
    input_type: str
    capabilities: list[str]


class VoiceInfo(BaseModel):
    name: str
    language: str
    gender: str


# =============================================================================
# API 路由
# =============================================================================

@router.get("/backends", summary="可用数字人后端")
async def list_backends():
    """返回所有可用的数字人后端"""
    return {
        "success": True,
        "backends": [
            BackendInfo(
                name="sadtalker",
                description="SadTalker - 单张照片 + 音频生成说话视频",
                input_type="image + audio",
                capabilities=["head_pose", "expression", "lip_sync"],
            ),
            BackendInfo(
                name="wav2lip",
                description="Wav2Lip - 高精度唇形同步",
                input_type="face_region + audio",
                capabilities=["lip_sync", "high_accuracy"],
            ),
            BackendInfo(
                name="liveportrait",
                description="LivePortrait - 单图驱动表情和头动",
                input_type="image + driving",
                capabilities=["expression", "head_movement", "eye_blink"],
            ),
        ]
    }


@router.get("/voices", summary="可用 TTS 音色")
async def list_voices(tts_type: str = "edge_tts"):
    """返回所有可用的 TTS 音色"""
    if tts_type == "edge_tts":
        return {
            "success": True,
            "voices": [
                VoiceInfo(name="zh-CN-XiaoxiaoNeural", language="中文", gender="女"),
                VoiceInfo(name="zh-CN-YunxiNeural", language="中文", gender="男"),
                VoiceInfo(name="zh-CN-XiaoyiNeural", language="中文", gender="女"),
                VoiceInfo(name="en-US-JennyNeural", language="英文", gender="女"),
                VoiceInfo(name="en-US-GuyNeural", language="英文", gender="男"),
            ]
        }
    elif tts_type == "cosyvoice":
        return {
            "success": True,
            "voices": [
                VoiceInfo(name="中文女声", language="中文", gender="女"),
                VoiceInfo(name="中文男声", language="中文", gender="男"),
                VoiceInfo(name="英文女声", language="英文", gender="女"),
                VoiceInfo(name="英文男声", language="英文", gender="男"),
            ]
        }
    return {"success": False, "error": "Unknown TTS type"}


@router.post("/generate", summary="生成数字人视频")
async def generate_digital_human(
    request: DigitalHumanGenerateRequest,
):
    """
    生成数字人视频

    工作流程：
    1. 如果提供了 script，调用 TTS 生成音频
    2. 调用数字人后端生成说话视频
    3. 返回 task_id，前端可轮询或使用 WebSocket 获取进度
    """
    service = get_service()

    try:
        # 验证输入
        if not request.source_image_url and not request.script:
            return DigitalHumanResponse(
                success=False,
                error="source_image_url or script is required",
            )

        if not request.script and not request.audio_url:
            return DigitalHumanResponse(
                success=False,
                error="script or audio_url is required",
            )

        # 映射后端类型
        backend_map = {
            "sadtalker": DigitalHumanBackend.SADTALKER,
            "wav2lip": DigitalHumanBackend.WAV2LIP,
            "liveportrait": DigitalHumanBackend.LIVE_PORTRAIT,
        }
        backend = backend_map.get(request.backend, DigitalHumanBackend.SADTALKER)

        # 映射 TTS 类型
        tts_map = {
            "cosyvoice": TTSType.COSYVOICE,
            "edge_tts": TTSType.EDGE_TTS,
        }
        tts_type = tts_map.get(request.tts_type, TTSType.EDGE_TTS)

        # 构建请求
        dh_request = DigitalHumanRequest(
            source_image=request.source_image_url or "",
            script=request.script,
            audio_path=request.audio_url,
            backend=backend,
            tts_type=tts_type,
            voice=request.voice,
            duration=request.duration,
            enhancement=request.enhancement,
            background=request.background_mode,
        )

        # 生成
        result = await service.generate(dh_request)

        return DigitalHumanResponse(
            success=result.success,
            task_id=result.task_id,
            video_url=result.video_url,
            video_path=result.video_path,
            status="done" if result.success else "error",
            progress=100 if result.success else 0,
            error=result.error,
        )

    except Exception as e:
        logger.error(f"Digital human generation failed: {e}")
        return DigitalHumanResponse(
            success=False,
            error=str(e),
        )


@router.post("/upload", summary="上传源图片")
async def upload_source_image(file: UploadFile = File(...)):
    """
    上传源图片用于数字人生成

    支持格式：PNG, JPG, WEBP
    建议：正脸、无遮挡、高清
    """
    from app.core.config import ensure_download_path
    import uuid

    # 验证格式
    allowed_types = ["image/png", "image/jpeg", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(400, f"Unsupported file type: {file.content_type}")

    upload_dir = ensure_download_path() / "digital_human" / "source"
    upload_dir.mkdir(parents=True, exist_ok=True)

    # 保存文件
    filename = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    file_path = upload_dir / filename

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    return {
        "success": True,
        "url": f"/api/v1/digital_human/images/{filename}",
        "path": str(file_path),
    }


@router.get("/images/{filename}", summary="获取源图片")
async def get_source_image(filename: str):
    """返回上传的源图片"""
    from app.core.config import ensure_download_path
    image_dir = ensure_download_path() / "digital_human" / "source"
    file_path = image_dir / filename

    if not file_path.exists():
        raise HTTPException(404, "Image not found")

    return FileResponse(path=str(file_path))


@router.get("/video/{task_id}", summary="获取生成的视频")
async def get_digital_human_video(task_id: str):
    """
    获取生成的数字人视频

    TODO: 需要一个任务存储来映射 task_id -> video_path
    """
    # 临时实现：需要任务存储
    raise HTTPException(404, "Video not found or task not completed")
```

---

## 四、前端集成方案

### 4.1 目录结构

```
frontend/src/pages/
├── digital_human/                # 🆕 数字人工厂页面
│   ├── index.tsx                 # 主页面
│   ├── components/
│   │   ├── SourceUploader.tsx     # 源图片上传
│   │   ├── ScriptEditor.tsx      # 脚本编辑器
│   │   ├── BackendSelector.tsx   # 后端选择器
│   │   ├── VoiceSelector.tsx     # 音色选择
│   │   └── VideoPreview.tsx      # 视频预览
│   └── hooks/
│       └── useDigitalHuman.ts    # API Hook
└── ...
```

### 4.2 主页面组件

```tsx
// frontend/src/pages/digital_human/index.tsx

import { useState, useCallback } from 'react'
import { Card, Row, Col, Upload, Input, Select, Slider, Switch, Button, message, Spin, Modal, Space, Tag } from 'antd'
import { RobotOutlined, AudioOutlined, VideoCameraOutlined, PlayCircleOutlined, UploadOutlined } from '@ant-design/icons'

const { TextArea } = Input
const { Dragger } = Upload

interface DigitalHumanConfig {
  sourceImage: string
  script: string
  backend: string
  ttsType: string
  voice: string
  duration: number
  enhancement: boolean
}

export default function DigitalHumanPage() {
  // 配置状态
  const [config, setConfig] = useState<DigitalHumanConfig>({
    sourceImage: '',
    script: '',
    backend: 'sadtalker',
    ttsType: 'edge_tts',
    voice: 'zh-CN-XiaoxiaoNeural',
    duration: 10,
    enhancement: true,
  })

  // 任务状态
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [previewVisible, setPreviewVisible] = useState(false)

  // 上传源图片
  const handleImageUpload = async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)

    try {
      const res = await fetch('/api/v1/digital_human/upload', {
        method: 'POST',
        body: formData,
      })
      const data = await res.json()

      if (data.success) {
        setConfig(prev => ({ ...prev, sourceImage: data.url }))
        message.success('图片上传成功')
      } else {
        message.error(data.error || '上传失败')
      }
    } catch (e) {
      message.error('上传失败')
    }

    return false // 阻止默认上传
  }

  // 生成数字人
  const handleGenerate = async () => {
    if (!config.sourceImage && !config.script) {
      message.warning('请上传源图片或输入脚本')
      return
    }

    if (!config.script) {
      message.warning('请输入脚本内容')
      return
    }

    setGenerating(true)

    try {
      const res = await fetch('/api/v1/digital_human/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      })
      const data = await res.json()

      if (data.success) {
        setResult(data)
        message.success('数字人生成任务已提交')
      } else {
        message.error(data.error || '生成失败')
      }
    } catch (e) {
      message.error('生成失败')
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div style={{ padding: 24 }}>
      <Row gutter={24}>
        {/* 左侧：配置面板 */}
        <Col xs={24} lg={12}>
          <Card
            title={
              <span>
                <RobotOutlined style={{ marginRight: 8 }} />
                数字人工厂
              </span>
            }
          >
            {/* 源图片上传 */}
            <div style={{ marginBottom: 24 }}>
              <div style={{ marginBottom: 8, fontWeight: 500 }}>源图片</div>
              {config.sourceImage ? (
                <div style={{ position: 'relative' }}>
                  <img
                    src={config.sourceImage}
                    style={{ width: '100%', borderRadius: 8 }}
                  />
                  <Button
                    size="small"
                    style={{ position: 'absolute', top: 8, right: 8 }}
                    onClick={() => setConfig(prev => ({ ...prev, sourceImage: '' }))}
                  >
                    重新上传
                  </Button>
                </div>
              ) : (
                <Dragger
                  accept="image/*"
                  showUploadList={false}
                  beforeUpload={handleImageUpload}
                >
                  <p><UploadOutlined style={{ fontSize: 32 }} /></p>
                  <p>点击或拖拽上传人脸图片</p>
                  <p style={{ color: '#999', fontSize: 12 }}>建议正脸、无遮挡、高清图片</p>
                </Dragger>
              )}
            </div>

            {/* 脚本输入 */}
            <div style={{ marginBottom: 24 }}>
              <div style={{ marginBottom: 8, fontWeight: 500 }}>脚本内容</div>
              <TextArea
                placeholder="输入要生成的语音脚本..."
                value={config.script}
                onChange={e => setConfig(prev => ({ ...prev, script: e.target.value }))}
                rows={4}
              />
              <div style={{ marginTop: 4, color: '#999', fontSize: 12 }}>
                {config.script.length} 字
              </div>
            </div>

            {/* 参数配置 */}
            <Card size="small" title="参数配置" style={{ marginBottom: 24 }}>
              <Space direction="vertical" style={{ width: '100%' }}>
                <div>
                  <span>数字人后端：</span>
                  <Select
                    value={config.backend}
                    onChange={v => setConfig(prev => ({ ...prev, backend: v }))}
                    style={{ width: 200 }}
                    options={[
                      { label: 'SadTalker（推荐）', value: 'sadtalker' },
                      { label: 'Wav2Lip', value: 'wav2lip' },
                      { label: 'LivePortrait', value: 'liveportrait' },
                    ]}
                  />
                </div>

                <div>
                  <span>TTS 引擎：</span>
                  <Select
                    value={config.ttsType}
                    onChange={v => setConfig(prev => ({ ...prev, ttsType: v }))}
                    style={{ width: 200 }}
                    options={[
                      { label: 'Edge-TTS（推荐）', value: 'edge_tts' },
                      { label: 'CosyVoice', value: 'cosyvoice' },
                    ]}
                  />
                </div>

                <div>
                  <span>音色：</span>
                  <Select
                    value={config.voice}
                    onChange={v => setConfig(prev => ({ ...prev, voice: v }))}
                    style={{ width: 200 }}
                    options={
                      config.ttsType === 'edge_tts' ? [
                        { label: '晓晓（女声）', value: 'zh-CN-XiaoxiaoNeural' },
                        { label: '云希（男声）', value: 'zh-CN-YunxiNeural' },
                        { label: '云扬（男声）', value: 'zh-CN-YunyangNeural' },
                      ] : [
                        { label: '中文女声', value: '中文女声' },
                        { label: '中文男声', value: '中文男声' },
                      ]
                    }
                  />
                </div>

                <div>
                  <span>最大时长：{config.duration} 秒</span>
                  <Slider
                    min={3}
                    max={60}
                    value={config.duration}
                    onChange={v => setConfig(prev => ({ ...prev, duration: v }))}
                  />
                </div>

                <div>
                  <span>面部增强：</span>
                  <Switch
                    checked={config.enhancement}
                    onChange={v => setConfig(prev => ({ ...prev, enhancement: v }))}
                  />
                </div>
              </Space>
            </Card>

            {/* 生成按钮 */}
            <Button
              type="primary"
              size="large"
              block
              icon={<VideoCameraOutlined />}
              onClick={handleGenerate}
              loading={generating}
              disabled={generating}
            >
              {generating ? '生成中...' : '生成数字人视频'}
            </Button>
          </Card>
        </Col>

        {/* 右侧：预览 */}
        <Col xs={24} lg={12}>
          <Card title="预览">
            {result?.video_url ? (
              <div>
                <video
                  src={result.video_url}
                  controls
                  style={{ width: '100%', borderRadius: 8 }}
                />
                <Space style={{ marginTop: 16 }}>
                  <Button icon={<PlayCircleOutlined />}>播放</Button>
                  <Tag color="green">生成成功</Tag>
                </Space>
              </div>
            ) : (
              <div style={{
                height: 400,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: '#f5f5f5',
                borderRadius: 8
              }}>
                <span style={{ color: '#999' }}>
                  {generating ? '正在生成...' : '点击生成后在此预览'}
                </span>
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
```

---

## 五、与 Live2D 的关系与差异

### 5.1 能力矩阵对比

| 维度 | Live2D 工厂（已有） | 数字人工厂（新增） |
|------|---------------------|-------------------|
| **输入** | Cosplay 照片/立绘 | 真人照片/视频 |
| **输出** | Live2D 模型（.model3.json） | MP4 视频 |
| **技术** | 抠图 + Live2D Cubism SDK | SadTalker/Wav2Lip |
| **交互** | 实时互动、WebGL 预览 | 一次性视频输出 |
| **用途** | 虚拟主播、角色互动 | AI 主播、新闻播报 |
| **输出格式** | 可交互动画 | 不可交互视频 |

### 5.2 架构独立性

```
backend/app/services/
├── live2d/                   # Live2D 工厂（已有）
│   ├── service.py
│   ├── pipeline.py
│   ├── vts_exporter.py
│   └── ...
│
└── digital_human/            # 🆕 数字人工厂（独立）
    ├── service.py
    ├── backends/
    │   ├── sadtalker.py
    │   ├── wav2lip.py
    │   └── liveportrait.py
    └── tts/
        ├── cosyvoice.py
        └── edge_tts.py
```

**关键设计原则**：
- ✅ 两个模块完全独立，无共享代码
- ✅ 独立 API 路由 (`/api/v1/live2d/*` vs `/api/v1/digital_human/*`)
- ✅ 独立前端页面
- ✅ 独立服务类
- ✅ 可以同时使用，互不影响

---

## 六、部署要求

### 6.1 ComfyUI 部署

```bash
# 方式 1：本地部署
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
pip install -r requirements.txt
python main.py --listen 0.0.0.0 --port 8188

# 方式 2：Docker 部署
docker run -p 8188:8188 \
  -v /path/to/models:/root/.local/Share/ComfyUI/Model \
  ghcr.io/comfyanonymous/comfyui:latest
```

### 6.2 模型下载

| 模型 | 大小 | 用途 | 下载链接 |
|------|------|------|---------|
| sd15 | ~4GB | 基础图像生成 | Civitai/HuggingFace |
| FLUX | ~30GB | 高质量图像 | [待确认] |
| Wan21 | ~20GB | 视频生成 | [待确认] |
| SadTalker | ~2GB | 说话视频 | GitHub release |
| Wav2Lip | ~1GB | 唇形同步 | GitHub release |
| CosyVoice | ~5GB | 高质量 TTS | ModelScope |

### 6.3 硬件要求

| 场景 | 最低配置 | 推荐配置 |
|------|---------|---------|
| **ComfyUI 图像** | RTX 3060 12GB | RTX 4090 24GB |
| **ComfyUI 视频** | RTX 4080 16GB | A100 40GB |
| **SadTalker** | RTX 3060 8GB | RTX 3090 24GB |
| **Wav2Lip** | RTX 3060 8GB | RTX 3090 24GB |
| **CosyVoice** | RTX 3060 8GB | RTX 3090 24GB |

---

## 七、总结与建议

### 7.1 可行性结论

| 问题 | 结论 | 说明 |
|------|------|------|
| **技术可行吗？** | ✅ 完全可行 | YLCraft 架构天然支持新 Backend 接入 |
| **需要大改吗？** | ❌ 几乎不需要 | 只需新增模块，核心架构不变 |
| **与 Live2D 冲突吗？** | ❌ 零冲突 | 完全独立模块，独立 API |
| **有参考项目吗？** | ✅ 有 | Pixelle-Video 提供了完整参考 |
| **难度大吗？** | ⚠️ 中等 | SadTalker 等有成熟开源实现 |

### 7.2 建议优先级

```
第一阶段（推荐先做）：
├── 🏆 ComfyUI 图像 Backend 接入
│   └── 价值高、难度低、有成熟 API
│
└── 🥈 CosyVoice TTS 接入
    └── 提升数字人语音质量

第二阶段：
├── 📹 ComfyUI 视频 Backend 接入
│
└── 🤖 数字人工厂（SadTalker）
    └── AI 主播场景

第三阶段：
├── 🔄 Wav2Lip 后端
├── 🎭 LivePortrait 后端
└── 🎨 更多 ComfyUI 工作流
```

### 7.3 关键成功因素

1. **复用现有架构**：完全基于 BackendManager + 抽象基类
2. **渐进式开发**：先图像后视频，先简单后复杂
3. **模块化设计**：每个后端独立实现，便于测试和替换
4. **参考 Pixelle-Video**：借鉴其 ComfyUI + TTS + 数字人的完整流水线

---

## 八、下一步行动

如需开始实施，建议按以下顺序：

1. **ComfyUI 集成**
   - [ ] 创建 `backend/app/services/comfyui/` 目录
   - [ ] 实现 `ComfyUIClient` API 客户端
   - [ ] 实现 `ComfyUIImageBackend`
   - [ ] 注册到 BackendManager
   - [ ] 配置 YAML 文件

2. **数字人工厂**
   - [ ] 创建 `backend/app/services/digital_human/` 目录
   - [ ] 实现 `DigitalHumanService` 主服务
   - [ ] 实现 SadTalker 后端
   - [ ] 接入 Edge-TTS
   - [ ] 创建 `/api/v1/digital_human/` API
   - [ ] 创建前端页面

3. **测试验证**
   - [ ] ComfyUI 图像生成测试
   - [ ] 数字人视频生成测试
   - [ ] 全流程集成测试

---

*报告生成时间：2026-05-06*
