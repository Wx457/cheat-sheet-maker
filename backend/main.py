from contextlib import asynccontextmanager
from pathlib import Path
from typing import Final

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pymongo import MongoClient

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
        password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
    )

    arq_pool = await create_pool(redis_settings)
    app.state.arq_pool = arq_pool

    print("✅ ARQ Redis connection pool created")

    # 启动时：创建 MongoDB TTL 索引（幂等）
    setup_mongodb_ttl_indexes()

    yield

    # 关闭时：清理连接池
    await arq_pool.close(close_connection_pool=True)
    print("👋 ARQ Redis connection pool closed")


app = FastAPI(title="Cheat Sheet Maker API", lifespan=lifespan)

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


# TTL 过期时间（秒）
PROJECTS_TTL_SECONDS: Final[int] = 60 * 60 * 24 * 7  # 7 天
VECTORS_TTL_SECONDS: Final[int] = 60 * 60 * 24 * 3  # 3 天


def setup_mongodb_ttl_indexes() -> None:
    """
    在启动时为 MongoDB 创建 TTL 索引。
    MongoDB 会自动去重创建，重复调用安全。
    """
    client = None
    try:
        client = MongoClient(settings.MONGODB_URI)
        db = client[settings.DB_NAME]

        # projects 集合：根据 created_at 7 天过期
        projects = db["projects"]
        projects.create_index("created_at", expireAfterSeconds=PROJECTS_TTL_SECONDS)

        # 向量集合：metadata.created_at 3 天过期
        vectors = db[settings.COLLECTION_NAME]
        vectors.create_index(
            "metadata.created_at",
            expireAfterSeconds=VECTORS_TTL_SECONDS,
        )

        print("✅ MongoDB TTL indexes checked/created")
    except Exception as exc:
        # 记录错误，但不阻止应用启动
        print(f"⚠️ Error creating MongoDB TTL indexes: {exc}")
    finally:
        try:
            if client:
                client.close()
        except Exception:
            pass


# 挂载静态文件（前端构建产物）
# 注意：static 目录应该在 Dockerfile 构建时从 frontend/dist 复制过来
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    # 挂载根目录，用于访问 index.html
    app.mount("/static", StaticFiles(directory=str(static_dir), html=True), name="static")

    # 3. 👇 新增：根路径路由 (这就是我们要加的！)
    @app.get("/")
    async def read_root():
        # 直接读取并返回 index.html 文件
        return FileResponse(static_dir / "index.html")

    # 挂载 assets 目录，用于访问 JS/CSS 等资源文件
    # Vite 构建的 HTML 中资源路径是 /assets/xxx，所以需要单独挂载
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
        print(f"✅ Assets directory mounted: {assets_dir}")

    print(f"✅ Static files mounted: {static_dir}")
else:
    print(
        f"⚠️ Warning: Static files directory does not exist: {static_dir}, PDF generation may not work properly"
    )


@app.get("/health")
async def health() -> dict:
    checks: dict[str, str] = {"api": "ok"}
    degraded = False

    mongo_client = None
    try:
        mongo_client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2000)
        mongo_client.admin.command("ping")
        checks["mongodb"] = "ok"
    except Exception as exc:
        degraded = True
        checks["mongodb"] = f"error: {exc}"
    finally:
        try:
            if mongo_client:
                mongo_client.close()
        except Exception:
            pass

    try:
        arq_pool = app.state.arq_pool
        await arq_pool.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        degraded = True
        checks["redis"] = f"error: {exc}"

    if degraded:
        raise HTTPException(
            status_code=503,
            detail={"status": "degraded", "checks": checks},
        )

    return {"status": "ok", "checks": checks}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
