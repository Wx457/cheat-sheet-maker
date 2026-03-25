import os
from dotenv import load_dotenv

# 确保加载环境变量
load_dotenv()


class Settings:
    """应用配置类，从环境变量读取配置"""

    # MongoDB 配置
    MONGODB_URI: str = os.getenv("MONGODB_URI", "")
    DB_NAME: str = os.getenv("DB_NAME", "cheat_sheet_db")
    COLLECTION_NAME: str = os.getenv("COLLECTION_NAME", "knowledge_base")

    # Google API 配置
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")

    # Redis 配置
    # ========== [上线检查] localhost 作为默认值 - 生产环境应通过环境变量 REDIS_HOST 配置 ==========
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")

    # RAG 检索重试配置（处理向量索引最终一致性延迟）
    RAG_RETRY_ATTEMPTS: int = int(os.getenv("RAG_RETRY_ATTEMPTS", "5"))
    RAG_RETRY_DELAY_SECONDS: int = int(os.getenv("RAG_RETRY_DELAY_SECONDS", "3"))

    # LLM / Embedding 调用重试配置
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "3"))
    LLM_INITIAL_RETRY_DELAY_SECONDS: float = float(
        os.getenv("LLM_INITIAL_RETRY_DELAY_SECONDS", "1")
    )
    LLM_MAX_RETRY_DELAY_SECONDS: float = float(os.getenv("LLM_MAX_RETRY_DELAY_SECONDS", "60"))
    LLM_REQUEST_TIMEOUT_SECONDS: int = int(os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "120"))

    # AWS S3 配置
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_REGION: str = os.getenv(
        "AWS_REGION", "us-east-1"
    )  # 默认 us-east-1，建议在 .env 中设置为实际使用的区域（如 us-east-2）
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "cheat-sheets")

    # PDF 生成配置
    # ========== [上线检查] localhost 作为默认值 - 生产环境应通过环境变量 PDF_GENERATION_HOST 配置（例如: http://backend:8000 或生产环境地址） ==========
    PDF_GENERATION_HOST: str = os.getenv(
        "PDF_GENERATION_HOST", "http://localhost:8000"
    )  # Worker 进程访问 FastAPI 服务器的地址

    @classmethod
    def validate(cls) -> None:
        """验证必需的配置项"""
        if not cls.MONGODB_URI:
            raise ValueError("MONGODB_URI 未在环境变量中设置")
        if not cls.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY 未在环境变量中设置")


# 创建全局配置实例
settings = Settings()
