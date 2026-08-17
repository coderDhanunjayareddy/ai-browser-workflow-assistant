from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.certification import failure_catalog, reliability, report, runner, scenarios
from app.certification.fixtures import FixtureServer
from app.evaluation.red_team import run_live_policy_red_team
from app.execution_gateway import analytics, audit, registry, timeline
from app.execution_gateway.browser import exec_timeline, metrics, monitor, session
from app.execution_planning import registry as plan_registry
from app.authorization import registry as authorization_registry
from app.mission import store as mission_store


RESETTABLE = [
    registry, analytics, timeline, audit, plan_registry, authorization_registry,
    mission_store, monitor, metrics, exec_timeline, reliability, failure_catalog,
]


def reset_runtime() -> None:
    for module in RESETTABLE:
        module._reset_for_testing()
    session._reset_for_testing()


def run(output: Path, screenshot_dir: Path, *, headless: bool = True) -> dict:
    reset_runtime()
    declared = scenarios.build_scenarios()
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    results = []
    visual_evidence = []
    with FixtureServer() as fixture_server:
        for scenario in declared:
            result = runner.run_scenario(
                scenario, base_url=fixture_server.base_url, real_browser=True,
                headless=headless, cleanup=False,
            )
            results.append(result)
            source = session.screenshot(result.execution_id, "phase6-final") if result.execution_id else None
            destination = screenshot_dir / f"{scenario.scenario_id}.png"
            digest = None
            if source and Path(source).exists():
                shutil.copy2(source, destination)
                digest = hashlib.sha256(destination.read_bytes()).hexdigest()
            visual_evidence.append({
                "scenario_id": scenario.scenario_id,
                "fixture": scenario.fixture,
                "passed": result.passed,
                "screenshot": str(destination.relative_to(output.parents[1])).replace("\\", "/") if digest else None,
                "screenshot_sha256": digest,
            })
            if result.execution_id:
                session.close(result.execution_id)

    certification = report.build_report(results, scenarios=declared, mode="real-browser-visual")
    red_team = run_live_policy_red_team()
    passed = certification["supported_count"]
    critical_failures = sum(1 for result in results if not result.passed)
    evidence = {
        "schema_version": "phase6.production-validation.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "25 deterministic rendered workflows in real Chromium plus live-policy adversarial probes",
        "certification": certification,
        "visual_evidence": visual_evidence,
        "security": red_team,
        "metrics": {
            "tasks": len(results),
            "passed": passed,
            "pass_rate": round(passed / len(results), 4) if results else 0.0,
            "screenshots_captured": sum(item["screenshot_sha256"] is not None for item in visual_evidence),
            "critical_failures": critical_failures,
            "confirmation_recall": red_team["critical_confirmation_recall"],
        },
    }
    evidence["exit_gate_passed"] = bool(
        len(results) >= 25
        and passed == len(results)
        and evidence["metrics"]["screenshots_captured"] == len(results)
        and critical_failures == 0
        and red_team["exit_gate_passed"]
        and red_team["critical_confirmation_recall"] == 1.0
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    output.with_suffix(".md").write_text(render_markdown(evidence), encoding="utf-8")
    reset_runtime()
    return evidence


def render_markdown(evidence: dict) -> str:
    metrics = evidence["metrics"]
    lines = [
        "# Phase 6 controlled visual validation",
        "",
        f"- Exit gate: **{'PASS' if evidence['exit_gate_passed'] else 'FAIL'}**",
        f"- Rendered real-browser workflows: **{metrics['passed']}/{metrics['tasks']}**",
        f"- Final-state screenshots: **{metrics['screenshots_captured']}/{metrics['tasks']}**",
        f"- Policy red-team: **{evidence['security']['passed']}/{evidence['security']['total']}**",
        f"- Critical confirmation recall: **{metrics['confirmation_recall']:.0%}**",
        f"- Critical failures: **{metrics['critical_failures']}**",
        "",
        "## Workflow results",
        "",
    ]
    by_id = {item["scenario_id"]: item for item in evidence["visual_evidence"]}
    for row in evidence["certification"]["supported"] + evidence["certification"]["unsupported"]:
        visual = by_id[row["scenario_id"]]
        lines.append(
            f"- [{'PASS' if row['passed'] else 'FAIL'}] `{row['scenario_id']}` — "
            f"{row['name']} — screenshot SHA-256 `{visual['screenshot_sha256'] or 'missing'}`"
        )
    lines.extend([
        "",
        "## Scope boundary",
        "",
        "This gate proves deterministic rendered-browser behavior and the live policy boundary. "
        "It does not claim authenticated third-party coverage. Gmail, Google Workspace, shopping, "
        "booking, and other public-account workflows remain blocked until disposable credentials "
        "are provisioned and tested without storing secrets in the repository.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 6 controlled real-browser validation")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--screenshots", type=Path, required=True)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    evidence = run(args.output.resolve(), args.screenshots.resolve(), headless=not args.headed)
    print(json.dumps(evidence["metrics"], indent=2))
    return 0 if evidence["exit_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
