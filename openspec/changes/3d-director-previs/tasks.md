# Tasks

## Phase 0: Design and research

- [x] 1. Survey 3D director/previs references and record license boundaries in `F:\PycharmProjects\YLCraft-refs\README.md`.
- [x] 2. Define the product boundary: previs is a project-storyboard spatial layer, not a second Story page, Asset Hub, Canvas document, or DCC tool.
- [x] 3. Define `PrevisSceneDocument`, stable node/camera IDs, transforms, locks, revision, and future keyframe contract.
- [x] 4. Define the screenshot return path: active camera capture -> Asset Hub -> `ProjectAssetLink` -> storyboard panel -> existing image/video reference fields.
- [x] 5. Write design, requirements, acceptance criteria, and Phase 1 scope.

## Phase 1: Static director desk

- [x] 6. Add `PrevisSceneDocument` persistence, Alembic migration, API schemas, CRUD endpoints, focused backend tests, and API surface documentation.
- [x] 7. Add a 3D previs entry from `/story` storyboard panels; find or create scenes by project/content/panel identity.
- [x] 8. Extract or extend reusable 3D scene primitives from `Model3DViewer` without moving Story business state into the generic viewer.
- [x] 9. Implement Asset Hub model insertion, lightweight human proxies, primitives, panoramic/background references, layer visibility, rename, delete, and lock.
- [ ] 10. Implement director view, active camera view, camera CRUD, transform/FOV controls, safe frame, and rule-of-thirds overlays.
- [ ] 11. Capture the active camera to PNG/WebP, import it into Asset Hub with previs provenance, and link it to the originating storyboard panel as a selectable reference.
- [ ] 12. Verify captured references enter the existing storyboard image/video generation request path without duplicate content, assets, or task records.
- [ ] 13. Add desktop and narrow-screen UI validation, focused backend/frontend tests, and document the module/API changes.

## Phase 2: Dynamic previs

- [ ] 14. Add scene duration, 24fps playhead, transform and camera keyframes, slerp rotation interpolation, and persisted scene operation history.
- [ ] 15. Reuse existing rigged-model animation clips as scene playback selections without claiming editable skeletal animation.
- [ ] 16. Evaluate frame capture and MP4/WebM export only after static capture is stable; document browser and cost constraints.

## Phase 3: Agent director assistant

- [ ] 17. Add a read-only previs scene summary to Agent context with stable IDs and lock state.
- [ ] 18. Add a reviewed `PrevisOperation` Tool contract with expected revision, lock validation, confirmation diff, Agent Run trace, and focused authorization tests.

## Acceptance criteria for Phase 1

- [ ] 19. A storyboard panel can create, close, reload, and reopen the same previs scene.
- [ ] 20. A scene restores asset references, object/camera transforms, visibility, locks, and active camera after refresh.
- [ ] 21. Director and active-camera views show the same scene; safe frame and rule-of-thirds overlays remain view-only.
- [ ] 22. A camera capture creates an Asset Hub image with `previs_scene_id`, camera, revision, and source-asset provenance, then links it to the originating storyboard panel.
- [ ] 23. The linked capture can be selected by existing storyboard image/video generation flows without creating duplicate project content or task ledgers.
