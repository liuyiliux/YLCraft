"""
YLCraft — AI 连接器模型

管理 AI 服务提供商的 API 凭证和配置
"""

from __future__ import annotations

from sqlmodel import SQLModel, Field
from sqlalchemy import String, DateTime, Text, Boolean, Integer
from datetime import datetime, timezone
from typing import Optional
import json
import enum


class AIProvider(str, enum.Enum):
    """
    AI 服务提供商（简化版）
    
    注意：实际数据库中 provider 字段为字符串类型，可存储任意值。
    所有类型都使用 OpenAI 兼容 API 格式，generic 用于完全自定义配置。
    """
    openai = "openai"
    siliconflow = "siliconflow"
    gemini = "gemini"
    generic = "generic"

    @classmethod
    def values(cls) -> list[str]:
        """返回所有枚举值"""
        return [e.value for e in cls]

    @classmethod
    def label(cls, value: str) -> str:
        """获取 provider 的中文标签"""
        labels = {
            "openai": "OpenAI",
            "siliconflow": "硅基流动",
            "gemini": "Google Gemini",
            "generic": "通用配置",
        }
        return labels.get(value, value)


class AIModelTier(str, enum.Enum):
    """模型等级"""
    FREE = "free"           # 免费模型
    TIER_1 = "tier_1"       # 低成本
    TIER_2 = "tier_2"       # 标准
    TIER_3 = "tier_3"       # 高端
    PREMIUM = "premium"      # 顶级


class AIProviderType(str, enum.Enum):
    """AI 提供商类型"""
    llm = "llm"           # 大语言模型
    image = "image"       # 图像生成
    video = "video"       # 视频生成
    tts = "tts"           # 文本转语音
    stt = "stt"           # 语音转文本


class AIConnectorBase(SQLModel):
    """AI 连接基础模型"""
    provider: str = Field(..., description="AI 提供商（字符串类型，支持任意值）")
    name: str = Field(..., description="连接名称（如：OpenAI-Main）")
    api_key: str = Field("", description="API Key")

    # 提供商类型（LLM / Image / Video / TTS / STT）
    provider_type: AIProviderType = Field(
        AIProviderType.llm,
        description="提供商类型：llm / image / video / tts / stt"
    )

    # 可选配置
    base_url: Optional[str] = Field(None, description="API 基础 URL（用于代理/自托管）")
    api_endpoint: Optional[str] = Field(None, description="API 端点路径（如 /images/generations）")
    organization_id: Optional[str] = Field(None, description="组织 ID（OpenAI）")
    project_id: Optional[str] = Field(None, description="项目 ID（部分 API）")

    # 模型配置
    default_model: str = Field("gpt-4o", description="默认模型")
    available_models: str = Field("[]", description="可用模型列表 JSON")
    max_tokens: int = Field(4096, description="默认最大 token 数")
    temperature: float = Field(0.7, ge=0, le=2, description="默认温度参数")

    # ===== 图像/视频生成专用配置（Generic Provider）=====
    # Request 模板（Jinja2），用于渲染请求体
    request_template: Optional[str] = Field(
        None,
        description="Request 模板（Jinja2 格式），用于 Generic Provider"
    )

    # Response 解析配置（JSON）
    response_config: Optional[str] = Field(
        None,
        description="Response 解析配置 JSON，包含 images_path、error_path 等"
    )

    # 参数转换规则（JSON）
    parameter_transforms: Optional[str] = Field(
        None,
        description="参数转换规则 JSON（Jinja2 模板）"
    )

    # 支持的尺寸列表（图像生成）
    supported_sizes: Optional[str] = Field(
        None,
        description="支持的尺寸列表 JSON，如 ['1024x1024', '1792x1024']"
    )

    # 默认参数（JSON）
    default_params: Optional[str] = Field(
        None,
        description="默认参数 JSON，如 {'n': 1, 'quality': 'standard'}"
    )

    # 参考图支持配置
    support_reference_image: bool = Field(False, description="是否支持参考图")
    support_multiple_reference_images: bool = Field(False, description="是否支持多张参考图")
    reference_image_field: str = Field("image", description="参考图字段名（逗号分隔，如 image1,image2,image）")
    reference_image_array_field: Optional[str] = Field(None, description="参考图数组字段名，如 images（所有图片组成数组）")
    # ===== 结束：图像/视频生成专用配置 =====

    # 测试配置
    test_prompt: Optional[str] = Field(
        None,
        description="测试提示词（为空时使用默认值）"
    )

    # 成本控制
    monthly_budget: Optional[float] = Field(None, description="月度预算（美元）")
    daily_limit: Optional[int] = Field(None, description="每日请求限制")

    # 状态
    is_active: bool = Field(True, description="是否启用")
    is_default: bool = Field(False, description="是否为默认连接")
    priority: int = Field(0, description="优先级（数字越小优先级越高）")

    # 元数据
    description: Optional[str] = Field("", description="备注说明")
    last_used: Optional[datetime] = Field(None, description="最后使用时间")
    usage_count: int = Field(0, description="使用次数")
    total_cost: float = Field(0.0, description="累计消耗（美元）")


class AIConnector(AIConnectorBase, table=True):
    """AI 连接数据库模型"""
    __tablename__ = "ai_connectors"

    # provider 字段为字符串，不再限制为枚举
    id: str = Field(primary_key=True, description="连接 ID")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="创建时间"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="更新时间"
    )

    def get_available_models(self) -> list[str]:
        """获取可用模型列表"""
        if not self.available_models:
            return []
        try:
            return json.loads(self.available_models)
        except Exception:
            return []

    def set_available_models(self, models: list[str]):
        """设置可用模型列表"""
        self.available_models = json.dumps(models)

    def update_usage(self, tokens_used: int = 0, cost: float = 0.0):
        """更新使用统计"""
        self.last_used = datetime.now(timezone.utc)
        self.usage_count += 1
        self.total_cost += cost


class AIConnectorCreate(SQLModel):
    """创建 AI 连接请求"""
    provider: str
    name: str
    api_key: str = ""
    base_url: Optional[str] = None
    api_endpoint: Optional[str] = None
    organization_id: Optional[str] = None
    project_id: Optional[str] = None
    default_model: str = "gpt-4o"
    available_models: list[str] = Field(default_factory=list)
    max_tokens: int = 4096
    temperature: float = 0.7
    monthly_budget: Optional[float] = None
    daily_limit: Optional[int] = None
    is_active: bool = True
    is_default: bool = False
    priority: int = 0
    description: str = ""
    # 扩展配置
    provider_type: str = "llm"  # llm, image, video, tts, stt
    request_template: Optional[str] = None
    response_config: Optional[str] = None
    parameter_transforms: Optional[str] = None
    supported_sizes: Optional[str] = None
    default_params: Optional[str] = None
    support_reference_image: bool = False
    support_multiple_reference_images: bool = False
    reference_image_field: str = "image"
    reference_image_array_field: Optional[str] = None
    test_prompt: Optional[str] = None


class AIConnectorUpdate(SQLModel):
    """更新 AI 连接请求"""
    name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    api_endpoint: Optional[str] = None
    organization_id: Optional[str] = None
    project_id: Optional[str] = None
    default_model: Optional[str] = None
    available_models: Optional[list[str]] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    monthly_budget: Optional[float] = None
    daily_limit: Optional[int] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    priority: Optional[int] = None
    description: Optional[str] = None
    # 扩展配置
    provider_type: Optional[str] = None
    request_template: Optional[str] = None
    response_config: Optional[str] = None
    parameter_transforms: Optional[str] = None
    supported_sizes: Optional[str] = None
    default_params: Optional[str] = None
    support_reference_image: Optional[bool] = None
    support_multiple_reference_images: Optional[bool] = None
    reference_image_field: Optional[str] = None
    reference_image_array_field: Optional[str] = None
    test_prompt: Optional[str] = None


class AIConnectorResponse(SQLModel):
    """AI 连接响应"""
    id: str
    provider: str
    provider_label: str = ""  # 提供商中文名称
    name: str
    base_url: Optional[str] = None
    api_endpoint: Optional[str] = None
    api_key: Optional[str] = None  # 完整的 API Key（仅用于编辑时显示）
    organization_id: Optional[str] = None
    default_model: str
    max_tokens: int
    temperature: float
    monthly_budget: Optional[float] = None
    daily_limit: Optional[int] = None
    is_active: bool
    is_default: bool
    priority: int
    description: str
    last_used: Optional[datetime] = None
    usage_count: int
    total_cost: float
    created_at: datetime
    # 扩展字段
    provider_type: str = "llm"
    request_template: Optional[str] = None
    response_config: Optional[str] = None
    supported_sizes: Optional[list[str]] = None
    default_params: Optional[dict] = None
    support_reference_image: bool = False
    support_multiple_reference_images: bool = False
    reference_image_field: str = "image"
    reference_image_array_field: Optional[str] = None
    test_prompt: Optional[str] = None
    has_api_key: bool = False  # 是否配置了 API Key（不返回实际 key）

    @classmethod
    def from_db(cls, conn: AIConnector) -> "AIConnectorResponse":
        # 解析 supported_sizes
        supported_sizes = None
        if conn.supported_sizes:
            try:
                supported_sizes = json.loads(conn.supported_sizes)
            except Exception:
                pass

        # 解析 default_params
        default_params = None
        if conn.default_params:
            try:
                default_params = json.loads(conn.default_params)
            except Exception:
                pass

        return cls(
            id=conn.id,
            provider=conn.provider,
            provider_label=AIProvider.label(conn.provider),
            name=conn.name,
            base_url=conn.base_url,
            api_endpoint=conn.api_endpoint,
            api_key=conn.api_key,
            organization_id=conn.organization_id,
            default_model=conn.default_model,
            max_tokens=conn.max_tokens,
            temperature=conn.temperature,
            monthly_budget=conn.monthly_budget,
            daily_limit=conn.daily_limit,
            is_active=conn.is_active,
            is_default=conn.is_default,
            priority=conn.priority,
            description=conn.description or "",
            last_used=conn.last_used,
            usage_count=conn.usage_count,
            total_cost=conn.total_cost,
            created_at=conn.created_at,
            # 扩展字段
            provider_type=conn.provider_type.value if hasattr(conn.provider_type, 'value') else conn.provider_type,
            request_template=conn.request_template,
            response_config=conn.response_config,
            supported_sizes=supported_sizes,
            default_params=default_params,
            support_reference_image=conn.support_reference_image,
            support_multiple_reference_images=conn.support_multiple_reference_images,
            reference_image_field=conn.reference_image_field,
            reference_image_array_field=conn.reference_image_array_field,
            test_prompt=conn.test_prompt,
            has_api_key=bool(conn.api_key),
        )


# =============================================================================
# 使用统计模型
# =============================================================================

class AIUsageLog(SQLModel, table=True):
    """AI 使用日志"""
    __tablename__ = "ai_usage_logs"

    id: str = Field(primary_key=True)
    connector_id: str = Field(..., description="连接 ID")
    provider: str = Field(..., description="提供商")
    model: str = Field(..., description="使用的模型")
    prompt_tokens: int = Field(0, description="提示 token 数")
    completion_tokens: int = Field(0, description="完成 token 数")
    total_tokens: int = Field(0, description="总 token 数")
    cost: float = Field(0.0, description="本次消耗（美元）")
    latency_ms: int = Field(0, description="延迟（毫秒）")
    status: str = Field("success", description="请求状态")
    error_message: Optional[str] = Field(None, description="错误信息")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="请求时间"
    )
