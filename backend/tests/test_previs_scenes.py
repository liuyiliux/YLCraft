from __future__ import annotations

import contextlib
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from app.api.v1 import previs as previs_api
from app.core.task_queue import TaskStatus
from app.db.models.creative_project import CreativeProject, ProjectAssetLink, ProjectContent
from app.db.models.previs import PrevisSceneDocument


@pytest.fixture()
def previs_session_factory(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'previs.db'}")
    PrevisSceneDocument.__table__.create(engine)
    factory = sessionmaker(class_=Session, autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(previs_api, "SessionLocal", factory)
    yield factory
    engine.dispose()


@pytest.fixture()
def previs_client(previs_session_factory):
    app = FastAPI()
    app.include_router(previs_api.router, prefix="/api/v1/previs")
    return TestClient(app)


def _create_payload(**overrides) -> dict:
    payload = {
        "project_id": "project-1",
        "storyboard_content_id": "content-1",
        "panel_number": 1,
        "title": "第 1 镜预演",
        "scene": {
            "fps": 24,
            "durationFrames": 0,
            "activeCameraId": "cam-1",
            "nodes": [{"id": "node-1", "kind": "asset_model", "name": "角色", "assetId": "asset-1"}],
            "cameras": [{"id": "cam-1", "name": "机位 1", "fov": 50}],
            "keyframes": [],
            "settings": {},
        },
    }
    payload.update(overrides)
    return payload


def test_previs_scene_create_and_round_trip(previs_client):
    create_response = previs_client.post("/api/v1/previs/scenes", json=_create_payload())
    assert create_response.status_code == 200
    created = create_response.json()["data"]
    assert created["project_id"] == "project-1"
    assert created["storyboard_content_id"] == "content-1"
    assert created["panel_number"] == 1
    assert created["revision"] == 1
    assert created["scene"]["nodes"][0]["id"] == "node-1"

    get_response = previs_client.get(f"/api/v1/previs/scenes/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["data"]["revision"] == 1


def test_previs_scene_rejects_duplicate_panel(previs_client):
    first = previs_client.post("/api/v1/previs/scenes", json=_create_payload())
    assert first.status_code == 200

    duplicate = previs_client.post("/api/v1/previs/scenes", json=_create_payload())
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]


def test_previs_scene_save_requires_matching_revision(previs_client):
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]
    scene_id = created["id"]

    save_response = previs_client.put(
        f"/api/v1/previs/scenes/{scene_id}",
        json={"expected_revision": 1, "title": "更新后", "scene": created["scene"]},
    )
    assert save_response.status_code == 200
    assert save_response.json()["data"]["revision"] == 2

    stale_response = previs_client.put(
        f"/api/v1/previs/scenes/{scene_id}",
        json={"expected_revision": 1, "title": "过期保存", "scene": created["scene"]},
    )
    assert stale_response.status_code == 409
    detail = stale_response.json()["detail"]
    assert detail["current_revision"] == 2
    assert detail["expected_revision"] == 1


def test_previs_scene_list_filters_by_panel(previs_client):
    previs_client.post("/api/v1/previs/scenes", json=_create_payload())
    previs_client.post(
        "/api/v1/previs/scenes",
        json=_create_payload(panel_number=2, title="第 2 镜预演"),
    )

    all_response = previs_client.get("/api/v1/previs/scenes?project_id=project-1")
    assert all_response.status_code == 200
    assert all_response.json()["total"] == 2

    filtered = previs_client.get(
        "/api/v1/previs/scenes?project_id=project-1&storyboard_content_id=content-1&panel_number=2"
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["data"][0]["panel_number"] == 2


def test_previs_scene_delete(previs_client):
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]
    scene_id = created["id"]

    delete_response = previs_client.delete(f"/api/v1/previs/scenes/{scene_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_id"] == scene_id
    assert previs_client.get(f"/api/v1/previs/scenes/{scene_id}").status_code == 404


def test_previs_scene_rejects_non_object_scene(previs_client):
    response = previs_client.post(
        "/api/v1/previs/scenes",
        json=_create_payload(scene="not-an-object"),
    )
    assert response.status_code == 422


def test_previs_standalone_scene_create_and_round_trip(previs_client):
    # 独立场景：不绑定项目分镜，纯思路摆位，用于生图参考
    response = previs_client.post(
        "/api/v1/previs/scenes",
        json={"title": "独立思路场景", "scene": {"fps": 24, "nodes": [], "cameras": []}},
    )
    assert response.status_code == 200
    created = response.json()["data"]
    assert created["project_id"] == ""
    assert created["storyboard_content_id"] == ""
    assert created["panel_number"] is None
    assert created["revision"] == 1

    get_response = previs_client.get(f"/api/v1/previs/scenes/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["data"]["title"] == "独立思路场景"


def test_previs_standalone_scene_list_and_binding_filter(previs_client):
    standalone = previs_client.post("/api/v1/previs/scenes", json={"title": "独立场景"}).json()["data"]
    previs_client.post("/api/v1/previs/scenes", json=_create_payload())

    all_response = previs_client.get("/api/v1/previs/scenes")
    assert all_response.status_code == 200
    assert any(item["id"] == standalone["id"] for item in all_response.json()["data"])

    # 按项目过滤时不返回独立场景（独立场景 project_id 为空）
    filtered = previs_client.get("/api/v1/previs/scenes?project_id=project-1")
    assert all(item["project_id"] == "project-1" for item in filtered.json()["data"])


# ---------------------------------------------------------------------------
# 截图回流：Asset Hub 入库 + 分镜关联 + **服务端派生**溯源
# ---------------------------------------------------------------------------

#: 1x1 PNG（最小合法图片）。断言的是"内容被原样落盘"，不需要真实画面。
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6300010000050001a5f645400000000049454e44ae426082"
)


class _FakeCreateResult:
    def __init__(self, node_id: str) -> None:
        self.node_id = node_id


class _FakeAssetHubFacade:
    """记录 create_imported_file 的入参；`fail=True` 时模拟上传失败。"""

    fail = False
    last_call: dict = {}

    def __init__(self, session) -> None:
        self.session = session

    async def create_imported_file(self, **kwargs):
        type(self).last_call = kwargs
        if type(self).fail:
            raise RuntimeError("asset hub unavailable")
        return _FakeCreateResult("asset-captured-1")


class _FakeAsyncSession:
    """只实现端点用到的那三个成员：get / add / commit。"""

    def __init__(self, project, content) -> None:
        self._project = project
        self._content = content
        self.added: list = []
        self.committed = False

    async def get(self, model, ident):
        if model is CreativeProject:
            return self._project
        if model is ProjectContent:
            return self._content
        return None

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True


@pytest.fixture()
def capture_env(previs_session_factory, monkeypatch, tmp_path):
    """把 Asset Hub、异步会话与截图目录都换成可控替身（不碰真实存储）。"""
    state = {"project": object(), "content": ProjectContent(project_id="project-1", content_type="storyboard"), "session": None}

    @contextlib.asynccontextmanager
    async def _session():
        session = _FakeAsyncSession(state["project"], state["content"])
        state["session"] = session
        yield session

    monkeypatch.setattr(previs_api, "get_async_session", _session)
    monkeypatch.setattr(previs_api, "AssetHubFacade", _FakeAssetHubFacade)
    monkeypatch.setattr(previs_api, "_capture_dir", lambda: tmp_path / "previs-captures")
    _FakeAssetHubFacade.fail = False
    _FakeAssetHubFacade.last_call = {}
    return state


def _capture(client, scene_id: str, *, filename="previs-capture.png", camera_id="cam-1", payload=PNG_1PX):
    return client.post(
        f"/api/v1/previs/scenes/{scene_id}/capture",
        files={"file": (filename, payload, "image/png")},
        data={"camera_id": camera_id, "frame": "0"},
    )


def test_previs_capture_rejects_scene_without_storyboard_panel(previs_client, capture_env):
    """独立场景没有分镜面板可关联：明确拒绝，而不是建一个悬空关联。"""
    standalone = previs_client.post(
        "/api/v1/previs/scenes",
        json={"title": "独立场景", "scene": {"nodes": [], "cameras": []}},
    ).json()["data"]

    response = _capture(previs_client, standalone["id"])
    assert response.status_code == 400
    assert "未绑定项目分镜面板" in response.json()["detail"]
    assert capture_env["session"] is None  # 未触碰 Asset Hub


def test_previs_capture_rejects_unknown_camera(previs_client, capture_env):
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]

    response = _capture(previs_client, created["id"], camera_id="cam-does-not-exist")
    assert response.status_code == 400
    assert "不存在机位" in response.json()["detail"]


def test_previs_capture_rejects_unsupported_format(previs_client, capture_env):
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]

    response = _capture(previs_client, created["id"], filename="notes.txt")
    assert response.status_code == 400
    assert "格式不受支持" in response.json()["detail"]


def test_previs_capture_creates_asset_and_link_with_server_derived_provenance(previs_client, capture_env):
    """溯源必须由服务端从场景派生，而不是采信客户端。"""
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]
    scene_id = created["id"]

    # 先保存一次把 revision 推到 2 —— 若端点采信硬编码值，这里就会露馅
    saved = previs_client.put(
        f"/api/v1/previs/scenes/{scene_id}",
        json={"expected_revision": 1, "title": created["title"], "scene": created["scene"]},
    )
    assert saved.json()["data"]["revision"] == 2

    response = _capture(previs_client, scene_id)
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    assert data["asset_id"] == "asset-captured-1"
    assert data["linked"] is True
    assert data["link_error"] is None
    assert data["role"] == "storyboard_reference"
    assert data["content_id"] == "content-1"

    provenance = data["provenance"]
    assert provenance["source"] == "previs_capture"
    assert provenance["previs_scene_id"] == scene_id
    assert provenance["camera_id"] == "cam-1"
    assert provenance["scene_revision"] == 2              # 来自行上的 revision
    assert provenance["source_asset_ids"] == ["asset-1"]  # 来自场景节点的 assetId
    assert provenance["panel_number"] == 1

    # Asset Hub 收到的元数据与 lineage 都带同一份溯源
    call = _FakeAssetHubFacade.last_call
    assert call["asset_type"] == "image"
    assert call["source"] == "previs_capture"
    assert call["metadata"]["scene_revision"] == 2
    assert call["lineage"]["project_id"] == "project-1"
    # 文件确实落盘且内容与上传一致
    written = Path(call["file_path"])
    assert written.exists() and written.read_bytes() == PNG_1PX

    # 关联记录：role/relation/content 正确，metadata 是同一份溯源
    links = [item for item in capture_env["session"].added if isinstance(item, ProjectAssetLink)]
    assert len(links) == 1
    link = links[0]
    assert (link.role, link.relation) == ("storyboard_reference", "derived_from")
    assert link.project_id == "project-1"
    assert link.content_id == "content-1"
    assert json.loads(link.metadata_json)["previs_scene_id"] == scene_id
    assert capture_env["session"].committed is True


def test_previs_capture_reports_partial_failure_without_fake_success(previs_client, capture_env):
    """上传成功但关联失败：返回 linked=false + 可重试信息，且不留半成品关联。"""
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]
    capture_env["project"] = None  # 项目不存在 → 关联阶段抛错（此时资产已入库）

    response = _capture(previs_client, created["id"])
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    assert data["asset_id"] == "asset-captured-1"  # 资产确实已入库
    assert data["linked"] is False
    assert data["link_error"]
    assert data["retry_hint"]
    assert "asset-captured-1" in data["retry_hint"]  # 重试需要它
    assert [item for item in capture_env["session"].added if isinstance(item, ProjectAssetLink)] == []


def test_previs_capture_upload_failure_creates_nothing(previs_client, capture_env):
    """上传失败：既不产生资产也不产生关联，直接报错。"""
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]
    _FakeAssetHubFacade.fail = True

    response = _capture(previs_client, created["id"])
    assert response.status_code == 503
    assert "截图入库失败" in response.json()["detail"]
    assert capture_env["session"].added == []


def test_previs_capture_missing_scene_returns_404(previs_client, capture_env):
    response = _capture(previs_client, "no-such-scene")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 批量参考帧导出（Phase 4 阶段 A：ZIP / 阶段 B：服务端合成）
#
# 这一组测试固定的是**契约里最容易写错、又最难事后发现**的两点：
# 1. 帧的编号与真实帧号的映射（step>1 时文件名必须仍连续，否则 ffmpeg 读不了序列）；
# 2. 合成失败与入库失败要分开报告（视频产出了就不能算白跑）。
# ---------------------------------------------------------------------------

#: 帧内容不参与解析（端点只按扩展名校验、原样落盘），任意字节足以验证"原样"。
JPEG_BYTES = b"\xff\xd8\xff\xe0previs-frame\xff\xd9"


class _FakeTask:
    def __init__(self, task_id: str, task_type: str, payload: dict) -> None:
        self.task_id = task_id
        self.task_type = task_type
        self.payload = payload
        self.status = TaskStatus.PENDING
        self.progress = 0
        self.progress_message = ""
        self.result = None
        self.error = ""
        self.completed_at = None


class _FakeQueue:
    """只实现端点与后台任务用到的那四个方法。"""

    def __init__(self) -> None:
        self.tasks: dict[str, _FakeTask] = {}
        self.progress_calls: list[tuple] = []

    async def create_task(self, task_type: str, payload: dict, max_retries: int = 2):
        task = _FakeTask(f"task-{len(self.tasks) + 1}", task_type, payload)
        self.tasks[task.task_id] = task
        return task

    async def update_progress(self, task_id: str, progress: int, message: str = "") -> None:
        task = self.tasks[task_id]
        task.progress = progress
        task.progress_message = message
        self.progress_calls.append((task_id, progress, message))

    async def get_task(self, task_id: str):
        return self.tasks.get(task_id)

    async def update_task(self, task) -> None:
        self.tasks[task.task_id] = task


class _FakeFFmpegService:
    calls: list[dict] = []
    fail = False

    async def images_to_video(self, frames_dir, output_path, **kwargs):
        type(self).calls.append({"frames_dir": frames_dir, "output_path": output_path, **kwargs})
        if type(self).fail:
            raise RuntimeError("ffmpeg exploded")
        Path(output_path).write_bytes(b"fake-mp4")
        return output_path


@pytest.fixture()
def export_env(previs_session_factory, capture_env, monkeypatch, tmp_path):
    """导出端点外围：工作目录、任务队列、ffmpeg 全部换成可控替身。"""
    queue = _FakeQueue()
    monkeypatch.setattr(previs_api, "_export_root", lambda: tmp_path / "previs-exports")
    monkeypatch.setattr(previs_api, "get_task_queue", lambda: queue)
    monkeypatch.setattr(previs_api, "get_ffmpeg_service", lambda: _FakeFFmpegService())
    _FakeFFmpegService.calls = []
    _FakeFFmpegService.fail = False
    return {"queue": queue, "tmp_path": tmp_path}


def _export_frames(client, scene_id: str, *, count=3, step=1, start_frame=0, fps=24, suffix=".jpg", camera_id="cam-1"):
    files = [("files", (f"{index}{suffix}", JPEG_BYTES, "image/jpeg")) for index in range(count)]
    return client.post(
        f"/api/v1/previs/scenes/{scene_id}/export-frames",
        files=files,
        data={"fps": str(fps), "start_frame": str(start_frame), "step": str(step), "camera_id": camera_id},
    )


def _export_video(client, scene_id: str, *, count=3, step=1, start_frame=0, fps=24, camera_id="cam-1"):
    files = [("files", (f"{index}.jpg", JPEG_BYTES, "image/jpeg")) for index in range(count)]
    return client.post(
        f"/api/v1/previs/scenes/{scene_id}/export-video",
        files=files,
        data={"fps": str(fps), "start_frame": str(start_frame), "step": str(step), "camera_id": camera_id},
    )


def test_export_frames_returns_zip_with_continuous_numbering(previs_client, export_env):
    """文件名连续（给 ffmpeg 读序列），真实帧号进 manifest（给人和剪辑软件读）。"""
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]
    scene_id = created["id"]
    previs_client.put(
        f"/api/v1/previs/scenes/{scene_id}",
        json={"expected_revision": 1, "title": created["title"], "scene": created["scene"]},
    )

    response = _export_frames(previs_client, scene_id, count=3, step=2, start_frame=10, fps=24)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["X-Previs-Frame-Count"] == "3"

    import io as _io
    import zipfile as _zipfile

    with _zipfile.ZipFile(_io.BytesIO(response.content)) as archive:
        names = sorted(archive.namelist())
        # step=2 时真实帧号是 10/12/14，但文件名必须仍是连续的 0001/0002/0003
        assert names == [
            "frames/frame_0001.jpg",
            "frames/frame_0002.jpg",
            "frames/frame_0003.jpg",
            "manifest.json",
        ]
        assert archive.read("frames/frame_0001.jpg") == JPEG_BYTES
        manifest = json.loads(archive.read("manifest.json"))

    assert manifest["source"] == "previs_frame_export"
    assert manifest["scene_id"] == scene_id
    assert manifest["scene_revision"] == 2          # 服务端从行上派生
    assert manifest["camera_id"] == "cam-1"
    assert manifest["panel_number"] == 1
    assert manifest["fps"] == 24
    assert manifest["frame_count"] == 3
    assert manifest["span_frames"] == 5             # (3-1)*2+1
    assert [item["frame"] for item in manifest["frames"]] == [10, 12, 14]
    assert manifest["frames"][2]["time"] == pytest.approx(14 / 24, abs=1e-4)
    assert manifest["source_asset_ids"] == ["asset-1"]


def test_export_frames_rejects_non_jpeg(previs_client, export_env):
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]

    response = _export_frames(previs_client, created["id"], suffix=".png")
    assert response.status_code == 400
    assert "格式不受支持" in response.json()["detail"]


def test_export_frames_rejects_too_many_frames(previs_client, export_env, monkeypatch):
    """上限是硬约束：它也决定了一次 multipart 的体积。"""
    monkeypatch.setattr(previs_api, "EXPORT_MAX_FRAMES", 2)
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]

    response = _export_frames(previs_client, created["id"], count=3)
    assert response.status_code == 400
    assert "最多导出 2 帧" in response.json()["detail"]


def test_export_frames_rejects_unknown_camera(previs_client, export_env):
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]

    response = _export_frames(previs_client, created["id"], camera_id="cam-nope")
    assert response.status_code == 400
    assert "不存在机位" in response.json()["detail"]


def test_export_frames_missing_scene_returns_404(previs_client, export_env):
    assert _export_frames(previs_client, "no-such-scene").status_code == 404


def test_export_video_composes_and_imports_asset(previs_client, export_env, capture_env):
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]
    scene_id = created["id"]

    response = _export_video(previs_client, scene_id, count=3, start_frame=0, fps=24)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["frame_count"] == 3
    assert data["fps"] == 24
    assert data["scene_revision"] == 1

    # TestClient 会等 BackgroundTasks 跑完，因此这里可以直接断言合成结果
    task = export_env["queue"].tasks[data["task_id"]]
    assert task.status == TaskStatus.DONE
    assert task.result["frame_count"] == 3
    assert task.result["asset_id"] == "asset-captured-1"
    assert task.result["asset_error"] == ""

    call = _FakeFFmpegService.calls[0]
    assert call["fps"] == 24
    assert call["pattern"] == "frame_%04d.jpg"
    assert call["start_number"] == 1
    assert Path(call["output_path"]).name == "previs-export.mp4"

    # Asset Hub 拿到的是视频类型与同一份溯源
    asset_call = _FakeAssetHubFacade.last_call
    assert asset_call["asset_type"] == "video"
    assert asset_call["source"] == "previs_frame_export"
    assert asset_call["metadata"]["previs_scene_id"] == scene_id
    assert asset_call["metadata"]["fps"] == 24
    assert asset_call["lineage"]["project_id"] == "project-1"


def test_export_video_cleans_frames_after_success(previs_client, export_env, capture_env):
    """帧序列是中间产物，合成成功后不该留几十 MB 残留。"""
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]
    _export_video(previs_client, created["id"], count=2)

    frames_dir = Path(_FakeFFmpegService.calls[0]["frames_dir"])
    work_dir = frames_dir.parent
    assert frames_dir.name == "frames"
    assert (work_dir / "previs-export.mp4").exists()
    assert (work_dir / "manifest.json").exists()
    assert not frames_dir.exists()


def test_export_video_failure_marks_task_failed_and_keeps_frames(previs_client, export_env, capture_env):
    """合成失败：任务标 failed、错误如实上报，且**保留帧序列**便于排查。"""
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]
    _FakeFFmpegService.fail = True

    response = _export_video(previs_client, created["id"], count=2)
    assert response.status_code == 200, response.text
    task = export_env["queue"].tasks[response.json()["data"]["task_id"]]

    assert task.status == TaskStatus.FAILED
    assert "视频合成失败" in task.error
    frames_dir = Path(_FakeFFmpegService.calls[0]["frames_dir"])
    assert frames_dir.exists()                     # 保留现场
    assert list(frames_dir.glob("frame_*.jpg"))
    assert not (frames_dir.parent / "previs-export.mp4").exists()


def test_export_video_keeps_success_when_asset_import_fails(previs_client, export_env, capture_env):
    """视频已产出、入库失败：任务仍是成功，但 `asset_error` 如实标注。"""
    created = previs_client.post("/api/v1/previs/scenes", json=_create_payload()).json()["data"]
    _FakeAssetHubFacade.fail = True

    response = _export_video(previs_client, created["id"], count=2)
    task = export_env["queue"].tasks[response.json()["data"]["task_id"]]

    assert task.status == TaskStatus.DONE
    assert task.result["asset_id"] == ""
    assert "asset hub unavailable" in task.result["asset_error"]
