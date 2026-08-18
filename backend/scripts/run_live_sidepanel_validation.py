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


def _initial_target_url(prompt: str) -> str:
    text = (prompt or "").lower()
    if "whatsapp" in text or "watsapp" in text:
        return "https://web.whatsapp.com/"
    if "gmail" in text or "google mail" in text:
        return "https://mail.google.com/mail/u/0/#inbox"
    if "google drive" in text or re.search(r"\bdrive\b", text):
        return "https://drive.google.com/drive/u/0/home"
    if "google docs" in text or "google document" in text:
        return "https://docs.google.com/document/u/0/"
    if "linkedin" in text:
        return "https://www.linkedin.com/jobs/"
    if any(term in text for term in ("google", "search", "first page of results", "search results")):
        return "https://www.google.com/"
    return "about:blank"


@dataclass
class TaskRun:
    task_id: str
    status: str
    duration_s: float
    phase: str
    error: str
    evidence: str
    screenshot: str
    target_screenshot: str
    target_controls: list[dict[str, str]]


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


def _ensure_advanced_control(sidepanel) -> None:
    if "Advanced control enabled: DOM first, trusted CDP fallback" in _sidepanel_text(sidepanel):
        return
    toggle = sidepanel.locator('[title*="CDP control"]').locator("div").first
    toggle.scroll_into_view_if_needed(timeout=3000)
    toggle.click(timeout=3000)
    deadline = time.time() + 3
    while time.time() < deadline:
        text = _sidepanel_text(sidepanel)
        if "Advanced control enabled: DOM first, trusted CDP fallback" in text:
            return
        if "Advanced control unavailable" in text or "Advanced control is missing" in text:
            raise RuntimeError(f"Could not enable trusted browser control: {text[:1000]}")
        time.sleep(0.1)
    raise RuntimeError("Trusted browser control toggle did not become enabled.")


def _approve_pending_action(sidepanel, timeout_ms: int = 1500) -> bool:
    try:
        clicked = sidepanel.evaluate(
            """() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const button = buttons.find((el) => {
                    const text = (el.textContent || '').toLowerCase();
                    return (text.includes('approve') || text.includes('resume safely')) && !el.hasAttribute('disabled');
                });
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
        sidepanel.get_by_role("button", name=re.compile(r"Resume safely", re.I)).first,
        sidepanel.locator("button", has_text=re.compile(r"Approve", re.I)).first,
        sidepanel.locator("button", has_text=re.compile(r"Resume safely", re.I)).first,
        sidepanel.get_by_text(re.compile(r"Approve", re.I)).first,
        sidepanel.get_by_text(re.compile(r"Resume safely", re.I)).first,
    ):
        try:
            if locator.is_visible(timeout=500):
                locator.scroll_into_view_if_needed(timeout=1000)
                locator.click(timeout=timeout_ms)
                return True
        except Exception:
            continue
    return False


def _looks_like_critical_approval(text: str) -> bool:
    approval_visible = "requires approval" in text or "approve" in text
    send_like = "send" in text and any(term in text for term in ("message", "whatsapp", "email", "mail"))
    account_like = any(
        term in text
        for term in (
            "payment",
            "checkout",
            "delete",
            "password",
            "security",
            "login",
            "submit government",
            "official form",
        )
    )
    return approval_visible and (send_like or account_like)


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


def _run_task(
    sidepanel,
    target,
    task_id: str,
    prompt: str,
    timeout_s: int,
    file_path: str = "",
    allow_confirmed_critical: bool = False,
    enable_advanced_control: bool = False,
) -> TaskRun:
    started = time.time()
    safe_id = task_id.lower()
    target.bring_to_front()
    try:
        target.goto(_initial_target_url(prompt), wait_until="domcontentloaded", timeout=45_000)
    except Exception:
        pass
    sidepanel.bring_to_front()
    _open_workflow_panel(sidepanel)
    _click_if_visible(sidepanel, "Clear")
    approved_file = Path(file_path).resolve() if file_path else None
    file_chooser_events: list[str] = []

    def provide_approved_file(chooser) -> None:
        if approved_file is None or not approved_file.is_file():
            file_chooser_events.append("chooser_opened_without_valid_approved_file")
            return
        try:
            chooser.set_files(str(approved_file), timeout=15_000)
            file_chooser_events.append(f"selected:{approved_file.name}")
        except Exception as exc:
            file_chooser_events.append(f"selection_failed:{exc}")

    target.on("filechooser", provide_approved_file)
    textarea = sidepanel.locator("textarea[placeholder*='Describe what you want']").first
    textarea.fill(prompt, timeout=10_000)
    _ensure_auto_mode(sidepanel)
    if enable_advanced_control:
        _ensure_advanced_control(sidepanel)
    sidepanel.get_by_role("button", name=re.compile("Analyze", re.I)).click(timeout=10_000)

    terminal_status = "timeout"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        text = _sidepanel_text(sidepanel)
        lowered = text.lower()
        _ensure_auto_mode(sidepanel)
        if _looks_like_critical_approval(lowered):
            if allow_confirmed_critical and _approve_pending_action(sidepanel, timeout_ms=1200):
                time.sleep(0.7)
                continue
            terminal_status = "needs_approval"
            break
        if _approve_pending_action(sidepanel, timeout_ms=1200):
            time.sleep(0.7)
            continue
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
        explicit_failure = (
            "workflow failed" in lowered
            or "analysis failed:" in lowered
            or "observation failed:" in lowered
            or "execution_failed" in lowered
            or "execution failed" in lowered
            or "error:" in lowered
        )
        if false_completion or explicit_failure:
            terminal_status = "failed"
            break
        if "need information" in lowered or "waiting for info" in lowered:
            terminal_status = "needs_info"
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
    if file_chooser_events:
        text = f"{text}\n\nFILE CHOOSER EVIDENCE\n" + "\n".join(file_chooser_events)
    for candidate in ["Reading page", "Thinking", "Executing", "Waiting for info", "completed", "failed"]:
        if candidate.lower() in text.lower():
            phase = candidate
    screenshot = REPORT_DIR / f"{safe_id}.png"
    try:
        sidepanel.screenshot(path=str(screenshot), full_page=True, timeout=10_000)
    except Exception as exc:
        text = f"{text}\n\n[screenshot failed: {exc}]"
        screenshot = REPORT_DIR / f"{safe_id}.screenshot_failed.txt"
        screenshot.write_text(str(exc), encoding="utf-8")
    target_screenshot = REPORT_DIR / f"{safe_id}-target.png"
    try:
        target.screenshot(path=str(target_screenshot), full_page=True, timeout=10_000)
    except Exception as exc:
        target_screenshot = REPORT_DIR / f"{safe_id}-target.screenshot_failed.txt"
        target_screenshot.write_text(str(exc), encoding="utf-8")
    try:
        target_controls = target.locator(
            '[contenteditable], [role="textbox"], [role="searchbox"], input, textarea, button[aria-label]'
        ).evaluate_all(
            """elements => elements.slice(0, 80).map((element) => ({
                tag: element.tagName.toLowerCase(),
                role: element.getAttribute('role') || '',
                aria_label: element.getAttribute('aria-label') || '',
                placeholder: element.getAttribute('placeholder') || element.getAttribute('data-placeholder') || '',
                contenteditable: element.getAttribute('contenteditable') || '',
                testid: element.getAttribute('data-testid') || '',
            }))"""
        )
    except Exception:
        target_controls = []
    return TaskRun(
        task_id=task_id,
        status=terminal_status,
        duration_s=round(time.time() - started, 1),
        phase=phase,
        error=_extract_error(text),
        evidence=text[-5000:],
        screenshot=str(screenshot),
        target_screenshot=str(target_screenshot),
        target_controls=target_controls,
    )


def _extract_error(text: str) -> str:
    for marker in ("Error:", "failed:", "Observation failed:", "Analysis failed:"):
        idx = text.lower().find(marker.lower())
        if idx >= 0:
            return text[idx : idx + 500]
    return ""


def _write_report(extension_id: str, profile_dir: Path, results: list[TaskRun]) -> None:
    report = {
        "mode": "extension_sidepanel_playwright",
        "extension_id": extension_id,
        "started_profile": str(profile_dir),
        "results": [asdict(item) for item in results],
    }
    out = REPORT_DIR / "live_sidepanel_first10_latest.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--timeout-s", type=int, default=420)
    parser.add_argument("--task-id", type=str, default="")
    parser.add_argument("--prompt", type=str, default="")
    parser.add_argument("--profile-dir", type=str, default="")
    parser.add_argument(
        "--browser-channel",
        choices=("chromium", "chrome"),
        default="chromium",
        help="Browser binary used for the visible extension run. Chrome is a bounded fallback when Windows blocks bundled Chromium network access.",
    )
    parser.add_argument("--file-path", type=str, default="")
    parser.add_argument(
        "--inspect-chat-name",
        type=str,
        default="",
        help="Read-only recovery inspection: open an exact visible WhatsApp chat and capture evidence without running a workflow.",
    )
    parser.add_argument(
        "--allow-confirmed-critical",
        action="store_true",
        help="Consume visible side-panel approvals only after the operator has recorded explicit user confirmation.",
    )
    parser.add_argument(
        "--enable-advanced-control",
        action="store_true",
        help="Visually enable the side panel's trusted CDP fallback before running the selected task.",
    )
    parser.add_argument(
        "--pause-before-tasks",
        action="store_true",
        help="Keep the visible browser open for operator authentication, then wait for Enter before running tasks.",
    )
    args = parser.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    profile_dir = Path(args.profile_dir).resolve() if args.profile_dir else REPORT_DIR / f"profile_{int(time.time() * 1000)}"
    if not EXTENSION_DIR.exists():
        raise SystemExit(f"Extension build not found: {EXTENSION_DIR}")

    results: list[TaskRun] = []
    with sync_playwright() as pw:
        launch_options = {
            "headless": False,
            "viewport": {"width": 1440, "height": 950},
            "args": [
                f"--disable-extensions-except={EXTENSION_DIR}",
                f"--load-extension={EXTENSION_DIR}",
                # Chromium documents this test switch as disabling QUIC. The
                # live validation profile observed ERR_QUIC_PROTOCOL_ERROR on
                # WhatsApp, so force the normal HTTPS transport for repeatable
                # validation without changing application behavior.
                "--disable-quic",
            ],
        }
        if args.browser_channel == "chrome":
            launch_options["channel"] = "chrome"
        context = pw.chromium.launch_persistent_context(str(profile_dir), **launch_options)
        context.set_default_timeout(15_000)
        extension_id = _extension_id(context)
        selected_tasks = [(args.task_id or "CUSTOM", args.prompt)] if args.prompt else TASKS[: args.limit]
        target = context.new_page()
        first_prompt = "Open WhatsApp" if args.inspect_chat_name else (selected_tasks[0][1] if selected_tasks else "")
        initial_url = _initial_target_url(first_prompt)
        try:
            target.goto(initial_url, wait_until="domcontentloaded", timeout=45_000)
        except Exception as exc:
            task_id = args.task_id or "BOOTSTRAP"
            safe_task_id = re.sub(r"[^a-z0-9]+", "-", task_id.lower()).strip("-") or "bootstrap"
            target_screenshot = REPORT_DIR / f"{safe_task_id}-bootstrap-failed.png"
            try:
                target.screenshot(path=str(target_screenshot), full_page=True, timeout=15_000)
            except Exception:
                target_screenshot = Path("")
            results.append(
                TaskRun(
                    task_id=task_id,
                    status="failed",
                    duration_s=0.0,
                    phase="bootstrap_navigation",
                    error=f"Initial navigation to {initial_url} failed: {exc}",
                    evidence=(
                        "The target page could not be opened, so the side-panel workflow was not started. "
                        "No application action or external side effect was attempted."
                    ),
                    screenshot="",
                    target_screenshot=str(target_screenshot),
                    target_controls=[],
                )
            )
            _write_report(extension_id, profile_dir, results)
            print(f"[live-sidepanel] {task_id} failed during bootstrap navigation: {exc}", flush=True)
            try:
                context.close()
            except Exception:
                pass
            return 1
        sidepanel = context.new_page()
        sidepanel.goto(f"chrome-extension://{extension_id}/src/sidepanel/index.html")
        _open_workflow_panel(sidepanel)
        sidepanel.screenshot(path=str(REPORT_DIR / "sidepanel_loaded.png"), full_page=True)
        if args.inspect_chat_name:
            target.bring_to_front()
            search = target.locator('input[role="textbox"], [contenteditable="true"][role="textbox"]').first
            try:
                search.wait_for(state="visible", timeout=30_000)
            except PlaywrightTimeoutError:
                unavailable_screenshot = REPORT_DIR / "inspection-whatsapp-unavailable.png"
                unavailable_text = REPORT_DIR / "inspection-whatsapp-unavailable.txt"
                target.screenshot(path=str(unavailable_screenshot), full_page=True, timeout=15_000)
                unavailable_text.write_text(target.locator("body").inner_text(timeout=5_000), encoding="utf-8")
                print(f"[live-sidepanel] WhatsApp chat search unavailable: {unavailable_screenshot}", flush=True)
                context.close()
                return 2
            search.fill(args.inspect_chat_name, timeout=10_000)
            target.wait_for_timeout(1200)
            exact = target.locator('span[title]').filter(has_text=re.compile(rf"^{re.escape(args.inspect_chat_name)}$", re.I)).first
            if not exact.is_visible(timeout=5_000):
                exact = target.get_by_text(args.inspect_chat_name, exact=True).first
            exact.click(timeout=10_000)
            target.wait_for_timeout(1800)
            safe_name = re.sub(r"[^a-z0-9]+", "-", args.inspect_chat_name.lower()).strip("-") or "chat"
            inspection_screenshot = REPORT_DIR / f"inspection-{safe_name}.png"
            inspection_text = REPORT_DIR / f"inspection-{safe_name}.txt"
            target.screenshot(path=str(inspection_screenshot), full_page=True, timeout=15_000)
            evidence = target.evaluate(
                r"""(chatName) => ({
                    text: (document.body.innerText || '').slice(-12000),
                    images: Array.from(document.querySelectorAll('img')).slice(-80).map((img) => ({
                        alt: img.getAttribute('alt') || '',
                        aria_label: img.getAttribute('aria-label') || '',
                        src_prefix: (img.getAttribute('src') || '').slice(0, 120),
                    })),
                    exact_matches: Array.from(document.querySelectorAll('body *'))
                        .filter((el) => (el.textContent || '').replace(/\s+/g, ' ').trim() === chatName)
                        .slice(0, 20)
                        .map((el) => ({
                            tag: el.tagName.toLowerCase(),
                            role: el.getAttribute('role') || '',
                            title: el.getAttribute('title') || '',
                            aria_label: el.getAttribute('aria-label') || '',
                            class_name: String(el.className || '').slice(0, 300),
                            outer_html: el.outerHTML.slice(0, 1500),
                        })),
                })""",
                args.inspect_chat_name,
            )
            evidence["adapter_traces"] = sidepanel.evaluate(
                """async () => {
                    const stored = await chrome.storage.local.get('phase2_adapter_traces');
                    const traces = Array.isArray(stored.phase2_adapter_traces) ? stored.phase2_adapter_traces : [];
                    return traces.slice(-20);
                }"""
            )
            inspection_text.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(f"[live-sidepanel] inspection screenshot: {inspection_screenshot}", flush=True)
            print(f"[live-sidepanel] inspection evidence: {inspection_text}", flush=True)
            context.close()
            return 0
        if args.pause_before_tasks:
            target.bring_to_front()
            print(
                "[live-sidepanel] browser ready for operator authentication; press Enter to continue",
                flush=True,
            )
            input()

        for task_id, prompt in selected_tasks:
            print(f"[live-sidepanel] starting {task_id}", flush=True)
            result = _run_task(
                sidepanel,
                target,
                task_id,
                prompt,
                args.timeout_s,
                args.file_path,
                args.allow_confirmed_critical,
                args.enable_advanced_control,
            )
            results.append(result)
            _write_report(extension_id, profile_dir, results)
            print(f"[live-sidepanel] {task_id} {result.status} {result.duration_s}s", flush=True)
            if result.status == "failed":
                break

        _write_report(extension_id, profile_dir, results)
        try:
            context.close()
        except Exception as exc:
            print(f"[live-sidepanel] browser close warning: {exc}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
