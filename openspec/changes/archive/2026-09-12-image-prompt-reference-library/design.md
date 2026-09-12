# Design

## Concept Boundary

| Concept | Role | Persistence | Asset Hub behavior |
| --- | --- | --- | --- |
| Image prompt reference | Searchable examples for visual prompt inspiration. | Prompt reference tables/cache. | Not an asset by default. |
| Prompt template | Parameterized workflow prompt for a known generation stage. | `PlatformTemplate`. | Not an asset by default. |
| Generated image | Output produced by an image model. | Image task/result + Asset Hub. | Enters Asset Hub with lineage. |
| Saved prompt asset | User explicitly saves a prompt reference as reusable material. | Asset Hub text/prompt asset. | Enters Asset Hub by user action. |

The reference library should be large, searchable and disposable/rebuildable from sources. It should not become project truth and should not pollute Asset Hub unless the user chooses to save a prompt or generates media from it.

## Data Shape

```ts
type ImagePromptSource = {
  id: string
  name: string
  repo_url: string
  raw_base_url: string
  parser: 'markdown_sections' | 'json_prompts' | 'custom'
  enabled: boolean
  last_synced_at?: string
  sync_status?: 'idle' | 'syncing' | 'success' | 'failed'
  error?: string
}

type ImagePromptReference = {
  id: string
  source_id: string
  external_id: string
  title: string
  prompt: string
  negative_prompt?: string
  cover_url?: string
  preview_markdown?: string
  tags: string[]
  category: string
  source_url: string
  model_hint?: string
  needs_reference_image?: boolean
  language?: string
  metadata?: Record<string, unknown>
  created_at: string
  updated_at: string
}
```

## Sync Strategy

- Seed known public sources with parser definitions.
- Sync through backend jobs instead of browser-only fetch so Agent, canvas and image generation can share one source of truth.
- Store raw-source metadata enough to re-sync and deduplicate by `source_id + external_id`.
- Keep prompt references rebuildable; do not treat them as user-authored assets.
- Allow manual refresh and scheduled refresh later.

## UI Strategy

- Add a standalone prompt-library page focused on browsing examples, not editing generation-stage templates.
- Add reusable picker dialog:
  - keyword search over title/prompt/tags/category
  - category and tag filters
  - cover/preview thumbnail when available
  - detail view with full prompt and source link
  - actions: copy, append, replace current prompt, save as asset
- Canvas integration:
  - Prompt node and image model node expose a prompt-library icon near the prompt input
  - Selecting a prompt can replace or append to the current prompt
  - Generated image nodes store the selected reference prompt id in metadata/lineage
- Image-generation page integration:
  - Same picker can fill the positive prompt
  - Generated results, not references, enter Asset Hub automatically

## Agent Tools

Read tools:

- `search_image_prompt_references`
- `get_image_prompt_reference`
- `list_image_prompt_sources`

Write tools:

- `refresh_image_prompt_sources` with `write` risk
- `save_image_prompt_reference_as_asset` with `write` risk

Agent should not silently import every reference into Asset Hub. It may suggest saving selected references, but user-confirmed saves should be explicit.
