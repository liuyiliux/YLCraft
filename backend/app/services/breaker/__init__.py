r"""
YLCraft — 爆款拆解服务

本模块重构后，所有实现已移至 `breaker/service.py`。
此处仅保留向后兼容的导出层。

Usage:
    from app.services.breaker import (
        create_task,
        get_task,
        parse_video_url,
        download_video,
        extract_audio,
        transcribe_audio,
        extract_key_frames,
        analyze_with_llm,
        analyze_xhs_content,
        run_analysis,
        result_to_dict,
        _build_prompts,
        AnalysisStatus,
        BreakTask,
        BreakdownResult,
        CharacterExtract,
        ShotExtract,
        XhsNote,
    )
"""

from app.services.breaker.service import (
    AnalysisStatus,
    BreakTask,
    BreakdownResult,
    CharacterExtract,
    ShotExtract,
    XhsNote,
    _build_prompts,
    analyze_with_llm,
    analyze_xhs_content,
    create_task,
    download_video,
    extract_audio,
    extract_key_frames,
    get_task,
    parse_video_url,
    result_to_dict,
    run_analysis,
    transcribe_audio,
)

__all__ = [
    "AnalysisStatus",
    "BreakTask",
    "BreakdownResult",
    "CharacterExtract",
    "ShotExtract",
    "XhsNote",
    "_build_prompts",
    "analyze_with_llm",
    "analyze_xhs_content",
    "create_task",
    "download_video",
    "extract_audio",
    "extract_key_frames",
    "get_task",
    "parse_video_url",
    "result_to_dict",
    "run_analysis",
    "transcribe_audio",
]
