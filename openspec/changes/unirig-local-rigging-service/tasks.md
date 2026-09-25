# Tasks

## Phase 1: Facts and contract

- [x] 1. Pin the UniRig upstream revision, weights source, license, and minimum GPU, memory, and driver requirements. List unverified items explicitly.
  - _2026-09-25 pinned: code `VAST-AI-Research/UniRig@6793c6640ff01c8fb389f3993434124bb43d2933` (MIT); model `VAST-AI/UniRig@36842e2b5947e9e60f89275b83208c8e74071c63` (MIT). Default checkpoints and SHA-256 values are recorded in `design.md`: skeleton articulation-xl 1,439,617,174 bytes and skin 4,375,464,854 bytes. Upstream requires Python 3.11, PyTorch >=2.3.1, CUDA, and at least 8GB VRAM. The current machine has an RTX 3060 Laptop 6,144 MiB and Docker Desktop is not running, so real GPU acceptance remains impossible here. Exact dependency wheels, peak VRAM, latency, and safe mesh size remain explicitly unverified._
- [x] 2. Define the sidecar health, job, poll, and result contract: states, error codes, timeout, and shared file directory.
  - _2026-09-25 contract fixed in `design.md`: health, submit, poll, cancel, and result endpoints; `pending/processing/done/error` states with cancellation represented by `error.code=cancelled`; structured error codes; relative-path-only shared input/output root; atomic result publication; concurrency 1 and queue 2; configurable 300s queue timeout, 1800s job timeout, 15s heartbeat, and 60s stale-worker threshold. These defaults still require measurement on supported hardware._
- [x] 3. Confirm YLCraft connector fields for local endpoint, timeout, concurrency, model version, and result path. Do not reuse cloud secret fields.
  - _2026-09-25 mapping fixed in `design.md`: existing AIConnector fields cover `provider_type=3d`, `api_format=custom`, loopback `base_url`, `/jobs`, default model `unirig-articulation-xl-2.0`, a 30s control-plane timeout, poll paths, and `$.result.url`. Local submission requires a relative shared-volume `source_path`; it must not require COS, a public model URL, TC3 signing, or any cloud secret. The actual caller change remains Phase 3._

## Phase 2: Local service

**Deferred (2026-09-25):** the user has no supported GPU in the current budget. Keep tasks 4-13 unchecked and do not ship a contract-only runtime or download multi-GB weights. Resume when an 8GB-or-higher NVIDIA GPU host is available.

- [ ] 4. Add the containerized UniRig service with Dockerfile/Compose, CUDA base image, weights volume, and GPU self-check.
  - _2026-09-25 blocker recorded: source and contract can be prepared, but this machine is below the official 8GB VRAM minimum and its Docker Linux engine is not running. Do not claim the service is runnable here; finish the container only when a supported GPU host is available or explicitly accept contract-only work as a separate slice._
- [ ] 5. Implement the HTTP sidecar: health, submit, poll, cancel/timeout, structured errors, and concurrency limit.
- [ ] 6. Run one minimal input to output after real NVIDIA GPU verification and record driver/CUDA/torch/memory facts and elapsed time.
  - _2026-09-25 not run: 6GB VRAM is below the official minimum. Required evidence remains a real supported GPU run; mocks or a 6GB failure cannot complete this task._

## Phase 3: YLCraft integration

- [ ] 7. Add the local UniRig connector/backend adapter and map sidecar state into the existing 3D task ledger.
- [ ] 8. Feed output models into the existing asset ingestion, Blender preview, bone/animation metadata extraction, and viewer.
- [ ] 9. Add an explicit local UniRig entry in the 3D workspace. Health failure shows the reason and blocks submission; no automatic cloud fallback.
- [ ] 10. Add contract and failure-path tests: unreachable service, timeout, out of memory, malformed response.

## Phase 4: Acceptance and documentation

- [ ] 11. Real end-to-end acceptance: workspace selection, submit, progress, ingestion, and viewer open. Keep screenshots or artifact evidence.
- [ ] 12. Update architecture, API surface, connector examples, and operations docs with local versus remote GPU boundaries.
- [ ] 13. Run openspec validate unirig-local-rigging-service --strict.
