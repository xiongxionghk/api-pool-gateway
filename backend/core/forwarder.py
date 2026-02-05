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
    ENDPOINT_RETRIES = 2
    # 跨端点的最大尝试次数
    MAX_ENDPOINT_ATTEMPTS = 5
    # 指数退避基数(秒)
    BACKOFF_BASE = 1.5
    # 最大退避时间(秒)
    BACKOFF_MAX = 30.0
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
        stream: bool = False
    ) -> tuple[Optional[Dict[str, Any]], Optional[AsyncIterator[bytes]], Optional[str]]:
        """
        转发请求到后端服务商，包含完整的重试和故障转移机制

        策略：
        1. 尝试多个端点 (Max 5)
        2. 每个端点尝试多次 (Max 2)
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
                            original_model, start_time
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
                db, self.pool_mgr.model_to_pool_type(original_model),
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
        start_time: float
    ) -> tuple[None, AsyncIterator[bytes], Optional[str]]:
        """
        处理流式请求 - 立即发起请求，确认连接成功后再返回生成器
        这样外层的重试逻辑可以捕获连接错误
        """
        req_timeout = endpoint.timeout if endpoint.timeout is not None else self.timeout

        # 1. 建立连接并发送请求头
        client = httpx.AsyncClient(timeout=req_timeout)
        try:
            request = client.build_request("POST", url, json=body, headers=headers)
            # 立即发送请求（stream=True），如果连接失败会在这里抛出异常
            response = await client.send(request, stream=True)

            # 2. 检查状态码
            if response.status_code != 200:
                # 读取错误信息
                error_text = await response.aread()
                await response.aclose()
                await client.aclose()

                # 抛出 StatusError，外层重试逻辑会捕获
                raise httpx.HTTPStatusError(
                    f"HTTP {response.status_code}: {error_text[:200]}",
                    request=request,
                    response=response
                )

            # 3. 返回生成器处理后续数据流
            # 注意：client 和 response 的所有权转移给了生成器
            generator = self._stream_generator(
                client, response, endpoint, original_model, start_time
            )
            return None, generator, None

        except Exception:
            # 如果在建立连接阶段失败，确保清理资源并抛出异常供外层重试
            await client.aclose()
            raise

    async def _stream_generator(
        self,
        client: httpx.AsyncClient,
        response: httpx.Response,
        endpoint: SelectedEndpoint,
        original_model: str,
        start_time: float
    ) -> AsyncIterator[bytes]:
        """
        流式响应生成器 - 负责读取数据流并处理中断
        """
        pool_mgr = self.pool_mgr
        endpoint_id = endpoint.endpoint_id

        try:
            # 直接 pipe 数据流
            async for chunk in response.aiter_bytes():
                yield chunk

            # 流正常结束，记录成功
            latency_ms = int((time.time() - start_time) * 1000)

            # 使用新的数据库会话记录日志（因为原来的可能已经关闭或不在此上下文）
            from db import get_db_context
            async with get_db_context() as new_db:
                await pool_mgr.mark_success(new_db, endpoint_id, latency_ms)
                # 记录请求日志
                await self._log_request(
                    new_db,
                    pool_mgr.model_to_pool_type(original_model),
                    original_model, endpoint,
                    success=True, latency_ms=latency_ms,
                    status_code=200
                )

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            logger.error(f"[Forwarder] 流式传输中断: {error_msg}")

            # 发送 SSE 错误事件，让客户端知道出错了
            error_json = json.dumps({
                "error": {
                    "message": f"Upstream stream error: {error_msg}",
                    "type": "upstream_error"
                }
            })
            yield f"data: {error_json}\n\n".encode("utf-8")

            from db import get_db_context
            async with get_db_context() as new_db:
                await pool_mgr.mark_failure(new_db, endpoint_id, error_msg)
                # 记录失败日志
                await self._log_request(
                    new_db,
                    pool_mgr.model_to_pool_type(original_model),
                    original_model, endpoint,
                    success=False, latency_ms=latency_ms,
                    error_message=error_msg
                )
        finally:
            # 务必关闭资源
            if response:
                await response.aclose()
            if client:
                await client.aclose()



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



# 全局单例
_forwarder: Optional[Forwarder] = None


def get_forwarder() -> Forwarder:
    """获取转发器单例"""
    global _forwarder
    if _forwarder is None:
        _forwarder = Forwarder()
    return _forwarder
