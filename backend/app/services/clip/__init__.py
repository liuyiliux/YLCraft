"""
YLCraft — Clip Lab 服务

三种剪辑模式：
- CutClaw Agent：自然语言指令驱动，LLM 工具调用循环
- NarratoAI Pipeline：自动节拍踩点 + VLM 美学评分
- MoE 多专家协作：Beat / Composition / Narrative 三专家 + ControlPlane 仲裁

参考：
- CutClaw (src/core.py): LLM Agent 工具调用
- NarratoAI (app/services/clip_video.py): Pipeline + OST 分派
- montage-ai (src/montage_ai/): MoE 多专家协作
"""

from app.services.clip.narrato_service import NarratoService, get_narrato_service
from app.services.clip.cutclaw_service import CutClawService, get_cutclaw_service
from app.services.clip.moe_service import MoEService, get_moe_service

__all__ = [
    "NarratoService", "get_narrato_service",
    "CutClawService", "get_cutclaw_service",
    "MoEService", "get_moe_service",
]
