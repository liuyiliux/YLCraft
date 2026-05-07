"""
YLCraft — ComfyUI 连接池与调度器

提供：
- ComfyUIPool: 多节点连接池管理
- ComfyUIScheduler: 任务调度器
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.services.comfyui import ComfyUIClient
from app.services.comfyui.service import NodeService, TaskService, WorkflowService

logger = logging.getLogger("ylcraft.comfyui.pool")


@dataclass
class NodeConnection:
    """节点连接"""
    node_id: str
    name: str
    server_url: str
    client: ComfyUIClient
    capabilities: List[str]
    max_resolution: int
    priority: int
    current_load: int = 0
    max_queue_size: int = 10
    is_healthy: bool = True
    last_error: str = ""
    last_heartbeat: datetime = field(default_factory=datetime.now)

    def can_accept_task(self) -> bool:
        """是否可以接受新任务"""
        return self.is_healthy and self.current_load < self.max_queue_size

    def load_factor(self) -> float:
        """负载因子（0.0 - 1.0）"""
        if self.max_queue_size == 0:
            return 1.0
        return self.current_load / self.max_queue_size


class ComfyUIPool:
    """
    ComfyUI 连接池

    管理多个 ComfyUI 节点的连接，支持：
    - 负载均衡（最小负载优先）
    - 故障转移（自动跳过不健康节点）
    - 健康检查（心跳检测）
    - 动态扩缩容
    """

    def __init__(self):
        self._nodes: Dict[str, NodeConnection] = {}
        self._lock = asyncio.Lock()
        self._health_check_task: Optional[asyncio.Task] = None

    # =========================================================================
    # 节点管理
    # =========================================================================

    async def add_node(
        self,
        node_id: str,
        server_url: str,
        name: str = "",
        capabilities: List[str] = None,
        max_resolution: int = 2048,
        priority: int = 0,
        max_queue_size: int = 10,
    ) -> NodeConnection:
        """添加节点到连接池"""
        async with self._lock:
            if node_id in self._nodes:
                logger.warning(f"Node {node_id} already exists, updating...")

            client = ComfyUIClient(server_url=server_url)
            node = NodeConnection(
                node_id=node_id,
                name=name or f"node_{node_id[:8]}",
                server_url=server_url,
                client=client,
                capabilities=capabilities or ["txt2img"],
                max_resolution=max_resolution,
                priority=priority,
                max_queue_size=max_queue_size,
            )
            self._nodes[node_id] = node
            logger.info(f"Added node {node.name} ({server_url}) to pool")
            return node

    async def remove_node(self, node_id: str) -> bool:
        """从连接池移除节点"""
        async with self._lock:
            if node_id not in self._nodes:
                return False
            node = self._nodes[node_id]
            await node.client.close()
            del self._nodes[node_id]
            logger.info(f"Removed node {node.name} from pool")
            return True

    async def get_node(self, node_id: str) -> Optional[NodeConnection]:
        """获取指定节点"""
        async with self._lock:
            return self._nodes.get(node_id)

    async def list_nodes(self) -> List[NodeConnection]:
        """列出所有节点"""
        async with self._lock:
            return list(self._nodes.values())

    async def sync_from_db(self):
        """从数据库同步节点列表"""
        nodes = await NodeService.list_nodes(is_active=None)
        async with self._lock:
            # 添加或更新节点
            for db_node in nodes:
                if db_node.id in self._nodes:
                    # 更新现有节点
                    self._nodes[db_node.id].max_queue_size = db_node.max_queue_size
                    self._nodes[db_node.id].priority = db_node.priority
                    self._nodes[db_node.id].capabilities = db_node.get_capabilities()
                else:
                    # 添加新节点
                    client = ComfyUIClient(server_url=db_node.server_url)
                    self._nodes[db_node.id] = NodeConnection(
                        node_id=db_node.id,
                        name=db_node.display_name,
                        server_url=db_node.server_url,
                        client=client,
                        capabilities=db_node.get_capabilities(),
                        max_resolution=db_node.max_resolution,
                        priority=db_node.priority,
                        max_queue_size=db_node.max_queue_size,
                    )
                    logger.info(f"Synced node {db_node.name} from database")

            # 移除数据库中已删除的节点
            db_node_ids = {n.id for n in nodes}
            for node_id in list(self._nodes.keys()):
                if node_id not in db_node_ids:
                    await self._nodes[node_id].client.close()
                    del self._nodes[node_id]

    # =========================================================================
    # 负载均衡
    # =========================================================================

    async def select_node(
        self,
        capability: str = "txt2img",
        prefer_high_priority: bool = True,
    ) -> Optional[NodeConnection]:
        """
        选择最佳节点（负载均衡）

        选择策略：
        1. 过滤出支持所需能力的节点
        2. 排除不健康的节点
        3. 优先选择高优先级节点
        4. 在同级优先级中选择负载最低的节点
        """
        async with self._lock:
            candidates = [
                n for n in self._nodes.values()
                if n.can_accept_task() and capability in n.capabilities
            ]

            if not candidates:
                # 放宽条件，允许轻微过载
                candidates = [
                    n for n in self._nodes.values()
                    if n.is_healthy and capability in n.capabilities
                ]

            if not candidates:
                return None

            if prefer_high_priority:
                # 按优先级分组
                max_priority = max(n.priority for n in candidates)
                candidates = [n for n in candidates if n.priority == max_priority]

            # 选择负载最低的
            candidates.sort(key=lambda n: n.load_factor())
            return candidates[0]

    async def increment_load(self, node_id: str):
        """增加节点负载"""
        async with self._lock:
            if node_id in self._nodes:
                self._nodes[node_id].current_load += 1
                # 更新数据库
                asyncio.create_task(NodeService.update_load(node_id, 1))

    async def decrement_load(self, node_id: str):
        """减少节点负载"""
        async with self._lock:
            if node_id in self._nodes:
                self._nodes[node_id].current_load = max(0, self._nodes[node_id].current_load - 1)
                asyncio.create_task(NodeService.update_load(node_id, -1))

    # =========================================================================
    # 健康检查
    # =========================================================================

    async def check_node_health(self, node_id: str) -> bool:
        """检查节点健康状态"""
        node = await self.get_node(node_id)
        if not node:
            return False

        try:
            stats = await node.client.get_system_stats()
            node.is_healthy = True
            node.last_error = ""
            node.last_heartbeat = datetime.now()
            await NodeService.heartbeat(node_id)
            return True
        except Exception as e:
            node.is_healthy = False
            node.last_error = str(e)
            logger.warning(f"Node {node.name} health check failed: {e}")
            return False

    async def start_health_check(self, interval: int = 60):
        """启动健康检查任务"""
        if self._health_check_task and not self._health_check_task.done():
            logger.warning("Health check already running")
            return

        async def _health_check_loop():
            while True:
                try:
                    for node_id in list(self._nodes.keys()):
                        await self.check_node_health(node_id)
                        await asyncio.sleep(1)  # 避免同时检查
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Health check error: {e}")
                await asyncio.sleep(interval)

        self._health_check_task = asyncio.create_task(_health_check_loop())
        logger.info("Started health check task")

    async def stop_health_check(self):
        """停止健康检查"""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
            logger.info("Stopped health check task")

    # =========================================================================
    # 统计信息
    # =========================================================================

    async def get_stats(self) -> Dict[str, Any]:
        """获取连接池统计"""
        async with self._lock:
            nodes = list(self._nodes.values())
            total_load = sum(n.current_load for n in nodes)
            healthy_count = sum(1 for n in nodes if n.is_healthy)
            return {
                "total_nodes": len(nodes),
                "healthy_nodes": healthy_count,
                "unhealthy_nodes": len(nodes) - healthy_count,
                "total_load": total_load,
                "nodes": [
                    {
                        "id": n.node_id,
                        "name": n.name,
                        "url": n.server_url,
                        "load": n.current_load,
                        "max_load": n.max_queue_size,
                        "healthy": n.is_healthy,
                        "priority": n.priority,
                        "capabilities": n.capabilities,
                    }
                    for n in nodes
                ],
            }


# 全局连接池实例
_pool: Optional[ComfyUIPool] = None


def get_pool() -> ComfyUIPool:
    """获取全局连接池"""
    global _pool
    if _pool is None:
        _pool = ComfyUIPool()
    return _pool


# =============================================================================
# ComfyUIScheduler: 任务调度器
# =============================================================================

class ComfyUIScheduler:
    """
    ComfyUI 任务调度器

    功能：
    - 接收任务请求
    - 选择最优节点执行
    - 跟踪任务状态
    - 自动重试失败任务
    """

    def __init__(self, pool: ComfyUIPool = None):
        self._pool = pool or get_pool()
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def submit_task(
        self,
        prompt_id: str,
        workflow: Dict[str, Any],
        params: Dict[str, Any] = None,
        template_id: str = None,
        on_progress: Callable = None,
        on_complete: Callable = None,
    ) -> Tuple[bool, str]:
        """
        提交任务到调度器

        Args:
            prompt_id: 任务 ID
            workflow: 工作流配置
            params: 生成参数
            template_id: 模板 ID（可选）
            on_progress: 进度回调
            on_complete: 完成回调

        Returns:
            (success, message)
        """
        # 选择节点
        capability = params.get("capability", "txt2img") if params else "txt2img"
        node = await self._pool.select_node(capability=capability)

        if not node:
            return False, "No available node"

        # 创建任务记录
        task_record = await TaskService.create_task(
            prompt_id=prompt_id,
            task_type=params.get("task_type", "txt2img") if params else "txt2img",
            prompt=params.get("prompt", "") if params else "",
            negative_prompt=params.get("negative_prompt", "") if params else "",
            params=params or {},
            template_id=template_id,
        )

        # 增加节点负载
        await self._pool.increment_load(node.node_id)

        # 启动后台执行
        task = asyncio.create_task(
            self._execute_task(
                prompt_id=prompt_id,
                node=node,
                workflow=workflow,
                params=params,
                on_progress=on_progress,
                on_complete=on_complete,
            )
        )

        async with self._lock:
            self._running_tasks[prompt_id] = task

        return True, f"Task submitted to {node.name}"

    async def _execute_task(
        self,
        prompt_id: str,
        node: NodeConnection,
        workflow: Dict[str, Any],
        params: Dict[str, Any] = None,
        on_progress: Callable = None,
        on_complete: Callable = None,
    ):
        """执行任务（后台运行）"""
        start_time = time.perf_counter()
        success = False
        error_msg = ""

        try:
            # 标记为已入队
            await TaskService.mark_queued(prompt_id, node.server_url)

            # 定义进度回调
            async def progress_callback(progress: float, elapsed: float):
                step = int(progress * (params.get("steps", 20) if params else 20))
                total = params.get("steps", 20) if params else 20
                await TaskService.update_progress(prompt_id, progress, step, total)
                if on_progress:
                    on_progress(progress, step, total)
                # 广播 WebSocket
                await broadcast_progress(prompt_id, progress, step, total)

            # 执行工作流
            result = await node.client.execute_workflow(
                workflow=workflow,
                poll_interval=2.0,
                max_wait=600.0,
                on_progress=progress_callback,
            )

            # 提取输出
            outputs = result.get("outputs", {})
            output_images = []

            for node_id, images in outputs.items():
                if isinstance(images, list):
                    for img in images:
                        if isinstance(img, dict) and "filename" in img:
                            url = node.client.get_image_url(
                                filename=img["filename"],
                                subfolder=img.get("subfolder", ""),
                                type=img.get("type", "output"),
                            )
                            output_images.append({"url": url, **img})

            # 标记完成
            await TaskService.mark_completed(prompt_id, output_images)
            success = True

            if on_complete:
                on_complete(success=True, outputs=output_images)

            # 广播完成
            await broadcast_complete(prompt_id, "success", output_images)

        except asyncio.CancelledError:
            error_msg = "Task cancelled"
            await TaskService.mark_cancelled(prompt_id)
            if on_complete:
                on_complete(success=False, error=error_msg)
            await broadcast_complete(prompt_id, "cancelled", error=error_msg)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Task {prompt_id} failed: {e}")
            await TaskService.mark_failed(prompt_id, error_msg)
            if on_complete:
                on_complete(success=False, error=error_msg)
            await broadcast_complete(prompt_id, "error", error=error_msg)

        finally:
            # 减少节点负载
            await self._pool.decrement_load(node.node_id)
            # 更新节点统计
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            asyncio.create_task(NodeService.update_stats(node.node_id, success, latency_ms))
            # 清理运行任务
            async with self._lock:
                self._running_tasks.pop(prompt_id, None)

    async def cancel_task(self, prompt_id: str) -> bool:
        """取消任务"""
        async with self._lock:
            if prompt_id in self._running_tasks:
                self._running_tasks[prompt_id].cancel()
                return True
        return False

    async def get_running_tasks(self) -> List[str]:
        """获取运行中的任务"""
        async with self._lock:
            return list(self._running_tasks.keys())


# 导入广播函数
from app.core.ws_broadcast import broadcast_progress, broadcast_complete
