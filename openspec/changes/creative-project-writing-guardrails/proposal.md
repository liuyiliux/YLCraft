# Creative Project Writing Guardrails

## Why

YLCraft already persists narrative state and blocks some invalid generation paths, but the reason for a blocked step is only visible after a request fails. The writing workflow also needs selectable, versioned method packages rather than hidden prompt fragments.

## What Changes

- Add a read-only writing preflight contract for chapter outline, prose and Writer Room stages.
- Return actionable blockers, current source content and compatible creative Skill methods.
- Add the first method package for chapter hooks and rhythm without mutating canon or approved prose.

## Non-goals

- No automatic prose promotion, fact acceptance or external publishing.
- No new database table; methods remain file-backed Skills with checksums in Context Pack metadata.
- No replacement of the existing generation gates.
