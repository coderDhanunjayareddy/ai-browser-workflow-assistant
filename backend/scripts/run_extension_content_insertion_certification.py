from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import time
from dataclasses import asdict
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.certification.fixtures import FixtureServer  # noqa: E402


HARNESS_PATH = BACKEND / "scripts" / "run_live_sidepanel_validation.py"
HARNESS_SPEC = importlib.util.spec_from_file_location("live_sidepanel_harness", HARNESS_PATH)
assert HARNESS_SPEC is not None and HARNESS_SPEC.loader is not None
HARNESS = importlib.util.module_from_spec(HARNESS_SPEC)
sys.modules[HARNESS_SPEC.name] = HARNESS
HARNESS_SPEC.loader.exec_module(HARNESS)

DEFAULT_FILE = "synthetic-day5.txt"
DEFAULT_SUBJECT = "Synthetic cross-domain attachment preview"


def _read_fixture_state(page) -> dict[str, object]:
    return page.evaluate(
        """() => ({
            fixture_state: document.querySelector('#fixture-state')?.textContent || '',
            draft_count: Number(document.querySelector('#draft-count')?.textContent || 0),
            selection_count: Number(document.querySelector('#selection-count')?.textContent || 0),
            send_count: Number(document.querySelector('#send-count')?.textContent || 0),
            discard_count: Number(document.querySelector('#discard-count')?.textContent || 0),
            subject: document.querySelector('#draft-subject')?.value || '',
            preview_filename: document.querySelector('#attachment-preview')?.getAttribute('data-content-identity') || '',
        })"""
    )


def _assert_safe_exact_preview(state: dict[str, object], *, subject: str, filename: str) -> list[str]:
    failures: list[str] = []
    expected = {
        "fixture_state": "fixture_state=draft_preview_ready_exactly_once",
        "draft_count": 1,
        "selection_count": 1,
        "send_count": 0,
        "discard_count": 0,
        "subject": subject,
        "preview_filename": filename,
    }
    for key, value in expected.items():
        if state.get(key) != value:
            failures.append(f"{key}: expected {value!r}, observed {state.get(key)!r}")
    return failures


def _launch_context(playwright, profile: Path, extension_dir: Path):
    return playwright.chromium.launch_persistent_context(
        str(profile),
        headless=False,
        viewport={"width": 1440, "height": 950},
        args=[
            f"--disable-extensions-except={extension_dir}",
            f"--load-extension={extension_dir}",
            "--disable-quic",
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run a provider-neutral content-insertion workflow through the built extension, "
            "then restart Chromium and independently verify exactly-once persistence."
        )
    )
    parser.add_argument("--filename", default=DEFAULT_FILE)
    parser.add_argument("--subject", default=DEFAULT_SUBJECT)
    parser.add_argument("--timeout-s", type=int, default=180)
    parser.add_argument("--extension-dir", default=str(ROOT / "extension" / "dist"))
    parser.add_argument("--profile-dir", default="")
    args = parser.parse_args()

    extension_dir = Path(args.extension_dir).resolve()
    if not (extension_dir / "manifest.json").is_file():
        raise SystemExit(f"Built extension was not found at {extension_dir}")
    if not re.fullmatch(r"[^\\/\x00]+", args.filename) or args.filename in {".", ".."}:
        raise SystemExit("--filename must be one exact leaf filename")

    report_dir = ROOT / "docs" / "production_validation" / "generic_foundation" / "extension_e2e"
    report_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"draft-preview-{int(time.time() * 1000)}"
    # Browser profiles are large, disposable runtime state. Keep them in the
    # repository's ignored top-level profile area, never beside evidence files
    # where they could be mistaken for reviewable certification artifacts.
    profile = (
        Path(args.profile_dir).resolve()
        if args.profile_dir
        else ROOT / f"playwright-profile-extension-e2e-{run_id}"
    )
    trace_path = report_dir / f"{run_id}-trace.zip"
    before_restart_png = report_dir / f"{run_id}-before-restart.png"
    after_restart_png = report_dir / f"{run_id}-after-restart.png"
    report_path = report_dir / f"{run_id}.json"

    report: dict[str, object] = {
        "schema_version": "extension_content_insertion_e2e.v1",
        "run_id": run_id,
        "mode": "application_owned_extension_sidepanel",
        "harness_file_injection": False,
        "profile_dir": str(profile),
        "extension_dir": str(extension_dir),
        "filename": args.filename,
        "subject": args.subject,
        "status": "failed",
    }

    with FixtureServer() as server, sync_playwright() as playwright:
        fixture_url = f"{server.base_url}/draft-content-insertion?run={run_id}"
        quoted_subject = json.dumps(args.subject, ensure_ascii=False)
        quoted_filename = json.dumps(args.filename, ensure_ascii=False)
        prompt = (
            f"On the current synthetic draft workspace, activate the exact enabled Create draft control once. "
            f"Enter the exact subject {quoted_subject} in the exact Subject field. Attach the explicitly approved file "
            f"{quoted_filename} from Downloads and verify its visible attachment preview. "
            "Do not send, submit, discard, or change any external data."
        )
        report["fixture_url"] = fixture_url
        report["prompt"] = prompt

        context = _launch_context(playwright, profile, extension_dir)
        context.set_default_timeout(15_000)
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        extension_id = HARNESS._extension_id(context)
        target = context.new_page()
        target.goto(fixture_url, wait_until="domcontentloaded", timeout=30_000)
        sidepanel = context.new_page()
        sidepanel.goto(f"chrome-extension://{extension_id}/src/sidepanel/index.html")
        HARNESS._open_workflow_panel(sidepanel)

        result = HARNESS._run_task(
            context,
            sidepanel,
            target,
            run_id,
            prompt,
            args.timeout_s,
            "",
            False,
            True,
            fixture_url,
            False,
            True,
        )
        target.screenshot(path=str(before_restart_png), full_page=True)
        before_restart = _read_fixture_state(target)
        failures = _assert_safe_exact_preview(before_restart, subject=args.subject, filename=args.filename)
        if result.status != "completed":
            failures.append(f"extension workflow status: expected 'completed', observed {result.status!r}")
        context.tracing.stop(path=str(trace_path))
        context.close()

        # Reopen the same isolated profile and fixture identity. The fixture and
        # extension durable ledgers must retain the completed state without
        # replaying any browser mutation.
        restarted = _launch_context(playwright, profile, extension_dir)
        restarted.set_default_timeout(15_000)
        restarted_target = restarted.new_page()
        restarted_target.goto(fixture_url, wait_until="domcontentloaded", timeout=30_000)
        after_restart = _read_fixture_state(restarted_target)
        restart_failures = _assert_safe_exact_preview(after_restart, subject=args.subject, filename=args.filename)
        restarted_target.screenshot(path=str(after_restart_png), full_page=True)
        restarted.close()

    report.update(
        {
            "extension_id": extension_id,
            "workflow_result": asdict(result),
            "before_restart": before_restart,
            "after_restart": after_restart,
            "failures": failures + restart_failures,
            "trace": str(trace_path),
            "before_restart_screenshot": str(before_restart_png),
            "after_restart_screenshot": str(after_restart_png),
            "status": "passed" if not failures and not restart_failures else "failed",
        }
    )
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    latest_path = report_dir / "latest.json"
    latest_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(report_path), "failures": report["failures"]}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
