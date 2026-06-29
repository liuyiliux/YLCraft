import json

import httpx
import pytest

from app.db.models.ai_connector import AIConnector, AIProviderType
from app.services.ai.backends.image.generic import GenericImageBackend
from app.services.ai.types import ImageGenerationRequest
from app.services.ai_connector.service import AIConnectorService


ASYNC_CONFIG = {
    "request_headers": {"X-ModelScope-Async-Mode": "true"},
    "task_id_path": "$.task_id",
    "poll_endpoint": "v1/tasks/{task_id}",
    "poll_method": "GET",
    "poll_headers": {"X-ModelScope-Task-Type": "image_generation"},
    "status_path": "$.task_status",
    "done_value": "SUCCEED",
    "failed_value": "FAILED",
    "images_path": "$.output_images[*]",
}


def _connector() -> AIConnector:
    return AIConnector(
        id="conn-modelscope",
        provider="modelscope",
        name="modelscope-image",
        provider_type=AIProviderType.image,
        api_key="test-token",
        base_url="https://api-inference.modelscope.cn",
        api_endpoint="/v1/images/generations",
        default_model="Qwen/Qwen-Image",
        request_template='{"model":"{{ model }}","prompt":"{{ prompt }}"}',
        response_config=json.dumps({"async_config": ASYNC_CONFIG}),
    )


@pytest.mark.asyncio
async def test_generic_image_async_generate_returns_pending_without_polling(monkeypatch):
    requests = []

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self.headers = kwargs.get("headers") or {}

        async def post(self, url, json=None):
            requests.append(("POST", url, dict(self.headers), json))
            return httpx.Response(200, json={"task_id": "task-123", "task_status": "PENDING"})

        async def get(self, url):
            requests.append(("GET", url, dict(self.headers), None))
            return httpx.Response(200, json={"task_status": "SUCCEED", "output_images": ["https://img.example/1.png"]})

        async def aclose(self):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr("app.services.ai.backends.image.generic.httpx.AsyncClient", FakeAsyncClient)

    backend = GenericImageBackend(_connector(), session=None)
    result = await backend.generate(ImageGenerationRequest(prompt="A golden cat"))

    assert result.success is True
    assert result.status == "pending"
    assert result.task_id == "task-123"
    assert result.provider == "modelscope-image"
    assert [req[0] for req in requests] == ["POST"]
    assert requests[0][1] == "https://api-inference.modelscope.cn/v1/images/generations"
    assert requests[0][2]["X-ModelScope-Async-Mode"] == "true"


@pytest.mark.asyncio
async def test_generic_image_async_poll_uses_configured_endpoint_and_headers(monkeypatch):
    requests = []

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self.headers = kwargs.get("headers") or {}

        async def get(self, url):
            requests.append(("GET", url, dict(self.headers), None))
            return httpx.Response(200, json={"task_status": "SUCCEED", "output_images": ["https://img.example/1.png"]})

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr("app.services.ai.backends.image.generic.httpx.AsyncClient", FakeAsyncClient)

    backend = GenericImageBackend(_connector(), session=None)
    async def fake_download(url, prompt):
        return None

    backend._download_image = fake_download
    result = await backend.poll("task-123")

    assert result.success is True
    assert result.status == "done"
    assert result.task_id == "task-123"
    assert result.url == "https://img.example/1.png"
    assert requests == [
        (
            "GET",
            "https://api-inference.modelscope.cn/v1/tasks/task-123",
            {
                "Authorization": "Bearer test-token",
                "Content-Type": "application/json",
                "X-ModelScope-Task-Type": "image_generation",
            },
            None,
        )
    ]


@pytest.mark.asyncio
async def test_generic_image_async_poll_returns_pending(monkeypatch):
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def get(self, url):
            return httpx.Response(200, json={"task_status": "RUNNING"})

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr("app.services.ai.backends.image.generic.httpx.AsyncClient", FakeAsyncClient)

    backend = GenericImageBackend(_connector(), session=None)
    result = await backend.poll("task-123")

    assert result.success is True
    assert result.status == "pending"
    assert result.task_id == "task-123"
    assert result.url is None
    assert result.urls is None


@pytest.mark.asyncio
async def test_generic_image_async_poll_returns_failed(monkeypatch):
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def get(self, url):
            return httpx.Response(200, json={"task_status": "FAILED", "message": "remote failed"})

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr("app.services.ai.backends.image.generic.httpx.AsyncClient", FakeAsyncClient)

    backend = GenericImageBackend(_connector(), session=None)
    result = await backend.poll("task-123")

    assert result.success is False
    assert result.status == "error"
    assert result.task_id == "task-123"
    assert "remote failed" in (result.error or "")


@pytest.mark.asyncio
async def test_connection_test_supports_async_image_poll():
    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["task_type"] = request.headers.get("X-ModelScope-Task-Type")
        return httpx.Response(200, json={"task_status": "PENDING"})

    service = object.__new__(AIConnectorService)
    conn = _connector()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await service._test_async_image_poll(
            conn=conn,
            client=client,
            create_response=httpx.Response(200, json={"task_id": "task-123"}),
            async_config=ASYNC_CONFIG,
        )

    assert result["success"] is True
    assert result["task_id"] == "task-123"
    assert seen == {
        "url": "https://api-inference.modelscope.cn/v1/tasks/task-123",
        "task_type": "image_generation",
    }
