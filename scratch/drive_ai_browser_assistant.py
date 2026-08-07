from __future__ import annotations

import re
import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = ROOT / "extension" / "dist"
PROFILE_DIR = ROOT / "playwright-profile-ai-assistant-task"
TASK = """Open Google Search and search for: `best AI browser automation tools 2026`.
From the first page of results:
1. Open the top 5 relevant results in new tabs.
2. Read each page enough to identify the product name, main purpose, pricing mention, and one key limitation.
3. Create a clean comparison table with columns: Tool, Purpose, Pricing, Limitation, URL.
4. Return the table only"""


def discover_extension_id(context) -> str:
    deadline = time.time() + 15
    while time.time() < deadline:
        for worker in context.service_workers:
            match = re.match(r"chrome-extension://([^/]+)/", worker.url)
            if match:
                return match.group(1)
        context.wait_for_event("serviceworker", timeout=1000)
    raise RuntimeError("AI Browser Assistant service worker did not start")


def click_if_visible(page, name: str, timeout: int = 500) -> bool:
    locator = page.get_by_role("button", name=re.compile(name, re.I)).first
    try:
        if locator.is_visible(timeout=timeout):
            locator.click(timeout=timeout)
            return True
    except PlaywrightTimeoutError:
        return False
    except Exception:
        return False
    return False


def main() -> None:
    if PROFILE_DIR.exists():
        shutil.rmtree(PROFILE_DIR)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=False,
            args=[
                f"--disable-extensions-except={EXTENSION_DIR}",
                f"--load-extension={EXTENSION_DIR}",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )

        google = context.new_page()
        google.goto("https://www.google.com/", wait_until="domcontentloaded", timeout=30000)

        extension_id = discover_extension_id(context)
        print(f"EXTENSION_ID={extension_id}")

        panel = context.new_page()
        panel.goto(
            f"chrome-extension://{extension_id}/src/sidepanel/index.html",
            wait_until="domcontentloaded",
            timeout=30000,
        )
        panel.wait_for_timeout(1500)

        panel.get_by_role("button", name="Workflow").click(timeout=10000)
        panel.locator("textarea").first.fill(TASK, timeout=10000)

        auto_label = panel.locator("label", has_text=re.compile("Auto", re.I)).first
        auto_label.click(timeout=5000)
        panel.get_by_role("button", name=re.compile("Analyze", re.I)).click(timeout=10000)

        final_text = ""
        deadline = time.time() + 600
        last_print = 0.0
        while time.time() < deadline:
            panel.wait_for_timeout(1500)
            text = panel.locator("body").inner_text(timeout=5000)
            if time.time() - last_print > 15:
                print("STATUS", text[-1200:].replace("\n", " | "))
                last_print = time.time()

            # Auto mode runs safe actions, but dangerous/uncertain actions still need approval.
            if click_if_visible(panel, "Approve", timeout=800):
                print("APPROVED")
                continue

            if "Type the missing detail" in text or "Need information" in text:
                print("NEEDS_INPUT")
                print(text)
                break

            if "Workflow error" in text or "Execution failed" in text or "HTTP " in text:
                print("ERROR_TEXT")
                print(text)
                break

            table_match = re.search(r"(\| *Tool *\| *Purpose *\| *Pricing *\| *Limitation *\| *URL *\|[\s\S]+)", text)
            if table_match and ("✓ Done" in text or "No actions needed" in text or text.count("|") > 15):
                final_text = table_match.group(1).strip()
                break

        if not final_text:
            final_text = panel.locator("body").inner_text(timeout=5000)

        print("FINAL_OUTPUT_START")
        print(final_text)
        print("FINAL_OUTPUT_END")
        context.close()


if __name__ == "__main__":
    main()
