# Local UniRig Rigging Service

Split local UniRig inference out of the cloud rigging change and track it as an independent infrastructure and inference-service change.

## Why

Local UniRig needs Docker, NVIDIA runtime, CUDA/torch, multi-GB weights, and a long-running inference process. The existing cloud rigging change is already delivered and should not carry a separate platform project with different deployment and acceptance requirements.

## What Changes

- Define the local UniRig sidecar HTTP contract, health check, queue, progress, timeout, and failure diagnostics.
- Pin the upstream source, model version, weights source, and license. Weights must not be committed.
- Add an explicit local UniRig option in the 3D workspace when the service is healthy.
- Reuse the existing task ledger, asset ingestion, preview, metadata extraction, and viewer paths.
- Validate the complete flow on a real NVIDIA GPU.

## Non-goals

- Replacing the existing Tencent cloud rigging connector.
- Pretending local inference works on machines without a supported GPU.
- Committing model weights or a GPU image into Git.
- Migrating TripoSR in this change; that has its own change.

## Impact

- Backend: local service adapter, connector/backend selection, task state, and diagnostics.
- Infrastructure: Dockerfile/Compose, CUDA version, weight volume, and health checks.
- Frontend: local UniRig entry and unavailable-state messaging.
- Tests: contract tests plus real-GPU end-to-end acceptance.
