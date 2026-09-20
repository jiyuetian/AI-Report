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

    # 单任务 Token 预算（P1-1 取长补短 InsightDesk §3.1）：
    # 一次 /brain/run 生成流水线的 LLM 累计消耗上限。达 80% 告警、达 100% 熔断，
    # 跳过后续 LLM 调用并保留已生成的图表/看板（已完成部分）。
    BRAIN_TASK_TOKEN_BUDGET: int = 8000

    # S3 LLM 图表生成硬超时（秒）：brain/run 在 S3 对 generate_charts_with_llm 的
    # 外层墙钟上限。内部 llm_chat 单次 timeout=60 × MAX_RETRIES 累计可能超过 60s，
    # 故此处用 asyncio.wait_for 强制总时长 ≤ 该值，保证「验收报告·优化1 <60s 兜底」
    # 成立，杜绝 LLM 不可达时 S3 卡在「正在推荐图表…」50% 无限挂起。
    # 2026-09-20 放宽至 180s：NVIDIA nemotron-3.5-lightning 为推理模型（带 thinking 过程）
    # 且经 7897 代理出口，图表 JSON 真实生成常需 50~120s，原 50s 包裹会提前掐断导致
    # 直接规则兜底（绿标永不亮）。放宽后让慢推理模型有足够时间返回，绿标方可亮起。
    BRAIN_S3_LLM_TIMEOUT: float = 180.0

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