from __future__ import annotations

from app.execution_orchestrator.models import PhaseName, PhaseState, ProgressLedger


DEFAULT_GRAPH: list[PhaseName] = ["DISCOVER", "COLLECT", "OPEN", "READ", "EXTRACT", "VALIDATE", "SYNTHESIZE", "REPORT", "COMPLETE"]
GRAPH_BY_CATEGORY: dict[str, list[PhaseName]] = {
    "multi_page_research": DEFAULT_GRAPH,
    "job_search": ["DISCOVER", "COLLECT", "OPEN", "EXTRACT", "VALIDATE", "SYNTHESIZE", "REPORT", "COMPLETE"],
    "file_upload": ["DISCOVER", "OPEN", "READ", "VALIDATE", "REPORT", "COMPLETE"],
    "form_filling": ["DISCOVER", "READ", "EXTRACT", "VALIDATE", "REPORT", "COMPLETE"],
    "saas_signup": ["DISCOVER", "OPEN", "READ", "VALIDATE", "REPORT", "COMPLETE"],
    "documentation_extraction": ["DISCOVER", "COLLECT", "OPEN", "READ", "EXTRACT", "SYNTHESIZE", "REPORT", "COMPLETE"],
}


ALLOWED_ACTIONS: dict[PhaseName, list[str]] = {
    "DISCOVER": ["navigate", "fill", "click", "wait", "scroll"],
    "COLLECT": ["scroll", "click", "wait", "focus_existing_tab", "switch_tab"],
    "OPEN": ["open_new_tab", "focus_existing_tab", "switch_tab", "wait"],
    "READ": ["focus_existing_tab", "switch_tab", "scroll", "wait"],
    "EXTRACT": ["focus_existing_tab", "switch_tab", "scroll", "wait"],
    "VALIDATE": ["focus_existing_tab", "switch_tab", "wait", "scroll"],
    "SYNTHESIZE": [],
    "REPORT": [],
    "COMPLETE": [],
}


FORBIDDEN_ACTIONS: dict[PhaseName, list[str]] = {
    "DISCOVER": ["close_tab"],
    "COLLECT": ["navigate"],
    "OPEN": ["navigate", "fill"],
    "READ": ["navigate", "open_new_tab", "fill", "click"],
    "EXTRACT": ["navigate", "open_new_tab", "fill", "click"],
    "VALIDATE": ["navigate", "open_new_tab"],
    "SYNTHESIZE": ["navigate", "open_new_tab", "click", "fill", "scroll", "wait"],
    "REPORT": ["navigate", "open_new_tab", "click", "fill", "scroll", "wait"],
    "COMPLETE": ["navigate", "open_new_tab", "click", "fill", "scroll", "wait"],
}


def workflow_category(task: str) -> str:
    text = task.lower()
    if any(term in text for term in ("job", "career", "opening", "linkedin")):
        return "job_search"
    if any(term in text for term in ("upload", "file accepted", "share link")):
        return "file_upload"
    if any(term in text for term in ("fill the form", "validation errors", "submit only", "form")):
        return "form_filling"
    if any(term in text for term in ("signup", "sign up", "free trial", "welcome page", "dashboard loads")):
        return "saas_signup"
    if any(term in text for term in ("documentation", "docs", "setup requirement", "supported languages")):
        return "documentation_extraction"
    return "multi_page_research"


def build_phases(category: str, ledger: ProgressLedger) -> tuple[list[PhaseState], PhaseState]:
    graph = GRAPH_BY_CATEGORY.get(category, DEFAULT_GRAPH)
    active_name = _active_phase_name(graph, ledger)
    phases: list[PhaseState] = []
    for name in graph:
        if name == active_name:
            status = "active"
        elif _phase_complete(name, ledger):
            status = "complete"
        else:
            status = "pending"
        phases.append(
            PhaseState(
                name=name,
                status=status,  # type: ignore[arg-type]
                objective=_objective(name, ledger),
                allowed_actions=ALLOWED_ACTIONS[name],
                forbidden_actions=FORBIDDEN_ACTIONS[name],
                completion_reason=_completion_reason(name, ledger) if status == "complete" else None,
            )
        )
    active = next(phase for phase in phases if phase.name == active_name)
    return phases, active


def next_phase(graph: list[PhaseName], current: PhaseName) -> PhaseName:
    try:
        return graph[min(graph.index(current) + 1, len(graph) - 1)]
    except ValueError:
        return graph[0]


def _active_phase_name(graph: list[PhaseName], ledger: ProgressLedger) -> PhaseName:
    for phase in graph:
        if not _phase_complete(phase, ledger):
            return phase
    return "COMPLETE"


def _phase_complete(phase: PhaseName, ledger: ProgressLedger) -> bool:
    return ledger.completed.get(phase.lower(), False)


def _completion_reason(phase: PhaseName, ledger: ProgressLedger) -> str:
    target_key = _target_key(phase)
    if target_key and target_key in ledger.target_counts:
        return f"{ledger.current_counts.get(target_key, 0)}/{ledger.target_counts[target_key]} {target_key} reached"
    return "phase evidence satisfied"


def _objective(phase: PhaseName, ledger: ProgressLedger) -> str:
    target_key = _target_key(phase)
    if target_key and target_key in ledger.target_counts:
        return f"{phase}: reach {ledger.target_counts[target_key]} {target_key}; currently {ledger.current_counts.get(target_key, 0)}"
    objectives = {
        "DISCOVER": "Find the starting page or source surface for this mission.",
        "COLLECT": "Collect candidate entities or sources without opening more than required.",
        "OPEN": "Open the selected entities needed by later phases.",
        "READ": "Read already opened pages or current artifacts; do not collect more.",
        "EXTRACT": "Extract requested fields from read artifacts.",
        "VALIDATE": "Validate extracted records and required evidence.",
        "SYNTHESIZE": "Synthesize final answer from artifacts.",
        "REPORT": "Return the final user-facing output.",
        "COMPLETE": "Mission complete.",
    }
    return objectives[phase]


def _target_key(phase: PhaseName) -> str | None:
    if phase == "OPEN":
        return "opened_pages"
    if phase == "COLLECT":
        return "collected_items"
    if phase == "EXTRACT":
        return "extracted_records"
    return None
