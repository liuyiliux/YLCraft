import base64
import io
import json

import httpx
import pytest

from app.db.models.ai_connector import AIConnector, AIConnectorResponse, AIProviderType
from app.services.ai.backends.image.generic import GenericImageBackend
from app.services.ai.types import ImageGenerationRequest
from app.services.ai_connector.service import (
    AIConnectorService,
    infer_image_connector_capabilities,
    normalize_reference_image_config_values,
)


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


def _aaccx_edit_connector(default_params: dict | None = None) -> AIConnector:
    return AIConnector(
        id="conn-aaccx-edit",
        provider="aaccx",
        name="aaccx-image-edit",
        provider_type=AIProviderType.image,
        api_key="test-token",
        base_url="https://api.aaccx.pw/v1",
        api_endpoint="/images/edits",
        default_model="gpt-image-2",
        request_template=(
            '{"model":"{{ model }}","prompt":{{ prompt_json }},'
            '"images":{{ images_json }},"size":"{{ size }}",'
            '"response_format":"{{ response_format }}"}'
        ),
        response_config=json.dumps(
            {
                "images_path": "$.data[*].b64_json",
                "base64_images_path": "$.data[*].b64_json",
                "response_format": "base64",
            }
        ),
        default_params=json.dumps(default_params or {}),
    )


def test_generic_image_template_escapes_multiline_prompt():
    backend = GenericImageBackend(_connector(), session=None)

    request_body = backend._render_request(
        {
            "model": "gpt-image-2",
            "prompt": "输出主立绘。\n外貌：冷白肤色，眼球是淡蓝色数据流。\n禁止：\"普通人类皮肤\"",
            "size": "1024x1024",
            "n": 1,
        }
    )

    assert request_body["model"] == "gpt-image-2"
    assert request_body["prompt"].startswith("输出主立绘。\n外貌")
    assert "普通人类皮肤" in request_body["prompt"]


def test_ai_connector_response_redacts_api_key():
    response = AIConnectorResponse.from_db(_aaccx_edit_connector())

    assert response.api_key == ""
    assert response.has_api_key is True


def test_edit_connector_is_not_exposed_as_text_to_image():
    conn = _aaccx_edit_connector()
    conn.support_reference_image = True
    capabilities = infer_image_connector_capabilities(conn)
    backend = GenericImageBackend(conn, session=None)

    assert capabilities == ["image_to_image"]
    assert backend.capabilities == {"image_to_image"}


def test_explicit_image_capabilities_override_nonstandard_endpoint_for_text_to_image():
    conn = _aaccx_edit_connector({"image_capabilities": ["text_to_image"]})
    conn.api_endpoint = "/vendor/custom-image-task"
    conn.support_reference_image = True

    assert infer_image_connector_capabilities(conn) == ["text_to_image"]


def test_explicit_image_capabilities_override_nonstandard_endpoint_for_image_to_image():
    conn = _connector()
    conn.api_endpoint = "/vendor/custom-image-task"
    conn.default_params = json.dumps({"image_capabilities": ["image_to_image"]})
    conn.support_reference_image = True

    assert infer_image_connector_capabilities(conn) == ["image_to_image"]


def test_explicit_image_capabilities_accept_alias_string():
    conn = _connector()
    conn.default_params = json.dumps({"image_capabilities": "txt2img,img2img"})

    assert infer_image_connector_capabilities(conn) == ["text_to_image", "image_to_image"]


def test_reference_image_config_normalizes_json_array_mode():
    config = normalize_reference_image_config_values(
        provider_type="image",
        default_params={},
        support_reference_image=True,
        support_multiple_reference_images=True,
        reference_image_field="image",
        reference_image_array_field="images",
        support_vision_input=False,
    )

    assert config["support_reference_image"] is True
    assert config["support_multiple_reference_images"] is True
    assert config["support_vision_input"] is True
    assert config["reference_image_field"] == ""
    assert config["reference_image_array_field"] == "images"
    assert "request_content_type" not in json.loads(config["default_params"] or "{}")


def test_reference_image_config_array_mode_enables_multiple_images():
    config = normalize_reference_image_config_values(
        provider_type="image",
        default_params={},
        support_reference_image=True,
        support_multiple_reference_images=False,
        reference_image_field="image",
        reference_image_array_field="images",
        support_vision_input=False,
    )

    assert config["support_multiple_reference_images"] is True
    assert config["reference_image_field"] == ""
    assert config["reference_image_array_field"] == "images"


def test_reference_image_config_normalizes_multipart_mode():
    config = normalize_reference_image_config_values(
        provider_type="image",
        default_params={"request_content_type": "multipart"},
        support_reference_image=True,
        support_multiple_reference_images=True,
        reference_image_field="image",
        reference_image_array_field="images",
        support_vision_input=False,
    )

    params = json.loads(config["default_params"])
    assert config["support_multiple_reference_images"] is False
    assert config["reference_image_field"] == "image"
    assert config["reference_image_array_field"] is None
    assert params["request_content_type"] == "multipart"
    assert params["multipart_image_field"] == "image"


def test_aaccx_edit_connector_builds_json_edit_request():
    service = object.__new__(AIConnectorService)
    request = service._build_test_request(
        base_url="https://api.aaccx.pw/v1",
        api_endpoint="/images/edits",
        provider_type="image",
        model="gpt-image-2",
        test_prompt="把这张图改成黑白极简海报风格，保留主体轮廓",
        api_format="custom",
        conn=_aaccx_edit_connector({"request_content_type": "multipart"}),
        test_options={"image_url": "https://example.com/input.png", "image_mode": "edit"},
    )

    assert request["method"] == "POST"
    assert request["url"] == "https://api.aaccx.pw/v1/images/edits"
    assert request["json"] == {
        "model": "gpt-image-2",
        "prompt": "把这张图改成黑白极简海报风格，保留主体轮廓",
        "images": [{"image_url": "https://example.com/input.png"}],
        "size": "1024x1024",
        "response_format": "b64_json",
    }


def test_generic_image_template_keeps_structured_reference_image_array():
    conn = _aaccx_edit_connector()
    conn.support_reference_image = True
    conn.reference_image_array_field = "images"
    conn.request_template = (
        '{"model":"{{ model }}","prompt":{{ prompt_json }},'
        '"images":[{"image_url":"{{ reference_image_url }}"}],'
        '"size":"{{ size }}","response_format":"b64_json"}'
    )
    backend = GenericImageBackend(conn, session=None)

    request_body = backend._render_request(
        {
            "model": "gpt-image-2",
            "prompt": "turn it into a minimal black and white poster",
            "size": "1024x1024",
            "reference_images": ["data:image/png;base64,AAAA"],
            "reference_image_url": "https://example.com/input.png",
        }
    )

    assert request_body["images"] == [{"image_url": "https://example.com/input.png"}]
    assert "image" not in request_body


def test_generic_image_reference_data_url_is_compressed(tmp_path):
    from PIL import Image

    image_path = tmp_path / "large.png"
    Image.new("RGB", (3000, 2200), (180, 40, 80)).save(image_path, format="PNG")
    backend = GenericImageBackend(_aaccx_edit_connector(), session=None)

    data_url = backend._url_to_base64(str(image_path))

    assert data_url.startswith("data:image/jpeg;base64,")
    _, payload = data_url.split(",", 1)
    with Image.open(io.BytesIO(base64.b64decode(payload))) as image:
        assert image.size == (1536, 1126)


def test_generic_image_reference_input_data_url_is_compressed(tmp_path):
    from PIL import Image

    image_path = tmp_path / "large-source.png"
    Image.new("RGB", (2600, 1800), (40, 100, 180)).save(image_path, format="PNG")
    raw = image_path.read_bytes()
    source_data_url = f"data:image/png;base64,{base64.b64encode(raw).decode()}"
    backend = GenericImageBackend(_aaccx_edit_connector(), session=None)

    data_url = backend._url_to_base64(source_data_url)

    assert data_url.startswith("data:image/jpeg;base64,")
    _, payload = data_url.split(",", 1)
    with Image.open(io.BytesIO(base64.b64decode(payload))) as image:
        assert image.size == (1536, 1063)

def test_aaccx_edit_connector_builds_multipart_edit_request(tmp_path):
    image_path = tmp_path / "input.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    service = object.__new__(AIConnectorService)
    conn = _aaccx_edit_connector({"request_content_type": "multipart"})

    request = service._build_test_request(
        base_url="https://api.aaccx.pw/v1",
        api_endpoint="/images/edits",
        provider_type="image",
        model="gpt-image-2",
        test_prompt="把这张图改成黑白极简海报风格，保留主体轮廓",
        api_format="custom",
        conn=conn,
        test_options={"image_path": str(image_path), "image_mode": "edit"},
    )

    assert request["method"] == "POST"
    assert request["url"] == "https://api.aaccx.pw/v1/images/edits"
    assert "json" not in request
    assert request["data"]["model"] == "gpt-image-2"
    assert request["data"]["response_format"] == "b64_json"
    assert "images" not in request["data"]
    file_name, file_bytes, mime_type = request["files"]["image"]
    assert file_name == "input.png"
    assert file_bytes == b"\x89PNG\r\n\x1a\n"
    assert mime_type == "image/png"


@pytest.mark.asyncio
async def test_generic_image_backend_sends_multipart_edit_request(monkeypatch, tmp_path):
    image_path = tmp_path / "input.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    requests = []

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self.headers = kwargs.get("headers") or {}

        async def post(self, url, json=None, data=None, files=None):
            requests.append(
                {
                    "url": url,
                    "headers": dict(self.headers),
                    "json": json,
                    "data": data,
                    "files": files,
                }
            )
            return httpx.Response(200, json={"data": [{"b64_json": "aGVsbG8="}]})

        async def aclose(self):
            return None

    monkeypatch.setattr("app.services.ai.backends.image.generic.httpx.AsyncClient", FakeAsyncClient)
    backend = GenericImageBackend(_aaccx_edit_connector({"request_content_type": "multipart"}), session=None)

    result = await backend.generate(
        ImageGenerationRequest(
            prompt="把这张图改成黑白极简海报风格，保留主体轮廓",
            source_image=str(image_path),
            size="1024x1024",
        )
    )

    assert result.success is True
    assert requests[0]["url"] == "https://api.aaccx.pw/v1/images/edits"
    assert requests[0]["json"] is None
    assert requests[0]["data"]["model"] == "gpt-image-2"
    assert requests[0]["data"]["response_format"] == "b64_json"
    assert "Content-Type" not in requests[0]["headers"]
    assert requests[0]["files"]["image"][0] == "image.png"


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
async def test_async_generate_keeps_completed_task_pollable_without_images(monkeypatch):
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self.headers = kwargs.get("headers") or {}

        async def post(self, url, json=None):
            return httpx.Response(200, json={"task_id": "task-123", "task_status": "SUCCEED"})

        async def aclose(self):
            return None

    monkeypatch.setattr("app.services.ai.backends.image.generic.httpx.AsyncClient", FakeAsyncClient)
    backend = GenericImageBackend(_connector(), session=None)

    result = await backend.generate(ImageGenerationRequest(prompt="A golden cat"))

    assert result.success is True
    assert result.status == "pending"
    assert result.task_id == "task-123"


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
        return httpx.Response(
            200,
            json={
                "task_status": "SUCCEED",
                "output_images": ["https://img.example/test.png"],
            },
        )

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
    assert result["status"] == "SUCCEED"
    assert result["image_urls"] == ["https://img.example/test.png"]
    assert seen == {
        "url": "https://api-inference.modelscope.cn/v1/tasks/task-123",
        "task_type": "image_generation",
    }
