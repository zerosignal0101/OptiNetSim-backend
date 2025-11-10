from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """
    MONGO_URI: str
    MONGO_DB_NAME: str
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8')


settings = Settings()


def get_settings() -> Settings:
    """Get settings instance."""
    return settings
