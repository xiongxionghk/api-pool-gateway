#!/usr/bin/env python3
"""context_window 功能回归测试"""

import sys
import unittest
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from api.admin import create_endpoint
from core.forwarder import calculate_request_tokens
from core.pool_manager import PoolManager
from db import crud
from models.database import Base, ModelEndpoint, Provider
from models.enums import ApiFormat, PoolType
from models.schemas import ModelEndpointCreate


class ContextWindowTests(unittest.IsolatedAsyncioTestCase):
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

        self.pool_manager = PoolManager()
        await self.pool_manager.cooldown_mgr.clear_all()

    async def asyncTearDown(self):
        await self.pool_manager.cooldown_mgr.clear_all()
        await self.engine.dispose()

    async def _create_provider(self, db, name: str = "test-provider") -> Provider:
        provider = Provider(
            name=name,
            base_url="http://example.com/v1",
            api_key="test-key",
            api_format=ApiFormat.OPENAI,
            enabled=True,
        )
        db.add(provider)
        await db.flush()
        return provider

    async def _create_endpoint(
        self,
        db,
        provider: Provider,
        model_id: str,
        pool_type: PoolType = PoolType.NORMAL,
        weight: int = 1,
        context_window: int | None = None,
        enabled: bool = True,
    ) -> ModelEndpoint:
        endpoint = ModelEndpoint(
            provider_id=provider.id,
            model_id=model_id,
            pool_type=pool_type,
            weight=weight,
            enabled=enabled,
            context_window=context_window,
        )
        db.add(endpoint)
        await db.flush()
        return endpoint

    def test_calculate_request_tokens_includes_anthropic_images(self):
        request_body = {
            "system": "你是助手",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "看图回答"},
                        {"type": "image", "source": {"type": "base64", "data": "xxx"}},
                        {"type": "image", "source": {"type": "base64", "data": "yyy"}},
                    ],
                }
            ],
            "max_tokens": 500,
        }

        total_tokens = calculate_request_tokens(request_body)

        self.assertGreaterEqual(total_tokens, 2800)

    def test_calculate_request_tokens_includes_openai_images(self):
        request_body = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "描述这张图"},
                        {"type": "image_url", "image_url": {"url": "https://example.com/a.jpg"}},
                        {"type": "input_image", "image_url": "data:image/png;base64,abc"},
                    ],
                }
            ],
            "max_tokens": 300,
        }

        total_tokens = calculate_request_tokens(request_body)

        self.assertGreaterEqual(total_tokens, 2800)

    async def test_select_endpoint_skips_models_with_small_context_window(self):
        async with self.session_factory() as db:
            provider = await self._create_provider(db)
            await self._create_endpoint(db, provider, "small-model", weight=10, context_window=8000)
            await self._create_endpoint(db, provider, "large-model", weight=1, context_window=30000)
            await db.commit()

            selected = await self.pool_manager.select_endpoint(
                db,
                PoolType.NORMAL,
                required_tokens=20000,
            )

            self.assertIsNotNone(selected)
            self.assertEqual(selected.model_id, "large-model")
            self.assertEqual(selected.context_window, 30000)

    async def test_get_pool_status_returns_context_window(self):
        async with self.session_factory() as db:
            provider = await self._create_provider(db)
            await self._create_endpoint(db, provider, "status-model", context_window=32000)
            await db.commit()

            status = await self.pool_manager.get_pool_status(db, PoolType.NORMAL)

            self.assertEqual(len(status["providers"]), 1)
            model = status["providers"][0]["models"][0]
            self.assertIn("context_window", model)
            self.assertEqual(model["context_window"], 32000)

    async def test_create_endpoint_persists_context_window(self):
        async with self.session_factory() as db:
            provider = await self._create_provider(db)
            await db.commit()

            response = await create_endpoint(
                ModelEndpointCreate(
                    provider_id=provider.id,
                    model_id="created-model",
                    pool_type=PoolType.NORMAL,
                    weight=1,
                    context_window=64000,
                ),
                db,
            )

            endpoint = await crud.get_endpoint(db, response.id)

            self.assertIsNotNone(endpoint)
            self.assertEqual(response.context_window, 64000)
            self.assertEqual(endpoint.context_window, 64000)


if __name__ == "__main__":
    unittest.main()
