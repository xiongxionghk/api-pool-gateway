"""冷却管理器"""

from datetime import datetime, timedelta
from typing import Dict, Optional
import asyncio


class CooldownManager:
    """管理模型端点的冷却状态（内存缓存 + 数据库持久化）"""

    def __init__(self, default_cooldown_seconds: int = 60):
        self.default_cooldown_seconds = default_cooldown_seconds
        # 内存缓存: endpoint_id -> cooldown_until
        self._cooldowns: Dict[int, datetime] = {}
        self._lock = asyncio.Lock()

    async def set_cooldown(
        self,
        endpoint_id: int,
        seconds: Optional[int] = None,
        error_message: str = ""
    ):
        """设置端点冷却"""
        cooldown_seconds = seconds or self.default_cooldown_seconds
        cooldown_until = datetime.utcnow() + timedelta(seconds=cooldown_seconds)

        async with self._lock:
            self._cooldowns[endpoint_id] = cooldown_until

    async def is_cooling(self, endpoint_id: int) -> bool:
        """检查端点是否在冷却中"""
        async with self._lock:
            cooldown_until = self._cooldowns.get(endpoint_id)
            if cooldown_until is None:
                return False

            if datetime.utcnow() >= cooldown_until:
                # 冷却已结束，清除
                del self._cooldowns[endpoint_id]
                return False

            return True

    async def get_remaining_seconds(self, endpoint_id: int) -> int:
        """获取剩余冷却时间（秒）"""
        async with self._lock:
            cooldown_until = self._cooldowns.get(endpoint_id)
            if cooldown_until is None:
                return 0

            remaining = (cooldown_until - datetime.utcnow()).total_seconds()
            return max(0, int(remaining))

    async def clear_cooldown(self, endpoint_id: int):
        """清除端点冷却"""
        async with self._lock:
            self._cooldowns.pop(endpoint_id, None)

    async def clear_all(self):
        """清除所有冷却"""
        async with self._lock:
            self._cooldowns.clear()

    async def get_all_cooling(self) -> Dict[int, int]:
        """获取所有冷却中的端点及剩余时间"""
        now = datetime.utcnow()
        result = {}

        async with self._lock:
            expired = []
            for endpoint_id, cooldown_until in self._cooldowns.items():
                if now >= cooldown_until:
                    expired.append(endpoint_id)
                else:
                    remaining = int((cooldown_until - now).total_seconds())
                    result[endpoint_id] = remaining

            # 清理过期的
            for endpoint_id in expired:
                del self._cooldowns[endpoint_id]

        return result


# 全局单例
_cooldown_manager: Optional[CooldownManager] = None


def get_cooldown_manager() -> CooldownManager:
    """获取冷却管理器单例"""
    global _cooldown_manager
    if _cooldown_manager is None:
        from config import get_settings
        settings = get_settings()
        _cooldown_manager = CooldownManager(settings.default_cooldown_seconds)
    return _cooldown_manager
