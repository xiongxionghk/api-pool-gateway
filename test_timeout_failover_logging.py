#!/usr/bin/env python3
"""测试超时故障转移日志"""

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from core.forwarder import Forwarder
from models.database import Base, Pool, RequestLog
from models.enums import PoolType


class TimeoutFailoverLoggingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            future=True,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_timeout_log_should_include_timeout_and_failover_source(self):
        """超时日志应包含超时秒数和故障转移来源模型"""
        async with self.session_factory() as db:
            pool = Pool(
                pool_type=PoolType.NORMAL,
                virtual_model_name="normal",
                timeout_seconds=20,
            )
            db.add(pool)
            await db.commit()

            forwarder = Forwarder()

            endpoint1 = type("Endpoint", (), {
                "endpoint_id": 1,
                "provider_id": 1,
                "provider_name": "provider-a",
                "model_id": "model-a",
                "base_url": "http://a.test/v1",
                "api_key": "key-a",
                "api_format": "openai",
                "timeout": 20.0,
                "context_window": None,
            })()
            endpoint2 = type("Endpoint", (), {
                "endpoint_id": 2,
                "provider_id": 2,
                "provider_name": "provider-b",
                "model_id": "model-b",
                "base_url": "http://b.test/v1",
                "api_key": "key-b",
                "api_format": "openai",
                "timeout": 20.0,
                "context_window": None,
            })()

            select_endpoint = AsyncMock(side_effect=[endpoint1, endpoint2])
            mark_failure = AsyncMock()
            mark_success = AsyncMock()

            # Mock httpx.AsyncClient.post: 第一次超时，第二次成功
            mock_response = Mock()  # 使用 Mock 而不是 AsyncMock，因为 response.json() 是同步方法
            mock_response.json.return_value = {"id": "ok", "usage": {"input_tokens": 10, "output_tokens": 20}}
            mock_response.status_code = 200
            mock_response.raise_for_status = Mock()  # 同步方法

            call_count = [0]

            async def mock_post(self, *args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise httpx.TimeoutException("Request timeout")
                return mock_response

            with patch.object(forwarder.pool_mgr, "select_endpoint", select_endpoint), \
                 patch.object(forwarder.pool_mgr, "mark_failure", mark_failure), \
                 patch.object(forwarder.pool_mgr, "mark_success", mark_success), \
                 patch.object(forwarder.pool_mgr, "model_to_pool_type", return_value=PoolType.NORMAL), \
                 patch.object(httpx.AsyncClient, "post", mock_post):

                response_body, stream_iter, error = await forwarder.forward_request(
                    db=db,
                    pool_type=PoolType.NORMAL,
                    request_body={"model": "normal", "messages": [{"role": "user", "content": "hi"}]},
                    stream=False,
                )

            self.assertIsNone(error)
            self.assertIsNotNone(response_body)
            self.assertIsNone(stream_iter)

            result = await db.execute(RequestLog.__table__.select().order_by(RequestLog.id.asc()))
            rows = result.fetchall()

            self.assertEqual(len(rows), 2)

            first_log = rows[0]
            second_log = rows[1]

            self.assertIn("20", first_log.error_message)
            self.assertIn("timeout", first_log.error_message.lower())
            self.assertIn("model-a", first_log.error_message)

            self.assertTrue(hasattr(first_log, "request_id"))
            self.assertEqual(first_log.attempt_index, 0)
            self.assertEqual(first_log.failover_reason, "timeout")
            self.assertIsNone(first_log.previous_model)
            self.assertEqual(first_log.configured_timeout_ms, 20000)

            self.assertTrue(second_log.success)
            self.assertEqual(second_log.attempt_index, 1)
            self.assertEqual(second_log.previous_model, "model-a")
            self.assertEqual(second_log.configured_timeout_ms, 20000)
            self.assertEqual(first_log.request_id, second_log.request_id)


if __name__ == "__main__":
    unittest.main()
