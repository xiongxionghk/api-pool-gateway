"""应用配置"""

from functools import lru_cache
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    """应用配置，从环境变量加载"""

    # 服务配置
    host: str = "0.0.0.0"
    api_port: int = 8899      # API 网关端口
    admin_port: int = 8900    # 管理后台端口（未使用，前端嵌入后端）

    # 管理后台认证
    admin_password: str = "admin123"

    # 数据库（使用绝对路径）
    database_url: str = f"sqlite+aiosqlite:///{DATA_DIR}/gateway.db"

    # 池配置
    default_cooldown_seconds: int = 60       # 默认冷却时间
    max_retries_per_provider: int = 3        # 单服务商最大重试次数

    # 日志
    log_level: str = "INFO"
    max_logs_count: int = 10000              # 最大日志条数

    # 虚拟模型名（对外暴露）
    virtual_model_tool: str = "haiku"        # 工具模型别名
    virtual_model_normal: str = "sonnet"     # 普通模型别名
    virtual_model_advanced: str = "opus"     # 高级模型别名

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """获取缓存的配置实例"""
    return Settings()
