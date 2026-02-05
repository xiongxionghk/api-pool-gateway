"""OpenAI Chat Completions API 路由 (/v1/chat/completions)"""

import logging
from typing import Dict, Any

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from core import get_forwarder
from models.enums import PoolType
from config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


def _resolve_pool_type(model: str) -> PoolType:
    """根据请求的模型名解析池类型"""
    model_lower = model.lower()

    # 虚拟模型名映射
    if "haiku" in model_lower or model_lower == settings.virtual_model_tool:
        return PoolType.TOOL
    elif "opus" in model_lower or model_lower == settings.virtual_model_advanced:
        return PoolType.ADVANCED
    else:
        # 默认使用 normal 池
        return PoolType.NORMAL


@router.post("/chat/completions")
async def create_chat_completion(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    OpenAI Chat Completions API 入口

    接收 OpenAI 格式的请求，根据模型名路由到对应池，
    池内轮询选择端点转发请求。
    """
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无效的 JSON: {e}")

    model = body.get("model", "")
    if not model:
        raise HTTPException(status_code=400, detail="缺少 model 参数")

    # 解析池类型
    pool_type = _resolve_pool_type(model)
    # 强制使用流式，防止预热机制导致超时
    stream = True
    body["stream"] = True

    logger.info(f"[OpenAI API] 收到请求: model={model}, pool={pool_type.value}, stream={stream}")

    # 转发请求
    forwarder = get_forwarder()
    response_body, stream_iter, error = await forwarder.forward_request(
        db=db,
        pool_type=pool_type,
        request_body=body,
        stream=stream
    )

    if error:
        logger.error(f"[OpenAI API] 转发失败: {error}")
        raise HTTPException(status_code=502, detail=error)

    if stream and stream_iter:
        # 流式响应
        return StreamingResponse(
            stream_iter,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )

    # 非流式响应
    return response_body


@router.get("/models")
async def list_models():
    """
    列出可用的虚拟模型

    返回三个虚拟模型名，对应三个池。
    """
    return {
        "object": "list",
        "data": [
            {
                "id": settings.virtual_model_tool,
                "object": "model",
                "created": 0,
                "owned_by": "api-pool-gateway",
                "description": "工具模型池 (Tool Pool)"
            },
            {
                "id": settings.virtual_model_normal,
                "object": "model",
                "created": 0,
                "owned_by": "api-pool-gateway",
                "description": "普通模型池 (Normal Pool)"
            },
            {
                "id": settings.virtual_model_advanced,
                "object": "model",
                "created": 0,
                "owned_by": "api-pool-gateway",
                "description": "高级模型池 (Advanced Pool)"
            },
        ]
    }
