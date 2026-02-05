"""Pydantic 模型（API 请求/响应）"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


# ==================== 枚举 ====================

class ApiFormat(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class PoolType(str, Enum):
    TOOL = "tool"
    NORMAL = "normal"
    ADVANCED = "advanced"


# ==================== 服务商 ====================

class ProviderCreate(BaseModel):
    """创建服务商请求"""
    name: str = Field(..., description="服务商名称")
    base_url: str = Field(..., description="基础URL")
    api_key: str = Field(..., description="API Key")
    api_format: ApiFormat = Field(default=ApiFormat.OPENAI, description="API 格式")


class ProviderUpdate(BaseModel):
    """更新服务商请求"""
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    api_format: Optional[ApiFormat] = None
    enabled: Optional[bool] = None


class ProviderResponse(BaseModel):
    """服务商响应"""
    id: int
    name: str
    base_url: str
    api_key: str  # 会在返回时脱敏
    api_format: ApiFormat
    enabled: bool
    total_requests: int
    success_requests: int
    error_requests: int
    created_at: datetime
    endpoint_count: int = 0
    healthy_endpoint_count: int = 0

    class Config:
        from_attributes = True


class ProviderWithModels(ProviderResponse):
    """带模型列表的服务商"""
    available_models: List[str] = []  # 从服务商拉取的可用模型


# ==================== 模型端点 ====================

class ModelEndpointCreate(BaseModel):
    """添加模型到池"""
    provider_id: int
    model_id: str
    pool_type: PoolType
    weight: int = 1


class ModelEndpointUpdate(BaseModel):
    """更新模型端点"""
    pool_type: Optional[PoolType] = None
    enabled: Optional[bool] = None
    weight: Optional[int] = None
    min_interval_seconds: Optional[int] = None


class ModelEndpointResponse(BaseModel):
    """模型端点响应"""
    id: int
    provider_id: int
    provider_name: str
    model_id: str
    pool_type: Optional[PoolType]
    enabled: bool
    weight: int
    min_interval_seconds: int = 0
    is_cooling: bool
    cooldown_until: Optional[datetime]
    last_error: Optional[str]
    last_request_at: Optional[datetime] = None
    total_requests: int
    success_requests: int
    error_requests: int
    avg_latency_ms: float
    success_rate: float = 0

    class Config:
        from_attributes = True


# ==================== 池 ====================

class PoolResponse(BaseModel):
    """池响应"""
    pool_type: PoolType
    virtual_model_name: str
    cooldown_seconds: int
    max_retries: int
    timeout_seconds: int = 60  # 请求超时(秒)
    endpoint_count: int
    healthy_endpoint_count: int
    provider_count: int


class PoolUpdate(BaseModel):
    """更新池配置"""
    cooldown_seconds: Optional[int] = None
    max_retries: Optional[int] = None
    timeout_seconds: Optional[int] = None


class PoolEndpointsResponse(BaseModel):
    """池内端点详情"""
    pool_type: PoolType
    virtual_model_name: str
    cooldown_seconds: int = 30  # Add this
    max_retries: int = 3        # Add this
    timeout_seconds: int = 60
    providers: List[Dict[str, Any]]  # 按服务商分组的端点


# ==================== 统计 ====================

class StatsResponse(BaseModel):
    """统计响应"""
    total_providers: int
    enabled_providers: int
    total_endpoints: int
    healthy_endpoints: int
    cooling_endpoints: int

    total_requests: int
    success_requests: int
    error_requests: int
    success_rate: float

    pool_stats: Dict[str, Dict[str, Any]]


# ==================== 日志 ====================

class LogResponse(BaseModel):
    """日志响应"""
    id: int
    pool_type: PoolType
    requested_model: str
    actual_model: str
    provider_name: str
    success: bool
    status_code: Optional[int]
    error_message: Optional[str]
    latency_ms: int
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class LogListResponse(BaseModel):
    """日志列表响应"""
    total: int
    logs: List[LogResponse]


# ==================== 通用 ====================

class MessageResponse(BaseModel):
    """通用消息响应"""
    success: bool
    message: str


class FetchModelsResponse(BaseModel):
    """拉取模型响应"""
    provider_id: int
    provider_name: str
    models: List[str]
