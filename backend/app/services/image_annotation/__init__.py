"""图生图「画面批注」服务层。

`build_effective_prompt` 是核心：它拼出**真正发给模型的完整提示词**，
提示词预览接口与生图路径共用它，避免两边实现漂移。
"""

from app.services.image_annotation.service import (
    MARKED_IMAGE_HINT,
    MAX_ANNOTATIONS,
    MAX_COMMENT_LEN,
    MAX_INSTRUCTIONS_LEN,
    SCHEMA_VERSION,
    AnnotationError,
    annotation_payload_summary,
    build_effective_prompt,
    compose_annotation_prompt,
    normalize_annotations,
)

__all__ = [
    "MARKED_IMAGE_HINT",
    "MAX_ANNOTATIONS",
    "MAX_COMMENT_LEN",
    "MAX_INSTRUCTIONS_LEN",
    "SCHEMA_VERSION",
    "AnnotationError",
    "annotation_payload_summary",
    "build_effective_prompt",
    "compose_annotation_prompt",
    "normalize_annotations",
]