"""请求转发器 - 处理请求转发到后端服务商"""

import time
import logging
from typing import Optional, Dict, Any, AsyncIterator

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import PoolType, RequestLog
from db import crud
from .pool_manager import get_pool_manager, SelectedEndpoint
from .converter import RequestConverter, ResponseConverter

logger = logging.getLogger(__name__)


class Forwarder:
    """请求转发器"""

    def __init__(self, timeout: float = 300.0):
        self.timeout = timeout
        self.pool_mgr = get_pool_manager()
        self.request_converter = RequestConverter()
        self.response_converter = ResponseConverter()

    async def forward_request(
        self,
        db: AsyncSession,
        pool_type: PoolType,
        request_body: Dict[str, Any],
        incoming_format: str,  # "openai" or "anthropic"
        stream: bool = False
    ) -> tuple[Optional[Dict[str, Any]], Optional[AsyncIterator[bytes]], Optional[str]]:
        """
        转发请求到后端服务商

        Args:
            db: 数据库会话
            pool_type: 池类型
            request_body: 原始请求体
            incoming_format: 入站格式 ("openai" or "anthropic")
            stream: 是否流式

        Returns:
            (response_body, stream_iterator, error_message)
            - 非流式: (response_body, None, None) 或 (None, None, error)
            - 流式: (None, stream_iterator, None) 或 (None, None, error)
        """
        # 记录原始请求的模型名
        original_model = request_body.get("model", "unknown")

        # 尝试获取端点
        max_attempts = 10  # 最多尝试10个端点
        last_error = ""

        for attempt in range(max_attempts):
            endpoint = await self.pool_mgr.select_endpoint(db, pool_type)
            if not endpoint:
                last_error = "没有可用的端点"
                break

            start_time = time.time()

            try:
                # 转换请求格式
                converted_body = self.request_converter.convert(
                    request_body,
                    from_format=incoming_format,
                    to_format=endpoint.api_format,
                    target_model=endpoint.model_id
                )

                # 构建请求URL
                if endpoint.api_format == "openai":
                    url = f"{endpoint.base_url}/chat/completions"
                else:
                    url = f"{endpoint.base_url}/messages"

                # 构建请求头
                headers = {
                    "Content-Type": "application/json",
                }
                if endpoint.api_format == "openai":
                    headers["Authorization"] = f"Bearer {endpoint.api_key}"
                else:
                    headers["x-api-key"] = endpoint.api_key
                    headers["anthropic-version"] = "2023-06-01"

                logger.info(
                    f"[Forwarder] 转发请求: {endpoint.provider_name}/{endpoint.model_id} "
                    f"(attempt={attempt+1}, stream={stream})"
                )

                if stream:
                    # 流式请求
                    return await self._forward_stream(
                        db, endpoint, url, headers, converted_body,
                        original_model, incoming_format, start_time
                    )
                else:
                    # 非流式请求
                    return await self._forward_normal(
                        db, endpoint, url, headers, converted_body,
                        original_model, incoming_format, start_time
                    )

            except httpx.HTTPStatusError as e:
                latency_ms = int((time.time() - start_time) * 1000)
                error_msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                logger.error(f"[Forwarder] HTTP 错误: {error_msg}")

                # 记录失败
                await self.pool_mgr.mark_failure(db, endpoint.endpoint_id, error_msg)
                await self._log_request(
                    db, pool_type, original_model, endpoint,
                    success=False, latency_ms=latency_ms,
                    status_code=e.response.status_code, error_message=error_msg
                )
                last_error = error_msg
                continue

            except Exception as e:
                latency_ms = int((time.time() - start_time) * 1000)
                error_msg = str(e)
                logger.error(f"[Forwarder] 请求异常: {error_msg}")

                await self.pool_mgr.mark_failure(db, endpoint.endpoint_id, error_msg)
                await self._log_request(
                    db, pool_type, original_model, endpoint,
                    success=False, latency_ms=latency_ms,
                    error_message=error_msg
                )
                last_error = error_msg
                continue

        # 所有尝试都失败
        return None, None, f"所有端点都失败: {last_error}"

    async def _forward_normal(
        self,
        db: AsyncSession,
        endpoint: SelectedEndpoint,
        url: str,
        headers: Dict[str, str],
        body: Dict[str, Any],
        original_model: str,
        incoming_format: str,
        start_time: float
    ) -> tuple[Optional[Dict[str, Any]], None, Optional[str]]:
        """非流式转发"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()

            latency_ms = int((time.time() - start_time) * 1000)
            response_data = response.json()

            # 转换响应格式
            converted_response = self.response_converter.convert(
                response_data,
                from_format=endpoint.api_format,
                to_format=incoming_format,
                original_model=original_model
            )

            # 记录成功
            await self.pool_mgr.mark_success(db, endpoint.endpoint_id, latency_ms)

            # 提取 token 统计
            input_tokens = None
            output_tokens = None
            if incoming_format == "anthropic":
                usage = converted_response.get("usage", {})
                input_tokens = usage.get("input_tokens")
                output_tokens = usage.get("output_tokens")
            else:
                usage = converted_response.get("usage", {})
                input_tokens = usage.get("prompt_tokens")
                output_tokens = usage.get("completion_tokens")

            await self._log_request(
                db, PoolType(self._model_to_pool_type(original_model)),
                original_model, endpoint,
                success=True, latency_ms=latency_ms,
                status_code=200,
                input_tokens=input_tokens, output_tokens=output_tokens
            )

            return converted_response, None, None

    async def _forward_stream(
        self,
        db: AsyncSession,
        endpoint: SelectedEndpoint,
        url: str,
        headers: Dict[str, str],
        body: Dict[str, Any],
        original_model: str,
        incoming_format: str,
        start_time: float
    ) -> tuple[None, AsyncIterator[bytes], Optional[str]]:
        """流式转发"""
        body["stream"] = True

        async def stream_generator():
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, json=body, headers=headers) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if line:
                            # 转换流式响应
                            converted_line = self.response_converter.convert_stream_line(
                                line,
                                from_format=endpoint.api_format,
                                to_format=incoming_format,
                                original_model=original_model
                            )
                            if converted_line:
                                yield converted_line.encode("utf-8") + b"\n"

            # 流结束后记录成功
            latency_ms = int((time.time() - start_time) * 1000)
            await self.pool_mgr.mark_success(db, endpoint.endpoint_id, latency_ms)

        return None, stream_generator(), None

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
