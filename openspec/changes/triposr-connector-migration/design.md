# Design: TripoSR Connector Migration

## Current state

- Model3DConnectorBackend already reads AIConnector request and response templates and supports submit, poll, download, and diagnostics.
- Model3DService.generate_3d_from_image still reads TRIPOSR_API_KEY and TRIPOSR_API_BASE and directly calls upload, task submit, and task status endpoints.
- As a result, TripoSR does not appear in the 3D connector list and does not reuse unified timeout, diagnostics, or model selection.

## Migration shape

### Target contract

Add a TripoSR preset that maps current behavior to connector fields:

- Base URL from TRIPOSR_API_BASE.
- API key from TRIPOSR_API_KEY using the existing credential storage path.
- Upload a local image first and obtain an image URL.
- Submit returns task_id.
- Poll returns status, progress, result.model_url, and error.
- On completion, download the model and use the existing asset ingestion path.

If the generic connector cannot express the upload-then-submit flow, extend only the generic contract. Do not keep a TripoSR-specific path in business routes.

### Legacy configuration migration

Provide an explicit operator script or one-time command:

1. Discover TRIPOSR environment variables.
2. Dry-run shows the connector name, base URL, and whether a key exists.
3. Apply writes an AIConnector record without printing the key.
4. Repeated apply is idempotent and does not overwrite manual non-empty fields.

### Cutover

1. Create and validate the connector record first.
2. Switch image-to-3D routing to the unified backend.
3. After regression passes, delete legacy TripoSR methods and environment branches from Model3DService.

During cutover there is still only one runtime path. If the connector record is missing, return a readable error and do not silently fall back to environment variables.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Generic connector cannot express multipart upload | Migration stalls | Extend the generic contract and add contract tests |
| Migration loses a secret | Service outage | Dry-run, explicit apply, report only whether a key exists |
| Legacy code is removed before configuration exists | Image-to-3D stops working | Migrate configuration before cutover; return a clear missing-connector error |
| Provider response fields change | Polling fails | Keep all mappings in response_config and record diagnostics |
