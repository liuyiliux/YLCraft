from app.services.ai.backends.llm.generic import _build_chat_url


def test_build_chat_url_from_api_root():
    assert (
        _build_chat_url("https://api.siliconflow.cn/v1", "/chat/completions")
        == "https://api.siliconflow.cn/v1/chat/completions"
    )


def test_build_chat_url_does_not_duplicate_full_endpoint_base():
    assert (
        _build_chat_url("https://api.siliconflow.cn/v1/chat/completions", "/chat/completions")
        == "https://api.siliconflow.cn/v1/chat/completions"
    )


def test_build_chat_url_handles_endpoint_with_version_prefix():
    assert (
        _build_chat_url("https://api.siliconflow.cn/v1", "/v1/chat/completions")
        == "https://api.siliconflow.cn/v1/chat/completions"
    )
