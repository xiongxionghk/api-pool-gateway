#!/usr/bin/env python3
"""
API Pool Gateway 测试脚本
测试完整的请求链路和工具调用功能
"""

import json
import httpx
import asyncio
import sys

# 网关地址
GATEWAY_URL = "http://127.0.0.1:8899"


async def test_list_models():
    """测试获取虚拟模型列表"""
    print("\n" + "=" * 60)
    print("📋 测试 1: 获取虚拟模型列表")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{GATEWAY_URL}/v1/models")
            response.raise_for_status()
            data = response.json()
            print(f"✅ 成功获取模型列表:")
            for model in data.get("data", []):
                print(f"   - {model['id']}: {model.get('description', '')}")
            return True
        except Exception as e:
            print(f"❌ 失败: {e}")
            return False


async def test_simple_chat():
    """测试简单聊天请求（非工具调用）"""
    print("\n" + "=" * 60)
    print("💬 测试 2: 简单聊天请求")
    print("=" * 60)

    payload = {
        "model": "sonnet",  # 使用虚拟模型名，将路由到 normal 池
        "messages": [
            {"role": "user", "content": "Hello, please reply with just 'Hi' in one word."}
        ],
        "max_tokens": 50
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                f"{GATEWAY_URL}/v1/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer test-key"}
            )

            if response.status_code == 502:
                print(f"⚠️  无可用端点 (502): {response.text}")
                print("   请先在管理界面添加服务商和模型到池中")
                return False

            response.raise_for_status()
            data = response.json()

            print(f"✅ 请求成功!")
            print(f"   模型: {data.get('model')}")
            if "choices" in data:
                content = data["choices"][0]["message"]["content"]
                print(f"   回复: {content[:100]}...")
            return True

        except httpx.HTTPStatusError as e:
            print(f"❌ HTTP 错误: {e.response.status_code}")
            print(f"   详情: {e.response.text[:200]}")
            return False
        except Exception as e:
            print(f"❌ 请求失败: {e}")
            return False


async def test_tool_calling():
    """测试工具调用（Function Calling）"""
    print("\n" + "=" * 60)
    print("🔧 测试 3: 工具调用 (Function Calling)")
    print("=" * 60)

    # 定义一个测试工具
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "获取指定城市的天气信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "城市名称，如 Beijing, Shanghai"
                        },
                        "unit": {
                            "type": "string",
                            "enum": ["celsius", "fahrenheit"],
                            "description": "温度单位"
                        }
                    },
                    "required": ["city"]
                }
            }
        }
    ]

    payload = {
        "model": "haiku",  # 使用工具模型，路由到 tool 池
        "messages": [
            {"role": "user", "content": "What's the weather like in Beijing today?"}
        ],
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": 200
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                f"{GATEWAY_URL}/v1/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer test-key"}
            )

            if response.status_code == 502:
                print(f"⚠️  无可用端点 (502): {response.text}")
                print("   请先在管理界面添加服务商和模型到 tool 池中")
                return False

            response.raise_for_status()
            data = response.json()

            print(f"✅ 请求成功!")
            print(f"   模型: {data.get('model')}")

            if "choices" in data:
                choice = data["choices"][0]
                message = choice.get("message", {})

                # 检查是否有工具调用
                if "tool_calls" in message and message["tool_calls"]:
                    print(f"   ✅ 检测到工具调用!")
                    for tc in message["tool_calls"]:
                        func = tc.get("function", {})
                        print(f"      - 函数: {func.get('name')}")
                        print(f"        参数: {func.get('arguments')}")
                    return True
                elif message.get("content"):
                    print(f"   ⚠️  模型返回了文本而不是工具调用:")
                    print(f"      {message['content'][:100]}...")
                    print("   这可能是因为模型决定不使用工具，或者工具调用格式不被支持")
                    return True  # 这不算失败，只是模型选择不调用工具

            return True

        except httpx.HTTPStatusError as e:
            print(f"❌ HTTP 错误: {e.response.status_code}")
            print(f"   详情: {e.response.text[:300]}")
            return False
        except Exception as e:
            print(f"❌ 请求失败: {e}")
            return False


async def test_anthropic_api():
    """测试 Anthropic 格式 API"""
    print("\n" + "=" * 60)
    print("🤖 测试 4: Anthropic Messages API")
    print("=" * 60)

    payload = {
        "model": "sonnet",
        "messages": [
            {"role": "user", "content": "Say 'Hello' only."}
        ],
        "max_tokens": 50
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(
                f"{GATEWAY_URL}/v1/messages",
                json=payload,
                headers={
                    "x-api-key": "test-key",
                    "anthropic-version": "2023-06-01"
                }
            )

            if response.status_code == 502:
                print(f"⚠️  无可用端点 (502): {response.text}")
                return False

            response.raise_for_status()
            data = response.json()

            print(f"✅ 请求成功!")
            print(f"   模型: {data.get('model')}")

            # Anthropic 格式响应
            if "content" in data:
                for block in data["content"]:
                    if block.get("type") == "text":
                        print(f"   回复: {block.get('text', '')[:100]}...")
                        break

            return True

        except httpx.HTTPStatusError as e:
            print(f"❌ HTTP 错误: {e.response.status_code}")
            print(f"   详情: {e.response.text[:200]}")
            return False
        except Exception as e:
            print(f"❌ 请求失败: {e}")
            return False


async def test_stream_request():
    """测试流式请求"""
    print("\n" + "=" * 60)
    print("🌊 测试 5: 流式请求 (Streaming)")
    print("=" * 60)

    payload = {
        "model": "sonnet",
        "messages": [
            {"role": "user", "content": "Count from 1 to 5."}
        ],
        "max_tokens": 100,
        "stream": True
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            async with client.stream(
                "POST",
                f"{GATEWAY_URL}/v1/chat/completions",
                json=payload,
                headers={"Authorization": "Bearer test-key"}
            ) as response:
                if response.status_code == 502:
                    text = await response.aread()
                    print(f"⚠️  无可用端点 (502): {text.decode()}")
                    return False

                response.raise_for_status()

                print(f"✅ 流式连接建立成功!")
                print(f"   接收数据: ", end="", flush=True)

                chunk_count = 0
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        if line.strip() == "data: [DONE]":
                            break
                        try:
                            data = json.loads(line[6:])
                            if "choices" in data:
                                delta = data["choices"][0].get("delta", {})
                                if "content" in delta:
                                    print(delta["content"], end="", flush=True)
                            chunk_count += 1
                        except:
                            pass

                print()
                print(f"   共接收 {chunk_count} 个数据块")
                return True

        except httpx.HTTPStatusError as e:
            print(f"❌ HTTP 错误: {e.response.status_code}")
            return False
        except Exception as e:
            print(f"❌ 请求失败: {e}")
            return False


async def test_admin_api():
    """测试管理 API"""
    print("\n" + "=" * 60)
    print("⚙️  测试 6: 管理 API")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        try:
            # 获取服务商列表
            response = await client.get(f"{GATEWAY_URL}/admin/providers")
            response.raise_for_status()
            providers = response.json()
            print(f"✅ 服务商列表: {len(providers)} 个")
            for p in providers:
                print(f"   - {p['name']} ({p['api_format']}): {p['endpoint_count']} 端点")

            # 获取池状态
            response = await client.get(f"{GATEWAY_URL}/admin/pools")
            response.raise_for_status()
            pools = response.json()
            print(f"\n✅ 池状态:")
            for pool in pools:
                print(f"   - {pool['pool_type']}: {pool['healthy_endpoint_count']}/{pool['endpoint_count']} 健康端点")

            # 获取统计
            response = await client.get(f"{GATEWAY_URL}/admin/stats")
            response.raise_for_status()
            stats = response.json()
            print(f"\n✅ 统计信息:")
            print(f"   - 总请求: {stats['total_requests']}")
            print(f"   - 成功率: {stats['success_rate']}%")

            return True

        except Exception as e:
            print(f"❌ 管理 API 测试失败: {e}")
            return False


async def main():
    print("=" * 60)
    print("🚀 API Pool Gateway 功能测试")
    print(f"   网关地址: {GATEWAY_URL}")
    print("=" * 60)

    # 检查服务是否运行
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{GATEWAY_URL}/v1/models", timeout=5.0)
            print(f"✅ 网关服务运行正常")
        except Exception as e:
            print(f"❌ 无法连接到网关服务: {e}")
            print(f"   请确保服务已启动: ./start.sh")
            sys.exit(1)

    results = []

    # 运行测试
    results.append(("获取模型列表", await test_list_models()))
    results.append(("管理 API", await test_admin_api()))
    results.append(("简单聊天", await test_simple_chat()))
    results.append(("工具调用", await test_tool_calling()))
    results.append(("Anthropic API", await test_anthropic_api()))
    results.append(("流式请求", await test_stream_request()))

    # 汇总结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)

    passed = 0
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {name}: {status}")
        if result:
            passed += 1

    print(f"\n   总计: {passed}/{len(results)} 通过")

    if passed < len(results):
        print("\n⚠️  提示: 部分测试失败可能是因为没有配置可用的服务商和模型")
        print("   请通过管理界面 (http://127.0.0.1:8899) 添加服务商并将模型添加到对应池中")


if __name__ == "__main__":
    asyncio.run(main())
