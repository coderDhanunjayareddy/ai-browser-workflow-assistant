from __future__ import annotations

from app.core.config import settings
from app.knowledge_extraction.collection_policy import build_collection_policy, evaluate_collection_page
from app.knowledge_extraction.engine import KnowledgeExtractionPipeline
from app.knowledge_extraction.extraction_engine import required_fields_for_task
from app.knowledge_extraction.page_reader import read_page
from app.knowledge_extraction.research_spec import build_research_mission_spec
from app.knowledge_extraction.report_engine import generate_report
from app.knowledge_extraction.synthesizer import synthesize_knowledge
from app.knowledge_extraction.validator import validate_records, validation_summary
from app.schemas.request import ContentBlock, InteractiveElement, PageContext
from app.schemas.response import AnalyzeResponse, SuggestedAction


def _page(text: str, *, title: str = "Example Tool", url: str = "https://example.test/tool") -> PageContext:
    return PageContext(
        url=url,
        title=title,
        metadata={"description": "Example page"},
        interactive_elements=[
            InteractiveElement(type="a", selector="#pricing", text="Pricing", href=f"{url}/pricing", visible=True),
            InteractiveElement(type="input", selector="#email", text="", placeholder="Email", input_type="email", visible=True),
        ],
        content_blocks=[ContentBlock(selector="#main", text=text, href=url)],
        headings=[title],
        selected_text="",
        visible_text=text,
        images=[],
    )


def _directory_page(*, url: str = "https://directory.example/page/1") -> PageContext:
    return PageContext(
        url=url,
        title="Example Directory",
        metadata={"description": "Directory page"},
        interactive_elements=[
            InteractiveElement(type="a", selector="#acme", text="Acme Labs", href="https://directory.example/acme", visible=True),
            InteractiveElement(type="a", selector="#beta", text="Beta Systems", href="https://directory.example/beta", visible=True),
            InteractiveElement(type="a", selector="#next", text="Next", href="https://directory.example/page/2", visible=True),
        ],
        content_blocks=[
            ContentBlock(selector=".item-a", text="Acme Labs Contact hello@acme.test Phone +1 555 123 4567", href="https://directory.example/acme"),
            ContentBlock(selector=".item-b", text="Beta Systems Contact team@beta.test Phone +1 555 987 6543", href="https://directory.example/beta"),
        ],
        headings=["Example Directory"],
        selected_text="",
        visible_text="Acme Labs Contact hello@acme.test Phone +1 555 123 4567\nBeta Systems Contact team@beta.test Phone +1 555 987 6543",
        images=[],
    )


def _quotes_page(*, url: str = "https://quotes.toscrape.com/page/1/") -> PageContext:
    return PageContext(
        url=url,
        title="Quotes to Scrape",
        metadata={"description": "Practice scraping page"},
        interactive_elements=[
            InteractiveElement(type="a", selector=".quote:nth-child(1) .author", text="(about)", href="https://quotes.toscrape.com/author/Albert-Einstein", visible=True),
            InteractiveElement(type="a", selector=".quote:nth-child(2) .author", text="(about)", href="https://quotes.toscrape.com/author/J-K-Rowling", visible=True),
            InteractiveElement(type="a", selector=".next a", text="Next", href="https://quotes.toscrape.com/page/2/", visible=True),
        ],
        content_blocks=[
            ContentBlock(
                selector=".quote:nth-child(1)",
                text="“The world as we have created it is a process of our thinking.” by Albert Einstein Tags: change, deep-thoughts, thinking, world",
                href=url,
            ),
            ContentBlock(
                selector=".quote:nth-child(2)",
                text="“It is our choices, Harry, that show what we truly are.” by J.K. Rowling Tags: abilities, choices",
                href=url,
            ),
        ],
        headings=["Quotes to Scrape"],
        selected_text="",
        visible_text="",
        images=[],
    )


def test_v50_flags_default_to_shadow():
    assert settings.__class__.model_fields["v50_page_reader"].default == "shadow"
    assert settings.__class__.model_fields["v50_extraction_engine"].default == "shadow"
    assert settings.__class__.model_fields["v50_synthesis"].default == "shadow"
    assert settings.__class__.model_fields["v50_report_engine"].default == "shadow"
    assert settings.__class__.model_fields["v50_extraction_validation"].default == "shadow"


def test_page_reader_extracts_structured_visible_content():
    artifact = read_page(_page("Free plan available. Contact support@example.test for details."))

    assert artifact.title == "Example Tool"
    assert artifact.pricing_blocks
    assert artifact.contact_blocks
    assert artifact.forms[0]["selector"] == "#email"


def test_collection_policy_detects_directory_items_and_next_page():
    policy = build_collection_policy("Collect 20 entries from a multi-page directory.")
    read = read_page(_directory_page())

    state = evaluate_collection_page(read, policy)

    assert policy is not None
    assert policy.collection_type == "directory"
    assert state.item_candidates
    assert {item.name for item in state.item_candidates} >= {"Acme Labs", "Beta Systems"}
    assert state.next_url == "https://directory.example/page/2"
    assert state.should_continue is True


def test_collection_pipeline_emits_item_level_directory_records(monkeypatch):
    monkeypatch.setattr(settings, "v50_page_reader", "active")
    monkeypatch.setattr(settings, "v50_extraction_engine", "active")
    monkeypatch.setattr(settings, "v50_extraction_validation", "active")
    monkeypatch.setattr(settings, "v50_synthesis", "active")
    monkeypatch.setattr(settings, "v50_report_engine", "active")
    pipeline = KnowledgeExtractionPipeline()

    snapshot = pipeline.observe(
        session_id="directory-collection",
        task="Collect 20 entries from a multi-page directory with name, website, email, and phone.",
        page_context=_directory_page(),
        current_phase="EXTRACT",
    )

    assert snapshot.collection_state is not None
    assert snapshot.collection_state.next_url == "https://directory.example/page/2"
    assert len(snapshot.extraction_records) >= 2
    assert all(record.entity_type == "directory_entry" for record in snapshot.extraction_records)
    assert {record.fields["name"] for record in snapshot.extraction_records} >= {"Acme Labs", "Beta Systems"}


def test_collection_pipeline_extracts_quote_card_fields(monkeypatch):
    monkeypatch.setattr(settings, "v50_page_reader", "active")
    monkeypatch.setattr(settings, "v50_extraction_engine", "active")
    monkeypatch.setattr(settings, "v50_extraction_validation", "active")
    monkeypatch.setattr(settings, "v50_synthesis", "active")
    monkeypatch.setattr(settings, "v50_report_engine", "active")
    pipeline = KnowledgeExtractionPipeline()
    task = """Collect 20 entries from this multi-page directory.
Extract:
- quote text
- author
- tags
- source URL
Return a table only."""

    snapshot = pipeline.observe(
        session_id="quote-card-collection",
        task=task,
        page_context=_quotes_page(),
        current_phase="EXTRACT",
    )

    assert snapshot.collection_state is not None
    assert snapshot.collection_state.next_url == "https://quotes.toscrape.com/page/2"
    assert len(snapshot.extraction_records) >= 2
    first = snapshot.extraction_records[0]
    assert first.fields["quote_text"].startswith("The world as we have created it")
    assert first.fields["author"] == "Albert Einstein"
    assert "thinking" in first.fields["tags"]
    assert first.fields["source_url"].rstrip("/") == "https://quotes.toscrape.com/page/1"


def test_page_reader_extracts_serialized_runtime_page_context():
    artifact = read_page(
        {
            "url": "https://www.firecrawl.dev/blog/best-browser-agents",
            "title": "11 Best AI Browser Agents in 2026",
            "metadata": {"description": "AI browser agent comparison"},
            "interactive_elements": [
                {
                    "type": "a",
                    "selector": "#pricing",
                    "text": "Pricing",
                    "href": "https://www.firecrawl.dev/pricing",
                    "visible": True,
                }
            ],
            "content_blocks": [
                {"selector": "h1", "text": "11 Best AI Browser Agents in 2026"},
                {"selector": "p", "text": "Free plan available for browser automation workflows."},
            ],
            "headings": ["11 Best AI Browser Agents in 2026"],
            "selected_text": "",
            "visible_text": "AI browser agents automate search and extraction.",
            "images": [],
        }
    )

    assert artifact.title == "11 Best AI Browser Agents in 2026"
    assert artifact.canonical_url == "https://www.firecrawl.dev/blog/best-browser-agents"
    assert "Free plan available" in artifact.paragraphs[1]
    assert artifact.pricing_blocks
    assert artifact.navigation_context[0]["url"] == "https://www.firecrawl.dev/pricing"


def test_research_pipeline_generates_comparison_report(monkeypatch):
    monkeypatch.setattr(settings, "v50_page_reader", "active")
    monkeypatch.setattr(settings, "v50_extraction_engine", "active")
    monkeypatch.setattr(settings, "v50_extraction_validation", "active")
    monkeypatch.setattr(settings, "v50_synthesis", "active")
    monkeypatch.setattr(settings, "v50_report_engine", "active")
    pipeline = KnowledgeExtractionPipeline()
    task = "Extract Tool, Purpose, Pricing, Limitation, URL and produce a comparison table."

    snapshot = pipeline.observe(
        session_id="research",
        task=task,
        page_context=_page("Example Tool automates browser workflows. Free plan available. Limited enterprise controls."),
        current_phase="READ",
    )

    assert snapshot is not None
    assert snapshot.report_artifact is not None
    assert "| tool | purpose | pricing | limitation | url |" in snapshot.report_artifact.content


def test_research_pipeline_keeps_opened_sources_with_missing_mentions(monkeypatch):
    monkeypatch.setattr(settings, "v50_page_reader", "active")
    monkeypatch.setattr(settings, "v50_extraction_engine", "active")
    monkeypatch.setattr(settings, "v50_extraction_validation", "active")
    monkeypatch.setattr(settings, "v50_synthesis", "active")
    monkeypatch.setattr(settings, "v50_report_engine", "active")
    pipeline = KnowledgeExtractionPipeline()
    task = "Extract Tool, Purpose, Pricing, Limitation, URL and produce a clean comparison table only."
    pages = [
        _page("Tool A automates browser workflows. Free plan available. Limited enterprise controls.", title="Tool A", url="https://example.test/a"),
        _page("Tool B helps teams compare AI browser agents for scraping and automation.", title="Tool B", url="https://example.test/b"),
        _page("Tool C records browser tasks. Paid plan starts at $20. Requires API setup.", title="Tool C", url="https://example.test/c"),
        _page("Tool D extracts data from websites and handles forms.", title="Tool D", url="https://example.test/d"),
        _page("Tool E runs web automation. Trial credits are included. Cannot solve every CAPTCHA.", title="Tool E", url="https://example.test/e"),
    ]

    snapshot = None
    for page in pages:
        snapshot = pipeline.observe(session_id="research-five", task=task, page_context=page, current_phase="EXTRACT")

    assert snapshot is not None
    assert snapshot.report_artifact is not None
    rows = snapshot.report_artifact.structured["rows"]
    assert len(rows) == 5
    assert any(row["pricing"] == "Not mentioned" for row in rows)
    assert any(row["limitation"] == "Not mentioned" for row in rows)
    assert all("\n" not in cell for row in rows for cell in row.values())
    assert all(len(cell) <= 220 for row in rows for cell in row.values())


def test_extraction_records_include_field_level_source_evidence(monkeypatch):
    monkeypatch.setattr(settings, "v50_page_reader", "active")
    monkeypatch.setattr(settings, "v50_extraction_engine", "active")
    monkeypatch.setattr(settings, "v50_extraction_validation", "active")
    monkeypatch.setattr(settings, "v50_synthesis", "active")
    monkeypatch.setattr(settings, "v50_report_engine", "active")
    pipeline = KnowledgeExtractionPipeline()

    snapshot = pipeline.observe(
        session_id="field-evidence",
        task="Extract Tool, Purpose, Pricing, Limitation, URL and produce a clean comparison table.",
        page_context=_page(
            "FieldBot automates browser workflows for QA teams. Free plan available. Requires API setup.",
            title="FieldBot",
            url="https://example.test/fieldbot",
        ),
        current_phase="EXTRACT",
    )

    record = snapshot.extraction_records[0]
    assert record.field_evidence["tool"].source_kind == "title"
    assert record.field_evidence["tool"].source_url == "https://example.test/fieldbot"
    assert record.field_evidence["purpose"].source_text
    assert record.field_evidence["pricing"].confidence > 0
    serialized = record.to_dict()
    assert serialized["field_evidence"]["pricing"]["source_url"] == "https://example.test/fieldbot"


def test_missing_research_fields_have_missing_reason(monkeypatch):
    monkeypatch.setattr(settings, "v50_page_reader", "active")
    monkeypatch.setattr(settings, "v50_extraction_engine", "active")
    monkeypatch.setattr(settings, "v50_extraction_validation", "active")
    monkeypatch.setattr(settings, "v50_synthesis", "active")
    monkeypatch.setattr(settings, "v50_report_engine", "active")
    pipeline = KnowledgeExtractionPipeline()

    snapshot = pipeline.observe(
        session_id="field-missing-reason",
        task="Extract Tool, Purpose, Pricing, Limitation, URL and produce a clean comparison table.",
        page_context=_page(
            "PlainTool helps teams organize browser research tasks.",
            title="PlainTool",
            url="https://example.test/plain",
        ),
        current_phase="EXTRACT",
    )

    record = snapshot.extraction_records[0]
    assert record.fields["pricing"] == "Not mentioned"
    assert record.field_evidence["pricing"].source_kind == "missing"
    assert record.field_evidence["pricing"].missing_reason
    assert record.fields["limitation"] == "Not mentioned"
    assert record.field_evidence["limitation"].missing_reason


def test_pricing_pages_emit_pricing_plan_entity(monkeypatch):
    monkeypatch.setattr(settings, "v50_page_reader", "active")
    monkeypatch.setattr(settings, "v50_extraction_engine", "active")
    monkeypatch.setattr(settings, "v50_extraction_validation", "active")
    monkeypatch.setattr(settings, "v50_synthesis", "active")
    pipeline = KnowledgeExtractionPipeline()

    snapshot = pipeline.observe(
        session_id="pricing-entity",
        task="Compare AI code assistant pricing with Tool, Purpose, Pricing, Limitation, URL.",
        page_context=_page(
            "Pro plan costs $20 per month. Free trial available. Enterprise plan requires sales.",
            title="CodeMate Pricing",
            url="https://codemate.example/pricing",
        ),
        current_phase="EXTRACT",
    )

    record = snapshot.extraction_records[0]
    assert record.entity_type == "pricing_plan"
    assert record.entity["price_text"]
    assert record.entity["billing_period"] == "monthly"


def test_documentation_pages_emit_documentation_entity(monkeypatch):
    monkeypatch.setattr(settings, "v50_page_reader", "active")
    monkeypatch.setattr(settings, "v50_extraction_engine", "active")
    monkeypatch.setattr(settings, "v50_extraction_validation", "active")
    monkeypatch.setattr(settings, "v50_synthesis", "active")
    pipeline = KnowledgeExtractionPipeline()

    snapshot = pipeline.observe(
        session_id="docs-entity",
        task="Extract supported languages, setup requirement, and browser control from documentation.",
        page_context=_page(
            "Install with npm install browser-agent. Supports Python and TypeScript SDKs for browser automation control.",
            title="Browser Agent Docs",
            url="https://docs.browseragent.example/quickstart",
        ),
        current_phase="EXTRACT",
    )

    record = snapshot.extraction_records[0]
    assert record.entity_type == "documentation_page"
    assert record.entity["official_source_hint"] is True
    assert "Browser Agent Docs" == record.entity["title"]


def test_job_pages_emit_job_posting_entity(monkeypatch):
    monkeypatch.setattr(settings, "v50_page_reader", "active")
    monkeypatch.setattr(settings, "v50_extraction_engine", "active")
    monkeypatch.setattr(settings, "v50_extraction_validation", "active")
    monkeypatch.setattr(settings, "v50_synthesis", "active")
    pipeline = KnowledgeExtractionPipeline()

    snapshot = pipeline.observe(
        session_id="job-entity",
        task="Collect jobs with title, company, location, experience and apply URL.",
        page_context=_page(
            "Senior Frontend Engineer job. Remote location. 5 years experience required. Apply now.",
            title="Senior Frontend Engineer - Acme",
            url="https://acme.example/careers/frontend",
        ),
        current_phase="EXTRACT",
    )

    record = snapshot.extraction_records[0]
    assert record.entity_type == "job_posting"
    assert record.entity["title"] == "Senior Frontend Engineer - Acme"
    assert record.entity["apply_url"] == "https://acme.example/careers/frontend"


def test_contact_directory_pages_emit_directory_entity(monkeypatch):
    monkeypatch.setattr(settings, "v50_page_reader", "active")
    monkeypatch.setattr(settings, "v50_extraction_engine", "active")
    monkeypatch.setattr(settings, "v50_extraction_validation", "active")
    monkeypatch.setattr(settings, "v50_synthesis", "active")
    pipeline = KnowledgeExtractionPipeline()

    snapshot = pipeline.observe(
        session_id="directory-entity",
        task="Find and extract contact email and phone from a directory.",
        page_context=_page(
            "Directory listing for Example Labs. Contact hello@example.test. Phone +1 555 123 4567.",
            title="Example Labs",
            url="https://directory.example/labs",
        ),
        current_phase="EXTRACT",
    )

    record = snapshot.extraction_records[0]
    assert record.entity_type == "directory_entry"
    assert record.entity["email"] == "hello@example.test"
    assert record.entity["phone"]


def test_research_mission_spec_parses_task1_contract():
    spec = build_research_mission_spec(
        "Open Google Search and search for: best AI browser automation tools 2026. "
        "From the first page of results open the top 5 relevant results. "
        "Create a clean comparison table with columns: Tool, Purpose, Pricing, Limitation, URL. "
        "Return the table only."
    )

    assert spec is not None
    assert spec.query == "best AI browser automation tools 2026"
    assert spec.source_count == 5
    assert spec.required_fields == ["tool", "purpose", "pricing", "limitation", "url"]
    assert spec.output_format == "markdown"
    assert "final_artifact_generated_from_extraction_records" in spec.completion_criteria


def test_research_pipeline_uses_spec_source_count_completion_gate(monkeypatch):
    monkeypatch.setattr(settings, "v50_page_reader", "active")
    monkeypatch.setattr(settings, "v50_extraction_engine", "active")
    monkeypatch.setattr(settings, "v50_extraction_validation", "active")
    monkeypatch.setattr(settings, "v50_synthesis", "active")
    monkeypatch.setattr(settings, "v50_report_engine", "active")
    pipeline = KnowledgeExtractionPipeline()
    task = (
        "Search for: best AI browser automation tools 2026. "
        "Open the top 5 relevant results. "
        "Create a clean comparison table with columns: Tool, Purpose, Pricing, Limitation, URL."
    )

    first = pipeline.observe(
        session_id="research-gated",
        task=task,
        page_context=_page("Tool A automates browsers. Free plan available. Limited support.", title="Tool A", url="https://example.test/a"),
        current_phase="EXTRACT",
    )

    assert first is not None
    assert first.research_spec is not None
    assert first.research_spec.source_count == 5
    assert first.completion_status["source_count"] is False
    assert first.completion_status["extract"] is False

    snapshot = first
    for index in range(2, 6):
        snapshot = pipeline.observe(
            session_id="research-gated",
            task=task,
            page_context=_page(
                f"Tool {index} automates browser workflows. Not mentioned. Requires setup.",
                title=f"Tool {index}",
                url=f"https://example.test/{index}",
            ),
            current_phase="EXTRACT",
        )

    assert snapshot is not None
    assert snapshot.completion_status["source_count"] is True
    assert snapshot.completion_status["extract"] is True
    assert snapshot.knowledge_artifact is not None
    assert snapshot.knowledge_artifact.content["research_spec"]["source_count"] == 5
    assert snapshot.report_artifact is not None
    assert len(snapshot.report_artifact.structured["rows"]) == 5


def test_research_pipeline_does_not_extract_google_serp_as_source(monkeypatch):
    monkeypatch.setattr(settings, "v50_page_reader", "active")
    monkeypatch.setattr(settings, "v50_extraction_engine", "active")
    monkeypatch.setattr(settings, "v50_extraction_validation", "active")
    monkeypatch.setattr(settings, "v50_synthesis", "active")
    monkeypatch.setattr(settings, "v50_report_engine", "active")
    pipeline = KnowledgeExtractionPipeline()
    task = "Extract Tool, Purpose, Pricing, Limitation, URL and produce a clean comparison table only."

    serp_snapshot = pipeline.observe(
        session_id="research-serp-ignore",
        task=task,
        page_context=_page(
            "Result one Result two Result three",
            title="best AI browser automation tools 2026 - Google Search",
            url="https://www.google.com/search?q=best+AI+browser+automation+tools+2026",
        ),
        current_phase="SEARCH",
    )
    source_snapshot = pipeline.observe(
        session_id="research-serp-ignore",
        task=task,
        page_context=_page(
            "Tool A automates browser workflows. Free plan available. Limited enterprise controls.",
            title="Tool A",
            url="https://example.test/a",
        ),
        current_phase="EXTRACT",
    )

    assert serp_snapshot is not None
    assert len(serp_snapshot.extraction_records) == 0
    assert source_snapshot is not None
    assert [row["url"] for row in source_snapshot.report_artifact.structured["rows"]] == ["https://example.test/a"]


def test_job_search_required_fields_are_generic():
    fields = required_fields_for_task("Collect jobs with title, company, location, experience and apply URL.")

    assert {"title", "company", "location", "experience", "apply_url"} <= set(fields)


def test_documentation_extraction_fields_are_generic():
    fields = required_fields_for_task("Extract supported languages, setup requirement, and browser control from documentation.")

    assert {"languages", "setup_requirement", "browser_control"} <= set(fields)


def test_validation_reports_missing_fields():
    pipeline = KnowledgeExtractionPipeline()
    snapshot = pipeline.observe(
        session_id="missing",
        task="Extract Tool, Purpose, Pricing, Limitation, URL.",
        page_context=_page("", title="", url="https://example.test/empty"),
        current_phase="EXTRACT",
    )

    assert snapshot is not None
    assert snapshot.missing_artifacts
    assert any(not record.validation.get("valid") for record in snapshot.extraction_records)


def test_registry_deduplicates_same_source_record():
    pipeline = KnowledgeExtractionPipeline()
    task = "Extract Tool, Purpose, Pricing, Limitation, URL."
    page = _page("Example Tool automates browsers. Free plan available. Limited support.")

    first = pipeline.observe(session_id="dedupe", task=task, page_context=page, current_phase="READ")
    second = pipeline.observe(session_id="dedupe", task=task, page_context=page, current_phase="READ")

    assert first is not None and second is not None
    assert len(second.extraction_records) == len(first.extraction_records)
    assert second.telemetry.duplicate_count >= 1


def test_report_generation_supports_markdown_json_and_csv():
    pipeline = KnowledgeExtractionPipeline()
    snapshot = pipeline.observe(
        session_id="formats",
        task="Extract Tool, Purpose, Pricing, Limitation, URL.",
        page_context=_page("Example Tool automates browsers. Free plan available. Limited support."),
        current_phase="READ",
    )
    knowledge = snapshot.knowledge_artifact

    assert generate_report(knowledge, output_format="markdown").content.startswith("|")
    assert generate_report(knowledge, output_format="json").content.startswith("{")
    assert "tool" in generate_report(knowledge, output_format="csv").content.splitlines()[0]


def test_contact_form_upload_download_tasks_have_typed_fields():
    assert "email" in required_fields_for_task("Find and extract contact email and phone.")
    assert "field" in required_fields_for_task("Fill the form and report validation errors.")
    assert "filename" in required_fields_for_task("Upload a file and report status and share link.")


def test_synthesis_uses_validated_records_only():
    pipeline = KnowledgeExtractionPipeline()
    snapshot = pipeline.observe(
        session_id="synthesis",
        task="Extract Tool, Purpose, Pricing, Limitation, URL.",
        page_context=_page("Example Tool automates browsers. Free plan available. Limited support."),
        current_phase="EXTRACT",
    )
    required = required_fields_for_task("Extract Tool, Purpose, Pricing, Limitation, URL.")
    records = validate_records(snapshot.extraction_records, required)
    knowledge = synthesize_knowledge(records, required, "comparison")

    assert validation_summary(records)["record_count"] >= 1
    assert knowledge is not None
    assert knowledge.content["rows"]


def test_synthesize_phase_produces_report_evidence_without_declaring_completion(monkeypatch):
    monkeypatch.setattr(settings, "v50_page_reader", "active")
    monkeypatch.setattr(settings, "v50_extraction_engine", "active")
    monkeypatch.setattr(settings, "v50_extraction_validation", "active")
    monkeypatch.setattr(settings, "v50_synthesis", "active")
    monkeypatch.setattr(settings, "v50_report_engine", "active")
    pipeline = KnowledgeExtractionPipeline()
    snapshot = pipeline.observe(
        session_id="synthesize-report-owner",
        task="Extract Tool, Purpose, Pricing, Limitation, URL.",
        page_context=_page("Example Tool automates browsers. Free plan available. Limited support."),
        current_phase="SYNTHESIZE",
    )
    planner_wait = AnalyzeResponse(
        session_id="synthesize-report-owner",
        analysis="Wait for extraction to complete.",
        outcome_kind="act",
        suggested_actions=[
            SuggestedAction(
                action_id="wait",
                action_type="wait",  # type: ignore[arg-type]
                target_selector="window",
                value="1000",
                description="Wait",
                reasoning="Planner wants to wait.",
                confidence=0.7,
                safety_level="safe",  # type: ignore[arg-type]
            )
        ],
    )

    result = pipeline.postprocess_response(planner_wait, snapshot)

    assert snapshot.report_artifact is not None
    assert snapshot.report_artifact.completion_status == "complete"
    assert result is planner_wait
    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].action_type == "wait"
