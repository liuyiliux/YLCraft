## ADDED Requirements

### Requirement: Gemini image generation via google-genai SDK
`GeminiImageBackend` SHALL use `google.genai.Client.models.generate_content()` with `response_modalities=["TEXT", "IMAGE"]` to generate images from text prompts.

#### Scenario: Text-to-image generation
- **WHEN** an `ImageGenerationRequest` with only a text prompt is submitted
- **THEN** the backend SHALL call `generate_content()` with the prompt and return the generated image as a local file path

#### Scenario: Image-to-image with reference image
- **WHEN** an `ImageGenerationRequest` with both a prompt and reference image(s) is submitted
- **THEN** the backend SHALL include reference images as `Part.from_bytes()` in the content array

#### Scenario: Image extraction from response
- **WHEN** the API returns a successful response
- **THEN** the backend SHALL iterate `response.candidates[0].content.parts` and save each `inline_data` blob to disk

### Requirement: Manager routes Gemini connectors to GeminiImageBackend
`BackendManager._init_image_backend()` SHALL route connectors with `provider == "gemini"` to `GeminiImageBackend`.

#### Scenario: Gemini routing
- **WHEN** a connector has `provider = "gemini"` and `provider_type = "image"`
- **THEN** `GeminiImageBackend(connector)` SHALL be instantiated

### Requirement: Frontend preset for Gemini image
`PROVIDER_PRESETS.gemini.image` SHALL provide default values for Gemini image generation.

#### Scenario: Preset includes Gemini image defaults
- **WHEN** user selects "Google Gemini" provider and "图像生成" type
- **THEN** the form SHALL auto-fill `base_url`, `default_model` (`gemini-2.5-flash-image`), and `supported_sizes`
