"""
YLCraft — 口型同步服务 (Lip Sync)

基于音频分析生成口型动画数据。
支持对接 TTS 服务或处理用户上传的音频。
"""

from __future__ import annotations

import json
import struct
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any


@dataclass
class LipSyncKeyframe:
    """口型关键帧"""
    time: float  # 时间（秒）
    mouth_open: float  # 嘴巴张开程度（0 到 1）


@dataclass
class LipSyncResult:
    """口型同步结果"""
    duration: float  # 音频时长（秒）
    keyframes: List[LipSyncKeyframe] = field(default_factory=list)
    phonemes: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class SimpleLipSyncAnalyzer:
    """
    简单的口型同步分析器

    基于音频幅度生成口型动画。
    实际项目中可使用 WebRTC VAD 或专业的口型同步模型。
    """

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.window_size = 1024  # 分析窗口大小
        self.hop_size = 512  # 跳跃步长

    def analyze_wav(self, wav_path: str) -> LipSyncResult:
        """
        分析 WAV 文件生成口型数据

        Args:
            wav_path: WAV 文件路径

        Returns:
            口型同步结果
        """
        try:
            with wave.open(wav_path, 'rb') as wav:
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                rate = wav.getframerate()
                n_frames = wav.getnframes()

                if rate != self.sample_rate:
                    raise ValueError(f"不支持的采样率: {rate}，仅支持 {self.sample_rate}")

                # 读取音频数据
                audio_data = wav.readframes(n_frames)

                # 转换为浮点数
                if sample_width == 2:
                    fmt = f'<{len(audio_data) // 2}h'
                    samples = [s / 32768.0 for s in struct.unpack(fmt, audio_data)]
                else:
                    samples = [b / 255.0 - 0.5 for b in audio_data]

            duration = n_frames / rate
            keyframes = self._generate_keyframes(samples, rate)

            return LipSyncResult(
                duration=duration,
                keyframes=keyframes,
                metadata={
                    "sample_rate": rate,
                    "channels": channels,
                    "keyframes_count": len(keyframes),
                }
            )

        except Exception as e:
            raise Exception(f"音频分析失败: {e}")

    def _generate_keyframes(self, samples: List[float], rate: int) -> List[LipSyncKeyframe]:
        """
        基于音频幅度生成口型关键帧

        Args:
            samples: 音频样本
            rate: 采样率

        Returns:
            关键帧列表
        """
        keyframes = []
        hop_size = self.hop_size
        window_size = self.window_size

        for i in range(0, len(samples) - window_size, hop_size):
            # 计算 RMS 幅度
            window = samples[i:i + window_size]
            rms = sum(s * s for s in window) ** 0.5 / len(window)

            # 归一化到 0-1
            mouth_open = min(1.0, rms * 3.0)

            # 时间点
            time = i / rate

            keyframes.append(LipSyncKeyframe(
                time=time,
                mouth_open=mouth_open,
            ))

        return keyframes

    def generate_motion_json(self, result: LipSyncResult) -> Dict[str, Any]:
        """
        生成 Live2D 动作 JSON

        Args:
            result: 口型同步结果

        Returns:
            motion3.json 格式的动作数据
        """
        curves = []

        # 嘴巴张开动画
        mouth_points = []
        for kf in result.keyframes:
            mouth_points.extend([kf.time, kf.mouth_open])

        curves.append({
            "Target": "Parameter",
            "Id": "ParamMouthOpenY",
            "Segments": mouth_points,
        })

        return {
            "Version": 3,
            "Meta": {
                "Duration": result.duration * 1000,  # 转换为毫秒
                "Fps": 30,
                "Loop": False,
                "AreBeziersRestricted": True,
                "CurveCount": len(curves),
                "TotalSegmentCount": len(mouth_points) // 2,
                "TotalPointCount": len(mouth_points),
            },
            "Curves": curves,
        }


class LipSyncService:
    """
    口型同步服务

    支持：
    - 从 WAV 文件分析口型
    - 生成 Live2D 动作 JSON
    - 对接 TTS 服务
    """

    def __init__(self):
        self.analyzer = SimpleLipSyncAnalyzer()

    def analyze(self, audio_path: str) -> LipSyncResult:
        """
        分析音频文件

        Args:
            audio_path: 音频文件路径

        Returns:
            口型同步结果
        """
        return self.analyzer.analyze_wav(audio_path)

    def generate_motion(self, audio_path: str) -> Dict[str, Any]:
        """
        从音频生成口型动作

        Args:
            audio_path: 音频文件路径

        Returns:
            Live2D motion3.json 格式的动作数据
        """
        result = self.analyze(audio_path)
        return self.analyzer.generate_motion_json(result)

    def save_motion(self, audio_path: str, output_path: Path) -> Dict[str, Any]:
        """
        保存口型动作到文件

        Args:
            audio_path: 音频文件路径
            output_path: 输出文件路径

        Returns:
            motion3.json 内容
        """
        motion = self.generate_motion(audio_path)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(motion, f, indent=2, ensure_ascii=False)

        return motion


# 全局服务实例
_lip_sync_service: Optional[LipSyncService] = None


def get_lip_sync_service() -> LipSyncService:
    """获取全局 LipSyncService 实例"""
    global _lip_sync_service
    if _lip_sync_service is None:
        _lip_sync_service = LipSyncService()
    return _lip_sync_service


def analyze_lip_sync(audio_path: str) -> LipSyncResult:
    """
    便捷函数：分析音频文件

    Args:
        audio_path: 音频文件路径

    Returns:
        口型同步结果
    """
    service = get_lip_sync_service()
    return service.analyze(audio_path)


def generate_lip_sync_motion(audio_path: str) -> Dict[str, Any]:
    """
    便捷函数：从音频生成口型动作

    Args:
        audio_path: 音频文件路径

    Returns:
        Live2D motion3.json 格式的动作数据
    """
    service = get_lip_sync_service()
    return service.generate_motion(audio_path)


__all__ = [
    "LipSyncService",
    "LipSyncKeyframe",
    "LipSyncResult",
    "SimpleLipSyncAnalyzer",
    "get_lip_sync_service",
    "analyze_lip_sync",
    "generate_lip_sync_motion",
]
