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

    # Optional LLM (OpenAI-compatible chat/completions API). Empty url = disabled.
    llm_api_url: str = ""           # e.g. https://api.deepseek.com/v1
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_timeout_s: int = 30

    # OIDC (Authentik). Empty issuer disables /oidc/* endpoints.
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""
    cabinet_cookie_name: str = "vg_session"
    cabinet_session_days: int = 30

    # Hybrid ranking weights (must sum to 1.0). See PLAN.md Phase 2.
    weight_semantic: float = 0.60
    weight_freshness: float = 0.25
    weight_quality: float = 0.15
    # Exponential decay half-life for freshness; matches the soft Solr profile.
    freshness_half_life_days: float = 365.0


settings = Settings()
