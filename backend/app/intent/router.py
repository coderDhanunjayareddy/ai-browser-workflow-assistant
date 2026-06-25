from dataclasses import dataclass

_SUMMARIZE = frozenset({
    "summarize", "tldr", "tl;dr", "summary", "brief",
    "overview", "in short", "shorten", "condense", "recap",
})

_RESEARCH = frozenset({
    "research", "find info", "find information",
    "look up", "look into", "investigate",
    "search for", "learn about",
})

_COMPARE = frozenset({
    "compare", "comparison", "vs", "versus",
    "difference between", "differences between",
    "which is better", "which is worse",
})

_ASK_PREFIXES = (
    "what ", "who ", "when ", "where ", "why ", "how ", "which ",
    "explain ", "tell me", "does ", "is there", "are there", "can i",
)


@dataclass
class IntentResult:
    intent: str
    route: str       # "light" | "fallback"
    confidence: float
    tier: str        # "deterministic"


def classify(message: str, selection_scope: str = "page") -> IntentResult:
    lowered = message.lower().strip()

    if any(kw in lowered for kw in _SUMMARIZE):
        return IntentResult(intent="summarize", route="light", confidence=1.0, tier="deterministic")

    if any(kw in lowered for kw in _RESEARCH):
        return IntentResult(intent="research", route="research", confidence=1.0, tier="deterministic")

    # compare checked before ask: "which is better" would otherwise match _ASK_PREFIXES
    if any(kw in lowered for kw in _COMPARE):
        return IntentResult(intent="compare", route="fallback", confidence=1.0, tier="deterministic")

    if (
        any(lowered.startswith(p) or f" {p}" in lowered for p in _ASK_PREFIXES)
        or lowered.endswith("?")
    ):
        return IntentResult(intent="ask", route="light", confidence=1.0, tier="deterministic")

    return IntentResult(intent="unknown", route="fallback", confidence=1.0, tier="deterministic")
