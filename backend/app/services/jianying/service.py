"""
YLCraft — 剪映草稿解析器

解析剪映草稿 ZIP 包，提取：
- 视频片段
- 音频片段（BGM、配音）
- 字幕
- 贴纸
- 时间轴信息
"""

from __future__ import annotations

import json
import logging
import os
import zipfile
from pathlib import Path
from typing import List, Optional, Dict, Any
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("ylcraft.jianying_parser")


class JianYingDraftParser:
    """剪映草稿解析器"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # -------------------------------------------------------------------------
    # 草稿解析
    # -------------------------------------------------------------------------

    async def parse_draft(self, draft_zip_path: str) -> Dict[str, Any]:
        """
        解析剪映草稿 ZIP 包

        返回格式：
        {
            "draft_info": {...},
            "video_segments": [...],
            "audio_segments": [...],
            "subtitles": [...],
            "stickers": [...],
            "materials": {...},
        }
        """
        draft_path = Path(draft_zip_path)

        if not draft_path.exists():
            return {"error": "Draft file not found"}

        if draft_path.suffix.lower() != ".zip":
            return {"error": "Only ZIP format is supported"}

        result = {
            "draft_path": str(draft_path),
            "draft_info": {},
            "video_segments": [],
            "audio_segments": [],
            "subtitles": [],
            "stickers": [],
            "materials": {},
        }

        try:
            with zipfile.ZipFile(draft_path, "r") as zf:
                # 列出所有文件
                file_list = zf.namelist()

                # 读取草稿配置
                draft_content = self._find_draft_content(zf, file_list)
                if draft_content:
                    result["draft_info"] = self._parse_draft_content(draft_content)

                # 提取素材信息
                result["materials"] = self._extract_materials(zf, file_list)

                # 提取时间轴信息
                result["video_segments"] = self._extract_video_segments(draft_content)
                result["audio_segments"] = self._extract_audio_segments(draft_content)
                result["subtitles"] = self._extract_subtitles(draft_content)
                result["stickers"] = self._extract_stickers(draft_content)

        except zipfile.BadZipFile:
            return {"error": "Invalid ZIP file"}
        except Exception as e:
            logger.error(f"[JianYingParser] Failed to parse draft: {e}")
            return {"error": str(e)}

        return result

    def _find_draft_content(
        self, zf: zipfile.ZipFile, file_list: List[str]
    ) -> Optional[Dict[str, Any]]:
        """查找并读取 draft_content.json"""
        # 常见的路径
        candidates = [
            "draft_content.json",
            "data/draft_content.json",
            "drafts/draft_content.json",
        ]

        for candidate in candidates:
            if candidate in file_list:
                try:
                    with zf.open(candidate) as f:
                        return json.load(f)
                except Exception:
                    pass

        # 搜索包含 draft_content 的文件
        for path in file_list:
            if "draft_content" in path and path.endswith(".json"):
                try:
                    with zf.open(path) as f:
                        return json.load(f)
                except Exception:
                    pass

        return None

    def _parse_draft_content(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """解析草稿内容"""
        info = {
            "draft_id": content.get("id", ""),
            "draft_name": content.get("draft_name", ""),
            "duration": content.get("duration", 0),
            "video_width": content.get("video_width", 1920),
            "video_height": content.get("video_height", 1080),
            "fps": content.get("fps", 30),
            "create_time": content.get("create_time", 0),
            "update_time": content.get("update_time", 0),
        }

        # 提取视频轨道信息
        tracks = content.get("tracks", [])
        info["track_count"] = len(tracks)
        info["tracks"] = self._parse_tracks(tracks)

        return info

    def _parse_tracks(self, tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """解析轨道信息"""
        parsed_tracks = []

        for track in tracks:
            track_info = {
                "id": track.get("id", ""),
                "type": track.get("type", ""),  # video, audio, subtitle, sticker
                "name": track.get("name", ""),
                "clips": [],
            }

            for clip in track.get("clips", []):
                clip_info = {
                    "id": clip.get("id", ""),
                    "start_time": clip.get("start_time", 0),
                    "duration": clip.get("duration", 0),
                    "material_id": clip.get("material_id", ""),
                    "target_timerange": clip.get("target_timerange", {}),
                }
                track_info["clips"].append(clip_info)

            parsed_tracks.append(track_info)

        return parsed_tracks

    def _extract_materials(
        self, zf: zipfile.ZipFile, file_list: List[str]
    ) -> Dict[str, Any]:
        """提取素材信息"""
        materials = {
            "videos": [],
            "audios": [],
            "images": [],
            "texts": [],
        }

        # 查找素材目录
        material_paths = [p for p in file_list if "material" in p.lower()]

        for path in material_paths:
            if path.endswith(".json"):
                try:
                    with zf.open(path) as f:
                        data = json.load(f)

                        # 提取视频素材
                        if "videos" in data:
                            for video in data["videos"]:
                                materials["videos"].append({
                                    "id": video.get("id", ""),
                                    "name": video.get("name", ""),
                                    "duration": video.get("duration", 0),
                                    "path": video.get("path", ""),
                                })

                        # 提取音频素材
                        if "audios" in data:
                            for audio in data["audios"]:
                                materials["audios"].append({
                                    "id": audio.get("id", ""),
                                    "name": audio.get("name", ""),
                                    "duration": audio.get("duration", 0),
                                    "path": audio.get("path", ""),
                                })

                except Exception:
                    pass

        return materials

    def _extract_video_segments(
        self, content: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """提取视频片段信息"""
        if not content:
            return []

        segments = []
        tracks = content.get("tracks", [])

        for track in tracks:
            if track.get("type") == "video":
                for clip in track.get("clips", []):
                    segments.append({
                        "id": clip.get("id", ""),
                        "material_id": clip.get("material_id", ""),
                        "start_time": clip.get("start_time", 0),
                        "duration": clip.get("duration", 0),
                        "source_time_range": clip.get("source_timerange", {}),
                    })

        return segments

    def _extract_audio_segments(
        self, content: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """提取音频片段信息"""
        if not content:
            return []

        segments = []
        tracks = content.get("tracks", [])

        for track in tracks:
            if track.get("type") == "audio":
                for clip in track.get("clips", []):
                    segments.append({
                        "id": clip.get("id", ""),
                        "material_id": clip.get("material_id", ""),
                        "start_time": clip.get("start_time", 0),
                        "duration": clip.get("duration", 0),
                        "volume": clip.get("volume", 1.0),
                    })

        return segments

    def _extract_subtitles(
        self, content: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """提取字幕信息"""
        if not content:
            return []

        subtitles = []
        tracks = content.get("tracks", [])

        for track in tracks:
            if track.get("type") == "subtitle":
                for clip in track.get("clips", []):
                    subtitles.append({
                        "id": clip.get("id", ""),
                        "content": clip.get("content", ""),
                        "start_time": clip.get("start_time", 0),
                        "duration": clip.get("duration", 0),
                        "style": clip.get("style", {}),
                    })

        return subtitles

    def _extract_stickers(
        self, content: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """提取贴纸信息"""
        if not content:
            return []

        stickers = []
        tracks = content.get("tracks", [])

        for track in tracks:
            if track.get("type") == "sticker":
                for clip in track.get("clips", []):
                    stickers.append({
                        "id": clip.get("id", ""),
                        "material_id": clip.get("material_id", ""),
                        "start_time": clip.get("start_time", 0),
                        "duration": clip.get("duration", 0),
                        "position": clip.get("position", {}),
                        "rotation": clip.get("rotation", 0),
                        "scale": clip.get("scale", 1.0),
                    })

        return stickers

    # -------------------------------------------------------------------------
    # 素材提取
    # -------------------------------------------------------------------------

    async def extract_materials(
        self,
        draft_zip_path: str,
        output_dir: Optional[str] = None,
    ) -> Dict[str, List[str]]:
        """
        解压并提取草稿中的素材文件

        返回提取的文件路径：
        {
            "videos": ["path/to/video1.mp4", ...],
            "audios": ["path/to/bgm.mp3", ...],
            "images": [...],
        }
        """
        draft_path = Path(draft_zip_path)

        if output_dir is None:
            output_dir = str(draft_path.parent / draft_path.stem)

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        extracted = {
            "videos": [],
            "audios": [],
            "images": [],
        }

        try:
            with zipfile.ZipFile(draft_path, "r") as zf:
                for file_info in zf.filelist:
                    filename = file_info.filename

                    # 跳过目录和非素材文件
                    if filename.endswith("/"):
                        continue

                    ext = Path(filename).suffix.lower()

                    # 确定输出目录
                    if ext in [".mp4", ".mov", ".avi", ".mkv"]:
                        subdir = output_path / "videos"
                    elif ext in [".mp3", ".wav", ".aac", ".m4a"]:
                        subdir = output_path / "audios"
                    elif ext in [".jpg", ".jpeg", ".png", ".gif"]:
                        subdir = output_path / "images"
                    else:
                        subdir = output_path / "other"

                    subdir.mkdir(parents=True, exist_ok=True)

                    # 解压文件
                    output_file = subdir / Path(filename).name
                    zf.extract(file_info, output_path)

                    # 记录路径
                    if subdir == output_path / "videos":
                        extracted["videos"].append(str(output_file))
                    elif subdir == output_path / "audios":
                        extracted["audios"].append(str(output_file))
                    elif subdir == output_path / "images":
                        extracted["images"].append(str(output_file))

        except Exception as e:
            logger.error(f"[JianYingParser] Failed to extract materials: {e}")
            return {"error": str(e)}

        return extracted

    # -------------------------------------------------------------------------
    # 导入到资产中枢
    # -------------------------------------------------------------------------

    async def import_to_asset_hub(
        self,
        draft_zip_path: str,
        project_name: str,
        extract_materials: bool = True,
    ) -> Dict[str, Any]:
        """
        将剪映草稿导入到资产中枢

        创建项目资产，并关联所有素材。
        """
        from app.db.models.asset_hub import AssetNode, AssetType, AssetRelation, RelationType

        # 解析草稿
        draft_info = await self.parse_draft(draft_zip_path)
        if "error" in draft_info:
            return draft_info

        # 创建项目根节点
        project = AssetNode(
            id=str(uuid4()),
            name=project_name,
            asset_type=AssetType.COLLECTION,
            metadata_json={
                "source": "jianying",
                "draft_path": draft_zip_path,
                "duration": draft_info["draft_info"].get("duration", 0),
                "video_width": draft_info["draft_info"].get("video_width", 0),
                "video_height": draft_info["draft_info"].get("video_height", 0),
            },
        )
        self.session.add(project)
        await self.session.flush()

        # 提取并导入素材
        if extract_materials:
            materials = await self.extract_materials(draft_zip_path)

            # 导入视频素材
            for video_path in materials.get("videos", []):
                video_asset = AssetNode(
                    id=str(uuid4()),
                    name=Path(video_path).name,
                    asset_type=AssetType.VIDEO,
                    parent_id=project.id,
                    metadata_json={"source": "jianying_draft"},
                )
                self.session.add(video_asset)

            # 导入音频素材
            for audio_path in materials.get("audios", []):
                audio_asset = AssetNode(
                    id=str(uuid4()),
                    name=Path(audio_path).name,
                    asset_type=AssetType.AUDIO,
                    parent_id=project.id,
                    metadata_json={"source": "jianying_draft"},
                )
                self.session.add(audio_asset)

        await self.session.commit()

        return {
            "project_id": str(project.id),
            "project_name": project_name,
            "video_count": len(materials.get("videos", [])) if extract_materials else 0,
            "audio_count": len(materials.get("audios", [])) if extract_materials else 0,
        }

    # -------------------------------------------------------------------------
    # 导出草稿
    # -------------------------------------------------------------------------

    async def export_draft(
        self,
        project_id: str,
        output_path: str,
    ) -> Dict[str, Any]:
        """
        将资产中枢项目导出为剪映草稿（预留接口）

        需要生成 draft_content.json 和打包素材
        """
        # TODO: 实现导出功能
        logger.info(f"[JianYingParser] Export not implemented: project_id={project_id}")
        return {"error": "Export not implemented"}
