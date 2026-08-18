from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import parse_qs, quote_plus, urlparse

from app.schemas.response import AnalyzeResponse, ReportOutcome, SuggestedAction


@dataclass(frozen=True)
class AppDestination:
    app_id: str
    display_name: str
    aliases: tuple[str, ...]
    entry_url: str
    domains: tuple[str, ...]
    capabilities: frozenset[str]


@dataclass(frozen=True)
class DestinationObjective:
    objective_id: str
    text: str
    capability: str
    app_id: str | None = None
    explicit_url: str | None = None
    entity_name: str | None = None
    constrained_app_id: str | None = None


@dataclass(frozen=True)
class DestinationCandidate:
    title: str
    url: str
    domain: str
    score: float
    evidence: tuple[str, ...] = field(default_factory=tuple)
    account_sensitive: bool = False


@dataclass(frozen=True)
class DestinationDecision:
    kind: Literal["none", "navigate", "search", "ask", "report"]
    objective: DestinationObjective | None = None
    url: str | None = None
    message: str = ""
    candidates: tuple[DestinationCandidate, ...] = field(default_factory=tuple)


APP_DESTINATIONS: tuple[AppDestination, ...] = (
    AppDestination(
        "youtube", "YouTube", ("youtube", "you tube", "yt"),
        "https://www.youtube.com/", ("youtube.com",),
        frozenset({"navigation", "media_search", "media_playback"}),
    ),
    AppDestination(
        "gmail", "Gmail", ("gmail", "google mail"),
        "https://mail.google.com/", ("mail.google.com",),
        frozenset({"navigation", "email", "mail_search", "draft", "send"}),
    ),
    AppDestination(
        "whatsapp", "WhatsApp", ("whatsapp", "whats app", "whatsapp web"),
        "https://web.whatsapp.com/", ("web.whatsapp.com",),
        frozenset({"navigation", "messaging", "file_transfer"}),
    ),
    AppDestination(
        "google_drive", "Google Drive", ("google drive", "drive"),
        "https://drive.google.com/", ("drive.google.com",),
        frozenset({"navigation", "file_storage", "file_search", "file_transfer"}),
    ),
    AppDestination(
        "google_docs", "Google Docs", ("google docs", "docs"),
        "https://docs.google.com/", ("docs.google.com",),
        frozenset({"navigation", "document_edit", "document_search"}),
    ),
    AppDestination(
        "linkedin_jobs", "LinkedIn Jobs", ("linkedin jobs",),
        "https://www.linkedin.com/jobs/", ("linkedin.com",),
        frozenset({"navigation", "job_search"}),
    ),
    AppDestination(
        "linkedin", "LinkedIn", ("linkedin",),
        "https://www.linkedin.com/", ("linkedin.com",),
        frozenset({"navigation", "professional_network"}),
    ),
)

_APP_BY_ID = {app.app_id: app for app in APP_DESTINATIONS}
_SEARCH_HOSTS = {"google.com", "www.google.com", "bing.com", "www.bing.com"}
_UNSAFE_SCHEMES = {"javascript", "data", "file", "chrome", "chrome-extension", "about"}
_ACCOUNT_PATH_TERMS = ("login", "signin", "sign-in", "account", "student", "portal", "exam")


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).split())


def _app_mentioned(text: str) -> AppDestination | None:
    normalized = f" {_normalize(text)} "
    matches: list[tuple[int, AppDestination]] = []
    for app in APP_DESTINATIONS:
        for alias in app.aliases:
            needle = f" {_normalize(alias)} "
            if needle in normalized:
                matches.append((len(needle), app))
    return max(matches, key=lambda item: item[0])[1] if matches else None


def known_app_entry_url(text: str) -> str:
    app = _app_mentioned(text)
    return app.entry_url if app else ""


def _capability(text: str) -> str:
    normalized = _normalize(text)
    if re.search(r"\b(play|listen|music|song|video)\b", normalized):
        return "media_playback"
    if re.search(r"\b(email|mail|inbox|draft|compose)\b", normalized):
        return "email"
    if re.search(r"\b(message|chat|whatsapp|text)\b", normalized):
        return "messaging"
    if re.search(r"\b(document|doc|write|edit)\b", normalized):
        return "document_edit"
    if re.search(r"\b(file|folder|drive|upload|download)\b", normalized):
        return "file_storage"
    if re.search(r"\b(portal|college|university|school)\b", normalized):
        return "portal_access"
    return "navigation"


def _safe_http_url(value: str) -> str | None:
    candidate = str(value or "").strip().rstrip(".,);]")
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return None
    if parsed.scheme.lower() in _UNSAFE_SCHEMES:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    return candidate


def _explicit_url(text: str) -> str | None:
    match = re.search(r"https?://[^\s<>'\"`]+", str(text or ""), flags=re.IGNORECASE)
    return _safe_http_url(match.group(0)) if match else None


def _split_objectives(task: str) -> list[str]:
    normalized = " ".join(str(task or "").split())
    parts = re.split(r"\s*(?:;|\band then\b|\bthen\b|\band\b)\s*", normalized, flags=re.IGNORECASE)
    meaningful = [part.strip(" ,.") for part in parts if part.strip(" ,.")]
    return meaningful or [normalized]


def _is_complex_mission(task: str) -> bool:
    """Leave research/collection/read pipelines to Mission Blueprint.

    Destination Resolution owns choosing where a task starts, not replacing an
    already structured multi-source mission or interpreting page-local controls.
    """
    normalized = _normalize(task)
    return bool(re.search(
        r"\b(?:collect|extract|compare|research|read each|multi page|multiple pages|"
        r"open top|open the top|top \d+|return (?:a )?(?:table|report)|source url|"
        r"pricing|limitation)\b",
        normalized,
    ))


def _unknown_entity(text: str) -> str | None:
    match = re.search(
        r"\b(?:open|visit|navigate to|go to)\s+(?:the\s+)?(.+?)(?:\s+(?:website|site))?$",
        str(text or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    entity = re.sub(r"\b(?:official|website|site)\b", " ", match.group(1), flags=re.IGNORECASE)
    entity = " ".join(entity.split()).strip(" ,.")
    if not entity:
        return None
    normalized = _normalize(entity)
    generic_targets = {
        "one", "it", "this", "that", "first", "second", "result", "first result",
        "folder", "file", "document", "chat", "thread", "message", "menu", "dialog",
        "settings", "tab", "inbox", "draft", "link", "attachment",
    }
    if normalized in generic_targets or normalized.startswith(("a synthetic ", "the first ", "the exact ")):
        return None
    has_destination_cue = bool(re.search(
        r"\b(?:portal|college|university|school|website|site|app|application)\b",
        entity,
        flags=re.IGNORECASE,
    ))
    has_name_shape = bool(re.search(r"\b[A-Z][A-Za-z0-9]{2,}\b|\b[A-Z]{3,}\b", entity))
    is_single_specific_token = len(normalized.split()) == 1 and normalized not in generic_targets
    return entity if has_destination_cue or has_name_shape or is_single_specific_token else None


def _constrained_app(text: str) -> AppDestination | None:
    normalized = _normalize(text)
    for app in APP_DESTINATIONS:
        for alias in app.aliases:
            escaped = re.escape(_normalize(alias))
            if re.search(rf"\b(?:inside|within|using)\s+(?:the\s+)?{escaped}\b", normalized):
                return app
    return None


def decompose_destination_objectives(task: str) -> list[DestinationObjective]:
    objectives: list[DestinationObjective] = []
    for index, part in enumerate(_split_objectives(task), start=1):
        capability = _capability(part)
        app = _app_mentioned(part)
        constrained = _constrained_app(part)
        explicit = _explicit_url(part)
        entity = None if app or explicit else _unknown_entity(part)
        if app is None and capability == "media_playback":
            app = _APP_BY_ID["youtube"]
        if not any((app, explicit, entity, constrained)):
            continue
        objectives.append(DestinationObjective(
            objective_id=f"objective-{index}",
            text=part,
            capability=capability,
            app_id=app.app_id if app else None,
            explicit_url=explicit,
            entity_name=entity,
            constrained_app_id=constrained.app_id if constrained else None,
        ))
    return objectives


def _successful_prior_urls(prior_steps: list[Any]) -> list[str]:
    urls: list[str] = []
    for step in prior_steps or []:
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        result = str(data.get("execution_result") or "").lower()
        if any(term in result for term in ("fail", "error", "no_effect", "no effect")):
            continue
        value = _safe_http_url(str(data.get("value") or ""))
        page_url = _safe_http_url(str(data.get("page_url") or ""))
        if value:
            urls.append(value)
        if page_url:
            urls.append(page_url)
    return urls


def _host_matches(url: str, domains: tuple[str, ...]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def _accepted_alternative(user_context: str) -> bool:
    normalized = _normalize(user_context)
    return bool(re.search(r"\banswer\s+(?:yes|okay|ok|sure|proceed|continue)\b", normalized)) or any(
        f"use {_normalize(app.display_name)}" in normalized for app in APP_DESTINATIONS
    )


def _objective_satisfied(
    objective: DestinationObjective,
    current_url: str,
    prior_steps: list[Any],
    user_context: str = "",
) -> bool:
    observed_urls = [current_url, *_successful_prior_urls(prior_steps)]
    if objective.constrained_app_id and _accepted_alternative(user_context):
        constrained = _APP_BY_ID[objective.constrained_app_id]
        if objective.capability not in constrained.capabilities:
            compatible = [app for app in APP_DESTINATIONS if objective.capability in app.capabilities]
            return any(
                _host_matches(url, app.domains)
                for url in observed_urls if url
                for app in compatible
            )
    if objective.app_id:
        app = _APP_BY_ID[objective.app_id]
        return any(_host_matches(url, app.domains) for url in observed_urls if url)
    if objective.explicit_url:
        expected = urlparse(objective.explicit_url)
        return any(
            (urlparse(url).hostname or "").lower() == (expected.hostname or "").lower()
            for url in observed_urls if url
        )
    return False


def _query_for(objective: DestinationObjective) -> str:
    entity = objective.entity_name or objective.text
    suffix = "official portal" if objective.capability == "portal_access" else "official website"
    return f"{entity} {suffix}".strip()


def _is_search_page(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return host in _SEARCH_HOSTS and parsed.path.rstrip("/") in {"/search", "/search/"}


def _unwrap_search_url(href: str) -> str | None:
    safe = _safe_http_url(href)
    if not safe:
        return None
    parsed = urlparse(safe)
    if (parsed.hostname or "").lower() in _SEARCH_HOSTS and parsed.path == "/url":
        values = parse_qs(parsed.query).get("q") or parse_qs(parsed.query).get("url")
        return _safe_http_url(values[0]) if values else None
    return safe


def _candidate_rows(page_context: Any) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for item in [
        *list(getattr(page_context, "interactive_elements", []) or []),
        *list(getattr(page_context, "content_blocks", []) or []),
    ]:
        data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        href = _unwrap_search_url(str(data.get("href") or ""))
        if not href:
            continue
        title = " ".join(str(data.get(key) or "") for key in ("text", "accessibility_name", "aria_label")).strip()
        rows.append((title, href))
    return rows


def _candidate_score(objective: DestinationObjective, title: str, url: str) -> DestinationCandidate | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if not host or host in _SEARCH_HOSTS:
        return None
    entity = _normalize(objective.entity_name or objective.text)
    tokens = [token for token in entity.split() if len(token) > 2 and token not in {"college", "portal", "official"}]
    haystack = _normalize(f"{title} {host} {parsed.path}")
    matched = [token for token in tokens if token in haystack]
    evidence: list[str] = []
    score = 0.0
    if tokens and len(matched) == len(tokens):
        score += 0.48
        evidence.append("all entity terms match")
    elif matched:
        score += 0.28 * (len(matched) / len(tokens))
        evidence.append("partial entity match")
    compact_entity = "".join(tokens)
    compact_host = re.sub(r"[^a-z0-9]", "", host)
    if compact_entity and compact_entity in compact_host:
        score += 0.25
        evidence.append("entity matches domain")
    if objective.capability == "portal_access" and any(term in haystack for term in _ACCOUNT_PATH_TERMS):
        score += 0.13
        evidence.append("portal purpose match")
    if "official" in _normalize(title):
        score += 0.08
        evidence.append("official label")
    if parsed.scheme == "https":
        score += 0.04
        evidence.append("https")
    account_sensitive = any(term in _normalize(f"{host} {parsed.path} {title}") for term in _ACCOUNT_PATH_TERMS)
    return DestinationCandidate(title=title or host, url=url, domain=host, score=min(score, 1.0), evidence=tuple(evidence), account_sensitive=account_sensitive)


def _rank_candidates(objective: DestinationObjective, page_context: Any) -> list[DestinationCandidate]:
    best_by_url: dict[str, DestinationCandidate] = {}
    for title, url in _candidate_rows(page_context):
        candidate = _candidate_score(objective, title, url)
        if candidate is None:
            continue
        key = candidate.url.rstrip("/").lower()
        existing = best_by_url.get(key)
        if existing is None or candidate.score > existing.score:
            best_by_url[key] = candidate
    return sorted(best_by_url.values(), key=lambda item: (-item.score, item.domain, item.url))


def _failed_prior_for_url(url: str, prior_steps: list[Any]) -> bool:
    expected = url.rstrip("/").lower()
    for step in prior_steps or []:
        data = step.model_dump() if hasattr(step, "model_dump") else dict(step)
        if str(data.get("value") or "").rstrip("/").lower() != expected:
            continue
        result = str(data.get("execution_result") or "").lower()
        if any(term in result for term in ("fail", "error", "no_effect", "no effect", "timeout")):
            return True
    return False


def _selected_candidate(candidates: list[DestinationCandidate], user_context: str) -> DestinationCandidate | None:
    normalized = _normalize(user_context)
    if not normalized:
        return None
    matches: list[DestinationCandidate] = []
    for candidate in candidates:
        domain = candidate.domain.lower()
        title_terms = [term for term in _normalize(candidate.title).split() if len(term) > 3]
        if domain in user_context.lower() or (title_terms and all(term in normalized for term in title_terms[:4])):
            matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


def _decision(task: str, page_context: Any, prior_steps: list[Any], user_context: str = "") -> DestinationDecision:
    if _is_complex_mission(task):
        return DestinationDecision("none")
    objectives = decompose_destination_objectives(task)
    if not objectives:
        return DestinationDecision("none")
    current_url = str(getattr(page_context, "url", "") or "")
    completed_count = 0
    pending: DestinationObjective | None = None
    for objective in objectives:
        if _objective_satisfied(objective, current_url, prior_steps, user_context):
            completed_count += 1
            continue
        pending = objective
        break
    if pending is None:
        return DestinationDecision("none")

    if pending.constrained_app_id:
        constrained = _APP_BY_ID[pending.constrained_app_id]
        if pending.capability not in constrained.capabilities:
            alternatives = [app.display_name for app in APP_DESTINATIONS if pending.capability in app.capabilities]
            alternative = alternatives[0] if alternatives else "another suitable application"
            if _accepted_alternative(user_context) and alternatives:
                alternative_app = next(app for app in APP_DESTINATIONS if app.display_name == alternative)
                return DestinationDecision(
                    "navigate", pending, alternative_app.entry_url,
                    f"Use the user-approved compatible application {alternative_app.display_name}.",
                )
            return DestinationDecision(
                "ask",
                pending,
                message=(
                    f"{constrained.display_name} does not support {pending.capability.replace('_', ' ')}. "
                    f"I did not search or loop inside {constrained.display_name}. May I use {alternative} instead?"
                ),
            )

    if pending.explicit_url:
        if _failed_prior_for_url(pending.explicit_url, prior_steps):
            return DestinationDecision(
                "report", pending,
                message=f"I could not open the supplied destination after a bounded safe attempt. No duplicate navigation was performed.",
            )
        return DestinationDecision("navigate", pending, pending.explicit_url, "Use the explicit safe URL supplied by the user.")
    if pending.app_id:
        app = _APP_BY_ID[pending.app_id]
        if _failed_prior_for_url(app.entry_url, prior_steps):
            return DestinationDecision(
                "report", pending,
                message=(
                    f"I could not open {app.display_name} after a bounded safe attempt. "
                    "I stopped instead of repeating the same navigation. Check the network or sign-in state and try again."
                ),
            )
        return DestinationDecision(
            "navigate", pending, app.entry_url,
            f"Resolve {app.display_name} through the trusted application registry.",
        )
    if not pending.entity_name:
        return DestinationDecision("none")

    if not _is_search_page(current_url):
        query = _query_for(pending)
        return DestinationDecision(
            "search", pending, f"https://www.google.com/search?q={quote_plus(query)}",
            f"Discover an evidence-backed destination for {pending.entity_name}.",
        )

    candidates = _rank_candidates(pending, page_context)
    credible = [candidate for candidate in candidates if candidate.score >= 0.55]
    if not credible:
        return DestinationDecision(
            "report", pending,
            message=(
                f'I could not verify an official destination for "{pending.entity_name}" from the available search results. '
                "No candidate website was opened. Please provide the city, full organization name, or another identifying detail."
            ),
        )
    top = credible[0]
    selected = _selected_candidate(credible, user_context)
    if selected is not None:
        return DestinationDecision(
            "navigate", pending, selected.url,
            f"Open the destination explicitly selected by the user after candidate verification ({', '.join(selected.evidence)}).",
            candidates=(selected,),
        )
    competing_domains = {
        candidate.domain for candidate in credible
        if candidate.score >= top.score - 0.12
    }
    if len(competing_domains) > 1 or (top.account_sensitive and top.score < 0.78):
        choices = "; ".join(f"{item.title} ({item.domain})" for item in credible[:3])
        return DestinationDecision(
            "ask", pending,
            message=(
                f'I found multiple plausible destinations for "{pending.entity_name}": {choices}. '
                "Which institution or portal should I open? No candidate has been opened."
            ),
            candidates=tuple(credible[:3]),
        )
    return DestinationDecision(
        "navigate", pending, top.url,
        f"Open the highest-confidence verified destination ({', '.join(top.evidence)}).",
        candidates=(top,),
    )


def _action_id(session_id: str, objective: DestinationObjective, url: str) -> str:
    digest = hashlib.sha256(f"{session_id}|{objective.objective_id}|{url}".encode("utf-8")).hexdigest()[:16]
    return f"destination-{digest}"


def resolve_destination(
    *,
    session_id: str,
    task: str,
    page_context: Any,
    prior_steps: list[Any] | None = None,
    user_context: str = "",
) -> AnalyzeResponse | None:
    decision = _decision(task, page_context, prior_steps or [], user_context)
    if decision.kind == "none" or decision.objective is None:
        return None
    if decision.kind == "ask":
        return AnalyzeResponse(
            session_id=session_id,
            analysis="Destination resolution paused because identity or capability was not safe to infer.",
            outcome_kind="ask",
            clarification_question=decision.message,
            suggested_actions=[],
        )
    if decision.kind == "report":
        return AnalyzeResponse(
            session_id=session_id,
            analysis="Destination discovery ended safely without selecting an unverifiable website.",
            outcome_kind="report",
            report=ReportOutcome(answer=decision.message, claim="No verified destination was available in observed search evidence."),
            suggested_actions=[],
            sgv_verified=True,
            goal_convergence=True,
            backend_authoritative_report=True,
        )
    assert decision.url
    current_url = str(getattr(page_context, "url", "") or "")
    preserve_existing = bool(_successful_prior_urls(prior_steps or [])) and current_url.startswith(("http://", "https://"))
    action_type = "open_new_tab" if preserve_existing else "navigate"
    return AnalyzeResponse(
        session_id=session_id,
        analysis=decision.message,
        outcome_kind="act",
        suggested_actions=[SuggestedAction(
            action_id=_action_id(session_id, decision.objective, decision.url),
            action_type=action_type,
            target_selector="",
            value=decision.url,
            description=(
                f"Search for the official destination of {decision.objective.entity_name}"
                if decision.kind == "search"
                else f"Open the resolved destination for {decision.objective.text}"
            ),
            reasoning=decision.message,
            confidence=0.92 if decision.kind == "navigate" else 0.85,
            safety_level="safe",
            provenance=[{
                "source_type": "system",
                "source_id": "destination_resolver.v1",
                "trust": "trusted",
                "labels": ["natural_language_destination", decision.kind],
            }],
        )],
    )
