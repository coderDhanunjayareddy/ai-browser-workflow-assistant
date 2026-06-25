from app.services import ai_service

_MAX_FOLLOWUPS = 3

# Mirror the intent router's trigger sets — follow-up questions containing these
# words would be misclassified when the user clicks them in the UI.
_BLOCKLIST = frozenset({
    # _SUMMARIZE triggers
    "summarize", "summarise", "tl;dr", "tldr",
    "give me a summary", "in short", "condense", "recap",
    # _RESEARCH triggers
    "research", "look up", "look into", "find info",
    "find information", "investigate",
    # _COMPARE triggers
    "compare", "comparison", "versus", " vs ",
    "difference between", "differences between",
    "which is better", "which is worse",
})

_SYSTEM_PROMPT = """You generate follow-up questions for a web page assistant.

Given PAGE CONTENT and a description of the RECENT INTERACTION, produce exactly 3 follow-up questions.

Rules:
- Every question must be answerable using only the provided PAGE CONTENT — no external knowledge, no outside sources
- Questions must explore aspects of the page not already covered in RECENT INTERACTION
- Each question must be genuinely distinct in topic or angle
- Questions must be specific to this page, not generic placeholders
- Do not use these words or phrases: "research", "look up", "look into", "investigate", "find information", "compare", "comparison", "versus", "vs", "which is better", "which is worse", "difference between", "summarize", "give me a summary", "recap"
- Do not number the questions, do not use bullets or labels
- Output format: exactly 3 questions, one per line, nothing else"""


def _parse(raw: str) -> list[str]:
    lines = [ln.strip() for ln in raw.strip().splitlines()]
    questions: list[str] = []
    for line in lines:
        if not line:
            continue
        # strip leading numbering or bullet characters
        for prefix in ("1.", "2.", "3.", "4.", "-", "•", "*", "–"):
            if line.startswith(prefix):
                line = line[len(prefix):].strip()
                break
        if line:
            questions.append(line)
    return questions[:_MAX_FOLLOWUPS]


def _is_clean(question: str) -> bool:
    lowered = question.lower()
    return not any(blocked in lowered for blocked in _BLOCKLIST)


def generate(read_view_str: str, context: str) -> list[str]:
    """
    Generate up to _MAX_FOLLOWUPS follow-up questions grounded in read_view_str.

    context: one or two sentences describing the just-completed interaction
             (e.g. "User requested a summary. TL;DR: ..." or "Q: ...\nA: ...").
    Returns [] on any LLM error — never raises.
    """
    user_message = (
        f"PAGE CONTENT:\n{read_view_str}\n\n"
        f"RECENT INTERACTION:\n{context}\n\n"
        "Generate 3 follow-up questions."
    )
    try:
        raw = ai_service.generate_text(_SYSTEM_PROMPT, user_message)
        questions = _parse(raw)
        return [q for q in questions if _is_clean(q)]
    except Exception:
        return []
