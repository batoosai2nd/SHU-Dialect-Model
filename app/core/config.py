from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 数据库
    DATABASE_URL: str = "sqlite+aiosqlite:///./chat.db"

    # API Keys
    DEEPSEEK_API_KEY: str = ""
    CHATGPT_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # 节点地址
    OLLAMA_ENDPOINT: str = ""
    TTS_API_BASE: str = ""
    SHANGHAI_ASR_URL: str = ""

    # 上海话 ASR（TeleSpeech HTTP API）
    SHANGHAI_ASR_API_KEY: str = ""
    SHANGHAI_ASR_MODEL_ID: str = "test2"
    SHANGHAI_ASR_DIALECT: str = "auto"
    SHANGHAI_ASR_USE_KALDI: bool = True
    SHANGHAI_ASR_ENABLE_PUNCTUATION: bool = True
    SHANGHAI_ASR_TIMEOUT_SECONDS: float = 120.0

    # 小沪 TTS（Bert-VITS2 FastAPI v2）
    TTS_MODEL: str = ""
    TTS_SPEAKER: str = ""
    # 留空时由 TTS 模型使用自己的默认语言（推荐）。
    TTS_LANG: str = ""
    TTS_EMOTION: str = "Neutral"
    TTS_SDP_RATIO: float = 0.2
    TTS_NOISE: float = 0.6
    TTS_NOISE_W: float = 0.8
    TTS_LENGTH_SCALE: float = 1.0
    TTS_AUTO_SPLIT: bool = True
    TTS_TIMEOUT_SECONDS: float = 300.0

    # 阿里云 ASR
    ALI_ASR_URL: str = ""
    ALI_ASR_APPKEY: str = ""
    ALI_ASR_TOKEN: str = ""

    # 文学馆展陈会话：浏览器会主动删除正常结束的会话；这里负责兜底清理
    # 设备异常断电、浏览器崩溃等情况下残留的临时会话。
    MUSEUM_SESSION_RETENTION_HOURS: int = 24
    MUSEUM_CLEANUP_INTERVAL_SECONDS: int = 3600

    class Config:
        # 指定读取的环境变量文件
        env_file = ".env"
        env_file_encoding = "utf-8"
        # 忽略未在类中定义的额外环境变量
        extra = "ignore"


# 实例化全局配置对象
# 以后在任何文件里，只需要 from app.core.config import settings
settings = Settings()
