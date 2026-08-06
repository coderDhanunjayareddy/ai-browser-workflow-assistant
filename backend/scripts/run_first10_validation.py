from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.mission.intelligence.blueprint_builder import MissionBlueprintBuilder

try:
    from validate_first10_readiness import CAPABILITIES, TASKS, audit, task_status
except ModuleNotFoundError:
    from scripts.validate_first10_readiness import CAPABILITIES, TASKS, audit, task_status


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "docs" / "production_validation"
BROWSER_ACTION_CONTRACT = {
    "click",
    "fill",
    "scroll",
    "navigate",
    "navigate_next_page",
    "wait",
    "select_option",
    "choose_date",
    "hover",
    "keyboard_shortcut",
    "open_new_tab",
    "switch_tab",
    "close_tab",
    "focus_existing_tab",
    "submit_search",
}

RunStatus = Literal["passed", "failed", "environment_gated"]


PROMPTS: dict[str, str] = {
    "VT-01": """Open Google Search and search for: `best AI browser automation tools 2026`.
From the first page of results:
1. Open the top 5 relevant results in new tabs.
2. Read each page enough to identify the product name, main purpose, pricing mention, and one key limitation.
3. Create a clean comparison table with columns: Tool, Purpose, Pricing, Limitation, URL.
4. Return the table only.""",
    "VT-02": """Open Google Search and search for: `Hyderabad software companies careers`.
Choose 3 company websites from the results that look relevant.
For each company:
1. Open the careers page.
2. Find any current software developer or full stack developer openings.
3. Extract the job title, location, experience needed, and application link.
4. Return the result in a table.""",
    "VT-03": """Go to LinkedIn Jobs and search for: `Full Stack Java Developer Hyderabad`.
Apply these filters if available:
- Experience level: Entry level or Associate
- Date posted: Past week
- On-site/Hybrid/Remote: any
Then:
1. Collect the first 10 relevant jobs.
2. For each job, capture title, company, location, posted date, and job link.
3. Remove duplicates.
4. Return the jobs ranked by relevance.""",
    "VT-04": """Open the official websites of 3 AI code assistant products from search results.
For each product:
1. Find the pricing page.
2. Capture the free plan, paid plan starting price, and whether a trial is available.
3. Capture one feature that is clearly mentioned on the pricing or product page.
4. Return a comparison table with source URLs.""",
    "VT-05": """Search the web for official documentation or product pages about browser automation tools.
Pick 3 different tools and for each one:
1. Find the official documentation page.
2. Extract the supported languages, main use case, and whether it supports browser control.
3. Note one setup requirement.
4. Return the answer in markdown bullets, grouped by tool.""",
    "VT-06": """Open a real public business directory or professional directory search result.
Collect 20 entries across at least 3 pages.
For each entry:
1. Capture name, category, city, and website if available.
2. Avoid duplicates.
3. Put the results into a table.
4. If any entry is missing a website, leave it blank rather than guessing.""",
    "VT-07": """Open a real SaaS website that offers a free account or free trial.
Complete the full signup flow using only a test email you control.
After signup:
1. Verify the welcome page or dashboard loads.
2. Locate one setting, one profile field, and one billing or plan page.
3. Capture screenshots of the successful login state and the profile page.
4. Return a short report with what worked and what failed.""",
    "VT-08": """Open a real website that allows file upload for logged-in users or public upload.
Upload a small PDF or image file.
Then:
1. Confirm the file was accepted.
2. Find where the uploaded file appears.
3. If the site provides a share link or processing result, copy it.
4. Return the result with the exact page path and any visible status text.""",
    "VT-09": """Open a real government, university, or company form that is publicly accessible and safe to use with test data.
Fill the form with clearly fake test data, but make it look realistic.
Then:
1. Check whether the form shows validation errors.
2. Fix any errors the page reports.
3. Submit only if it is a genuine test or sandbox form.
4. Report the validation rules you encountered and whether submission succeeded.""",
    "VT-10": """Use Google Search and official websites to research:
`AI browser automation testing best practices`
Do this in order:
1. Open at least 5 authoritative sources.
2. Extract the top recommended testing practices.
3. Separate practices into: reliability, observability, recovery, and safety.
4. Create a final checklist with 1 line per practice.
5. Cite the source URL next to each line.""",
}


EXPECTED_ACTIONS: dict[str, set[str]] = {
    "VT-01": {"navigate", "open_new_tab", "extract_fields", "validate_records", "generate_report"},
    "VT-02": {"navigate", "open_new_tab", "extract_fields", "validate_records", "generate_report"},
    "VT-03": {"navigate", "extract_fields", "validate_records", "generate_report"},
    "VT-04": {"navigate", "open_new_tab", "extract_fields", "validate_records", "generate_report"},
    "VT-05": {"navigate", "open_new_tab", "extract_fields", "validate_records", "generate_report"},
    "VT-06": {"navigate", "collect_page_items", "navigate_next_page", "extract_fields", "validate_records", "generate_report"},
    "VT-07": {"navigate", "fill", "validate_records"},
    "VT-08": {"navigate", "access_file", "click", "validate_records", "generate_report"},
    "VT-09": {"navigate", "fill", "validate_records"},
    "VT-10": {"navigate", "open_new_tab", "extract_fields", "validate_records", "generate_report"},
}


@dataclass(frozen=True)
class TaskValidationResult:
    task_id: str
    title: str
    status: RunStatus
    readiness_status: str
    mission_type: str
    deliverable: str
    node_count: int
    executable_actions: list[str]
    unsupported_browser_actions: list[str]
    missing_expected_actions: list[str]
    blocking_or_partial_capabilities: list[str]
    external_risks: list[str]
    root_cause: str
    next_generic_fix: str


def _task_by_id(task_id: str):
    return next(task for task in TASKS if task.task_id == task_id)


def _node_actions(nodes: list[Any]) -> list[str]:
    actions: list[str] = []
    for node in nodes:
        metadata = getattr(node, "metadata", {}) or {}
        payload = metadata.get("action_payload") or {}
        action = payload.get("action_type") or getattr(node, "expansion_template", {}).get("action")
        if action:
            actions.append(str(action))
    return actions


def _unsupported_browser_actions(actions: list[str]) -> list[str]:
    browser_owned = {
        "click",
        "fill",
        "scroll",
        "navigate",
        "navigate_next_page",
        "wait",
        "select_option",
        "choose_date",
        "hover",
        "keyboard_shortcut",
        "open_new_tab",
        "switch_tab",
        "close_tab",
        "focus_existing_tab",
        "submit_search",
    }
    return sorted(action for action in actions if action in browser_owned and action not in BROWSER_ACTION_CONTRACT)


def _root_cause(blocking: list[str], unsupported: list[str], missing_actions: list[str]) -> str:
    if unsupported:
        return f"Blueprint emits unsupported browser actions: {', '.join(unsupported)}."
    if blocking:
        first = blocking[0]
        capability = CAPABILITIES[first]
        return f"{first}: {capability.reason}"
    if missing_actions:
        return f"Blueprint/runtime contract is missing expected actions: {', '.join(missing_actions)}."
    return "All current contract checks passed."


def _generic_fix(blocking: list[str], unsupported: list[str], missing_actions: list[str]) -> str:
    if unsupported:
        return "Register the action end-to-end or remap the blueprint node to an existing generic browser primitive."
    if blocking:
        return CAPABILITIES[blocking[0]].generic_fix
    if missing_actions:
        return "Update mission classification and blueprint templates so this task type expands into the required generic workflow."
    return ""


def validate_task(task_id: str, prompt: str) -> TaskValidationResult:
    task = _task_by_id(task_id)
    blueprint_result = MissionBlueprintBuilder().build(mission_id=f"first10-{task_id.lower()}", user_goal=prompt)
    actions = _node_actions(blueprint_result.blueprint.nodes)
    unsupported = _unsupported_browser_actions(actions)
    missing_actions = sorted(EXPECTED_ACTIONS[task_id].difference(actions))
    readiness = task_status(task)
    blocking = [
        capability_id
        for capability_id in task.required_capabilities
        if CAPABILITIES[capability_id].status in {"missing", "partial", "environment"}
    ]
    if readiness == "environment":
        status: RunStatus = "environment_gated"
    elif unsupported or missing_actions or blocking:
        status = "failed"
    else:
        status = "passed"
    return TaskValidationResult(
        task_id=task.task_id,
        title=task.title,
        status=status,
        readiness_status=readiness,
        mission_type=blueprint_result.mission_type.value,
        deliverable=blueprint_result.understanding.deliverable,
        node_count=len(blueprint_result.blueprint.nodes),
        executable_actions=actions,
        unsupported_browser_actions=unsupported,
        missing_expected_actions=missing_actions,
        blocking_or_partial_capabilities=blocking,
        external_risks=task.external_risks,
        root_cause=_root_cause(blocking, unsupported, missing_actions),
        next_generic_fix=_generic_fix(blocking, unsupported, missing_actions),
    )


def run_suite() -> dict[str, Any]:
    results = [validate_task(task_id, prompt) for task_id, prompt in PROMPTS.items()]
    summary = {
        "task_count": len(results),
        "passed": sum(1 for result in results if result.status == "passed"),
        "failed": sum(1 for result in results if result.status == "failed"),
        "environment_gated": sum(1 for result in results if result.status == "environment_gated"),
        "milestone_achieved": all(result.status in {"passed", "environment_gated"} for result in results),
    }
    return {
        "suite": "first_10_validation_contract_run",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "readiness_summary": audit()["summary"],
        "results": [asdict(result) for result in results],
    }


def _write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# First 10 Validation Run",
        "",
        f"Generated: `{payload['generated_at']}`",
        "",
        "## Summary",
        "",
        f"- Passed: `{payload['summary']['passed']}`",
        f"- Failed: `{payload['summary']['failed']}`",
        f"- Environment gated: `{payload['summary']['environment_gated']}`",
        f"- Milestone achieved: `{payload['summary']['milestone_achieved']}`",
        "",
        "## Task Results",
        "",
        "| Task | Status | Mission Type | Blocking Root Cause | Next Generic Fix |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in payload["results"]:
        lines.append(
            "| {task_id} | {status} | {mission_type} | {root_cause} | {next_generic_fix} |".format(
                task_id=result["task_id"],
                status=result["status"],
                mission_type=result["mission_type"],
                root_cause=result["root_cause"].replace("|", "\\|"),
                next_generic_fix=(result["next_generic_fix"] or "").replace("|", "\\|"),
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    payload = run_suite()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    json_path = REPORT_DIR / f"first10_validation_run_{date}.json"
    md_path = REPORT_DIR / f"first10_validation_run_{date}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_markdown(payload, md_path)
    print(json.dumps({"summary": payload["summary"], "json": str(json_path), "markdown": str(md_path)}, indent=2))


if __name__ == "__main__":
    main()
