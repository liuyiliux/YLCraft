# Story Video Shot Production

## Why

`/story` owns scripts, storyboards, reference cards, generated images and project lineage, while `/video-gen` has remained an isolated generator. A short-drama production flow must allow a storyboard panel to become a video shot without losing its chapter, source panel or visual references.

## What Changes

- Add a storyboard-panel action that opens `/video-gen` with the panel prompt, source context and selected reference asset ids.
- Extend video generation requests with optional creative-project provenance.
- Resolve project reference Asset Hub files server-side for first-frame video generation.
- Persist completed videos in Asset Hub and create a project `output -> derived_from` link to the storyboard content.

## Non-goals

- This change does not build a nonlinear video editor, scene concatenator or a separate project video table.
- This change does not assume a fixed video provider or model.
- Remote asynchronous providers are not treated as complete until a local video file is available for Asset Hub persistence.
