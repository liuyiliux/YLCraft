# `watermarks-remover` 评估记录

评估日期：2026-08-24

- 仓库：`guillaumemeyer/watermarks-remover`
- 当前锁定版本：`v0.5.0`
- 许可证：仓库页面标注 MIT；接入前仍需在发布构建中保留许可证与版权声明。
- 运行边界：项目只把它视为可选的本地/内网适配器；外部 Agent 不直接访问该服务，也不接触用户文件路径、平台凭证或供应商密钥。
- 能力边界：它覆盖 Unicode/bidi、C2PA/EXIF/XMP 和多种文档/媒体格式；YLCraft 当前内置适配器先实现文本控制符与常见图片元数据，未支持格式只做审计。
- 产品文案：使用“AI 来源标记与文件元数据清理”，不宣称可以移除任意视觉水印；原资产始终保留，清理结果作为派生资产写入 Asset Hub。

上游仓库：<https://github.com/guillaumemeyer/watermarks-remover>
