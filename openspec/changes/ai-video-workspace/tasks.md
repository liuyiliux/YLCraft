# Tasks

## Phase 1: Durable standalone video workspace

- [x] 1. Add a durable `VideoGenerationTask` ledger with request/result, status, Asset Hub and optional project provenance.
- [x] 2. Return async provider task ids immediately instead of blocking the workspace request.
- [x] 3. On terminal poll, import a local video into Asset Hub exactly once and retain project lineage.
- [x] 4. Add video history API and restore it in `/video-gen` after refresh.
- [x] 5. Display Asset Hub state and provide direct navigation from the workspace result.

## Phase 2: Provider and capability integrity

- [ ] 6. Expose provider-specific video capability constraints in the workspace and disable unsupported controls.
- [ ] 7. Verify one configured real provider from submit through Asset Hub playback.
- [ ] 8. Add focused backend/API tests and frontend external-Chrome smoke.

## Phase 3: Documentation

- [ ] 9. Regenerate API surface and update system architecture after the contract is verified.
