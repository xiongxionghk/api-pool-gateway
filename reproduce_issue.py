import asyncio
import aiohttp
import json

async def test_update_timeout():
    url = "http://localhost:8000/admin/pools/tool"  # 假设测试 tool 类型的池
    # 模拟前端发送的 payload
    payload = {
        "cooldown_seconds": 5,
        "timeout_seconds": 120  # 设置为 120 秒
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            # 1. 先获取当前配置
            async with session.get(url) as resp:
                if resp.status != 200:
                    print(f"Failed to get pool info: {resp.status}")
                    text = await resp.text()
                    print(text)
                    return

                data = await resp.json()
                print(f"Before update: timeout_seconds = {data.get('timeout_seconds')}")

            # 2. 发送更新请求
            print(f"Sending update request: {payload}")
            async with session.put(url, json=payload) as resp:
                if resp.status != 200:
                    print(f"Failed to update pool: {resp.status}")
                    text = await resp.text()
                    print(text)
                    return
                
                result = await resp.json()
                print(f"Update response: timeout_seconds = {result.get('timeout_seconds')}")

            # 3. 再次获取配置确认是否持久化
            async with session.get(url) as resp:
                data = await resp.json()
                print(f"After update verification: timeout_seconds = {data.get('timeout_seconds')}")
                
                if data.get('timeout_seconds') == 120:
                    print("SUCCESS: Timeout updated correctly.")
                else:
                    print("FAILURE: Timeout NOT updated.")

        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_update_timeout())
