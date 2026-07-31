from __future__ import annotations

from app.validation.benchmark_models import BenchmarkCategory, BenchmarkDefinition


def benchmark_catalog() -> list[BenchmarkDefinition]:
    return [
        _benchmark(BenchmarkCategory.RESEARCH, "Research AI browser automation tools.", ["search_sources", "collect_results", "read_pages", "extract_records", "create_report"], ["browser_control", "knowledge_extraction", "validation"]),
        _benchmark(BenchmarkCategory.SHOPPING, "Compare three laptops and identify the best value.", ["search_products", "compare_prices", "validate_specs", "summarize_choice"], ["browser_control", "knowledge_extraction", "validation"]),
        _benchmark(BenchmarkCategory.BOOKING, "Find available flights for a date range without purchasing.", ["search_options", "filter_results", "verify_availability"], ["browser_control", "validation"]),
        _benchmark(BenchmarkCategory.AUTHENTICATION, "Sign in and verify dashboard visibility.", ["request_credentials", "submit_login", "confirm_dashboard"], ["browser_control", "runtime_state", "validation"]),
        _benchmark(BenchmarkCategory.NAVIGATION, "Open a known documentation page and verify location.", ["navigate", "verify_page"], ["browser_control", "validation"]),
        _benchmark(BenchmarkCategory.FORMS, "Complete a long form using provided data.", ["map_fields", "fill_form", "validate_entries"], ["browser_control", "validation"]),
        _benchmark(BenchmarkCategory.JOB_APPLICATIONS, "Fill a job application draft without final submission.", ["open_listing", "fill_application", "request_approval"], ["browser_control", "validation", "user_approval"]),
        _benchmark(BenchmarkCategory.DASHBOARD_WORKFLOWS, "Inspect a dashboard and summarize key metrics.", ["open_dashboard", "read_widgets", "extract_metrics"], ["browser_control", "knowledge_extraction"]),
        _benchmark(BenchmarkCategory.MULTI_TAB_RESEARCH, "Open multiple relevant sources and synthesize findings.", ["collect_urls", "open_tabs", "read_tabs", "synthesize"], ["browser_control", "knowledge_extraction", "validation"]),
        _benchmark(BenchmarkCategory.EXTRACTION, "Extract structured records from a directory page.", ["identify_records", "extract_fields", "validate_records"], ["knowledge_extraction", "validation"]),
        _benchmark(BenchmarkCategory.UPLOAD, "Upload a provided file and verify attachment state.", ["select_file", "upload_file", "verify_upload"], ["browser_control", "files", "validation"]),
        _benchmark(BenchmarkCategory.DOWNLOAD, "Download a report and verify the file exists.", ["request_download", "track_download", "verify_file"], ["browser_control", "files", "validation"]),
        _benchmark(BenchmarkCategory.EMAIL, "Draft an email from provided notes without sending.", ["compose_draft", "validate_recipients", "request_approval"], ["email", "validation", "user_approval"]),
        _benchmark(BenchmarkCategory.CALENDAR, "Create a calendar draft for a meeting time.", ["find_slot", "draft_event", "request_approval"], ["calendar", "validation", "user_approval"]),
        _benchmark(BenchmarkCategory.CROSS_SYSTEM_WORKFLOW, "Extract data from one system and draft an update in another.", ["extract_source_data", "transform_data", "prepare_target_update"], ["browser_control", "knowledge_extraction", "api", "validation"]),
        _benchmark(BenchmarkCategory.CUSTOM_MISSION, "Run a custom mission with explicit criteria.", ["understand_goal", "execute_criteria", "validate_outcome"], ["runtime_state", "validation"]),
    ]


def get_benchmark(benchmark_id: str) -> BenchmarkDefinition | None:
    return next((item for item in benchmark_catalog() if item.benchmark_id == benchmark_id), None)


def _benchmark(category: BenchmarkCategory, mission: str, structure: list[str], providers: list[str]) -> BenchmarkDefinition:
    return BenchmarkDefinition(
        benchmark_id=f"benchmark_{category.value}",
        category=category.value,
        mission=mission,
        expected_outcome="mission criteria satisfied without runtime contract violations",
        expected_success_criteria=[f"{node}_satisfied" for node in structure],
        expected_providers=providers,
        expected_blueprint_structure=structure,
        expected_ledger_progression=["QUEUED", "DISPATCHED", "EXECUTING", "COMPLETED"],
        metadata={"passive": True, "execution_impact": "none"},
    )
