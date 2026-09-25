# TripoSR Connector Migration

Move legacy TripoSR image-to-3D generation onto the configuration-driven AIConnector and Model3DConnectorBackend path.

## Why

Image-to-3D currently has two semantics. New providers use AIConnector configuration, while TripoSR still reads TRIPOSR environment variables in Model3DService and performs direct HTTP submit and poll calls. This duplicates adapters, produces inconsistent diagnostics, hides provider configuration from the connector UI, and risks leaving routes pointed at a removed legacy path.

## What Changes

- Inventory the current TripoSR callers, environment variables, request fields, poll fields, and asset ingestion path.
- Represent TripoSR submit, poll, download, and error mapping through the connector contract.
- Add an explicit one-time migration tool or command that imports existing TRIPOSR environment configuration into AIConnector records.
- Switch image-to-3D routing to Model3DConnectorBackend.
- Remove the legacy TripoSR branch and duplicate HTTP code after cutover so only one runtime path remains.

## Non-goals

- Changing the existing image-to-3D HTTP endpoints, frontend workspace, or asset ingestion semantics.
- Adding a new provider.
- Implementing local UniRig; that is a separate change.
- Mutating database configuration during application startup.

## Impact

- Backend: Model3DService, Model3DConnectorBackend, and connector migration configuration.
- Tests: request/poll/error mapping, legacy configuration migration, and readable failure when the connector is missing.
- Docs: connector preset, migration command, and rollback notes.
