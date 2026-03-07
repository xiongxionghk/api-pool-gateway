"""请求转发器 - 处理请求转发到后端服务商"""

import time
import logging
import json
import asyncio
import uuid
from typing import Optional, Dict, Any, AsyncIterator, List

import httpx
import tiktoken
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import RequestLog
from models.enums import PoolType
from db import crud
from .pool_manager import get_pool_manager, SelectedEndpoint

logger = logging.getLogger(__name__)

IMAGE_TOKEN_COST = 1400
IMAGE_BLOCK_TYPES = {"image", "image_url", "input_image"}


def _detect_sse_error(chunk: bytes) -> Optional[str]:
    """
    检测 SSE 流中的错误事件

    返回错误消息（如果检测到错误），否则返回 None
    """
    try:
        text = chunk.decode('utf-8')

        # 解析 SSE 格式：查找 data: 行
        for line in text.split('\n'):
            if line.startswith('data: '):
                data_json = line[6:].strip()
                if not data_json or data_json == '[DONE]':
                    continue

                try:
                    data = json.loads(data_json)

                    # 检测 Anthropic 格式的错误（嵌套在 text_delta 中）
                    if data.get('type') == 'content_block_delta':
                        delta = data.get('delta', {})
                        if delta.get('type') == 'text_delta':
                            text_content = delta.get('text', '')
                            # 尝试解析 text 内容为 JSON（某些错误会嵌套在这里）
                            try:
                                error_obj = json.loads(text_content)
                                if 'code' in error_obj and 'type' in error_obj:
                                    error_code = error_obj.get('code', '')
                                    error_type = error_obj.get('type', '')
                                    error_msg = error_obj.get('message', '')

                                    # 检测已知的错误代码
                                    if error_code in ['context_length_exceeded', 'invalid_request_error', 'token_quota_exceeded']:
                                        return f"{error_type}: {error_msg} (code={error_code})"
                            except (json.JSONDecodeError, ValueError):
                                pass

                    # 检测标准错误格式
                    if 'error' in data:
                        error = data['error']
                        if isinstance(error, dict):
                            error_type = error.get('type', 'unknown_error')
                            error_msg = error.get('message', 'Unknown error')
                            return f"{error_type}: {error_msg}"

                except json.JSONDecodeError:
                    continue

        return None
    except Exception:
        return None


def count_image_tokens(request_body: Dict[str, Any]) -> int:
    """统计请求中的图片 token 预估值"""
    image_count = 0

    system = request_body.get("system", "")
    if isinstance(system, list):
        for block in system:
            if isinstance(block, dict) and block.get("type") in IMAGE_BLOCK_TYPES:
                image_count += 1

    for msg in request_body.get("messages", []):
        if not isinstance(msg, dict):
            continue
        content = msg.get("content", "")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") in IMAGE_BLOCK_TYPES:
                    image_count += 1

    return image_count * IMAGE_TOKEN_COST


def calculate_request_tokens(request_body: Dict[str, Any]) -> int:
    """
    使用 tiktoken 计算请求输入所需的总 token 数（文本输入 + 图片输入）

    Args:
        request_body: 请求体，包含 messages、system 等字段

    Returns:
        预计请求输入 token 数（不含输出预留）
    """
    try:
        # 使用 gpt-4 编码器（通用性较好）
        enc = tiktoken.encoding_for_model("gpt-4")
    except Exception:
        # 回退到 cl100k_base
        enc = tiktoken.get_encoding("cl100k_base")

    # 提取所有文本内容
    text_parts = []

    # 提取 system
    system = request_body.get("system", "")
    if isinstance(system, str):
        text_parts.append(system)
    elif isinstance(system, list):
        for block in system:
            if isinstance(block, dict) and "text" in block:
                text_parts.append(block["text"])

    # 提取 messages
    for msg in request_body.get("messages", []):
        if not isinstance(msg, dict):
            continue

        # 添加 role
        text_parts.append(msg.get("role", ""))

        # 提取 content
        content = msg.get("content", "")
        if isinstance(content, str):
            text_parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if "text" in block:
                        text_parts.append(block["text"])
                    # 图片等多模态内容暂时忽略，实际会占用 token 但这里简化处理

    # 计算输入 token
    full_text = "\n".join(text_parts)
    input_tokens = len(enc.encode(full_text))
    image_tokens = count_image_tokens(request_body)

    # 请求输入总大小（不含输出预留）
    total_input_tokens = input_tokens + image_tokens

    if image_tokens > 0:
        logger.info(
            f"[TokenCalc] 请求输入={total_input_tokens} tokens (文本={input_tokens}, 图片={image_tokens})"
        )
    else:
        logger.info(
            f"[TokenCalc] 请求输入={total_input_tokens} tokens (文本={input_tokens})"
        )

    return total_input_tokens


# 重试配置
class RetryConfig:
    """重试配置"""
    # 单个端点的重试次数
    ENDPOINT_RETRIES = 1  # 改为1次，避免同一端点拖太久
    # 跨端点的最大尝试次数
    MAX_ENDPOINT_ATTEMPTS = 5
    # 指数退避基数(秒)
    BACKOFF_BASE = 1.5
    # 最大退避时间(秒)
    BACKOFF_MAX = 30.0
    # 当前端点可立即重试的HTTP状态码
    RETRIABLE_STATUS_CODES = {429, 500, 502, 503, 504}
    # 不应故障转移到其他端点的状态码（通常是请求体本身有问题）
    NO_FAILOVER_STATUS_CODES = {400, 422}
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


def _classify_failover_reason(error: Exception) -> str:
    """将异常分类为故障转移原因"""
    if isinstance(error, httpx.TimeoutException) or isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, (httpx.ConnectError, httpx.ReadError, httpx.WriteError, httpx.PoolTimeout, httpx.NetworkError)):
        return "network_error"
    if isinstance(error, httpx.HTTPStatusError):
        status_code = error.response.status_code if error.response else None
        if status_code == 429:
            return "http_429"
        if status_code and 500 <= status_code < 600:
            return "http_5xx"
        if status_code and 400 <= status_code < 500:
            text = error.response.text if error.response else ""
            if "context_length_exceeded" in text:
                return "context_length_exceeded"
            if "token_quota_exceeded" in text:
                return "token_quota_exceeded"
            return "http_4xx"
    message = str(error)
    if "context_length_exceeded" in message:
        return "context_length_exceeded"
    if "token_quota_exceeded" in message:
        return "token_quota_exceeded"
    if "Stream error" in message:
        return "stream_error"
    return "unknown_error"


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

        # 计算本次请求所需的 token 总量
        required_tokens = calculate_request_tokens(request_body)
        logger.info(f"[Forwarder] 请求预计需要 {required_tokens} tokens")

        # 上一次错误信息，用于最终返回
        last_error = ""
        request_id = str(uuid.uuid4())
        previous_model = None

        # 跨端点尝试循环
        for attempt in range(RetryConfig.MAX_ENDPOINT_ATTEMPTS):
            endpoint = await self.pool_mgr.select_endpoint(db, pool_type, required_tokens=required_tokens)
            if not endpoint:
                last_error = "没有可用的端点"
                break

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

                    attempt_start_time = time.time()

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
                            original_model, attempt_start_time,
                            request_id, attempt, previous_model
                        )
                    else:
                        return await self._handle_normal_request(
                            db, endpoint, url, headers, body,
                            original_model, attempt_start_time,
                            request_id, attempt, previous_model
                        )

                except RetryConfig.RETRIABLE_EXCEPTIONS as e:
                    # 可重试的网络/连接错误
                    latency_ms = int((time.time() - attempt_start_time) * 1000)
                    error_type = type(e).__name__
                    is_status_error = isinstance(e, httpx.HTTPStatusError)
                    status_code = e.response.status_code if is_status_error else None

                    # 检查状态码是否可在当前端点立即重试，以及是否允许故障转移
                    should_retry = True
                    should_failover = True

                    if is_status_error:
                        error_msg = f"HTTP {status_code}: {e.response.text[:200]}"
                        should_retry = status_code in RetryConfig.RETRIABLE_STATUS_CODES
                        should_failover = status_code not in RetryConfig.NO_FAILOVER_STATUS_CODES
                    else:
                        # 增强错误消息：包含超时配置和模型信息
                        timeout_info = f" (timeout={endpoint.timeout}s)" if endpoint.timeout else ""
                        error_msg = f"{error_type}{timeout_info} on {endpoint.provider_name}/{endpoint.model_id}: {str(e)}"

                    logger.error(f"[Forwarder] 请求失败 (retry={retry}): {error_msg}")

                    # 如果是最后一次单端点重试，或当前状态码不适合继续重试当前端点
                    if retry == RetryConfig.ENDPOINT_RETRIES - 1 or not should_retry:
                        await self.pool_mgr.mark_failure(db, endpoint.endpoint_id, error_msg)
                        failover_reason = _classify_failover_reason(e)
                        await self._log_request(
                            db, pool_type, original_model, endpoint,
                            success=False, latency_ms=latency_ms,
                            request_id=request_id, attempt_index=attempt,
                            status_code=status_code, error_message=error_msg,
                            failover_reason=failover_reason,
                            previous_model=previous_model,
                            request_body=body
                        )
                        last_error = error_msg
                        previous_model = endpoint.model_id

                        # 对于请求体本身错误（如400/422），直接返回，避免无意义轮询
                        if not should_failover:
                            return None, None, error_msg

                        # 否则切换到下一个端点（包含401/403等情况）
                        break

                    # 还有单端点重试机会，继续循环
                    continue

                except Exception as e:
                    # 未知错误，记录并切换端点
                    latency_ms = int((time.time() - attempt_start_time) * 1000)
                    timeout_info = f" (timeout={endpoint.timeout}s)" if endpoint.timeout else ""
                    error_msg = f"Unexpected Error{timeout_info} on {endpoint.provider_name}/{endpoint.model_id}: {str(e)}"
                    logger.error(f"[Forwarder] 未知异常: {error_msg}")

                    await self.pool_mgr.mark_failure(db, endpoint.endpoint_id, error_msg)
                    failover_reason = _classify_failover_reason(e)
                    await self._log_request(
                        db, pool_type, original_model, endpoint,
                        success=False, latency_ms=latency_ms,
                        request_id=request_id, attempt_index=attempt,
                        error_message=error_msg,
                        failover_reason=failover_reason,
                        previous_model=previous_model,
                        request_body=body
                    )
                    last_error = error_msg
                    previous_model = endpoint.model_id
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
        start_time: float,
        request_id: str,
        attempt_index: int,
        previous_model: Optional[str]
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
                request_id=request_id, attempt_index=attempt_index,
                status_code=200,
                previous_model=previous_model,
                input_tokens=input_tokens, output_tokens=output_tokens,
                request_body=body,
                response_body=response_data
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
        request_id: str,
        attempt_index: int,
        previous_model: Optional[str]
    ) -> tuple[None, AsyncIterator[bytes], Optional[str]]:
        """
        处理流式请求 - 立即发起请求，预读首批数据检测错误后再返回生成器
        这样外层的重试逻辑可以捕获连接错误和流式错误
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

            # 3. 预读首批数据检测流式错误
            # 必须保存迭代器引用，后续继续用同一个迭代器，避免重复调用 aiter_bytes() 导致 "content already streamed" 错误
            stream_iter = response.aiter_bytes()
            first_chunk = None
            try:
                first_chunk = await stream_iter.__anext__()
            except StopAsyncIteration:
                pass

            if first_chunk:
                # 检测首批数据中是否包含错误
                error_msg = _detect_sse_error(first_chunk)
                if error_msg:
                    await response.aclose()
                    await client.aclose()
                    # 抛出异常触发重试
                    raise httpx.HTTPStatusError(
                        f"Stream contains error: {error_msg}",
                        request=request,
                        response=response
                    )

            # 4. 返回生成器处理后续数据流
            # 注意：client、response、stream_iter 的所有权转移给了生成器
            generator = self._stream_generator(
                client, response, stream_iter, endpoint, original_model, start_time,
                request_id, attempt_index, previous_model, body, first_chunk
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
        stream_iter: AsyncIterator[bytes],
        endpoint: SelectedEndpoint,
        original_model: str,
        start_time: float,
        request_id: str,
        attempt_index: int,
        previous_model: Optional[str],
        request_body: Dict[str, Any],
        first_chunk: Optional[bytes] = None
    ) -> AsyncIterator[bytes]:
        """
        流式响应生成器 - 负责读取数据流并处理中断
        """
        pool_mgr = self.pool_mgr
        endpoint_id = endpoint.endpoint_id

        # 收集响应数据用于日志
        response_chunks = []

        try:
            # 先 yield 预读的首批数据
            if first_chunk:
                response_chunks.append(first_chunk)
                yield first_chunk

            # 继续 pipe 剩余数据流，使用同一个迭代器（而不是重新调用 aiter_bytes）
            async for chunk in stream_iter:
                # 持续监控错误
                error_msg = _detect_sse_error(chunk)
                if error_msg:
                    logger.error(f"[Forwarder] 流式传输中检测到错误: {error_msg}")
                    raise Exception(f"Stream error detected: {error_msg}")

                response_chunks.append(chunk)
                yield chunk

            # 流正常结束，记录成功
            latency_ms = int((time.time() - start_time) * 1000)

            # 尝试解析响应体（流式响应通常是 SSE 格式）
            response_body = None
            try:
                full_response = b''.join(response_chunks).decode('utf-8')
                # 简单记录原始响应（SSE 格式），不做复杂解析
                response_body = {"raw_stream": full_response[:5000]}  # 限制长度避免过大
            except Exception:
                pass

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
                    request_id=request_id, attempt_index=attempt_index,
                    status_code=200,
                    previous_model=previous_model,
                    request_body=request_body,
                    response_body=response_body
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
                    request_id=request_id, attempt_index=attempt_index,
                    error_message=error_msg,
                    failover_reason="stream_error",
                    previous_model=previous_model,
                    request_body=request_body
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
        request_id: str,
        attempt_index: int,
        status_code: Optional[int] = None,
        error_message: Optional[str] = None,
        failover_reason: Optional[str] = None,
        previous_model: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        request_body: Optional[Dict[str, Any]] = None,
        response_body: Optional[Dict[str, Any]] = None
    ):
        """记录请求日志"""
        try:
            configured_timeout_ms = int(endpoint.timeout * 1000) if endpoint.timeout else None
            await crud.create_log(
                db,
                pool_type=pool_type,
                requested_model=requested_model,
                actual_model=endpoint.model_id,
                provider_name=endpoint.provider_name,
                request_id=request_id,
                attempt_index=attempt_index,
                failover_reason=failover_reason,
                previous_model=previous_model,
                configured_timeout_ms=configured_timeout_ms,
                success=success,
                status_code=status_code,
                error_message=error_message,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                request_body=request_body,
                response_body=response_body
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
