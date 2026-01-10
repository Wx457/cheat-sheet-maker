import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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

# 挂载静态文件（前端构建产物）
# 注意：static 目录应该在 Dockerfile 构建时从 frontend/dist 复制过来
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    # 挂载根目录，用于访问 index.html
    app.mount("/static", StaticFiles(directory=str(static_dir), html=True), name="static")
    
    # 挂载 assets 目录，用于访问 JS/CSS 等资源文件
    # Vite 构建的 HTML 中资源路径是 /assets/xxx，所以需要单独挂载
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
        print(f"✅ Assets 目录已挂载: {assets_dir}")
    
    print(f"✅ 静态文件已挂载: {static_dir}")
else:
    print(f"⚠️ 警告: 静态文件目录不存在: {static_dir}，PDF 生成功能可能无法正常工作")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
