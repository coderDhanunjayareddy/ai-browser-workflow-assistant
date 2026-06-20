from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = str(Path(__file__).resolve().parents[2] / ".env")


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5433/ai_browser_assist"

    # AI provider. Supported values: "gemini", "openrouter".
    ai_provider: str = "gemini"

    # Gemini API.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # OpenRouter API.
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_site_url: str = "http://localhost:8000"
    openrouter_app_name: str = "AI Browser Assist"

    # Ensure the .env file in the backend/ directory is loaded even if the
    # process current working directory is different when the app is started.
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8-sig",
        extra="ignore",
    )


settings = Settings()
