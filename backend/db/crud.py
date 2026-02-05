"""数据库 CRUD 操作"""

from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.database import Provider, ModelEndpoint, Pool, RequestLog
from models.enums import PoolType


# ==================== Provider CRUD ====================

async def create_provider(db: AsyncSession, **kwargs) -> Provider:
    """创建服务商"""
    provider = Provider(**kwargs)
    db.add(provider)
    await db.flush()
    await db.refresh(provider)
    return provider


async def get_provider(db: AsyncSession, provider_id: int) -> Optional[Provider]:
    """获取单个服务商"""
    result = await db.execute(
        select(Provider)
        .options(selectinload(Provider.endpoints))
        .where(Provider.id == provider_id)
    )
    return result.scalar_one_or_none()


async def get_all_providers(db: AsyncSession) -> List[Provider]:
    """获取所有服务商"""
    result = await db.execute(
        select(Provider).options(selectinload(Provider.endpoints))
    )
    return list(result.scalars().all())


async def update_provider(db: AsyncSession, provider_id: int, **kwargs) -> Optional[Provider]:
    """更新服务商"""
    await db.execute(
        update(Provider).where(Provider.id == provider_id).values(**kwargs)
    )
    return await get_provider(db, provider_id)


async def delete_provider(db: AsyncSession, provider_id: int) -> bool:
    """删除服务商"""
    result = await db.execute(
        delete(Provider).where(Provider.id == provider_id)
    )
    return result.rowcount > 0


# ==================== ModelEndpoint CRUD ====================

async def create_endpoint(db: AsyncSession, **kwargs) -> ModelEndpoint:
    """创建模型端点"""
    endpoint = ModelEndpoint(**kwargs)
    db.add(endpoint)
    await db.flush()
    await db.refresh(endpoint)
    return endpoint


async def get_endpoint(db: AsyncSession, endpoint_id: int) -> Optional[ModelEndpoint]:
    """获取单个端点"""
    result = await db.execute(
        select(ModelEndpoint)
        .options(selectinload(ModelEndpoint.provider))
        .where(ModelEndpoint.id == endpoint_id)
    )
    return result.scalar_one_or_none()


async def get_endpoints_by_pool(db: AsyncSession, pool_type: PoolType) -> List[ModelEndpoint]:
    """获取池内所有端点"""
    result = await db.execute(
        select(ModelEndpoint)
        .options(selectinload(ModelEndpoint.provider))
        .where(
            ModelEndpoint.pool_type == pool_type,
            ModelEndpoint.enabled == True
        )
        .order_by(ModelEndpoint.weight.desc())  # Use weight for sorting
    )
    return list(result.scalars().all())


async def get_endpoints_by_provider(db: AsyncSession, provider_id: int) -> List[ModelEndpoint]:
    """获取服务商的所有端点"""
    result = await db.execute(
        select(ModelEndpoint)
        .where(ModelEndpoint.provider_id == provider_id)
    )
    return list(result.scalars().all())


async def update_endpoint(db: AsyncSession, endpoint_id: int, **kwargs) -> Optional[ModelEndpoint]:
    """更新端点"""
    await db.execute(
        update(ModelEndpoint).where(ModelEndpoint.id == endpoint_id).values(**kwargs)
    )
    return await get_endpoint(db, endpoint_id)


async def delete_endpoint(db: AsyncSession, endpoint_id: int) -> bool:
    """删除端点"""
    result = await db.execute(
        delete(ModelEndpoint).where(ModelEndpoint.id == endpoint_id)
    )
    return result.rowcount > 0


async def set_endpoint_cooldown(
    db: AsyncSession,
    endpoint_id: int,
    cooldown_until: datetime,
    error_message: str
):
    """设置端点冷却"""
    await db.execute(
        update(ModelEndpoint)
        .where(ModelEndpoint.id == endpoint_id)
        .values(
            is_cooling=True,
            cooldown_until=cooldown_until,
            last_error=error_message
        )
    )


async def clear_endpoint_cooldown(db: AsyncSession, endpoint_id: int):
    """清除端点冷却"""
    await db.execute(
        update(ModelEndpoint)
        .where(ModelEndpoint.id == endpoint_id)
        .values(is_cooling=False, cooldown_until=None)
    )


async def increment_endpoint_stats(
    db: AsyncSession,
    endpoint_id: int,
    success: bool,
    latency_ms: int
):
    """增加端点统计"""
    endpoint = await get_endpoint(db, endpoint_id)
    if not endpoint:
        return

    new_total = endpoint.total_requests + 1
    new_success = endpoint.success_requests + (1 if success else 0)
    new_error = endpoint.error_requests + (0 if success else 1)

    # 计算新的平均延迟
    if success:
        old_avg = endpoint.avg_latency_ms
        old_count = endpoint.success_requests
        new_avg = (old_avg * old_count + latency_ms) / new_success if new_success > 0 else latency_ms

        # 更新最后请求时间
        await db.execute(
            update(ModelEndpoint)
            .where(ModelEndpoint.id == endpoint_id)
            .values(
                total_requests=new_total,
                success_requests=new_success,
                error_requests=new_error,
                avg_latency_ms=new_avg,
                last_request_at=datetime.utcnow()
            )
        )
    else:
        new_avg = endpoint.avg_latency_ms

        await db.execute(
            update(ModelEndpoint)
            .where(ModelEndpoint.id == endpoint_id)
            .values(
                total_requests=new_total,
                success_requests=new_success,
                error_requests=new_error,
                avg_latency_ms=new_avg
            )
        )


# ==================== Pool CRUD ====================

async def get_or_create_pool(db: AsyncSession, pool_type: PoolType, virtual_model_name: str) -> Pool:
    """获取或创建池"""
    result = await db.execute(
        select(Pool).where(Pool.pool_type == pool_type)
    )
    pool = result.scalar_one_or_none()

    if not pool:
        pool = Pool(pool_type=pool_type, virtual_model_name=virtual_model_name)
        db.add(pool)
        await db.flush()
        await db.refresh(pool)

    return pool


async def get_pool_by_type(db: AsyncSession, pool_type: PoolType) -> Optional[Pool]:
    """获取池配置"""
    result = await db.execute(select(Pool).where(Pool.pool_type == pool_type))
    return result.scalar_one_or_none()


async def get_all_pools(db: AsyncSession) -> List[Pool]:
    """获取所有池"""
    result = await db.execute(select(Pool))
    return list(result.scalars().all())


async def update_pool_index(db: AsyncSession, pool_type: PoolType, new_index: int):
    """更新池的服务商轮询指针"""
    await db.execute(
        update(Pool)
        .where(Pool.pool_type == pool_type)
        .values(current_provider_index=new_index)
    )


async def update_pool(db: AsyncSession, pool_type: PoolType, **kwargs) -> Optional[Pool]:
    """更新池配置"""
    await db.execute(
        update(Pool)
        .where(Pool.pool_type == pool_type)
        .values(**kwargs)
    )

    result = await db.execute(
        select(Pool).where(Pool.pool_type == pool_type)
    )
    return result.scalar_one_or_none()


# ==================== RequestLog CRUD ====================

async def create_log(db: AsyncSession, **kwargs) -> RequestLog:
    """创建请求日志"""
    log = RequestLog(**kwargs)
    db.add(log)
    await db.flush()
    return log


async def get_logs(
    db: AsyncSession,
    limit: int = 100,
    offset: int = 0,
    pool_type: Optional[PoolType] = None,
    success: Optional[bool] = None,
    provider_name: Optional[str] = None
) -> tuple[List[RequestLog], int]:
    """获取日志列表"""
    query = select(RequestLog)

    if pool_type:
        query = query.where(RequestLog.pool_type == pool_type)
    if success is not None:
        query = query.where(RequestLog.success == success)
    if provider_name:
        query = query.where(RequestLog.provider_name == provider_name)

    # 总数
    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar() or 0

    # 分页
    query = query.order_by(RequestLog.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)

    return list(result.scalars().all()), total


async def get_stats(db: AsyncSession) -> Dict[str, Any]:
    """获取统计信息"""
    # 服务商统计
    provider_result = await db.execute(select(Provider))
    providers = list(provider_result.scalars().all())

    # 端点统计
    endpoint_result = await db.execute(select(ModelEndpoint))
    endpoints = list(endpoint_result.scalars().all())

    total_requests = sum(e.total_requests for e in endpoints)
    success_requests = sum(e.success_requests for e in endpoints)
    error_requests = sum(e.error_requests for e in endpoints)

    # 按池分组统计
    pool_stats = {}
    for pool_type in PoolType:
        pool_endpoints = [e for e in endpoints if e.pool_type == pool_type]
        healthy = [e for e in pool_endpoints if e.enabled and not e.is_cooling]
        pool_stats[pool_type.value] = {
            "total_endpoints": len(pool_endpoints),
            "healthy_endpoints": len(healthy),
            "total_requests": sum(e.total_requests for e in pool_endpoints),
            "success_requests": sum(e.success_requests for e in pool_endpoints),
        }

    return {
        "total_providers": len(providers),
        "enabled_providers": len([p for p in providers if p.enabled]),
        "total_endpoints": len(endpoints),
        "healthy_endpoints": len([e for e in endpoints if e.enabled and not e.is_cooling]),
        "cooling_endpoints": len([e for e in endpoints if e.is_cooling]),
        "total_requests": total_requests,
        "success_requests": success_requests,
        "error_requests": error_requests,
        "success_rate": round(success_requests / total_requests * 100, 2) if total_requests > 0 else 0,
        "pool_stats": pool_stats,
    }
