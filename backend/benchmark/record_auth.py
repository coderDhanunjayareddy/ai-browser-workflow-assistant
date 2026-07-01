"""
M0 — Auth state recorder.

Opens a headed Chromium so an operator can sign in to a site manually (including 2FA),
then saves the Playwright storage state (cookies + localStorage) to
benchmark/.playwright_state/{site}.json. Auth-gated benchmark tasks restore this state.

Auth state files are gitignored and contain live session secrets — store them in the team
vault, never commit them, and refresh roughly every 14 days.

Usage:
  python -m benchmark.record_auth --site google_com --url https://accounts.google.com
"""
from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
AUTH_DIR = os.path.join(_HERE, ".playwright_state")


def record(site: str, url: str) -> int:
    from playwright.sync_api import sync_playwright
    os.makedirs(AUTH_DIR, exist_ok=True)
    out = os.path.join(AUTH_DIR, f"{site}.json")
    print(f"[record_auth] launching headed browser at {url}")
    print("[record_auth] sign in, then return here and press Enter to save the session.")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(url)
        try:
            input("Press Enter once you are fully signed in... ")
        except EOFError:
            print("[record_auth] no interactive stdin; aborting", flush=True)
            return 2
        ctx.storage_state(path=out)
        browser.close()
    print(f"[record_auth] saved -> {out}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Record Playwright auth state for a site")
    p.add_argument("--site", required=True, help="site_id, e.g. google_com")
    p.add_argument("--url", required=True, help="sign-in URL to open")
    args = p.parse_args(argv)
    return record(args.site, args.url)


if __name__ == "__main__":
    sys.exit(main())
