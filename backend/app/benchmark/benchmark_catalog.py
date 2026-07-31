from __future__ import annotations

from app.benchmark.benchmark_models import BenchmarkCategory, BenchmarkMission


def benchmark_catalog() -> list[BenchmarkMission]:
    return [
        _mission(BenchmarkCategory.RESEARCH, "Research Comparison", "Research AI browser automation tools and return a comparison table.", ["search_sources", "open_results", "read_pages", "extract_fields", "report"], ["browser_control", "knowledge_extraction", "validation"], "medium"),
        _mission(BenchmarkCategory.SHOPPING, "Shopping Compare", "Compare three products by price, specs, and limitation.", ["search_products", "collect_products", "compare", "report"], ["browser_control", "knowledge_extraction"], "medium"),
        _mission(BenchmarkCategory.NAVIGATION, "Navigation Verify", "Navigate to a documentation page and verify it loaded.", ["navigate", "verify"], ["browser_control", "validation"], "easy"),
        _mission(BenchmarkCategory.EXTRACTION, "Directory Extraction", "Extract structured records from a directory listing.", ["identify_records", "extract_fields", "validate_records"], ["knowledge_extraction", "validation"], "medium"),
        _mission(BenchmarkCategory.FORMS, "Long Form Draft", "Fill a form draft with provided non-sensitive data.", ["map_fields", "fill_fields", "validate"], ["browser_control", "validation"], "hard"),
        _mission(BenchmarkCategory.AUTHENTICATION, "Authentication Handoff", "Sign in with user-provided credentials and verify dashboard.", ["request_user", "submit_login", "verify_dashboard"], ["browser_control", "runtime_state", "validation"], "hard"),
        _mission(BenchmarkCategory.UPLOAD, "Upload Verify", "Upload a supplied file and verify attachment state.", ["select_file", "upload", "verify"], ["browser_control", "files", "validation"], "hard"),
        _mission(BenchmarkCategory.DOWNLOAD, "Download Verify", "Download a report and verify file evidence.", ["request_download", "track_download", "verify_file"], ["browser_control", "files", "validation"], "hard"),
        _mission(BenchmarkCategory.DASHBOARD, "Dashboard Summary", "Inspect dashboard widgets and summarize key metrics.", ["open_dashboard", "read_widgets", "extract_metrics"], ["browser_control", "knowledge_extraction"], "medium"),
        _mission(BenchmarkCategory.DOCUMENTATION, "Docs QA", "Find a documentation answer and cite the relevant page.", ["search_docs", "read_section", "answer"], ["browser_control", "knowledge_extraction", "validation"], "easy"),
        _mission(BenchmarkCategory.NEWS, "News Summary", "Find recent news about a topic and summarize sources.", ["search_news", "read_articles", "summarize"], ["browser_control", "knowledge_extraction"], "medium"),
        _mission(BenchmarkCategory.JOB_APPLICATION, "Job Application Draft", "Prepare a job application draft without submitting.", ["open_listing", "fill_draft", "request_approval"], ["browser_control", "validation", "user_approval"], "hard"),
        _mission(BenchmarkCategory.CROSS_SYSTEM, "Cross-System Update", "Extract data from one app and prepare an update in another.", ["extract_source", "transform", "prepare_target"], ["browser_control", "knowledge_extraction", "api", "validation"], "hard"),
        _mission(BenchmarkCategory.CUSTOM, "Custom Criteria", "Execute a custom mission against explicit criteria.", ["understand", "execute_criteria", "validate"], ["runtime_state", "validation"], "medium"),
    ]


def get_benchmark(benchmark_id: str) -> BenchmarkMission | None:
    return next((item for item in benchmark_catalog() if item.id == benchmark_id), None)


def _mission(category: BenchmarkCategory, title: str, prompt: str, blueprint: list[str], providers: list[str], difficulty: str) -> BenchmarkMission:
    return BenchmarkMission(
        id=f"exec_{category.value}",
        title=title,
        description=prompt,
        category=category.value,
        difficulty=difficulty,
        user_prompt=prompt,
        expected_deliverable="structured mission result with validation evidence",
        expected_blueprint=blueprint,
        expected_success_criteria=[f"{node}_satisfied" for node in blueprint],
        expected_providers=providers,
        timeout=300,
        tags=[category.value, difficulty, "passive_harness"],
    )
