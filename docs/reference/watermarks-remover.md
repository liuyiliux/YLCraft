# `watermarks-remover` 评估记录

评估日期：2026-08-24

- 仓库：`guillaumemeyer/watermarks-remover`
- 当前锁定版本：`v0.5.0`
- 许可证：仓库页面标注 MIT；接入前仍需在发布构建中保留许可证与版权声明。
- 运行边界：项目只把它视为可选的本地/内网适配器；外部 Agent 不直接访问该服务，也不接触用户文件路径、平台凭证或供应商密钥。
- 能力边界：它覆盖 Unicode/bidi、C2PA/EXIF/XMP 和多种文档/媒体格式；YLCraft 内置适配器已逐步复刻其 Layer A 文本与文档/图片覆盖，未支持格式仍只做审计、不宣称清理。
- ## 能力边界（2026-08-24 复刻进展）

- 已复刻：文本 Layer A 隐形 Unicode 清理（零宽/bidi/标签/非字符/保留可忽略/私有用途/空间同形字），并保留 emoji 胶水、变体选择符与连接脚本内的合法 ZWJ/ZWNJ；报告含 `unicode_breakdown` 类型细分。
- 已复刻文档：PDF（pypdf）、docx/xlsx/pptx（docProps/core.xml）、odt（meta.xml）、epub（OPF dc 元数据）。
- 已复刻图片：PNG/JPEG/WebP/BMP/TIFF/GIF；视频/音频走 ffmpeg 去容器元数据。
- 未复刻（可后续接入）：Layer B 统计文本水印的 LLM 改写、SynthID/CtrlRegen 像素域水印、MarkLLM 验证。

产品文案：使用“AI 来源标记与文件元数据清理”，不宣称可以移除任意视觉水印；原资产始终保留，清理结果作为派生资产写入 Asset Hub。

上游仓库：<https://github.com/guillaumemeyer/watermarks-remover>
