from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.contracts.serialization import SerializationValidator
from app.contracts.validator import ContractValidator
from app.intent_dispatcher.models import IntentDispatchDirective, IntentExecutionEvidence
from app.knowledge_extraction.models import KnowledgeArtifact, PageReadArtifact, ReportArtifact
from app.mission_result.models import MissionResult, MissionResultArtifact
from app.schema_validation import SchemaValidator
from app.schemas.intent import IntentEvidence
from app.schemas.request import PageContext


def main() -> int:
    schema_report = SchemaValidator().compare()
    contract_statuses = ContractValidator().validate()
    contract_failures = [item for item in contract_statuses if not item.compatible]
    serialization_failures = _serialization_failure_count()
    migration_status = (
        "UP_TO_DATE"
        if schema_report.alembic_head and schema_report.alembic_current == schema_report.alembic_head
        else "OUT_OF_DATE"
    )

    print("Infrastructure Validation")
    print(f"schema_compatible={schema_report.compatible}")
    print(f"schema_errors={schema_report.error_count}")
    print(f"schema_warnings={schema_report.warning_count}")
    print(f"alembic_current={schema_report.alembic_current}")
    print(f"alembic_head={schema_report.alembic_head}")
    print(f"migration_status={migration_status}")
    print(f"contract_count={len(contract_statuses)}")
    print(f"contract_failures={len(contract_failures)}")
    print(f"serialization_failures={serialization_failures}")

    if not schema_report.compatible or contract_failures or serialization_failures:
        return 1
    return 0


def _serialization_failure_count() -> int:
    validator = SerializationValidator()
    now = datetime.utcnow()
    samples = [
        PageContext(
            url="https://example.test",
            title="Example",
            metadata={},
            interactive_elements=[],
            content_blocks=[],
            headings=[],
            selected_text="",
            visible_text="Hello",
            images=[],
        ),
        IntentEvidence(success=True, payload={"page_context": {"url": "https://example.test"}}),
        IntentDispatchDirective(
            intent="navigate",
            owner="browser_control",
            capability="Browser",
            dispatch_target="browser_control",
            reason="Open page",
        ),
        IntentExecutionEvidence(evidence_id="ev", source="provider", kind="test", summary="ok"),
        PageReadArtifact(
            id="read_1",
            title="Example",
            canonical_url="https://example.test",
            headings=[],
            sections=[],
            paragraphs=["hello"],
            metadata={},
            tables=[],
            lists=[],
            forms=[],
            pricing_blocks=[],
            contact_blocks=[],
            navigation_context=[],
            timestamp_ms=1,
        ),
        KnowledgeArtifact(
            id="knowledge_1",
            artifact_type="comparison_table",
            records=[],
            content={"columns": ["Tool"], "rows": []},
            validation={},
            timestamp_ms=1,
        ),
        ReportArtifact(
            id="report_1",
            format="markdown",
            content="| Tool |",
            structured={"columns": ["Tool"], "rows": []},
            source_knowledge_id="knowledge_1",
            completion_status="complete",
            timestamp_ms=1,
        ),
        MissionResult(
            mission_result_id="mission_result_1",
            mission_id="mission_1",
            outcome="COMPLETE",
            final_answer="| Tool |",
            report_format="markdown",
            completion_reason="done",
            confidence=1.0,
            artifacts=[
                MissionResultArtifact(
                    artifact_id="report_1",
                    mission_result_id="mission_result_1",
                    mission_id="mission_1",
                    kind="markdown_report",
                    title="Report",
                    content_type="text/markdown",
                    content="| Tool |",
                    structured={"columns": ["Tool"], "rows": []},
                    metadata={},
                    created_at=now,
                )
            ],
            created_at=now,
            updated_at=now,
        ),
    ]
    return sum(1 for sample in samples if not validator.round_trip(sample)["compatible"])


if __name__ == "__main__":
    sys.exit(main())
