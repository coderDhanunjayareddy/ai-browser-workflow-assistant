from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal


ROOT = Path(__file__).resolve().parents[2]

Status = Literal["ready", "partial", "missing", "environment"]
Layer = Literal[
    "mission",
    "observation",
    "representation",
    "grounding",
    "execution",
    "extraction",
    "validation",
    "policy",
    "ui",
    "environment",
]


@dataclass(frozen=True)
class Capability:
    capability_id: str
    layer: Layer
    status: Status
    reason: str
    evidence_files: list[str] = field(default_factory=list)
    generic_fix: str = ""


@dataclass(frozen=True)
class ValidationTask:
    task_id: str
    title: str
    prompt: str
    required_capabilities: list[str]
    external_risks: list[str] = field(default_factory=list)


CAPABILITIES: dict[str, Capability] = {
    "research_mission_spec": Capability(
        "research_mission_spec",
        "mission",
        "ready",
        "Research/comparison prompts can be parsed into explicit required fields, source count, and output format.",
        ["backend/app/knowledge_extraction/research_spec.py"],
    ),
    "search_result_collection": Capability(
        "search_result_collection",
        "representation",
        "partial",
        "Browser intelligence collects semantic SearchResult candidates with domain/source/relevance metadata, but source coverage policy is not yet authoritative across every mission type.",
        ["backend/app/intent_providers/browser_intelligence_executor.py", "backend/app/browser_intelligence/page_understanding.py"],
        "Unify SearchResult ranking, opened-tab evidence, and mission completion source coverage into one reusable policy.",
    ),
    "multi_tab_open_read": Capability(
        "multi_tab_open_read",
        "execution",
        "partial",
        "Extension can open/switch tabs and track evidence, and backend completion now checks distinct source coverage, but opened-tab evidence is not yet unified with every mission blueprint node.",
        ["extension/src/background/tab_control.ts", "extension/src/workspace/multiTabWorkspace.ts", "extension/src/sidepanel/hooks/useWorkflow.ts"],
        "Unify opened-tab evidence with mission blueprint nodes and completion criteria for source coverage.",
    ),
    "schema_extraction": Capability(
        "schema_extraction",
        "extraction",
        "partial",
        "Extraction records are schema-aware and include field evidence plus typed entity metadata, but values are still heuristic and page-type extractors are not robust enough for production validation.",
        ["backend/app/knowledge_extraction/extraction_engine.py", "backend/app/knowledge_extraction/models.py"],
        "Harden typed extractors for pricing pages, documentation pages, job postings, directories, forms, and uploads.",
    ),
    "artifact_builder": Capability(
        "artifact_builder",
        "ui",
        "ready",
        "Reports are generated from KnowledgeArtifact rows, and table-only UI output is supported.",
        ["backend/app/knowledge_extraction/report_engine.py", "extension/src/sidepanel/App.tsx"],
    ),
    "source_count_completion": Capability(
        "source_count_completion",
        "validation",
        "ready",
        "Research mission completion now checks requested distinct source count before final mission result persistence.",
        ["backend/app/mission_completion/criteria.py", "backend/app/mission_completion/engine.py", "backend/app/mission_completion/models.py"],
    ),
    "directory_pagination": Capability(
        "directory_pagination",
        "execution",
        "partial",
        "CollectionPolicy detects item candidates, next-page targets, stop conditions, and item-key dedupe; backend now creates ledger-backed safe next-page navigation, but live multi-page browser validation and timeline stop-reason evidence remain pending.",
        ["backend/app/knowledge_extraction/collection_policy.py", "backend/app/mission/intelligence/blueprint_builder.py", "backend/app/orchestrator/workflow_orchestrator.py"],
        "Run live multi-page validation and add timeline evidence for per-page item count, next URL, and final stop reason.",
    ),
    "job_board_semantics": Capability(
        "job_board_semantics",
        "representation",
        "partial",
        "JobPosting entity metadata exists, but job-card/detail-page collection and robust field extraction are still heuristic.",
        ["backend/app/knowledge_extraction/extraction_engine.py"],
        "Harden JobPosting extraction with card/detail-page state, apply URL handling, salary/location parsing, and source evidence.",
    ),
    "linkedin_environment": Capability(
        "linkedin_environment",
        "environment",
        "environment",
        "LinkedIn often requires login and may rate-limit or block automation; this is an expected external blocker class.",
        [],
        "Run with known auth state, classify login/CAPTCHA as environment, and avoid account-changing actions without approval.",
    ),
    "pricing_page_semantics": Capability(
        "pricing_page_semantics",
        "representation",
        "partial",
        "PricingPlan entity metadata exists, but plan tables and free/paid tier structures are still heuristic.",
        ["backend/app/knowledge_extraction/page_reader.py", "backend/app/knowledge_extraction/extraction_engine.py"],
        "Harden PricingPlan extraction for plan tables, billing periods, free tiers, limits, and source sections.",
    ),
    "documentation_semantics": Capability(
        "documentation_semantics",
        "representation",
        "partial",
        "DocumentationPage entity metadata exists, but section-targeted extraction and official-source policy need hardening.",
        ["backend/app/knowledge_extraction/extraction_engine.py"],
        "Harden DocumentationPage extraction with section headings, install/API snippets, official-source scoring, and citation anchors.",
    ),
    "saas_signup_policy": Capability(
        "saas_signup_policy",
        "policy",
        "partial",
        "Risky/critical approvals exist, but signup/account-creation workflow policy is not a central deterministic gate.",
        ["extension/src/sidepanel/hooks/useWorkflow.ts", "backend/app/mission_completion/criteria.py"],
        "Centralize account-creation policy: allowed test email, stop conditions, no payment, no email verification bypass, approval gates.",
    ),
    "safe_form_filling": Capability(
        "safe_form_filling",
        "execution",
        "partial",
        "Generic fill/click exists, but form schema mapping and final-submit safety are not fully centralized.",
        ["extension/src/content/executor_v2.ts", "backend/app/mission_completion/criteria.py"],
        "Add FormWorkflowSpec with field mapping, fake-data broker, review-page target, and critical-submit blocking.",
    ),
    "file_upload_broker": Capability(
        "file_upload_broker",
        "execution",
        "partial",
        "File transfer support exists, but user file permission, selected-file evidence, and upload completion policy need a single broker.",
        ["extension/src/content/file_transfer.ts", "extension/src/background/file_transfer_metadata.ts"],
        "Build file broker: approved file handle, upload intent, filename evidence, widget acceptance evidence, and no-submit policy.",
    ),
    "batch_live_runner": Capability(
        "batch_live_runner",
        "environment",
        "missing",
        "There is no production extension batch runner for the first 10 validation tasks with per-task artifacts and taxonomy output.",
        ["docs/production_validation/validation-procedure.md"],
        "Add a controlled batch runner that starts each task, records timelines/artifacts, stops at criteria/budget, and emits failure taxonomy.",
    ),
}


TASKS: list[ValidationTask] = [
    ValidationTask(
        "VT-01",
        "Search and summarize AI browser automation tools",
        "Open Google Search and search for: best AI browser automation tools 2026. Open the top 5 relevant results and return a table only.",
        ["research_mission_spec", "search_result_collection", "multi_tab_open_read", "schema_extraction", "artifact_builder", "source_count_completion"],
    ),
    ValidationTask(
        "VT-02",
        "Extract software company career/job details",
        "Extract software company career/job details from a careers page.",
        ["job_board_semantics", "schema_extraction", "artifact_builder", "source_count_completion"],
    ),
    ValidationTask(
        "VT-03",
        "Discover LinkedIn jobs",
        "Discover LinkedIn jobs and report title, company, location, and URL.",
        ["job_board_semantics", "search_result_collection", "multi_tab_open_read", "linkedin_environment"],
        ["auth_wall", "captcha", "rate_limit"],
    ),
    ValidationTask(
        "VT-04",
        "Compare AI code assistant pricing",
        "Compare AI code assistant pricing across vendor pricing pages.",
        ["research_mission_spec", "search_result_collection", "multi_tab_open_read", "pricing_page_semantics", "schema_extraction", "artifact_builder", "source_count_completion"],
    ),
    ValidationTask(
        "VT-05",
        "Extract browser automation documentation details",
        "Extract browser automation documentation details from official docs.",
        ["research_mission_spec", "documentation_semantics", "schema_extraction", "artifact_builder", "source_count_completion"],
    ),
    ValidationTask(
        "VT-06",
        "Collect multi-page directory entries",
        "Collect entries from a multi-page directory.",
        ["directory_pagination", "schema_extraction", "artifact_builder", "source_count_completion"],
    ),
    ValidationTask(
        "VT-07",
        "Complete real SaaS signup workflow with test email",
        "Complete a real SaaS signup workflow with a test email, stopping before unsafe/critical actions.",
        ["saas_signup_policy", "safe_form_filling", "multi_tab_open_read"],
        ["email_verification", "account_creation_policy", "captcha"],
    ),
    ValidationTask(
        "VT-08",
        "Upload a real test file and report result",
        "Upload a real test file and report the upload result.",
        ["file_upload_broker", "safe_form_filling", "artifact_builder"],
        ["local_file_permission", "public_upload_target_safety"],
    ),
    ValidationTask(
        "VT-09",
        "Fill a safe public test/sandbox form with fake data",
        "Fill a safe public test/sandbox form with fake data and report result.",
        ["safe_form_filling", "saas_signup_policy", "artifact_builder"],
    ),
    ValidationTask(
        "VT-10",
        "Research AI browser automation testing best practices",
        "Research AI browser automation testing best practices and return a sourced summary.",
        ["research_mission_spec", "search_result_collection", "multi_tab_open_read", "documentation_semantics", "schema_extraction", "artifact_builder", "source_count_completion"],
    ),
]


def capability_present(capability: Capability) -> bool:
    return all((ROOT / file_name).exists() for file_name in capability.evidence_files)


def task_status(task: ValidationTask) -> Status:
    statuses = [CAPABILITIES[item].status for item in task.required_capabilities]
    if "missing" in statuses:
        return "missing"
    if "environment" in statuses:
        return "environment"
    if "partial" in statuses:
        return "partial"
    return "ready"


def audit() -> dict[str, object]:
    task_rows = []
    gap_counts: dict[str, int] = {}
    layer_counts: dict[str, int] = {}
    for task in TASKS:
        missing_or_partial = [
            capability_id
            for capability_id in task.required_capabilities
            if CAPABILITIES[capability_id].status in {"missing", "partial", "environment"}
        ]
        for capability_id in missing_or_partial:
            gap_counts[capability_id] = gap_counts.get(capability_id, 0) + 1
            layer = CAPABILITIES[capability_id].layer
            layer_counts[layer] = layer_counts.get(layer, 0) + 1
        task_rows.append(
            {
                **asdict(task),
                "status": task_status(task),
                "blocking_or_partial_capabilities": missing_or_partial,
            }
        )
    ranked_gaps = sorted(
        (
            {
                "capability_id": capability_id,
                "affected_task_count": count,
                **asdict(CAPABILITIES[capability_id]),
                "evidence_files_exist": capability_present(CAPABILITIES[capability_id]),
            }
            for capability_id, count in gap_counts.items()
        ),
        key=lambda item: (-int(item["affected_task_count"]), str(item["capability_id"])),
    )
    return {
        "suite": "first_10_validation_tasks",
        "summary": {
            "task_count": len(TASKS),
            "ready": sum(1 for task in TASKS if task_status(task) == "ready"),
            "partial": sum(1 for task in TASKS if task_status(task) == "partial"),
            "missing": sum(1 for task in TASKS if task_status(task) == "missing"),
            "environment": sum(1 for task in TASKS if task_status(task) == "environment"),
            "layer_gap_counts": layer_counts,
        },
        "tasks": task_rows,
        "ranked_gaps": ranked_gaps,
        "recommended_build_order": [
            "search_result_collection",
            "schema_extraction",
            "pricing_page_semantics",
            "documentation_semantics",
            "directory_pagination",
            "safe_form_filling",
            "file_upload_broker",
            "saas_signup_policy",
            "batch_live_runner",
        ],
    }


def main() -> None:
    print(json.dumps(audit(), indent=2))


if __name__ == "__main__":
    main()
