from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ENV_FILE = str(Path(__file__).resolve().parents[2] / ".env")


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5433/ai_browser_assist"

    # AI provider. Supported values: "gemini", "openrouter", "anthropic".
    ai_provider: str = "gemini"

    # Gemini API.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # OpenRouter API.
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_site_url: str = "http://localhost:8000"
    openrouter_app_name: str = "AI Browser Assist"

    # Anthropic Claude API.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # V4.6: set to true to enable SQLAlchemy persistence for UnifiedTask lifecycle.
    # Keep false (default) so existing tests continue to run without a DB.
    unified_task_persistence: bool = False

    # V5.0: set to true to enable SQLAlchemy persistence for Mission lifecycle.
    mission_persistence: bool = False

    # M0.6 diagnostics: when true, the /analyze path additionally writes the exact
    # provider prompt + raw response to <trace_dir>/backend/<trace_id>.json for the
    # benchmark trace viewer. OFF by default → byte-identical behavior. Purely additive
    # recording; never influences planning, prompts, parsing, or execution.
    trace_mode: bool = False
    trace_dir: str = ""   # default resolved in app.diagnostics.trace_sink when empty

    # V3.0 Foundation feature flags. States: off | shadow | active.
    # New infrastructure starts non-invasive. Shadow may write diagnostics or
    # ledger records, but must not change planner, workflow, or execution behavior.
    v3_run_ledger: str = "shadow"
    v3_trace_parity: str = "off"
    v3_capability_platform: str = "shadow"
    v3_scheduler: str = "off"
    v3_cost_controller: str = "shadow"

    # Ensure the .env file in the backend/ directory is loaded even if the
    # process current working directory is different when the app is started.
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8-sig",
        extra="ignore",
    )


settings = Settings()
