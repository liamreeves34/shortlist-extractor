from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    EXTRACTOR_BACKEND: Literal["stub", "teacher", "student", "rules"] = "stub"
    EXTRACTOR_MODE: str = "stub"
    EXTRACTOR_URL: str = "http://localhost:8001"
    CONNECTOR_MODE: Literal["live", "stub"] = "stub"
    CONNECTOR_USER_AGENT: str = "Shortlist Extractor Service"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
