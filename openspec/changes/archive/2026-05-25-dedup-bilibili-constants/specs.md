# Spec: B站共享常量与方法

## 需求

- `BILI_QUALITY_MAP`、`BILI_RESOLUTION_MAP`、`_QUALITY_BITRATE_MAP` 只有一份定义
- `_quality_to_resolution()`、`_get_filesize_for_qn()`、`_normalize_resolution()` 只有一份定义
- 上述符号都在 `platforms/bilibili/utils.py` 中
- `download/platforms/bilibili.py` 和 `video/parser_bilibili.py` 均从 utils.py import，各自的本地定义已删除
- 所有现有功能行为不变
