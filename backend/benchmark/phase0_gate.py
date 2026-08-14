"""Audit the frozen Phase 0 suite and, optionally, its raw result reports."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from benchmark.m0_runner import load_suite, select_tasks
from benchmark.website_profiles import get_profile


MIN_TASKS = 25
MAX_TASKS = 50
SUITE_NAME = "phase0_baseline"


def build_manifest() -> dict[str, Any]:
    suite = load_suite(SUITE_NAME)
    declared = list(suite.get("task_ids") or [])
    tasks = select_tasks(suite, site=None, task=None)
    selected_ids = [task.task_id for task in tasks]
    errors: list[str] = []
    if not MIN_TASKS <= len(declared) <= MAX_TASKS:
        errors.append(f"task count {len(declared)} is outside [{MIN_TASKS}, {MAX_TASKS}]")
    if len(declared) != len(set(declared)):
        errors.append("suite contains duplicate task IDs")
    missing = sorted(set(declared) - set(selected_ids))
    if missing:
        errors.append("unknown task IDs: " + ", ".join(missing))
    if declared != selected_ids:
        errors.append("selected task order does not match the frozen suite order")
    for task in tasks:
        if not task.success_criteria:
            errors.append(f"{task.task_id} has no success criteria")
        if task.timeout_ms <= 0 or task.max_steps <= 0:
            errors.append(f"{task.task_id} has invalid execution bounds")
        if get_profile(task.site_id) is None:
            errors.append(f"{task.task_id} has no website profile for {task.site_id}")

    task_payload = [task.to_dict() for task in tasks]
    canonical = json.dumps(task_payload, sort_keys=True, separators=(",", ":"))
    return {
        "schema_version": "phase0.baseline-manifest.v1",
        "suite": SUITE_NAME,
        "task_count": len(tasks),
        "dataset_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "categories": sorted({task.category.value for task in tasks}),
        "sites": sorted({task.site_id for task in tasks}),
        "fixture_count": sum(1 for task in tasks if task.is_fixture),
        "auth_required_count": sum(1 for task in tasks if task.preconditions.auth_required),
        "errors": errors,
        "tasks": task_payload,
    }


def audit_report(path: Path, manifest: dict[str, Any], expected_executor: str) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"missing {expected_executor} report: {path}"]
    report = json.loads(path.read_text(encoding="utf-8"))
    meta = report.get("meta") or {}
    if meta.get("suite") != SUITE_NAME:
        errors.append(f"{path}: suite is {meta.get('suite')!r}, expected {SUITE_NAME!r}")
    executor = meta.get("executor_mode") or report.get("executor_mode")
    if executor != expected_executor:
        errors.append(f"{path}: executor is {executor!r}, expected {expected_executor!r}")
    results = report.get("task_results") or report.get("tasks") or report.get("results") or []
    result_ids = [str(item.get("task_id") or "") for item in results if isinstance(item, dict)]
    expected_ids = [item["task_id"] for item in manifest["tasks"]]
    missing = sorted(set(expected_ids) - set(result_ids))
    unexpected = sorted(set(result_ids) - set(expected_ids))
    if missing:
        errors.append(f"{path}: missing task results: {', '.join(missing)}")
    if unexpected:
        errors.append(f"{path}: unexpected task results: {', '.join(unexpected)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-output", type=Path)
    parser.add_argument("--playwright-report", type=Path)
    parser.add_argument("--synthetic-report", type=Path)
    args = parser.parse_args()
    manifest = build_manifest()
    errors = list(manifest["errors"])
    if args.playwright_report:
        errors.extend(audit_report(args.playwright_report, manifest, "playwright"))
    if args.synthetic_report:
        errors.extend(audit_report(args.synthetic_report, manifest, "synthetic"))
    if args.manifest_output:
        args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "suite": SUITE_NAME,
        "task_count": manifest["task_count"],
        "dataset_sha256": manifest["dataset_sha256"],
        "fixture_count": manifest["fixture_count"],
        "auth_required_count": manifest["auth_required_count"],
        "errors": errors,
    }, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
