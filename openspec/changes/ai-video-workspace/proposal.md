# AI Video Workspace

## Why

Video generation already has a page and provider adapter, but an asynchronous
submission disappears after refresh and its completed file may never reach the
Asset Hub. That makes the page a demo rather than an independently usable
creative tool.

## What Changes

- Treat `/video-gen` as a standalone video workspace, not only a Story jump target.
- Persist every provider task with its request context, status, result and Asset Hub id.
- Submit asynchronous jobs immediately; poll them separately and import a
  completed local file into Asset Hub exactly once.
- Restore recent video history after a page refresh and show whether each output
  is already in Asset Hub or linked back to a project.

## Non-goals

- This does not build a timeline editor or stitch shots together.
- This does not make an unavailable provider appear usable.
- This does not replace the later media production-line work.
