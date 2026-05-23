"""
YLCraft — AI 模型管理服务

实现 AI 模型的发现、下载、管理：
- 模型池管理
- CivitAI 集成
- 模型元数据提取
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from uuid import uuid4
import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset_hub import AssetNode, AssetType, AIModel

logger = logging.getLogger("ylcraft.model_service")


class ModelService:
    """AI 模型管理服务"""

    # CivitAI API 配置
    CIVITAI_API_BASE = "https://civitai.com/api/v1"

    # 支持的模型类型
    MODEL_TYPES = ["Checkpoint", "LoRA", "TextualInversion", "Controlnet", "VAE", "Upscaler"]

    def __init__(self, session: AsyncSession):
        self.session = session
        self._storage_base = Path(__file__).parent.parent.parent.parent.parent / "storage" / "models"
        self._storage_base.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------------------
    # 模型发现
    # -------------------------------------------------------------------------

    async def scan_local_models(self, directory: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        扫描本地模型目录，发现新模型

        支持的格式：.safetensors, .ckpt, .pth, .onnx
        """
        scan_dir = Path(directory) if directory else self._storage_base
        discovered = []

        for ext in ["*.safetensors", "*.ckpt", "*.pth", "*.onnx", "*.pt"]:
            for model_path in scan_dir.rglob(ext):
                # 计算文件哈希
                file_hash = await self._calculate_file_hash(model_path)

                # 检查是否已存在于数据库
                existing = await self._get_model_by_hash(file_hash)

                if not existing:
                    discovered.append({
                        "path": str(model_path),
                        "filename": model_path.name,
                        "size": model_path.stat().st_size,
                        "hash": file_hash,
                        "type": self._detect_model_type(model_path.name),
                    })

        return discovered

    async def _calculate_file_hash(self, file_path: Path) -> str:
        """计算文件的 SHA256 哈希（用于 CivitAI 匹配）"""
        sha256_hash = hashlib.sha256()

        try:
            # 快速哈希：只读取前 10MB
            with open(file_path, "rb") as f:
                chunk = f.read(10 * 1024 * 1024)
                sha256_hash.update(chunk)
        except Exception as e:
            logger.warning(f"[ModelService] Failed to hash file {file_path}: {e}")

        return sha256_hash.hexdigest()

    async def _get_model_by_hash(self, file_hash: str) -> Optional[AIModel]:
        """根据文件哈希查找模型"""
        result = await self.session.execute(
            select(AIModel).where(AIModel.file_hash == file_hash)
        )
        return result.scalar_one_or_none()

    def _detect_model_type(self, filename: str) -> str:
        """根据文件名检测模型类型"""
        name_lower = filename.lower()

        if "lora" in name_lower or "_lora" in name_lower or "-lora" in name_lower:
            return "LoRA"
        elif "textual" in name_lower or "embedding" in name_lower:
            return "TextualInversion"
        elif "controlnet" in name_lower or "control" in name_lower:
            return "Controlnet"
        elif "vae" in name_lower:
            return "VAE"
        elif "upscale" in name_lower or "upscaler" in name_lower:
            return "Upscaler"
        else:
            return "Checkpoint"

    # -------------------------------------------------------------------------
    # CivitAI 集成
    # -------------------------------------------------------------------------

    async def search_civitai(
        self,
        query: str,
        model_types: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """搜索 CivitAI 模型"""
        params = {
            "query": query,
            "limit": min(limit, 50),
        }

        if model_types:
            params["types"] = ",".join(model_types)

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.CIVITAI_API_BASE}/models",
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

                return [
                    {
                        "id": model["id"],
                        "name": model["name"],
                        "type": model["type"],
                        "description": model.get("description", "")[:200],
                        "download_count": model.get("downloadCount", 0),
                        "rating": model.get("rating", 0),
                        "base_model": model.get("baseModel", ""),
                        "thumbnail_url": model.get("images", [{}])[0].get("url", "") if model.get("images") else "",
                        "url": f"https://civitai.com/models/{model['id']}",
                    }
                    for model in data.get("items", [])
                ]
        except httpx.HTTPError as e:
            logger.error(f"[ModelService] CivitAI API error: {e}")
            return []

    async def get_civitai_model_info(self, model_id: str) -> Optional[Dict[str, Any]]:
        """获取 CivitAI 模型详细信息"""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.CIVITAI_API_BASE}/models/{model_id}"
                )
                response.raise_for_status()
                data = response.json()

                return {
                    "id": data["id"],
                    "name": data["name"],
                    "type": data["type"],
                    "description": data.get("description", ""),
                    "base_model": data.get("baseModel", ""),
                    "tags": [t["name"] for t in data.get("tags", [])],
                    "versions": [
                        {
                            "id": v["id"],
                            "name": v["name"],
                            "base_model": v.get("baseModel", ""),
                            "download_url": v.get("downloadUrl", ""),
                            "size": v.get("size", 0),
                            "hashes": v.get("hashes", {}),
                        }
                        for v in data.get("modelVersions", [])
                    ],
                    "creator": {
                        "username": data.get("creator", {}).get("username", ""),
                        "avatar_url": data.get("creator", {}).get("image", ""),
                    },
                }
        except httpx.HTTPError as e:
            logger.error(f"[ModelService] CivitAI API error: {e}")
            return None

    async def download_civitai_model(
        self,
        model_id: str,
        version_id: Optional[str] = None,
        target_directory: Optional[str] = None,
        on_progress: Optional[callable] = None,
    ) -> Optional[Dict[str, Any]]:
        """下载 CivitAI 模型"""
        # 获取模型信息
        info = await self.get_civitai_model_info(model_id)
        if not info:
            return None

        # 选择版本
        if version_id:
            version = next((v for v in info["versions"] if v["id"] == version_id), None)
        else:
            version = info["versions"][0] if info["versions"] else None

        if not version:
            logger.error(f"[ModelService] No version found for model {model_id}")
            return None

        download_url = version["download_url"]
        if not download_url:
            logger.error(f"[ModelService] No download URL for version {version_id}")
            return None

        # 确定保存路径
        save_dir = Path(target_directory) if target_directory else self._storage_base
        save_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{info['name'].replace('/', '_')}_{version['id']}.safetensors"
        save_path = save_dir / filename

        # 下载文件
        try:
            async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
                async with client.stream("GET", download_url) as response:
                    response.raise_for_status()

                    total_size = int(response.headers.get("content-length", 0))
                    downloaded = 0

                    with open(save_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            f.write(chunk)
                            downloaded += len(chunk)

                            if on_progress and total_size:
                                progress = int(downloaded / total_size * 100)
                                on_progress(progress)

            # 验证文件
            file_hash = await self._calculate_file_hash(save_path)

            # 创建数据库记录
            model_record = await self.register_model(
                file_path=str(save_path),
                file_hash=file_hash,
                civitai_model_id=str(model_id),
                civitai_version_id=str(version_id),
                model_type=info["type"],
                base_model=version.get("base_model", ""),
                name=info["name"],
                metadata={
                    "civitai_url": f"https://civitai.com/models/{model_id}",
                    "version_name": version["name"],
                    "file_size": version["size"],
                },
            )

            return {
                "path": str(save_path),
                "hash": file_hash,
                "model_record": model_record,
            }

        except Exception as e:
            logger.error(f"[ModelService] Download failed: {e}")
            # 清理失败的文件
            if save_path.exists():
                save_path.unlink()
            return None

    # -------------------------------------------------------------------------
    # 模型注册
    # -------------------------------------------------------------------------

    async def register_model(
        self,
        file_path: str,
        file_hash: str,
        name: str,
        model_type: str = "Checkpoint",
        base_model: str = "",
        civitai_model_id: str = "",
        civitai_version_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[AIModel]:
        """注册模型到数据库"""
        # 检查是否已存在
        existing = await self._get_model_by_hash(file_hash)
        if existing:
            logger.info(f"[ModelService] Model already registered: {name}")
            return existing

        # 创建 AssetNode（作为模型资产）
        asset = AssetNode(
            id=str(uuid4()),
            name=name,
            asset_type=AssetType.MODEL,
            metadata_json=metadata or {},
        )
        self.session.add(asset)
        await self.session.flush()

        # 创建 AIModel 记录
        model_record = AIModel(
            id=str(uuid4()),
            asset_node_id=asset.id,
            model_type=model_type,
            base_model=base_model,
            file_hash=file_hash,
            civitai_model_id=civitai_model_id,
            civitai_version_id=civitai_version_id,
            file_path=file_path,
            file_size=Path(file_path).stat().st_size if Path(file_path).exists() else 0,
        )

        self.session.add(model_record)
        await self.session.commit()
        await self.session.refresh(model_record)

        logger.info(f"[ModelService] Registered model: {name}")
        return model_record

    async def get_model(self, model_id: str) -> Optional[AIModel]:
        """获取模型详情"""
        return await self.session.get(AIModel, model_id)

    async def get_model_by_asset_id(self, asset_id: str) -> Optional[AIModel]:
        """根据 AssetNode ID 获取模型"""
        result = await self.session.execute(
            select(AIModel).where(AIModel.asset_node_id == asset_id)
        )
        return result.scalar_one_or_none()

    async def list_models(
        self,
        model_type: Optional[str] = None,
        base_model: Optional[str] = None,
        limit: int = 50,
    ) -> List[AIModel]:
        """列出模型"""
        query = select(AIModel)

        if model_type:
            query = query.where(AIModel.model_type == model_type)

        if base_model:
            query = query.where(AIModel.base_model == base_model)

        query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # 模型元数据
    # -------------------------------------------------------------------------

    async def extract_model_metadata(self, model_path: str) -> Dict[str, Any]:
        """提取模型元数据（预留接口）"""
        # TODO: 集成 diffusion_simple 或其他库提取模型元数据
        # 例如：SD 模型可提取 version, checkpoint_info 等

        path = Path(model_path)

        return {
            "filename": path.name,
            "size": path.stat().st_size if path.exists() else 0,
            "detected_type": self._detect_model_type(path.name),
        }

    async def update_trigger_words(self, model_id: str, trigger_words: str) -> bool:
        """更新模型的触发词"""
        model = await self.session.get(AIModel, model_id)
        if not model:
            return False

        model.trigger_words = trigger_words
        await self.session.commit()
        return True

    # -------------------------------------------------------------------------
    # 模型删除
    # -------------------------------------------------------------------------

    async def delete_model(self, model_id: str, delete_file: bool = False) -> bool:
        """删除模型记录（可选删除文件）"""
        model = await self.session.get(AIModel, model_id)
        if not model:
            return False

        # 删除文件
        if delete_file and model.file_path:
            file_path = Path(model.file_path)
            if file_path.exists():
                file_path.unlink()
                logger.info(f"[ModelService] Deleted model file: {file_path}")

        # 删除 AssetNode
        asset = await self.session.get(AssetNode, model.asset_node_id)
        if asset:
            await self.session.delete(asset)

        # 删除 AIModel
        await self.session.delete(model)
        await self.session.commit()

        return True
