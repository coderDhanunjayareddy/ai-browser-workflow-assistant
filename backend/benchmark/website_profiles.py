"""
M0 — Website Profiles.

Per-site operational configuration that is NOT task-specific: auth strategy, rate limiting,
anti-bot expectation, recording mode. Pure data + a lookup. The runner reads a profile to
decide how to set up the browser for every task on that site.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WebsiteProfile:
    site_id:             str
    base_url:            str
    auth_required:       bool = False
    auth_strategy:       str = "none"          # "none" | "session_state" | "credential_login"
    auth_state_file:     Optional[str] = None  # relative to benchmark/.playwright_state/
    credentials_key:     Optional[str] = None
    rate_limit_delay_ms: int = 0               # minimum delay between tasks on this site
    captcha_probability: str = "low"           # "low" | "medium" | "high"
    anti_bot:            bool = False
    recording_mode:      str = "live"          # "live" | "recorded"
    known_blocks:        list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "site_id": self.site_id, "base_url": self.base_url,
            "auth_required": self.auth_required, "auth_strategy": self.auth_strategy,
            "auth_state_file": self.auth_state_file, "credentials_key": self.credentials_key,
            "rate_limit_delay_ms": self.rate_limit_delay_ms,
            "captcha_probability": self.captcha_probability, "anti_bot": self.anti_bot,
            "recording_mode": self.recording_mode, "known_blocks": self.known_blocks,
        }


# ── Registry ───────────────────────────────────────────────────────────────--

_PROFILES: dict[str, WebsiteProfile] = {p.site_id: p for p in [
    # local fixture server (offline, deterministic)
    WebsiteProfile("fixture_server", "", auth_required=False),

    # no-auth real sites
    WebsiteProfile("youtube_com",   "https://www.youtube.com",  captcha_probability="low"),
    WebsiteProfile("github_com",    "https://github.com",       captcha_probability="low",
                   rate_limit_delay_ms=2000),
    WebsiteProfile("instagram_com", "https://www.instagram.com", captcha_probability="medium",
                   anti_bot=True, known_blocks=["/accounts/login"]),
    WebsiteProfile("zomato_com",    "https://www.zomato.com",   captcha_probability="medium",
                   anti_bot=True),
    WebsiteProfile("amazon_in",     "https://www.amazon.in",    captcha_probability="high",
                   anti_bot=True, rate_limit_delay_ms=3000),
    WebsiteProfile("flipkart_com",  "https://www.flipkart.com", captcha_probability="high",
                   anti_bot=True, rate_limit_delay_ms=3000),
    WebsiteProfile("booking_com",   "https://www.booking.com",  captcha_probability="medium",
                   anti_bot=True),
    WebsiteProfile("makemytrip_com", "https://www.makemytrip.com", captcha_probability="high",
                   anti_bot=True, rate_limit_delay_ms=3000),

    # auth-gated real sites (session_state; auth files do not exist until recorded)
    WebsiteProfile("linkedin_com", "https://www.linkedin.com", auth_required=True,
                   auth_strategy="session_state", auth_state_file="linkedin_com.json",
                   captcha_probability="medium", anti_bot=True),
    WebsiteProfile("docs_google_com", "https://docs.google.com", auth_required=True,
                   auth_strategy="session_state", auth_state_file="google_com.json"),
    WebsiteProfile("sheets_google_com", "https://sheets.google.com", auth_required=True,
                   auth_strategy="session_state", auth_state_file="google_com.json"),
    WebsiteProfile("gmail_com", "https://mail.google.com", auth_required=True,
                   auth_strategy="session_state", auth_state_file="google_com.json"),
    WebsiteProfile("canva_com", "https://www.canva.com", auth_required=True,
                   auth_strategy="session_state", auth_state_file="canva_com.json"),

    # cross-site composite (no single base)
    WebsiteProfile("cross_site", "", auth_required=False),
]}


def get_profile(site_id: str) -> Optional[WebsiteProfile]:
    return _PROFILES.get(site_id)


def all_profiles() -> list[WebsiteProfile]:
    return list(_PROFILES.values())
