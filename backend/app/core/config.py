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
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    
    # MinIO/S3 配置
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "cheat-sheets")
    S3_ENDPOINT_URL: str = os.getenv("S3_ENDPOINT_URL", "http://localhost:9000")
    
    @classmethod
    def validate(cls) -> None:
        """验证必需的配置项"""
        if not cls.MONGODB_URI:
            raise ValueError("MONGODB_URI 未在环境变量中设置")
        if not cls.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY 未在环境变量中设置")


# 创建全局配置实例
settings = Settings()

