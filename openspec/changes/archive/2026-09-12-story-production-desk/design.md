# Design: Story Production Desk

## Ownership

The desk is a presentation layer over existing authoritative records:

```text
CreativeProject.outline / chapter_plan
  + ProjectContent (detail, prose, script, storyboard)
  + Writer Room candidate/review content
  + ProjectAssetLink
  -> /story production desk
```

The desk does not persist an independent stage status. Completion is calculated at render time from the same project-scoped resources already loaded by `/story`.

## Interaction Model

1. The compact header selects configured text/image models and opens project setup actions.
2. The project header exposes project identity, the primary Agent advance action and export.
3. The stage rail displays real counts and opens the appropriate existing workspace tab.
4. Batch production remains available behind a compact disclosure. It retains dependency order, skip-existing behavior and failure retry semantics.
5. Episode workbench remains the execution surface. Follow-up work may reorganize its existing controls, but must reuse `ProjectAssetLink`, content versions, task records and generation logs.

## Completion Rules

- Story blueprint: a non-empty persisted outline.
- Project setting: at least one project-bible or world-asset content record.
- Chapter plan: a non-empty persisted chapter plan.
- Episode production: the count of latest chapter outline, approved prose, script and storyboard records divided by planned chapters times four.
- Writing review: chapters with persisted `prose_review` candidates relative to chapters with approved prose.
- Relationship and delivery: at least one project-linked asset; the rail labels the actual asset-link count.

Counts are status indicators only. They never promote candidates, mark a production run successful, or imply provider cost.
