# AI Connector Presets

Public, credential-free AI connector files. In YLCraft, open `Settings`, use
the `Import` action in AI model configuration, then edit the imported connector
to enter your own API key. The files use the same `connectors` contract as the
application export format.

| File | Provider | Capability | Notes |
| --- | --- | --- | --- |
| `agnes-video-v2.json` | Agnes | Text to video | Image-to-video needs a publicly reachable image URL, so it is not enabled in the local-first preset. |
| `agnes-image.json` | Agnes | Text/image to image | Agnes Image 2.1/2.0 Flash, synchronous URL response at `data[0].url`; img2img/multi-image goes through `extra_body.image`. |
| `dashscope-wan-2.7-video.json` | Alibaba Bailian | Text/image to video | Uses DashScope asynchronous polling; image-to-video uses the first-frame media contract. |
| `openai-text-image.json` | OpenAI | Text + image | Standard Chat Completions and Images API examples. |
| `siliconflow-text-image.json` | SiliconFlow | Text + image | OpenAI-compatible text plus configurable image generation. Verify the selected model's reference-image contract. |
| `siliconflow-free-stt.json` | SiliconFlow | Speech-to-text (STT) | Free `XingChenAGI/XingChenGSR-V1.0` ASR model via `/v1/audio/transcriptions`, multipart `file` upload. |
| `image-to-3d-generic.json` | Generic | Image to 3D | Generic HTTP task/poll contract. Replace endpoint, model, authentication headers and JSONPath values for the selected provider. |
| `tencent-hunyuan-3d-pro.json` | Tencent Cloud | Image/text to 3D | Hunyuan 3D Pro OpenAI-compatible submit/query API. Uses raw `Authorization: sk-...` API key auth and POST polling. |
| `tencent-hunyuan-rigging.json` | Tencent Cloud | 3D auto-rigging | Hunyuan auto-rigging (SubmitAutoRiggingJob/DescribeAutoRiggingJob). TC3-signed auth (`SecretId:SecretKey`). `no_model_selector=true` (no model parameter); declares `motion_types` (48 preset motions, `value`=vendor id / `label`=UI name). |
