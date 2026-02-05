"""池管理器 - 核心轮询逻辑"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from models.database import Provider, ModelEndpoint, Pool
from models.enums import PoolType
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
    timeout: Optional[float] = None  # 超时时间(秒)


class PoolManager:
    """池管理器 - 实现两级轮询 + 故障转移"""

    def __init__(self):
        self.cooldown_mgr = get_cooldown_manager()
        # 内存中的加权轮询状态: pool_type -> { "current_weight": int, "current_index": int, "gcd": int, "max_weight": int }
        # 简化版平滑加权轮询状态: pool_type -> { endpoint_id: current_effective_weight }
        self._swrr_state: Dict[PoolType, Dict[int, int]] = {}
        self._lock = asyncio.Lock()

    async def select_endpoint(
        self,
        db: AsyncSession,
        pool_type: PoolType
    ) -> Optional[SelectedEndpoint]:
        """
        选择一个可用的端点（基于平滑加权轮询 Smooth Weighted Round Robin）
        """
        async with self._lock:
            # 1. 获取池内所有启用的端点
            all_endpoints = await crud.get_endpoints_by_pool(db, pool_type)

            # 2. 过滤掉冷却中的端点和在间隔期内的端点
            now = datetime.utcnow()
            available_endpoints = []
            for ep in all_endpoints:
                if ep.provider is None:
                    logger.warning(
                        f"[PoolManager] 端点缺少服务商关系: endpoint_id={ep.id}, provider_id={ep.provider_id}"
                    )
                    continue
                if await self.cooldown_mgr.is_cooling(ep.id):
                    continue
                # 检查最小请求间隔
                if ep.min_interval_seconds and ep.min_interval_seconds > 0 and ep.last_request_at:
                    next_available_time = ep.last_request_at + timedelta(seconds=ep.min_interval_seconds)
                    if now < next_available_time:
                        logger.debug(
                            f"[PoolManager] 端点 {ep.id} 在间隔期内，跳过 (剩余 {(next_available_time - now).total_seconds():.1f}s)"
                        )
                        continue
                available_endpoints.append(ep)

            if not available_endpoints:
                logger.warning(f"[PoolManager] 池 {pool_type.value} 没有可用端点")
                return None

            # 3. 初始化或清理状态
            if pool_type not in self._swrr_state:
                self._swrr_state[pool_type] = {}

            # 移除不在当前可用列表中的端点状态（清理过期数据）
            current_ids = {ep.id for ep in available_endpoints}
            keys_to_remove = [eid for eid in self._swrr_state[pool_type] if eid not in current_ids]
            for k in keys_to_remove:
                del self._swrr_state[pool_type][k]

            # 初始化新端点
            for ep in available_endpoints:
                if ep.id not in self._swrr_state[pool_type]:
                    self._swrr_state[pool_type][ep.id] = 0

            # 4. 执行平滑加权轮询算法 (Nginx Smooth Weighted Round Robin)
            # 算法逻辑：
            # 1. 每个端点维护一个 current_weight
            # 2. 每次选择前，current_weight += effective_weight (即配置的 weight)
            # 3. 选择 current_weight 最大的那个
            # 4. 选中后，该端点的 current_weight -= total_weight (所有可用端点权重之和)

            # 注意：weight 可能为 None，默认设为 1
            total_weight = sum((ep.weight or 1) for ep in available_endpoints)
            best_endpoint = None
            max_current_weight = -float('inf')

            # 增加权重并寻找最大值
            for ep in available_endpoints:
                # 累加权重（如果 weight 为 None，默认为 1）
                ep_weight = ep.weight or 1
                self._swrr_state[pool_type][ep.id] += ep_weight

                # 寻找最大值
                if self._swrr_state[pool_type][ep.id] > max_current_weight:
                    max_current_weight = self._swrr_state[pool_type][ep.id]
                    best_endpoint = ep

            if not best_endpoint:
                # 理论上不应该发生，除非 total_weight <= 0 或者列表为空
                if available_endpoints:
                    best_endpoint = available_endpoints[0]
                else:
                    return None

            # 减去总权重
            self._swrr_state[pool_type][best_endpoint.id] -= total_weight

            provider = best_endpoint.provider
            if provider is None:
                logger.warning(
                    f"[PoolManager] 端点缺少服务商关系: endpoint_id={best_endpoint.id}, provider_id={best_endpoint.provider_id}"
                )
                return None

            logger.info(
                f"[PoolManager] 选中端点: {provider.name}/{best_endpoint.model_id} "
                f"(权重={best_endpoint.weight}, 池={pool_type.value})"
            )

            # 获取池配置的超时时间
            # 我们需要获取 Pool 对象，但 crud.get_or_create_pool 是 async 的，且可能创建新对象
            # 为了性能，这里可以考虑缓存，或者直接再次查询
            # 简单起见，这里先再次查询 Pool 配置
            # 注意：crud.get_endpoints_by_pool 不返回 Pool 对象，只返回 Endpoints
            # 为了获取 timeout，我们需要查询 Pool 表

            # 使用简单的查询获取 pool timeout
            pool_config = await crud.get_or_create_pool(db, pool_type, pool_type.value)
            timeout = float(pool_config.timeout_seconds) if pool_config and pool_config.timeout_seconds else 60.0

            return SelectedEndpoint(
                endpoint_id=best_endpoint.id,
                provider_id=provider.id,
                provider_name=provider.name,
                base_url=provider.base_url,
                api_key=provider.api_key,
                model_id=best_endpoint.model_id,
                api_format=provider.api_format.value,
                timeout=timeout
            )

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
        """标记请求失败（不设置冷却，直接重试下一个端点）"""
        await crud.increment_endpoint_stats(db, endpoint_id, success=False, latency_ms=0)
        # 不再设置冷却时间，失败后立即可以重试其他端点
        # 只记录错误日志
        logger.warning(f"[PoolManager] 端点 {endpoint_id} 请求失败: {error_message}")

    async def _group_endpoints_by_provider(
        self,
        endpoints: List[ModelEndpoint]
    ) -> Dict[int, List[ModelEndpoint]]:
        """按服务商分组端点"""
        groups: Dict[int, List[ModelEndpoint]] = {}
        for ep in endpoints:
            groups.setdefault(ep.provider_id, []).append(ep)
        return groups

    async def get_pool_status(self, db: AsyncSession, pool_type: PoolType) -> Dict[str, Any]:
        """获取池状态"""
        endpoints = await crud.get_endpoints_by_pool(db, pool_type)
        provider_groups = await self._group_endpoints_by_provider(endpoints)

        providers_status = []
        for provider_id, eps in provider_groups.items():
            if not eps:
                continue

            provider = eps[0].provider
            if provider is None:
                logger.warning(f"[PoolManager] 端点关联的服务商不存在: provider_id={provider_id}")
                continue

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
                    "min_interval_seconds": ep.min_interval_seconds or 0,
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
