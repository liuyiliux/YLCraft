# Design: Creative Writing Style Profiles

## Product model

The system has three separate layers:

1. `ProjectStyleMeasurement` is observed evidence from a particular approved prose
   version. It is immutable evidence and is not directly reusable as a prompt.
2. `WritingStyleProfile` is a reviewed abstraction assembled from measurements and
   model analysis. It contains rules, confidence, provenance and copyright limits.
3. `ProjectWritingStyleLink` binds a profile to a project, stage and intensity. The
   link is the runtime selection, not the profile itself.

The profile must never contain the full source novel. Source data is referenced by
snapshot/content IDs and hashes. Examples in a profile are newly generated examples,
not copied source sentences.

## Extraction workflow

```text
source snapshot
-> chapter/segment sampling
-> deterministic measurement
-> abstract LLM analysis
-> merge evidence and analysis
-> provenance and similarity checks
-> draft profile
-> human/Agent review
-> explicit activation
-> project/stage binding
```

The analysis is split into two passes:

- Measurement pass: sentence and paragraph length, punctuation, dialogue ratio,
  action/abstract-word ratio, connective density, repetition and scene rhythm.
- Abstraction pass: narrative voice, diction, dialogue mechanics, imagery, emotional
  temperature, scene method and anti-template constraints.

The model must return observed facts, supported interpretations, low-confidence
assumptions and material that must not be imitated. It must not summarize the source
plot as style.

## Profile shape

The initial table can use JSON for evolving dimensions while keeping lifecycle and
ownership relational:

```text
WritingStyleProfile
- id, owner_id, name, description
- source_type: user_defined | extracted_from_source | agent_draft | builtin
- source_snapshot_id, source_sample_hash
- status: draft | reviewed | active | archived
- version, profile_json, prompt_contract_json, provenance_json
- created_at, updated_at

ProjectWritingStyleLink
- project_id, style_profile_id, enabled, priority
- intensity, stage_scope, override_json
```

The JSON profile is organized into:

- narrative voice and distance
- syntax and rhythm
- lexicon and register
- dialogue and subtext
- description and rhetoric
- scene and plot technique
- emotional temperature
- anti-template constraints
- prohibited source-specific material

Every dimension has `value`, `confidence`, `evidence_summary` and optional
`measurement_keys`. Rules are short and executable. They are not free-form essays.

## Lifecycle

`draft -> reviewed -> active -> archived`, and `archived -> draft` on restore.

Archiving is a reversible retirement rather than a deletion: it removes the profile
from runtime selection while keeping existing bindings attached (they simply stop
taking effect). Restoring returns the profile to `draft` and must never jump straight
back to `reviewed` or `active`, because the material gate has to re-run. Human and
Agent clients expose the same reversal, so an Agent that archived a profile can undo
it without a human round trip.

## Runtime contract

The Context Pack remains authoritative. T0-T5 carry canon, state, chapter contract,
approved prose and retrieval. A selected style profile contributes only to T6:

- `style_profile_id`
- `style_profile_version`
- `style_profile_checksum`
- bounded `prompt_contract`
- intensity and stage scope

The profile cannot add names, facts, events or world rules. It cannot override
character voice rules or locked facts. Each generation log records the exact profile
version and checksum used. A profile is never silently selected from a source name.

Recommended intensity values are `subtle`, `balanced` and `strong`. The UI and Agent
API may disable individual dimensions, for example applying rhythm to prose but not
dialogue.

As implemented, intensity is a real injection weight rather than a label: it caps how
much of the contract reaches the prompt (8 / 16 / 24 expression rules and 1 / 2 / 4
new examples) and is surfaced as a two-character tag on the header line. T6 has a fixed
budget shared with project Skills, so intensity must never be expressed by adding extra
prompt lines — writing it longer would push style rules out of the budget and look like
"the profile was bound but no rules were injected".

## Human and Agent parity

Both clients call the same service methods:

- preview extraction
- review/edit draft
- activate profile
- bind/unbind profile
- preview runtime prompt

Preview endpoints do not write or call a provider unless explicitly named as a
generation preview. Confirm endpoints are the only path that writes candidates or
activates a profile. Agents receive the same validation errors, provenance and
confirmation requirements as the UI.

## Anti-template review

The review pass must distinguish:

- observable evidence: a quoted or precisely located construction in the candidate;
- supported editorial inference: repeated evidence across the candidate;
- preference: a subjective suggestion that cannot block promotion.

It must not mechanically ban three-part structures, parallelism, short sentences,
metaphor or common connectives. A device is a defect only when its local evidence
shows repetition, explanation replacing action, voice mismatch or scene damage.

## Path comparison

### A. Internal integration

Best consistency and auditability. It naturally reuses source snapshots, Context Pack,
candidate promotion and existing measurements. It increases core API and UI scope.

### B. External Agent

Fast for experimentation and batch research, but risks bypassing provenance,
confirmation and copyright controls. It also creates profile schema drift.

### C. Hybrid

The internal service owns source access, storage, validation, activation and runtime
injection. External Agents can propose a draft profile or import/export Markdown, but
the draft must pass the same schema, provenance and confirmation checks.

Recommendation: build A first, then expose B through C. C is the product architecture;
A is the first implementation slice.
