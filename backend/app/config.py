from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    gemini_api_key: str = ""
    firebase_project_id: str = ""
    database_url: str = "sqlite:///./gateway.db"
    mandate_signing_secret: str = "dev-secret-change-in-production"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
