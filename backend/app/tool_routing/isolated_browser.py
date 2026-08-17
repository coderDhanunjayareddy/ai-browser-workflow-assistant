from __future__ import annotations

import ipaddress
import socket
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class IsolatedResearchResult:
    url: str
    title: str
    text: str
    links: list[dict[str, str]]
    isolation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only credential-free public http/https URLs are allowed")
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        raise ValueError("Local and private destinations are blocked")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError("Destination hostname could not be resolved") from exc
    if not addresses or any(not _is_public_ip(value) for value in addresses):
        raise ValueError("Local, private, link-local, and reserved destinations are blocked")
    return url


def run_isolated_research(
    url: str,
    *,
    timeout_ms: int = 15_000,
    playwright_factory: Any = None,
) -> IsolatedResearchResult:
    target = validate_public_url(url)
    if playwright_factory is None:
        from playwright.sync_api import sync_playwright
        playwright_factory = sync_playwright

    with playwright_factory() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            accept_downloads=False,
            service_workers="block",
            viewport={"width": 1280, "height": 900},
        )
        try:
            context.clear_cookies()
            context.route("**/*", _guard_public_request)
            page = context.new_page()
            page.set_default_timeout(timeout_ms)
            page.goto(target, wait_until="domcontentloaded", timeout=timeout_ms)
            final_url = validate_public_url(page.url)
            title = page.title()[:300]
            text = page.locator("body").inner_text(timeout=timeout_ms)[:20_000]
            raw_links = page.locator("a[href]").evaluate_all(
                "els => els.slice(0, 50).map(a => ({text: (a.innerText || a.textContent || '').trim().slice(0, 200), url: a.href}))"
            )
            links = [
                {"text": str(item.get("text", ""))[:200], "url": str(item.get("url", ""))[:2048]}
                for item in raw_links
                if isinstance(item, dict) and str(item.get("url", "")).startswith(("http://", "https://"))
            ][:50]
            return IsolatedResearchResult(
                url=final_url,
                title=title,
                text=text,
                links=links,
                isolation={
                    "profile": "ephemeral",
                    "logged_out": True,
                    "persist_storage": False,
                    "downloads": False,
                    "extensions": False,
                    "service_workers": "blocked",
                },
            )
        finally:
            context.close()
            browser.close()


def _is_public_ip(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.is_global


def _guard_public_request(route: Any) -> None:
    try:
        validate_public_url(route.request.url)
    except ValueError:
        route.abort()
        return
    route.continue_()
