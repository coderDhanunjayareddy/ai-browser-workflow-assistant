"""
Phase F — Certification Report generator.

Aggregates CertificationResults + reliability + failure catalog into a structured report:
supported / unsupported scenarios, known limitations, observed failure patterns, and
reliability recommendations. Deterministic given the same inputs.
"""
from __future__ import annotations

from typing import Any, Optional

from app.certification.models import CertificationResult, OutcomeStatus
from app.certification import reliability, failure_catalog


def build_report(results: list[CertificationResult], *, scenarios: Optional[list] = None,
                 mode: str = "mock") -> dict[str, Any]:
    supported = [r for r in results if r.status == OutcomeStatus.passed]
    unsupported = [r for r in results if r.status in (OutcomeStatus.failed, OutcomeStatus.error)]
    skipped = [r for r in results if r.status == OutcomeStatus.skipped]

    # known limitations aggregated from scenario declarations
    limitations: list[dict] = []
    if scenarios:
        for s in scenarios:
            if s.known_limitations:
                limitations.append({"scenario_id": s.scenario_id, "limitations": s.known_limitations})

    rel = reliability.metrics()
    cat = failure_catalog.summary()

    recommendations = _recommendations(rel, cat, unsupported)

    return {
        "mode":               mode,
        "scenarios_total":    len(results),
        "supported_count":    len(supported),
        "unsupported_count":  len(unsupported),
        "skipped_count":      len(skipped),
        "pass_rate":          round(len(supported) / len(results), 4) if results else 0.0,
        "supported":          [r.to_dict() for r in supported],
        "unsupported":        [r.to_dict() for r in unsupported],
        "known_limitations":  limitations,
        "observed_failures":  cat,
        "reliability":        rel,
        "recommendations":    recommendations,
    }


def _recommendations(rel: dict, cat: dict, unsupported: list) -> list[str]:
    recs: list[str] = []
    wsr = rel.get("workflow_success_rate", 0.0)
    if wsr >= 1.0 and rel.get("workflows_total", 0) > 0:
        recs.append("All certified workflows pass; maintain regression coverage as new patterns are added.")
    elif wsr < 1.0:
        recs.append(f"Workflow success rate is {wsr:.0%}; triage the {len(unsupported)} unsupported scenario(s) "
                    "in the failure catalog before release.")
    step = rel.get("step_metrics", {})
    rec_rate = step.get("recovery_success_rate")
    if rec_rate is not None and step.get("recoveries_attempted", 0) > 0 and rec_rate < 1.0:
        recs.append(f"Deterministic recovery success is {rec_rate:.0%}; review the failure classes that did not recover.")
    val_rate = step.get("validation_success_rate")
    if val_rate is not None and step.get("validations_attempted", 0) > 0 and val_rate < 1.0:
        recs.append(f"Post-action validation success is {val_rate:.0%}; tighten validate_after criteria or selectors.")
    if cat.get("total_distinct", 0) == 0:
        recs.append("Failure catalog is empty; no reliability defects observed in this run.")
    else:
        recs.append(f"{cat['total_distinct']} distinct failure pattern(s) catalogued; track to resolution.")
    p95 = rel.get("duration_ms", {}).get("p95", 0.0)
    if p95:
        recs.append(f"Workflow p95 duration is {p95:.0f}ms; monitor for regressions against this baseline.")
    return recs


def render_markdown(report: dict) -> str:
    lines: list[str] = []
    lines.append(f"# Certification Report ({report['mode']} mode)\n")
    lines.append(f"- Scenarios: {report['scenarios_total']}  |  "
                 f"Supported: {report['supported_count']}  |  "
                 f"Unsupported: {report['unsupported_count']}  |  "
                 f"Pass rate: {report['pass_rate']:.0%}\n")
    rel = report["reliability"]
    lines.append("## Reliability")
    lines.append(f"- Workflow success rate: {rel['workflow_success_rate']:.0%} "
                 f"({rel['workflows_passed']}/{rel['workflows_total']})")
    d = rel["duration_ms"]
    lines.append(f"- Workflow duration: p50={d['p50']}ms p95={d['p95']}ms p99={d['p99']}ms\n")
    lines.append("## Supported scenarios")
    for r in report["supported"]:
        lines.append(f"- [PASS] {r['name']} ({r['category']})")
    if report["unsupported"]:
        lines.append("\n## Unsupported scenarios")
        for r in report["unsupported"]:
            lines.append(f"- [FAIL] {r['name']} — {r['failure_category']}: {r['failure_detail']}")
    if report["known_limitations"]:
        lines.append("\n## Known limitations")
        for lim in report["known_limitations"]:
            for text in lim["limitations"]:
                lines.append(f"- {lim['scenario_id']}: {text}")
    lines.append("\n## Recommendations")
    for rec in report["recommendations"]:
        lines.append(f"- {rec}")
    return "\n".join(lines)
