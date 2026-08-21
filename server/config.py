"""应用配置管理，使用 pydantic-settings 从环境变量加载配置。"""

from functools import lru_cache
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，优先从 .env 文件读取，支持环境变量覆盖。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- 应用 ----------
    APP_NAME: str = "MemoryBridge Server"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ---------- PostgreSQL ----------
    POSTGRES_USER: str = "memorybridge"
    POSTGRES_PASSWORD: str = "memorybridge"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "memorybridge"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ---------- Redis ----------
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""

    @property
    def redis_url(self) -> str:
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # ---------- LLM ----------
    # api | ollama
    LLM_MODE: Literal["api", "ollama"] = "api"
    # 当 LLM_MODE=api 时选择提供商: deepseek | qwen
    LLM_PROVIDER: Literal["deepseek", "qwen"] = "deepseek"

    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL: str = "qwen-plus"
    QWEN_EMBEDDING_MODEL: str = "text-embedding-v2"

    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"

    # ---------- 向量维度 ----------
    EMBEDDING_DIM: int = 1024

    # ---------- RAG ----------
    MEMORY_TOP_K: int = 5
    # Redis 会话缓存保留的对话轮数
    SESSION_HISTORY_TURNS: int = 5
    SESSION_TTL: int = 86400  # 会话缓存过期时间（秒），默认 1 天

    # ---------- TTS ----------
    TTS_VOICE: str = "zh-CN-XiaoxiaoNeural"
    TTS_RATE: str = "+0%"
    TTS_VOLUME: str = "+0%"

    # ---------- ASR（在线语音识别） ----------
    # asr 后端选择: unisound | funasr | whisper | simple
    #   unisound: 云知声 U2-ASR，云端异步，精度高，推荐做"先粗后精"的精修后端
    #   funasr : 阿里达摩院 FunASR，中文识别最优，需 GPU 或较强 CPU
    #   whisper: OpenAI Whisper，多语言，faster-whisper 实现
    #   simple : speech_recognition + Google Web API，无需安装模型，适合快速测试
    ASR_BACKEND: Literal["unisound", "funasr", "whisper", "simple"] = "simple"

    # 云知声 U2-ASR API Key（Token Plan 优先）。获取：https://maas.unisound.com/
    UNISOUND_API_KEY: str = ""

    # FunASR 模型名称（paraformer 系列为离线模型，适合短音频）
    ASR_FUNASR_MODEL: str = "paraformer-zh"

    # Whisper 模型大小: tiny | base | small | medium | large-v3
    # small 以下可在 CPU 上运行，medium 以上建议 GPU
    ASR_WHISPER_MODEL: str = "small"

    # Whisper 设备: cpu | cuda
    ASR_WHISPER_DEVICE: str = "cpu"

    # ASR 识别超时（秒），超时返回空结果
    ASR_TIMEOUT: int = 15

    # ---------- 生成参数 ----------
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 512

    # ---------- CORS ----------
    CORS_ORIGINS: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    """单例获取配置，避免重复读取环境变量。"""
    return Settings()


settings = get_settings()
