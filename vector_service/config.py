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
    # Bearer token for write endpoints (services CRUD). Empty disables auth —
    # only safe in local dev.
    admin_token: str = ""

    # Optional LLM (OpenAI-compatible chat/completions API) used by the
    # gap-analyzer to turn unsatisfied queries into seed URLs. Empty url
    # disables the feature — the /unsatisfied/seed endpoint then returns
    # 503 and the cron is a no-op.
    llm_api_url: str = ""           # e.g. https://api.deepseek.com/v1
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_timeout_s: int = 30

    # Hybrid ranking weights (must sum to 1.0). See PLAN.md Phase 2.
    weight_semantic: float = 0.60
    weight_freshness: float = 0.25
    weight_quality: float = 0.15
    # Exponential decay half-life for freshness; matches the soft Solr profile.
    freshness_half_life_days: float = 365.0


settings = Settings()
