"""数据库连接与会话管理"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import event
from sqlalchemy.engine import Engine

from config import get_settings
from models.database import Base

settings = get_settings()

# 创建异步引擎
# SQLite 需要特殊配置来避免并发锁定问题
engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    # SQLite 需要使用 StaticPool 来避免多线程问题
    poolclass=StaticPool if "sqlite" in settings.database_url else None,
    # SQLite 需要开启 check_same_thread=False
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

# 确保 SQLite 开启外键约束
if "sqlite" in settings.database_url:
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# 创建异步会话工厂
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db():
    """初始化数据库（创建表）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话（依赖注入）"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话（上下文管理器）"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
