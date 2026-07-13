"""
Production SGV — report claim verifier.

Determines whether the current page evidence corroborates the planner's report.
Returns True (verified) or False (not verified).

This is a validator only.  It never:
  - modifies the planner response
  - selects a recovery strategy
  - triggers Goal Convergence / Planner Recovery

The caller (WorkflowOrchestrator) decides what to do with the result.

Implementation mirrors the proven benchmark SGV pattern:
  benchmark/m0_task_runner.py  TaskRunner._report_ctx() + _semantic_texts()
  benchmark/criteria.py        evaluate_success() + all_passed()
"""
from __future__ import annotations

from app.schemas.request import PageContext


def collect_page_evidence(page_context: PageContext) -> list[str]:
    """
    Extract all semantic text signals from a live page observation.

    Sources (mirrors benchmark TaskRunner._semantic_texts + _report_ctx):
      - visible_text            (primary — benchmark prepends this in _report_ctx)
      - title
      - headings
      - selected_text
      - content_blocks[].text
      - interactive_elements[].text / aria_label / accessibility_name / placeholder
      - interactive_elements[].state value / selected_text
    """
    texts: list[str] = []

    def _add(value: object) -> None:
        if value is None:
            return
        text = str(value).strip()
        if text:
            texts.append(text)

    # Core visible page text — added first so the corpus reflects reading order
    _add(page_context.visible_text)
    _add(page_context.title)

    for heading in page_context.headings or []:
        _add(heading)

    _add(page_context.selected_text)

    for block in page_context.content_blocks or []:
        _add(block.text)

    for element in page_context.interactive_elements or []:
        _add(element.text)
        _add(element.aria_label)
        _add(element.accessibility_name)
        _add(element.placeholder)
        state = element.state or {}
        _add(state.get("value"))
        _add(state.get("selected_text"))

    return texts


def verify_report(
    claim: str,
    answer: str | None,
    page_context: PageContext,
) -> bool:
    """
    Return True if the current page evidence corroborates the planner's report.

    Verification strategy (mirrors benchmark extracted_value_present criterion):
      - Require a non-empty ``answer`` — a specific extractable value the planner
        claims is present on the page.
      - Check whether that answer appears (case-insensitive substring) in the
        full evidence corpus collected from the live PageContext.
      - A bare claim with no answer cannot be objectively checked from page text
        and always returns False.
      - Empty evidence always returns False (page has nothing to confirm).

    This is a validator only.  The caller decides whether the workflow completes.
    """
    answer_text = (answer or "").strip()
    if not answer_text:
        # No specific value to locate — cannot objectively verify from page text.
        return False

    evidence = collect_page_evidence(page_context)
    if not evidence:
        return False

    corpus = "\n".join(evidence).lower()
    return answer_text.lower() in corpus
