"""
系统设置模型 - 存储在数据库中的配置

优先级：数据库 > 配置文件
"""

from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional


class SystemSetting(SQLModel, table=True):
    """系统配置表"""
    __tablename__ = "system_settings"

    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(unique=True, index=True, description="配置键")
    value: str = Field(default="", description="配置值")
    description: str = Field(default="", description="配置描述")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class SystemSettingCreate(SQLModel):
    key: str
    value: str
    description: str = ""


class SystemSettingUpdate(SQLModel):
    value: Optional[str] = None
    description: Optional[str] = None


# 默认存储配置
DEFAULT_STORAGE_SETTINGS = {
    "video_download_path": {
        "value": "",
        "description": "视频解析下载保存路径"
    },
    "image_gen_path": {
        "value": "",
        "description": "AI图片生成保存路径"
    },
    "video_gen_path": {
        "value": "",
        "description": "AI视频生成保存路径"
    },
    "reference_image_path": {
        "value": "",
        "description": "参考图存储路径"
    },
    "upload_path": {
        "value": "",
        "description": "本地上传素材存储路径"
    },
}
