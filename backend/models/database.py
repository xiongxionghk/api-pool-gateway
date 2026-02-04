"""数据模型定义"""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, Text, Enum as SQLEnum, JSON
)
from sqlalchemy.orm import relationship, DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy 基类"""
    pass


class ApiFormat(str, Enum):
    """API 格式类型"""
    OPENAI = "openai"           # /v1/chat/completions
    ANTHROPIC = "anthropic"     # /v1/messages


class PoolType(str, Enum):
    """池类型"""
    TOOL = "tool"
    NORMAL = "normal"
    ADVANCED = "advanced"


class Provider(Base):
    """服务商表"""
    __tablename__ = "providers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="服务商名称")
    base_url = Column(String(500), nullable=False, comment="基础URL，如 http://127.0.0.1:8311/v1")
    api_key = Column(String(500), nullable=False, comment="API Key")
    api_format = Column(SQLEnum(ApiFormat), default=ApiFormat.OPENAI, comment="API 格式")
    enabled = Column(Boolean, default=True, comment="是否启用")

    # 统计
    total_requests = Column(Integer, default=0)
    success_requests = Column(Integer, default=0)
    error_requests = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    endpoints = relationship("ModelEndpoint", back_populates="provider", cascade="all, delete-orphan")


class ModelEndpoint(Base):
    """模型端点表（服务商提供的具体模型）"""
    __tablename__ = "model_endpoints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_id = Column(Integer, ForeignKey("providers.id", ondelete="CASCADE"), nullable=False)
    model_id = Column(String(200), nullable=False, comment="模型ID，如 github-copilot/claude-haiku-4.5")
    pool_type = Column(SQLEnum(PoolType), nullable=True, comment="所属池类型，null表示未分配")
    enabled = Column(Boolean, default=True, comment="是否启用")
    priority = Column(Integer, default=0, comment="优先级，数字越大越优先")

    # 状态
    is_cooling = Column(Boolean, default=False, comment="是否在冷却中")
    cooldown_until = Column(DateTime, nullable=True, comment="冷却结束时间")
    last_error = Column(Text, nullable=True, comment="最后错误信息")

    # 统计
    total_requests = Column(Integer, default=0)
    success_requests = Column(Integer, default=0)
    error_requests = Column(Integer, default=0)
    avg_latency_ms = Column(Float, default=0, comment="平均延迟(ms)")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    provider = relationship("Provider", back_populates="endpoints")


class Pool(Base):
    """池配置表"""
    __tablename__ = "pools"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pool_type = Column(SQLEnum(PoolType), unique=True, nullable=False)
    virtual_model_name = Column(String(100), nullable=False, comment="对外暴露的虚拟模型名")

    # 轮询状态
    current_provider_index = Column(Integer, default=0, comment="当前服务商轮询指针")

    # 配置
    cooldown_seconds = Column(Integer, default=60)
    max_retries = Column(Integer, default=3)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RequestLog(Base):
    """请求日志表"""
    __tablename__ = "request_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 请求信息
    pool_type = Column(SQLEnum(PoolType), nullable=False)
    requested_model = Column(String(200), comment="请求的模型名")
    actual_model = Column(String(200), comment="实际使用的模型")
    provider_name = Column(String(100), comment="服务商名称")

    # 结果
    success = Column(Boolean, default=True)
    status_code = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)

    # 性能
    latency_ms = Column(Integer, default=0)

    # Token 统计
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)

    # 请求摘要
    request_summary = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
