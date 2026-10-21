import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from qdrant_client import QdrantClient

from app.api import generate_router
from app.api.rag import router as rag_router
from app.api.cheat_sheets import router as cheat_sheets_router
from app.api.auth import router as auth_router
from app.core.config import settings

app = FastAPI(title="Cheat Sheet Maker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，支持 Chrome 插件调用
    allow_credentials=False,  # 当 allow_origins=["*"] 时，allow_credentials 必须为 False
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate_router)
app.include_router(rag_router, prefix="/api/rag", tags=["RAG"])
app.include_router(cheat_sheets_router, tags=["CheatSheets"])
app.include_router(auth_router, tags=["Auth"])


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

    # Qdrant 是生成链路的必需依赖（RAG 检索）。
    # Supabase 不在此检查：它是外部托管服务，挂掉只影响保存，且每 20s 的 healthcheck
    # 都去请求它没有必要。
    def _ping_qdrant() -> None:
        client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT, timeout=2)
        try:
            client.get_collections()
        finally:
            client.close()

    try:
        await asyncio.to_thread(_ping_qdrant)
        checks["qdrant"] = "ok"
    except Exception as exc:
        degraded = True
        checks["qdrant"] = f"error: {exc}"

    if degraded:
        raise HTTPException(
            status_code=503,
            detail={"status": "degraded", "checks": checks},
        )

    return {"status": "ok", "checks": checks}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
