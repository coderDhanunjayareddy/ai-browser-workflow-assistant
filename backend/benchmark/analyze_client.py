"""
M0 — /analyze client + risk gate.

Thin HTTP client that POSTs a PageContext to the LIVE backend /analyze endpoint (real
Gemini/OpenRouter reasoning) and returns the parsed suggested action. Also the risk gate
that decides safe / require-human / block per the task's HumanInterventionRules.

`requests` is imported lazily so this module imports without the dep installed (tests can
construct AnalyzeResult directly / inject a fake client).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# danger phrases — same list the production system treats as destructive/irreversible
DANGER_PHRASES = (
    "pay now", "place order", "confirm booking", "complete booking", "buy now", "purchase",
    "delete account", "delete permanently", "publish", "send email", "send message", "checkout",
)
CAUTION_PHRASES = (
    "add to cart", "submit", "save", "delete", "remove", "apply", "book", "register", "sign up",
)


@dataclass
class AnalyzeError(Exception):
    status_code: int
    detail: str
    transient: bool = False

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"AnalyzeError({self.status_code}): {self.detail}"


@dataclass
class SuggestedActionDTO:
    action_id:       str
    action_type:     str
    target_selector: str
    value:           Optional[str]
    description:     str
    reasoning:       str
    confidence:      float
    safety_level:    str


@dataclass
class ReportOutcomeDTO:
    claim:  str = ""
    answer: Optional[str] = None


@dataclass
class ReplanOutcomeDTO:
    reason: str = ""


@dataclass
class AnalyzeResult:
    analysis:               str = ""
    # Planner Contract V2: which kind of turn this is. Defaults to "act" so every
    # existing construction site (which never sets this) is unaffected.
    outcome_kind:           str = "act"
    suggested_actions:      list[SuggestedActionDTO] = field(default_factory=list)
    clarification_question: Optional[str] = None
    report:                 Optional[ReportOutcomeDTO] = None
    replan:                 Optional[ReplanOutcomeDTO] = None
    prompt_tokens:          int = 0
    completion_tokens:      int = 0

    @property
    def first_action(self) -> Optional[SuggestedActionDTO]:
        return self.suggested_actions[0] if self.suggested_actions else None


class AnalyzeClient:
    """POSTs to a running backend's /analyze. Reused for every step of every task."""

    def __init__(self, backend_url: str, timeout_s: float = 60.0) -> None:
        self.backend_url = backend_url.rstrip("/")
        self.timeout_s = timeout_s

    def analyze(self, *, session_id: str, task: str, page_context: dict,
                prior_steps: list[dict], trace_id: Optional[str] = None) -> AnalyzeResult:
        import requests  # lazy

        payload = {
            "session_id": session_id,
            "task": task,
            "page_context": page_context,
            "prior_steps": prior_steps,
            "supplemental_context": "",
        }
        # M0.6: correlate this call with the backend trace. Header is only added when a
        # trace_id is supplied (tracing runs) — normal runs send an identical request.
        headers = {"X-Trace-Id": trace_id} if trace_id else None
        try:
            resp = requests.post(f"{self.backend_url}/analyze", json=payload,
                                 timeout=self.timeout_s, headers=headers)
        except requests.exceptions.RequestException as e:
            raise AnalyzeError(503, f"backend unreachable: {type(e).__name__}: {e}", transient=True)

        if resp.status_code >= 400:
            transient = resp.status_code in (429, 502, 503, 504)
            detail = _safe_detail(resp)
            raise AnalyzeError(resp.status_code, detail, transient=transient)

        return parse_analyze_response(resp.json())


def parse_analyze_response(body: dict[str, Any]) -> AnalyzeResult:
    actions = []
    for a in body.get("suggested_actions") or []:
        actions.append(SuggestedActionDTO(
            action_id=a.get("action_id", ""),
            action_type=a.get("action_type", ""),
            target_selector=a.get("target_selector", "") or "",
            value=a.get("value"),
            description=a.get("description", ""),
            reasoning=a.get("reasoning", ""),
            confidence=float(a.get("confidence", 0.0) or 0.0),
            safety_level=a.get("safety_level", "safe"),
        ))
    usage = body.get("usage") or {}

    report_raw = body.get("report")
    report = (ReportOutcomeDTO(claim=report_raw.get("claim", ""), answer=report_raw.get("answer"))
              if isinstance(report_raw, dict) else None)
    replan_raw = body.get("replan")
    replan = (ReplanOutcomeDTO(reason=replan_raw.get("reason", ""))
              if isinstance(replan_raw, dict) else None)

    return AnalyzeResult(
        analysis=body.get("analysis", "") or "",
        outcome_kind=body.get("outcome_kind") or "act",
        suggested_actions=actions,
        clarification_question=body.get("clarification_question"),
        report=report,
        replan=replan,
        prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
        completion_tokens=int(usage.get("completion_tokens", 0) or 0),
    )


def _safe_detail(resp) -> str:
    try:
        body = resp.json()
        d = body.get("detail", body)
        return str(d)[:300]
    except Exception:
        return (resp.text or "")[:300]


# ── Risk gate ────────────────────────────────────────────────────────────────

def classify_risk(action: SuggestedActionDTO) -> str:
    """safe | caution | danger. Trusts the model's safety_level, then phrase-escalates."""
    blob = f"{action.description} {action.value or ''} {action.target_selector}".lower()
    if action.safety_level == "danger" or any(p in blob for p in DANGER_PHRASES):
        return "danger"
    if action.safety_level == "caution" or any(p in blob for p in CAUTION_PHRASES):
        return "caution"
    return action.safety_level if action.safety_level in ("safe", "caution", "danger") else "safe"


def gate_decision(risk: str, rules) -> str:
    """Returns one of: 'proceed' | 'human' | 'block'. `rules` is a HumanInterventionRules."""
    if risk == "danger":
        return {"block": "block", "require_human": "human", "auto_approve": "proceed"}.get(
            rules.danger_actions, "human")
    if risk == "caution":
        return {"require_human": "human", "auto_approve": "proceed"}.get(rules.caution_actions, "proceed")
    return "proceed"
