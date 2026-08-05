from __future__ import annotations

from app.core.config import settings
from app.knowledge_extraction.engine import KnowledgeExtractionPipeline
from app.knowledge_extraction.extraction_engine import required_fields_for_task
from app.knowledge_extraction.page_reader import read_page
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
