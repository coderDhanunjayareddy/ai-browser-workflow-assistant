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
        "ready",
        "Search result collection now normalizes observed SERP candidates, filters non-openable/ad/internal results, registers ranked source entities for deterministic OPEN phase work, and emits source collection policy metadata.",
        [
            "backend/app/intent_providers/browser_intelligence_executor.py",
            "backend/app/browser_intelligence/page_understanding.py",
            "backend/app/execution_orchestrator/completion_engine.py",
            "backend/tests/unit/test_browser_intelligence_executor.py",
            "backend/tests/unit/test_v48_execution_orchestrator.py",
        ],
    ),
    "multi_tab_open_read": Capability(
        "multi_tab_open_read",
        "execution",
        "ready",
        "Extension open/switch actions now send structured browser evidence through PriorStep, and backend artifact/runtime/tab-state builders consume that evidence for opened/read source coverage.",
        [
            "extension/src/background/tab_control.ts",
            "extension/src/workspace/multiTabWorkspace.ts",
            "extension/src/sidepanel/hooks/useWorkflow.ts",
            "backend/app/schemas/request.py",
            "backend/app/execution_orchestrator/artifact_registry.py",
            "backend/app/runtime_state_manager/artifacts.py",
            "backend/app/runtime_state_manager/registry.py",
            "backend/tests/unit/test_v49_runtime_state_manager.py",
            "backend/tests/unit/test_execution_orchestrator_artifact_registry.py",
            "extension/tests/useWorkflow.routing.test.cjs",
        ],
    ),
    "schema_extraction": Capability(
        "schema_extraction",
        "extraction",
        "ready",
        "Extraction records are schema-aware, include field evidence and typed entity metadata, and now use generic task-derived schema profiles for research, pricing, jobs, docs, directories, forms, uploads, and testing-practice checklists.",
        ["backend/app/knowledge_extraction/extraction_engine.py", "backend/app/knowledge_extraction/models.py", "backend/tests/unit/test_v50_knowledge_extraction.py"],
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
        "ready",
        "CollectionPolicy now honors requested item counts and minimum page counts, tracks visited pages, new/total item counts, next URL, and stop reason; the extension reports next-page navigation evidence through PriorStep browser evidence.",
        [
            "backend/app/knowledge_extraction/collection_policy.py",
            "backend/app/mission/intelligence/blueprint_builder.py",
            "backend/app/orchestrator/workflow_orchestrator.py",
            "backend/tests/unit/test_v50_knowledge_extraction.py",
            "extension/src/content/executor_v2.ts",
            "extension/src/sidepanel/hooks/useWorkflow.ts",
            "extension/tests/useWorkflow.routing.test.cjs",
        ],
    ),
    "job_board_semantics": Capability(
        "job_board_semantics",
        "representation",
        "ready",
        "Job pages now produce structured job posting candidates, field-level job evidence, apply URL handling, location/experience/posted-date parsing, and typed JobPosting entities with candidate metadata.",
        [
            "backend/app/knowledge_extraction/page_reader.py",
            "backend/app/knowledge_extraction/extraction_engine.py",
            "backend/app/knowledge_extraction/models.py",
            "backend/tests/unit/test_v50_knowledge_extraction.py",
        ],
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
        "ready",
        "Pricing pages now produce structured pricing plan candidates, extract free tier, paid starting price, trial availability, and feature evidence from plan-card/table-like text, and store plan summaries in PricingPlan entities.",
        [
            "backend/app/knowledge_extraction/page_reader.py",
            "backend/app/knowledge_extraction/extraction_engine.py",
            "backend/app/knowledge_extraction/models.py",
            "backend/tests/unit/test_v50_knowledge_extraction.py",
        ],
    ),
    "documentation_semantics": Capability(
        "documentation_semantics",
        "representation",
        "ready",
        "Documentation pages now produce section-aware documentation candidates, extract supported languages, setup requirements, browser-control evidence, and official-source score/citation metadata.",
        [
            "backend/app/knowledge_extraction/page_reader.py",
            "backend/app/knowledge_extraction/extraction_engine.py",
            "backend/app/knowledge_extraction/models.py",
            "backend/tests/unit/test_v50_knowledge_extraction.py",
        ],
    ),
    "saas_signup_policy": Capability(
        "saas_signup_policy",
        "policy",
        "ready",
        "Signup/account-creation workflows now use a central SignupWorkflowPolicy with test-email requirement, one-account-per-mission limit, payment/password/security-change blocks, email-verification/CAPTCHA stop conditions, and blueprint policy metadata.",
        [
            "backend/app/signup_policy/policy.py",
            "backend/app/form_workflow/spec.py",
            "backend/app/mission/intelligence/blueprint_builder.py",
            "backend/tests/unit/test_mission_blueprint_wave2.py",
        ],
    ),
    "safe_form_filling": Capability(
        "safe_form_filling",
        "execution",
        "ready",
        "Form workflows now have a generic FormWorkflowSpec, blueprint field-mapping/fill/validation nodes, sandbox-only submit policy metadata, and extension fill evidence for field validity, validation messages, form validity, invalid count, filled count, and submit control presence.",
        [
            "backend/app/form_workflow/spec.py",
            "backend/app/mission/intelligence/blueprint_builder.py",
            "extension/src/content/executor_v2.ts",
            "extension/src/sidepanel/hooks/useWorkflow.ts",
            "backend/tests/unit/test_mission_blueprint_wave2.py",
            "extension/tests/useWorkflow.routing.test.cjs",
        ],
    ),
    "file_upload_broker": Capability(
        "file_upload_broker",
        "execution",
        "ready",
        "File upload workflows now use a FileUploadBrokerPolicy with user-selected-file requirement, allowed file kinds, blocked follow-up actions, required upload evidence, upload-control blueprint nodes, and extension evidence for target selector, file count, filename, acceptance, and user-selection status.",
        [
            "backend/app/file_upload_broker/policy.py",
            "backend/app/mission/intelligence/blueprint_builder.py",
            "extension/src/content/file_transfer.ts",
            "extension/src/sidepanel/hooks/useWorkflow.ts",
            "extension/tests/fileTransfer.test.cjs",
            "extension/tests/useWorkflow.routing.test.cjs",
        ],
    ),
    "batch_live_runner": Capability(
        "batch_live_runner",
        "environment",
        "ready",
        "The first-10 validation runner emits per-task artifacts, blueprint/runtime contract checks, failure taxonomy, and milestone status.",
        ["backend/scripts/run_first10_validation.py", "docs/production_validation/first10_validation_run_2026-08-06.md"],
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
        ["safe_form_filling", "artifact_builder"],
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
            "linkedin_environment",
            "batch_live_runner",
        ],
    }


def main() -> None:
    print(json.dumps(audit(), indent=2))


if __name__ == "__main__":
    main()
