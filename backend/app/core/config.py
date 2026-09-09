"""应用配置"""
import os
from pydantic_settings import BaseSettings
from functools import lru_cache


# 基于项目根目录的 .env 绝对路径
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ENV_PATH = os.path.join(_PROJECT_ROOT, ".env")


class Settings(BaseSettings):
    """应用配置类"""

    # 数据库
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/aibi"
    SQLITE_DATABASE_URL: str = "sqlite+aiosqlite:///./data/aibi.db"
    DB_FALLBACK_SQLITE: bool = True

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM配置
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    LLM_MODEL: str = ""

    # 文件上传
    MAX_FILE_SIZE: int = 100 * 1024 * 1024  # 100MB
    UPLOAD_DIR: str = "./data/uploads"
    EXPORT_DIR: str = "./data/exports"

    # DuckDB
    DUCKDB_PATH: str = "./data/duckdb/aibi.db"

    # 安全
    SECRET_KEY: str = "your-secret-key-here"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # 调试
    DEBUG: bool = True

    class Config:
        env_file = _ENV_PATH
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()