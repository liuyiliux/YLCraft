"""
YLCraft — ComfyUI 服务层

提供：
- WorkflowService: 工作流模板管理
- TaskService: 任务持久化
- NodeService: 节点连接池管理
- Scheduler: 任务调度器
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlmodel import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import AsyncSessionLocal
from app.db.models.comfyui import (
    WorkflowTemplate, WorkflowPreset, ComfyUITask, ComfyUINode,
    WorkflowCategory, TaskStatus, TaskPriority,
)

logger = logging.getLogger("ylcraft.comfyui.service")


# =============================================================================
# WorkflowService: 工作流模板管理
# =============================================================================

class WorkflowService:
    """工作流模板服务"""

    @staticmethod
    async def create_template(
        name: str,
        display_name: str,
        workflow_json: Dict[str, Any],
        category: WorkflowCategory = WorkflowCategory.TEXT_TO_IMAGE,
        description: str = "",
        tags: List[str] = None,
        node_mapping: Dict[str, str] = None,
    ) -> WorkflowTemplate:
        """创建工作流模板"""
        async with AsyncSessionLocal() as session:
            template = WorkflowTemplate(
                name=name,
                display_name=display_name or name,
                description=description,
                category=category,
                workflow_json=json.dumps(workflow_json, ensure_ascii=False, indent=2),
                node_mapping=json.dumps(node_mapping or {}, ensure_ascii=False),
                tags=json.dumps(tags or [], ensure_ascii=False),
            )
            session.add(template)
            await session.commit()
            await session.refresh(template)
            return template

    @staticmethod
    async def get_template(template_id: str) -> Optional[WorkflowTemplate]:
        """获取模板"""
        async with AsyncSessionLocal() as session:
            result = await session.get(WorkflowTemplate, template_id)
            if result:
                # detach from session
                await session.detach(result)
            return result

    @staticmethod
    async def get_template_by_name(name: str) -> Optional[WorkflowTemplate]:
        """通过名称获取模板"""
        async with AsyncSessionLocal() as session:
            result = await session.exec(
                select(WorkflowTemplate).where(WorkflowTemplate.name == name)
            )
            template = result.first()
            if template:
                await session.detach(template)
            return template

    @staticmethod
    async def list_templates(
        category: WorkflowCategory = None,
        is_active: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[WorkflowTemplate], int]:
        """列出模板"""
        async with AsyncSessionLocal() as session:
            query = select(WorkflowTemplate)
            count_query = select(func.count(WorkflowTemplate.id))

            if category:
                query = query.where(WorkflowTemplate.category == category)
                count_query = count_query.where(WorkflowTemplate.category == category)
            if is_active is not None:
                query = query.where(WorkflowTemplate.is_active == is_active)
                count_query = count_query.where(WorkflowTemplate.is_active == is_active)

            query = query.order_by(WorkflowTemplate.use_count.desc(), WorkflowTemplate.updated_at.desc())
            query = query.offset(offset).limit(limit)

            result = await session.execute(query).scalars()
            templates = result.all()

            count_result = await session.execute(count_query).scalars()
            total = count_result.one()

            # detach
            for t in templates:
                await session.detach(t)

            return list(templates), total

    @staticmethod
    async def update_template(
        template_id: str,
        **kwargs,
    ) -> Optional[WorkflowTemplate]:
        """更新模板"""
        async with AsyncSessionLocal() as session:
            template = await session.get(WorkflowTemplate, template_id)
            if not template:
                return None

            for key, value in kwargs.items():
                if hasattr(template, key):
                    if key == "workflow_json" and isinstance(value, dict):
                        value = json.dumps(value, ensure_ascii=False, indent=2)
                    elif key in ("node_mapping", "tags") and isinstance(value, (dict, list)):
                        value = json.dumps(value, ensure_ascii=False)
                    setattr(template, key, value)

            template.updated_at = datetime.now()
            template.workflow_version += 1

            await session.commit()
            await session.refresh(template)
            await session.detach(template)
            return template

    @staticmethod
    async def delete_template(template_id: str) -> bool:
        """删除模板"""
        async with AsyncSessionLocal() as session:
            template = await session.get(WorkflowTemplate, template_id)
            if not template:
                return False
            await session.delete(template)
            await session.commit()
            return True

    @staticmethod
    async def increment_use_count(template_id: str):
        """增加使用次数"""
        async with AsyncSessionLocal() as session:
            template = await session.get(WorkflowTemplate, template_id)
            if template:
                template.use_count += 1
                await session.commit()

    @staticmethod
    async def import_from_file(workflow_dir: str) -> int:
        """从文件导入工作流模板"""
        import_count = 0
        workflow_path = Path(workflow_dir)

        if not workflow_path.exists():
            logger.warning(f"Workflow dir not found: {workflow_dir}")
            return 0

        for f in workflow_path.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    workflow = json.load(fp)

                name = f.stem
                category = WorkflowCategory.CUSTOM

                # 尝试根据文件名推断分类
                if "txt2img" in name.lower() or "t2i" in name.lower():
                    category = WorkflowCategory.TEXT_TO_IMAGE
                elif "img2img" in name.lower() or "i2i" in name.lower():
                    category = WorkflowCategory.IMAGE_TO_IMAGE
                elif "upscale" in name.lower():
                    category = WorkflowCategory.UPSCALE
                elif "controlnet" in name.lower():
                    category = WorkflowCategory.CONTROLNET
                elif "video" in name.lower():
                    category = WorkflowCategory.VIDEO

                # 检查是否已存在
                existing = await WorkflowService.get_template_by_name(name)
                if existing:
                    # 更新
                    await WorkflowService.update_template(
                        existing.id,
                        workflow_json=workflow,
                    )
                else:
                    # 创建
                    await WorkflowService.create_template(
                        name=name,
                        display_name=name.replace("_", " ").title(),
                        workflow_json=workflow,
                        category=category,
                    )
                import_count += 1
                logger.info(f"Imported workflow: {name}")

            except Exception as e:
                logger.error(f"Failed to import {f.name}: {e}")

        return import_count


# =============================================================================
# PresetService: 预设管理
# =============================================================================

class PresetService:
    """工作流预设服务"""

    @staticmethod
    async def create_preset(
        name: str,
        template_id: str,
        params: Dict[str, Any],
        display_name: str = "",
        description: str = "",
        use_case: str = "general",
        is_default: bool = False,
    ) -> WorkflowPreset:
        """创建预设"""
        async with AsyncSessionLocal() as session:
            preset = WorkflowPreset(
                name=name,
                display_name=display_name or name,
                template_id=template_id,
                params_json=json.dumps(params, ensure_ascii=False),
                description=description,
                use_case=use_case,
                is_default=is_default,
            )
            session.add(preset)
            await session.commit()
            await session.refresh(preset)
            await session.detach(preset)
            return preset

    @staticmethod
    async def get_preset(preset_id: str) -> Optional[WorkflowPreset]:
        """获取预设"""
        async with AsyncSessionLocal() as session:
            result = await session.get(WorkflowPreset, preset_id)
            if result:
                await session.detach(result)
            return result

    @staticmethod
    async def list_presets(
        template_id: str = None,
        use_case: str = None,
        limit: int = 50,
    ) -> List[WorkflowPreset]:
        """列出预设"""
        async with AsyncSessionLocal() as session:
            query = select(WorkflowPreset)

            if template_id:
                query = query.where(WorkflowPreset.template_id == template_id)
            if use_case:
                query = query.where(WorkflowPreset.use_case == use_case)

            query = query.order_by(WorkflowPreset.use_count.desc())

            result = await session.execute(query).scalars()
            presets = result.all()

            for p in presets:
                await session.detach(p)

            return list(presets)

    @staticmethod
    async def delete_preset(preset_id: str) -> bool:
        """删除预设"""
        async with AsyncSessionLocal() as session:
            preset = await session.get(WorkflowPreset, preset_id)
            if not preset:
                return False
            await session.delete(preset)
            await session.commit()
            return True


# =============================================================================
# TaskService: 任务管理
# =============================================================================

class TaskService:
    """ComfyUI 任务服务"""

    @staticmethod
    async def create_task(
        prompt_id: str,
        task_type: WorkflowCategory,
        prompt: str,
        negative_prompt: str = "",
        params: Dict[str, Any] = None,
        template_id: str = None,
        preset_id: str = None,
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> ComfyUITask:
        """创建任务"""
        async with AsyncSessionLocal() as session:
            task = ComfyUITask(
                prompt_id=prompt_id,
                task_type=task_type,
                template_id=template_id,
                preset_id=preset_id,
                prompt=prompt,
                negative_prompt=negative_prompt,
                params_json=json.dumps(params or {}, ensure_ascii=False),
                priority=priority,
                status=TaskStatus.PENDING,
            )
            session.add(task)
            await session.commit()
            await session.refresh(task)
            await session.detach(task)
            return task

    @staticmethod
    async def get_task(prompt_id: str) -> Optional[ComfyUITask]:
        """获取任务"""
        async with AsyncSessionLocal() as session:
            result = await session.exec(
                select(ComfyUITask).where(ComfyUITask.prompt_id == prompt_id)
            )
            task = result.first()
            if task:
                await session.detach(task)
            return task

    @staticmethod
    async def get_task_by_id(task_id: str) -> Optional[ComfyUITask]:
        """通过 ID 获取任务"""
        async with AsyncSessionLocal() as session:
            result = await session.get(ComfyUITask, task_id)
            if result:
                await session.detach(result)
            return result

    @staticmethod
    async def list_tasks(
        status: TaskStatus = None,
        template_id: str = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[ComfyUITask], int]:
        """列出任务"""
        async with AsyncSessionLocal() as session:
            query = select(ComfyUITask)
            count_query = select(func.count(ComfyUITask.id))

            if status:
                query = query.where(ComfyUITask.status == status)
                count_query = count_query.where(ComfyUITask.status == status)
            if template_id:
                query = query.where(ComfyUITask.template_id == template_id)
                count_query = count_query.where(ComfyUITask.template_id == template_id)

            query = query.order_by(ComfyUITask.priority.desc(), ComfyUITask.created_at.desc())
            query = query.offset(offset).limit(limit)

            result = await session.execute(query).scalars()
            tasks = result.all()

            count_result = await session.execute(count_query).scalars()
            total = count_result.one()

            for t in tasks:
                await session.detach(t)

            return list(tasks), total

    @staticmethod
    async def update_progress(
        prompt_id: str,
        progress: float,
        step: int = 0,
        total: int = 0,
    ) -> Optional[ComfyUITask]:
        """更新进度"""
        async with AsyncSessionLocal() as session:
            result = await session.exec(
                select(ComfyUITask).where(ComfyUITask.prompt_id == prompt_id)
            )
            task = result.first()
            if task:
                task.progress = progress
                task.current_step = step
                task.total_steps = total
                if task.status == TaskStatus.PENDING:
                    task.mark_started()
                await session.commit()
                await session.refresh(task)
                await session.detach(task)
            return task

    @staticmethod
    async def mark_queued(prompt_id: str, node_url: str) -> Optional[ComfyUITask]:
        """标记为已入队"""
        async with AsyncSessionLocal() as session:
            result = await session.exec(
                select(ComfyUITask).where(ComfyUITask.prompt_id == prompt_id)
            )
            task = result.first()
            if task:
                task.mark_queued(node_url)
                await session.commit()
                await session.refresh(task)
                await session.detach(task)
            return task

    @staticmethod
    async def mark_completed(
        prompt_id: str,
        outputs: List[Dict] = None,
        output_images: List[str] = None,
    ) -> Optional[ComfyUITask]:
        """标记为已完成"""
        async with AsyncSessionLocal() as session:
            result = await session.exec(
                select(ComfyUITask).where(ComfyUITask.prompt_id == prompt_id)
            )
            task = result.first()
            if task:
                task.mark_completed(outputs or [], output_images or [])
                await session.commit()
                await session.refresh(task)
                await session.detach(task)
            return task

    @staticmethod
    async def mark_failed(prompt_id: str, error: str) -> Optional[ComfyUITask]:
        """标记为失败"""
        async with AsyncSessionLocal() as session:
            result = await session.exec(
                select(ComfyUITask).where(ComfyUITask.prompt_id == prompt_id)
            )
            task = result.first()
            if task:
                task.mark_failed(error)
                await session.commit()
                await session.refresh(task)
                await session.detach(task)
            return task

    @staticmethod
    async def mark_cancelled(prompt_id: str) -> Optional[ComfyUITask]:
        """标记为已取消"""
        async with AsyncSessionLocal() as session:
            result = await session.exec(
                select(ComfyUITask).where(ComfyUITask.prompt_id == prompt_id)
            )
            task = result.first()
            if task:
                task.mark_cancelled()
                await session.commit()
                await session.refresh(task)
                await session.detach(task)
            return task

    @staticmethod
    async def get_stats() -> Dict[str, Any]:
        """获取统计信息"""
        async with AsyncSessionLocal() as session:
            stats = {}

            for status in TaskStatus:
                result = await session.exec(
                    select(func.count(ComfyUITask.id)).where(ComfyUITask.status == status)
                )
                stats[status.value] = result.one()

            # 总计
            result = await session.execute(select(func.count(ComfyUITask.id).scalars()))
            stats["total"] = result.one()

            return stats


# =============================================================================
# NodeService: 节点管理
# =============================================================================

class NodeService:
    """ComfyUI 节点服务"""

    @staticmethod
    async def create_node(
        name: str,
        server_url: str,
        display_name: str = "",
        capabilities: List[str] = None,
        max_resolution: int = 2048,
        priority: int = 0,
    ) -> ComfyUINode:
        """创建节点"""
        async with AsyncSessionLocal() as session:
            node = ComfyUINode(
                name=name,
                display_name=display_name or name,
                server_url=server_url,
                capabilities=json.dumps(capabilities or ["txt2img"], ensure_ascii=False),
                max_resolution=max_resolution,
                priority=priority,
            )
            session.add(node)
            await session.commit()
            await session.refresh(node)
            await session.detach(node)
            return node

    @staticmethod
    async def get_node(node_id: str) -> Optional[ComfyUINode]:
        """获取节点"""
        async with AsyncSessionLocal() as session:
            result = await session.get(ComfyUINode, node_id)
            if result:
                await session.detach(result)
            return result

    @staticmethod
    async def get_default_node() -> Optional[ComfyUINode]:
        """获取默认节点"""
        async with AsyncSessionLocal() as session:
            result = await session.exec(
                select(ComfyUINode)
                .where(ComfyUINode.is_default == True)
                .where(ComfyUINode.is_active == True)
            )
            node = result.first()
            if node:
                await session.detach(node)
            return node

    @staticmethod
    async def list_nodes(
        is_active: bool = True,
        capability: str = None,
    ) -> List[ComfyUINode]:
        """列出节点"""
        async with AsyncSessionLocal() as session:
            query = select(ComfyUINode)

            if is_active is not None:
                query = query.where(ComfyUINode.is_active == is_active)
            if capability:
                # JSON 包含查询（SQLite）
                query = query.where(ComfyUINode.capabilities.contains(capability))

            query = query.order_by(ComfyUINode.priority.desc(), ComfyUINode.current_load.asc())

            result = await session.execute(query).scalars()
            nodes = result.all()

            for n in nodes:
                await session.detach(n)

            return list(nodes)

    @staticmethod
    async def update_load(node_id: str, delta: int = 1) -> Optional[ComfyUINode]:
        """更新节点负载"""
        async with AsyncSessionLocal() as session:
            node = await session.get(ComfyUINode, node_id)
            if node:
                node.current_load = max(0, node.current_load + delta)
                await session.commit()
                await session.refresh(node)
                await session.detach(node)
            return node

    @staticmethod
    async def update_stats(
        node_id: str,
        success: bool = True,
        latency_ms: int = 0,
    ) -> Optional[ComfyUINode]:
        """更新节点统计"""
        async with AsyncSessionLocal() as session:
            node = await session.get(ComfyUINode, node_id)
            if node:
                node.total_tasks += 1
                if success:
                    node.success_tasks += 1
                else:
                    node.failed_tasks += 1

                # 滑动平均延迟
                if latency_ms > 0 and node.avg_latency_ms > 0:
                    node.avg_latency_ms = int((node.avg_latency_ms + latency_ms) / 2)
                elif latency_ms > 0:
                    node.avg_latency_ms = latency_ms

                await session.commit()
                await session.refresh(node)
                await session.detach(node)
            return node

    @staticmethod
    async def heartbeat(node_id: str) -> bool:
        """更新心跳"""
        async with AsyncSessionLocal() as session:
            node = await session.get(ComfyUINode, node_id)
            if node:
                node.last_heartbeat = datetime.now()
                node.is_active = True
                await session.commit()
                return True
            return False

    @staticmethod
    async def set_default(node_id: str) -> bool:
        """设为默认节点"""
        async with AsyncSessionLocal() as session:
            # 先清除所有默认标记
            result = await session.exec(
                select(ComfyUINode).where(ComfyUINode.is_default == True)
            )
            for node in result.all():
                node.is_default = False

            # 设置新默认
            node = await session.get(ComfyUINode, node_id)
            if node:
                node.is_default = True
                await session.commit()
                return True
            return False

    @staticmethod
    async def delete_node(node_id: str) -> bool:
        """删除节点"""
        async with AsyncSessionLocal() as session:
            node = await session.get(ComfyUINode, node_id)
            if not node:
                return False
            await session.delete(node)
            await session.commit()
            return True
