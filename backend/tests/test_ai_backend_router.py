from types import SimpleNamespace

from app.services.ai.service import AIService
from app.services.ai.backends.router import BackendRouter
from app.services.ai.types import MediaType


class FakeRegistry:
    def __init__(self, backends):
        self.backends = backends

    def get_all_backends(self, media_type):
        assert media_type == MediaType.LLM
        return self.backends

    def get_default(self, media_type):
        assert media_type == MediaType.LLM
        return None


def make_backend(name, provider, default_model, available_models="[]"):
    return SimpleNamespace(
        name=name,
        connector=SimpleNamespace(
            provider=provider,
            default_model=default_model,
            available_models=available_models,
        ),
    )


def test_resolve_llm_accepts_unique_provider_alias():
    backend = make_backend("deepseek-v4-pro", "deepseek", "deepseek-v4-pro")
    router = BackendRouter(FakeRegistry({"deepseek-v4-pro": backend}))

    resolved, model = router.resolve_llm(backend_name="deepseek", model="deepseek-v4-pro")

    assert resolved is backend
    assert model == "deepseek-v4-pro"


def test_resolve_llm_provider_alias_uses_model_to_disambiguate():
    chat = make_backend("vendor-chat", "vendor", "chat-v1")
    reasoning = make_backend("vendor-reasoning", "vendor", "reason-v2", '["reason-v2", "reason-v3"]')
    router = BackendRouter(FakeRegistry({"vendor-chat": chat, "vendor-reasoning": reasoning}))

    resolved, model = router.resolve_llm(backend_name="vendor", model="reason-v3")

    assert resolved is reasoning
    assert model == "reason-v3"


def test_resolve_llm_normalizes_html_space_and_trailing_whitespace():
    backend = make_backend("若海-qwen3.8-27b", "openai", "qwen3.8-27b")
    router = BackendRouter(FakeRegistry({backend.name: backend}))

    resolved, model = router.resolve_llm(
        backend_name="若海-qwen3.8-27b\u00a0",
        model="qwen3.8-27b &#x20;",
    )

    assert resolved is backend
    assert model == "qwen3.8-27b"


def test_ai_service_initialize_keeps_registry_session_usable(monkeypatch):
    """The registry retains connector instances, so initialization must not expire them."""

    class Registry:
        def load_all(self, *, config_path, session):
            assert config_path is None
            assert session is db_session

        def get_all_backends(self, _media_type):
            return {}

    class Session:
        def __init__(self):
            self.rollback_calls = 0

        def rollback(self):
            self.rollback_calls += 1

    db_session = Session()
    monkeypatch.setattr("app.services.ai.backends.registry.BackendRegistry", Registry)

    AIService.initialize(session=db_session)

    assert db_session.rollback_calls == 0
