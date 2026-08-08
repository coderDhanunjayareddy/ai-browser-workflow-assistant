from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
EXTENSION_DIR = ROOT / "extension" / "dist"
REPORT_DIR = ROOT / "docs" / "production_validation" / "live_sidepanel"


TASKS = [
    (
        "VT-01",
        """Open Google Search and search for: `best AI browser automation tools 2026`.
From the first page of results:
1. Open the top 5 relevant results in new tabs.
2. Read each page enough to identify the product name, main purpose, pricing mention, and one key limitation.
3. Create a clean comparison table with columns: Tool, Purpose, Pricing, Limitation, URL.
4. Return the table only.""",
    ),
    (
        "VT-02",
        """Open Google Search and search for: `Hyderabad software companies careers`.
Choose 3 company websites from the results that look relevant.
For each company:
1. Open the careers page.
2. Find any current software developer or full stack developer openings.
3. Extract the job title, location, experience needed, and application link.
4. Return the result in a table.""",
    ),
    (
        "VT-03",
        """Go to LinkedIn Jobs and search for: `Full Stack Java Developer Hyderabad`.
Apply these filters if available:
- Experience level: Entry level or Associate
- Date posted: Past week
- On-site/Hybrid/Remote: any
Then:
1. Collect the first 10 relevant jobs.
2. For each job, capture title, company, location, posted date, and job link.
3. Remove duplicates.
4. Return the jobs ranked by relevance.""",
    ),
    (
        "VT-04",
        """Open the official websites of 3 AI code assistant products from search results.
For each product:
1. Find the pricing page.
2. Capture the free plan, paid plan starting price, and whether a trial is available.
3. Capture one feature that is clearly mentioned on the pricing or product page.
4. Return a comparison table with source URLs.""",
    ),
    (
        "VT-05",
        """Search the web for official documentation or product pages about browser automation tools.
Pick 3 different tools and for each one:
1. Find the official documentation page.
2. Extract the supported languages, main use case, and whether it supports browser control.
3. Note one setup requirement.
4. Return the answer in markdown bullets, grouped by tool.""",
    ),
    (
        "VT-06",
        """Open a real public business directory or professional directory search result.
Collect 20 entries across at least 3 pages.
For each entry:
1. Capture name, category, city, and website if available.
2. Avoid duplicates.
3. Put the results into a table.
4. If any entry is missing a website, leave it blank rather than guessing.""",
    ),
    (
        "VT-07",
        """Open a real SaaS website that offers a free account or free trial.
Complete the full signup flow using only a test email you control.
After signup:
1. Verify the welcome page or dashboard loads.
2. Locate one setting, one profile field, and one billing or plan page.
3. Capture screenshots of the successful login state and the profile page.
4. Return a short report with what worked and what failed.""",
    ),
    (
        "VT-08",
        """Open a real website that allows file upload for logged-in users or public upload.
Upload a small PDF or image file.
Then:
1. Confirm the file was accepted.
2. Find where the uploaded file appears.
3. If the site provides a share link or processing result, copy it.
4. Return the result with the exact page path and any visible status text.""",
    ),
    (
        "VT-09",
        """Open a real government, university, or company form that is publicly accessible and safe to use with test data.
Fill the form with clearly fake test data, but make it look realistic.
Then:
1. Check whether the form shows validation errors.
2. Fix any errors the page reports.
3. Submit only if it is a genuine test or sandbox form.
4. Report the validation rules you encountered and whether submission succeeded.""",
    ),
    (
        "VT-10",
        """Use Google Search and official websites to research:
`AI browser automation testing best practices`
Do this in order:
1. Open at least 5 authoritative sources.
2. Extract the top recommended testing practices.
3. Separate practices into: reliability, observability, recovery, and safety.
4. Create a final checklist with 1 line per practice.
5. Cite the source URL next to each line.""",
    ),
]


@dataclass
class TaskRun:
    task_id: str
    status: str
    duration_s: float
    phase: str
    error: str
    evidence: str
    screenshot: str


def _extension_id(context) -> str:
    worker = context.service_workers[0] if context.service_workers else context.wait_for_event("serviceworker")
    match = re.match(r"chrome-extension://([^/]+)/", worker.url)
    if not match:
        raise RuntimeError(f"Could not parse extension id from service worker URL: {worker.url}")
    return match.group(1)


def _click_if_visible(page, name: str, timeout_ms: int = 1500) -> bool:
    try:
        locator = page.get_by_text(name, exact=False).first
        locator.click(timeout=timeout_ms)
        return True
    except Exception:
        return False


def _sidepanel_text(page) -> str:
    try:
        return page.locator("body").inner_text(timeout=3000)
    except Exception as exc:
        return f"[body read failed: {exc}]"


def _ensure_auto_mode(sidepanel) -> None:
    text = _sidepanel_text(sidepanel)
    if "Auto mode: safe steps run automatically" in text:
        return
    try:
        clicked = sidepanel.evaluate(
            """() => {
                const titled = Array.from(document.querySelectorAll('[title]'))
                    .find((el) => (el.getAttribute('title') || '').toLowerCase().includes('auto mode'));
                const target = titled?.querySelector('div') || titled;
                if (target instanceof HTMLElement) {
                    target.click();
                    return true;
                }
                const labels = Array.from(document.querySelectorAll('label, span, div'))
                    .filter((el) => (el.textContent || '').trim().toLowerCase() === '🤖 auto'
                        || (el.textContent || '').trim().toLowerCase() === 'auto');
                const label = labels[labels.length - 1];
                if (label instanceof HTMLElement) {
                    label.click();
                    return true;
                }
                return false;
            }"""
        )
        if clicked:
            time.sleep(0.3)
            if "Auto mode: safe steps run automatically" in _sidepanel_text(sidepanel):
                return
    except Exception:
        pass
    for locator in (
        sidepanel.locator("[title*='Auto mode']").first,
        sidepanel.locator("label", has_text=re.compile(r"Auto", re.I)).first,
        sidepanel.get_by_text(re.compile(r"Auto$", re.I)).first,
        sidepanel.get_by_text("Auto", exact=False).first,
    ):
        try:
            locator.scroll_into_view_if_needed(timeout=1000)
            locator.click(timeout=1500)
            time.sleep(0.3)
            if "Auto mode: safe steps run automatically" in _sidepanel_text(sidepanel):
                return
        except Exception:
            continue


def _approve_pending_action(sidepanel, timeout_ms: int = 1500) -> bool:
    try:
        clicked = sidepanel.evaluate(
            """() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const button = buttons.find((el) => /approve/i.test(el.textContent || ''));
                if (button instanceof HTMLElement) {
                    button.scrollIntoView({ block: 'center', inline: 'center' });
                    button.click();
                    return true;
                }
                return false;
            }"""
        )
        if clicked:
            return True
    except Exception:
        pass
    for locator in (
        sidepanel.get_by_role("button", name=re.compile(r"Approve", re.I)).first,
        sidepanel.locator("button", has_text=re.compile(r"Approve", re.I)).first,
        sidepanel.get_by_text(re.compile(r"Approve", re.I)).first,
    ):
        try:
            if locator.is_visible(timeout=500):
                locator.scroll_into_view_if_needed(timeout=1000)
                locator.click(timeout=timeout_ms)
                return True
        except Exception:
            continue
    return False


def _open_workflow_panel(sidepanel) -> None:
    sidepanel.bring_to_front()
    workflow_tab = sidepanel.get_by_role("button", name=re.compile(r"^Workflow$", re.I))
    workflow_tab.click(timeout=10_000)
    try:
        sidepanel.locator("textarea[placeholder*='Describe what you want']").wait_for(
            state="visible",
            timeout=10_000,
        )
        return
    except PlaywrightTimeoutError:
        text = _sidepanel_text(sidepanel)
        raise RuntimeError(f"Workflow panel did not open. Visible side panel text: {text[:1000]}")


def _run_task(sidepanel, target, task_id: str, prompt: str, timeout_s: int) -> TaskRun:
    started = time.time()
    safe_id = task_id.lower()
    target.bring_to_front()
    try:
        target.goto("https://www.google.com/", wait_until="domcontentloaded", timeout=45_000)
    except Exception:
        pass
    sidepanel.bring_to_front()
    _open_workflow_panel(sidepanel)
    _click_if_visible(sidepanel, "Clear")
    textarea = sidepanel.locator("textarea[placeholder*='Describe what you want']").first
    textarea.fill(prompt, timeout=10_000)
    _ensure_auto_mode(sidepanel)
    sidepanel.get_by_role("button", name=re.compile("Analyze", re.I)).click(timeout=10_000)

    terminal_status = "timeout"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        text = _sidepanel_text(sidepanel)
        lowered = text.lower()
        _ensure_auto_mode(sidepanel)
        if "✕ stop workflow" in lowered or "stop workflow" in lowered:
            pass
        if "requires approval" in lowered or "✓ approve" in lowered or "approve" in lowered:
            if _approve_pending_action(sidepanel, timeout_ms=1200):
                time.sleep(0.7)
                continue
        false_completion = (
            "mission stopped without a verified report" in lowered
            or "no executable browser action was returned" in lowered
            or "mission ledger has no further browser intent assigned before completion evidence" in lowered
            or (
                "mission ledger has no further browser intent assigned" in lowered
                and "report answer:" not in lowered
                and "mission result is ready" not in lowered
            )
        )
        planner_replan = "planner requested replan" in lowered or "replan reason:" in lowered
        if planner_replan:
            terminal_status = "failed"
            break
        if false_completion or "failed" in lowered or "error:" in lowered or "observation failed" in lowered:
            terminal_status = "failed"
            break
        if "✓ done" in lowered or "done —" in lowered or "no actions needed" in lowered:
            terminal_status = "completed"
            break
        if "complete" in lowered and ("report answer:" in lowered or "mission result is ready" in lowered):
            terminal_status = "completed"
            break
        time.sleep(1)

    phase = "unknown"
    text = _sidepanel_text(sidepanel)
    for candidate in ["Reading page", "Thinking", "Executing", "Waiting for info", "completed", "failed"]:
        if candidate.lower() in text.lower():
            phase = candidate
    screenshot = REPORT_DIR / f"{safe_id}.png"
    sidepanel.screenshot(path=str(screenshot), full_page=True)
    return TaskRun(
        task_id=task_id,
        status=terminal_status,
        duration_s=round(time.time() - started, 1),
        phase=phase,
        error=_extract_error(text),
        evidence=text[-5000:],
        screenshot=str(screenshot),
    )


def _extract_error(text: str) -> str:
    for marker in ("Error:", "failed:", "Observation failed:", "Analysis failed:"):
        idx = text.lower().find(marker.lower())
        if idx >= 0:
            return text[idx : idx + 500]
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--timeout-s", type=int, default=420)
    args = parser.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    profile_dir = REPORT_DIR / f"profile_{int(time.time() * 1000)}"
    if not EXTENSION_DIR.exists():
        raise SystemExit(f"Extension build not found: {EXTENSION_DIR}")

    results: list[TaskRun] = []
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            str(profile_dir),
            headless=False,
            viewport={"width": 1440, "height": 950},
            args=[
                f"--disable-extensions-except={EXTENSION_DIR}",
                f"--load-extension={EXTENSION_DIR}",
            ],
        )
        context.set_default_timeout(15_000)
        extension_id = _extension_id(context)
        target = context.new_page()
        target.goto("https://www.google.com/", wait_until="domcontentloaded")
        sidepanel = context.new_page()
        sidepanel.goto(f"chrome-extension://{extension_id}/src/sidepanel/index.html")
        _open_workflow_panel(sidepanel)
        sidepanel.screenshot(path=str(REPORT_DIR / "sidepanel_loaded.png"), full_page=True)

        for task_id, prompt in TASKS[: args.limit]:
            print(f"[live-sidepanel] starting {task_id}", flush=True)
            result = _run_task(sidepanel, target, task_id, prompt, args.timeout_s)
            results.append(result)
            print(f"[live-sidepanel] {task_id} {result.status} {result.duration_s}s", flush=True)
            if result.status == "failed":
                break

        report = {
            "mode": "extension_sidepanel_playwright",
            "extension_id": extension_id,
            "started_profile": str(profile_dir),
            "results": [asdict(item) for item in results],
        }
        out = REPORT_DIR / "live_sidepanel_first10_latest.json"
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        context.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
