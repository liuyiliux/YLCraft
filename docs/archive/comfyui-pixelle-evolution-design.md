# YLCraft ComfyUI 演进规划 — 借鉴 Pixelle-Video

> **版本**：v1.0.0
> **参考来源**：Pixelle-Video (AIDC-AI/Pixelle-Video)
> **状态**：规划阶段
> **最后更新**：2026-05-06

---

## 一、参考来源分析

### 1.1 Pixelle-Video 项目简介

**Pixelle-Video** 是 AIDC-AI 开源的 AI 全自动短视频生成引擎，GitHub Stars 10k+，基于 ComfyUI 架构设计。

**核心特点**：
- 输入主题 → 3 分钟自动生成完整短视频
- 支持本地 ComfyUI / RunningHub 云端 GPU
- 原子能力灵活组合，工作流可替换

### 1.2 源代码结构

```
Pixelle-Video/
├── pixelle_video/           # 核心源码
│   ├── pipelines/          # 流水线编排（视频生成主流程）
│   ├── services/           # 外部服务抽象（LLM、TTS、ComfyUI）
│   ├── prompts/           # LLM 提示词模板
│   └── utils/             # 辅助工具函数
├── workflows/             # ComfyUI 工作流（selfhost/ + runninghub/）
├── templates/             # HTML 视频模板
└── api/                   # API 模块
```

### 1.3 技术栈

| 组件 | 技术 |
|------|------|
| **语言** | Python |
| **Web 框架** | Streamlit |
| **AI 集成** | ComfyUI + RunningHub |
| **LLM 支持** | GPT、通义千问、DeepSeek、Ollama |
| **TTS** | Edge-TTS、Index-TTS、声音克隆 |
| **视频合成** | FFmpeg |

---

## 二、YLCraft vs Pixelle-Video 对比

| 维度 | Pixelle-Video | YLCraft ComfyUI | YLCraft 现状 |
|------|---------------|-----------------|--------------|
| **架构定位** | 视频生成引擎 | AI 内容创作平台 | ✅ 多场景覆盖 |
| **ComfyUI 用途** | 图像 + TTS + 视频 | 图像 + 视频 | ⚠️ 需扩展 |
| **连接模式** | 本地 / RunningHub 云端 | 本地多节点 | ❌ 无云端 |
| **节点管理** | 单节点配置 | 多节点连接池 | ✅ 已实现 |
| **调度器** | 无专门调度器 | ComfyUIScheduler | ✅ 已实现 |
| **工作流存储** | JSON 文件 | 数据库 + 文件 | ⚠️ 需整合 |
| **视频合成** | 内置 FFmpeg | CutClaw 模块 | ⚠️ 需集成 |
| **TTS 集成** | Edge-TTS + 声音克隆 | 字幕服务 | ❌ 无独立 TTS |
| **数字人口播** | 支持 | 无 | ❌ 缺失 |
| **工作流热重载** | 支持 | 无 | ❌ 缺失 |
| **并行任务** | 支持 | 基础异步 | ⚠️ 需优化 |

---

## 三、借鉴规划

### 3.1 功能优先级矩阵

| # | 功能 | 当前状态 | 优先级 | 工作量 |
|---|------|---------|--------|--------|
| 1 | RunningHub 云端 GPU 集成 | ❌ 无 | ⭐⭐⭐ 高 | 2-3 天 |
| 2 | 工作流自动发现 + 热重载 | ❌ 仅数据库 | ⭐⭐⭐ 高 | 2 天 |
| 3 | 视频生成流水线 | ⚠️ 分散 | ⭐⭐⭐ 高 | 3-4 天 |
| 4 | TTS 语音合成服务 | ⚠️ 部分 | ⭐⭐ 中 | 2-3 天 |
| 5 | 数字人口播模块 | ❌ 无 | ⭐⭐ 中 | 3-4 天 |
| 6 | HTML 视频模板系统 | ⚠️ CutClaw | ⭐⭐ 中 | 2 天 |
| 7 | 图生视频（WAN 2.1） | ⚠️ 基础 | ⭐⭐ 中 | 2-3 天 |
| 8 | 动作迁移 | ❌ 无 | ⭐ 低 | 4-5 天 |

---

## 四、详细设计

### 4.1 RunningHub 云端 GPU 集成 ⭐⭐⭐

#### 目标
支持 RunningHub 云端 GPU，无需本地显卡即可使用 ComfyUI 能力。

#### 架构设计

```
ComfyUIPool
├── LocalNode(s)          # 本地 ComfyUI（已有）
│   ├── node_id: str
│   ├── server_url: str
│   └── client: ComfyUIClient
├── RunningHubNode        # 🆕 云端 RunningHub
│   ├── api_key: str
│   ├── concurrent_limit: int
│   └── instance_type: str  # "standard" | "plus" (48GB)
└── HybridScheduler       # 混合调度器
```

#### 新增文件

```
backend/app/services/comfyui/
├── providers/            # 🆕 Provider 抽象
│   ├── __init__.py
│   ├── base.py           # CloudProvider 基类
│   ├── local.py          # 本地 ComfyUI（封装现有 Client）
│   └── runninghub.py      # RunningHub 实现
└── scheduler.py          # 混合调度器
```

#### 接口设计

```python
# backend/app/services/comfyui/providers/base.py

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

@dataclass
class WorkflowResult:
    """工作流执行结果"""
    success: bool
    job_id: str = ""
    outputs: Dict[str, Any] = None
    error: str = ""

class CloudProvider(ABC):
    """云端 Provider 抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 名称"""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> List[str]:
        """支持的能力"""
        pass

    @abstractmethod
    async def execute_workflow(
        self,
        workflow: Dict[str, Any],
        workflow_id: str = None,
    ) -> WorkflowResult:
        """执行工作流"""
        pass

    @abstractmethod
    async def get_job_status(self, job_id: str) -> str:
        """获取任务状态：pending / running / completed / failed"""
        pass

    @abstractmethod
    async def download_outputs(self, job_id: str) -> Dict[str, Any]:
        """下载输出文件"""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """健康检查"""
        pass
```

```python
# backend/app/services/comfyui/providers/runninghub.py

from .base import CloudProvider, WorkflowResult
import httpx

class RunningHubProvider(CloudProvider):
    """RunningHub 云端 Provider"""

    def __init__(
        self,
        api_key: str,
        concurrent_limit: int = 1,
        instance_type: str = "standard",
    ):
        self.api_key = api_key
        self.concurrent_limit = concurrent_limit
        self.instance_type = instance_type
        self.base_url = "https://api.runninghub.com"
        self._client = httpx.AsyncClient(timeout=300.0)

    async def execute_workflow(
        self,
        workflow: Dict[str, Any],
        workflow_id: str = None,
    ) -> WorkflowResult:
        # 1. 上传工作流到 RunningHub
        upload_resp = await self._client.post(
            f"{self.base_url}/v2/workflow/upload",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"workflow": workflow},
        )
        upload_resp.raise_for_status()
        remote_workflow_id = upload_resp.json()["workflow_id"]

        # 2. 提交执行
        exec_resp = await self._client.post(
            f"{self.base_url}/v2/workflow/run",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "workflow_id": remote_workflow_id,
                "instance_type": self.instance_type,
                "concurrent_limit": self.concurrent_limit,
            },
        )
        exec_resp.raise_for_status()
        job_id = exec_resp.json()["job_id"]

        return WorkflowResult(success=True, job_id=job_id)

    async def get_job_status(self, job_id: str) -> str:
        resp = await self._client.get(
            f"{self.base_url}/v2/workflow/status/{job_id}",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        resp.raise_for_status()
        return resp.json()["status"]

    async def download_outputs(self, job_id: str) -> Dict[str, Any]:
        resp = await self._client.get(
            f"{self.base_url}/v2/workflow/outputs/{job_id}",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        resp.raise_for_status()
        return resp.json()["outputs"]

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get(
                f"{self.base_url}/v2/user/balance",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            return resp.status_code == 200
        except Exception:
            return False
```

#### 配置扩展

```yaml
# config/comfyui.yaml

comfyui:
  # 本地节点
  local:
    - name: "local-gpu"
      url: "http://127.0.0.1:8188"
      capabilities: ["txt2img", "img2img", "video"]
      priority: 10

  # RunningHub 云端
  runninghub:
    api_key: "${RUNNINGHUB_API_KEY}"
    concurrent_limit: 1
    instance_type: "standard"  # standard (24GB) | plus (48GB)
    capabilities: ["txt2img", "img2img", "video", "wan21"]

  # 调度策略
  scheduler:
    prefer_local: true  # 优先使用本地节点
    fallback_cloud: true  # 本地节点不可用时切换云端
```

---

### 4.2 工作流自动发现 + 热重载 ⭐⭐⭐

#### 目标
支持从文件系统自动扫描工作流，并支持运行时热重载。

#### 目录结构

```
backend/
├── workflows/                    # 🆕 工作流文件目录
│   ├── image/
│   │   ├── flux.json            # FLUX 模型
│   │   ├── sdxl.json            # SDXL 模型
│   │   └── anime.json           # 动漫风格
│   ├── video/
│   │   ├── wan21.json           # Wan 2.1 视频生成
│   │   └── svd.json            # Stable Video Diffusion
│   ├── tts/
│   │   ├── edge.json            # Edge TTS
│   │   └── chatts.json          # ChatTTS
│   └── templates/               # HTML 视频模板
│       └── 1080x1920/
│           ├── image_default.html
│           └── video_default.html
```

#### 服务实现

```python
# backend/app/services/comfyui/discovery.py

from pathlib import Path
from typing import Dict, List, Optional
import json
import logging

logger = logging.getLogger("ylcraft.comfyui.discovery")

class WorkflowDiscovery:
    """工作流自动发现服务"""

    def __init__(self, workflow_dir: str = "workflows"):
        self.workflow_dir = Path(workflow_dir)

    async def scan_workflows(self) -> Dict[str, List[Dict]]:
        """
        扫描工作流目录，返回按类型分组的列表

        Returns:
            {
                "image": [{"path": "...", "name": "...", "category": "flux"}],
                "video": [...],
                "tts": [...],
            }
        """
        result = {"image": [], "video": [], "tts": [], "template": []}

        for category in result.keys():
            category_dir = self.workflow_dir / category
            if not category_dir.exists():
                continue

            for json_file in category_dir.glob("*.json"):
                try:
                    workflow = self._load_workflow(json_file)
                    result[category].append({
                        "path": str(json_file),
                        "name": json_file.stem,
                        "category": self._infer_category(workflow),
                        "nodes": len(workflow.get("nodes", {})),
                        "version": workflow.get("version", "unknown"),
                    })
                except Exception as e:
                    logger.warning(f"Failed to load {json_file}: {e}")

        # 扫描 HTML 模板
        template_dir = self.workflow_dir / "templates"
        if template_dir.exists():
            for html_file in template_dir.rglob("*.html"):
                result["template"].append({
                    "path": str(html_file),
                    "name": html_file.stem,
                    "size": html_file.stat().st_size,
                })

        return result

    async def auto_import(self) -> Dict[str, int]:
        """
        自动导入新工作流到数据库

        Returns:
            {"imported": 3, "updated": 1, "skipped": 5}
        """
        from app.services.comfyui.service import WorkflowService
        from app.db.models.comfyui import WorkflowCategory

        scanned = await self.scan_workflows()
        stats = {"imported": 0, "updated": 0, "skipped": 0}

        category_map = {
            "image": WorkflowCategory.TEXT_TO_IMAGE,
            "video": WorkflowCategory.VIDEO,
            "tts": WorkflowCategory.CUSTOM,
        }

        for category, workflows in scanned.items():
            if category == "template":
                continue

            for wf in workflows:
                try:
                    # 检查是否已存在
                    existing = await WorkflowService.get_template_by_name(wf["name"])

                    workflow_data = self._load_workflow(Path(wf["path"]))

                    if existing:
                        # 更新
                        await WorkflowService.update_template(
                            existing.id,
                            workflow_json=workflow_data,
                        )
                        stats["updated"] += 1
                    else:
                        # 创建
                        await WorkflowService.create_template(
                            name=wf["name"],
                            display_name=wf["name"].replace("_", " ").title(),
                            workflow_json=workflow_data,
                            category=category_map.get(category, WorkflowCategory.CUSTOM),
                            description=f"自动导入: {wf['path']}",
                        )
                        stats["imported"] += 1

                except Exception as e:
                    logger.error(f"Failed to import {wf['name']}: {e}")
                    stats["skipped"] += 1

        return stats

    async def hot_reload(self, template_id: str) -> bool:
        """
        热重载单个工作流

        Args:
            template_id: 工作流模板 ID

        Returns:
            是否成功
        """
        from app.services.comfyui.service import WorkflowService

        template = await WorkflowService.get_template(template_id)
        if not template:
            return False

        # 查找对应的文件
        path = self._find_workflow_file(template.name)
        if not path:
            return False

        # 重新加载
        workflow_data = self._load_workflow(path)
        await WorkflowService.update_template(
            template_id,
            workflow_json=workflow_data,
            workflow_version=template.workflow_version + 1,
        )

        logger.info(f"Hot reloaded workflow: {template.name}")
        return True

    def _load_workflow(self, path: Path) -> Dict:
        """加载工作流 JSON"""
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _infer_category(self, workflow: Dict) -> str:
        """推断工作流类型"""
        nodes = workflow.get("nodes", {})

        # 简单推断逻辑
        if any("Flux" in str(node) for node in nodes.values()):
            return "flux"
        if any("StableDiffusion" in str(node) for node in nodes.values()):
            return "sdxl"
        if any("WAN" in str(node) or "Video" in str(node) for node in nodes.values()):
            return "video"
        return "general"

    def _find_workflow_file(self, name: str) -> Optional[Path]:
        """根据名称查找工作流文件"""
        for category in ["image", "video", "tts"]:
            path = self.workflow_dir / category / f"{name}.json"
            if path.exists():
                return path
        return None
```

#### API 扩展

```python
# backend/app/api/v1/comfyui.py 新增端点

@router.get("/workflows/discover")
async def discover_workflows():
    """扫描工作流目录"""
    discovery = WorkflowDiscovery()
    return await discovery.scan_workflows()

@router.post("/workflows/sync")
async def sync_workflows():
    """同步工作流到数据库"""
    discovery = WorkflowDiscovery()
    return await discovery.auto_import()

@router.post("/workflows/{workflow_id}/reload")
async def reload_workflow(workflow_id: str):
    """热重载单个工作流"""
    discovery = WorkflowDiscovery()
    success = await discovery.hot_reload(workflow_id)
    return {"success": success}
```

---

### 4.3 视频生成流水线 ⭐⭐⭐

#### 目标
基于 Pixelle-Video 的流水线设计，实现完整的视频生成能力。

#### 架构设计

```
VideoPipeline
├── ScriptGenerator    # LLM 生成文案
├── ImageGenerator     # ComfyUI 并行生图
├── TTSGenerator       # 语音合成
├── BGMManager         # 背景音乐
└── FFmpegSynthesizer  # 最终合成
```

#### 新增文件

```
backend/app/services/
├── video_pipeline/           # 🆕 视频生成流水线
│   ├── __init__.py
│   ├── pipeline.py           # 主流水线
│   ├── script.py             # 文案生成
│   ├── image.py              # 图像生成
│   ├── tts.py                # TTS 合成
│   ├── bgm.py                # BGM 管理
│   └── synthesizer.py        # FFmpeg 合成
└── tts/                      # 🆕 TTS 服务
    ├── __init__.py
    ├── base.py               # TTS Provider 基类
    ├── edge.py               # Edge TTS
    ├── index.py              # 阿里云 TTS
    └── chatts.py             # ChatTTS 本地
```

#### 流水线实现

```python
# backend/app/services/video_pipeline/pipeline.py

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from pathlib import Path
import asyncio
import json

@dataclass
class Scene:
    """分镜"""
    index: int
    text: str                    # 旁白文案
    image_prompt: str            # 图像生成提示词
    duration: float = 3.0        # 持续时间（秒）

@dataclass
class VideoConfig:
    """视频配置"""
    topic: str                   # 主题
    n_scenes: int = 5            # 分镜数量
    resolution: str = "1080x1920" # 分辨率
    fps: int = 30
    template: str = "1080x1920/image_default.html"
    bgm_path: str = ""
    bgm_volume: float = 0.3
    tts_workflow: str = "edge"
    image_workflow: str = "flux"
    voice_ref: str = ""          # 声音克隆参考音频

@dataclass
class VideoResult:
    """视频生成结果"""
    success: bool
    output_path: Path = None
    duration: float = 0.0
    file_size: int = 0
    scenes: List[Scene] = None
    error: str = ""

class VideoPipeline:
    """视频生成流水线"""

    def __init__(
        self,
        llm_service,        # LLM 服务
        comfy_pool,         # ComfyUI 连接池
        tts_service,        # TTS 服务
        synthesizer,        # FFmpeg 合成器
    ):
        self.llm = llm_service
        self.comfy = comfy_pool
        self.tts = tts_service
        self.synthesizer = synthesizer

    async def generate(
        self,
        config: VideoConfig,
        output_dir: str = "output/videos",
    ) -> VideoResult:
        """
        生成视频

        流程：
        1. LLM 生成文案（分镜脚本）
        2. ComfyUI 并发生图
        3. TTS 语音合成
        4. BGM 混音
        5. FFmpeg 最终合成
        """
        output_path = Path(output_dir) / f"video_{int(time.time())}.mp4"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Step 1: 生成文案
            scenes = await self._generate_script(config.topic, config.n_scenes)

            # Step 2: 并发生图
            images = await self._generate_images(
                scenes,
                config.image_workflow,
                output_dir,
            )

            # Step 3: TTS 语音合成
            audio_files = await self._generate_audio(
                scenes,
                config.tts_workflow,
                config.voice_ref,
                output_dir,
            )

            # Step 4: FFmpeg 合成
            await self.synthesizer.synthesize(
                images=images,
                audio_files=audio_files,
                bgm_path=config.bgm_path,
                bgm_volume=config.bgm_volume,
                template=config.template,
                output_path=output_path,
            )

            # 获取输出信息
            stat = output_path.stat()

            return VideoResult(
                success=True,
                output_path=output_path,
                duration=sum(s.duration for s in scenes),
                file_size=stat.st_size,
                scenes=scenes,
            )

        except Exception as e:
            logger.error(f"Video pipeline failed: {e}")
            return VideoResult(success=False, error=str(e))

    async def _generate_script(self, topic: str, n_scenes: int) -> List[Scene]:
        """Step 1: LLM 生成文案"""
        prompt = f"""为短视频生成{n_scenes}个分镜脚本。

主题：{topic}

要求：
- 每个分镜包含旁白文案和图像生成提示词
- 旁白简洁有力，适合口播
- 图像提示词描述画面风格和内容
- 输出 JSON 格式"""

        response = await self.llm.chat(prompt)
        script_data = json.loads(response.content)

        return [
            Scene(
                index=i,
                text=scene["text"],
                image_prompt=scene["image_prompt"],
                duration=float(scene.get("duration", 3.0)),
            )
            for i, scene in enumerate(script_data["scenes"])
        ]

    async def _generate_images(
        self,
        scenes: List[Scene],
        workflow: str,
        output_dir: str,
    ) -> List[Path]:
        """Step 2: ComfyUI 并发生图"""
        async def generate_single(scene: Scene) -> Path:
            # 从连接池获取节点
            node = await self.comfy.select_node(capability="image")
            if not node:
                raise RuntimeError("No available ComfyUI node")

            # 执行工作流
            result = await node.client.generate_image(
                prompt=scene.image_prompt,
                workflow=workflow,
            )

            output_path = Path(output_dir) / f"scene_{scene.index}.png"
            await node.client.download_output(result["image_name"], output_path)
            return output_path

        # 并行执行
        return await asyncio.gather(*[generate_single(s) for s in scenes])

    async def _generate_audio(
        self,
        scenes: List[Scene],
        workflow: str,
        voice_ref: str,
        output_dir: str,
    ) -> List[Path]:
        """Step 3: TTS 语音合成"""
        audio_files = []

        for scene in scenes:
            audio_path = Path(output_dir) / f"audio_{scene.index}.mp3"

            await self.tts.synthesize(
                text=scene.text,
                output_path=audio_path,
                workflow=workflow,
                voice_ref=voice_ref,
            )

            audio_files.append(audio_path)

        return audio_files
```

---

### 4.4 TTS 语音合成服务 ⭐⭐

#### Provider 抽象

```python
# backend/app/services/tts/base.py

from abc import ABC, abstractmethod
from pathlib import Path
from dataclasses import dataclass

@dataclass
class TTSResult:
    success: bool
    audio_path: Path = None
    duration: float = 0.0
    error: str = ""

class TTSProvider(ABC):
    """TTS Provider 抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def capabilities(self) -> list[str]:
        """voice_clone, multi_language 等"""
        pass

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        output_path: Path,
        voice: str = "default",
        **kwargs,
    ) -> TTSResult:
        """文本转语音"""
        pass

    @abstractmethod
    async def voice_clone(
        self,
        reference_audio: Path,
        text: str,
        output_path: Path,
    ) -> TTSResult:
        """声音克隆"""
        pass
```

#### Edge TTS 实现

```python
# backend/app/services/tts/edge.py

import edge_tts
from pathlib import Path
from .base import TTSProvider, TTSResult

class EdgeTTSProvider(TTSProvider):
    """Edge TTS Provider（免费）"""

    def __init__(self):
        self._voices = {
            "zh-CN": "zh-CN-XiaoxiaoNeural",
            "zh-CN-female": "zh-CN-XiaoyiNeural",
            "zh-CN-male": "zh-CN-YunxiNeural",
            "en-US": "en-US-JennyNeural",
            "ko-KR": "ko-KR-SunHiNeural",
        }

    @property
    def name(self) -> str:
        return "edge-tts"

    @property
    def capabilities(self) -> list[str]:
        return ["basic", "multi_language"]

    async def synthesize(
        self,
        text: str,
        output_path: Path,
        voice: str = "zh-CN-XiaoxiaoNeural",
        **kwargs,
    ) -> TTSResult:
        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(output_path))

            return TTSResult(success=True, audio_path=output_path)
        except Exception as e:
            return TTSResult(success=False, error=str(e))

    async def voice_clone(self, reference_audio: Path, text: str, output_path: Path) -> TTSResult:
        # Edge TTS 不支持声音克隆
        return TTSResult(success=False, error="Edge TTS does not support voice cloning")
```

#### 声音克隆实现

```python
# backend/app/services/tts/voice_clone.py

class VoiceCloneProvider(TTSProvider):
    """声音克隆 Provider"""

    def __init__(self):
        self._model = None  # CosyVoice / XTTS 模型

    @property
    def name(self) -> str:
        return "voice-clone"

    @property
    def capabilities(self) -> list[str]:
        return ["voice_clone", "emotion_control"]

    async def voice_clone(
        self,
        reference_audio: Path,
        text: str,
        output_path: Path,
    ) -> TTSResult:
        """使用参考音频克隆声音"""
        try:
            # 1. 提取参考音频特征
            ref_features = await self._extract_features(reference_audio)

            # 2. 生成音频
            audio_data = await self._model.generate(
                text=text,
                reference=ref_features,
            )

            # 3. 保存
            with open(output_path, "wb") as f:
                f.write(audio_data)

            return TTSResult(success=True, audio_path=output_path)

        except Exception as e:
            return TTSResult(success=False, error=str(e))
```

---

### 4.5 数字人口播模块 ⭐⭐

#### 目标
上传参考音频 → 克隆音色 → 朗读任意文案

#### 使用场景
- 个人 IP 但不想露脸
- 多语言配音
- 批量视频生成

#### 实现方案

```python
# backend/app/services/avatar/digital_human.py

@dataclass
class AvatarConfig:
    reference_audio: Path              # 参考音频（3-30秒）
    reference_text: str = ""           # 参考音频对应文本（可选）
    language: str = "zh-CN"            # 语言
    emotion: str = "neutral"           # 情感风格

class DigitalHumanService:
    """数字人口播服务"""

    def __init__(self, tts_provider, video_backend):
        self.tts = tts_provider
        self.video = video_backend

    async def generate(
        self,
        script: str,
        avatar_config: AvatarConfig,
        output_path: Path,
    ) -> AvatarResult:
        """
        生成数字人口播视频

        Args:
            script: 要朗读的文案
            avatar_config: 数字人配置
            output_path: 输出路径
        """

        # Step 1: 声音克隆 + TTS
        audio_result = await self.tts.voice_clone(
            reference_audio=avatar_config.reference_audio,
            text=script,
            output_path=output_path.with_suffix(".mp3"),
        )

        if not audio_result.success:
            return AvatarResult(success=False, error=audio_result.error)

        # Step 2: 生成口型动画（可选）
        # 使用 SadTalker / Wav2Lip 等技术

        # Step 3: 合成最终视频
        video_result = await self.video.synthesize(
            audio_path=audio_result.audio_path,
            avatar_image=avatar_config.avatar_image,
            output_path=output_path,
        )

        return AvatarResult(
            success=video_result.success,
            video_path=video_result.video_path,
            audio_path=audio_result.audio_path,
        )
```

---

### 4.6 HTML 视频模板系统 ⭐⭐

#### 目标
提供可定制的 HTML 视频模板，支持图片 + 音频 + 字幕组合。

#### 模板结构

```html
<!-- templates/1080x1920/image_default.html -->

<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        .video-container {
            width: 1080px;
            height: 1920px;
            position: relative;
            background: {{ background_color }};
            overflow: hidden;
        }

        .image-layer {
            position: absolute;
            width: 100%;
            height: 70%;
            top: 0;
            background-image: url('{{ image_url }}');
            background-size: cover;
            background-position: center;
        }

        .text-layer {
            position: absolute;
            bottom: 0;
            height: 30%;
            padding: 40px;
            background: linear-gradient(transparent, rgba(0,0,0,0.8));
            color: white;
            font-size: 36px;
            line-height: 1.6;
        }

        .subtitle {
            position: absolute;
            bottom: 100px;
            left: 0;
            right: 0;
            text-align: center;
            font-size: 42px;
            color: {{ accent_color }};
            text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
        }
    </style>
</head>
<body>
    <div class="video-container">
        <div class="image-layer"></div>
        <div class="text-layer">
            {{ content }}
        </div>
        <div class="subtitle">{{ subtitle }}</div>
    </div>
</body>
</html>
```

#### FFmpeg 渲染

```python
# backend/app/services/video_pipeline/synthesizer.py

class FFmpegSynthesizer:
    """FFmpeg 视频合成器"""

    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg = ffmpeg_path

    async def render_template(
        self,
        template_path: Path,
        params: Dict[str, Any],
        output_path: Path,
    ) -> Path:
        """渲染 HTML 模板为图片"""

        # 使用 puppeteer/playwright 截图
        # 或使用 earthscreenshort 等工具

    async def synthesize(
        self,
        images: List[Path],
        audio_files: List[Path],
        bgm_path: Path,
        bgm_volume: float,
        template: str,
        output_path: Path,
    ) -> Path:
        """合成最终视频"""

        # 1. 渲染每个场景为图片
        scene_images = []
        for i, (img, audio) in enumerate(zip(images, audio_files)):
            audio_duration = self._get_duration(audio)

            rendered = await self.render_template(
                template,
                {
                    "image_url": img,
                    "content": f"Scene {i+1}",
                    "subtitle": f"场景 {i+1}",
                },
            )
            scene_images.append(rendered)

        # 2. 拼接视频片段
        temp_dir = output_path.parent / "temp"
        temp_dir.mkdir(exist_ok=True)

        segments = []
        for i, (img, audio) in enumerate(zip(scene_images, audio_files)):
            segment_path = temp_dir / f"segment_{i}.mp4"
            await self._create_segment(img, audio, segment_path)
            segments.append(segment_path)

        # 3. 合并片段
        concat_list = temp_dir / "concat.txt"
        with open(concat_list, "w") as f:
            for seg in segments:
                f.write(f"file '{seg}'\n")

        await self._run_ffmpeg(
            f"-f concat -safe 0 -i {concat_list} "
            f"-i {bgm_path} -filter_complex "
            f'"[1:a]volume={bgm_volume}[a]" '
            f"-map 0:v -map [a] -c:v libx264 -c:a aac {output_path}"
        )

        # 4. 清理临时文件
        shutil.rmtree(temp_dir, ignore_errors=True)

        return output_path
```

---

## 五、实施计划

### Phase 1: 基础能力（1-2 周）⭐⭐⭐

| 任务 | 工作量 | 说明 |
|------|--------|------|
| RunningHub Provider 实现 | 2-3 天 | 云端 GPU 支持 |
| 工作流自动发现 | 1-2 天 | 文件扫描 + 数据库同步 |
| 工作流热重载 | 1 天 | 运行时更新 |

### Phase 2: 视频生成（2 周）⭐⭐⭐

| 任务 | 工作量 | 说明 |
|------|--------|------|
| TTS Provider 抽象 | 1 天 | 基类 + Edge TTS |
| Edge TTS 实现 | 1 天 | 免费 TTS |
| 视频流水线框架 | 2 天 | 五步流程 |
| FFmpeg 合成器 | 2 天 | 模板渲染 + 合成 |
| HTML 模板系统 | 1-2 天 | 模板引擎 |

### Phase 3: 高级功能（2-3 周）⭐⭐

| 任务 | 工作量 | 说明 |
|------|--------|------|
| 声音克隆 | 3-4 天 | CosyVoice / XTTS |
| 数字人口播 | 3-4 天 | SadTalker / Wav2Lip |
| WAN 2.1 图生视频 | 2-3 天 | ComfyUI 工作流 |
| 动作迁移 | 4-5 天 | AnimateDiff / LoRA |

---

## 六、文件清单

```
backend/app/services/
├── comfyui/
│   ├── providers/              # 🆕 Provider 抽象
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── local.py
│   │   └── runninghub.py
│   ├── discovery.py            # 🆕 工作流自动发现
│   ├── scheduler.py            # 🆕 混合调度器
│   ├── service.py              # (已有)
│   ├── pool.py                 # (已有)
│   └── client.py               # (已有)
│
├── video_pipeline/             # 🆕 视频生成流水线
│   ├── __init__.py
│   ├── pipeline.py
│   ├── script.py
│   ├── image.py
│   ├── tts.py
│   ├── bgm.py
│   └── synthesizer.py
│
└── tts/                        # 🆕 TTS 服务
    ├── __init__.py
    ├── base.py
    ├── edge.py
    ├── index.py
    ├── chatts.py
    └── voice_clone.py

backend/workflows/               # 🆕 工作流文件目录
├── image/
├── video/
├── tts/
└── templates/

config/
└── providers.yaml              # (扩展)
```

---

## 七、配置示例

```yaml
# config/comfyui.yaml

comfyui:
  # 本地节点
  local:
    - name: "local-gpu-3090"
      url: "http://127.0.0.1:8188"
      capabilities: ["txt2img", "img2img", "video"]
      priority: 10
      max_queue_size: 10

  # RunningHub 云端
  runninghub:
    enabled: true
    api_key: "${RUNNINGHUB_API_KEY}"
    concurrent_limit: 1
    instance_type: "standard"  # standard (24GB) | plus (48GB)
    capabilities: ["txt2img", "img2img", "video", "wan21"]

  # 调度策略
  scheduler:
    prefer_local: true
    fallback_cloud: true
    health_check_interval: 60

  # 工作流目录
  workflow_dir: "workflows"
  auto_discovery: true
  hot_reload: true

# TTS 配置
tts:
  default_provider: "edge-tts"
  providers:
    edge-tts:
      enabled: true
    voice-clone:
      enabled: false
      model_path: "models/cosyvoice"

# 视频生成配置
video_pipeline:
  output_dir: "output/videos"
  default_template: "1080x1920/image_default.html"
  default_bgm: "bgm/default.mp3"
  default_fps: 30
```

---

*本文档记录 YLCraft ComfyUI 模块的演进规划，借鉴 Pixelle-Video 的优秀设计。*
