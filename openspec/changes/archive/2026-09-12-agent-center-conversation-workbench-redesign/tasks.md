# Tasks

## Phase 0: Contract

- [x] 1. Audit current Agent Center hierarchy, state ownership and auxiliary requests.
- [x] 2. Define the three product constraints and conversation-first information architecture.
- [x] 3. Confirm the redesign does not change backend APIs or Agent runtime semantics.

## Phase 1: Structure

- [x] 4. Replace the large console header and metric wall with a compact conversation header.
- [x] 5. Keep only recent conversations and active Agent summary in the left rail.
- [x] 6. Constrain the message reading column and keep execution evidence inline.
- [x] 7. Simplify the composer and remove repeated status/model/budget labels.

## Phase 2: Robustness

- [x] 8. Add an Agent page error boundary with in-place recovery.
- [x] 9. Add local loading/error/retry states for thread, Profile and auxiliary resources.
- [x] 10. Make thread restoration failure explicit without creating a duplicate conversation.
- [x] 11. Preserve partial streaming output and retry affordance on request failure.

## Phase 3: Verification and Docs

- [x] 12. Verify TypeScript and frontend build.
- [x] 13. Validate desktop and mobile layout with external Chrome/Patchright, not the in-app browser.
- [x] 14. Update product, system architecture and Agent domain docs.
- [x] 15. Mark completed tasks and leave remaining acceptance work explicit.

## External Acceptance

- Local visual validation on 2026-08-11 confirmed no desktop/mobile horizontal overflow. The active local proxy returned HTTP 500 for all Agent resource endpoints, so functional multi-turn restoration and streamed retry still require a healthy backend/remote PostgreSQL environment.
