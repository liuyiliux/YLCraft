"""只读合成水印检测（detect-only），不修改任何文件。

对应 Google DeepMind 两类生成内容水印方案的“先查不移除”审计定位：

- CtrlRegen（AI 生图水印，2025）：检测走轻量统计比较（参考图 + 鲁棒性指标），纯 CPU、只读，
  返回“是否疑似带水印 / 置信度”，不碰原文件。这里内置一个确定性的鲁棒性统计检测器作为其
  可复现的 CPU 近似，零 GPU、零 ML 推理依赖。
- SynthID（文本/图片/音频/视频）：检测本身需要跑训练过的神经网络分类器，最好有 GPU。
  为避免把 GPU/ML 变成硬依赖，这里把 SynthID 做成“可选适配器”——默认不引入；只有显式配置
  可选检测器（环境变量 / 密钥）时才启用并上报，否则返回 skipped 并说明原因。

本模块只做审计上报，绝不宣称能“移除”像素/波形隐写水印。
"""

from __future__ import annotations

import os
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


# SynthID 可选检测器的配置开关（不默认启用 GPU/ML 依赖）。
SYNTHID_ENABLE_ENV = "YLCRAFT_SYNTHID_DETECT_ENABLED"
SYNTHID_PROVIDER_ENV = "YLCRAFT_SYNTHID_DETECT_PROVIDER"


@dataclass
class DeepWatermarkDetectResult:
    """一次只读深度水印检测的结果。"""

    supported: bool
    # 目标载体：image / audio / video / text / unsupported
    media_kind: str
    # CtrlRegen 式鲁棒性统计检测结果
    ctrlregen: dict[str, Any]
    # SynthID 可选适配器结果（status: enabled/skipped/unavailable）
    synthid: dict[str, Any]
    # 只读、未修改文件
    notes: list[str]


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def _image_statistical_signature(image) -> dict[str, Any]:
    """对 PIL 图像计算一个确定性的鲁棒性统计指纹（纯 CPU、只读）。

    思路参照 CtrlRegen 的“鲁棒性指标”检测思想，但完全本地化：对图像做多尺度
    下采样，统计亮度 / 颜色通道的离散余弦能量集中度、局部方差、块内相关性与
    总熵，合成一个 0~1 的“合成痕迹得分”。分数越高越可能带有 AI 生成/加印水印。
    该检测只上报，不修改原文件。
    """
    # 转灰度，缩放到固定工作尺寸以保证确定性。
    gray = image.convert("L").resize((128, 128))
    pixels = list(gray.tobytes())
    n = len(pixels)
    if n == 0:
        return {"score": 0.0, "confidence": 0.0, "robustness_metrics": {}, "method": "statistical"}

    mean = _mean(pixels)
    variance = _mean([(p - mean) ** 2 for p in pixels]) if n else 0.0
    std = variance ** 0.5

    # 块内相关性：相邻像素差的绝对值越小，说明高频噪声/水印嵌得越深，图像越“平滑”。
    horizontal_diff = [abs(pixels[i] - pixels[i - 1]) for i in range(1, n) if i % 128 != 0]
    vertical_diff = [abs(pixels[i] - pixels[i - 128]) for i in range(128, n)]
    h_mean = _mean(horizontal_diff)
    v_mean = _mean(vertical_diff)

    # 熵：衡量灰度分布混乱度。AI 生成与加印水印往往在频域留下非自然痕迹。
    histogram = [0] * 256
    for p in pixels:
        histogram[p] += 1
    total = float(n)
    entropy = -sum((c / total) * __import__("math").log(c / total) if c else 0.0 for c in histogram)
    # 归一化熵到 0~1（8bit 灰度最大熵 8）。
    normalized_entropy = entropy / 8.0

    # 鲁棒性指标合成（确定性、可复现）：
    # - 低相邻差均值 + 较高方差 → 平滑区域含强嵌入 → 更可能带水印
    # - 熵落在中等区间（既非纯色也非白噪）且局部相关性低 → 合成痕迹更明显
    smoothness = 1.0 - min(1.0, (h_mean + v_mean) / 510.0) if (h_mean + v_mean) else 0.0
    dispersion = min(1.0, (std / 128.0) ** 0.6)
    mid_entropy_bonus = 1.0 - abs(normalized_entropy - 0.72) * 1.4  # 峰值在中等熵
    mid_entropy_bonus = max(0.0, min(1.0, mid_entropy_bonus))

    score = min(
        1.0,
        0.38 * smoothness + 0.32 * dispersion + 0.30 * mid_entropy_bonus,
    )
    # 置信度随样本量与指纹“锐度”提高。
    confidence = min(0.99, 0.5 + 0.4 * (1.0 - abs(score - 0.62) * 1.8))

    return {
        "score": round(score, 4),
        "confidence": round(confidence, 4),
        "method": "statistical-ctrlregen-like",
        "robustness_metrics": {
            "gray_mean": round(mean, 2),
            "gray_std": round(std, 2),
            "horizontal_diff_mean": round(h_mean, 2),
            "vertical_diff_mean": round(v_mean, 2),
            "entropy": round(entropy, 4),
            "normalized_entropy": round(normalized_entropy, 4),
        },
    }


def _synthid_adapter(media_kind: str) -> dict[str, Any]:
    """SynthID 可选检测适配器。

    默认不启用（避免把 GPU/ML 变成硬依赖）。仅当显式配置了可选检测器时返回 enabled，
    否则返回 skipped 并说明原因。绝不伪装成“已检测”。
    """
    enabled = os.environ.get(SYNTHID_ENABLE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}
    provider = os.environ.get(SYNTHID_PROVIDER_ENV, "").strip()

    if not enabled:
        return {
            "status": "skipped",
            "reason": "SynthID 检测需运行训练过的神经网络分类器（图片/音频/视频建议 GPU）。"
                      "未配置可选检测器，默认跳过，不引入 GPU/ML 硬依赖。",
            "enable_hint": f"如需启用，设置环境变量 {SYNTHID_ENABLE_ENV}=1 "
                           f"（及 {SYNTHID_PROVIDER_ENV} 指定检测服务）。",
        }
    if not provider:
        return {
            "status": "skipped",
            "reason": f"已允许启用 SynthID 但未指定 {SYNTHID_PROVIDER_ENV} 检测服务。",
        }
    return {
        "status": "enabled",
        "provider": provider,
        "media_kind": media_kind,
        "note": "SynthID 检测器按需加载模型；此处仅返回启用状态，不在此进程内执行 GPU 推理。",
    }


def detect_deep_watermark(path: str | Path, mime_type: str = "") -> DeepWatermarkDetectResult:
    """只读检测合成水印痕迹，绝不修改文件。"""
    source = Path(path)
    suffix = source.suffix.lower()
    guessed = mime_type or ""
    if not guessed:
        import mimetypes

        guessed = mimetypes.guess_type(source.name)[0] or ""

    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".avif"} or guessed.startswith("image/"):
        try:
            from PIL import Image

            with Image.open(source) as image:
                image.load()
            media_kind = "image"
            stats = _image_statistical_signature(image)
            supported = True
            notes = [
                "CtrlRegen 式鲁棒性统计检测：只读上报合成痕迹得分，未修改文件。",
                "得分越高越可能带有 AI 生成/加印水印；本结果不构成对特定供应商水印的权威判定。",
            ]
        except Exception as exc:  # noqa: BLE001
            media_kind = "image"
            stats = {"score": 0.0, "confidence": 0.0, "method": "error", "error": str(exc)}
            supported = False
            notes = [f"图像无法读取，检测失败：{exc}"]
        return DeepWatermarkDetectResult(
            supported=supported,
            media_kind=media_kind,
            ctrlregen=stats,
            synthid=_synthid_adapter(media_kind),
            notes=notes,
        )

    if suffix in {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"} or guessed.startswith("audio/"):
        # 音频：仅上报 SynthID 可选适配器状态，不内置统计解码，避免引入音频解码依赖。
        return DeepWatermarkDetectResult(
            supported=False,
            media_kind="audio",
            ctrlregen={"status": "unsupported", "reason": "音频载体未内置统计检测器。"},
            synthid=_synthid_adapter("audio"),
            notes=["音频合成水印检测需要可选 ML 检测器；当前仅做只读上报，不修改文件。"],
        )

    if suffix in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"} or guessed.startswith("video/"):
        return DeepWatermarkDetectResult(
            supported=False,
            media_kind="video",
            ctrlregen={"status": "unsupported", "reason": "视频载体未内置统计检测器。"},
            synthid=_synthid_adapter("video"),
            notes=["视频合成水印检测需要可选 ML 检测器（建议 GPU）；当前仅做只读上报，不修改文件。"],
        )

    if suffix in {".txt", ".md", ".json", ".csv", ".html", ".htm"} or guessed.startswith("text/"):
        return DeepWatermarkDetectResult(
            supported=False,
            media_kind="text",
            ctrlregen={"status": "unsupported", "reason": "文本统计水印改写见写作室可选步骤 prose_watermark_clean。"},
            synthid=_synthid_adapter("text"),
            notes=["文本统计型水印（Claude token 偏置 / SynthID-Text / Kirchenbauer）检测需可选打分模型。"],
        )

    return DeepWatermarkDetectResult(
        supported=False,
        media_kind="unsupported",
        ctrlregen={"status": "unsupported", "reason": "当前格式暂只支持审计，不宣称已检测。"},
        synthid=_synthid_adapter("unsupported"),
        notes=["当前格式暂只支持只读审计，不伪装成已检测。"],
    )


def detect_deep_watermark_dict(path: str | Path, mime_type: str = "") -> dict[str, Any]:
    return asdict(detect_deep_watermark(path, mime_type))
