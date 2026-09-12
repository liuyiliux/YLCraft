# Image Prompt Reference Library

## Why

YLCraft currently has prompt templates for creative-project stages and platform generation workflows. That is not the same as a large image-prompt reference library.

The reference project `basketikun/infinite-canvas` includes a prompt library that pulls hundreds or thousands of image prompt examples from public GitHub repositories, lets users search by title/category/tags, and inserts the selected prompt into canvas generation input. YLCraft needs the same concept as a standalone capability.

## What Changes

- Add a standalone image prompt reference library for visual-generation inspiration and reusable prompt examples.
- Keep this library separate from `PlatformTemplate` and creative-project stage templates.
- Import/sync prompt examples from public GitHub prompt repositories into a normalized local cache/database.
- Expose search, category, tag, detail, refresh and source-management APIs.
- Add a prompt-library page for browsing image prompt examples.
- Add prompt-library pickers to `/canvas` prompt/image nodes and the image-generation page.
- Only generated images/results enter Asset Hub automatically. Reference prompt examples remain reference data unless the user explicitly saves one as an asset.

## Reference

Implementation reference: `basketikun/infinite-canvas`.

Observed behavior:

- prompt items include `id`, `title`, `coverUrl`, `prompt`, `tags`, `category`, `githubUrl`, `preview`, `createdAt`, `updatedAt`
- prompt sources are public GitHub repositories such as `ZeroLu/awesome-gpt-image`, `ImgEdify/Awesome-GPT4o-Image-Prompts`, `YouMind-OpenLab/awesome-gpt-image-2`, `YouMind-OpenLab/awesome-nano-banana-pro-prompts`, and `davidwuw0811-boop/awesome-gpt-image2-prompts`
- the reference app uses frontend direct fetch and IndexedDB cache; YLCraft should prefer backend sync for stability, source governance, and future Agent/tool access
- canvas integration inserts or appends a selected prompt into the active prompt input

License boundary: use the reference for behavior and data-source ideas. Do not copy AGPL source code into YLCraft unless the project explicitly accepts that license obligation.

## Impact

- Backend: new service/module for image prompt reference sources, sync, parsing and search.
- Database: new tables or Asset Hub-compatible reference records for prompt sources and prompt items.
- Frontend: prompt-library page, reusable prompt picker dialog, canvas/image-generation integration.
- Agent: read-only tools for searching and retrieving prompt references; optional write tools for refreshing sources or saving a selected prompt as an asset.
- Docs/OpenSpec: keep this concept separate from `PlatformTemplate` and generated asset storage.
