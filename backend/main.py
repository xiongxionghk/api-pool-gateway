"""API Pool Gateway - 主入口"""

import logging
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from config import get_settings
from db import init_db
from api import anthropic_router, openai_router, admin_router

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("🚀 API Pool Gateway 启动中...")

    # 确保数据目录存在
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # 初始化数据库
    await init_db()
    logger.info("✅ 数据库初始化完成")

    logger.info(f"✅ API 网关运行在 http://{settings.host}:{settings.api_port}")
    logger.info(f"   - Anthropic API: POST /v1/messages")
    logger.info(f"   - OpenAI API: POST /v1/chat/completions")
    logger.info(f"   - 管理后台: http://{settings.host}:{settings.api_port}/admin")
    logger.info(f"   - 虚拟模型: {settings.virtual_model_tool}, {settings.virtual_model_normal}, {settings.virtual_model_advanced}")

    yield

    # 关闭时
    logger.info("👋 API Pool Gateway 关闭")


# 创建应用
app = FastAPI(
    title="API Pool Gateway",
    description="多服务商模型池轮询网关，支持 OpenAI 和 Anthropic 格式",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"未处理的异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": {"type": "internal_error", "message": str(exc)}}
    )


# 注册路由
app.include_router(anthropic_router, prefix="/v1", tags=["Anthropic API"])
app.include_router(openai_router, prefix="/v1", tags=["OpenAI API"])
app.include_router(admin_router, tags=["Admin API"])


# 健康检查
@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "service": "api-pool-gateway"}


# 静态文件（前端）
# 兼容 Docker 和本地开发环境的路径查找
# 本地开发: backend/main.py -> ../frontend/dist
# Docker: /app/main.py -> /app/frontend/dist (如果 backend 内容直接拷到了 /app)
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"

# 如果第一种路径不存在，尝试 Docker 环境常见的路径结构 (如果 main.py 在 /app 下)
if not frontend_dist.exists():
    frontend_dist = Path(__file__).parent / "frontend" / "dist"

if frontend_dist.exists():
    # 静态资源
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    # 前端首页
    @app.get("/")
    async def serve_frontend():
        """服务前端首页"""
        return FileResponse(frontend_dist / "index.html")

    # 前端 SPA 路由 - 这些是前端页面路由
    @app.get("/providers")
    @app.get("/pools")
    @app.get("/pools/{pool_type}")
    @app.get("/logs")
    @app.get("/settings")
    async def serve_frontend_spa():
        """服务前端 SPA 页面"""
        return FileResponse(frontend_dist / "index.html")

    # 静态文件
    @app.get("/favicon.svg")
    async def serve_favicon():
        """服务 favicon"""
        return FileResponse(frontend_dist / "favicon.svg")
else:
    @app.get("/")
    async def no_frontend():
        """无前端时的提示"""
        return {
            "message": "API Pool Gateway",
            "docs": "/docs",
            "admin_api": "/admin",
            "note": "前端未构建，请运行 cd frontend && npm run build"
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.api_port,
        reload=True
    )
