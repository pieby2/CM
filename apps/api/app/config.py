from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CUE_",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg2://cue:cue@localhost:5432/cue_math"
    redis_url: str = "redis://localhost:6379/0"
    storage_path: str = "./storage"
    cors_origins_raw: str = "http://localhost:5173"
    default_due_limit: int = 30
    ocr_language: str = "eng"
    section_min_chars: int = 700
    section_max_chars: int = 1800
    hlr_enabled: bool = True
    hlr_service_url: str = "http://localhost:8010"
    hlr_timeout_seconds: float = 2.0
    hlr_min_reviews_per_card: int = 5
    hlr_default_target_recall: float = 0.78
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_temperature: float = 0.7

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]


settings = Settings()
