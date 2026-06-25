"""
V4.0 Component 1 — ExecutionOpportunityDetector.

Determines whether a user query contains an actionable intent beyond research.
All detection is deterministic keyword matching — no LLM, < 1 ms.

Decision table:
  Pure research    → detected=False,  action_type=unknown
  Action keywords  → detected=True,   action_type=<classified>
"""
from __future__ import annotations

from app.intelligence.models import ActionType, ExecutionOpportunity

# ── Keyword sets per action_type ──────────────────────────────────────────────

_BOOK_KW = frozenset({
    "book", "booking", "reserve", "reservation", "ticket", "flight", "hotel",
    "check in", "check-in", "check out", "check-out",
})

_PURCHASE_KW = frozenset({
    "buy", "purchase", "order", "pay", "payment", "checkout",
    "add to cart", "place order", "buy now",
})

_REGISTER_KW = frozenset({
    "register", "sign up", "signup", "subscribe", "enroll", "enrollment",
    "create account", "join",
})

_DOWNLOAD_KW = frozenset({
    "download", "install", "get app", "get the app",
})

_SCHEDULE_KW = frozenset({
    "schedule", "appointment", "meeting", "calendar", "remind", "reminder",
    "set up a call", "book a call", "book a meeting",
})

_COMMUNICATE_KW = frozenset({
    "send", "message", "email", "whatsapp", "text", "contact",
    "reply", "forward",
})

_NAVIGATE_KW = frozenset({
    "open", "go to", "navigate to", "visit", "access",
})

_RENT_KW = frozenset({
    "rent", "lease", "hire",
})

_APPLY_KW = frozenset({
    "apply", "application", "submit application",
})

# Required entities per action type (used by ReadinessAnalyzer)
_REQUIRED_ENTITIES: dict[ActionType, list[str]] = {
    ActionType.book: ["origin", "destination", "date"],
    ActionType.purchase: ["product_name"],
    ActionType.register: ["email"],
    ActionType.download: ["software_name"],
    ActionType.schedule: ["date", "time"],
    ActionType.communicate: ["recipient"],
    ActionType.navigate: [],
    ActionType.rent: ["location", "date"],
    ActionType.apply: ["position"],
    ActionType.search: [],
    ActionType.unknown: [],
}

# Human-readable missing information per entity key
_ENTITY_LABELS: dict[str, str] = {
    "origin": "departure city or airport",
    "destination": "destination city or airport",
    "date": "travel date or appointment date",
    "time": "specific time",
    "product_name": "product name or model",
    "email": "email address",
    "software_name": "software or application name",
    "recipient": "message recipient",
    "location": "location",
    "position": "job position or role",
    "check_in_date": "check-in date",
    "check_out_date": "check-out date",
}

# Workflow candidate (maps to a known workflow type in the engine)
_WORKFLOW_CANDIDATES: frozenset[ActionType] = frozenset({
    ActionType.book,
    ActionType.purchase,
    ActionType.register,
    ActionType.schedule,
    ActionType.rent,
    ActionType.apply,
    ActionType.download,
})


def _classify_action(lowered: str) -> tuple[ActionType, list[str]]:
    """Return (action_type, matched_keywords) from message text."""
    matched: list[str] = []

    for kw in _BOOK_KW:
        if kw in lowered:
            matched.append(kw)
    if matched:
        return ActionType.book, matched

    for kw in _PURCHASE_KW:
        if kw in lowered:
            matched.append(kw)
    if matched:
        return ActionType.purchase, matched

    for kw in _REGISTER_KW:
        if kw in lowered:
            matched.append(kw)
    if matched:
        return ActionType.register, matched

    for kw in _SCHEDULE_KW:
        if kw in lowered:
            matched.append(kw)
    if matched:
        return ActionType.schedule, matched

    for kw in _COMMUNICATE_KW:
        if kw in lowered:
            matched.append(kw)
    if matched:
        return ActionType.communicate, matched

    for kw in _RENT_KW:
        if kw in lowered:
            matched.append(kw)
    if matched:
        return ActionType.rent, matched

    for kw in _APPLY_KW:
        if kw in lowered:
            matched.append(kw)
    if matched:
        return ActionType.apply, matched

    for kw in _DOWNLOAD_KW:
        if kw in lowered:
            matched.append(kw)
    if matched:
        return ActionType.download, matched

    for kw in _NAVIGATE_KW:
        if kw in lowered:
            matched.append(kw)
    if matched:
        return ActionType.navigate, matched

    return ActionType.unknown, []


class ExecutionOpportunityDetector:
    """
    Detects whether a query contains an executable action intent.

    Pure keyword matching — deterministic, no LLM, zero latency overhead.
    """

    def detect(
        self,
        query: str,
        cognitive_session=None,
    ) -> ExecutionOpportunity:
        """
        Analyze a user query and return an ExecutionOpportunity.

        Args:
            query: raw user message (original, not enriched)
            cognitive_session: optional CognitiveSession for entity context
        """
        lowered = query.lower().strip()
        action_type, matched_keywords = _classify_action(lowered)

        detected = len(matched_keywords) > 0

        # Deterministic check to override matches on nouns/passive terms when the user is explicitly requesting research only
        research_keywords = {
            "research", "find info", "find information", "look up", "look into",
            "investigate", "search for", "learn about", "tell me about",
            "find info about", "learn ", "history of"
        }
        has_research_keyword = any(kw in lowered for kw in research_keywords)

        strong_action_keywords = {
            "book", "reserve", "buy", "purchase", "order", "pay", "checkout",
            "register", "sign up", "signup", "subscribe", "enroll", "download",
            "install", "schedule", "appointment", "send", "email", "whatsapp",
            "rent", "lease", "apply"
        }
        has_strong_action = any(kw in lowered for kw in strong_action_keywords)

        if has_research_keyword and not has_strong_action:
            detected = False
            action_type = ActionType.unknown
            matched_keywords = []

        confidence = 0.9 if detected else 0.0
        required_entities = _REQUIRED_ENTITIES.get(action_type, [])
        workflow_candidate = action_type in _WORKFLOW_CANDIDATES

        # Determine missing information based on what the cognitive session knows
        available_entity_names: set[str] = set()
        if cognitive_session is not None:
            for entity in cognitive_session.active_entities.values():
                available_entity_names.add(entity.name.lower())
                for alias in entity.aliases:
                    available_entity_names.add(alias.lower())

        missing_information: list[str] = []
        for req in required_entities:
            if req not in available_entity_names:
                label = _ENTITY_LABELS.get(req, req.replace("_", " "))
                missing_information.append(label)

        return ExecutionOpportunity(
            detected=detected,
            confidence=confidence,
            action_type=action_type,
            required_entities=required_entities,
            missing_information=missing_information,
            workflow_candidate=workflow_candidate,
            raw_action_keywords=matched_keywords,
        )


# Module-level singleton
detector = ExecutionOpportunityDetector()
