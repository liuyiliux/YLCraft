# Design: AI Video Workspace

## Ownership

```text
Video workspace request
  -> provider task
  -> VideoGenerationTask (durable request/result ledger)
  -> local video file
  -> Asset Hub Node/Version/Representation
  -> optional ProjectAssetLink
```

`VideoGenerationTask` is the workspace execution ledger. It is not a second
asset model: finished media remains canonical in Asset Hub, where the existing
three-layer model stores file, duration/format, prompt/model parameters, tags
and lineage.

## Async Contract

`POST /api/v1/videos/generate` submits an asynchronous provider task and
returns its task id without waiting for the provider's full generation time.
`GET /api/v1/videos/tasks/{task_id}` owns polling. On the first terminal
success with a local file it imports the output into Asset Hub and saves the
resulting `asset_id`; subsequent polls are idempotent. `GET /videos/history`
restores records for the independent workspace after refresh.

## Asset Hub Closure

Every completed video records provider, model, prompt, seed, duration,
resolution, aspect ratio, audio preference and reference-asset ids in Asset
Hub metadata/version params. A project-originated job additionally creates the
existing `ProjectAssetLink(output -> derived_from)` relation. Standalone jobs
remain usable assets without requiring a project.
## Configured provider adapters

Video workspaces load enabled `AIConnector(provider_type="video", api_format="custom")` records through `GenericVideoBackend`. The connector explicitly declares its request template and task response contract (`task_id_path`, status/result paths, request headers and polling endpoint); adding a provider must not depend on a hard-coded backend class. This permits DashScope Wan and future configured providers to appear in `/video-gen` after connector reload.

When a connector declares `default_params.video_capabilities`, `/api/v1/videos/backends` returns its supported modes and constraints: text/image-to-video, seed/audio controls, resolutions, aspect ratios, durations and maximum duration. `/video-gen` disables unsupported modes and controls, then resets incompatible selections on connector change. The generation API validates the same declared constraints and returns `422` for incompatible direct requests. Older generic connectors without this optional block remain permissive until their owner explicitly describes provider limits.

Agnes Video V2.0 is configured against the official China gateway
`https://api.agnes-ai.cn` with `POST /v1/videos`, `task_id_path=$.video_id`,
`poll_endpoint=/agnesapi?video_id={task_id}`, `status_path=$.status` and
`video_url_path=$.metadata.url`. Generic templates expose numeric `width`,
`height`, `fps` and `num_frames` values; the latter follows the 8n+1 frame
contract. Agnes text-to-video can therefore use the connector directly.

Agnes image-to-video accepts only a publicly reachable image URL. Asset Hub
representations and browser uploads resolve to local paths/data URIs in the
current workspace, so they MUST NOT be sent to Agnes as `image` until a public
object-storage or media-proxy publishing path is configured. The connector UI
only provides the verified text-to-video preset and states this boundary.
