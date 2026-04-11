from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="HLR_",
        case_sensitive=False,
        extra="ignore",
    )

    model_path: str = "./storage/hlr_weights.json"
    default_target_recall: float = 0.78
    min_half_life_days: float = 0.25
    max_half_life_days: float = 365.0


settings = Settings()
