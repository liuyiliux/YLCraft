"""
YLCraft — Agent 工具基类
"""
from __future__ import annotations


class ToolResult:
    """工具执行结果"""
    def __init__(self, success: bool, data: any = None, error: str = ""):
        self.success = success
        self.data = data
        self.error = error

    def to_dict(self):
        return {"success": self.success, "data": self.data, "error": self.error}
