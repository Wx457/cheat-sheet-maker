from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import generate_router
from app.api.rag import router as rag_router
from app.api.plugin import router as plugin_router

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
app.include_router(plugin_router, tags=["Plugin"])


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
