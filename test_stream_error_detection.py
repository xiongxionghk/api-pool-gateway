#!/usr/bin/env python3
"""测试流式响应中的错误检测"""

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = Path(__file__).parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from core.forwarder import Forwarder
from core.pool_manager import SelectedEndpoint
from models.enums import ApiFormat


class StreamErrorDetectionTests(unittest.IsolatedAsyncioTestCase):
    """测试流式响应中的错误检测"""

    async def test_stream_with_context_length_exceeded_should_raise_error(self):
        """当流式响应包含 context_length_exceeded 错误时应该在预读阶段抛出异常"""

        # 模拟包含错误的 SSE 流
        error_stream = b"""event: message_start
data: {"type": "message_start", "message": {"id": "msg_123", "type": "message", "role": "assistant", "content": [], "model": "gpt-oss-120b", "stop_reason": null, "stop_sequence": null, "usage": {"input_tokens": 86356, "output_tokens": 1}}}

event: content_block_start
data: {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}

event: content_block_delta
data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "{\\"message\\":\\"Please reduce the length of the messages or completion. Current length is 81995 while limit is 65536\\",\\"type\\":\\"invalid_request_error\\",\\"param\\":\\"messages\\",\\"code\\":\\"context_length_exceeded\\",\\"id\\":\\"\\"}"}}

event: content_block_stop
data: {"type": "content_block_stop", "index": 0}

event: message_delta
data: {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": null}, "usage": {"output_tokens": 0}}

event: message_stop
data: {"type": "message_stop"}

[DONE]

"""

        forwarder = Forwarder()

        # 模拟端点
        endpoint = SelectedEndpoint(
            endpoint_id=1,
            provider_id=1,
            provider_name="test-provider",
            base_url="http://test.com",
            api_key="test-key",
            model_id="test-model",
            api_format=ApiFormat.ANTHROPIC,
            timeout=None,
            context_window=None,
        )

        # 模拟 httpx 响应
        mock_response = MagicMock()
        mock_response.status_code = 200

        async def mock_aiter_bytes():
            # 分块返回错误流
            yield error_stream

        mock_response.aiter_bytes = mock_aiter_bytes
        mock_response.aclose = AsyncMock()

        mock_client = MagicMock()
        mock_client.aclose = AsyncMock()

        # 模拟 httpx.AsyncClient
        mock_async_client = MagicMock()
        mock_async_client.aclose = AsyncMock()
        mock_async_client.build_request = MagicMock(return_value=MagicMock())
        mock_async_client.send = AsyncMock(return_value=mock_response)

        # 测试：_handle_stream_request 应该在预读阶段检测到错误并抛出异常
        with patch('httpx.AsyncClient', return_value=mock_async_client):
            with self.assertRaises(Exception) as context:
                await forwarder._handle_stream_request(
                    db=None,  # 不需要真实的 db
                    endpoint=endpoint,
                    url="http://test.com/messages",
                    headers={"x-api-key": "test"},
                    body={"model": "test-model", "messages": []},
                    original_model="test-model",
                    start_time=0.0,
                    request_id="test-request-id",
                    attempt_index=0,
                    previous_model=None
                )

        # 验证异常消息包含错误信息
        error_msg = str(context.exception).lower()
        self.assertTrue(
            "context_length_exceeded" in error_msg or "stream contains error" in error_msg,
            f"Expected error message to contain 'context_length_exceeded' or 'stream contains error', got: {error_msg}"
        )


if __name__ == "__main__":
    unittest.main()
