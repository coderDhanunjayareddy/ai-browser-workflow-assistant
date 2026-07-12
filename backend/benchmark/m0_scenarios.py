"""
M0 — Benchmark task definitions (the dataset).

28 declarative tasks: 11 local fixtures (offline, deterministic regression anchors),
14 real-site tasks, and 3 capability-specific tasks. Pure data — no control flow, no
browser, no AI. The runner drives them. Do not invent additional tasks here; this set
maps 1:1 to docs/benchmark-m0.md Part 4.

start_url may contain the literal "{fixture_base}" placeholder, which the runner replaces
with the running FixtureServer base_url for is_fixture tasks.
"""
from __future__ import annotations

from benchmark.m0_models import (
    M0TaskDefinition, M0Criterion, M0CriterionKind, M0FailureCriterion, FailureCriterionKind,
    Preconditions, HumanInterventionRules, ArtifactSpec, Difficulty, BenchmarkCategory,
)

FB = "{fixture_base}"


def _c(kind, detail="", target=None, value=None) -> M0Criterion:
    return M0Criterion(kind=kind, detail=detail, target=target, value=value)


def _fc(kind, detail="", target=None) -> M0FailureCriterion:
    return M0FailureCriterion(kind=kind, detail=detail, target=target)


def _shot(desc) -> ArtifactSpec:
    return ArtifactSpec(artifact_id="final_screenshot", type="screenshot", description=desc)


K = M0CriterionKind
FK = FailureCriterionKind


def build_m0_scenarios() -> list[M0TaskDefinition]:
    tasks: list[M0TaskDefinition] = []

    # ─────────────────────────── SIMPLE TIER (1–8) ───────────────────────────
    tasks.append(M0TaskDefinition(
        task_id="youtube_com__video_search", site_id="youtube_com", website="YouTube",
        difficulty=Difficulty.simple, category=BenchmarkCategory.search,
        goal='Search for "Python tutorial for beginners" and confirm search results appear',
        start_url="https://www.youtube.com",
        success_criteria=[
            _c(K.dom_text_present, "Python tutorial in results", target="Python tutorial"),
            _c(K.url_matches, "search_query in URL", target=r"search_query=Python"),
            _c(K.min_completed_steps, "search performed", value=2),
        ],
        failure_criteria=[_fc(FK.dom_error_present, "error banner", target="Something went wrong")],
        expected_artifacts=[_shot("search results")],
        timeout_ms=60_000, max_steps=8, retry_budget=2, expected_step_range=(2, 4),
        notes="Search box grounding + query submission (Enter vs click).",
    ))

    tasks.append(M0TaskDefinition(
        task_id="github_com__repo_search", site_id="github_com", website="GitHub",
        difficulty=Difficulty.simple, category=BenchmarkCategory.search,
        goal='Search for "fastapi" repositories on GitHub and confirm repositories appear in results',
        start_url="https://github.com/search?type=repositories",
        success_criteria=[
            _c(K.dom_text_present, "fastapi in results", target="fastapi"),
            _c(K.url_matches, "q=fastapi in URL", target=r"q=fastapi"),
        ],
        failure_criteria=[
            _fc(FK.http_error, "rate limited", target="429"),
            _fc(FK.dom_error_present, "no results", target="We couldn't find any repositories"),
        ],
        timeout_ms=60_000, max_steps=6, retry_budget=2, expected_step_range=(2, 3),
    ))

    tasks.append(M0TaskDefinition(
        task_id="instagram_com__profile_view", site_id="instagram_com", website="Instagram",
        difficulty=Difficulty.simple, category=BenchmarkCategory.navigation,
        goal='Navigate to the Instagram profile for user "nasa" and confirm the profile page loaded',
        start_url="https://www.instagram.com/nasa/",
        success_criteria=[
            _c(K.dom_text_present, "nasa on page", target="nasa"),
            _c(K.url_matches, "/nasa/ in URL", target=r"/nasa/"),
        ],
        failure_criteria=[
            _fc(FK.dom_error_present, "unavailable", target="Sorry, this page isn't available"),
            _fc(FK.dom_error_present, "login wall", target="Log in to see this content"),
        ],
        timeout_ms=45_000, max_steps=5, retry_budget=1, expected_step_range=(1, 2),
        notes="Instagram aggressively shows a login wall; classifier maps that to BLOCKED_LOGIN_WALL.",
    ))

    tasks.append(M0TaskDefinition(
        task_id="fixture__login_form", site_id="fixture_server", website="Fixture: Login",
        difficulty=Difficulty.simple, category=BenchmarkCategory.form_submit, is_fixture=True,
        goal='Log in with username "tester" and password "secret123", then confirm the welcome message appears',
        start_url=f"{FB}/login",
        success_criteria=[
            _c(K.dom_text_present, "welcome message", target="Welcome tester"),
            _c(K.min_completed_steps, "filled + submitted", value=3),
        ],
        timeout_ms=30_000, max_steps=5, retry_budget=1, expected_step_range=(4, 5),
        notes="Regression anchor: failure here means the LOOP is broken, not the site.",
    ))

    tasks.append(M0TaskDefinition(
        task_id="zomato_com__restaurant_search", site_id="zomato_com", website="Zomato",
        difficulty=Difficulty.simple, category=BenchmarkCategory.search,
        goal='Search for restaurants serving "biryani" in Bangalore and confirm results appear',
        start_url="https://www.zomato.com/bangalore",
        success_criteria=[
            _c(K.dom_text_present, "biryani in results", target="biryani"),
        ],
        failure_criteria=[
            _fc(FK.dom_error_present, "no restaurants", target="No restaurants found"),
            _fc(FK.http_error, "geo-blocked", target="403"),
        ],
        timeout_ms=90_000, max_steps=10, retry_budget=2,
        notes="Geolocation prompt likely; captcha => BLOCKED.",
    ))

    tasks.append(M0TaskDefinition(
        task_id="fixture__pagination", site_id="fixture_server", website="Fixture: Pagination",
        difficulty=Difficulty.simple, category=BenchmarkCategory.pagination, is_fixture=True,
        goal="Navigate to page 2 of the paged list and confirm page 2 items appear",
        start_url=f"{FB}/pagination",
        success_criteria=[
            _c(K.dom_text_present, "page 2 shown", target="page 2"),
            _c(K.dom_text_present, "page-2 item", target="Item C"),
        ],
        timeout_ms=20_000, max_steps=4, retry_budget=1,
    ))

    tasks.append(M0TaskDefinition(
        task_id="fixture__modal_dialog", site_id="fixture_server", website="Fixture: Modal",
        difficulty=Difficulty.simple, category=BenchmarkCategory.dialog, is_fixture=True,
        goal="Open the settings modal, then save the setting",
        start_url=f"{FB}/modal",
        success_criteria=[_c(K.dom_text_present, "saved", target="Setting saved")],
        timeout_ms=20_000, max_steps=4, retry_budget=1,
    ))

    tasks.append(M0TaskDefinition(
        task_id="fixture__file_upload", site_id="fixture_server", website="Fixture: Upload",
        difficulty=Difficulty.simple, category=BenchmarkCategory.upload, is_fixture=True,
        goal='Upload the test file "benchmark_test.txt" using the file input',
        start_url=f"{FB}/upload",
        success_criteria=[_c(K.dom_text_present, "uploaded", target="Uploaded: benchmark_test.txt")],
        timeout_ms=20_000, max_steps=3, retry_budget=1,
        notes="Mode A uses set_input_files; Mode B uses synthetic flow. A/B gap expected.",
    ))

    tasks.append(M0TaskDefinition(
        task_id="fixture__invoice_total_report", site_id="fixture_server",
        website="Fixture: Invoice Details",
        difficulty=Difficulty.simple, category=BenchmarkCategory.search, is_fixture=True,
        goal="Tell me the invoice total.",
        start_url=f"{FB}/invoice",
        success_criteria=[
            _c(K.extracted_value_present, "invoice total", target="INR 14,632.00"),
        ],
        timeout_ms=20_000, max_steps=2, retry_budget=0, expected_step_range=(1, 1),
        notes="Deterministic positive Planner Contract V2 Report path: visible value, no action required.",
    ))

    # ─────────────────────────── MEDIUM TIER (9–18) ──────────────────────────
    tasks.append(M0TaskDefinition(
        task_id="amazon_in__product_search_price", site_id="amazon_in", website="Amazon India",
        difficulty=Difficulty.medium, category=BenchmarkCategory.search,
        goal='Search for "wireless headphones" on Amazon India, open the first result, and extract the price',
        start_url="https://www.amazon.in",
        success_criteria=[
            _c(K.url_matches, "product page", target=r"/dp/"),
            _c(K.extracted_value_present, "price in analysis", target="₹"),
        ],
        failure_criteria=[
            _fc(FK.dom_error_present, "captcha", target="CAPTCHA"),
            _fc(FK.http_error, "unavailable", target="503"),
        ],
        timeout_ms=120_000, max_steps=12, retry_budget=2, expected_step_range=(4, 8),
        notes="Hashed price classes => grounding stress; anti-bot likely => BLOCKED.",
    ))

    tasks.append(M0TaskDefinition(
        task_id="flipkart_com__product_filter", site_id="flipkart_com", website="Flipkart",
        difficulty=Difficulty.medium, category=BenchmarkCategory.filter,
        goal='Search for "laptop" on Flipkart, apply the "HP" brand filter, and confirm filtered results appear',
        start_url="https://www.flipkart.com",
        success_criteria=[
            _c(K.dom_text_present, "HP in results/filter", target="HP"),
        ],
        failure_criteria=[
            _fc(FK.dom_error_present, "captcha", target="CAPTCHA"),
            _fc(FK.dom_error_present, "no results", target="No results found"),
        ],
        timeout_ms=120_000, max_steps=15, retry_budget=2,
        notes="Aggressively hashed class names; key grounding stress test.",
    ))

    tasks.append(M0TaskDefinition(
        task_id="linkedin_com__people_search", site_id="linkedin_com", website="LinkedIn",
        difficulty=Difficulty.medium, category=BenchmarkCategory.search,
        goal='Search for people with the title "Python Developer" on LinkedIn and confirm results appear',
        start_url="https://www.linkedin.com/search/results/people/?keywords=Python%20Developer",
        preconditions=Preconditions(auth_required=True, auth_strategy="session_state",
                                    auth_state_file="linkedin_com.json"),
        success_criteria=[
            _c(K.dom_text_present, "title in results", target="Python Developer"),
            _c(K.min_completed_steps, "search loaded", value=1),
        ],
        failure_criteria=[
            _fc(FK.url_matches_error, "auth expired", target=r"/login"),
            _fc(FK.dom_error_present, "join wall", target="Join LinkedIn to see"),
        ],
        timeout_ms=90_000, max_steps=8, retry_budget=1,
    ))

    tasks.append(M0TaskDefinition(
        task_id="github_com__pr_read_comments", site_id="github_com", website="GitHub",
        difficulty=Difficulty.medium, category=BenchmarkCategory.navigation,
        goal='Open pull request #1 in "torvalds/linux" and extract the author name and the first comment',
        start_url="https://github.com/torvalds/linux/pull/1",
        success_criteria=[
            _c(K.dom_element_present, "comment body", target=".comment-body, .TimelineItem"),
            _c(K.extracted_value_present, "author in analysis", target="author"),
        ],
        timeout_ms=60_000, max_steps=8, retry_budget=1, expected_step_range=(1, 4),
        notes="DOM extraction quality on a busy real page; context_compression test.",
    ))

    tasks.append(M0TaskDefinition(
        task_id="docs_google_com__create_type", site_id="docs_google_com", website="Google Docs",
        difficulty=Difficulty.medium, category=BenchmarkCategory.form_submit,
        goal='Open a new Google Doc, type "Hello from the benchmark", and confirm the text appears',
        start_url="https://docs.new",
        preconditions=Preconditions(auth_required=True, auth_strategy="session_state",
                                    auth_state_file="google_com.json"),
        success_criteria=[
            _c(K.dom_text_present, "typed text", target="Hello from the benchmark"),
            _c(K.url_matches, "doc opened", target=r"docs\.google\.com/document"),
        ],
        failure_criteria=[_fc(FK.url_matches_error, "auth expired", target=r"accounts\.google\.com")],
        timeout_ms=120_000, max_steps=10, retry_budget=2,
        notes="Canvas/contenteditable editor — expected hard baseline failure (VISION_REQUIRED).",
    ))

    tasks.append(M0TaskDefinition(
        task_id="booking_com__hotel_search", site_id="booking_com", website="Booking.com",
        difficulty=Difficulty.medium, category=BenchmarkCategory.search,
        goal=("Search for hotels in Bangalore for check-in next Saturday, check-out next Sunday, "
              "1 adult, and confirm hotel results appear"),
        start_url="https://www.booking.com",
        success_criteria=[
            _c(K.url_matches, "city search", target=r"dest_type=city"),
        ],
        failure_criteria=[
            _fc(FK.dom_error_present, "no properties", target="couldn't find any available properties"),
            _fc(FK.http_error, "blocked", target="403"),
        ],
        timeout_ms=120_000, max_steps=15, retry_budget=2,
        notes="Date-picker widget interaction.",
    ))

    tasks.append(M0TaskDefinition(
        task_id="fixture__multistep_form", site_id="fixture_server", website="Fixture: Wizard",
        difficulty=Difficulty.medium, category=BenchmarkCategory.multistep, is_fixture=True,
        goal=('Complete the onboarding wizard: enter full name "Test User" in step 1, '
              'then enter role "Engineer" in step 2, then click Finish'),
        start_url=f"{FB}/multistep",
        success_criteria=[
            _c(K.dom_text_present, "complete", target="Onboarding complete"),
            _c(K.min_completed_steps, "multi-step", value=4),
        ],
        timeout_ms=30_000, max_steps=6, retry_budget=1,
    ))

    tasks.append(M0TaskDefinition(
        task_id="canva_com__create_design", site_id="canva_com", website="Canva",
        difficulty=Difficulty.medium, category=BenchmarkCategory.navigation,
        goal='Create a new "Presentation" design in Canva and confirm the editor opens',
        start_url="https://www.canva.com",
        preconditions=Preconditions(auth_required=True, auth_strategy="session_state",
                                    auth_state_file="canva_com.json"),
        success_criteria=[
            _c(K.url_matches, "design editor", target=r"/design/"),
        ],
        failure_criteria=[_fc(FK.url_matches_error, "auth expired", target=r"canva\.com/login")],
        timeout_ms=120_000, max_steps=12, retry_budget=2,
        notes="Heavy React SPA; reasoning stress on a busy UI.",
    ))

    tasks.append(M0TaskDefinition(
        task_id="fixture__infinite_scroll", site_id="fixture_server", website="Fixture: Feed",
        difficulty=Difficulty.medium, category=BenchmarkCategory.infinite_scroll, is_fixture=True,
        goal="Scroll the feed to load more posts until at least 6 posts are visible",
        start_url=f"{FB}/scroll",
        success_criteria=[_c(K.dom_text_present, ">=6 posts", target="6 posts")],
        timeout_ms=30_000, max_steps=8, retry_budget=2,
    ))

    tasks.append(M0TaskDefinition(
        task_id="makemytrip_com__flight_search", site_id="makemytrip_com", website="MakeMyTrip",
        difficulty=Difficulty.medium, category=BenchmarkCategory.search,
        goal=("Search for one-way flights from Mumbai (BOM) to Delhi (DEL) for the first day of "
              "next month and confirm flight results appear"),
        start_url="https://www.makemytrip.com/flights/",
        success_criteria=[
            _c(K.url_matches, "BOM->DEL", target=r"(BOM|Mumbai)"),
        ],
        failure_criteria=[
            _fc(FK.dom_error_present, "no flights", target="no flights found"),
            _fc(FK.http_error, "rate limited", target="429"),
        ],
        timeout_ms=180_000, max_steps=20, retry_budget=3,
        notes="City autocomplete + date picker + traveler count; high grounding challenge.",
    ))

    # ─────────────────────────── COMPLEX TIER (19–24) ────────────────────────
    tasks.append(M0TaskDefinition(
        task_id="amazon_in__add_to_cart", site_id="amazon_in", website="Amazon India",
        difficulty=Difficulty.complex, category=BenchmarkCategory.multistep,
        goal=('Search for "USB-C cable", open the first result that is Prime-eligible, '
              "and add it to the cart"),
        start_url="https://www.amazon.in",
        success_criteria=[
            _c(K.dom_text_present, "added to cart", target="Added to Cart"),
        ],
        failure_criteria=[
            _fc(FK.dom_error_present, "captcha", target="CAPTCHA"),
            _fc(FK.dom_error_present, "unavailable", target="Currently unavailable"),
        ],
        human_intervention_rules=HumanInterventionRules(danger_actions="require_human",
                                                        caution_actions="auto_approve"),
        timeout_ms=180_000, max_steps=20, retry_budget=3, expected_step_range=(6, 15),
        notes="Add-to-cart is caution (not danger=checkout). Logged, not blocked.",
    ))

    tasks.append(M0TaskDefinition(
        task_id="gmail_com__read_summarize", site_id="gmail_com", website="Gmail",
        difficulty=Difficulty.complex, category=BenchmarkCategory.navigation,
        goal="Open the most recent email in the inbox and provide a one-sentence summary of its content",
        start_url="https://mail.google.com/mail/u/0/#inbox",
        preconditions=Preconditions(auth_required=True, auth_strategy="session_state",
                                    auth_state_file="google_com.json"),
        success_criteria=[
            _c(K.url_matches, "email opened", target=r"#inbox/"),
            _c(K.extracted_value_present, "summary in analysis", target="summary"),
        ],
        failure_criteria=[
            _fc(FK.url_matches_error, "auth expired", target=r"accounts\.google\.com"),
            _fc(FK.dom_error_present, "disabled", target="account has been temporarily disabled"),
        ],
        timeout_ms=120_000, max_steps=10, retry_budget=2,
        notes="Read path only; no sending.",
    ))

    tasks.append(M0TaskDefinition(
        task_id="fixture__table_edit", site_id="fixture_server", website="Fixture: CRUD",
        difficulty=Difficulty.complex, category=BenchmarkCategory.table_edit, is_fixture=True,
        goal="Edit the first row in the customer table and confirm the row is updated",
        start_url=f"{FB}/crud",
        success_criteria=[_c(K.dom_text_present, "row updated", target="Row updated")],
        timeout_ms=30_000, max_steps=6, retry_budget=1,
    ))

    tasks.append(M0TaskDefinition(
        task_id="cross_site__amazon_search_github_compare", site_id="cross_site",
        website="Cross-Site (Amazon->GitHub)", difficulty=Difficulty.complex,
        category=BenchmarkCategory.cross_site,
        goal=('On Amazon, search for a "Raspberry Pi 4" product. Then, on GitHub, search for the '
              '"raspberrypi/linux" repository. Confirm both searches succeeded and report the '
              "Amazon price and the GitHub star count."),
        start_url="https://www.amazon.in",
        success_criteria=[
            _c(K.extracted_value_present, "amazon price", target="₹"),
            _c(K.extracted_value_present, "github stars", target="star"),
        ],
        failure_criteria=[_fc(FK.dom_error_present, "captcha", target="CAPTCHA")],
        timeout_ms=240_000, max_steps=25, retry_budget=3, expect_failure=True,
        notes="Expected baseline failure: no multi-tab coordination (tabs subsystem orphaned). "
              "Documents the ORCHESTRATION gap M4 addresses.",
    ))

    tasks.append(M0TaskDefinition(
        task_id="sheets_google_com__enter_data", site_id="sheets_google_com", website="Google Sheets",
        difficulty=Difficulty.complex, category=BenchmarkCategory.form_submit,
        goal=("Open a new Google Sheet, click on cell A1, type the number 42, press Enter, "
              "and confirm the value is in cell A1"),
        start_url="https://sheets.new",
        preconditions=Preconditions(auth_required=True, auth_strategy="session_state",
                                    auth_state_file="google_com.json"),
        success_criteria=[
            _c(K.url_matches, "sheet opened", target=r"spreadsheets"),
            _c(K.dom_text_present, "value entered", target="42"),
        ],
        failure_criteria=[_fc(FK.url_matches_error, "auth expired", target=r"accounts\.google\.com")],
        timeout_ms=150_000, max_steps=12, retry_budget=3, expect_failure=True,
        notes="Canvas cell grid — coordinate interaction. Expected VISION_REQUIRED baseline failure.",
    ))

    tasks.append(M0TaskDefinition(
        task_id="generic_gov__form_fill", site_id="fixture_server",
        website="Fixture: Government-style Form", difficulty=Difficulty.complex,
        category=BenchmarkCategory.form_submit, is_fixture=True,
        goal=('Complete the registration form: enter name into email/password fields, '
              'select country "India", accept terms, then submit and confirm the success message'),
        start_url=f"{FB}/register",
        success_criteria=[_c(K.dom_text_present, "account created", target="Account created")],
        timeout_ms=45_000, max_steps=8, retry_budget=2,
        notes="Reuses the registration fixture: select dropdown + checkbox + submit.",
    ))

    # ───────────────────── CAPABILITY-SPECIFIC TASKS (25–27) ──────────────────
    tasks.append(M0TaskDefinition(
        task_id="fixture__file_download", site_id="fixture_server", website="Fixture: Download",
        difficulty=Difficulty.simple, category=BenchmarkCategory.download, is_fixture=True,
        goal="Click the download link to download the report file",
        start_url=f"{FB}/download",
        success_criteria=[
            _c(K.dom_element_present, "download link", target="#dl"),
            _c(K.min_completed_steps, "navigate + click", value=2),
        ],
        expected_artifacts=[ArtifactSpec("download_file", "download_file", "captured report.txt")],
        timeout_ms=20_000, max_steps=3, retry_budget=1,
    ))

    tasks.append(M0TaskDefinition(
        task_id="fixture__dynamic_load", site_id="fixture_server", website="Fixture: Dynamic",
        difficulty=Difficulty.simple, category=BenchmarkCategory.dynamic_loading, is_fixture=True,
        goal='Wait for the "Ready" button to appear (it loads after a delay) and click it',
        start_url=f"{FB}/dynamic",
        success_criteria=[_c(K.dom_text_present, "loaded", target="Loaded")],
        timeout_ms=20_000, max_steps=5, retry_budget=2,
        notes="Tests wait/retry behaviour for late-rendered elements.",
    ))

    tasks.append(M0TaskDefinition(
        task_id="fixture__accordion", site_id="fixture_server", website="Fixture: FAQ Accordion",
        difficulty=Difficulty.simple, category=BenchmarkCategory.accordion, is_fixture=True,
        goal='Expand the second FAQ question ("How much?") and confirm its answer is visible',
        start_url=f"{FB}/accordion",
        success_criteria=[_c(K.dom_text_present, "expanded", target="q2 expanded")],
        timeout_ms=15_000, max_steps=3, retry_budget=1,
    ))

    return tasks


def scenarios_by_id() -> dict[str, M0TaskDefinition]:
    return {t.task_id: t for t in build_m0_scenarios()}
