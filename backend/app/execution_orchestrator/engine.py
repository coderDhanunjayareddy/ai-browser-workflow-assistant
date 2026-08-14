from __future__ import annotations

import re
import time
from typing import Any

from app.browser_url_policy import is_openable_browser_url
from app.execution_orchestrator.artifact_registry import build_artifacts
from app.execution_orchestrator.budgets import build_budgets
from app.execution_orchestrator.completion_engine import build_progress_ledger
from app.execution_orchestrator.models import ExecutionOrchestratorSnapshot
from app.execution_orchestrator.phase_execution import attach_phase_execution_directive
from app.execution_orchestrator.phase_state_machine import build_phases, workflow_category
from app.execution_orchestrator.planner_gating import action_allowed, planner_constraints, reject_for_phase
from app.execution_orchestrator.recovery import route_recovery
from app.execution_orchestrator.replay import phase_replay
from app.execution_orchestrator.telemetry import build_telemetry
from app.execution_orchestrator.transition_engine import build_transitions
from app.feature_flags import is_active, is_shadow_or_active
from app.intent_dispatcher.models import IntentDispatchDirective
from app.schemas.response import AnalyzeResponse, SuggestedAction


class ExecutionOrchestrator:
    def build_snapshot(
        self,
        *,
        session_id: str,
        task: str,
        page_context: Any,
        prior_steps: list[Any],
    ) -> ExecutionOrchestratorSnapshot | None:
        if not is_shadow_or_active("V48_EXECUTION_ORCHESTRATOR"):
            return None
        started = time.perf_counter()
        artifacts = build_artifacts(page_context, prior_steps)
        ledger = build_progress_ledger(task, artifacts, prior_steps, session_id=session_id)
        category = workflow_category(task)
        phases, active_phase = build_phases(category, ledger)
        budgets = build_budgets(prior_steps, artifacts)
        transitions = build_transitions(phases)
        recovery = route_recovery(active_phase, budgets)
        replay = phase_replay(phases, artifacts, transitions)
        telemetry = build_telemetry(
            started_at=started,
            active_phase=active_phase,
            artifacts=artifacts,
            budgets=budgets,
            transitions=transitions,
        )
        return ExecutionOrchestratorSnapshot(
            schema_version="execution_orchestrator.v1",
            session_id=session_id,
            workflow_category=category,
            phases=phases,
            active_phase=active_phase,
            progress_ledger=ledger,
            artifacts=artifacts,
            budgets=budgets,
            transitions=transitions,
            recovery=recovery,
            replay=replay,
            telemetry=telemetry,
        )

    def enrich_context(self, compressed_context: dict[str, Any], snapshot: ExecutionOrchestratorSnapshot | None) -> dict[str, Any]:
        if snapshot is None or not is_active("V48_EXECUTION_ORCHESTRATOR"):
            return compressed_context
        enriched = dict(compressed_context)
        enriched["execution_orchestrator"] = snapshot.to_compact_context()
        enriched["planner_phase_constraints"] = planner_constraints(snapshot)
        return enriched

    def postprocess_response(
        self,
        result: AnalyzeResponse,
        snapshot: ExecutionOrchestratorSnapshot | None,
    ) -> AnalyzeResponse:
        if snapshot is None or not is_active("V48_EXECUTION_ORCHESTRATOR"):
            return result
        if result.outcome_kind in {"report", "ask", "replan"}:
            return result
        if snapshot.budgets.exhausted:
            return reject_for_phase(result, snapshot, f"budget exhausted: {', '.join(snapshot.budgets.exhausted)}")
        if result.intent_dispatch is not None and not result.intent_dispatch.browser_executable:
            if result.intent_execution is not None:
                result.analysis = (
                    f"{result.analysis}\n\nExecution Dispatcher executed intent "
                    f"{result.intent_dispatch.intent} with {result.intent_dispatch.owner}: "
                    f"{result.intent_execution.reason}"
                ).strip()
            return result
        if not result.suggested_actions:
            return result
        action = result.suggested_actions[0]
        read_response = _read_phase_backend_response(result, snapshot, action)
        if read_response is not None:
            return read_response
        source_cap = _source_cap_transition_response(result, snapshot, action)
        if source_cap is not None:
            return attach_phase_execution_directive(source_cap, snapshot)
        search_provider_reroute = _reroute_challenged_search_navigation_response(result, snapshot, action)
        if search_provider_reroute is not None:
            return attach_phase_execution_directive(search_provider_reroute, snapshot)
        direct_open_navigation = _open_phase_direct_navigation_response(result, snapshot, action)
        if direct_open_navigation is not None:
            return direct_open_navigation
        if not action_allowed(action.action_type, snapshot.active_phase):
            open_collection = _open_phase_search_collection_response(result, snapshot, action)
            if open_collection is not None:
                return open_collection
        open_response = _open_phase_entity_response(result, snapshot, action.action_type)
        if open_response is not None:
            return attach_phase_execution_directive(open_response, snapshot)
        if not action_allowed(action.action_type, snapshot.active_phase):
            collect_navigation = _collect_external_navigation_to_collection_response(result, snapshot, action)
            if collect_navigation is not None:
                return collect_navigation
            recovery_navigation = _collect_search_recovery_navigation_response(result, snapshot, action)
            if recovery_navigation is not None:
                return attach_phase_execution_directive(recovery_navigation, snapshot)
            resource_focus = _resource_phase_focus_response(result, snapshot)
            if resource_focus is not None:
                return attach_phase_execution_directive(resource_focus, snapshot)
            partial_open = _collect_partial_open_response(result, snapshot, action)
            if partial_open is not None:
                return partial_open
            collect_response = _collect_before_open_response(result, snapshot, action.action_type)
            if collect_response is not None:
                return collect_response
            return reject_for_phase(result, snapshot, f"action {action.action_type} is not allowed in phase {snapshot.active_phase.name}")
        return attach_phase_execution_directive(result, snapshot)


_orchestrator = ExecutionOrchestrator()


def _source_cap_transition_response(
    result: AnalyzeResponse,
    snapshot: ExecutionOrchestratorSnapshot,
    action: SuggestedAction,
) -> AnalyzeResponse | None:
    action_type = str(action.action_type or "").lower()
    if action_type not in {"navigate", "open_new_tab"}:
        return None
    target = int(snapshot.progress_ledger.target_counts.get("opened_pages", 1) or 1)
    opened_count = int(snapshot.progress_ledger.current_counts.get("opened_pages", 0) or 0)
    if opened_count < target:
        return None
    opened = _opened_source_urls(snapshot)
    if not opened:
        return None
    read = {_canonical_opened_url(url) for url in snapshot.artifacts.visited_urls}
    target_url = next((url for url in opened if _canonical_opened_url(url) not in read), opened[0])
    action = SuggestedAction(
        action_id=f"orchestrator_source_cap_focus_{len(opened)}",
        action_type="focus_existing_tab",
        target_selector="",
        value=f"url:{target_url}",
        description=f"Focus opened source after source cap reached: {target_url}",
        reasoning=(
            "Execution Orchestrator stopped additional source opening because the mission "
            f"already reached the opened source target {opened_count}/{target}; continuing with READ evidence."
        ),
        confidence=0.88,
        safety_level="safe",
    )
    return AnalyzeResponse(
        session_id=result.session_id,
        analysis=(
            f"{result.analysis}\n\nExecution Orchestrator enforced the source collection cap "
            f"({opened_count}/{target}) and advanced to reading opened sources."
        ),
        outcome_kind="act",
        clarification_question=result.clarification_question,
        report=result.report,
        replan=result.replan,
        suggested_actions=[action],
    )


def _collect_before_open_response(
    result: AnalyzeResponse,
    snapshot: ExecutionOrchestratorSnapshot,
    action_type: str,
) -> AnalyzeResponse | None:
    if snapshot.active_phase.name != "COLLECT":
        return None
    if str(action_type or "").lower() != "open_new_tab":
        return None
    if snapshot.progress_ledger.current_counts.get("collected_items", 0) > 0:
        return None
    current_url = snapshot.artifacts.visited_urls[-1] if snapshot.artifacts.visited_urls else ""
    if not _is_search_results_url(current_url):
        return None

    directive = IntentDispatchDirective(
        mission_id=result.session_id,
        intent="collect_search_results",
        owner="browser_intelligence",
        capability="serp_collection",
        dispatch_target="browser_intelligence",
        browser_executable=False,
        reason=(
            "Execution Orchestrator requires deterministic search-result collection "
            "before opening ranked result entities from the COLLECT phase."
        ),
        payload={
            "action_type": "collect_search_results",
            "description": "Collect visible search result candidates before opening sources",
            "reasoning": "Collect and register visible result entities so OPEN phase actions are grounded.",
            "confidence": 0.9,
            "safety_level": "safe",
        },
    )
    return AnalyzeResponse(
        session_id=result.session_id,
        analysis=(
            f"{result.analysis}\n\nExecution Orchestrator converted the premature open-tab proposal "
            "into deterministic search-result collection for the active COLLECT phase."
        ),
        outcome_kind="act",
        suggested_actions=[],
        intent_dispatch=directive,
    )


def _open_phase_search_collection_response(
    result: AnalyzeResponse,
    snapshot: ExecutionOrchestratorSnapshot,
    action: SuggestedAction,
) -> AnalyzeResponse | None:
    if snapshot.active_phase.name != "OPEN":
        return None
    if str(action.action_type or "").lower() not in {"scroll", "wait"}:
        return None
    target = int(snapshot.progress_ledger.target_counts.get("opened_pages", 1) or 1)
    opened_count = int(snapshot.progress_ledger.current_counts.get("opened_pages", 0) or 0)
    if opened_count >= target:
        return None
    opened_urls = {_canonical_opened_url(url) for url in snapshot.artifacts.opened_pages}
    if _openable_entity_count(snapshot.session_id, opened_urls=opened_urls) >= max(1, target - opened_count):
        return None
    current_url = next((url for url in reversed(snapshot.artifacts.visited_urls) if _is_search_results_url(url)), "")
    if not current_url:
        return None

    directive = IntentDispatchDirective(
        mission_id=result.session_id,
        intent="collect_search_results",
        owner="browser_intelligence",
        capability="serp_collection",
        dispatch_target="browser_intelligence",
        browser_executable=False,
        reason=(
            "Execution Orchestrator converted OPEN-phase search-results scrolling into deterministic "
            "search-result collection because the opened source target has not been reached."
        ),
        payload={
            "action_type": "collect_search_results",
            "description": "Collect additional visible search result candidates before opening sources",
            "reasoning": "OPEN phase is below target and needs more grounded source entities.",
            "confidence": 0.88,
            "safety_level": "safe",
        },
    )
    return AnalyzeResponse(
        session_id=result.session_id,
        analysis=(
            f"{result.analysis}\n\nExecution Orchestrator converted OPEN-phase search-result scrolling "
            "into deterministic result collection instead of rejecting the planner action."
        ),
        outcome_kind="act",
        suggested_actions=[],
        intent_dispatch=directive,
    )


def _openable_entity_count(session_id: str, *, opened_urls: set[str]) -> int:
    return len(_openable_entities_for_phase(session_id, opened_urls=opened_urls))


def _open_phase_direct_navigation_response(
    result: AnalyzeResponse,
    snapshot: ExecutionOrchestratorSnapshot,
    action: SuggestedAction,
) -> AnalyzeResponse | None:
    if snapshot.active_phase.name != "OPEN":
        return None
    if str(action.action_type or "").lower() != "navigate":
        return None
    if snapshot.workflow_category not in {"interactive_browser_task", "saas_signup", "file_upload"}:
        return None
    if int(snapshot.progress_ledger.current_counts.get("opened_pages", 0) or 0) > 0:
        return None
    target_url = _extract_http_url(" ".join([
        str(action.value or ""),
        str(action.description or ""),
        str(action.reasoning or ""),
    ])) or _known_app_entry_url(" ".join([
        str(action.value or ""),
        str(action.description or ""),
        str(action.reasoning or ""),
    ])) or str(action.value or "")
    if not is_openable_browser_url(target_url):
        return None
    action.value = target_url
    action.target_selector = ""
    return AnalyzeResponse(
        session_id=result.session_id,
        analysis=(
            f"{result.analysis}\n\nExecution Orchestrator allowed direct OPEN-phase navigation "
            "because this workflow starts from a known web application entry URL."
        ),
        outcome_kind="act",
        clarification_question=result.clarification_question,
        report=result.report,
        replan=result.replan,
        suggested_actions=[action],
    )


def _known_app_entry_url(text: str) -> str:
    lowered = str(text or "").lower()
    known = (
        (("whatsapp", "whats app"), "https://web.whatsapp.com/"),
        (("gmail", "google mail"), "https://mail.google.com/"),
        (("linkedin jobs",), "https://www.linkedin.com/jobs/"),
        (("linkedin",), "https://www.linkedin.com/"),
    )
    for names, url in known:
        if any(name in lowered for name in names):
            return url
    return ""


def _collect_search_recovery_navigation_response(
    result: AnalyzeResponse,
    snapshot: ExecutionOrchestratorSnapshot,
    action: SuggestedAction,
) -> AnalyzeResponse | None:
    if snapshot.active_phase.name != "COLLECT":
        return None
    if str(action.action_type or "").lower() != "navigate":
        return None
    target_url = _extract_http_url(" ".join([
        str(action.value or ""),
        str(action.description or ""),
        str(action.reasoning or ""),
    ])) or str(action.value or "")
    current_url = snapshot.artifacts.visited_urls[-1] if snapshot.artifacts.visited_urls else ""
    if not (_is_safe_http_url(target_url) and _is_search_results_url(current_url)):
        return None
    if not (_is_search_results_url(target_url) or _is_search_provider_url(target_url)):
        return None
    action.value = target_url
    return AnalyzeResponse(
        session_id=result.session_id,
        analysis=(
            f"{result.analysis}\n\nExecution Orchestrator allowed search-provider recovery navigation "
            "inside COLLECT because the current provider did not yield enough openable candidates."
        ),
        outcome_kind=result.outcome_kind,
        clarification_question=result.clarification_question,
        report=result.report,
        replan=result.replan,
        suggested_actions=[action],
    )


def _collect_external_navigation_to_collection_response(
    result: AnalyzeResponse,
    snapshot: ExecutionOrchestratorSnapshot,
    action: SuggestedAction,
) -> AnalyzeResponse | None:
    if snapshot.active_phase.name != "COLLECT":
        return None
    if str(action.action_type or "").lower() != "navigate":
        return None
    target_url = _extract_http_url(" ".join([
        str(action.value or ""),
        str(action.description or ""),
        str(action.reasoning or ""),
    ])) or str(action.value or "")
    current_url = snapshot.artifacts.visited_urls[-1] if snapshot.artifacts.visited_urls else ""
    if not (_is_safe_http_url(target_url) and _is_search_results_url(current_url)):
        return None
    if _is_search_results_url(target_url) or _is_search_provider_url(target_url):
        return None

    directive = IntentDispatchDirective(
        mission_id=result.session_id,
        intent="collect_search_results",
        owner="browser_intelligence",
        capability="serp_collection",
        dispatch_target="browser_intelligence",
        browser_executable=False,
        reason=(
            "Collect visible organic search-result entities before navigating to external source URLs."
        ),
        payload={
            "action_type": "collect_search_results",
            "description": "Collect visible search result candidates before opening sources",
            "reasoning": "External source URLs must be grounded as registered search-result entities first.",
            "confidence": 0.9,
            "safety_level": "safe",
        },
    )
    return AnalyzeResponse(
        session_id=result.session_id,
        analysis=(
            f"{result.analysis}\n\nExecution Orchestrator converted external COLLECT navigation "
            "into deterministic search-result collection before opening sources."
        ),
        outcome_kind="act",
        suggested_actions=[],
        intent_dispatch=directive,
    )


def _collect_partial_open_response(
    result: AnalyzeResponse,
    snapshot: ExecutionOrchestratorSnapshot,
    action: SuggestedAction,
) -> AnalyzeResponse | None:
    if snapshot.active_phase.name != "COLLECT":
        return None
    if str(action.action_type or "").lower() != "open_new_tab":
        return None
    collected = int(snapshot.progress_ledger.current_counts.get("collected_items", 0) or 0)
    if collected <= 0:
        return None
    opened_urls = {_canonical_opened_url(url) for url in snapshot.artifacts.opened_pages}
    entity = _first_openable_entity(snapshot.session_id, opened_urls=opened_urls)
    if entity is not None and entity.canonical_url:
        action = SuggestedAction(
            action_id=f"orchestrator_collect_partial_open_{entity.entity_id[-12:]}",
            action_type="open_new_tab",
            target_selector="",
            value=f"entity:{entity.entity_id}",
            description=f"Open collected source: {entity.title or entity.canonical_url}",
            reasoning=(
                "Execution Orchestrator grounded a partial COLLECT open to a registered "
                f"search-result entity_id={entity.entity_id} before URL execution."
            ),
            confidence=max(0.0, min(1.0, float(entity.confidence or 0.82))),
            safety_level="safe",
        )
    return AnalyzeResponse(
        session_id=result.session_id,
        analysis=(
            f"{result.analysis}\n\nExecution Orchestrator allowed opening an available collected source "
            "because partial collection already produced a grounded candidate."
        ),
        outcome_kind=result.outcome_kind,
        clarification_question=result.clarification_question,
        report=result.report,
        replan=result.replan,
        suggested_actions=[action],
    )


def _is_search_results_url(url: str) -> bool:
    from urllib.parse import urlsplit

    parsed = urlsplit(str(url or ""))
    host = parsed.netloc.lower().removeprefix("www.")
    if host in {"google.com", "bing.com"} and parsed.path.startswith("/search"):
        return True
    if host == "duckduckgo.com" and parsed.query:
        return True
    return False


def _is_search_provider_url(url: str) -> bool:
    from urllib.parse import urlsplit

    parsed = urlsplit(str(url or ""))
    host = parsed.netloc.lower().removeprefix("www.")
    return parsed.scheme in {"http", "https"} and host in {"google.com", "bing.com", "duckduckgo.com"}


def _reroute_challenged_search_navigation_response(
    result: AnalyzeResponse,
    snapshot: ExecutionOrchestratorSnapshot,
    action: SuggestedAction,
) -> AnalyzeResponse | None:
    if str(action.action_type or "").lower() != "navigate":
        return None
    target_url = _extract_http_url(" ".join([
        str(action.value or ""),
        str(action.description or ""),
        str(action.reasoning or ""),
    ])) or str(action.value or "")
    if not _is_search_results_url(target_url):
        return None
    challenged_hosts = _challenged_search_hosts(snapshot.artifacts.visited_urls)
    target_host = _search_host(target_url)
    if not target_host or target_host not in challenged_hosts:
        return None
    query = _query_from_search_url(target_url)
    if not query:
        return None
    target = int(snapshot.progress_ledger.target_counts.get("opened_pages", 1) or 1)
    opened_count = int(snapshot.progress_ledger.current_counts.get("opened_pages", 0) or 0)
    if opened_count >= target:
        return None
    opened_urls = {_canonical_opened_url(url) for url in snapshot.artifacts.opened_pages}
    entity = _first_openable_entity(snapshot.session_id, opened_urls=opened_urls)
    if entity is not None and entity.canonical_url:
        action = SuggestedAction(
            action_id=f"orchestrator_search_recovery_open_{entity.entity_id[-12:]}",
            action_type="open_new_tab",
            target_selector="",
            value=f"entity:{entity.entity_id}",
            description=f"Open collected source instead of repeating search recovery: {entity.title or entity.canonical_url}",
            reasoning=(
                "Execution Orchestrator avoided a repeated search-provider navigation because "
                f"the mission already has an unopened collected source entity_id={entity.entity_id}."
            ),
            confidence=max(0.0, min(1.0, float(entity.confidence or 0.82))),
            safety_level="safe",
        )
        return AnalyzeResponse(
            session_id=result.session_id,
            analysis=(
                f"{result.analysis}\n\nExecution Orchestrator continued with a collected source "
                "instead of repeating challenged search-provider recovery."
            ),
            outcome_kind="act",
            clarification_question=result.clarification_question,
            report=result.report,
            replan=result.replan,
            suggested_actions=[action],
        )
    for provider_url in (
        f"https://duckduckgo.com/?q={query}",
        f"https://www.bing.com/search?q={query}",
    ):
        host = _search_host(provider_url)
        if host and host not in challenged_hosts and _canonical_opened_url(provider_url) != _canonical_opened_url(target_url):
            action.value = provider_url
            action.description = f"Recover search by avoiding challenged provider: {query}"
            action.reasoning = (
                "Execution Orchestrator rerouted search navigation because the requested "
                "provider already showed a challenge/no-results surface during this mission."
            )
            return AnalyzeResponse(
                session_id=result.session_id,
                analysis=(
                    f"{result.analysis}\n\nExecution Orchestrator rerouted challenged search-provider "
                    "navigation to a non-challenged provider."
                ),
                outcome_kind=result.outcome_kind,
                clarification_question=result.clarification_question,
                report=result.report,
                replan=result.replan,
                suggested_actions=[action],
            )
    return None


def _challenged_search_hosts(urls: list[str]) -> set[str]:
    from urllib.parse import urlsplit

    challenged: set[str] = set()
    for url in urls:
        parsed = urlsplit(str(url or ""))
        host = parsed.netloc.lower().removeprefix("www.")
        path = parsed.path.lower()
        if host == "google.com" and path.startswith(("/sorry", "/challenge", "/consent")):
            challenged.add(host)
    return challenged


def _search_host(url: str) -> str:
    from urllib.parse import urlsplit

    return urlsplit(str(url or "")).netloc.lower().removeprefix("www.")


def _query_from_search_url(url: str) -> str:
    from urllib.parse import parse_qs, quote_plus, urlsplit

    raw = parse_qs(urlsplit(str(url or "")).query).get("q", [""])[0]
    return quote_plus(raw)


def _is_safe_http_url(url: str) -> bool:
    from urllib.parse import urlsplit

    parsed = urlsplit(str(url or ""))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _opened_source_urls(snapshot: ExecutionOrchestratorSnapshot) -> list[str]:
    from app.browser_url_policy import is_openable_browser_url

    seen: set[str] = set()
    urls: list[str] = []
    for url in snapshot.artifacts.opened_pages:
        identity = _canonical_opened_url(url)
        if not identity or identity in seen or not is_openable_browser_url(url):
            continue
        seen.add(identity)
        urls.append(url)
    return urls


def _extract_http_url(value: str) -> str | None:
    match = re.search(r"https?://[^\s<>'\"]+", str(value or ""), flags=re.IGNORECASE)
    return match.group(0).rstrip("),.;]") if match else None


def _resource_phase_focus_response(
    result: AnalyzeResponse,
    snapshot: ExecutionOrchestratorSnapshot,
) -> AnalyzeResponse | None:
    if snapshot.active_phase.name not in {"READ", "EXTRACT", "VALIDATE"}:
        return None
    opened = [url for url in snapshot.artifacts.opened_pages if _canonical_opened_url(url)]
    if not opened:
        return None
    read = {_canonical_opened_url(url) for url in snapshot.artifacts.visited_urls}
    target_url = next((url for url in opened if _canonical_opened_url(url) not in read), opened[0])
    action = SuggestedAction(
        action_id=f"orchestrator_{snapshot.active_phase.name.lower()}_focus_recovery",
        action_type="focus_existing_tab",
        target_selector="",
        value=f"url:{target_url}",
        description=f"Focus opened source for {snapshot.active_phase.name.lower()} phase: {target_url}",
        reasoning=(
            "Execution Orchestrator recovered an invalid planner action by focusing an opened "
            f"resource required for the active {snapshot.active_phase.name} phase."
        ),
        confidence=0.86,
        safety_level="safe",
    )
    return AnalyzeResponse(
        session_id=result.session_id,
        analysis=(
            f"{result.analysis}\n\nExecution Orchestrator recovered the {snapshot.active_phase.name} phase "
            "by focusing an opened source instead of allowing a forbidden navigation."
        ),
        outcome_kind="act",
        suggested_actions=[action],
    )


def _read_phase_backend_response(
    result: AnalyzeResponse,
    snapshot: ExecutionOrchestratorSnapshot,
    action: SuggestedAction,
) -> AnalyzeResponse | None:
    if snapshot.active_phase.name != "READ":
        return None
    if str(action.action_type or "").lower() not in {
        "wait",
        "scroll",
        "focus_existing_tab",
        "switch_tab",
        "navigate",
        "open_new_tab",
    }:
        return None
    current_url = snapshot.artifacts.visited_urls[-1] if snapshot.artifacts.visited_urls else ""
    if not _is_opened_resource(snapshot, current_url):
        return None
    directive = IntentDispatchDirective(
        mission_id=result.session_id,
        intent="read_page",
        owner="knowledge_extraction",
        capability="page_reading",
        dispatch_target="knowledge_extraction_pipeline",
        browser_executable=False,
        reason="Read the currently focused opened source page with the backend knowledge extraction pipeline.",
        payload={
            "action_type": "read_page",
            "description": f"Read opened source page: {current_url}",
            "reasoning": (
                "READ phase should extract evidence from the currently focused source instead of waiting repeatedly."
            ),
            "confidence": 0.9,
            "safety_level": "safe",
        },
    )
    return AnalyzeResponse(
        session_id=result.session_id,
        analysis=(
            f"{result.analysis}\n\nExecution Orchestrator routed READ phase to backend page reading "
            "for the focused opened source."
        ),
        outcome_kind="act",
        suggested_actions=[],
        intent_dispatch=directive,
    )


def _open_phase_entity_response(
    result: AnalyzeResponse,
    snapshot: ExecutionOrchestratorSnapshot,
    action_type: str,
) -> AnalyzeResponse | None:
    if snapshot.active_phase.name != "OPEN":
        return None
    if str(action_type or "").lower() in {"open_new_tab", "focus_existing_tab", "switch_tab"}:
        return None
    target = int(snapshot.progress_ledger.target_counts.get("opened_pages", 1) or 1)
    if snapshot.progress_ledger.current_counts.get("opened_pages", 0) >= target:
        return None
    opened_urls = {_canonical_opened_url(url) for url in snapshot.artifacts.opened_pages}
    entity = _first_openable_entity(snapshot.session_id, opened_urls=opened_urls)
    if entity is None or not entity.canonical_url:
        return None

    from app.schemas.response import SuggestedAction

    action = SuggestedAction(
        action_id=f"orchestrator_open_recovery_{entity.entity_id[-12:]}",
        action_type="open_new_tab",
        target_selector="",
        value=entity.canonical_url,
        description=f"Open collected source: {entity.title or entity.canonical_url}",
        reasoning=(
            "Execution Orchestrator recovered an invalid planner action for the OPEN phase "
            f"by opening a registered search-result entity_id={entity.entity_id}."
        ),
        confidence=max(0.0, min(1.0, float(entity.confidence or 0.82))),
        safety_level="safe",
    )
    return AnalyzeResponse(
        session_id=result.session_id,
        analysis=(
            f"{result.analysis}\n\nExecution Orchestrator recovered the OPEN phase by selecting "
            "the first registered source entity instead of the invalid planner action."
        ),
        outcome_kind="act",
        suggested_actions=[action],
    )


def _first_openable_entity(session_id: str, *, opened_urls: set[str] | None = None):
    entities = _openable_entities_for_phase(session_id, opened_urls=opened_urls)
    return entities[0] if entities else None


def _openable_entities_for_phase(session_id: str, *, opened_urls: set[str] | None = None):
    from app.browser_url_policy import is_openable_browser_url
    from app.runtime_state_manager.entity_binding import list_entities

    opened_urls = {url for url in (opened_urls or set()) if url}
    entities = [
        entity
        for entity in list_entities(session_id)
        if entity.canonical_url
        and entity.state != "INVALID"
        and entity.entity_type in {"search_result", "semantic_element", "link", "card", "list_item", "table_row"}
        and is_openable_browser_url(entity.canonical_url)
        and _canonical_opened_url(entity.canonical_url) not in opened_urls
    ]
    return sorted(
        entities,
        key=lambda entity: (
            _entity_rank(entity),
            0 if entity.entity_type == "search_result" else 1,
            -float(entity.confidence or 0.0),
            entity.title,
            entity.entity_id,
        ),
    )


def _entity_rank(entity) -> int:
    try:
        return int((entity.metadata or {}).get("rank") or 9999)
    except (TypeError, ValueError):
        return 9999


def _canonical_opened_url(url: str) -> str:
    from urllib.parse import urlsplit, urlunsplit

    parsed = urlsplit(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/") or "/", parsed.query, "")).lower()


def _is_opened_resource(snapshot: ExecutionOrchestratorSnapshot, url: str) -> bool:
    current = _canonical_opened_url(url)
    if not current:
        return False
    return current in {_canonical_opened_url(opened) for opened in snapshot.artifacts.opened_pages}


def observe_execution_orchestrator(
    *,
    session_id: str,
    task: str,
    page_context: Any,
    prior_steps: list[Any],
) -> ExecutionOrchestratorSnapshot | None:
    return _orchestrator.build_snapshot(
        session_id=session_id,
        task=task,
        page_context=page_context,
        prior_steps=prior_steps,
    )


def enrich_planner_context_with_orchestrator(
    compressed_context: dict[str, Any],
    snapshot: ExecutionOrchestratorSnapshot | None,
) -> dict[str, Any]:
    return _orchestrator.enrich_context(compressed_context, snapshot)


def postprocess_with_orchestrator(
    result: AnalyzeResponse,
    snapshot: ExecutionOrchestratorSnapshot | None,
) -> AnalyzeResponse:
    return _orchestrator.postprocess_response(result, snapshot)
