# Proposal: 去重 B站共享常量与方法

## What

将 `download/platforms/bilibili.py` 和 `video/parser_bilibili.py` 中重复的 4 份代码（分辨率映射、码率映射、`_quality_to_resolution()`、`_get_filesize_for_qn()`）提取到 `platforms/bilibili/utils.py`，两处改为 import 共享模块。

## Why

两处维护相同逻辑容易不同步。之前修复分辨率显示 bug 时就需要改两处，且下次加新 qn 或改码率时又要改两处。

## What changes

- `platforms/bilibili/utils.py`：追加 `BILI_QUALITY_MAP`、`BILI_RESOLUTION_MAP`、`_QUALITY_BITRATE_MAP`、`_quality_to_resolution()`、`_get_filesize_for_qn()`、`_normalize_resolution()`
- `download/platforms/bilibili.py`：删除本地定义，改为 from import
- `video/parser_bilibili.py`：删除本地定义，改为 from import

## Non-goals

- 不改其他平台的类似重复（如 xiaohongshu 的 `parse_count`）
- 不创建 `backend/app/services/utils/` 通用工具目录
