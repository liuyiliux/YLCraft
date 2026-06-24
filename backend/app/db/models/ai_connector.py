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
    embedding = "embedding"  # 嵌入模型（文本/图像向量化）


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
    reference_image_field: str = Field("image", description="参考图字段名（逗号分隔，如 image1,image2,）")
    reference_image_array_field: Optional[str] = Field(None, description="参考图数组字段名，如 images（所有图片组成数组）")
    # ===== 结束：图像/视频生成专用配置 =====

    # ===== 嵌入模型专用配置 =====
    embedding_type: Optional[str] = Field(
        None,
        description="嵌入类型：text（文本嵌入）/ image（图像嵌入）/ multimodal（多模态）"
    )
    embedding_dimension: Optional[int] = Field(
        None,
        description="向量维度，如 384、512、1024、3072 等"
    )
    normalize_embeddings: bool = Field(True, description="是否归一化向量（余弦相似度搜索推荐开启）")
    # ===== 结束：嵌入模型专用配置 =====
    
    # ===== LLM 视觉支持配置 =====
    support_vision_input: bool = Field(
        False,
        description="是否支持视觉输入（多模态模型，如 Qwen/Qwen3-VL-32B-Instruct）"
    )
    # ===== 结束：LLM 视觉支持配置 =====

    # 测试配置
    test_prompt: Optional[str] = Field(
        None,
        description="测试提示词（为空时使用默认值）"
    )

    # 超时配置（秒）
    timeout: int = Field(300, description="API 请求超时时间（秒），默认 300 秒（5分钟）")
    test_timeout: int = Field(20, description="连接测试超时时间（秒），默认 20 秒")

    # 成本控制
    monthly_budget: Optional[float] = Field(None, description="月度预算（美元）")
    daily_limit: Optional[int] = Field(None, description="每日请求限制")
    
    # 按次计费（图像/视频生成专用）
    price_per_call: Optional[float] = Field(None, description="每次调用费用（美元），如 0.002 表示每次调用 0.002 美元")

    # 状态
    is_active: bool = Field(True, description="是否启用")
    is_default: bool = Field(False, description="是否为默认连接")
    priority: int = Field(0, description="优先级（数字越小优先级越高）")

    # 元数据
    description: Optional[str] = Field("", description="备注说明")
    last_used: Optional[datetime] = Field(None, description="最后使用时间")
    usage_count: int = Field(0, description="使用次数")
    total_cost: float = Field(0.0, description="累计消耗（美元）")

    # API 格式类型：openai_sdk（使用 OpenAI SDK）/ custom（使用 httpx 手动模式）
    api_format: str = Field("custom", description="API 格式类型：openai_sdk / custom")


class AIConnector(AIConnectorBase, table=True):
    """AI 连接数据库模型"""
    __tablename__ = "ai_connectors"

    # provider 字段为字符串，不再限制为枚举
    id: str = Field(primary_key=True, description="连接 ID")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        description="创建时间"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
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
        self.last_used = datetime.now(timezone.utc).replace(tzinfo=None)
        self.usage_count += 1
        self.total_cost += cost


class AIConnectorCreate(SQLModel):
    """创建 AI 连接请求"""
    model_config = {"extra": "ignore"}
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
    price_per_call: Optional[float] = None
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
    # 超时配置
    timeout: int = 300
    test_timeout: int = 20
    # LLM 视觉支持配置
    support_vision_input: bool = False
    # 嵌入模型专用配置
    embedding_type: Optional[str] = None
    embedding_dimension: Optional[int] = None
    normalize_embeddings: bool = True
    # API 格式类型
    api_format: str = "custom"


class AIConnectorUpdate(SQLModel):
    """更新 AI 连接请求"""
    model_config = {"extra": "ignore"}
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
    price_per_call: Optional[float] = None
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
    # 超时配置
    timeout: Optional[int] = None
    test_timeout: Optional[int] = None
    # LLM 视觉支持配置
    support_vision_input: Optional[bool] = None
    # 嵌入模型专用配置
    embedding_type: Optional[str] = None
    embedding_dimension: Optional[int] = None
    normalize_embeddings: Optional[bool] = None
    # API 格式类型
    api_format: Optional[str] = None


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
    price_per_call: Optional[float] = None
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
    # 超时配置
    timeout: int = 300
    test_timeout: int = 20
    support_vision_input: bool = False
    has_api_key: bool = False  # 是否配置了 API Key（不返回实际 key）
    # 嵌入模型专用配置
    embedding_type: Optional[str] = None
    embedding_dimension: Optional[int] = None
    normalize_embeddings: bool = True
    # API 格式类型
    api_format: str = "custom"

    @classmethod
    def from_db(cls, conn: AIConnector) -> "AIConnectorResponse":
        # 解析 supported_sizes（支持 JSON 数组和逗号分隔字符串）
        supported_sizes = []
        if conn.supported_sizes:
            try:
                sizes = json.loads(conn.supported_sizes)
                if isinstance(sizes, list):
                    # 标准化分隔符为 'x'
                    supported_sizes = [s.replace('*', 'x') if isinstance(s, str) else str(s) for s in sizes]
            except Exception:
                # 兼容逗号分隔的旧格式
                if isinstance(conn.supported_sizes, str) and ',' in conn.supported_sizes:
                    supported_sizes = [s.strip().replace('*', 'x') for s in conn.supported_sizes.split(',') if s.strip()]
                elif isinstance(conn.supported_sizes, str) and conn.supported_sizes:
                    supported_sizes = [conn.supported_sizes.replace('*', 'x')]

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
            price_per_call=conn.price_per_call,
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
            timeout=conn.timeout,
            test_timeout=conn.test_timeout,
            support_vision_input=conn.support_vision_input,
            has_api_key=bool(conn.api_key),
            # 嵌入模型专用配置
            embedding_type=conn.embedding_type,
            embedding_dimension=conn.embedding_dimension,
            normalize_embeddings=conn.normalize_embeddings,
            api_format=getattr(conn, 'api_format', 'custom'),
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
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        description="请求时间"
    )


# =============================================================================
# AI Provider 元数据模型
# =============================================================================

class AIProviderMetadataBase(SQLModel):
    """AI Provider 元数据基础模型
    
    注意：此模型用于数据库表 ai_provider_metadata。
    已废弃的 request_template 字段已删除，统一使用按类型分组的 request_templates。
    """
    # Provider 基本信息
    name: str = Field(..., description="Provider 显示名称（如 OpenAI、硅基流动）")
    icon: str = Field("brain", description="图标标识")
    color: str = Field("#94a3b8", description="品牌颜色（十六进制）")
    description: str = Field("", description="描述信息")

    # API 配置
    base_url: Optional[str] = Field(None, description="默认 API 基础 URL")
    api_key: Optional[str] = Field(None, description="默认 API Key（加密存储）")
    api_format: str = Field(
        "openai-compatible",
        description="API 格式类型：openai-compatible / custom / gemini"
    )

    # 支持的类型列表
    supported_types: str = Field(
        "[]",
        description="支持的类型列表 JSON，如 ['llm', 'image']"
    )

    # 按类型分组的默认模型
    default_models: str = Field(
        "{}",
        description="按类型分组的默认模型 JSON，如 {'llm': 'gpt-4o', 'image': 'dall-e-3'}"
    )

    # 按类型分组的可用模型列表
    available_models: str = Field(
        "{}",
        description="按类型分组的可用模型列表 JSON，如 {'llm': ['gpt-4o', 'gpt-4o-mini']}"
    )

    # 按类型分组的默认参数
    default_params: str = Field(
        "{}",
        description="按类型分组的默认参数 JSON"
    )

    # 按类型分组的请求模板
    request_templates: str = Field(
        "{}",
        description="按类型分组的请求模板 JSON，如 {'llm': '...', 'image': '...'}"
    )

    # 按类型分组的响应配置
    response_configs: str = Field(
        "{}",
        description="按类型分组的响应配置 JSON"
    )

    # 按类型分组的支持尺寸
    supported_sizes: str = Field(
        "{}",
        description="按类型分组的支持尺寸 JSON"
    )

    # 按类型分组的参考图配置
    reference_image_configs: str = Field(
        "{}",
        description="按类型分组的参考图配置 JSON"
    )

    # 按类型分组的参数转换
    parameter_transforms: str = Field(
        "{}",
        description="按类型分组的参数转换 JSON"
    )

    # 状态
    is_active: bool = Field(True, description="是否启用")
    is_editable: bool = Field(False, description="是否可编辑（系统内置 Provider 不可编辑）")


class AIProviderMetadata(AIProviderMetadataBase, table=True):
    """AI Provider 元数据数据库模型"""
    __tablename__ = "ai_provider_metadata"

    provider_id: str = Field(primary_key=True, description="Provider ID（如 openai、siliconflow）")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        description="创建时间"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        description="更新时间"
    )

    def get_supported_types(self) -> list[str]:
        """获取支持的类型列表"""
        if not self.supported_types:
            return []
        try:
            return json.loads(self.supported_types)
        except Exception:
            return []

    def get_default_models(self) -> dict:
        """获取按类型分组的默认模型"""
        if not self.default_models:
            return {}
        try:
            return json.loads(self.default_models)
        except Exception:
            return {}

    def get_available_models(self) -> dict:
        """获取按类型分组的可用模型列表"""
        if not self.available_models:
            return {}
        try:
            return json.loads(self.available_models)
        except Exception:
            return {}

    def get_default_params(self) -> dict:
        """获取按类型分组的默认参数"""
        if not self.default_params:
            return {}
        try:
            return json.loads(self.default_params)
        except Exception:
            return {}

    def get_default_for_type(self, provider_type: str) -> dict:
        """获取指定类型的默认配置"""
        params = self.get_default_params()
        return params.get(provider_type, {})

    def get_request_templates(self) -> dict:
        """获取按类型分组的请求模板"""
        if not self.request_templates:
            return {}
        try:
            return json.loads(self.request_templates)
        except Exception:
            return {}

    def get_response_configs(self) -> dict:
        """获取按类型分组的响应配置"""
        if not self.response_configs:
            return {}
        try:
            return json.loads(self.response_configs)
        except Exception:
            return {}

    def get_supported_sizes(self) -> dict:
        """获取按类型分组的支持尺寸"""
        if not self.supported_sizes:
            return {}
        try:
            return json.loads(self.supported_sizes)
        except Exception:
            return {}

    def get_reference_image_configs(self) -> dict:
        """获取按类型分组的参考图配置"""
        if not self.reference_image_configs:
            return {}
        try:
            return json.loads(self.reference_image_configs)
        except Exception:
            return {}

    def get_parameter_transforms(self) -> dict:
        """获取按类型分组的参数转换"""
        if not self.parameter_transforms:
            return {}
        try:
            return json.loads(self.parameter_transforms)
        except Exception:
            return {}


class AIProviderMetadataCreate(SQLModel):
    """创建 Provider 元数据请求"""
    model_config = {"extra": "ignore"}
    provider_id: str
    name: str
    icon: str = "brain"
    color: str = "#94a3b8"
    description: str = ""
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    api_format: str = "openai-compatible"
    supported_types: list[str] = Field(default_factory=list)
    default_models: dict = Field(default_factory=dict)
    available_models: dict = Field(default_factory=dict)
    default_params: dict = Field(default_factory=dict)
    request_templates: dict = Field(default_factory=dict)
    response_configs: dict = Field(default_factory=dict)
    supported_sizes: dict = Field(default_factory=dict)
    reference_image_configs: dict = Field(default_factory=dict)
    parameter_transforms: dict = Field(default_factory=dict)
    is_active: bool = True
    is_editable: bool = True


class AIProviderMetadataUpdate(SQLModel):
    """更新 Provider 元数据请求"""
    model_config = {"extra": "ignore"}
    name: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    api_format: Optional[str] = None
    supported_types: Optional[list[str]] = None
    default_models: Optional[dict] = None
    available_models: Optional[dict] = None
    default_params: Optional[dict] = None
    request_templates: Optional[dict] = None
    response_configs: Optional[dict] = None
    supported_sizes: Optional[dict] = None
    reference_image_configs: Optional[dict] = None
    parameter_transforms: Optional[dict] = None
    is_active: Optional[bool] = None


class AIProviderMetadataResponse(SQLModel):
    """Provider 元数据响应"""
    provider_id: str
    name: str
    icon: str = "brain"
    color: str = "#94a3b8"
    description: str = ""
    base_url: Optional[str] = None
    api_key: Optional[str] = None  # 完整的 API Key（仅用于编辑时显示）
    api_format: str = "openai-compatible"
    supported_types: list[str] = Field(default_factory=list)
    default_models: dict = Field(default_factory=dict)
    available_models: dict = Field(default_factory=dict)
    default_params: dict = Field(default_factory=dict)
    request_templates: dict = Field(default_factory=dict)
    response_configs: dict = Field(default_factory=dict)
    supported_sizes: dict = Field(default_factory=dict)
    reference_image_configs: dict = Field(default_factory=dict)
    parameter_transforms: dict = Field(default_factory=dict)
    is_active: bool = True
    is_editable: bool = False
    has_api_key: bool = False  # 是否配置了 API Key
    created_at: datetime = None
    updated_at: datetime = None

    @classmethod
    def from_db(cls, metadata: AIProviderMetadata) -> "AIProviderMetadataResponse":
        return cls(
            provider_id=metadata.provider_id,
            name=metadata.name,
            icon=metadata.icon,
            color=metadata.color,
            description=metadata.description or "",
            base_url=metadata.base_url,
            api_key=metadata.api_key,
            api_format=metadata.api_format,
            supported_types=metadata.get_supported_types(),
            default_models=metadata.get_default_models(),
            available_models=metadata.get_available_models(),
            default_params=metadata.get_default_params(),
            request_templates=metadata.get_request_templates(),
            response_configs=metadata.get_response_configs(),
            supported_sizes=metadata.get_supported_sizes(),
            reference_image_configs=metadata.get_reference_image_configs(),
            parameter_transforms=metadata.get_parameter_transforms(),
            is_active=metadata.is_active,
            is_editable=metadata.is_editable,
            has_api_key=bool(metadata.api_key),
            created_at=metadata.created_at,
            updated_at=metadata.updated_at,
        )
