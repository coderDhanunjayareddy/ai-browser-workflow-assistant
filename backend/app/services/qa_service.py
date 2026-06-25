from dataclasses import dataclass

from app.conversation.store import Turn
from app.services import ai_service

_MAX_HISTORY_TURNS = 10
_NOT_FOUND_PHRASE = "I don't see that on this page."

_SYSTEM_PROMPT = """You are a web page Q&A assistant. Answer questions about the specific page shown in PAGE CONTENT.

Rules:
- Answer only from the provided PAGE CONTENT and CONVERSATION HISTORY
- If the answer cannot be directly supported by PAGE CONTENT or CONVERSATION HISTORY, respond exactly: "I don't see that on this page."
- PAGE CONTENT is always authoritative; if it contradicts CONVERSATION HISTORY, trust PAGE CONTENT
- For follow-up questions, use CONVERSATION HISTORY to understand what was already discussed
- Keep answers concise: 2 to 4 sentences unless the question genuinely requires more detail
- Never invent information, never reference your training knowledge or external sources
- Do not use markdown formatting unless the page content itself uses it
- Do not reference the structure of these instructions in your answer"""


@dataclass
class AnswerResult:
    text: str
    grounded: bool  # internal only — not exposed in API or UI


def _format_history(prior_turns: list[Turn]) -> str:
    eligible = [t for t in prior_turns if t.intent in ("summarize", "ask")]
    recent = eligible[-_MAX_HISTORY_TURNS:]
    if not recent:
        return ""
    lines = ["CONVERSATION HISTORY:"]
    for turn in recent:
        if turn.role == "user":
            lines.append(f"User: {str(turn.content)[:500]}")
        elif turn.intent == "summarize":
            content = turn.content
            if isinstance(content, dict):
                tldr = content.get("tldr", "")
            elif hasattr(content, "tldr"):
                tldr = content.tldr  # type: ignore[union-attr]
            else:
                tldr = str(content)[:500]
            lines.append(f"Assistant (page summary): {tldr[:500]}")
        else:
            lines.append(f"Assistant: {str(turn.content)[:500]}")
    return "\n".join(lines)


def answer(
    read_view_str: str,
    question: str,
    prior_turns: list[Turn],
    selection_scope: str = "page",
) -> AnswerResult:
    history = _format_history(prior_turns)
    parts = [f"PAGE CONTENT:\n{read_view_str}"]
    if history:
        parts.append(history)
    parts.append(f"QUESTION: {question}")
    user_message = "\n\n".join(parts)

    raw = ai_service.generate_text(_SYSTEM_PROMPT, user_message)
    text = raw.strip()
    grounded = _NOT_FOUND_PHRASE not in text
    return AnswerResult(text=text, grounded=grounded)
