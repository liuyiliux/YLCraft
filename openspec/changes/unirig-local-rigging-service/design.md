# Design: Local UniRig Rigging Service

## Current state

- Cloud rigging already runs through AIConnector and a Tencent TC3 connector.
- UniRig has only a route-B planning note. There is no runnable service, container, weight management, or workspace entry.
- There is no unified probe for local GPU availability, so the UI cannot safely show a button that is guaranteed to work.

## Deferred decision (2026-09-25)

The user has deferred UniRig because the current machine has only 6GB VRAM and a supported GPU is not in the current budget. Phase 1 (upstream facts, sidecar contract, and connector mapping) is complete and should remain as the durable plan. Do not start Phase 2 implementation, Docker images, weight downloads, or workspace UI work until a supported GPU host is available. Reopen this change only when the user confirms an 8GB-or-higher NVIDIA GPU (more VRAM is preferable for the two-stage pipeline) and the Docker Linux engine can run on that host.

## Pinned upstream facts (2026-09-25)

These facts come from the upstream repository, Hugging Face model card/API, and the local machine probe. Unverified items remain explicit instead of being treated as known.

| Item | Pinned value | Evidence |
|---|---|---|
| Code revision | `VAST-AI-Research/UniRig@6793c6640ff01c8fb389f3993434124bb43d2933` (`main`, 2026-06-04) | GitHub `git ls-remote` and commit API |
| Source license | MIT (`Copyright (c) 2025 VAST-AI-Research and contributors`) | Upstream `LICENSE` |
| Model repository | `VAST-AI/UniRig`, revision `36842e2b5947e9e60f89275b83208c8e74071c63`, license field `mit` | Hugging Face model API/card |
| Skeleton checkpoint | `skeleton/articulation-xl_quantization_256/model.ckpt`, 1,439,617,174 bytes, SHA-256 `d8cf9b42d56e7bc316d293597ecf8c4c39a8631cdd44a261ecf388242fabd0f4` | Hugging Face LFS metadata and upstream quick-inference config |
| Skinning checkpoint | `skin/articulation-xl/model.ckpt`, 4,375,464,854 bytes, SHA-256 `9d40cf42fb9d4c10d8b373d9f4f557c6fbbc5ebacae7ae6b3dce5a0d8a18bc33` | Hugging Face LFS metadata and upstream quick-inference config |
| Alternates not chosen by default | `skeleton/rignet/model.ckpt`, 621,660,032 bytes, SHA-256 `e68121ed9ef1ad8bd396c51e8c5e985048e45951d7e4be740b44723653659c45` | Hugging Face LFS metadata. The quick Articulation-XL route is the default target; RigNet remains a fallback only if the Articulation-XL route is blocked. |
| Runtime prerequisites | Python 3.11, PyTorch tested with `>=2.3.1`, CUDA GPU, at least 8GB VRAM for generation | Upstream README and Hugging Face card |
| Dependency risk | Upstream requires compiled CUDA/PyTorch ecosystem packages such as `flash_attn`, `spconv`, `torch_scatter`, and `torch_cluster`; exact wheel/CUDA combinations are not pinned upstream | Upstream installation instructions; container matrix is still unverified |
| Full Hugging Face repository size | 11,472,503,676 bytes including datasets; only the two runtime checkpoints above may be downloaded for the service | Hugging Face API |
| Current local machine | `NVIDIA GeForce RTX 3060 Laptop GPU`, 6,144 MiB VRAM, driver 561.09, compute capability 8.6 | `nvidia-smi` on this machine |
| Docker runtime state | Docker client 29.0.1 is installed, but the Docker Desktop Linux engine is not running | `docker version` / `docker info` on this machine |

**Hardware conclusion:** the current machine is below the official 8GB minimum. Phase 2 implementation may be prepared as source and contract tests, but real inference and end-to-end acceptance must not be claimed until a machine with at least 8GB VRAM is available and the full two-stage pipeline is measured there. The skinning training documentation mentions much larger memory needs, but this change uses inference checkpoints only; inference peak memory remains unverified.

**Unverified items:**

- Actual peak VRAM, elapsed time, and maximum practical mesh size on an 8GB GPU.
- Exact working CUDA, PyTorch, `flash_attn`, `spconv`, `torch_scatter`, and `torch_cluster` wheel set.
- Whether an 8GB card can run skeleton and skinning stages safely with the default upstream settings without device cleanup between stages.
- Docker image digest and reproducibility on Windows and Linux hosts.
- Whether there is a stable upstream release tag; no tag was present at the reviewed revision, so the commit hash is the pin.

## Target architecture

3D workspace to YLCraft Model3D service to local UniRig connector to local HTTP sidecar to CUDA and UniRig weights.

### Sidecar contract

The first version provides:

- `GET /health`: `service_version`, `model_version`, `status`, CUDA/GPU facts, free VRAM, whether weights are loaded, queue depth, and the maximum concurrency. Returns `503` with a structured error when the service cannot accept jobs.
- `POST /jobs`: accepts a job request with a relative input file under the configured input root, `mode` (`skeleton`, `skin`, or `full`), `output_format`, `seed`, and `faces_target_count`; returns `202` with `job_id` and `pending` state.
- `GET /jobs/{job_id}`: returns `pending`, `processing`, `done`, or `error`, plus `progress`, `stage`, `result_url`, `result_sha256`, and a structured error. Cancellation is represented as `error` with `error.code = cancelled` so the existing YLCraft task states do not need a parallel state machine.
- `POST /jobs/{job_id}/cancel`: requests cancellation. A terminal job returns `409`; an active job moves to the cancelled error state.
- `GET /jobs/{job_id}/result`: streams the completed model only when the job is `done`; the response includes `ETag` equal to the result SHA-256.

The shared file contract is:

```text
<UNIRIG_SHARED_DIR>/
  input/<job_id>.<ext>       # YLCraft writes, sidecar reads
  output/<job_id>/<name>.glb # sidecar writes
  output/<job_id>/<name>.fbx
  weights/                   # downloaded checkpoints, never committed
  tmp/                       # scratch space owned by the sidecar
```

`UNIRIG_SHARED_DIR` defaults to `storage/unirig` in a source checkout and is mounted at `/data/unirig` in the container. Input and output paths in JSON are relative to this root. The sidecar resolves them, rejects absolute paths, `..`, and symlink escapes, and never embeds binary payloads in JSON. YLCraft also validates the resolved result path before copying it into the existing model storage. Successful results are written through a temporary sibling file and atomically renamed; incomplete files must never appear as `done`.

The error object is:

```json
{
  "error": {
    "code": "gpu_unavailable",
    "message": "readable operator-facing reason",
    "detail": {}
  }
}
```

Initial error codes are `invalid_request`, `path_out_of_root`, `gpu_unavailable`, `weights_missing`, `queue_full`, `queue_timeout`, `job_timeout`, `out_of_memory`, `worker_lost`, `cancelled`, `result_missing`, and `provider_error`.

The first version uses concurrency `1`, maximum queued jobs `2`, a `300` second queue timeout, a `1800` second job timeout, a `15` second worker heartbeat, and a `60` second stale-heartbeat threshold. These are defaults, not benchmark claims; Phase 2 must make them configurable and record the measured values from the first supported GPU.

### YLCraft integration

- Service selection is explicit. The connector declares capability=rigging and a local endpoint type; it must not reuse cloud TC3 signing fields.
- A failed health check blocks submission and shows a readable reason.
- The existing task ledger stores owner, provider, source asset, state, and diagnostics. Do not create a UniRig-only task table.
- Results enter the existing asset ingestion, Blender preview, metadata extraction, and viewer paths.

The connector mapping uses the existing AIConnector fields:

| AIConnector field | Local UniRig value |
|---|---|
| `provider_type` | `3d` |
| `api_format` | `custom` |
| `base_url` | `http://127.0.0.1:8190` by default; operator-overridable and bound to loopback unless a trusted network boundary is configured |
| `api_endpoint` | `/jobs` |
| `default_model` | `unirig-articulation-xl-2.0` |
| `available_models` | `["unirig-articulation-xl-2.0"]` |
| `timeout` | `30` seconds for submit and poll HTTP calls; this is not the inference timeout |
| `response_config.capability` | `rigging` |
| `response_config.health_endpoint` | `/health` |
| `response_config.poll_endpoint` | `/jobs/{task_id}` |
| `response_config.task_id_path` | `$.job_id` |
| `response_config.status_path` | `$.state` |
| `response_config.progress_path` | `$.progress` |
| `response_config.model_url_path` | `$.result.url` |
| `response_config.error_path` | `$.error.message` |
| `response_config.done_values` | `["done"]` |
| `response_config.failed_values` | `["error"]` |
| `response_config.poll_interval` | `5` seconds |
| `response_config.local_service` | `true` |
| `response_config.shared_root` | `storage/unirig` by default |

For local submissions the existing rigging route must pass the already-resolved local model path as a relative shared-volume path. It must not require COS, a public `/model3d-files` URL, or a cloud-style `FileType`/`MotionType` payload. The local connector's request template forwards `source_path`, `mode`, `seed`, `faces_target_count`, and `output_format`; secrets and cloud TC3 fields stay empty. The local route has no cloud fallback: a health or submission failure is returned to the user.

## Operational constraints

- Pin source, image tag, and weights version. Record source and license. Keep weights on a host volume or object storage, never in Git.
- Check GPU capability at startup. CUDA or driver mismatch must fail fast.
- Timeouts, out-of-memory errors, and service restarts must produce readable diagnostics and must not leave jobs pending forever.
- Enforce a concurrency limit and queue policy so multiple large jobs do not exhaust GPU memory.
- The UI derives availability from the real health check, not from a build-time constant.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| CUDA, torch, or driver mismatch | Service fails to start or fails at runtime | Pin versions, startup self-check, record driver/GPU facts |
| Unclear weights license | Cannot safely distribute | Verify source and license first; document download only |
| Insufficient GPU memory | Failed or unstable jobs | Concurrency limit, timeout, readable errors, queue state |
| Two rigging paths behave differently | Users cannot choose reliably | Explicit provider capability and shared task/ingest paths |
| Silent fallback to cloud | Cost and privacy boundary is lost | No cross-provider fallback; show the local failure |
