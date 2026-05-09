"""
YLCraft — ComfyUI 图像生成 Backend

支持：
- 文生图 (txt2img)
- 图生图 (img2img)
- ControlNet 控制
- LoRA 微调
"""

from __future__ import annotations

import json
import logging
import time
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.contracts.types import ImageGenerationRequest, ImageGenerationResult, ImageCapability
from app.services.image.base import BaseImageBackend

logger = logging.getLogger("ylcraft.comfyui.image")


@dataclass
class ComfyUIImageConfig:
    """ComfyUI 图像配置"""
    server_url: str = "http://127.0.0.1:8188"
    workflow_dir: str = "backend/app/services/comfyui/workflows"
    output_dir: str = "storage/comfyui/outputs"
    timeout: int = 300
    default_workflow: str = "txt2img"
    default_model: str = "sd15"
    # 能力开关（ComfyUI 理论上支持所有功能，可按需禁用）
    support_img2img: bool = True  # 图生图
    support_style_control: bool = True  # 风格控制


@dataclass
class ComfyUIImageCapabilities:
    """ComfyUI 图像能力详情"""
    max_resolution: int = 2048
    supports_controlnet: bool = True
    supports_lora: bool = True
    supports_img2img: bool = True
    supports_upscale: bool = True
    supported_models: List[str] = field(default_factory=lambda: ["sd15", "sdxl", "flux"])


class ComfyUIImageBackend(BaseImageBackend):
    """
    ComfyUI 图像生成后端

    使用方法：
    ```python
    config = ComfyUIImageConfig(server_url="http://127.0.0.1:8188")
    backend = ComfyUIImageBackend(config)

    result = await backend.generate(ImageGenerationRequest(
        prompt="a beautiful landscape",
        negative_prompt="ugly, blurry",
        size="512x512",
    ))
    ```
    """

    PROVIDER_ID = "comfyui"
    PROVIDER_NAME = "ComfyUI"

    # 工作流模板中的节点 ID（需根据实际工作流调整）
    NODE_IDS = {
        # 文生图工作流节点
        "text_encoder": "3",      # CLIP Text Encode (prompt)
        "negative_encoder": "7", # CLIP Text Encode (negative)
        "checkpoint_loader": "4", # Checkpoint Loader
        "sampler": "5",           # KSampler
        "latent_image": "6",      # Empty Latent Image
        "vae_decode": "8",        # VAE Decode
        "save_image": "9",        # Save Image
        # LoRA 节点
        "lora_loader": "10",      # LoraLoader
        # 图生图工作流节点
        "load_image": "9",        # Load Image
        "vae_encode": "10",       # VAE Encode
    }

    def __init__(self, config: ComfyUIImageConfig = None):
        """
        初始化 ComfyUI 图像后端

        Args:
            config: 配置对象
        """
        self._config = config or ComfyUIImageConfig()
        self._client = None
        self._capabilities = set()
        self._image_capabilities = ComfyUIImageCapabilities()

    # =========================================================================
    # 属性
    # =========================================================================

    @property
    def name(self) -> str:
        return f"comfyui-{self._config.default_model}"

    @property
    def model(self) -> str:
        return self._config.default_model

    @property
    def capabilities(self) -> set:
        caps = {ImageCapability.TEXT_TO_IMAGE}
        if self._config.support_img2img:
            caps.add(ImageCapability.IMAGE_TO_IMAGE)
        if self._config.support_style_control:
            caps.add(ImageCapability.STYLE_CONTROL)
        return caps

    @property
    def image_capabilities(self) -> ComfyUIImageCapabilities:
        return self._image_capabilities

    # =========================================================================
    # 生命周期
    # =========================================================================

    async def initialize(self) -> bool:
        """
        初始化 ComfyUI 客户端并测试连接

        Returns:
            True if 连接成功
        """
        try:
            from .client import ComfyUIClient
            self._client = ComfyUIClient(
                server_url=self._config.server_url,
                workflow_dir=self._config.workflow_dir,
            )

            # 测试连接
            stats = await self._client.get_system_stats()
            devices = stats.get("devices", [])
            logger.info(f"ComfyUI connected: {len(devices)} device(s)")

            # 确保输出目录存在
            os.makedirs(self._config.output_dir, exist_ok=True)

            return True
        except Exception as e:
            logger.error(f"ComfyUI init failed: {e}")
            return False

    async def close(self):
        """关闭客户端"""
        if self._client:
            await self._client.close()

    async def health_check(self) -> bool:
        """健康检查"""
        if not self._client:
            return False
        try:
            await self._client.get_system_stats()
            return True
        except Exception:
            return False

    # =========================================================================
    # 生成接口
    # =========================================================================

    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        """
        生成图像

        Args:
            req: 图像生成请求

        Returns:
            图像生成结果
        """
        from app.core.contracts.types import ImageGenerationResult

        start = time.perf_counter()
        prompt_id = req.prompt_id or f"comfyui_{int(start * 1000)}"

        try:
            # 1. 确定工作流类型
            workflow_name = self._config.default_workflow
            if req.source_image:  # 图生图
                workflow_name = "img2img"

            # 2. 加载工作流
            workflow = self._client.load_workflow(workflow_name)
            logger.info(f"Loaded workflow: {workflow_name}")

            # 3. 替换参数
            await self._apply_parameters(workflow, req)

            # 4. 如果有源图片，先上传
            if req.source_image:
                upload_result = await self._client.upload_image(req.source_image)
                logger.info(f"Image uploaded: {upload_result}")

            # 5. 执行工作流（后台执行，不阻塞）
            # 先提交任务获取 prompt_id
            queue_result = await self._client.queue_prompt(workflow)
            submitted_prompt_id = queue_result.get("prompt_id", prompt_id)

            # 启动后台任务处理
            async def process_task():
                try:
                    # 广播进度
                    from app.core.ws_broadcast import broadcast_progress, broadcast_complete

                    on_progress = lambda p, e: asyncio.create_task(
                        broadcast_progress(submitted_prompt_id, p)
                    )

                    result = await self._client.poll_until_complete(
                        submitted_prompt_id,
                        poll_interval=2.0,
                        max_wait=self._config.timeout,
                        on_progress=on_progress,
                    )

                    # 提取输出图片
                    images = self._extract_images(result)

                    if images:
                        local_paths = []
                        urls = []
                        for img_info in images:
                            local_path = await self._download_output(img_info)
                            local_paths.append(local_path)
                            urls.append(self._client.get_image_url(
                                filename=img_info["filename"],
                                subfolder=img_info.get("subfolder", ""),
                                type=img_info.get("type", "output"),
                            ))

                        await broadcast_complete(
                            submitted_prompt_id,
                            status="success",
                            outputs=[{"url": urls[0], "local_path": local_paths[0]}],
                        )
                    else:
                        await broadcast_complete(
                            submitted_prompt_id,
                            status="error",
                            error="No output images found",
                        )
                except Exception as e:
                    logger.error(f"Background task error: {e}")
                    await broadcast_complete(submitted_prompt_id, status="error", error=str(e))

            # 启动后台处理
            asyncio.create_task(process_task())

            # 立即返回（异步模式）
            return ImageGenerationResult(
                success=True,
                prompt_id=submitted_prompt_id,
                task_id=submitted_prompt_id,
                status="processing",
                progress=0.0,
                latency_ms=(time.perf_counter() - start) * 1000,
            )

        except Exception as e:
            logger.error(f"ComfyUI image generation failed: {e}", exc_info=True)
            return ImageGenerationResult(
                success=False,
                error=str(e),
                latency_ms=(time.perf_counter() - start) * 1000,
            )

    # =========================================================================
    # 内部方法
    # =========================================================================

    async def _apply_parameters(self, workflow: Dict, req: ImageGenerationRequest) -> None:
        """
        将请求参数应用到工作流节点

        Args:
            workflow: 工作流配置（会被修改）
            req: 生成请求
        """
        # 提取尺寸
        width, height = 512, 512
        if req.size:
            try:
                width, height = map(int, req.size.replace("*", "x").split("x"))
            except:
                pass

        # 文生图参数
        if "text_encoder" in self.NODE_IDS:
            self._client.__class__.set_node_input(
                workflow, self.NODE_IDS["text_encoder"], "text", req.prompt
            )

        if "negative_encoder" in self.NODE_IDS and req.negative_prompt:
            self._client.__class__.set_node_input(
                workflow, self.NODE_IDS["negative_encoder"], "text", req.negative_prompt
            )

        # 采样器参数
        if "sampler" in self.NODE_IDS:
            if req.seed is not None:
                self._client.__class__.set_node_input(
                    workflow, self.NODE_IDS["sampler"], "seed", req.seed
                )
            if req.steps:
                self._client.__class__.set_node_input(
                    workflow, self.NODE_IDS["sampler"], "steps", req.steps
                )
            if req.cfg_scale:
                self._client.__class__.set_node_input(
                    workflow, self.NODE_IDS["sampler"], "cfg", req.cfg_scale
                )
            # 采样器名称
            if req.sampler:
                self._client.__class__.set_node_input(
                    workflow, self.NODE_IDS["sampler"], "sampler_name", req.sampler
                )

        # 潜空间尺寸
        if "latent_image" in self.NODE_IDS:
            self._client.__class__.set_node_input(
                workflow, self.NODE_IDS["latent_image"], "width", width
            )
            self._client.__class__.set_node_input(
                workflow, self.NODE_IDS["latent_image"], "height", height
            )
            if req.batch_size and req.batch_size > 1:
                self._client.__class__.set_node_input(
                    workflow, self.NODE_IDS["latent_image"], "batch_size", req.batch_size
                )

        # LoRA（如果工作流支持）
        if req.lora and "lora_loader" in self.NODE_IDS:
            self._client.__class__.set_node_input(
                workflow, self.NODE_IDS["lora_loader"], "lora_name", req.lora
            )

        # ControlNet（如果工作流支持）
        if req.controlnet and "controlnet_loader" in self.NODE_IDS:
            self._client.__class__.set_node_input(
                workflow, self.NODE_IDS["controlnet_loader"], "controlnet_name", req.controlnet
            )

        logger.debug(f"Applied parameters: size={width}x{height}, prompt={req.prompt[:50]}...")

    def _extract_images(self, result: Dict) -> List[Dict]:
        """
        从执行结果中提取输出图片信息

        Args:
            result: execute_workflow 的返回值

        Returns:
            图片信息列表 [{"filename": "...", "subfolder": "...", "type": "..."}]
        """
        outputs = result.get("outputs", {})
        images = []

        for node_id, node_output in outputs.items():
            if isinstance(node_output, list):
                for item in node_output:
                    if isinstance(item, dict) and "filename" in item:
                        images.append(item)

        return images

    async def _download_output(self, img_info: Dict) -> str:
        """
        将 ComfyUI 输出下载到本地

        Args:
            img_info: 图片信息字典

        Returns:
            本地文件路径
        """
        filename = img_info["filename"]
        subfolder = img_info.get("subfolder", "")
        file_type = img_info.get("type", "output")

        # 构建本地路径
        local_filename = f"comfyui_{int(time.time())}_{filename}"
        local_path = os.path.join(self._config.output_dir, local_filename)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        # 下载
        url = self._client.get_image_url(filename, subfolder, file_type)
        async with self._client._client.stream("GET", url) as response:
            response.raise_for_status()
            with open(local_path, "wb") as f:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)

        logger.info(f"Downloaded: {url} -> {local_path}")
        return local_path

    # =========================================================================
    # 模型管理
    # =========================================================================

    async def get_available_models(self) -> List[str]:
        """获取可用的模型列表"""
        try:
            models_data = await self._client.get_models()
            return [m["filename"] for m in models_data.get("model_list", [])]
        except Exception as e:
            logger.error(f"Failed to get models: {e}")
            return []

    async def get_available_loras(self) -> List[str]:
        """获取可用的 LoRA 列表"""
        try:
            loras_data = await self._client.get_lora_models()
            return [m["filename"] for m in loras_data.get("lora_list", [])]
        except Exception as e:
            logger.error(f"Failed to get LoRAs: {e}")
            return []

    async def get_available_controlnets(self) -> List[str]:
        """获取可用的 ControlNet 列表"""
        try:
            cn_data = await self._client.get_controlnet_models()
            return [m["filename"] for m in cn_data.get("control_net_list", [])]
        except Exception as e:
            logger.error(f"Failed to get ControlNets: {e}")
            return []
