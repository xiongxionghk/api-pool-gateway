"""池管理器 - 核心轮询逻辑"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from models.database import Provider, ModelEndpoint, Pool, PoolType
from db import crud
from .cooldown import get_cooldown_manager

logger = logging.getLogger(__name__)


@dataclass
class SelectedEndpoint:
    """选中的端点信息"""
    endpoint_id: int
    provider_id: int
    provider_name: str
    base_url: str
    api_key: str
    model_id: str
    api_format: str  # "openai" or "anthropic"


class PoolManager:
    """池管理器 - 实现两级轮询 + 故障转移"""

    def __init__(self):
        self.cooldown_mgr = get_cooldown_manager()
        # 内存中的轮询指针: pool_type -> (provider_index, model_indices_per_provider)
        self._pool_indices: Dict[PoolType, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def _get_pool_state(self, pool_type: PoolType) -> Dict[str, Any]:
        """获取池的轮询状态"""
        if pool_type not in self._pool_indices:
            self._pool_indices[pool_type] = {
                "provider_index": 0,
                "model_indices": {}  # provider_id -> model_index
            }
        return self._pool_indices[pool_type]

    async def _group_endpoints_by_provider(
        self,
        endpoints: List[ModelEndpoint]
    ) -> Dict[int, List[ModelEndpoint]]:
        """按服务商分组端点"""
        groups: Dict[int, List[ModelEndpoint]] = {}
        for ep in endpoints:
            if ep.provider_id not in groups:
                groups[ep.provider_id] = []
            groups[ep.provider_id].append(ep)
        return groups

    async def select_endpoint(
        self,
        db: AsyncSession,
        pool_type: PoolType
    ) -> Optional[SelectedEndpoint]:
        """
        选择一个可用的端点（两级轮询 + 故障转移）

        返回: SelectedEndpoint 或 None（所有端点都不可用）
        """
        async with self._lock:
            # 获取池内所有启用的端点
            endpoints = await crud.get_endpoints_by_pool(db, pool_type)
            if not endpoints:
                logger.warning(f"[PoolManager] 池 {pool_type.value} 没有可用端点")
                return None

            # 按服务商分组
            provider_groups = await self._group_endpoints_by_provider(endpoints)
            provider_ids = list(provider_groups.keys())

            if not provider_ids:
                return None

            # 获取池状态
            state = await self._get_pool_state(pool_type)
            provider_index = state["provider_index"]
            model_indices = state["model_indices"]

            # 尝试所有服务商
            tried_providers = 0
            total_providers = len(provider_ids)

            while tried_providers < total_providers:
                # 当前服务商
                current_provider_idx = provider_index % total_providers
                current_provider_id = provider_ids[current_provider_idx]
                provider_endpoints = provider_groups[current_provider_id]

                # 获取该服务商的模型轮询指针
                if current_provider_id not in model_indices:
                    model_indices[current_provider_id] = 0
                model_index = model_indices[current_provider_id]

                # 尝试该服务商的所有模型
                tried_models = 0
                total_models = len(provider_endpoints)

                while tried_models < total_models:
                    current_model_idx = model_index % total_models
                    endpoint = provider_endpoints[current_model_idx]

                    # 检查是否在冷却中
                    if not await self.cooldown_mgr.is_cooling(endpoint.id):
                        # 找到可用端点
                        provider = endpoint.provider

                        # 更新轮询指针（下次请求用下一个服务商）
                        state["provider_index"] = (provider_index + 1) % total_providers
                        # 更新该服务商的模型指针
                        model_indices[current_provider_id] = (model_index + 1) % total_models

                        logger.info(
                            f"[PoolManager] 选中端点: {provider.name}/{endpoint.model_id} "
                            f"(池={pool_type.value}, 服务商索引={current_provider_idx}, 模型索引={current_model_idx})"
                        )

                        return SelectedEndpoint(
                            endpoint_id=endpoint.id,
                            provider_id=provider.id,
                            provider_name=provider.name,
                            base_url=provider.base_url,
                            api_key=provider.api_key,
                            model_id=endpoint.model_id,
                            api_format=provider.api_format.value
                        )

                    # 该模型在冷却中，尝试下一个
                    model_index += 1
                    tried_models += 1

                # 该服务商所有模型都在冷却，尝试下一个服务商
                logger.warning(
                    f"[PoolManager] 服务商 {current_provider_id} 所有模型都在冷却中"
                )
                provider_index += 1
                tried_providers += 1

            # 所有端点都不可用
            logger.error(f"[PoolManager] 池 {pool_type.value} 所有端点都不可用")
            return None

    async def mark_success(
        self,
        db: AsyncSession,
        endpoint_id: int,
        latency_ms: int
    ):
        """标记请求成功"""
        await crud.increment_endpoint_stats(db, endpoint_id, success=True, latency_ms=latency_ms)
        # 如果之前在冷却，清除冷却状态
        await self.cooldown_mgr.clear_cooldown(endpoint_id)

    async def mark_failure(
        self,
        db: AsyncSession,
        endpoint_id: int,
        error_message: str,
        cooldown_seconds: Optional[int] = None
    ):
        """标记请求失败并设置冷却"""
        await crud.increment_endpoint_stats(db, endpoint_id, success=False, latency_ms=0)
        await self.cooldown_mgr.set_cooldown(
            endpoint_id,
            seconds=cooldown_seconds,
            error_message=error_message
        )
        logger.warning(f"[PoolManager] 端点 {endpoint_id} 进入冷却: {error_message}")

    async def get_pool_status(self, db: AsyncSession, pool_type: PoolType) -> Dict[str, Any]:
        """获取池状态"""
        endpoints = await crud.get_endpoints_by_pool(db, pool_type)
        provider_groups = await self._group_endpoints_by_provider(endpoints)

        providers_status = []
        for provider_id, eps in provider_groups.items():
            if not eps:
                continue
            provider = eps[0].provider

            models_status = []
            for ep in eps:
                is_cooling = await self.cooldown_mgr.is_cooling(ep.id)
                remaining = await self.cooldown_mgr.get_remaining_seconds(ep.id)
                models_status.append({
                    "id": ep.id,
                    "model_id": ep.model_id,
                    "enabled": ep.enabled,
                    "is_cooling": is_cooling,
                    "cooldown_remaining": remaining,
                    "total_requests": ep.total_requests,
                    "success_requests": ep.success_requests,
                    "success_rate": round(ep.success_requests / ep.total_requests * 100, 2) if ep.total_requests > 0 else 0,
                    "avg_latency_ms": round(ep.avg_latency_ms, 2),
                })

            providers_status.append({
                "provider_id": provider.id,
                "provider_name": provider.name,
                "base_url": provider.base_url,
                "api_format": provider.api_format.value,
                "models": models_status,
                "healthy_count": len([m for m in models_status if not m["is_cooling"]]),
                "total_count": len(models_status),
            })

        return {
            "pool_type": pool_type.value,
            "providers": providers_status,
            "total_endpoints": len(endpoints),
            "healthy_endpoints": sum(p["healthy_count"] for p in providers_status),
        }


# 全局单例
_pool_manager: Optional[PoolManager] = None


def get_pool_manager() -> PoolManager:
    """获取池管理器单例"""
    global _pool_manager
    if _pool_manager is None:
        _pool_manager = PoolManager()
    return _pool_manager
