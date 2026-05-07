"""
YLCraft — Live2D 服务层

包含：
- rembg: AI 抠图服务
- style_transfer: 风格转换服务
- segmentation: AI 自动分层服务
- api_client: 云端API客户端
- config: 配置管理
"""

from __future__ import annotations

# 配置管理
from app.core.config import ProcessingMode, Live2DConfig, get_live2d_config

# AI 抠图服务
from app.services.live2d.rembg import (
    RembangService,
    RembangResult,
    get_rembg_service,
    process_image as rembg_process,
    MODEL_CACHE_DIR as REMBG_MODEL_DIR,
)

# 风格转换服务
from app.services.live2d.style_transfer import (
    StyleTransferService,
    StyleTransferMode,
    StyleTransferResult,
    get_style_transfer_service,
    process_image as style_transfer_process,
)

# AI 分层服务
from app.services.live2d.segmentation import (
    SegmentationService,
    SegmentationModelType,
    SegmentationResult,
    LayerInfo,
    PersonPartCategory,
    get_segmentation_service,
    process_image as segmentation_process,
)

# 五官绑骨服务
from app.services.live2d.rigging import (
    RiggingService,
    RiggingResult,
    RiggedFace,
    BoneTransform,
    EyeTracking,
    ExpressionBlend,
    ExpressionType,
    FacePart,
    ExpressionCalculator,
    BlinkController,
    LookAtController,
    get_rigging_service,
    rig_face_image,
)

# API 客户端
from app.services.live2d.api_client import (
    APIClientError,
    RemoveBgClient,
    ReplicateClient,
    HuggingFaceClient,
    get_api_client,
)

# VTS 导出服务
from app.services.live2d.vts_exporter import (
    VTSExporter,
    VTSModelSettings,
    VTSExpression,
    VTSMotion,
    export_to_vts,
)

# 口型同步服务
from app.services.live2d.lip_sync import (
    LipSyncService,
    LipSyncKeyframe,
    LipSyncResult,
    SimpleLipSyncAnalyzer,
    get_lip_sync_service,
    analyze_lip_sync,
    generate_lip_sync_motion,
)

# 动作预设库
from app.services.live2d.motion_presets import (
    MotionCategory,
    MotionPreset,
    MOTION_PRESETS,
    get_motion_preset,
    get_motion_presets_by_category,
    generate_motion_json,
    get_all_presets,
)

# 批量处理队列
from app.services.live2d.batch_queue import (
    QueueStatus,
    QueueItem,
    BatchQueue,
    BatchQueueManager,
    get_batch_queue_manager,
    create_batch_queue,
    get_batch_queue,
    cancel_batch_queue,
)

__all__ = [
    # Config
    "ProcessingMode",
    "Live2DConfig",
    "get_live2d_config",
    # Rembang
    "RembangService",
    "RembangResult",
    "get_rembg_service",
    "rembg_process",
    "REMBG_MODEL_DIR",
    # Style Transfer
    "StyleTransferService",
    "StyleTransferMode",
    "StyleTransferResult",
    "get_style_transfer_service",
    "style_transfer_process",
    # Segmentation
    "SegmentationService",
    "SegmentationModelType",
    "SegmentationResult",
    "LayerInfo",
    "PersonPartCategory",
    "get_segmentation_service",
    "segmentation_process",
    # Rigging
    "RiggingService",
    "RiggingResult",
    "RiggedFace",
    "BoneTransform",
    "EyeTracking",
    "ExpressionBlend",
    "ExpressionType",
    "FacePart",
    "ExpressionCalculator",
    "BlinkController",
    "LookAtController",
    "get_rigging_service",
    "rig_face_image",
    # API Client
    "APIClientError",
    "RemoveBgClient",
    "ReplicateClient",
    "HuggingFaceClient",
    "get_api_client",
    # VTS Exporter
    "VTSExporter",
    "VTSModelSettings",
    "VTSExpression",
    "VTSMotion",
    "export_to_vts",
    # Lip Sync
    "LipSyncService",
    "LipSyncKeyframe",
    "LipSyncResult",
    "SimpleLipSyncAnalyzer",
    "get_lip_sync_service",
    "analyze_lip_sync",
    "generate_lip_sync_motion",
    # Motion Presets
    "MotionCategory",
    "MotionPreset",
    "MOTION_PRESETS",
    "get_motion_preset",
    "get_motion_presets_by_category",
    "generate_motion_json",
    "get_all_presets",
]
