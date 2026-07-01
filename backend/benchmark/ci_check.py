"""
M0 — CI regression gate.

Compares a fresh report against a baseline and exits non-zero if the completion rate
regressed beyond the allowed threshold, if any fixture task failed, or if any
INFRASTRUCTURE error occurred. Used by the smoke (PR) and nightly CI jobs.

Usage:
  python -m benchmark.ci_check --report benchmark/reports/m0.json \\
      --baseline benchmark/baselines/nightly.json --regression-threshold 0.10
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional


def _load(path: Optional[str]) -> Optional[dict]:
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def _is_example(data: dict) -> bool:
    """Synthetic example reports are tagged; they must never act as a report or baseline."""
    return bool(data.get("_EXAMPLE")) or bool(data.get("meta", {}).get("example"))


def check(report: dict, baseline: Optional[dict], *, regression_threshold: float,
          require_fixtures_pass: bool = True) -> tuple[bool, list[str]]:
    problems: list[str] = []
    s = report["summary"]

    # 1. fixture tasks must complete (broken loop, not site flakiness)
    if require_fixtures_pass:
        for r in report["task_results"]:
            if r["task_id"].startswith("fixture__") and r["status"] != "COMPLETED":
                problems.append(f"fixture task failed: {r['task_id']} -> {r['status']} "
                                f"({r['failure_layer']})")

    # 2. no infrastructure errors
    infra = sum(1 for r in report["task_results"] if r["failure_layer"] == "INFRASTRUCTURE")
    if infra:
        problems.append(f"{infra} INFRASTRUCTURE error(s) — investigate harness/network")

    # 3. completion regression vs baseline
    if baseline is not None:
        base_rate = baseline.get("summary", {}).get("completion_rate", 0.0)
        cur_rate = s.get("completion_rate", 0.0)
        if base_rate - cur_rate > regression_threshold:
            problems.append(f"completion regressed {base_rate:.1%} -> {cur_rate:.1%} "
                            f"(> {regression_threshold:.0%} threshold)")

    return (len(problems) == 0, problems)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="M0 CI regression gate")
    p.add_argument("--report", required=True)
    p.add_argument("--baseline", default=None)
    p.add_argument("--regression-threshold", type=float, default=0.10)
    p.add_argument("--no-require-fixtures", dest="require_fixtures", action="store_false")
    args = p.parse_args(argv)

    report = _load(args.report)
    if report is None:
        print(f"[ci_check] report not found: {args.report}", flush=True)
        return 2
    if _is_example(report):
        print(f"[ci_check] {args.report} is a synthetic EXAMPLE report, not a real run — refusing.",
              flush=True)
        return 2
    baseline = _load(args.baseline)
    if baseline is not None and _is_example(baseline):
        print(f"[ci_check] {args.baseline} is a synthetic EXAMPLE report, not a valid baseline — "
              "refusing. The only valid baseline is produced by m0_runner in benchmark/baselines/.",
              flush=True)
        return 2

    ok, problems = check(report, baseline, regression_threshold=args.regression_threshold,
                         require_fixtures_pass=args.require_fixtures)
    if ok:
        print(f"[ci_check] PASS completion={report['summary']['completion_rate']:.1%}", flush=True)
        return 0
    print("[ci_check] FAIL", flush=True)
    for prob in problems:
        print(f"  - {prob}", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
