# 2026-07-09 AI Image Connector Capability Handoff

## Goal

Make image connector capability selection explicit instead of relying on endpoint names such as `/images/edits` or `/images/generations`.

## Current Progress

- Code now reads `default_params.image_capabilities` first.
- Endpoint/mode inference is kept only as a fallback for old data.
- Settings page exposes an explicit image capability selector.
- The settings capability selector is a three-choice dropdown: text-to-image only, image-to-image/edit only, or both. The `both` UI value is still persisted as `["text_to_image", "image_to_image"]`.
- Agent AI config tools and system prompt now require `image_capabilities` when creating or updating image connectors.
- Remote database image connectors have been patched with explicit capabilities.

## Remote DB Configuration

Configured 9 existing `provider_type=image` connectors:

| Connector id | Connector role | image_capabilities |
| --- | --- | --- |
| `41df403d-1c13-4015-bf91-84909aaeae85` | `aaccx-gpt-image-2` | `["text_to_image"]` |
| `345e6a97-c335-4239-8656-ccb198676adf` | `aaccx-gpt-image-2-edit` | `["image_to_image"]` |
| `dc1d8bff-8ce8-4369-9995-7525c21c533f` | `aaccx-gpt-image-2 copy` | `["text_to_image"]` |
| `e535ae5e-847a-45c5-9e52-f7813b1a80cc` | `openai-gemini-3.0-pro-image-preview` | `["text_to_image", "image_to_image"]` |
| `7f5a6da8-96bb-4d3e-9343-93419a2d065d` | `siliconflow-Kolors` | `["text_to_image"]` |
| `438b2a8f-d3f4-4d06-b406-aba3188c770a` | `siliconflow-Qwen-Image` | `["text_to_image"]` |
| `1325077e-ca44-442a-a3b2-a80ca7ebb169` | `Qwen-Image-Edit via DashScope/Bailian` | `["image_to_image"]` |
| `df0ccd79-d36d-455a-8d38-94fa44d06f7e` | `Qwen-Image-Edit via SiliconFlow` | `["image_to_image"]` |
| `939b16f7-65a3-4864-8e4e-9bb3144efbad` | `ModelScope Z-Image-Turbo` | `["text_to_image"]` |

No API keys were read, printed, or modified.

## Verification

- Remote DB update transaction completed.
- Follow-up select verified each connector now has the expected `default_params.image_capabilities`.
- Reloaded current backend via `POST /api/v1/ai/connectors/reload`; API returned success.
- Previous code verification for this change:
  - `backend\venv_win\Scripts\python.exe -m pytest backend\tests\test_ai_image_async.py -q` -> 20 passed
  - `backend\venv_win\Scripts\python.exe -m pytest backend\tests\test_agent_center.py -q` -> 101 passed
  - `cd frontend; npm.cmd run build` -> passed
- After the three-choice dropdown update, `cd frontend; npm.cmd run build` was run again and passed.
- Live AACCX generation smoke through YLCraft succeeded with provider `aaccx-gpt-image-2`, model `gpt-image-2`, size `1024x1024`, `n=1`. Three YLCraft promo images were generated and saved to Asset Hub:
  - `774ff848-045b-44df-aa48-2e20bdaea1a1` -> `backend/app/storage/images/20260709_180910_Use_case_ads-market_0.png`
  - `a27cb6fd-5a75-492d-8652-ef719dd0df4c` -> `backend/app/storage/images/20260709_181105_Use_case_ads-market_0.png`
  - `cc594834-dde2-481a-a069-d768d1e27ae7` -> `backend/app/storage/images/20260709_181302_Use_case_ads-market_0.png`
- Direct OpenAI-compatible endpoint tests:
  - `https://sub.chccc.xyz/v1/images/generations` was reachable, but the supplied token returned `403 Image generation is not enabled for this group`.
  - `https://oai.yby6.com/v1/images/generations` was reachable, but returned `401 Invalid token` for both the supplied real token and the placeholder-style token used in the user's server example.
  - The user's CentOS local `127.0.0.1:8787/v1/images/generations` succeeded outside this workstation using payload shape `{ model: "gpt-image-2", size: "1:1", resolution: "1K", quality: "medium", n: 1 }`.

## Next Step

Open `/settings` and confirm each image connector shows the expected capability selector value. Then verify `/image-gen` text-to-image and image-to-image selectors no longer mix edit-only and generation-only connectors.

For AACCX/NewAPI connector tuning, prefer the explicit successful payload shape from the user's server when configuring a compatible text-to-image connector:

```json
{
  "model": "gpt-image-2",
  "size": "1:1",
  "resolution": "1K",
  "quality": "medium",
  "n": 1
}
```

Do not infer image-generation availability from account balance alone. NewAPI-compatible deployments can reject image generation by token group even when the token is otherwise valid.
