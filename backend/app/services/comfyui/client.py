"""
YLCraft — ComfyUI API 客户端

功能：
- 图像生成（文生图、图生图）
- 视频生成（图生视频）
- 工作流执行
- 任务状态轮询
- 模型管理
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

import httpx

logger = logging.getLogger("ylcraft.comfyui")


class ComfyUIClient:
    """
    ComfyUI API 客户端

    封装 ComfyUI Server 的所有 API 调用。
    支持同步和异步两种模式。
    """

    def __init__(self, server_url: str, workflow_dir: str = None):
        """
        初始化 ComfyUI 客户端

        Args:
            server_url: ComfyUI 服务地址（如 http://127.0.0.1:8188）
            workflow_dir: 工作流 JSON 文件目录
        """
        self.server_url = server_url.rstrip("/")
        self.workflow_dir = Path(workflow_dir) if workflow_dir else None
        self._client = httpx.AsyncClient(timeout=300.0)
        self._sync_client = None

    # =========================================================================
    # 系统信息
    # =========================================================================

    async def get_system_stats(self) -> Dict[str, Any]:
        """
        获取系统状态（显存、模型列表）

        Returns:
            {"system": {...}, "devices": [...]}
        """
        resp = await self._client.get(f"{self.server_url}/system_stats")
        resp.raise_for_status()
        return resp.json()

    async def get_models(self) -> Dict[str, Any]:
        """
        获取可用模型列表

        Returns:
            {"model_list": [{"name": "...", "filename": "..."}]}
        """
        resp = await self._client.get(f"{self.server_url}/api/model_list")
        resp.raise_for_status()
        return resp.json()

    async def get_embeddings(self) -> Dict[str, Any]:
        """获取可用 Embedding 列表"""
        resp = await self._client.get(f"{self.server_url}/api/embeddings")
        resp.raise_for_status()
        return resp.json()

    async def get_lora_models(self) -> Dict[str, Any]:
        """获取可用 LoRA 模型列表"""
        resp = await self._client.get(f"{self.server_url}/api/loras")
        resp.raise_for_status()
        return resp.json()

    async def get_controlnet_models(self) -> Dict[str, Any]:
        """获取可用 ControlNet 模型列表"""
        resp = await self._client.get(f"{self.server_url}/api/controlnet/models")
        resp.raise_for_status()
        return resp.json()

    # =========================================================================
    # 工作流执行
    # =========================================================================

    async def queue_prompt(self, workflow: Dict) -> Dict[str, Any]:
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

    async def get_history(self, prompt_id: str = None) -> Dict[str, Any]:
        """
        获取任务历史（含输出）

        Args:
            prompt_id: 任务 ID（可选，不传返回所有历史）

        Returns:
            历史记录字典，key 为 prompt_id
        """
        url = f"{self.server_url}/api/history"
        if prompt_id:
            url = f"{url}/{prompt_id}"
        resp = await self._client.get(url)
        resp.raise_for_status()
        return resp.json()

    async def get_progress(self) -> Dict[str, Any]:
        """
        获取当前执行进度

        Returns:
            {"progress": 0.5, "running": [...], "queued": [...]}
        """
        resp = await self._client.get(f"{self.server_url}/api/progress")
        resp.raise_for_status()
        return resp.json()

    async def get_queue(self) -> Dict[str, Any]:
        """
        获取队列状态

        Returns:
            {"queue_running": [...], "queue_pending": [...]}
        """
        resp = await self._client.get(f"{self.server_url}/api/queue")
        resp.raise_for_status()
        return resp.json()

    async def interrupt(self) -> None:
        """中断当前执行"""
        resp = await self._client.post(f"{self.server_url}/api/interrupt")
        resp.raise_for_status()

    async def delete_from_queue(self, prompt_id: str) -> None:
        """从队列中删除任务"""
        resp = await self._client.post(
            f"{self.server_url}/api/queue",
            json={"delete": [prompt_id]}
        )
        resp.raise_for_status()

    # =========================================================================
    # 轮询等待完成
    # =========================================================================

    async def poll_until_complete(
        self,
        prompt_id: str,
        poll_interval: float = 1.0,
        max_wait: float = 600.0,
        on_progress: callable = None,
    ) -> Dict[str, Any]:
        """
        轮询直到任务完成

        Args:
            prompt_id: 任务 ID
            poll_interval: 轮询间隔（秒）
            max_wait: 最大等待时间（秒）
            on_progress: 进度回调函数 (progress: float, elapsed: float) -> None

        Returns:
            完整的任务历史记录

        Raises:
            TimeoutError: 超时
            RuntimeError: 任务执行出错
        """
        start = time.perf_counter()
        elapsed = 0.0

        while elapsed < max_wait:
            history = await self.get_history(prompt_id)

            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                status = history[prompt_id].get("status", {})

                # 检查是否完成
                if status.get("completed", False):
                    logger.info(f"ComfyUI task {prompt_id} completed")
                    return history[prompt_id]

                # 检查是否出错
                if status.get("error"):
                    error_msg = status.get("error", "Unknown error")
                    logger.error(f"ComfyUI task {prompt_id} error: {error_msg}")
                    raise RuntimeError(f"ComfyUI task error: {error_msg}")

                # 获取进度
                if on_progress:
                    progress_data = await self.get_progress()
                    progress = progress_data.get("progress", 0.0)
                    on_progress(progress, elapsed)

            await asyncio.sleep(poll_interval)
            elapsed = time.perf_counter() - start

            if elapsed > 10:  # 每 10 秒打印一次日志
                logger.debug(f"Waiting for ComfyUI task {prompt_id}, {int(elapsed)}s elapsed")

        raise TimeoutError(f"ComfyUI task {prompt_id} timeout after {max_wait}s")

    async def execute_workflow(
        self,
        workflow: Dict,
        poll_interval: float = 1.0,
        max_wait: float = 600.0,
        on_progress: callable = None,
    ) -> Dict[str, Any]:
        """
        执行工作流并等待完成

        Args:
            workflow: 工作流配置
            poll_interval: 轮询间隔
            max_wait: 最大等待时间
            on_progress: 进度回调

        Returns:
            {"prompt_id": "...", "outputs": {...}}
        """
        # 1. 提交任务
        result = await self.queue_prompt(workflow)
        prompt_id = result["prompt_id"]
        logger.info(f"ComfyUI task submitted: {prompt_id}")

        # 2. 等待完成
        task_result = await self.poll_until_complete(
            prompt_id, poll_interval, max_wait, on_progress
        )

        # 3. 提取输出
        outputs = {}
        for node_id, node_data in task_result.get("outputs", {}).items():
            if "images" in node_data:
                outputs[node_id] = node_data["images"]
            elif "gifs" in node_data:
                outputs[node_id] = node_data["gifs"]
            elif "video" in node_data:
                outputs[node_id] = node_data["video"]

        return {
            "prompt_id": prompt_id,
            "outputs": outputs,
            "raw": task_result,
        }

    # =========================================================================
    # 文件上传与下载
    # =========================================================================

    async def upload_image(
        self,
        file_path: str,
        name: str = None,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """
        上传图片到 ComfyUI

        Args:
            file_path: 本地文件路径
            name: 上传后的文件名（默认使用原文件名）
            overwrite: 是否覆盖已存在的文件

        Returns:
            {"name": "...", "subfolder": "...", "type": "..."}
        """
        with open(file_path, "rb") as f:
            files = {"image": (name or Path(file_path).name, f.read())}
            data = {"overwrite": "true" if overwrite else "false"}

            resp = await self._client.post(
                f"{self.server_url}/upload/image",
                files=files,
                data=data,
            )
        resp.raise_for_status()
        return resp.json()

    async def upload_mask(self, file_path: str, name: str = None) -> Dict[str, Any]:
        """上传蒙版图片"""
        with open(file_path, "rb") as f:
            files = {"mask": (name or Path(file_path).name, f.read())}
            resp = await self._client.post(
                f"{self.server_url}/upload/mask",
                files=files,
            )
        resp.raise_for_status()
        return resp.json()

    def get_image_url(self, filename: str, subfolder: str = "", type: str = "output") -> str:
        """
        获取图片访问 URL

        Args:
            filename: 文件名
            subfolder: 子目录
            type: 文件类型（input/output/temp）

        Returns:
            完整的图片 URL
        """
        from urllib.parse import quote
        params = f"filename={quote(filename)}&subfolder={quote(subfolder)}&type={type}"
        return f"{self.server_url}/view?{params}"

    def get_video_url(self, filename: str, subfolder: str = "", type: str = "output") -> str:
        """获取视频访问 URL"""
        return self.get_image_url(filename, subfolder, type)

    # =========================================================================
    # 工作流文件管理
    # =========================================================================

    def load_workflow(self, name: str) -> Dict:
        """
        从文件加载工作流 JSON

        Args:
            name: 工作流名称（不含 .json 后缀）

        Returns:
            工作流节点配置字典

        Raises:
            ValueError: workflow_dir 未配置
            FileNotFoundError: 工作流文件不存在
        """
        if not self.workflow_dir:
            raise ValueError("workflow_dir not configured")

        path = self.workflow_dir / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Workflow not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_workflow(self, name: str, workflow: Dict) -> None:
        """
        保存工作流到文件

        Args:
            name: 工作流名称（不含 .json 后缀）
            workflow: 工作流节点配置
        """
        if not self.workflow_dir:
            raise ValueError("workflow_dir not configured")

        self.workflow_dir.mkdir(parents=True, exist_ok=True)
        path = self.workflow_dir / f"{name}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(workflow, f, indent=2, ensure_ascii=False)
        logger.info(f"Workflow saved: {path}")

    # =========================================================================
    # 工作流参数替换工具
    # =========================================================================

    @staticmethod
    def set_node_input(workflow: Dict, node_id: str, input_name: str, value: Any) -> None:
        """
        设置工作流节点的输入参数

        Args:
            workflow: 工作流配置
            node_id: 节点 ID（字符串）
            input_name: 输入参数名
            value: 参数值
        """
        if node_id not in workflow:
            raise ValueError(f"Node {node_id} not found in workflow")
        workflow[node_id]["inputs"][input_name] = value

    @staticmethod
    def get_node_input(workflow: Dict, node_id: str, input_name: str) -> Any:
        """
        获取工作流节点的输入参数

        Args:
            workflow: 工作流配置
            node_id: 节点 ID
            input_name: 输入参数名

        Returns:
            参数值
        """
        if node_id not in workflow:
            raise ValueError(f"Node {node_id} not found in workflow")
        return workflow[node_id]["inputs"].get(input_name)

    # =========================================================================
    # 清理
    # =========================================================================

    async def close(self):
        """关闭客户端"""
        await self._client.aclose()
        if self._sync_client:
            self._sync_client.close()

    # =========================================================================
    # 上下文管理器支持
    # =========================================================================

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
