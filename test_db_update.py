import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from backend.db import get_db, crud
from backend.models.enums import PoolType
from backend.config import get_settings
from backend.models.database import Base

async def test_direct_db_update():
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        pool_type = PoolType.TOOL
        print(f"Testing direct update for pool: {pool_type}")
        
        # 1. Get current config
        pool = await crud.get_or_create_pool(db, pool_type, "virtual-tool")
        print(f"Current timeout: {pool.timeout_seconds}")
        
        # 2. Update timeout
        new_timeout = 120
        print(f"Updating timeout to: {new_timeout}")
        updated_pool = await crud.update_pool(db, pool_type, timeout_seconds=new_timeout)
        
        if updated_pool:
            print(f"Updated timeout: {updated_pool.timeout_seconds}")
        else:
            print("Update returned None")
            
        # 3. Verify
        pool_after = await crud.get_or_create_pool(db, pool_type, "virtual-tool")
        print(f"Timeout after refetch: {pool_after.timeout_seconds}")
        
        if pool_after.timeout_seconds == new_timeout:
            print("SUCCESS: Database update logic is working correctly.")
        else:
            print("FAILURE: Database update logic failed.")

if __name__ == "__main__":
    asyncio.run(test_direct_db_update())
