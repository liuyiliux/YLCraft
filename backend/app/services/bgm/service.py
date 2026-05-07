"""
YLCraft — BGM 配乐服务

管理 BGM 曲目库、混音操作、内置曲目初始化。
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ylcraft.bgm")

# 内置 BGM 数据（免费商用曲目示例，实际运行时需要放置对应的 mp3 文件）
BUILTIN_BGM_CATALOG = [
    {
        "id": "builtin_upbeat_01",
        "name": "Energy Boost",
        "artist": "YouTube Audio Library",
        "duration": 120.0,
        "genre": "upbeat",
        "mood": "energetic",
        "bpm": 128,
        "license": "YouTube Audio Library - Free",
        "file": "upbeat_energy_boost.mp3",
    },
    {
        "id": "builtin_upbeat_02",
        "name": "Summer Vibes",
        "artist": "YouTube Audio Library",
        "duration": 95.0,
        "genre": "upbeat",
        "mood": "happy",
        "bpm": 120,
        "license": "YouTube Audio Library - Free",
        "file": "upbeat_summer_vibes.mp3",
    },
    {
        "id": "builtin_calm_01",
        "name": "Gentle Rain",
        "artist": "Incompetech",
        "duration": 180.0,
        "genre": "calm",
        "mood": "relaxed",
        "bpm": 70,
        "license": "CC BY 4.0 - Kevin MacLeod",
        "file": "calm_gentle_rain.mp3",
    },
    {
        "id": "builtin_calm_02",
        "name": "Peaceful Morning",
        "artist": "Incompetech",
        "duration": 150.0,
        "genre": "calm",
        "mood": "relaxed",
        "bpm": 65,
        "license": "CC BY 4.0 - Kevin MacLeod",
        "file": "calm_peaceful_morning.mp3",
    },
    {
        "id": "builtin_epic_01",
        "name": "Epic Journey",
        "artist": "Pixabay Music",
        "duration": 210.0,
        "genre": "epic",
        "mood": "intense",
        "bpm": 140,
        "license": "Pixabay License - Free Commercial",
        "file": "epic_journey.mp3",
    },
    {
        "id": "builtin_epic_02",
        "name": "Rise of Heroes",
        "artist": "Pixabay Music",
        "duration": 195.0,
        "genre": "epic",
        "mood": "intense",
        "bpm": 135,
        "license": "Pixabay License - Free Commercial",
        "file": "epic_rise_of_heroes.mp3",
    },
    {
        "id": "builtin_ambient_01",
        "name": "Dreamy Clouds",
        "artist": "Free Music Archive",
        "duration": 240.0,
        "genre": "ambient",
        "mood": "neutral",
        "bpm": 80,
        "license": "CC0 - Public Domain",
        "file": "ambient_dreamy_clouds.mp3",
    },
    {
        "id": "builtin_ambient_02",
        "name": "Night Stars",
        "artist": "Free Music Archive",
        "duration": 200.0,
        "genre": "ambient",
        "mood": "relaxed",
        "bpm": 75,
        "license": "CC0 - Public Domain",
        "file": "ambient_night_stars.mp3",
    },
    {
        "id": "builtin_cinematic_01",
        "name": "Cinematic Tension",
        "artist": "YouTube Audio Library",
        "duration": 160.0,
        "genre": "cinematic",
        "mood": "intense",
        "bpm": 100,
        "license": "YouTube Audio Library - Free",
        "file": "cinematic_tension.mp3",
    },
    {
        "id": "builtin_jazz_01",
        "name": "Smooth Jazz Cafe",
        "artist": "Incompetech",
        "duration": 220.0,
        "genre": "jazz",
        "mood": "relaxed",
        "bpm": 90,
        "license": "CC BY 4.0 - Kevin MacLeod",
        "file": "jazz_smooth_cafe.mp3",
    },
]


class BGMService:
    """BGM 配乐服务"""

    _bgm_dir: Path = Path("data/bgm")
    _tracks: dict[str, dict] = {}  # 内存缓存（简单实现，避免强依赖数据库）

    def __init__(self):
        self._bgm_dir.mkdir(parents=True, exist_ok=True)
        self._init_builtin_catalog()

    def _init_builtin_catalog(self):
        """初始化内置曲目目录（仅元数据，文件不存在时标记 available=False）"""
        for track_meta in BUILTIN_BGM_CATALOG:
            track_id = track_meta["id"]
            file_path = self._bgm_dir / track_meta["file"]
            self._tracks[track_id] = {
                "id": track_id,
                "name": track_meta["name"],
                "artist": track_meta["artist"],
                "duration": track_meta["duration"],
                "file_path": str(file_path),
                "genre": track_meta["genre"],
                "mood": track_meta["mood"],
                "bpm": track_meta["bpm"],
                "license": track_meta["license"],
                "is_builtin": True,
                "is_favorite": False,
                "available": file_path.exists(),   # 文件是否实际存在
                "tags": f"{track_meta['genre']},{track_meta['mood']}",
                "created_at": datetime.now().isoformat(),
            }
        logger.info(f"BGM 目录初始化完成，共 {len(self._tracks)} 首曲目")

    def list_tracks(
        self,
        genre: Optional[str] = None,
        mood: Optional[str] = None,
        search: Optional[str] = None,
        include_unavailable: bool = True,
    ) -> list[dict]:
        """列出曲目，支持按风格/情绪过滤"""
        result = list(self._tracks.values())

        if not include_unavailable:
            result = [t for t in result if t.get("available")]

        if genre:
            result = [t for t in result if t.get("genre", "").lower() == genre.lower()]

        if mood:
            result = [t for t in result if t.get("mood", "").lower() == mood.lower()]

        if search:
            s = search.lower()
            result = [
                t for t in result
                if s in t.get("name", "").lower()
                or s in t.get("artist", "").lower()
            ]

        return sorted(result, key=lambda t: (t["genre"], t["name"]))

    def get_track(self, track_id: str) -> Optional[dict]:
        """获取曲目详情"""
        return self._tracks.get(track_id)

    def add_track(
        self,
        file_path: str,
        name: str,
        artist: str = "",
        genre: str = "other",
        mood: str = "neutral",
        bpm: int = 0,
        duration: float = 0.0,
        license_info: str = "自定义上传",
    ) -> dict:
        """添加自定义曲目"""
        track_id = uuid.uuid4().hex
        track = {
            "id": track_id,
            "name": name,
            "artist": artist,
            "duration": duration,
            "file_path": file_path,
            "genre": genre,
            "mood": mood,
            "bpm": bpm,
            "license": license_info,
            "is_builtin": False,
            "is_favorite": False,
            "available": Path(file_path).exists(),
            "tags": f"{genre},{mood}",
            "created_at": datetime.now().isoformat(),
        }
        self._tracks[track_id] = track
        logger.info(f"新增 BGM 曲目: {name} ({track_id})")
        return track

    def delete_track(self, track_id: str) -> bool:
        """删除自定义曲目（内置曲目不可删除）"""
        track = self._tracks.get(track_id)
        if not track:
            return False
        if track.get("is_builtin"):
            raise ValueError("内置曲目不可删除")

        # 删除文件
        file_path = Path(track["file_path"])
        if file_path.exists():
            file_path.unlink()

        del self._tracks[track_id]
        return True

    def toggle_favorite(self, track_id: str) -> bool:
        """切换收藏状态"""
        track = self._tracks.get(track_id)
        if not track:
            return False
        track["is_favorite"] = not track.get("is_favorite", False)
        return track["is_favorite"]

    def get_genres(self) -> list[str]:
        """获取所有风格分类"""
        genres = set(t.get("genre", "") for t in self._tracks.values())
        return sorted(genres - {""})

    def get_moods(self) -> list[str]:
        """获取所有情绪分类"""
        moods = set(t.get("mood", "") for t in self._tracks.values())
        return sorted(moods - {""})

    async def get_audio_duration(self, file_path: str) -> float:
        """用 FFprobe 获取音频时长"""
        import subprocess
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", file_path],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception as e:
            logger.warning(f"获取音频时长失败: {e}")
        return 0.0


# 全局单例
bgm_service = BGMService()
