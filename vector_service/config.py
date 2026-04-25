from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    pg_dsn: str = "postgresql://localhost:5432/yacy_pages"
    embedding_model: str = "intfloat/multilingual-e5-base"
    embedding_dim: int = 768
    max_summary_chars: int = 6000
    server_host: str = "127.0.0.1"
    server_port: int = 8001


settings = Settings()
