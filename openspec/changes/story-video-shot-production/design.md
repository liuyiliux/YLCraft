# Design: Story Video Shot Production

## Ownership

```text
ProjectContent(storyboard panel)
  -> /video-gen request context
  -> configured video provider/model
  -> AssetNode(video) -> AssetVersion -> AssetRepresentation
  -> ProjectAssetLink(role=output, relation=derived_from)
```

`ProjectContent` remains the source of the shot plan. Asset Hub remains the canonical video file store. `ProjectAssetLink` is the project-local relation and carries chapter, panel, task, prompt, provider/model and reference-asset provenance.

## Request Contract

`POST /api/v1/videos/generate` accepts optional `project_id`, `content_id`, `chapter_number`, `source_type`, `source_index`, `source_title` and `reference_asset_ids` in addition to existing generation controls. `reference_asset_ids` are Asset Hub node ids, not browser object URLs. The backend resolves their latest local image representations; the first usable one becomes `start_image` when the user did not upload a first frame.

## Completion Contract

When the configured video backend returns a local video file, the API imports it into Asset Hub in the same DB session as its `ProjectAssetLink`. If the project context is invalid, the generated file is not silently claimed as a project output. The API response includes `asset_id` and echoed project source fields for the video UI.

## Storyboard Video Plan

Storyboard panels carry a small video plan in addition to their existing image-generation plan:

- `image_prompt` describes the static first-frame composition only.
- `video_prompt` describes the motion after that frame: visible action, camera movement, pacing and emotional change. It does not duplicate a complete visual-character inventory.
- `duration_seconds` is normalized to an integer from 3 through 6. Legacy panels without a duration receive a shot-size-based default.
- `camera_motion` is normalized to one of `推近`, `拉远`, `摇镜`, `平移`, `跟拍`, `环绕`, or `静止`.
- `generate_audio` defaults to false. `music_hint` is optional and only guides a provider when the shot intentionally needs native sound.

Opening a panel's video action serializes this plan into the `/video-gen` URL. The generator preserves the fields in its request and persistence metadata. Existing storyboards remain compatible because normalization derives a video prompt and duration when their old payload contains only an image prompt.

## Project Output Readback

The episode workbench derives completed storyboard videos from existing `ProjectAssetLink` records. It selects links with `role=output`, `metadata.source=video_generation`, `metadata.source_type=storyboard_panel`, matching storyboard `content_id` and panel number. The linked Asset Hub representation is played in the originating panel. This is a readback projection, not a second video list or a browser-local result cache.

## Follow-up

Provider-native asynchronous video task context is owned by the standalone
`ai-video-workspace` change. `VideoGenerationTask` persists source provenance,
so a process restart can finish Asset Hub import and project linkage on a later
poll. Shot assembly and nonlinear editing remain separate work.
