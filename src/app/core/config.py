import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    PROJECT_NAME: str = "Tableau to Databricks Lakeview Migration Engine"
    API_V1_STR: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = "sqlite:///./migrations.db"
    
    # LLM Settings
    OPENAI_API_KEY: Optional[str] = None
    AZURE_OPENAI_API_KEY: Optional[str] = None
    AZURE_OPENAI_ENDPOINT: Optional[str] = None
    AZURE_OPENAI_DEPLOYMENT: Optional[str] = "gpt-4o-2"
    AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"
    OPENAI_MODEL: str = "gpt-4o-mini-2"
    USE_LLM_CACHE: bool = True
    
    # Databricks Target Defaults
    DATABRICKS_HOST: Optional[str] = None
    DATABRICKS_TOKEN: Optional[str] = None
    DEFAULT_WAREHOUSE_ID: Optional[str] = None
    DEFAULT_CATALOG: str = "main"
    DEFAULT_SCHEMA: str = "default"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
