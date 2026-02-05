"""请求转发器 - 处理请求转发到后端服务商"""

import time
import logging
import json
import asyncio
from typing import Optional, Dict, Any, AsyncIterator, List

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import RequestLog
from models.enums import PoolType
from db import crud
from .pool_manager import get_pool_manager, SelectedEndpoint

logger = logging.getLogger(__name__)


# 重试配置
class RetryConfig:
    """重试配置"""
    # 单个端点的重试次数
    ENDPOINT_RETRIES = 3
    # 跨端点的最大尝试次数
    MAX_ENDPOINT_ATTEMPTS = 10
    # 指数退避基数(秒)
    BACKOFF_BASE = 1.5
    # 最大退避时间(秒)
    BACKOFF_MAX = 30.0
    # 流式请求:验证前N个chunk才开始传输
    STREAM_VALIDATION_CHUNKS = 3
    # 可重试的HTTP状态码
    RETRIABLE_STATUS_CODES = {429, 500, 502, 503, 504}
    # 可重试的异常类型
    RETRIABLE_EXCEPTIONS = (
        httpx.ConnectError,
        httpx.TimeoutException,
        httpx.HTTPStatusError,
        httpx.ReadError,
        httpx.WriteError,
        httpx.PoolTimeout,
        httpx.NetworkError,
    )


class Forwarder:
    """请求转发器"""

    def __init__(self, timeout: float = 300.0):
        self.timeout = timeout
        self.pool_mgr = get_pool_manager()

    async def forward_request(
        self,
        db: AsyncSession,
        pool_type: PoolType,
        request_body: Dict[str, Any],
        incoming_format: str,  # "openai" or "anthropic" (保留参数以保持接口兼容性)
        stream: bool = False
    ) -> tuple[Optional[Dict[str, Any]], Optional[AsyncIterator[bytes]], Optional[str]]:
        """
        转发请求到后端服务商，包含完整的重试和故障转移机制

        策略：
        1. 尝试多个端点 (Max 10)
        2. 每个端点尝试多次 (Max 3)
        3. 遇到网络错误/5xx/429 指数退避重试
        4. 遇到 4xx (非429) 客户端错误直接返回不重试
        """
        # 记录原始请求的模型名
        original_model = request_body.get("model", "unknown")

        # 上一次错误信息，用于最终返回
        last_error = ""

        # 跨端点尝试循环
        for attempt in range(RetryConfig.MAX_ENDPOINT_ATTEMPTS):
            endpoint = await self.pool_mgr.select_endpoint(db, pool_type)
            if not endpoint:
                last_error = "没有可用的端点"
                break

            start_time = time.time()

            # 单端点重试循环
            for retry in range(RetryConfig.ENDPOINT_RETRIES):
                try:
                    # 指数退避等待 (除了第一次)
                    if retry > 0:
                        backoff = min(RetryConfig.BACKOFF_BASE ** retry, RetryConfig.BACKOFF_MAX)
                        logger.warning(
                            f"[Forwarder] 端点重试等待 {backoff:.2f}s: "
                            f"{endpoint.provider_name}/{endpoint.model_id} (retry={retry})"
                        )
                        await asyncio.sleep(backoff)

                    # 1. 准备请求数据
                    body = request_body.copy()
                    body["model"] = endpoint.model_id

                    if endpoint.api_format == "openai":
                        url = f"{endpoint.base_url}/chat/completions"
                        headers = {
                            "Content-Type": "application/json",
                            "Authorization": f"Bearer {endpoint.api_key}"
                        }
                    else:
                        url = f"{endpoint.base_url}/messages"
                        headers = {
                            "Content-Type": "application/json",
                            "x-api-key": endpoint.api_key,
                            "anthropic-version": "2023-06-01"
                        }

                    logger.info(
                        f"[Forwarder] 发起请求: {endpoint.provider_name}/{endpoint.model_id} "
                        f"(pool_attempt={attempt+1}, retry={retry}, stream={stream})"
                    )

                    # 2. 执行请求
                    if stream:
                        return await self._handle_stream_request(
                            db, endpoint, url, headers, body,
                            original_model, start_time, retry, attempt
                        )
                    else:
                        return await self._handle_normal_request(
                            db, endpoint, url, headers, body,
                            original_model, start_time
                        )

                except RetryConfig.RETRIABLE_EXCEPTIONS as e:
                    # 可重试的网络/连接错误
                    latency_ms = int((time.time() - start_time) * 1000)
                    error_type = type(e).__name__
                    is_status_error = isinstance(e, httpx.HTTPStatusError)
                    status_code = e.response.status_code if is_status_error else None

                    # 检查状态码是否可重试
                    should_retry = True
                    if is_status_error and status_code not in RetryConfig.RETRIABLE_STATUS_CODES:
                        # 4xx 客户端错误 (非429) 不应该重试
                        should_retry = False
                        error_msg = f"HTTP {status_code}: {e.response.text[:200]}"
                    else:
                        error_msg = f"{error_type}: {str(e)}"

                    logger.error(f"[Forwarder] 请求失败 (retry={retry}): {error_msg}")

                    # 如果是最后一次单端点重试，记录失败并决定是否切换端点
                    if retry == RetryConfig.ENDPOINT_RETRIES - 1 or not should_retry:
                        await self.pool_mgr.mark_failure(db, endpoint.endpoint_id, error_msg)
                        await self._log_request(
                            db, pool_type, original_model, endpoint,
                            success=False, latency_ms=latency_ms,
                            status_code=status_code, error_message=error_msg
                        )
                        last_error = error_msg

                        # 如果是不可重试的状态码(如400/401)，直接结束整个流程，返回错误
                        if not should_retry:
                            return None, None, error_msg

                        # 否则跳出单端点循环，进入下一个端点
                        break

                    # 还有单端点重试机会，继续循环
                    continue

                except Exception as e:
                    # 未知错误，记录并切换端点
                    latency_ms = int((time.time() - start_time) * 1000)
                    error_msg = f"Unexpected Error: {str(e)}"
                    logger.error(f"[Forwarder] 未知异常: {error_msg}")

                    await self.pool_mgr.mark_failure(db, endpoint.endpoint_id, error_msg)
                    await self._log_request(
                        db, pool_type, original_model, endpoint,
                        success=False, latency_ms=latency_ms,
                        error_message=error_msg
                    )
                    last_error = error_msg
                    break # 切换到下一个端点

        # 所有端点尝试都失败
        return None, None, f"所有重试失败 (尝试了{RetryConfig.MAX_ENDPOINT_ATTEMPTS}个端点): {last_error}"

    async def _handle_normal_request(
        self,
        db: AsyncSession,
        endpoint: SelectedEndpoint,
        url: str,
        headers: Dict[str, str],
        body: Dict[str, Any],
        original_model: str,
        start_time: float
    ) -> tuple[Optional[Dict[str, Any]], None, Optional[str]]:
        """处理非流式请求"""
        req_timeout = endpoint.timeout if endpoint.timeout is not None else self.timeout

        async with httpx.AsyncClient(timeout=req_timeout) as client:
            response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()

            latency_ms = int((time.time() - start_time) * 1000)
            response_data = response.json()

            # 统一模型ID
            if "model" in response_data:
                response_data["model"] = original_model
            elif response_data.get("type") == "message" and "model" in response_data:
                response_data["model"] = original_model

            # 记录成功
            await self.pool_mgr.mark_success(db, endpoint.endpoint_id, latency_ms)

            # 提取token用于日志
            input_tokens = None
            output_tokens = None
            try:
                usage = response_data.get("usage", {})
                if "input_tokens" in usage:
                    input_tokens = usage.get("input_tokens")
                    output_tokens = usage.get("output_tokens")
                elif "prompt_tokens" in usage:
                    input_tokens = usage.get("prompt_tokens")
                    output_tokens = usage.get("completion_tokens")
            except Exception:
                pass

            await self._log_request(
                db, PoolType(self._model_to_pool_type(original_model)),
                original_model, endpoint,
                success=True, latency_ms=latency_ms,
                status_code=200,
                input_tokens=input_tokens, output_tokens=output_tokens
            )

            return response_data, None, None

    async def _handle_stream_request(
        self,
        db: AsyncSession,
        endpoint: SelectedEndpoint,
        url: str,
        headers: Dict[str, str],
        body: Dict[str, Any],
        original_model: str,
        start_time: float,
        retry_count: int,
        attempt_count: int
    ) -> tuple[None, AsyncIterator[bytes], Optional[str]]:
        """
        处理流式请求 - 立即返回生成器，在生成器内部发起请求
        这样可以在等待上游响应时发送心跳，保持客户端连接
        """
        req_timeout = endpoint.timeout if endpoint.timeout is not None else self.timeout
        pool_mgr = self.pool_mgr
        endpoint_id = endpoint.endpoint_id
        # 心跳间隔(秒)
        HEARTBEAT_INTERVAL = 5.0
        # 首包超时(秒) - 等待上游首次响应的最大时间
        FIRST_CHUNK_TIMEOUT = 120.0

        async def stream_with_heartbeat():
            client = None
            response = None
            try:
                client = httpx.AsyncClient(timeout=req_timeout)
                request = client.build_request("POST", url, json=body, headers=headers)

                # 发起请求，同时发送心跳
                send_task = asyncio.create_task(client.send(request, stream=True))
                elapsed = 0.0

                while elapsed < FIRST_CHUNK_TIMEOUT:
                    try:
                        response = await asyncio.wait_for(
                            asyncio.shield(send_task),
                            timeout=HEARTBEAT_INTERVAL
                        )
                        break  # 收到响应，退出心跳循环
                    except asyncio.TimeoutError:
                        # 还没收到响应，发送心跳
                        elapsed += HEARTBEAT_INTERVAL
                        yield b": heartbeat\n\n"
                        continue

                if response is None:
                    # 超时未收到响应
                    send_task.cancel()
                    raise httpx.ReadTimeout("Upstream response timeout", request=request)

                # 检查状态码
                if response.status_code != 200:
                    error_text = await response.aread()
                    await response.aclose()
                    raise httpx.HTTPStatusError(
                        f"HTTP {response.status_code}: {error_text[:200]}",
                        request=request,
                        response=response
                    )

                # 开始处理流
                iterator = response.aiter_bytes()

                while True:
                    try:
                        chunk = await asyncio.wait_for(
                            iterator.__anext__(),
                            timeout=HEARTBEAT_INTERVAL
                        )
                        # 检查是否有错误
                        chunk_str = chunk.decode('utf-8', errors='ignore')
                        if '"error":' in chunk_str and '"message":' in chunk_str:
                            raise httpx.HTTPStatusError(
                                f"Stream contained error: {chunk_str[:100]}",
                                request=request,
                                response=response
                            )
                        # 处理并输出 chunk
                        for processed in self._process_stream_chunk(chunk, original_model):
                            yield processed
                    except asyncio.TimeoutError:
                        # 发送心跳
                        yield b": heartbeat\n\n"
                        continue
                    except StopAsyncIteration:
                        break

                # 流正常结束，记录成功
                latency_ms = int((time.time() - start_time) * 1000)
                from db import get_db_context
                async with get_db_context() as new_db:
                    await pool_mgr.mark_success(new_db, endpoint_id, latency_ms)
                    # 记录请求日志
                    await self._log_request(
                        new_db,
                        PoolType(self._model_to_pool_type(original_model)),
                        original_model, endpoint,
                        success=True, latency_ms=latency_ms,
                        status_code=200
                    )

            except Exception as e:
                latency_ms = int((time.time() - start_time) * 1000)
                logger.error(f"[Forwarder] 流式请求失败: {e}")
                from db import get_db_context
                async with get_db_context() as new_db:
                    await pool_mgr.mark_failure(new_db, endpoint_id, str(e))
                    # 记录失败日志
                    await self._log_request(
                        new_db,
                        PoolType(self._model_to_pool_type(original_model)),
                        original_model, endpoint,
                        success=False, latency_ms=latency_ms,
                        error_message=str(e)
                    )
                # 不抛出异常，客户端会看到流中断
            finally:
                if response:
                    await response.aclose()
                if client:
                    await client.aclose()

        return None, stream_with_heartbeat(), None

    async def _create_stream_response(
        self,
        client: httpx.AsyncClient,
        response: httpx.Response,
        iterator: AsyncIterator[bytes],
        buffered_chunks: List[bytes],
        db: AsyncSession,
        endpoint: SelectedEndpoint,
        original_model: str,
        start_time: float
    ) -> tuple[None, AsyncIterator[bytes], Optional[str]]:
        """创建流式响应生成器，包含心跳保活机制"""
        pool_mgr = self.pool_mgr
        endpoint_id = endpoint.endpoint_id
        # 心跳间隔(秒) - 每5秒发送一次心跳，防止客户端超时
        HEARTBEAT_INTERVAL = 5.0

        async def stream_generator():
            try:
                # 1. 先发送缓冲的 chunks
                for chunk in buffered_chunks:
                    for processed in self._process_stream_chunk(chunk, original_model):
                        yield processed

                # 2. 继续处理剩余的流，带心跳保活
                while True:
                    try:
                        # 等待下一个 chunk，超时则发送心跳
                        chunk = await asyncio.wait_for(
                            iterator.__anext__(),
                            timeout=HEARTBEAT_INTERVAL
                        )
                        for processed in self._process_stream_chunk(chunk, original_model):
                            yield processed
                    except asyncio.TimeoutError:
                        # 超时未收到数据，发送 SSE 心跳注释保持连接
                        yield b": heartbeat\n\n"
                        continue
                    except StopAsyncIteration:
                        # 流正常结束
                        break

                # 流结束后记录成功 - 使用独立的数据库会话
                latency_ms = int((time.time() - start_time) * 1000)
                from db import get_db_context
                async with get_db_context() as new_db:
                    await pool_mgr.mark_success(new_db, endpoint_id, latency_ms)

            except Exception as e:
                # 流传输中出错（此时已无法重试，因为已经开始给客户端发数据了）
                latency_ms = int((time.time() - start_time) * 1000)
                logger.error(f"[Forwarder] 流传输中断: {e}")
                from db import get_db_context
                async with get_db_context() as new_db:
                    await pool_mgr.mark_failure(new_db, endpoint_id, str(e))
                # 不再抛出异常，客户端只会看到流中断
            finally:
                # 确保资源释放
                await response.aclose()
                await client.aclose()

        return None, stream_generator(), None

    def _process_stream_chunk(self, chunk: bytes, original_model: str) -> AsyncIterator[bytes]:
        """处理单个流数据块，解析并替换模型名"""
        # 注意：这里简化处理，假设 chunk 边界正好是行边界
        # 实际生产中可能需要 LineBuffer 处理跨 chunk 的行
        # 但大多数 LLM API 返回的 chunk 都是完整的 data: 行

        text = chunk.decode("utf-8", errors="ignore")
        lines = text.split('\n')

        for i, line in enumerate(lines):
            # 处理分割导致的空行，最后一行如果为空不需要加回车
            if not line and i == len(lines) - 1:
                continue

            if line.startswith("data: "):
                if line.strip() == "data: [DONE]":
                    yield (line + "\n").encode("utf-8")
                    continue

                try:
                    content = line[6:]  # remove "data: "
                    data = json.loads(content)
                    changed = False

                    # OpenAI 格式
                    if "model" in data:
                        data["model"] = original_model
                        changed = True

                    # Anthropic 格式 (message_start event)
                    if data.get("type") == "message_start" and "message" in data:
                        if "model" in data["message"]:
                            data["message"]["model"] = original_model
                            changed = True

                    if changed:
                        new_line = f"data: {json.dumps(data)}\n"
                        yield new_line.encode("utf-8")
                    else:
                        yield (line + "\n").encode("utf-8")
                except Exception:
                    # 解析失败，原样返回
                    yield (line + "\n").encode("utf-8")
            else:
                # 其他行（如 event:, :ping, 空行），直接返回
                # 只有非空行才加回车，或者是中间的空行
                yield (line + "\n").encode("utf-8")


    async def _log_request(
        self,
        db: AsyncSession,
        pool_type: PoolType,
        requested_model: str,
        endpoint: SelectedEndpoint,
        success: bool,
        latency_ms: int,
        status_code: Optional[int] = None,
        error_message: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None
    ):
        """记录请求日志"""
        try:
            await crud.create_log(
                db,
                pool_type=pool_type,
                requested_model=requested_model,
                actual_model=endpoint.model_id,
                provider_name=endpoint.provider_name,
                success=success,
                status_code=status_code,
                error_message=error_message,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
        except Exception as e:
            logger.error(f"[Forwarder] 记录日志失败: {e}")

    def _model_to_pool_type(self, model: str) -> str:
        """根据模型名推断池类型"""
        model_lower = model.lower()
        if "haiku" in model_lower or "tool" in model_lower:
            return "tool"
        elif "opus" in model_lower or "advanced" in model_lower:
            return "advanced"
        else:
            return "normal"


# 全局单例
_forwarder: Optional[Forwarder] = None


def get_forwarder() -> Forwarder:
    """获取转发器单例"""
    global _forwarder
    if _forwarder is None:
        _forwarder = Forwarder()
    return _forwarder
