from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
SINGLE_RUNNER = BACKEND / "scripts" / "run_extension_content_insertion_certification.py"
REPORT_DIR = ROOT / "docs" / "production_validation" / "generic_foundation" / "extension_e2e"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run consecutive application-owned extension content-insertion certifications."
    )
    parser.add_argument("--repeat", type=int, default=20)
    parser.add_argument("--timeout-s", type=int, default=240)
    parser.add_argument("--filename", default="synthetic-day5.txt")
    parser.add_argument("--confirm-synthetic-submit", action="store_true")
    args = parser.parse_args()
    if args.repeat < 1 or args.repeat > 100:
        parser.error("--repeat must be between 1 and 100")

    started = time.time()
    sequence_id = f"content-insertion-reliability-{int(started * 1000)}"
    results: list[dict[str, object]] = []
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    for index in range(1, args.repeat + 1):
        print(f"[reliability] starting {index}/{args.repeat}", flush=True)
        command = [
            sys.executable,
            str(SINGLE_RUNNER),
            "--timeout-s",
            str(args.timeout_s),
            "--filename",
            args.filename,
            "--subject",
            f"Synthetic cross-domain attachment preview {sequence_id} run {index:02d}",
        ]
        if args.confirm_synthetic_submit:
            command.append("--confirm-synthetic-submit")
        completed = subprocess.run(
            command,
            cwd=str(BACKEND),
            text=True,
            capture_output=True,
            timeout=args.timeout_s + 90,
            check=False,
        )
        parsed: dict[str, object] = {}
        try:
            parsed = json.loads(completed.stdout)
        except json.JSONDecodeError:
            parsed = {
                "status": "failed",
                "failures": ["single-runner output was not valid JSON"],
            }
        report_path = Path(str(parsed.get("report") or ""))
        detail: dict[str, object] = {}
        if report_path.is_file():
            detail = json.loads(report_path.read_text(encoding="utf-8"))
        workflow = dict(detail.get("workflow_result") or {})
        before = dict(detail.get("before_restart") or {})
        after = dict(detail.get("after_restart") or {})
        durable = list(workflow.get("durable_executions") or [])
        record = {
            "index": index,
            "status": detail.get("status") or parsed.get("status") or "failed",
            "return_code": completed.returncode,
            "report": str(report_path) if report_path else "",
            "duration_s": workflow.get("duration_s"),
            "harness_file_injection": detail.get("harness_file_injection"),
            "before_restart": before,
            "after_restart": after,
            "durable_action_count": len(durable),
            "durable_attempts": [item.get("attempts") for item in durable if isinstance(item, dict)],
            "failures": detail.get("failures") or parsed.get("failures") or [],
            "stderr": completed.stderr[-2000:],
        }
        results.append(record)
        print(
            f"[reliability] run {index}/{args.repeat}: {record['status']} "
            f"({record['duration_s']}s)",
            flush=True,
        )
        if completed.returncode != 0 or record["status"] != "passed":
            break

    passed = sum(1 for item in results if item["status"] == "passed")
    durations = [float(item["duration_s"]) for item in results if isinstance(item.get("duration_s"), (int, float))]
    aggregate = {
        "schema_version": "extension_content_insertion_reliability.v1",
        "sequence_id": sequence_id,
        "requested_runs": args.repeat,
        "executed_runs": len(results),
        "passed_runs": passed,
        "failed_runs": len(results) - passed,
        "status": "passed" if passed == args.repeat else "failed",
        "stopped_on_first_failure": True,
        "harness_file_injection": False,
        "synthetic_submit_confirmed": args.confirm_synthetic_submit,
        "total_duration_s": round(time.time() - started, 1),
        "min_workflow_duration_s": min(durations) if durations else None,
        "max_workflow_duration_s": max(durations) if durations else None,
        "average_workflow_duration_s": round(sum(durations) / len(durations), 2) if durations else None,
        "results": results,
    }
    output = REPORT_DIR / f"{sequence_id}.json"
    serialized = json.dumps(aggregate, indent=2)
    output.write_text(serialized, encoding="utf-8")
    (REPORT_DIR / "reliability-latest.json").write_text(serialized, encoding="utf-8")
    print(json.dumps({
        "status": aggregate["status"],
        "passed_runs": passed,
        "requested_runs": args.repeat,
        "report": str(output),
    }, indent=2), flush=True)
    return 0 if aggregate["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
