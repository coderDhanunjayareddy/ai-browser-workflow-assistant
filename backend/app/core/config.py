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
    v5_product_layer: str = "shadow"
    v5_jwt_secret: str = ""

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
    v3_semantic_graph: str = "shadow"
    v3_context_packet: str = "shadow"
    v3_intent_grounding: str = "shadow"
    v3_mission_intelligence: str = "shadow"
    v3_validation: str = "shadow"
    v3_governance: str = "shadow"
    v3_learning: str = "shadow"

    # V4 Wave 1 Browser Control feature flags. States: off | shadow | active.
    # Defaults are non-invasive; V4 capabilities are registered and certifiable
    # without changing production browser behavior until explicitly enabled.
    v4_smart_waits: str = "off"
    v4_locator_resilience: str = "off"
    v4_action_verification: str = "off"
    v4_native_forms: str = "off"
    v4_custom_selects: str = "off"
    v4_date_time_pickers: str = "off"
    v4_overlay_handling: str = "off"
    v4_toast_detection: str = "off"
    v4_multi_tab_hardening: str = "off"
    v4_history_control: str = "off"
    v4_upload_engine: str = "off"
    v4_download_lifecycle: str = "off"
    v4_auth_handoff: str = "off"
    v4_browser_profile: str = "off"
    v4_browser_observability: str = "shadow"
    v4_browser_replay: str = "shadow"
    v4_capability_certification: str = "shadow"
    v4_rich_text_editing: str = "shadow"
    v4_monaco_editor: str = "shadow"
    v4_codemirror_editor: str = "shadow"
    v4_drag_drop: str = "shadow"
    v4_virtual_lists: str = "shadow"
    v4_shadow_dom: str = "shadow"
    v4_infinite_scroll: str = "shadow"
    v4_advanced_keyboard: str = "shadow"
    v4_clipboard: str = "shadow"
    v4_canvas: str = "shadow"
    v4_svg_interaction: str = "shadow"
    v4_pdf_viewer: str = "shadow"
    v4_charts: str = "shadow"
    v4_maps: str = "shadow"
    v4_media_controls: str = "shadow"
    v4_file_preview: str = "shadow"
    v4_visual_regions: str = "shadow"
    v4_google_workspace_adapter: str = "shadow"
    v4_microsoft365_adapter: str = "shadow"
    v4_github_advanced_adapter: str = "shadow"
    v4_jira_adapter: str = "shadow"
    v4_confluence_adapter: str = "shadow"
    v4_slack_adapter: str = "shadow"
    v4_notion_adapter: str = "shadow"
    v4_figma_adapter: str = "shadow"
    v4_canva_adapter: str = "shadow"
    v4_salesforce_adapter: str = "shadow"
    v4_sso_auth: str = "shadow"
    v4_mfa_otp_handoff: str = "shadow"
    v4_enterprise_file_workflows: str = "shadow"
    v4_site_optimization_framework: str = "shadow"

    # V4.5 Browser Intelligence Layer feature flags. States: off | shadow | active.
    # Shadow builds deterministic artifacts and telemetry only. Active additionally
    # enriches planner context while preserving Planner Contract V2 actions.
    v45_browser_intelligence: str = "shadow"
    v45_page_model: str = "shadow"
    v45_selector_engine: str = "shadow"
    v45_action_verification: str = "shadow"
    v45_site_adapters: str = "shadow"
    v45_serp_adapter: str = "shadow"

    # V4.6 Adaptive Browser Intelligence feature flags. States: off | shadow | active.
    v46_dynamic_dom: str = "shadow"
    v46_intelligent_wait: str = "shadow"
    v46_browser_memory: str = "shadow"
    v46_recovery_engine: str = "shadow"
    v46_visual_grounding: str = "shadow"
    v46_browser_health: str = "shadow"

    # V4.7 Execution Continuity Engine feature flag. States: off | shadow | active.
    # Shadow records deterministic continuity state only. Active enriches planner
    # context and can return Planner Contract V2 replan outcomes for detected loops.
    v47_execution_continuity: str = "shadow"

    # Ensure the .env file in the backend/ directory is loaded even if the
    # process current working directory is different when the app is started.
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8-sig",
        extra="ignore",
    )


settings = Settings()
