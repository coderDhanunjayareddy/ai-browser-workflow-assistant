from __future__ import annotations

from app.feature_flags import is_shadow_or_active
from app.observability.metrics import default_metric_sink
from app.schemas.request import ContentBlock, InteractiveElement, PageContext
from app.semantic_page.builder import SemanticPageGraphBuilder
from app.verification import ValidationEngine, replay_validation
from app.verification.telemetry import record_validation_metrics


def sample_page() -> PageContext:
    return PageContext(
        url="https://example.test/invoice",
        title="Invoice Details",
        metadata={"lang": "en"},
        headings=["Invoice Details"],
        content_blocks=[
            ContentBlock(selector="#total", text="Total Due INR 14,632.00"),
            ContentBlock(selector="#status", text="Status Paid"),
        ],
        interactive_elements=[
            InteractiveElement(
                type="button",
                text="Download PDF",
                selector="#download",
                visible=True,
            ),
        ],
        selected_text="",
        visible_text="Invoice Number INV-100 Total Due INR 14,632.00 Payment Terms Net 30",
    )


def test_report_validation_satisfied_maps_to_sgv_compatibility():
    page = sample_page()
    graph = SemanticPageGraphBuilder().build(page)

    validation, latency_ms = ValidationEngine().validate_report(
        run_id="run-1",
        mission_id="run-1",
        step_id="planner.report.1",
        claim="The invoice total is visible.",
        answer="INR 14,632.00",
        page_context=page,
        semantic_graph=graph,
    )

    assert validation.schema_version == "validation.v1"
    assert validation.validation_status == "satisfied"
    assert validation.status == "satisfied"
    assert validation.sgv_verified is True
    assert validation.failure_category is None
    assert validation.confidence >= 0.9
    assert validation.replay_metadata["semantic_graph_id"] == graph.graph_id
    assert latency_ms < 50


def test_report_validation_missing_answer_is_uncertain():
    validation, _ = ValidationEngine().validate_report(
        run_id="run-1",
        mission_id="run-1",
        step_id="planner.report.1",
        claim="The invoice total is visible.",
        answer=None,
        page_context=sample_page(),
    )

    assert validation.validation_status == "uncertain"
    assert validation.failure_category == "missing_target"
    assert validation.sgv_verified is False
    assert validation.missing_evidence == ["specific_report_answer"]


def test_report_validation_missing_value_is_not_satisfied():
    validation, _ = ValidationEngine().validate_report(
        run_id="run-1",
        mission_id="run-1",
        step_id="planner.report.1",
        claim="The invoice total is visible.",
        answer="$99.00",
        page_context=sample_page(),
    )

    assert validation.validation_status == "not_satisfied"
    assert validation.failure_category == "missing_target"
    assert validation.missing_evidence == ["$99.00"]


def test_execution_validation_success_and_no_effect_classification():
    engine = ValidationEngine()

    success, _ = engine.validate_execution(
        run_id="run-1",
        mission_id="run-1",
        step_id="execution.1",
        action_type="click",
        selector="#continue",
        success=True,
        execution_result="success",
    )
    no_effect, _ = engine.validate_execution(
        run_id="run-1",
        mission_id="run-1",
        step_id="execution.2",
        action_type="click",
        selector="#continue",
        success=True,
        execution_result="No effect: DOM unchanged",
    )

    assert success.validation_status == "satisfied"
    assert no_effect.validation_status == "not_satisfied"
    assert no_effect.failure_category == "unexpected_state"


def test_navigation_validation_detects_contradiction_when_url_unchanged():
    validation, _ = ValidationEngine().validate_execution(
        run_id="run-1",
        mission_id="run-1",
        step_id="execution.1",
        action_type="navigate",
        selector="",
        success=True,
        execution_result="navigation completed",
        before_url="https://example.test/a",
        after_url="https://example.test/a",
    )

    assert validation.validation_status == "not_satisfied"
    assert validation.failure_category == "navigation_failed"
    assert validation.contradictions == ["expected_navigation_but_url_unchanged"]


def test_validation_evidence_is_bounded_and_replayable():
    validation, _ = ValidationEngine().validate_report(
        run_id="run-1",
        mission_id="run-1",
        step_id="planner.report.1",
        claim="The invoice total is visible.",
        answer="INR 14,632.00",
        page_context=sample_page(),
    )

    replayed, replay_ms = replay_validation(validation)

    assert len(validation.evidence) <= 30
    assert replayed.to_stable_json() == validation.to_stable_json()
    assert replay_ms < 100


def test_validation_feature_flag_default_and_off(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "v3_validation", "shadow")
    assert is_shadow_or_active("V3_VALIDATION") is True
    assert is_shadow_or_active("V3_VALIDATION_OBJECT") is True

    monkeypatch.setattr(settings, "v3_validation", "off")
    assert is_shadow_or_active("V3_VALIDATION") is False


def test_validation_telemetry_records_metrics():
    validation, latency_ms = ValidationEngine().validate_report(
        run_id="run-telemetry",
        mission_id="run-telemetry",
        step_id="planner.report.1",
        claim="The invoice total is visible.",
        answer="INR 14,632.00",
        page_context=sample_page(),
    )

    before = len(default_metric_sink.snapshot())
    record_validation_metrics("run-telemetry", validation, latency_ms=latency_ms)
    recorded = default_metric_sink.snapshot()[before:]

    assert {point.name for point in recorded} >= {
        "v3.validation.latency_ms",
        "v3.validation.confidence",
        "v3.validation.result",
    }
