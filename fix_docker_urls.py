import asyncio
import os
import sys
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from backend.db.connection import get_db
from sqlalchemy import text

async def fix_provider_urls():
    print("正在修正数据库中的服务商 URL...")
    async for session in get_db():
        # 查找所有包含 localhost 的 URL
        result = await session.execute(text("SELECT id, name, base_url FROM providers WHERE base_url LIKE '%localhost%' OR base_url LIKE '%127.0.0.1%'"))
        providers = result.fetchall()

        for p in providers:
            old_url = p.base_url
            new_url = old_url.replace("localhost", "host.docker.internal").replace("127.0.0.1", "host.docker.internal")
            print(f"修改服务商 [{p.name}]: {old_url} -> {new_url}")

            await session.execute(
                text("UPDATE providers SET base_url = :new_url WHERE id = :id"),
                {"new_url": new_url, "id": p.id}
            )

        await session.commit()
        print(f"已更新 {len(providers)} 个服务商配置")

if __name__ == "__main__":
    asyncio.run(fix_provider_urls())
