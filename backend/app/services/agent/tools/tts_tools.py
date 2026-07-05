"""Agent tools for text-to-speech output."""

from __future__ import annotations

from typing import Any

from app.services.agent.registry import register_tool


def _to_plain(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, dict):
        return value
    return {"value": value}


@register_tool(
    name="preview_tts_request",
    description="Preview a text-to-speech request without generating audio, useful before converting narration, dialogue, or script text to voice.",
    category="tts",
    examples=["预览这段旁白转语音参数", "检查 TTS 会用什么声音和语速", "先不要生成音频，只看请求"],
    input_schema_note="text is required and will be truncated in the preview. voice/provider are optional; speed defaults to 1.0.",
    output_schema_note="Returns success, normalized_request, text_length, text_preview, and cost_warning. No file is written.",
    risk_level="read",
    output_type="tts_request_preview",
)
async def preview_tts_request(
    text: str,
    voice: str = "",
    speed: float = 1.0,
    provider: str = "",
) -> dict[str, Any]:
    if not (text or "").strip():
        raise ValueError("text cannot be empty")
    cleaned = text.strip()
    safe_speed = max(0.25, min(float(speed or 1.0), 4.0))
    return {
        "success": True,
        "normalized_request": {
            "voice": voice or "",
            "speed": safe_speed,
            "provider": provider or "",
        },
        "text_length": len(cleaned),
        "text_preview": cleaned[:500] + ("..." if len(cleaned) > 500 else ""),
        "cost_warning": "This is only a preview. generate_tts_audio writes an audio file and may call a paid TTS provider when configured.",
    }


@register_tool(
    name="generate_tts_audio",
    description="Convert text to an audio file through YLCraft TTS and return the generated local file path and audio URL.",
    category="tts",
    examples=["把这一章旁白生成语音", "把短剧台词转成音频", "用指定 voice 生成 TTS 文件"],
    input_schema_note="text is required. voice/provider are optional and depend on configured TTS support. speed is clamped between 0.25 and 4.0.",
    output_schema_note="Returns success, file_path, audio_url, and error. The current backend may return a placeholder file until a real provider is configured.",
    risk_level="costly",
    output_type="tts_audio_result",
    cost_hint="This writes a local audio file and may consume paid TTS quota once a real provider is connected.",
)
async def generate_tts_audio(
    text: str,
    voice: str = "",
    speed: float = 1.0,
    provider: str = "",
) -> dict[str, Any]:
    if not (text or "").strip():
        raise ValueError("text cannot be empty")
    from app.api.v1.tts import TTSSpeakRequest, tts_speak

    response = await tts_speak(
        TTSSpeakRequest(
            text=text.strip(),
            voice=voice or None,
            speed=max(0.25, min(float(speed or 1.0), 4.0)),
            provider=provider or None,
        )
    )
    return _to_plain(response)
