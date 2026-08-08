# Design: Creative Project Writing Guardrails

`GET /api/v1/creative-projects/{project_id}/writing-preflight` is a read-only projection over persisted project state. It does not create a context snapshot and does not call a model.

The response contains:

- normalized `stage` and `chapter_number`;
- ordered checks with `pass` or `block` status;
- `ready`, `blockers` and a human-actionable `next_action`;
- the available chapter-outline source id;
- compatible creative Skill method packages and their checksums.

The generation methods remain authoritative. A future UI can call preflight before enabling a button, while an Agent can use the same contract to explain and repair a blocked workflow.

The initial `chapter-hook-rhythm` Skill is opt-in (`auto_apply=false`). It contributes method guidance to T6 only when selected in project settings, and its prohibited mutations preserve the existing candidate/canon boundary.
