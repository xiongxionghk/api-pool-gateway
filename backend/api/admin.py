"""管理后台 API 路由"""

import logging
from typing import Optional, List

import httpx
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db, crud
from models import (
    ProviderCreate, ProviderUpdate, ProviderResponse, ProviderWithModels,
    ModelEndpointCreate, ModelEndpointUpdate, ModelEndpointResponse,
    PoolResponse, PoolEndpointsResponse,
    StatsResponse, LogResponse, LogListResponse,
    MessageResponse, FetchModelsResponse,
)
from models.database import Provider, ModelEndpoint, PoolType, ApiFormat
from core import get_pool_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin")


# ==================== 服务商管理 ====================

@router.get("/providers", response_model=List[ProviderResponse])
async def list_providers(db: AsyncSession = Depends(get_db)):
    """获取所有服务商"""
    providers = await crud.get_all_providers(db)
    result = []
    for p in providers:
        healthy = len([e for e in p.endpoints if e.enabled and not e.is_cooling])
        result.append(ProviderResponse(
            id=p.id,
            name=p.name,
            base_url=p.base_url,
            api_key=p.api_key[:8] + "***" if len(p.api_key) > 8 else "***",
            api_format=p.api_format,
            enabled=p.enabled,
            total_requests=p.total_requests,
            success_requests=p.success_requests,
            error_requests=p.error_requests,
            created_at=p.created_at,
            endpoint_count=len(p.endpoints),
            healthy_endpoint_count=healthy,
        ))
    return result


@router.post("/providers", response_model=ProviderResponse)
async def create_provider(
    data: ProviderCreate,
    db: AsyncSession = Depends(get_db)
):
    """添加服务商"""
    provider = await crud.create_provider(
        db,
        name=data.name,
        base_url=data.base_url.rstrip("/"),
        api_key=data.api_key,
        api_format=data.api_format
    )
    return ProviderResponse(
        id=provider.id,
        name=provider.name,
        base_url=provider.base_url,
        api_key=provider.api_key[:8] + "***",
        api_format=provider.api_format,
        enabled=provider.enabled,
        total_requests=0,
        success_requests=0,
        error_requests=0,
        created_at=provider.created_at,
        endpoint_count=0,
        healthy_endpoint_count=0,
    )


@router.put("/providers/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: int,
    data: ProviderUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新服务商"""
    update_data = data.model_dump(exclude_unset=True)
    if "base_url" in update_data:
        update_data["base_url"] = update_data["base_url"].rstrip("/")

    provider = await crud.update_provider(db, provider_id, **update_data)
    if not provider:
        raise HTTPException(status_code=404, detail="服务商不存在")

    healthy = len([e for e in provider.endpoints if e.enabled and not e.is_cooling])
    return ProviderResponse(
        id=provider.id,
        name=provider.name,
        base_url=provider.base_url,
        api_key=provider.api_key[:8] + "***",
        api_format=provider.api_format,
        enabled=provider.enabled,
        total_requests=provider.total_requests,
        success_requests=provider.success_requests,
        error_requests=provider.error_requests,
        created_at=provider.created_at,
        endpoint_count=len(provider.endpoints),
        healthy_endpoint_count=healthy,
    )


@router.delete("/providers/{provider_id}", response_model=MessageResponse)
async def delete_provider(
    provider_id: int,
    db: AsyncSession = Depends(get_db)
):
    """删除服务商"""
    success = await crud.delete_provider(db, provider_id)
    if not success:
        raise HTTPException(status_code=404, detail="服务商不存在")
    return MessageResponse(success=True, message="服务商已删除")


@router.post("/providers/{provider_id}/fetch-models", response_model=FetchModelsResponse)
async def fetch_provider_models(
    provider_id: int,
    db: AsyncSession = Depends(get_db)
):
    """从服务商拉取模型列表"""
    provider = await crud.get_provider(db, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="服务商不存在")

    # 构建请求
    url = f"{provider.base_url}/models"
    headers = {}
    if provider.api_format == ApiFormat.OPENAI:
        headers["Authorization"] = f"Bearer {provider.api_key}"
    else:
        headers["x-api-key"] = provider.api_key
        headers["anthropic-version"] = "2023-06-01"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            # 解析模型列表
            models = []
            if "data" in data:
                for m in data["data"]:
                    model_id = m.get("id") or m.get("name")
                    if model_id:
                        models.append(model_id)

            return FetchModelsResponse(
                provider_id=provider.id,
                provider_name=provider.name,
                models=sorted(models)
            )

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"拉取模型失败: HTTP {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"拉取模型失败: {e}")


# ==================== 模型端点管理 ====================

@router.get("/endpoints", response_model=List[ModelEndpointResponse])
async def list_endpoints(
    provider_id: Optional[int] = None,
    pool_type: Optional[PoolType] = None,
    db: AsyncSession = Depends(get_db)
):
    """获取模型端点列表"""
    if provider_id:
        endpoints = await crud.get_endpoints_by_provider(db, provider_id)
    elif pool_type:
        endpoints = await crud.get_endpoints_by_pool(db, pool_type)
    else:
        # 获取所有
        providers = await crud.get_all_providers(db)
        endpoints = []
        for p in providers:
            endpoints.extend(p.endpoints)

    result = []
    for ep in endpoints:
        provider = ep.provider if hasattr(ep, "provider") and ep.provider else None
        provider_name = provider.name if provider else "Unknown"
        success_rate = round(ep.success_requests / ep.total_requests * 100, 2) if ep.total_requests > 0 else 0

        result.append(ModelEndpointResponse(
            id=ep.id,
            provider_id=ep.provider_id,
            provider_name=provider_name,
            model_id=ep.model_id,
            pool_type=ep.pool_type,
            enabled=ep.enabled,
            priority=ep.priority,
            is_cooling=ep.is_cooling,
            cooldown_until=ep.cooldown_until,
            last_error=ep.last_error,
            total_requests=ep.total_requests,
            success_requests=ep.success_requests,
            error_requests=ep.error_requests,
            avg_latency_ms=ep.avg_latency_ms,
            success_rate=success_rate,
        ))

    return result


@router.post("/endpoints", response_model=ModelEndpointResponse)
async def create_endpoint(
    data: ModelEndpointCreate,
    db: AsyncSession = Depends(get_db)
):
    """添加模型到池"""
    # 检查服务商存在
    provider = await crud.get_provider(db, data.provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="服务商不存在")

    endpoint = await crud.create_endpoint(
        db,
        provider_id=data.provider_id,
        model_id=data.model_id,
        pool_type=data.pool_type,
        priority=data.priority
    )

    return ModelEndpointResponse(
        id=endpoint.id,
        provider_id=endpoint.provider_id,
        provider_name=provider.name,
        model_id=endpoint.model_id,
        pool_type=endpoint.pool_type,
        enabled=endpoint.enabled,
        priority=endpoint.priority,
        is_cooling=False,
        cooldown_until=None,
        last_error=None,
        total_requests=0,
        success_requests=0,
        error_requests=0,
        avg_latency_ms=0,
        success_rate=0,
    )


@router.post("/endpoints/batch", response_model=MessageResponse)
async def batch_create_endpoints(
    provider_id: int,
    pool_type: PoolType,
    model_ids: List[str],
    db: AsyncSession = Depends(get_db)
):
    """批量添加模型到池"""
    provider = await crud.get_provider(db, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="服务商不存在")

    created = 0
    for model_id in model_ids:
        await crud.create_endpoint(
            db,
            provider_id=provider_id,
            model_id=model_id,
            pool_type=pool_type,
            priority=0
        )
        created += 1

    return MessageResponse(success=True, message=f"已添加 {created} 个模型到 {pool_type.value} 池")


@router.put("/endpoints/{endpoint_id}", response_model=ModelEndpointResponse)
async def update_endpoint(
    endpoint_id: int,
    data: ModelEndpointUpdate,
    db: AsyncSession = Depends(get_db)
):
    """更新模型端点"""
    update_data = data.model_dump(exclude_unset=True)
    endpoint = await crud.update_endpoint(db, endpoint_id, **update_data)
    if not endpoint:
        raise HTTPException(status_code=404, detail="端点不存在")

    provider = endpoint.provider
    success_rate = round(endpoint.success_requests / endpoint.total_requests * 100, 2) if endpoint.total_requests > 0 else 0

    return ModelEndpointResponse(
        id=endpoint.id,
        provider_id=endpoint.provider_id,
        provider_name=provider.name if provider else "Unknown",
        model_id=endpoint.model_id,
        pool_type=endpoint.pool_type,
        enabled=endpoint.enabled,
        priority=endpoint.priority,
        is_cooling=endpoint.is_cooling,
        cooldown_until=endpoint.cooldown_until,
        last_error=endpoint.last_error,
        total_requests=endpoint.total_requests,
        success_requests=endpoint.success_requests,
        error_requests=endpoint.error_requests,
        avg_latency_ms=endpoint.avg_latency_ms,
        success_rate=success_rate,
    )


@router.delete("/endpoints/{endpoint_id}", response_model=MessageResponse)
async def delete_endpoint(
    endpoint_id: int,
    db: AsyncSession = Depends(get_db)
):
    """删除模型端点"""
    success = await crud.delete_endpoint(db, endpoint_id)
    if not success:
        raise HTTPException(status_code=404, detail="端点不存在")
    return MessageResponse(success=True, message="端点已删除")


# ==================== 池管理 ====================

@router.get("/pools", response_model=List[PoolResponse])
async def list_pools(db: AsyncSession = Depends(get_db)):
    """获取所有池状态"""
    from config import get_settings
    settings = get_settings()

    result = []
    for pool_type in PoolType:
        endpoints = await crud.get_endpoints_by_pool(db, pool_type)
        provider_ids = set(ep.provider_id for ep in endpoints)
        healthy = len([ep for ep in endpoints if ep.enabled and not ep.is_cooling])

        virtual_name = {
            PoolType.TOOL: settings.virtual_model_tool,
            PoolType.NORMAL: settings.virtual_model_normal,
            PoolType.ADVANCED: settings.virtual_model_advanced,
        }.get(pool_type, pool_type.value)

        result.append(PoolResponse(
            pool_type=pool_type,
            virtual_model_name=virtual_name,
            cooldown_seconds=settings.default_cooldown_seconds,
            max_retries=settings.max_retries_per_provider,
            endpoint_count=len(endpoints),
            healthy_endpoint_count=healthy,
            provider_count=len(provider_ids),
        ))

    return result


@router.get("/pools/{pool_type}", response_model=PoolEndpointsResponse)
async def get_pool_detail(
    pool_type: PoolType,
    db: AsyncSession = Depends(get_db)
):
    """获取池详情（按服务商分组）"""
    pool_mgr = get_pool_manager()
    status = await pool_mgr.get_pool_status(db, pool_type)

    from config import get_settings
    settings = get_settings()

    virtual_name = {
        PoolType.TOOL: settings.virtual_model_tool,
        PoolType.NORMAL: settings.virtual_model_normal,
        PoolType.ADVANCED: settings.virtual_model_advanced,
    }.get(pool_type, pool_type.value)

    return PoolEndpointsResponse(
        pool_type=pool_type,
        virtual_model_name=virtual_name,
        providers=status["providers"]
    )


# ==================== 统计和日志 ====================

@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """获取统计信息"""
    stats = await crud.get_stats(db)
    return StatsResponse(**stats)


@router.get("/logs", response_model=LogListResponse)
async def get_logs(
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    pool_type: Optional[PoolType] = None,
    success: Optional[bool] = None,
    provider_name: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """获取请求日志"""
    logs, total = await crud.get_logs(
        db,
        limit=limit,
        offset=offset,
        pool_type=pool_type,
        success=success,
        provider_name=provider_name
    )

    return LogListResponse(
        total=total,
        logs=[LogResponse(
            id=log.id,
            pool_type=log.pool_type,
            requested_model=log.requested_model or "",
            actual_model=log.actual_model or "",
            provider_name=log.provider_name or "",
            success=log.success,
            status_code=log.status_code,
            error_message=log.error_message,
            latency_ms=log.latency_ms,
            input_tokens=log.input_tokens,
            output_tokens=log.output_tokens,
            created_at=log.created_at,
        ) for log in logs]
    )


@router.delete("/logs", response_model=MessageResponse)
async def clear_logs(db: AsyncSession = Depends(get_db)):
    """清除所有日志"""
    from sqlalchemy import delete
    from models.database import RequestLog

    await db.execute(delete(RequestLog))
    return MessageResponse(success=True, message="日志已清除")
