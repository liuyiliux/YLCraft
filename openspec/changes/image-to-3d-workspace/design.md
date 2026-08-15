# Design

- A connector has explicit `provider_type: "3d"`; endpoint names never imply capability.
- Connector request/response configuration describes JSON request rendering, task ID/status/model URL JSONPaths, optional request/poll headers, an optional polling endpoint, and an optional poll cadence via `response_config.poll_interval` (seconds). The settings UI routes this type through `custom` generic HTTP or the `tencent_tc3` TC3-HMAC-SHA256 signing option (`SecretId:SecretKey`), never through an OpenAI SDK preset.
- `/api/v1/model-3d` owns standalone backend discovery, submit, poll and durable history. The workspace selects from active `provider_type: "3d"` connectors and their advertised models; no provider name is hard-coded into the workflow. `/backends` exposes each connector's `poll_interval`, and the workspace page polls pending tasks at their provider's declared interval instead of a fixed timer.
- The input can be an uploaded image or an Asset Hub image. Asset inputs retain `source_asset_id` and are materialized only for the connector request; completed outputs remain linked with `derived_from` lineage.
- Durable task ids are local short ids. Opaque provider ids are retained in `result_json.provider_task_id` for polling, so provider-specific encoded ids cannot exceed the ledger primary-key limit.
- `model3d_generation` records also join the global task-center aggregation alongside video generation tasks.
- Submit, poll and download diagnostics retain redacted request headers/body, endpoint, HTTP status and a bounded response excerpt. A polling transport failure is persisted as an error record so durable history does not remain falsely pending.
- Completed model URLs download locally, then create `AssetNode(3d_model) -> AssetVersion -> AssetRepresentation` exactly once. When the input was an Asset Hub image, an `AssetRelation(derived_from)` records lineage.
- Providers that return multiple formats declare `result_files_path` + `prefer_model_type`; the workspace prefers that type (default `GLB`) and unpacks ZIP archives before importing, so a packed archive is never stored as a model file.
- When the stored result is an OBJ model (obj + mtl + 贴图), the asset keeps the sibling files and `/api/v1/assets/{asset_id}/files/{filename}` serves them, so the frontend `MTLLoader` can resolve materials and textures by relative path and render the model with color.
- The existing `/api/v1/3d` TripoSR and utility routes stay compatible but are not extended by this workspace.
- GLB is the default expected output. Format conversion and server-rendered preview remain out of scope until a real conversion/rendering backend exists.
