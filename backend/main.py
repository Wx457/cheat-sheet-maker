from contextlib import asynccontextmanager
from pathlib import Path
from typing import Final

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pymongo import MongoClient

from app.api import generate_router
from app.api.auth import router as auth_router
from app.api.rag import router as rag_router
from app.api.plugin import router as plugin_router
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # TODO: DEPRECATED — TTL indexes were for the MongoDB knowledge_base and projects
    # collections. knowledge_base → Qdrant; projects → Supabase (Phase 3). Remove this call.
    # setup_mongodb_ttl_indexes()
    setup_users_indexes()  # still needed until Clerk replaces bcrypt/PyJWT (Phase 2)

    yield


app = FastAPI(title="Cheat Sheet Maker API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，支持 Chrome 插件调用
    allow_credentials=False,  # 当 allow_origins=["*"] 时，allow_credentials 必须为 False
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(generate_router)
app.include_router(rag_router, prefix="/api/rag", tags=["RAG"])
app.include_router(plugin_router, tags=["Plugin"])


# TTL 过期时间（秒）
PROJECTS_TTL_SECONDS: Final[int] = 60 * 60 * 24 * 7  # 7 天
VECTORS_TTL_SECONDS: Final[int] = 60 * 60 * 24 * 3  # 3 天


# TODO: DEPRECATED — remove after Phase 3 (Supabase). knowledge_base is now Qdrant;
# projects persistence will move to Supabase.
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


# TODO: DEPRECATED — remove after Phase 2 (Clerk). Users table moves to Clerk/Supabase.
def setup_users_indexes() -> None:
    """
    为 users 集合创建唯一索引（email 唯一、user_id 唯一）。
    MongoDB 会自动去重，重复调用安全。
    """
    client = None
    try:
        client = MongoClient(settings.MONGODB_URI)
        db = client[settings.DB_NAME]
        users = db["users"]
        users.create_index("email", unique=True)
        users.create_index("user_id", unique=True)
        print("✅ MongoDB users indexes checked/created")
    except Exception as exc:
        print(f"⚠️ Error creating users indexes: {exc}")
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

    # TODO: DEPRECATED — MongoDB health check; remove after Phase 2/3 (Clerk + Supabase).
    # Keep until auth.py and plugin.py finish migrating away from MongoDB.
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

    if degraded:
        raise HTTPException(
            status_code=503,
            detail={"status": "degraded", "checks": checks},
        )

    return {"status": "ok", "checks": checks}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
