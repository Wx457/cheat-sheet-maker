from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from arq.connections import create_pool, RedisSettings

from app.api import generate_router
from app.api.rag import router as rag_router
from app.api.plugin import router as plugin_router
from app.api.task import router as task_router
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    在启动时创建 ARQ Redis 连接池，在关闭时清理
    """
    # 启动时：创建 ARQ Redis 连接池
    redis_settings = RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        database=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None
    )
    
    arq_pool = await create_pool(redis_settings)
    app.state.arq_pool = arq_pool
    
    print("✅ ARQ Redis 连接池已创建")
    
    yield
    
    # 关闭时：清理连接池
    await arq_pool.close(close_connection_pool=True)
    print("👋 ARQ Redis 连接池已关闭")


app = FastAPI(
    title="Cheat Sheet Maker API",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，支持 Chrome 插件调用
    allow_credentials=False,  # 当 allow_origins=["*"] 时，allow_credentials 必须为 False
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate_router)
app.include_router(rag_router, prefix="/api/rag", tags=["RAG"])
app.include_router(plugin_router, tags=["Plugin"])
app.include_router(task_router, tags=["Task"])


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
