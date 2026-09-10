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

    # 模型能力标记（移植 B 的能力探测思想：
    #   L3 = 支持 OpenAI 风格函数调用 -> 可一次性下发 tools/整块改写
    #   L2 = 不支持（如讯飞星火 pro-128k）-> 必须走「先定位章节 → 再逐块喂原文」两步降级，
    #        否则整篇喂入会被模型缩写（B 实测 20k 字符只回 99 token）
    LLM_FUNCTION_CALLING: bool = True
    LLM_JSON_MODE: bool = True

    # 大脑阶段开关（PRD 4.8：S2 目标生成默认规则引擎降本，可开 LLM 增强）
    BRAIN_S2_USE_LLM: bool = False

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